"""Conflict-safe, crash-consistent save of an import's translation files (Qt-free).

``TranslationCommit.commit`` saves the project file together with the
translation files that an import staged (Pending_Translation), following steps
S1 to S8 of design Component 10. Before anything is written it verifies the
SHA-256 digest of every file it will replace (Digest_Verification: state OLD,
NEW or OTHER). A file in state OTHER was changed outside Släktbusken and is
never overwritten.

``recover_translation_intent`` runs at open and finishes or discards an
interrupted save by the decision table of the design. A combination it cannot
explain is refused (codes T1 to T5) through ``RecoveryRefusedError``, the
mechanism the merge recovery already uses; no file is changed then.

All file access goes through the ``CommitFs`` protocol, so tests can inject
faults at every operation.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from slaktbusken.persistence import translation_io
from slaktbusken.services.commit.fs_ops import CommitFs, RealFs
from slaktbusken.services.commit.journal import (
    SCHEMA,
    _checksum_ok,
    _req,
    _serialize,
    _with_checksum,
    sha256_hex,
    temp_path_for,
)
from slaktbusken.services.commit.preflight import Preflight
from slaktbusken.services.commit.recovery import (
    RecoveryKind,
    RecoveryOutcome,
    RecoveryRefusal,
    RecoveryRefusedError,
)

__all__ = [
    "ABSENT",
    "TRANSLATION_FILES",
    "ImportSaveRefusal",
    "ImportSaveUnfinished",
    "SaveConflict",
    "SaveFailed",
    "TranslationCommit",
    "intent_path_for",
    "recover_translation_intent",
]

logger = logging.getLogger(__name__)

#: Marker digest of a file that does not exist.
ABSENT = "absent"

#: Translation files in name order (the order in which they are replaced).
TRANSLATION_FILES: tuple[str, ...] = (
    "translation/persons.json",
    "translation/places.json",
    "translation/sources.json",
)

# Digest states.
OLD = "OLD"
NEW = "NEW"
OTHER = "OTHER"
MISSING = "MISSING"
ERROR = "ERROR"

_STATE_TEXT = {
    OLD: "oförändrad",
    NEW: "ny",
    OTHER: "okänd, ändrad utanför Släktbusken",
    MISSING: "saknas",
    ERROR: "kunde inte läsas",
}

# Swedish messages (design Component 10 and Requirements 20.8, 20.9, 20.11, 20.19, 20.20).
MSG_UNOWNED_STATE = "okänd, ändrad utanför Släktbusken"
MSG_SAVE_FAILED = "Projektet kunde inte sparas. Inga filer ändrades."
MSG_UNFINISHED_SAVED = (
    "Projektet är sparat. Översättningsfilerna slutförs när projektet öppnas nästa gång."
)
MSG_UNFINISHED_BLOCK = (
    "En sparning av en import är inte avslutad. Starta om Släktbusken för att "
    "slutföra eller kontrollera filerna."
)
MSG_RECOVERY_COMPLETED = "En avbruten sparning slutfördes."
MSG_RECOVERY_ROLLED_BACK = "En avbruten sparning återställdes."

_CONFLICT_TAIL = (
    "Inga filer har ändrats. Återställ filen och välj Spara igen, eller stäng "
    "projektet utan att spara och importera GEDCOM-filen på nytt."
)

_REFUSAL_REASONS = {
    "T1": "Projektfilen stämmer varken med läget före eller efter sparningen.",
    "T2": "En översättningsfil stämmer varken med läget före eller efter sparningen.",
    "T3": "Filerna är i en kombination som inte kan förklaras av sparningen.",
    "T4": "Importintentionen är skadad eller har ett okänt format.",
    "T5": "En fil kunde inte läsas. Ingenting har ändrats. Försök igen när filen går att läsa.",
}


# --------------------------------------------------------------------------
# Errors


class SaveConflict(Exception):
    """A file was changed outside Släktbusken; nothing was replaced (Requirement 20.8)."""

    def __init__(self, files: list[str] | tuple[str, ...]) -> None:
        self.files: tuple[str, ...] = tuple(files)
        self.message = _conflict_message(self.files)
        super().__init__(self.message)


class SaveFailed(Exception):
    """The save failed before the project file was replaced (Requirement 20.9).

    ``unresolved`` is True when the outcome of the commit point could not be
    determined; the artifacts were kept and the caller must treat the save as
    unfinished (block further saves until the project is reopened).
    """

    def __init__(self, message: str = MSG_SAVE_FAILED, *, unresolved: bool = False) -> None:
        self.message = message
        self.unresolved = unresolved
        super().__init__(message)


class ImportSaveUnfinished(Exception):
    """The project file was replaced but the translation files were not finished.

    ``files`` names the files found in state OTHER (a conflict); it is empty
    for an error. The intent and the temporary files were kept.
    """

    def __init__(self, files: list[str] | tuple[str, ...] = ()) -> None:
        self.files: tuple[str, ...] = tuple(files)
        if self.files:
            names = ", ".join(self.files)
            word = "översättningsfilen" if len(self.files) == 1 else "översättningsfilerna"
            self.message = (
                f"Projektet är sparat, men {word} {names} har ändrats utanför "
                f"Släktbusken och skrevs inte över. Starta om Släktbusken för att "
                f"kontrollera filerna."
            )
        else:
            self.message = MSG_UNFINISHED_SAVED
        super().__init__(self.message)


def _conflict_message(files: tuple[str, ...]) -> str:
    lines = "\n".join(f"  - {f}  ({MSG_UNOWNED_STATE})" for f in files)
    return (
        f"Projektet sparades inte. {len(files)} fil(er) har ändrats utanför "
        f"Släktbusken sedan importen:\n{lines}\n{_CONFLICT_TAIL}"
    )


# --------------------------------------------------------------------------
# Paths, digests and states


def intent_path_for(project_file: Path) -> Path:
    """``<project file name>.import-intent.json`` beside the project file."""
    project_file = Path(project_file)
    return project_file.with_name(project_file.name + ".import-intent.json")


def _path_of(directory: Path, name: str) -> Path:
    return directory.joinpath(*name.split("/"))


def _digest(fs: CommitFs, path: Path) -> str:
    """SHA-256 of the file bytes, or ``ABSENT``. Raises OSError when unreadable."""
    if not fs.exists(path):
        return ABSENT
    return sha256_hex(fs.read_bytes(path))


def _state(actual: str, old: str, new: str) -> str:
    """OLD, NEW or OTHER. When ``old == new`` the state is OLD (or OTHER)."""
    if actual == old:
        return OLD
    if actual == new:
        return NEW
    return OTHER


def _is_digest(value: Any) -> bool:
    if value == ABSENT:
        return True
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


# --------------------------------------------------------------------------
# Translation_Intent


@dataclass(frozen=True)
class _FileEntry:
    name: str  # "translation/places.json"
    old: str
    new: str
    content: bytes  # new content


@dataclass(frozen=True)
class _Intent:
    txid: str
    project_name: str
    old_project: str
    new_project: str
    files: tuple[_FileEntry, ...]


def _build_intent_bytes(intent: _Intent) -> bytes:
    body = {
        "schema": SCHEMA,
        "kind": "import-save",
        "txid": intent.txid,
        "project_file": intent.project_name,
        "old_project_sha256": intent.old_project,
        "new_project_sha256": intent.new_project,
        "files": [
            {
                "name": f.name,
                "old_sha256": f.old,
                "new_sha256": f.new,
                "content_b64": base64.b64encode(f.content).decode("ascii"),
            }
            for f in intent.files
        ],
    }
    return _serialize(_with_checksum(body, "checksum"))


def _parse_intent(raw: bytes) -> Optional[_Intent]:
    """The intent, or ``None`` when it is damaged, has a wrong checksum or an unknown schema."""
    try:
        doc = json.loads(raw.decode("utf-8"))
        if not isinstance(doc, dict) or not _checksum_ok(doc, "checksum"):
            return None
        if _req(doc, "schema", int) != SCHEMA or _req(doc, "kind", str) != "import-save":
            return None
        txid = _req(doc, "txid", str)
        if not re.fullmatch(r"[0-9a-zA-Z]{4,64}", txid):
            return None
        old_p = _req(doc, "old_project_sha256", str)
        new_p = _req(doc, "new_project_sha256", str)
        if not (_is_digest(old_p) and _is_digest(new_p)):
            return None
        entries: list[_FileEntry] = []
        for item in _req(doc, "files", list):
            if not isinstance(item, dict):
                return None
            name = _req(item, "name", str)
            if name not in TRANSLATION_FILES:
                return None
            old = _req(item, "old_sha256", str)
            new = _req(item, "new_sha256", str)
            content = base64.b64decode(_req(item, "content_b64", str), validate=True)
            if not (_is_digest(old) and _is_digest(new)) or sha256_hex(content) != new:
                return None
            entries.append(_FileEntry(name, old, new, content))
        if len({e.name for e in entries}) != len(entries):
            return None
        return _Intent(txid, _req(doc, "project_file", str), old_p, new_p, tuple(entries))
    except (ValueError, UnicodeDecodeError, TypeError):
        return None


# --------------------------------------------------------------------------
# Stray temporary files of this protocol

_TEMP_RE = re.compile(r"^(?P<base>.+)\.(?P<txid>[0-9a-zA-Z]{4,64})\.new$")


def _listdir(fs: CommitFs, directory: Path) -> list[str]:
    try:
        return sorted(fs.listdir(directory)) if fs.exists(directory) else []
    except OSError:
        return []


def _stray_temps(fs: CommitFs, project_file: Path) -> list[Path]:
    """Every ``<target>.<txid>.new`` of this protocol beside the project file.

    Targets are the project file, its intent and the three translation files.
    """
    directory = project_file.parent
    bases = {project_file.name, intent_path_for(project_file).name}
    found: list[Path] = []
    for n in _listdir(fs, directory):
        m = _TEMP_RE.match(n)
        if m and m.group("base") in bases:
            found.append(directory / n)
    tdir = directory / "translation"
    tbases = {n.split("/", 1)[1] for n in TRANSLATION_FILES}
    for n in _listdir(fs, tdir):
        m = _TEMP_RE.match(n)
        if m and m.group("base") in tbases:
            found.append(tdir / n)
    return found


# --------------------------------------------------------------------------
# Refusal (Conflict_Refusal at open)


@dataclass(frozen=True)
class ImportSaveRefusal:
    """Why an interrupted import save could not be resolved at open (T1 to T5)."""

    code: str
    project_path: Path
    intent_path: Path
    temp_paths: tuple[Path, ...] = ()
    #: (relative file name, state code) of each translation file named in the intent.
    file_states: tuple[tuple[str, str], ...] = ()
    #: State code of the project file; empty when it was not examined (T4, T5).
    project_state: str = ""

    @property
    def reason(self) -> str:
        return _REFUSAL_REASONS.get(self.code, "")

    @property
    def message(self) -> str:
        def label(code: str) -> str:
            return f"   ({_STATE_TEXT.get(code, code)})" if code else ""

        files = (
            "\n".join(f"  - {n}{label(s)}" for n, s in self.file_states)
            if self.file_states
            else "  (ingen uppgift)"
        )
        temps = (
            "\n".join(f"                      {p}" for p in self.temp_paths).lstrip()
            if self.temp_paths
            else "inga"
        )
        return (
            "Projektet kunde inte öppnas. En tidigare sparning av en import avbröts, och Släktbusken kan inte avgöra\n"
            "säkert hur filerna ska slutföras, eftersom en eller flera filer har ändrats utanför Släktbusken.\n"
            "\n"
            f"Orsak: {self.reason}\n"
            "\n"
            f"Projektfil:           {self.project_path}{label(self.project_state)}\n"
            f"Importintention:      {self.intent_path}\n"
            f"Översättningsfiler:\n{files}\n"
            f"Temporära filer:      {temps}\n"
            "\n"
            "Alla dessa filer har lämnats orörda. Ta inte bort dem.\n"
            "Nästa steg: återställ de filer som är markerade \"okänd\" från en säkerhetskopia eller versionshistorik.\n"
            "När filerna är kontrollerade: flytta importintentionen ut ur projektmappen och starta om Släktbusken."
        )

    # Read by ``log_recovery_refusal`` through ``getattr``.
    @property
    def journal_path(self) -> Path:
        return self.intent_path

    @property
    def backup_dir(self) -> None:
        return None


# --------------------------------------------------------------------------
# Commit


class _PendingLike(Protocol):
    data: translation_io.TranslationData
    base: dict[str, str]


@dataclass
class _Item:
    name: str
    path: Path
    old: str
    new: str
    content: bytes

    @property
    def changed(self) -> bool:
        return self.old != self.new


def _encode_translation(data: translation_io.TranslationData) -> dict[str, bytes]:
    return {
        "translation/persons.json": translation_io.dumps_persons(
            data.persons, data.families, data.person_aliases
        ),
        "translation/places.json": translation_io.dumps_places(data.places),
        "translation/sources.json": translation_io.dumps_sources(data.sources),
    }


class TranslationCommit:
    """Saves the project file and the staged translation files (S1 to S8)."""

    def __init__(
        self,
        project_file: Path,
        fs: CommitFs | None = None,
        *,
        txid: str | None = None,
    ) -> None:
        self.project_file = Path(project_file)
        self.directory = self.project_file.parent
        self.fs: CommitFs = fs if fs is not None else RealFs()
        self.txid = txid or uuid.uuid4().hex[:16]
        self.intent_path = intent_path_for(self.project_file)

    # -- public ------------------------------------------------------------

    def commit(
        self,
        project_bytes: bytes,
        pending: _PendingLike,
        expected_project_digest: str,
    ) -> str:
        """Run the save protocol; return the SHA-256 of the new project file.

        Raises:
            SaveConflict: a file is in state OTHER before the commit point.
                Nothing was replaced; artifacts this attempt created were removed.
            SaveFailed: an error before the commit point (same cleanup), or an
                undeterminable commit point (``unresolved``; artifacts kept).
            ImportSaveUnfinished: the project file was replaced but a
                translation file was not finished; intent and temps kept.
        """
        fs = self.fs
        new_project = sha256_hex(project_bytes)
        items = self._plan(pending)
        changed = [i for i in items if i.changed]
        created: list[Path] = []  # artifacts of this attempt, oldest first

        # S1: pre-flight and Digest_Verification; nothing is written.
        try:
            self._preflight(changed, len(project_bytes))
            if fs.exists(self.intent_path):
                raise SaveFailed(
                    f"Projektet sparades inte. Importintentionen {self.intent_path.name} finns "
                    f"redan. Starta om Släktbusken för att slutföra eller kontrollera filerna."
                )
            others = self._verify(expected_project_digest, new_project, items)
        except SaveFailed:
            raise
        except Exception as exc:  # noqa: BLE001 - any error means: refuse, nothing written
            logger.exception("Kontrollen före sparning av import misslyckades.")
            raise SaveFailed() from exc
        if others:
            raise SaveConflict(others)

        project_tmp = temp_path_for(self.project_file, self.txid)
        intent_tmp = temp_path_for(self.intent_path, self.txid)
        file_tmps = {i.name: temp_path_for(i.path, self.txid) for i in changed}

        # S2 to S6: everything before the commit point.
        try:
            intent = _Intent(
                self.txid,
                self.project_file.name,
                expected_project_digest,
                new_project,
                tuple(_FileEntry(i.name, i.old, i.new, i.content) for i in changed),
            )
            # S2
            created.append(intent_tmp)
            fs.write_file_durable(intent_tmp, _build_intent_bytes(intent))
            # S3
            created.append(self.intent_path)
            fs.replace(intent_tmp, self.intent_path)
            fs.fsync_dir(self.directory)
            # S4
            created.append(project_tmp)
            fs.write_file_durable(project_tmp, project_bytes)
            self._check_written(project_tmp, new_project)
            # S5
            for i in changed:
                tmp = file_tmps[i.name]
                if not fs.exists(i.path.parent):
                    fs.mkdir(i.path.parent)
                created.append(tmp)
                fs.write_file_durable(tmp, i.content)
                self._check_written(tmp, i.new)
            # S6: verify again, then the commit point.
            others = self._verify(expected_project_digest, new_project, items)
            if others:
                self._cleanup(created)
                raise SaveConflict(others)
            committed = self._replace_project(project_tmp, new_project)
            if not committed:
                self._cleanup(created)
                raise SaveFailed()
        except (SaveConflict, SaveFailed, ImportSaveUnfinished):
            raise
        except Exception as exc:  # noqa: BLE001 - error before the commit point
            logger.exception("Sparning av import misslyckades före checkpunkten.")
            self._cleanup(created)
            raise SaveFailed() from exc

        # S7: the project file is new. Keep the intent and temps from here on.
        for i in changed:
            tmp = file_tmps[i.name]
            try:
                state = _state(_digest(fs, i.path), i.old, i.new)
                if state == OLD:
                    committed_file = self._replace_file(tmp, i)
                    if not committed_file:
                        raise ImportSaveUnfinished(())
                elif state == NEW:
                    fs.remove(tmp)
                else:
                    raise ImportSaveUnfinished((i.name,))
            except ImportSaveUnfinished:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("Översättningsfilen %s kunde inte slutföras.", i.name)
                raise ImportSaveUnfinished(()) from exc

        # S8
        try:
            for stray in _stray_temps(fs, self.project_file):
                fs.remove(stray)
            fs.remove(self.intent_path)
            fs.fsync_dir(self.directory)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Importintentionen kunde inte tas bort.")
            raise ImportSaveUnfinished(()) from exc
        return new_project

    # -- helpers -----------------------------------------------------------

    def _plan(self, pending: _PendingLike) -> list[_Item]:
        contents = _encode_translation(pending.data)
        items: list[_Item] = []
        for name in TRANSLATION_FILES:
            content = contents[name]
            items.append(
                _Item(
                    name,
                    _path_of(self.directory, name),
                    pending.base.get(name, ABSENT),
                    sha256_hex(content),
                    content,
                )
            )
        return items

    def _preflight(self, changed: list[_Item], project_size: int) -> None:
        refusals = Preflight.check([self.project_file], self.directory, project_size)
        tdir = self.directory / "translation"
        if changed and tdir.exists():
            refusals += Preflight.check(
                [i.path for i in changed], tdir, sum(len(i.content) for i in changed)
            )
        if refusals:
            raise SaveFailed(MSG_SAVE_FAILED + "\n" + "\n".join(refusals))

    def _verify(self, expected_project: str, new_project: str, items: list[_Item]) -> list[str]:
        """Names of the files in state OTHER (project file first)."""
        others: list[str] = []
        if _state(_digest(self.fs, self.project_file), expected_project, new_project) != OLD:
            others.append(self.project_file.name)
        for i in items:
            if _state(_digest(self.fs, i.path), i.old, i.new) == OTHER:
                others.append(i.name)
        return others

    def _check_written(self, tmp: Path, expected: str) -> None:
        if sha256_hex(self.fs.read_bytes(tmp)) != expected:
            raise OSError(f"Den temporära filen {tmp.name} skrevs inte korrekt.")

    def _replace_project(self, tmp: Path, new_digest: str) -> bool:
        """Replace the project file. True when it is new afterwards.

        False when it is certainly not replaced. Raises ``SaveFailed``
        (``unresolved``) when the outcome cannot be determined.
        """
        try:
            self.fs.replace(tmp, self.project_file)
            return True
        except Exception:  # noqa: BLE001
            logger.exception("Projektfilen kunde inte ersättas.")
            try:
                return _digest(self.fs, self.project_file) == new_digest
            except Exception as exc:  # noqa: BLE001
                raise SaveFailed(MSG_SAVE_FAILED, unresolved=True) from exc

    def _replace_file(self, tmp: Path, item: _Item) -> bool:
        """Replace a translation file. True when it is new afterwards."""
        try:
            self.fs.replace(tmp, item.path)
            return True
        except Exception:  # noqa: BLE001
            logger.exception("Översättningsfilen %s kunde inte ersättas.", item.name)
            try:
                return _digest(self.fs, item.path) == item.new
            except Exception:  # noqa: BLE001
                return False

    def _cleanup(self, created: list[Path]) -> None:
        """Remove only the artifacts this attempt created (temps first, intent last)."""
        ordered = [p for p in created if p != self.intent_path] + (
            [self.intent_path] if self.intent_path in created else []
        )
        for p in ordered:
            try:
                self.fs.remove(p)
            except Exception:  # noqa: BLE001
                logger.exception("Kunde inte ta bort %s.", p)


# --------------------------------------------------------------------------
# Recovery at open


def recover_translation_intent(
    project_file: Path, fs: CommitFs | None = None
) -> RecoveryOutcome | None:
    """Finish or discard an interrupted import save (decision table of the design).

    Returns ``None`` when no intent exists (leftover temps are removed), a
    ``RecoveryOutcome`` after completing or discarding, and raises
    ``RecoveryRefusedError`` (``ImportSaveRefusal``, T1 to T5) when the files
    cannot be explained. Nothing is written in the refusal rows. Idempotent.
    """
    project_file = Path(project_file)
    fs = fs if fs is not None else RealFs()
    directory = project_file.parent
    intent_path = intent_path_for(project_file)

    def refuse(
        code: str,
        project_state: str = "",
        states: tuple[tuple[str, str], ...] = (),
        extra: tuple[Path, ...] = (),
    ) -> RecoveryRefusedError:
        temps: dict[Path, None] = {}
        for p in (*extra, *_stray_temps(fs, project_file)):
            try:
                if fs.exists(p):
                    temps[p] = None
            except OSError:
                pass
        return RecoveryRefusedError(
            _as_refusal(
                ImportSaveRefusal(
                    code, project_file, intent_path, tuple(temps), states, project_state
                )
            )
        )

    try:
        has_intent = fs.exists(intent_path)
    except OSError:
        raise refuse("T5") from None
    if not has_intent:
        for stray in _stray_temps(fs, project_file):
            fs.remove(stray)
        return None

    try:
        raw = fs.read_bytes(intent_path)
    except OSError:
        raise refuse("T5") from None
    intent = _parse_intent(raw)
    if intent is None or intent.project_name != project_file.name:
        raise refuse("T4")

    # Read every file once, before any write.
    try:
        actual_project = _digest(fs, project_file)
        actual_files = {
            e.name: _digest(fs, _path_of(directory, e.name)) for e in intent.files
        }
    except OSError:
        raise refuse("T5") from None

    p_state = _state(actual_project, intent.old_project, intent.new_project)
    if p_state == OLD and intent.old_project == intent.new_project:
        # The save did not change the project bytes (same data, same gzip
        # second), so "before" and "after" the project replace look the same.
        # Rolling forward gives the state the save was meant to produce, and
        # avoids a false T3 when a translation file is already new.
        p_state = NEW
    f_states = {e.name: _state(actual_files[e.name], e.old, e.new) for e in intent.files}

    def view(project: str) -> tuple[str, tuple[tuple[str, str], ...]]:
        return project, tuple((n, s) for n, s in f_states.items())

    if p_state == OTHER:
        shown = MISSING if actual_project == ABSENT else OTHER
        raise refuse("T1", *view(shown))
    if any(s == OTHER for s in f_states.values()):
        raise refuse("T2", *view(p_state))
    if p_state == OLD and any(s == NEW for s in f_states.values()):
        raise refuse("T3", *view(p_state))

    if p_state == OLD:  # every file OLD: discard
        _remove_artifacts(fs, project_file, intent_path)
        return RecoveryOutcome(RecoveryKind.ROLLED_BACK, MSG_RECOVERY_ROLLED_BACK)

    # Project NEW, every file OLD or NEW: complete.
    for e in intent.files:
        path = _path_of(directory, e.name)
        # Verify immediately before the write.
        try:
            now = _state(_digest(fs, path), e.old, e.new)
        except OSError:
            raise refuse("T5") from None
        if now == NEW:
            continue
        if now == OTHER:
            f_states[e.name] = OTHER
            raise refuse("T2", *view(NEW))
        tmp = temp_path_for(path, intent.txid)
        if not fs.exists(path.parent):
            fs.mkdir(path.parent)
        fs.write_file_durable(tmp, e.content)
        if sha256_hex(fs.read_bytes(tmp)) != e.new:
            raise OSError(f"Den temporära filen {tmp.name} skrevs inte korrekt.")
        try:
            now = _state(_digest(fs, path), e.old, e.new)
        except OSError:
            raise refuse("T5", extra=(tmp,)) from None
        if now == OTHER:
            f_states[e.name] = OTHER
            raise refuse("T2", *view(NEW), extra=(tmp,))
        if now == OLD:
            fs.replace(tmp, path)
        else:
            fs.remove(tmp)

    # Remove the intent only after every file is NEW.
    try:
        final = {e.name: _digest(fs, _path_of(directory, e.name)) for e in intent.files}
    except OSError:
        raise refuse("T5") from None
    for e in intent.files:
        if final[e.name] != e.new:
            f_states[e.name] = _state(final[e.name], e.old, e.new)
            raise refuse("T2", *view(NEW))
    _remove_artifacts(fs, project_file, intent_path)
    return RecoveryOutcome(RecoveryKind.COMPLETED, MSG_RECOVERY_COMPLETED)


def _remove_artifacts(fs: CommitFs, project_file: Path, intent_path: Path) -> None:
    """Remove the temps of the protocol, then the intent (last)."""
    for stray in _stray_temps(fs, project_file):
        fs.remove(stray)
    fs.remove(intent_path)
    fs.fsync_dir(project_file.parent)


def _as_refusal(refusal: ImportSaveRefusal) -> RecoveryRefusal:
    """``RecoveryRefusedError`` reads ``.message`` and stores the object as ``.refusal``.

    The import refusal is duck-typed to the merge refusal; typing is relaxed here.
    """
    return refusal  # type: ignore[return-value]
