"""MergeTransaction: the atomic commit of project file and persons.json (Qt-free).

Implements design section 13.2 (Requirements 27.14, 27.15, 27.17, 7.9, 7.10, 7.12):

    P0 pre-flight, P1 lock, P2 on-disk Recovery_Point (backup directory with
    manifest), (a) temp files written, fsynced and verified, (b) journal
    written atomically, (c) flush barrier, (d) replace persons.json (T) first
    and the project file (P) last (the logical commit point), (e) remove the
    journal, (f) remove backup directory, temps and lock.

The transaction handles bytes only; the caller prepares them with
``FilePersistence.encode`` and ``translation_io.dumps_persons``.

Failure policy
--------------
* Only ``Exception`` is caught, at the protocol runner and in the cleanup
  steps. A ``BaseException`` (a simulated or real crash) propagates and leaves
  every artifact in place for startup recovery. There is no ``finally`` that
  removes artifacts.
* An ``Exception`` before the journal is started removes what the transaction
  created (temps, backup directory, lock). That is the state the recovery
  function would produce for a crash at that point.
* An ``Exception`` from the moment the journal write starts runs the recovery
  function (the same decision as after a crash at that point). If the recovery
  decision is a refusal, ``RecoveryRefusedError`` propagates unchanged.
"""

from __future__ import annotations

import gzip
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from slaktbusken.services.commit.fs_ops import CommitFs, RealFs
from slaktbusken.services.commit.journal import (
    BackupManifest,
    JournalTarget,
    ManifestFile,
    MergeJournal,
    backup_dir_for,
    journal_path_for,
    journal_tmp_path_for,
    lock_path_for,
    sha256_hex,
    temp_path_for,
    write_journal,
    write_manifest,
)
from slaktbusken.services.commit.preflight import Preflight

__all__ = [
    "CommitRefused",
    "CommitFailed",
    "CommitResult",
    "MergeTransaction",
    "persons_path_for",
    "PROJECT_BACKUP_NAME",
    "PERSONS_BACKUP_NAME",
]

PROJECT_BACKUP_NAME = "project.json.gz"
PERSONS_BACKUP_NAME = "persons.json"

LOCK_EXISTS_MESSAGE = "En annan sammanslagning pågår eller avbröts. Öppna projektet på nytt."


def persons_path_for(project_file: Path) -> Path:
    """``translation/persons.json`` beside the project file."""
    return Path(project_file).parent / "translation" / "persons.json"


class CommitRefused(Exception):
    """Pre-flight or lock refusal. Nothing was created or changed."""

    def __init__(self, messages: list[str]) -> None:
        super().__init__("\n".join(messages))
        self.messages = list(messages)


class CommitFailed(Exception):
    """The commit failed and the disk is in the old state.

    ``recovery_error`` holds an error raised by the recovery function itself
    (the artifacts are then left for startup recovery).
    """

    def __init__(
        self,
        message: str,
        *,
        cause: BaseException | None = None,
        recovery_error: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.cause = cause
        self.recovery_error = recovery_error


@dataclass(frozen=True)
class CommitResult:
    """Outcome of a commit that ended in the NEW state.

    ``recovered`` is true when an error occurred after the journal existed and
    the recovery decision rolled forward (or found everything complete).
    """

    txid: str
    recovered: bool = False
    recovery_outcome: Any = None


@dataclass
class _Target:
    role: str
    path: Path
    tmp: Path
    new: bytes
    existed: bool
    old: bytes
    backup_name: str  # file name inside the backup directory ("" when absent before)


def _default_recover() -> Callable[..., Any] | None:
    try:
        from slaktbusken.services.commit.recovery import recover_if_needed
    except ImportError:  # recovery module not available (task 13.4)
        return None
    return recover_if_needed


class MergeTransaction:
    """One atomic commit of the project file and, optionally, persons.json."""

    def __init__(
        self,
        project_file: Path,
        fs: CommitFs | None = None,
        *,
        recover: Callable[..., Any] | None = None,
        app_version: str = "unknown",
        txid_factory: Callable[[], str] = lambda: secrets.token_hex(6),
        preflight: Callable[..., list[str]] = Preflight.check,
    ) -> None:
        self.project_file = Path(project_file)
        self.directory = self.project_file.parent
        self.persons_file = persons_path_for(self.project_file)
        self.fs: CommitFs = fs if fs is not None else RealFs()
        self._recover = recover
        self._app_version = app_version
        self._txid_factory = txid_factory
        self._preflight = preflight

    # ------------------------------------------------------------------
    # Public API

    def commit(
        self,
        project_bytes: bytes,
        persons_bytes: bytes | None = None,
        *,
        revision_before: int = 0,
    ) -> CommitResult:
        """Commit ``project_bytes`` (and ``persons_bytes`` when not None).

        Raises ``CommitRefused`` (nothing changed), ``CommitFailed`` (disk is
        in the old state) or ``RecoveryRefusedError`` (from the recovery
        function; every artifact preserved). Returns a ``CommitResult`` when
        the new state is in place.
        """
        fs = self.fs
        txid = self._txid_factory()
        P = self.project_file

        # -- read the saved files (the Recovery_Point content) -----------
        try:
            old_p = fs.read_bytes(P)
            t_exists = fs.exists(self.persons_file)
            old_t = fs.read_bytes(self.persons_file) if t_exists else b""
        except Exception as exc:  # noqa: BLE001 - reported as a refusal
            raise CommitRefused(
                [f"Filen {P.name} eller translation/persons.json kunde inte läsas: {exc}"]
            ) from exc

        targets: list[_Target] = []  # commit order: T first, P last
        if persons_bytes is not None:
            targets.append(
                _Target(
                    "persons",
                    self.persons_file,
                    temp_path_for(self.persons_file, txid),
                    persons_bytes,
                    t_exists,
                    old_t,
                    PERSONS_BACKUP_NAME if t_exists else "",
                )
            )
        targets.append(
            _Target(
                "project",
                P,
                temp_path_for(P, txid),
                project_bytes,
                True,
                old_p,
                PROJECT_BACKUP_NAME,
            )
        )

        # -- P0 pre-flight (changes nothing) -----------------------------
        check_paths = [t.path for t in targets]
        needed = sum(len(t.new) for t in targets)
        refusals = self._preflight(
            check_paths, self.directory, needed, project_file=P
        )
        if refusals:
            raise CommitRefused(list(refusals))

        # -- P1 lock ------------------------------------------------------
        lock = lock_path_for(P)
        try:
            fs.create_exclusive(lock)
        except FileExistsError as exc:
            raise CommitRefused([LOCK_EXISTS_MESSAGE]) from exc
        except Exception as exc:  # noqa: BLE001
            raise CommitRefused(
                [f"Låsfilen {lock.name} kunde inte skapas: {exc}"]
            ) from exc

        # From here on the lock is ours. Track how far the protocol got.
        journal_started = False
        created_dirs: list[Path] = []
        try:
            # -- P2 Recovery_Point on disk -------------------------------
            self._take_recovery_point(txid, targets, old_p, t_exists, old_t, persons_bytes)

            # -- (a) temp files ------------------------------------------
            tdir = self.persons_file.parent
            if persons_bytes is not None and not fs.exists(tdir):
                fs.mkdir(tdir)
                fs.fsync_dir(self.directory)
                created_dirs.append(tdir)
            for t in targets:
                fs.write_file_durable(t.tmp, t.new)
            for t in targets:
                back = fs.read_bytes(t.tmp)
                if sha256_hex(back) != sha256_hex(t.new) or len(back) != len(t.new):
                    raise OSError(f"Den temporära filen {t.tmp.name} stämmer inte efter skrivning.")
            self._verify_project_bytes(project_bytes)

            # -- (b) journal, (c) flush barrier --------------------------
            journal = self._build_journal(txid, targets, revision_before)
            journal_started = True
            write_journal(fs, P, journal)
            fs.fsync_dir(self.directory)

            # -- (d) replace targets: T first, P last --------------------
            for t in targets:
                fs.replace(t.tmp, t.path)

            # -- (e) remove the journal ----------------------------------
            fs.remove(journal_path_for(P))
        except Exception as exc:  # noqa: BLE001 - same decision as a crash here
            return self._handle_error(
                exc, txid, targets, journal_started, lock_held=True
            )

        # -- (f) cleanup: never affects data ------------------------------
        self._cleanup_after_commit(txid, targets)
        return CommitResult(txid=txid)

    # ------------------------------------------------------------------
    # Protocol pieces

    def _take_recovery_point(
        self,
        txid: str,
        targets: list[_Target],
        old_p: bytes,
        t_exists: bool,
        old_t: bytes,
        persons_bytes: bytes | None,
    ) -> None:
        """P2: backup directory with verified copies and a manifest."""
        fs = self.fs
        bdir = backup_dir_for(self.directory, txid)
        fs.mkdir(bdir)
        fs.fsync_dir(self.directory)

        files: list[ManifestFile] = []
        absent: list[str] = []

        fs.copy_file_durable(self.project_file, bdir / PROJECT_BACKUP_NAME)
        copy = fs.read_bytes(bdir / PROJECT_BACKUP_NAME)
        if sha256_hex(copy) != sha256_hex(old_p):
            raise OSError(f"Säkerhetskopian av {self.project_file.name} stämmer inte med originalet.")
        files.append(
            ManifestFile(
                PROJECT_BACKUP_NAME,
                self.project_file.relative_to(self.directory).as_posix(),
                sha256_hex(old_p),
                len(old_p),
            )
        )

        rel_t = self.persons_file.relative_to(self.directory).as_posix()
        if t_exists:
            # Copied whenever present (Req 7.9), also when it is not rewritten.
            fs.copy_file_durable(self.persons_file, bdir / PERSONS_BACKUP_NAME)
            copy = fs.read_bytes(bdir / PERSONS_BACKUP_NAME)
            if sha256_hex(copy) != sha256_hex(old_t):
                raise OSError("Säkerhetskopian av persons.json stämmer inte med originalet.")
            files.append(ManifestFile(PERSONS_BACKUP_NAME, rel_t, sha256_hex(old_t), len(old_t)))
        elif persons_bytes is not None:
            absent.append(rel_t)  # restoring means deleting it (Req 7.10)

        write_manifest(
            fs, self.directory, BackupManifest(txid=txid, files=tuple(files), absent_before=tuple(absent))
        )

    @staticmethod
    def _verify_project_bytes(project_bytes: bytes) -> None:
        """The new project file must decompress and parse as JSON."""
        try:
            json.loads(gzip.decompress(project_bytes).decode("utf-8"))
        except (OSError, EOFError, ValueError) as exc:
            raise ValueError(f"Den nya projektfilen går inte att läsa tillbaka: {exc}") from exc

    def _build_journal(
        self, txid: str, targets: list[_Target], revision_before: int
    ) -> MergeJournal:
        bname = backup_dir_for(self.directory, txid).name
        entries: list[JournalTarget] = []
        for t in targets:
            rel = lambda p: Path(p).relative_to(self.directory).as_posix()  # noqa: E731
            entries.append(
                JournalTarget(
                    role=t.role,
                    target=rel(t.path),
                    tmp=rel(t.tmp),
                    backup=f"{bname}/{t.backup_name}" if t.backup_name else "",
                    existed_before=t.existed,
                    old_sha256=sha256_hex(t.old),
                    old_size=len(t.old),
                    new_sha256=sha256_hex(t.new),
                    new_size=len(t.new),
                )
            )
        return MergeJournal(
            txid=txid,
            created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            app_version=self._app_version,
            targets=tuple(entries),
            dirty_before=False,
            revision_before=revision_before,
        )

    # ------------------------------------------------------------------
    # Error handling and cleanup

    def _handle_error(
        self,
        exc: Exception,
        txid: str,
        targets: list[_Target],
        journal_started: bool,
        *,
        lock_held: bool,
    ) -> CommitResult:
        """Make the same decision as after a crash at this point."""
        if not journal_started:
            # A crash here leaves a consistent OLD state with orphans; remove
            # what this transaction created.
            self._remove_orphans(txid, targets, lock_held=lock_held)
            raise CommitFailed(
                "Sammanslagningen kunde inte genomföras. Inga ändringar har gjorts i projektet.",
                cause=exc,
            ) from exc

        recover = self._recover if self._recover is not None else _default_recover()
        if recover is None:
            raise CommitFailed(
                "Sammanslagningen avbröts. Projektet återställs när det öppnas nästa gång.",
                cause=exc,
            ) from exc
        try:
            outcome = recover(self.project_file, fs=self.fs)
        except Exception as rexc:  # noqa: BLE001
            if type(rexc).__name__ == "RecoveryRefusedError":
                raise
            raise CommitFailed(
                "Sammanslagningen avbröts och kunde inte återställas direkt. "
                "Projektet återställs när det öppnas nästa gång.",
                cause=exc,
                recovery_error=rexc,
            ) from exc

        if self._project_is_new(targets):
            return CommitResult(txid=txid, recovered=True, recovery_outcome=outcome)
        raise CommitFailed(
            "Sammanslagningen kunde inte genomföras. Projektet har återställts till läget före sammanslagningen.",
            cause=exc,
        ) from exc

    def _project_is_new(self, targets: list[_Target]) -> bool:
        p = targets[-1]
        try:
            return sha256_hex(self.fs.read_bytes(p.path)) == sha256_hex(p.new)
        except Exception:  # noqa: BLE001
            return False

    def _remove_orphans(self, txid: str, targets: list[_Target], *, lock_held: bool) -> None:
        """Remove temps, backup directory and lock, each step on its own."""
        fs = self.fs
        steps: list[Callable[[], None]] = [lambda t=t: fs.remove(t.tmp) for t in targets]
        steps.append(lambda: fs.rmtree(backup_dir_for(self.directory, txid)))
        steps.append(lambda: fs.remove(journal_tmp_path_for(self.project_file)))
        if lock_held:
            steps.append(lambda: fs.remove(lock_path_for(self.project_file)))
        for step in steps:
            try:
                step()
            except Exception:  # noqa: BLE001 - garbage is removed at the next open
                pass

    def _cleanup_after_commit(self, txid: str, targets: list[_Target]) -> None:
        """Step (f): backup directory, remaining temps, lock. Never raises."""
        fs = self.fs
        steps: list[Callable[[], None]] = [
            lambda: fs.rmtree(backup_dir_for(self.directory, txid))
        ]
        steps.extend(lambda t=t: fs.remove(t.tmp) for t in targets)
        steps.append(lambda: fs.remove(lock_path_for(self.project_file)))
        for step in steps:
            try:
                step()
            except Exception:  # noqa: BLE001
                pass
