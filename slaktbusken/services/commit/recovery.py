"""Checksum-based startup recovery with Recovery_Refusal (Qt-free).

Implements design sections 13.7 and 13.8 (Requirements 7.13, 27.16, 27.17,
27.18, 27.21, 27.25). Every decision is made from SHA-256 content checksums
of the files on disk compared with the checksums in the Merge_Journal (or, if
the journal is unusable or absent, in the backup manifest). Timestamps, sizes
and listing order are never trusted.

The decision tables A (two targets), B (journal and manifest state) and D
(refusal rows) are data (``TABLE_A``, ``TABLE_B``, ``REFUSAL_REASONS``) and the
classifier is a lookup in them. Table C (crash points) is the set of disk
states those tables map; it is exercised by the crash-matrix tests.

Refusals are decided from read-only inspection: nothing is written, renamed,
deleted or touched before ``RecoveryRefusedError`` is raised. The only
refusal that happens after a write is R10 (recovery's own write did not
verify); it keeps every artifact for a retry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from slaktbusken.services.commit.fs_ops import CommitFs, RealFs
from slaktbusken.services.commit.journal import (
    BackupManifest,
    JournalReadResult,
    JournalState,
    ManifestState,
    MergeJournal,
    backup_dir_for,
    journal_path_for,
    journal_tmp_path_for,
    lock_path_for,
    read_journal,
    read_manifest,
    sha256_hex,
    temp_path_for,
)

__all__ = [
    "COMPLETED_MESSAGE",
    "ROLLED_BACK_MESSAGE",
    "RecoveryKind",
    "RecoveryOutcome",
    "RecoveryRefusal",
    "RecoveryRefusedError",
    "REFUSAL_REASONS",
    "TABLE_A",
    "TABLE_B",
    "recover_if_needed",
    "format_refusal_message",
]

COMPLETED_MESSAGE = "Sammanslagningen slutfördes."
ROLLED_BACK_MESSAGE = "Sammanslagningen återställdes."

OLD, NEW, OTHER, NONE = "OLD", "NEW", "OTHER", "NONE"  # NONE: no such target

# --------------------------------------------------------------------------
# Decision data (design 13.8)

REFUSAL_REASONS: dict[str, str] = {
    "R1": "Projektfilen stämmer varken med läget före eller efter sammanslagningen.",
    "R2": "Översättningsfilen translation/persons.json stämmer varken med läget före eller efter sammanslagningen.",
    "R3": "Filerna är i en kombination som inte kan förklaras av sammanslagningen.",
    "R4": "Filerna är i en kombination som inte kan förklaras av sammanslagningen.",
    "R5": "Sammanslagningsjournalen och säkerhetskopians förteckning är skadade.",
    "R6": "Sammanslagningsjournalen är skadad och resultatet av sammanslagningen kan inte styrkas.",
    "R7": "Säkerhetskopian som behövs saknas.",
    "R8": "Säkerhetskopian som behövs är skadad.",
    "R9": "Sammanslagningsjournalen saknas men filerna är i olika tillstånd.",
    "R10": "Återställningen kunde inte verifieras.",
}

FORWARD = "ROLL_FORWARD"
BACK = "ROLL_BACK"
DONE = "COMPLETED"
REFUSE = "REFUSE"
ORPHANS = "REMOVE_ORPHANS"
BACK_EMPTY = "ROLL_BACK_EMPTY"

_ANY = frozenset({OLD, NEW, OTHER, NONE})
_T_OK = frozenset({OLD, NEW, NONE})

# Table A. Valid journal. Columns: T states, P states, temp condition
# (ANY / ALL_OK / NOT_ALL_OK for the OLD targets), backup condition for the
# targets to restore (ANY / OK / BAD / MISSING), decision, refusal code.
# First matching row wins. T is NONE when persons.json is not a target.
TABLE_A: tuple[tuple[frozenset, frozenset, str, str, str, str], ...] = (
    # A12-A16: a target matching neither state
    (frozenset({OTHER}), frozenset({OLD}), "ANY", "ANY", REFUSE, "R2"),
    (frozenset({OTHER}), frozenset({NEW, OTHER}), "ANY", "ANY", REFUSE, "R4"),
    (frozenset({OLD, NONE}), frozenset({OTHER}), "ANY", "ANY", REFUSE, "R1"),
    (frozenset({NEW}), frozenset({OTHER}), "ANY", "ANY", REFUSE, "R3"),
    # A1: everything already replaced
    (frozenset({NEW, NONE}), frozenset({NEW}), "ANY", "ANY", DONE, ""),
    # A2, A4, A8: every unreplaced target has a verified NEW temp
    (_T_OK, frozenset({OLD, NEW}), "ALL_OK", "ANY", FORWARD, ""),
    # A3, A5, A9: roll back
    (_T_OK, frozenset({OLD, NEW}), "NOT_ALL_OK", "OK", BACK, ""),
    (_T_OK, frozenset({OLD, NEW}), "NOT_ALL_OK", "MISSING", REFUSE, "R7"),
    (_T_OK, frozenset({OLD, NEW}), "NOT_ALL_OK", "BAD", REFUSE, "R8"),
)

# Table B. Journal ABSENT or DAMAGED. Columns: journal state, manifest states,
# manifest view of the targets, decision, refusal code.
# View: NA (no valid manifest), ALL_OLD, MIXED, NOT_OLD_TEMPS, NOT_OLD_CLEAN.
_NOT_VALID = frozenset({ManifestState.UNUSABLE, ManifestState.ABSENT})
_VALID = frozenset({ManifestState.VALID})
TABLE_B: tuple[tuple[JournalState, frozenset, frozenset, str, str], ...] = (
    (JournalState.ABSENT, _NOT_VALID, frozenset({"NA"}), ORPHANS, ""),  # B1
    (JournalState.ABSENT, _VALID, frozenset({"ALL_OLD"}), ORPHANS, ""),  # B2
    (JournalState.ABSENT, _VALID, frozenset({"NOT_OLD_CLEAN"}), ORPHANS, ""),  # B3
    (JournalState.ABSENT, _VALID, frozenset({"MIXED"}), REFUSE, "R9"),  # B4
    (JournalState.ABSENT, _VALID, frozenset({"NOT_OLD_TEMPS"}), REFUSE, "R9"),  # B5
    (JournalState.DAMAGED, _NOT_VALID, frozenset({"NA"}), REFUSE, "R5"),  # B6
    (JournalState.DAMAGED, _VALID, frozenset({"ALL_OLD"}), BACK_EMPTY, ""),  # B7
    (
        JournalState.DAMAGED,
        _VALID,
        frozenset({"MIXED", "NOT_OLD_TEMPS", "NOT_OLD_CLEAN"}),
        REFUSE,
        "R6",
    ),  # B8
)


def _decide_a(t: str, p: str, temps: str, backup: str) -> tuple[str, str]:
    for ts, ps, tc, bc, decision, code in TABLE_A:
        if t in ts and p in ps and tc in ("ANY", temps) and bc in ("ANY", backup):
            return decision, code
    raise AssertionError(f"decision table A has no row for {(t, p, temps, backup)}")


def _decide_b(journal: JournalState, manifest: ManifestState, view: str) -> tuple[str, str]:
    for js, ms, vs, decision, code in TABLE_B:
        if journal is js and manifest in ms and view in vs:
            return decision, code
    raise AssertionError(f"decision table B has no row for {(journal, manifest, view)}")


# --------------------------------------------------------------------------
# Results


class RecoveryKind(str, Enum):
    COMPLETED = "COMPLETED"  # already complete or rolled forward: "slutfördes"
    ROLLED_FORWARD = "ROLLED_FORWARD"
    ROLLED_BACK = "ROLLED_BACK"  # "återställdes"


@dataclass(frozen=True)
class RecoveryOutcome:
    kind: RecoveryKind
    message: str

    @property
    def rolled_back(self) -> bool:
        return self.kind is RecoveryKind.ROLLED_BACK


@dataclass(frozen=True)
class RecoveryRefusal:
    code: str
    project_path: Path
    journal_path: Path | None
    temp_paths: tuple[Path, ...]
    backup_dir: Path | None
    target_states: tuple[tuple[str, str], ...] = ()  # (relative target, state)

    @property
    def reason(self) -> str:
        return REFUSAL_REASONS.get(self.code, "")

    @property
    def message(self) -> str:
        return format_refusal_message(self)


class RecoveryRefusedError(Exception):
    """Recovery refused (Recovery_Refusal). Nothing on disk was touched
    (R10 excepted: only recovery's own verified write failed)."""

    def __init__(self, refusal: RecoveryRefusal) -> None:
        super().__init__(refusal.message)
        self.refusal = refusal


def format_refusal_message(r: RecoveryRefusal) -> str:
    temps = "\n".join(f"                         {p}" for p in r.temp_paths)
    temps = temps.lstrip() if temps else "inga"
    return (
        "Projektet kunde inte öppnas. En tidigare sammanslagning avbröts, och Släktbusken kan inte avgöra\n"
        "säkert hur filerna ska återställas automatiskt.\n"
        "\n"
        f"Orsak: {r.reason}\n"
        "\n"
        f"Projektfil:              {r.project_path}\n"
        f"Sammanslagningsjournal:  {r.journal_path if r.journal_path else '(saknas)'}\n"
        f"Temporära filer:         {temps}\n"
        f"Säkerhetskopia (mapp):   {r.backup_dir if r.backup_dir else '(saknas)'}\n"
        "\n"
        "Alla dessa filer har sparats orörda. Ta inte bort dem.\n"
        "Nästa steg: återställ projektfilen och translation/persons.json manuellt genom att kopiera filerna från\n"
        "säkerhetskopian, och byt sedan namn på sammanslagningsjournalen så att den inte läses igen. Alternativt\n"
        "kontakta supporten och bifoga alla filer ovan."
    )


# --------------------------------------------------------------------------
# Read-only inspection helpers

_ABSENT = "absent"
_ERROR = "error"
_TEMP_RE = re.compile(r"^(?P<base>.+)\.(?P<txid>[0-9a-zA-Z]{4,64})\.(?P<kind>new|restore)$")
_BACKUP_PREFIX = ".merge-backup-"


def _hash(fs: CommitFs, path: Path) -> str:
    """Hex SHA-256, or ``_ABSENT`` / ``_ERROR``."""
    try:
        if not fs.exists(path):
            return _ABSENT
        return sha256_hex(fs.read_bytes(path))
    except OSError:
        return _ERROR


def _exists(fs: CommitFs, path: Path) -> bool:
    try:
        return fs.exists(path)
    except OSError:
        return False


def _listdir(fs: CommitFs, path: Path) -> list[str]:
    try:
        return fs.listdir(path) if fs.exists(path) else []
    except OSError:
        return []


def _restore_path(target: Path, txid: str) -> Path:
    return target.with_name(f"{target.name}.{txid}.restore")


class _Ctx:
    """Paths of one recovery run."""

    def __init__(self, project_file: Path, fs: CommitFs) -> None:
        self.project_file = Path(project_file)
        self.directory = self.project_file.parent
        self.fs = fs
        self.journal_path = journal_path_for(self.project_file)
        self.lock_path = lock_path_for(self.project_file)
        self.journal_tmp = journal_tmp_path_for(self.project_file)

    def backup_dirs(self) -> list[Path]:
        return [
            self.directory / n
            for n in sorted(_listdir(self.fs, self.directory))
            if n.startswith(_BACKUP_PREFIX)
        ]

    def stray_temps(self) -> list[Path]:
        """Every ``<target>.<txid>.new|restore`` beside the project or persons file."""
        names = {self.project_file.name, "persons.json"}
        found: list[Path] = []
        for d in (self.directory, self.directory / "translation"):
            for n in sorted(_listdir(self.fs, d)):
                m = _TEMP_RE.match(n)
                if m and m.group("base") in names:
                    found.append(d / n)
        return found

    def all_temps(self, extra: list[Path] = ()) -> tuple[Path, ...]:
        seen: dict[Path, None] = {}
        for p in [*extra, *self.stray_temps()]:
            if _exists(self.fs, p):
                seen[p] = None
        if _exists(self.fs, self.journal_tmp):
            seen[self.journal_tmp] = None
        return tuple(seen)

    def refusal(
        self,
        code: str,
        *,
        backup_dir: Path | None,
        states: tuple[tuple[str, str], ...] = (),
        extra_temps: list[Path] = (),
    ) -> RecoveryRefusedError:
        if backup_dir is None:
            dirs = self.backup_dirs()
            backup_dir = dirs[0] if dirs else None
        elif not _exists(self.fs, backup_dir):
            backup_dir = None
        return RecoveryRefusedError(
            RecoveryRefusal(
                code=code,
                project_path=self.project_file,
                journal_path=self.journal_path if _exists(self.fs, self.journal_path) else None,
                temp_paths=self.all_temps(list(extra_temps)),
                backup_dir=backup_dir,
                target_states=states,
            )
        )

    # -- cleanup (order: restore/.new temps, backup dir, lock, journal.tmp, journal)
    def cleanup(self, temps: list[Path], backup_dirs: list[Path], *, journal: bool) -> None:
        fs = self.fs
        for p in {*temps, *self.stray_temps()}:
            if _exists(fs, p):
                fs.remove(p)
        for d in backup_dirs:
            if _exists(fs, d):
                fs.rmtree(d)
        if _exists(fs, self.lock_path):
            fs.remove(self.lock_path)
        if _exists(fs, self.journal_tmp):
            fs.remove(self.journal_tmp)
        if journal and _exists(fs, self.journal_path):
            fs.remove(self.journal_path)


# --------------------------------------------------------------------------
# Public entry point


def recover_if_needed(project_file: Path, fs: CommitFs | None = None) -> RecoveryOutcome | None:
    """Recover from an interrupted merge commit, deciding by checksums only.

    Returns ``None`` when nothing was pending (orphans are removed silently),
    a ``RecoveryOutcome`` after a roll forward, completion or roll back, and
    raises ``RecoveryRefusedError`` on a Recovery_Refusal. Idempotent: every
    state recovery passes through is again a state this function resolves.
    """
    ctx = _Ctx(Path(project_file), fs if fs is not None else RealFs())
    jr = read_journal(ctx.fs, ctx.project_file)
    if jr.state is JournalState.VALID:
        assert jr.journal is not None
        return _recover_valid(ctx, jr.journal)
    return _recover_without_journal(ctx, jr)


# --------------------------------------------------------------------------
# Journal ABSENT or DAMAGED (table B)


def _manifest_view(
    ctx: _Ctx, manifest: BackupManifest
) -> tuple[str, tuple[tuple[str, str], ...], list[Path]]:
    """(view, target states, temp paths) of one valid manifest."""
    fs, d = ctx.fs, ctx.directory
    pname = ctx.project_file.relative_to(d).as_posix()
    states: dict[str, str] = {}
    for f in manifest.files:
        states[f.restore_to] = OLD if _hash(fs, d / f.restore_to) == f.sha256 else "NOT_OLD"
    for rel in manifest.absent_before:
        states[rel] = OLD if _hash(fs, d / rel) == _ABSENT else "NOT_OLD"
    temps = [
        p
        for rel in states
        for p in (temp_path_for(d / rel, manifest.txid), _restore_path(d / rel, manifest.txid))
        if _exists(fs, p)
    ]
    p_state = states.get(pname, "NOT_OLD")
    others = [s for rel, s in states.items() if rel != pname]
    # persons.json that exists is recorded even when it is not a target, so
    # "P changed, T old" is ambiguous and not treated as mixed. "P old, T
    # changed" and any state mixed among absent-before targets cannot arise
    # from an unrelated commit and is.
    if p_state == OLD and any(s != OLD for s in others):
        view = "MIXED"
    elif manifest.absent_before and len(set(states[r] for r in manifest.absent_before) | {p_state}) > 1:
        view = "MIXED"
    elif p_state == OLD and all(s == OLD for s in others):
        view = "ALL_OLD"
    elif temps:
        view = "NOT_OLD_TEMPS"
    else:
        view = "NOT_OLD_CLEAN"
    return view, tuple(sorted(states.items())), temps


_VIEW_RANK = ("ALL_OLD", "NOT_OLD_CLEAN", "NOT_OLD_TEMPS", "MIXED")


def _recover_without_journal(ctx: _Ctx, jr: JournalReadResult) -> RecoveryOutcome | None:
    fs = ctx.fs
    bdirs = ctx.backup_dirs()
    views: list[str] = []
    states: list[tuple[str, str]] = []
    temps: list[Path] = []
    for bd in bdirs:
        txid = bd.name[len(_BACKUP_PREFIX):]
        mr = read_manifest(fs, ctx.directory, txid)
        if mr.state is ManifestState.VALID and mr.manifest is not None:
            v, s, t = _manifest_view(ctx, mr.manifest)
            views.append(v)
            states.extend(s)
            temps.extend(t)
    if views:
        view = max(views, key=_VIEW_RANK.index)
        mstate = ManifestState.VALID
    else:
        view, mstate = "NA", ManifestState.ABSENT
    decision, code = _decide_b(jr.state, mstate, view)
    if decision == REFUSE:
        raise ctx.refusal(code, backup_dir=None, states=tuple(states), extra_temps=temps)
    if decision == BACK_EMPTY:
        ctx.cleanup(temps, bdirs, journal=True)
        return RecoveryOutcome(RecoveryKind.ROLLED_BACK, ROLLED_BACK_MESSAGE)
    # ORPHANS: silent, state is consistent
    ctx.cleanup(temps, bdirs, journal=False)
    return None


# --------------------------------------------------------------------------
# Journal VALID (table A)


@dataclass
class _T:
    entry_target: Path
    tmp: Path
    restore: Path
    backup: Path | None
    existed_before: bool
    old: str
    new: str
    role: str
    rel: str
    cur: str = OTHER
    tmp_ok: bool = False
    bak: str = "NA"  # OK / BAD / MISSING / NA


def _classify(ctx: _Ctx, journal: MergeJournal) -> list[_T]:
    fs, d = ctx.fs, ctx.directory
    out: list[_T] = []
    for e in journal.targets:
        t = _T(
            entry_target=d / e.target,
            tmp=d / e.tmp,
            restore=_restore_path(d / e.target, journal.txid),
            backup=(d / e.backup) if e.backup else None,
            existed_before=e.existed_before,
            old=e.old_sha256,
            new=e.new_sha256,
            role=e.role,
            rel=e.target,
        )
        h = _hash(fs, t.entry_target)
        if h == t.new:
            t.cur = NEW
        elif h == _ABSENT and not t.existed_before:
            t.cur = OLD
        elif t.existed_before and h == t.old:
            t.cur = OLD
        else:
            t.cur = OTHER
        if t.cur == OLD:
            t.tmp_ok = _hash(fs, t.tmp) == t.new
        if t.cur == NEW:
            if not t.existed_before:
                t.bak = "NA"
            elif t.backup is None:
                t.bak = "MISSING"
            else:
                bh = _hash(fs, t.backup)
                t.bak = "OK" if bh == t.old else "MISSING" if bh == _ABSENT else "BAD"
        out.append(t)
    return out


def _role_state(ts: list[_T], role: str) -> str:
    for t in ts:
        if t.role == role:
            return t.cur
    return NONE


def _recover_valid(ctx: _Ctx, journal: MergeJournal) -> RecoveryOutcome:
    ts = _classify(ctx, journal)
    bdir = backup_dir_for(ctx.directory, journal.txid)
    states = tuple((t.rel, t.cur) for t in ts)
    t_state = _role_state(ts, "persons")
    p_state = _role_state(ts, "project")
    if p_state == NONE:  # no project target: cannot occur, treat as refusal
        raise ctx.refusal("R3", backup_dir=bdir, states=states)

    old_targets = [t for t in ts if t.cur == OLD]
    temps_ok = "ALL_OK" if all(t.tmp_ok for t in old_targets) else "NOT_ALL_OK"
    restore_set = [t for t in ts if t.cur == NEW]
    baks = {t.bak for t in restore_set}
    backup = "MISSING" if "MISSING" in baks else "BAD" if "BAD" in baks else "OK"

    decision, code = _decide_a(t_state, p_state, temps_ok, backup)
    own_temps = [x for t in ts for x in (t.tmp, t.restore)]

    if decision == REFUSE:
        raise ctx.refusal(code, backup_dir=bdir, states=states, extra_temps=own_temps)

    def done(kind: RecoveryKind, msg: str) -> RecoveryOutcome:
        ctx.cleanup(own_temps, [bdir, *ctx.backup_dirs()], journal=True)
        return RecoveryOutcome(kind, msg)

    def unverified(t: _T) -> RecoveryRefusedError:
        return ctx.refusal("R10", backup_dir=bdir, states=states, extra_temps=own_temps)

    if decision == DONE:
        return done(RecoveryKind.COMPLETED, COMPLETED_MESSAGE)

    if decision == FORWARD:
        for t in ts:  # journal order: T then P
            if t.cur != OLD:
                continue
            ctx.fs.replace(t.tmp, t.entry_target)
            if _hash(ctx.fs, t.entry_target) != t.new:
                raise unverified(t)
        return done(RecoveryKind.ROLLED_FORWARD, COMPLETED_MESSAGE)

    assert decision == BACK
    for t in reversed(ts):  # P then T
        if t.cur != NEW:
            continue
        if not t.existed_before:
            ctx.fs.remove(t.entry_target)
            if _hash(ctx.fs, t.entry_target) != _ABSENT:
                raise unverified(t)
            continue
        assert t.backup is not None
        ctx.fs.copy_file_durable(t.backup, t.restore)
        if _hash(ctx.fs, t.restore) != t.old:
            raise unverified(t)
        ctx.fs.replace(t.restore, t.entry_target)
        if _hash(ctx.fs, t.entry_target) != t.old:
            raise unverified(t)
    return done(RecoveryKind.ROLLED_BACK, ROLLED_BACK_MESSAGE)
