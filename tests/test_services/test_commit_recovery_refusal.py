"""Recovery_Refusal matrix (task 13.20, Mandatory group d: crash recovery).

Property 49: Recovery is refused, never guessed.

**Validates: Requirements 7.13, 27.16, 27.19, 27.25**

One real on-disk interrupted state is built per refusal row R1 to R9 of the
decision table D. Every refusal must leave every artifact byte-for-byte (and
mtime) untouched, must not open the project and must give the same refusal
when repeated. A table-driven test also feeds tables A and B through the
in-memory ``CommitFs``.

The state builders are local to this module on purpose.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.services.commit.journal import (
    BackupManifest,
    JournalTarget,
    ManifestFile,
    MergeJournal,
    backup_dir_for,
    journal_path_for,
    lock_path_for,
    manifest_path_for,
    sha256_hex,
)
from slaktbusken.services.commit.recovery import (
    COMPLETED_MESSAGE,
    ROLLED_BACK_MESSAGE,
    RecoveryKind,
    RecoveryRefusedError,
    recover_if_needed,
)
from slaktbusken.services.project_service import ProjectService
from tests.helpers.fault_fs import MemoryFs

pytestmark = pytest.mark.mandatory_integrity

OLD, NEW, OTHER, NONE = "OLD", "NEW", "OTHER", "NONE"
TXID = "a1b2c3d4e5f6"
PROJECT_NAME = "P.json.gz"
PERSONS_REL = "translation/persons.json"
GARBAGE = b"\x00garbage that matches neither state\xff"


# --------------------------------------------------------------------------
# Local state builder. A scenario describes the disk after a crash; ``build``
# turns it into ``{relative path: bytes}`` which is then written to a real
# directory or into a MemoryFs.


@dataclass(frozen=True)
class Scenario:
    name: str
    code: str  # expected refusal code
    journal: str = "valid"  # valid | absent | truncated | empty | garbage | bad_checksum | not_utf8
    manifest: str = "valid"  # valid | absent | corrupt
    backup_dir: bool = True
    t: str = OLD  # persons.json state
    p: str = OLD  # project file state
    t_tmp: bool = True
    p_tmp: bool = True
    t_backup: str = "ok"  # ok | missing | bad
    p_backup: str = "ok"
    lock: bool = True


def _journal_bytes(journal: str, good: bytes) -> bytes | None:
    if journal == "absent":
        return None
    if journal == "valid":
        return good
    if journal == "truncated":
        return good[: len(good) // 2]
    if journal == "empty":
        return b""
    if journal == "garbage":
        return b"not json at all"
    if journal == "bad_checksum":
        return good.replace(TXID.encode(), b"ffffffffffff", 1)
    if journal == "not_utf8":
        return b"\xff\xfe\x00{"
    raise AssertionError(journal)


def build(sc: Scenario, old_p: bytes, old_t: bytes) -> dict[str, bytes]:
    new_p, new_t = old_p + b"-NEW-PROJECT", old_t + b" -NEW-PERSONS"
    has_t = sc.t != NONE
    bdir = backup_dir_for(Path("."), TXID).name
    files: dict[str, bytes] = {}

    def disk(state: str, old: bytes, new: bytes) -> bytes:
        return {OLD: old, NEW: new, OTHER: GARBAGE}[state]

    files[PROJECT_NAME] = disk(sc.p, old_p, new_p)
    if has_t:
        files[PERSONS_REL] = disk(sc.t, old_t, new_t)
    if sc.p_tmp:
        files[f"{PROJECT_NAME}.{TXID}.new"] = new_p
    if has_t and sc.t_tmp:
        files[f"{PERSONS_REL}.{TXID}.new"] = new_t
    if sc.lock:
        files[lock_path_for(Path(PROJECT_NAME)).name] = b""

    if sc.backup_dir:
        for rel, backup_name, data, how, present in (
            (PROJECT_NAME, "project.json.gz", old_p, sc.p_backup, True),
            (PERSONS_REL, "persons.json", old_t, sc.t_backup, has_t),
        ):
            if not present or how == "missing":
                continue
            files[f"{bdir}/{backup_name}"] = data if how == "ok" else data + b"-damaged"
        if sc.manifest == "valid":
            mf = [ManifestFile("project.json.gz", PROJECT_NAME, sha256_hex(old_p), len(old_p))]
            if has_t:
                mf.append(ManifestFile("persons.json", PERSONS_REL, sha256_hex(old_t), len(old_t)))
            files[f"{bdir}/manifest.json"] = BackupManifest(TXID, tuple(mf)).to_bytes()
        elif sc.manifest == "corrupt":
            files[f"{bdir}/manifest.json"] = b'{"schema": 1, "txid": "' + TXID.encode() + b'", "files": ['

    targets = []
    if has_t:
        targets.append(
            JournalTarget("persons", PERSONS_REL, f"{PERSONS_REL}.{TXID}.new", f"{bdir}/persons.json",
                          True, sha256_hex(old_t), len(old_t), sha256_hex(new_t), len(new_t))
        )
    targets.append(
        JournalTarget("project", PROJECT_NAME, f"{PROJECT_NAME}.{TXID}.new", f"{bdir}/project.json.gz",
                      True, sha256_hex(old_p), len(old_p), sha256_hex(new_p), len(new_p))
    )
    good = MergeJournal(TXID, "2024-01-01T00:00:00", "test", tuple(targets)).to_bytes()
    jb = _journal_bytes(sc.journal, good)
    if jb is not None:
        files[journal_path_for(Path(PROJECT_NAME)).name] = jb
    return files


# The refusal rows R1 to R9 of table D, with variants.
ROWS: tuple[Scenario, ...] = (
    Scenario("R1", "R1", t=OLD, p=OTHER),
    Scenario("R1-persons-absent", "R1", t=NONE, p=OTHER),
    Scenario("R2", "R2", t=OTHER, p=OLD),
    Scenario("R3", "R3", t=NEW, p=OTHER),
    Scenario("R4-p-new", "R4", t=OTHER, p=NEW),
    Scenario("R4-both-other", "R4", t=OTHER, p=OTHER),
    Scenario("R5-manifest-corrupt", "R5", journal="truncated", manifest="corrupt"),
    Scenario("R5-no-backup-dir", "R5", journal="garbage", manifest="absent", backup_dir=False),
    Scenario("R5-empty-journal-no-manifest", "R5", journal="empty", manifest="absent"),
    Scenario("R6-t-new-p-old", "R6", journal="truncated", t=NEW, p=OLD),
    Scenario("R6-bad-checksum", "R6", journal="bad_checksum", t=NEW, p=OLD),
    Scenario("R6-not-utf8", "R6", journal="not_utf8", t=OLD, p=NEW),
    Scenario("R7-persons-backup-missing", "R7", t=NEW, p=OLD, p_tmp=False, t_backup="missing"),
    Scenario("R7-backup-dir-missing", "R7", t=NEW, p=OLD, p_tmp=False, backup_dir=False),
    Scenario("R7-project-backup-missing", "R7", t=OLD, p=NEW, t_tmp=False, p_backup="missing"),
    Scenario("R8-persons-backup-corrupt", "R8", t=NEW, p=OLD, p_tmp=False, t_backup="bad"),
    Scenario("R8-project-backup-corrupt", "R8", t=OLD, p=NEW, t_tmp=False, p_backup="bad"),
    Scenario("R9-mixed", "R9", journal="absent", t=NEW, p=OLD),
    Scenario("R9-not-old-temps", "R9", journal="absent", t=OLD, p=NEW, p_tmp=False),
)
ROW_IDS = [r.name for r in ROWS]


def rows_for(code: str) -> list[Scenario]:
    return [r for r in ROWS if r.code == code]


# --------------------------------------------------------------------------
# Real-disk state


@dataclass
class DiskState:
    root: Path
    project: Path
    scenario: Scenario
    old_p: bytes
    old_t: bytes
    files: dict[str, bytes] = field(default_factory=dict)


def make_disk_state(tmp_path: Path, sc: Scenario) -> DiskState:
    ProjectService().create_project("P", tmp_path)
    root = tmp_path / "P"
    project = root / PROJECT_NAME
    persons = root / PERSONS_REL
    if not persons.exists():
        persons.parent.mkdir(parents=True, exist_ok=True)
        persons.write_bytes(b'{"persons": {}}\n')
    old_p, old_t = project.read_bytes(), persons.read_bytes()
    files = build(sc, old_p, old_t)
    if sc.t == NONE:
        persons.unlink()
    for rel, data in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return DiskState(root, project, sc, old_p, old_t, files)


def snapshot(root: Path) -> dict[str, tuple]:
    """path -> (kind, size, sha256, mtime_ns) for every file and directory."""
    snap: dict[str, tuple] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames:
            p = Path(dirpath) / name
            snap[p.relative_to(root).as_posix()] = ("dir", 0, "", p.stat().st_mtime_ns)
        for name in filenames:
            p = Path(dirpath) / name
            data = p.read_bytes()
            snap[p.relative_to(root).as_posix()] = (
                "file", len(data), hashlib.sha256(data).hexdigest(), p.stat().st_mtime_ns,
            )
    return snap


def _no_load(monkeypatch) -> list[Path]:
    calls: list[Path] = []

    def spy(path):
        calls.append(Path(path))
        raise AssertionError("FilePersistence.load must not be called after a refusal")

    monkeypatch.setattr(FilePersistence, "load", staticmethod(spy))
    return calls


def assert_refused(st_: DiskState, monkeypatch) -> RecoveryRefusedError:
    """The common refusal checks of Property 49 on one real interrupted state."""
    sc = st_.scenario
    calls = _no_load(monkeypatch)
    before = snapshot(st_.root)

    service = ProjectService()
    with pytest.raises(RecoveryRefusedError) as info:
        service.open_project(st_.project)
    err = info.value
    refusal = err.refusal

    # code, project not opened, nothing loaded
    assert refusal.code == sc.code, sc.name
    assert calls == []
    assert service.project_path is None

    # nothing modified: path, size, SHA-256 and modification time
    assert snapshot(st_.root) == before

    # the Swedish message names every path and the preservation statements
    msg = str(err)
    assert msg == refusal.message
    assert str(st_.project) in msg
    journal = journal_path_for(st_.project)
    assert (str(journal) in msg) == journal.exists()
    if not journal.exists():
        assert "(saknas)" in msg
    temps = [p for p in st_.root.rglob("*") if p.name.endswith(".new") or p.name.endswith(".restore")]
    assert set(refusal.temp_paths) == set(temps)
    for t in temps:
        assert str(t) in msg
    bdir = backup_dir_for(st_.root, TXID)
    if bdir.exists():
        assert str(bdir) in msg
    else:
        assert "(saknas)" in msg
    assert "Orsak:" in msg
    assert "Alla dessa filer har sparats orörda. Ta inte bort dem." in msg
    assert "translation/persons.json" in msg
    assert "byt sedan namn på sammanslagningsjournalen" in msg

    # a second open gives the same refusal
    with pytest.raises(RecoveryRefusedError) as again:
        ProjectService().open_project(st_.project)
    assert again.value.refusal.code == sc.code
    assert str(again.value) == msg
    assert calls == []
    assert snapshot(st_.root) == before
    return err


def manual_restore_and_open(st_: DiskState, monkeypatch) -> None:
    """Restore from the backup (or a good copy), rename the journal, open."""
    monkeypatch.undo()
    root, bdir = st_.root, backup_dir_for(st_.root, TXID)
    for backup_name, target, good in (
        ("project.json.gz", st_.project, st_.old_p),
        ("persons.json", root / PERSONS_REL, st_.old_t),
    ):
        src = bdir / backup_name
        data = src.read_bytes() if src.exists() and src.read_bytes() == good else good
        if target.exists() or st_.scenario.t != NONE or backup_name == "project.json.gz":
            target.write_bytes(data)
    journal = journal_path_for(st_.project)
    if journal.exists():
        journal.rename(journal.with_name(journal.name + ".old"))
    service = ProjectService()
    service.open_project(st_.project)
    assert service.project_path == st_.project


# --------------------------------------------------------------------------
# Named tests


@pytest.mark.parametrize("sc", rows_for("R1"), ids=lambda s: s.name)
def test_refusal_project_file_matches_neither(tmp_path, monkeypatch, sc):
    st_ = make_disk_state(tmp_path, sc)
    assert_refused(st_, monkeypatch)
    manual_restore_and_open(st_, monkeypatch)


@pytest.mark.parametrize("sc", rows_for("R2"), ids=lambda s: s.name)
def test_refusal_persons_json_matches_neither(tmp_path, monkeypatch, sc):
    st_ = make_disk_state(tmp_path, sc)
    assert_refused(st_, monkeypatch)
    manual_restore_and_open(st_, monkeypatch)


@pytest.mark.parametrize("sc", rows_for("R3") + rows_for("R4"), ids=lambda s: s.name)
def test_refusal_one_new_other_neither(tmp_path, monkeypatch, sc):
    st_ = make_disk_state(tmp_path, sc)
    assert_refused(st_, monkeypatch)
    manual_restore_and_open(st_, monkeypatch)


@pytest.mark.parametrize(
    "sc", rows_for("R5") + rows_for("R6") + rows_for("R9"), ids=lambda s: s.name
)
def test_refusal_corrupt_journal(tmp_path, monkeypatch, sc):
    """R5, R6 (damaged journal) and R9 (journal gone, files in different states)."""
    st_ = make_disk_state(tmp_path, sc)
    assert_refused(st_, monkeypatch)
    manual_restore_and_open(st_, monkeypatch)


@pytest.mark.parametrize("sc", rows_for("R7") + rows_for("R8"), ids=lambda s: s.name)
def test_refusal_backup_missing_or_corrupt(tmp_path, monkeypatch, sc):
    st_ = make_disk_state(tmp_path, sc)
    assert_refused(st_, monkeypatch)
    manual_restore_and_open(st_, monkeypatch)


def test_refusal_preserves_every_artifact_byte_for_byte(tmp_path, monkeypatch):
    """Across every row the exact bytes written by the builder are still there."""
    for i, sc in enumerate(ROWS):
        sub = tmp_path / f"row{i}"
        sub.mkdir()
        st_ = make_disk_state(sub, sc)
        before_files = {p.relative_to(st_.root).as_posix() for p in st_.root.rglob("*") if p.is_file()}
        _no_load(monkeypatch)
        with pytest.raises(RecoveryRefusedError):
            ProjectService().open_project(st_.project)
        for rel, data in st_.files.items():
            assert (st_.root / rel).read_bytes() == data, (sc.name, rel)
        after_files = {p.relative_to(st_.root).as_posix() for p in st_.root.rglob("*") if p.is_file()}
        assert after_files == before_files, sc.name  # nothing deleted, nothing added
        monkeypatch.undo()


# --------------------------------------------------------------------------
# Table-driven classifier test through the in-memory CommitFs.

MEM_ROOT = Path("proj")
MEM_OLD_P, MEM_OLD_T = b"old-project", b"old-persons"


def populate(fs: MemoryFs, files: dict[str, bytes]) -> None:
    """Fill a MemoryFs, creating parent directories locally (MemoryFs.mkdir is
    strict about parents, which makes ``add_file`` unusable for new trees)."""
    fs.dirs.update({MEM_ROOT, MEM_ROOT / "translation"})
    for rel, data in files.items():
        path = MEM_ROOT / rel
        fs.dirs.update(path.parents)
        fs.files[path] = data


def mem_fs(sc: Scenario) -> tuple[MemoryFs, Path]:
    fs = MemoryFs()
    populate(fs, build(sc, MEM_OLD_P, MEM_OLD_T))
    return fs, MEM_ROOT / PROJECT_NAME


# (row name, scenario, expected decision): decision is a refusal code or an outcome kind.
TABLE_A_CASES: tuple[tuple[str, Scenario, str], ...] = (
    ("A1 both replaced", Scenario("A1", "", t=NEW, p=NEW), "COMPLETED"),
    ("A1b persons not a target, project replaced", Scenario("A1b", "", t=NONE, p=NEW), "COMPLETED"),
    ("A2 both old, temps verified", Scenario("A2", "", t=OLD, p=OLD), "ROLLED_FORWARD"),
    ("A4 persons replaced, project temp verified", Scenario("A4", "", t=NEW, p=OLD), "ROLLED_FORWARD"),
    ("A8 no persons target, project temp verified", Scenario("A8", "", t=NONE, p=OLD), "ROLLED_FORWARD"),
    ("A3 both old, temp missing", Scenario("A3", "", t=OLD, p=OLD, p_tmp=False), "ROLLED_BACK"),
    (
        "A5 persons replaced, project temp missing, backup ok",
        Scenario("A5", "", t=NEW, p=OLD, p_tmp=False),
        "ROLLED_BACK",
    ),
    ("A9 no persons target, temp missing", Scenario("A9", "", t=NONE, p=OLD, p_tmp=False), "ROLLED_BACK"),
    (
        "A6 persons old, project replaced, persons temp missing",
        Scenario("A6", "", t=OLD, p=NEW, t_tmp=False),
        "ROLLED_BACK",
    ),
    ("A12 persons other, project old", Scenario("A12", "", t=OTHER, p=OLD), "R2"),
    ("A13 persons other, project new", Scenario("A13", "", t=OTHER, p=NEW), "R4"),
    ("A14 persons other, project other", Scenario("A14", "", t=OTHER, p=OTHER), "R4"),
    ("A15 persons old, project other", Scenario("A15", "", t=OLD, p=OTHER), "R1"),
    ("A15b no persons target, project other", Scenario("A15b", "", t=NONE, p=OTHER), "R1"),
    ("A16 persons new, project other", Scenario("A16", "", t=NEW, p=OTHER), "R3"),
    (
        "A5-R7 backup file missing",
        Scenario("A5m", "", t=NEW, p=OLD, p_tmp=False, t_backup="missing"),
        "R7",
    ),
    (
        "A5-R8 backup file corrupt",
        Scenario("A5b", "", t=NEW, p=OLD, p_tmp=False, t_backup="bad"),
        "R8",
    ),
)

TABLE_B_CASES: tuple[tuple[str, Scenario, str], ...] = (
    ("B1 no journal, no manifest", Scenario("B1", "", journal="absent", manifest="absent", lock=False), "ORPHANS"),
    ("B1b no journal, unusable manifest", Scenario("B1b", "", journal="absent", manifest="corrupt"), "ORPHANS"),
    ("B2 no journal, all old", Scenario("B2", "", journal="absent", t=OLD, p=OLD), "ORPHANS"),
    (
        "B3 no journal, all replaced, no temps",
        Scenario("B3", "", journal="absent", t=NEW, p=NEW, t_tmp=False, p_tmp=False),
        "ORPHANS",
    ),
    ("B4 no journal, mixed", Scenario("B4", "", journal="absent", t=NEW, p=OLD), "R9"),
    (
        "B5 no journal, project replaced, persons temp left",
        Scenario("B5", "", journal="absent", t=OLD, p=NEW, p_tmp=False),
        "R9",
    ),
    ("B6 damaged journal, manifest unusable", Scenario("B6", "", journal="truncated", manifest="corrupt"), "R5"),
    (
        "B6b damaged journal, no manifest",
        Scenario("B6b", "", journal="garbage", manifest="absent"),
        "R5",
    ),
    ("B7 damaged journal, all old", Scenario("B7", "", journal="truncated", t=OLD, p=OLD), "ROLLED_BACK"),
    ("B8 damaged journal, mixed", Scenario("B8", "", journal="truncated", t=NEW, p=OLD), "R6"),
    (
        "B8b damaged journal, all replaced",
        Scenario("B8b", "", journal="bad_checksum", t=NEW, p=NEW, t_tmp=False, p_tmp=False),
        "R6",
    ),
)


@pytest.mark.parametrize(
    "label,sc,expected", TABLE_A_CASES + TABLE_B_CASES, ids=[c[0] for c in TABLE_A_CASES + TABLE_B_CASES]
)
def test_classifier_decision_per_named_row(label, sc, expected):
    fs, project = mem_fs(sc)
    before = dict(fs.files)
    if expected[1:].isdigit():  # a refusal code R1..R9
        with pytest.raises(RecoveryRefusedError) as info:
            recover_if_needed(project, fs)
        assert info.value.refusal.code == expected, label
        assert fs.files == before, label  # nothing modified by a refusal
        return
    outcome = recover_if_needed(project, fs)
    if expected == "ORPHANS":
        assert outcome is None, label
        assert fs.files[MEM_ROOT / PROJECT_NAME] == before[MEM_ROOT / PROJECT_NAME]
    elif expected == "COMPLETED":
        assert outcome is not None and outcome.kind is RecoveryKind.COMPLETED, label
        assert outcome.message == COMPLETED_MESSAGE
    elif expected == "ROLLED_FORWARD":
        assert outcome is not None and outcome.kind is RecoveryKind.ROLLED_FORWARD, label
        assert outcome.message == COMPLETED_MESSAGE
        assert fs.files[MEM_ROOT / PROJECT_NAME] == MEM_OLD_P + b"-NEW-PROJECT"
    else:
        assert outcome is not None and outcome.kind is RecoveryKind.ROLLED_BACK, label
        assert outcome.message == ROLLED_BACK_MESSAGE
        assert fs.files[MEM_ROOT / PROJECT_NAME] == MEM_OLD_P
        if sc.t != NONE:
            assert fs.files[MEM_ROOT / PERSONS_REL] == MEM_OLD_T
    if expected != "ORPHANS" or outcome is None:
        # recovery finished: no journal is left behind
        assert journal_path_for(project) not in fs.files


# --------------------------------------------------------------------------
# Property 49


def _damage(good: bytes, cut: int, how: str) -> bytes:
    if how == "truncate":
        return good[: max(0, len(good) - 2 - cut % max(1, len(good) - 2))]
    if how == "garbage":
        return GARBAGE + good[:cut % 7]
    return bytes(b ^ 0xFF for b in good[:8]) + good[8:]


# Feature: person-comparison-and-merge, Property 49:
@settings(max_examples=100, deadline=None)
@given(
    row=st.sampled_from(ROWS),
    old_p=st.binary(min_size=1, max_size=64),
    old_t=st.binary(min_size=1, max_size=64),
    cut=st.integers(min_value=0, max_value=10_000),
    how=st.sampled_from(["truncate", "garbage", "flip"]),
)
def test_property_49_recovery_refused_never_guessed(row, old_p, old_t, cut, how):
    """For any bytes in the targets and any journal damage, a refusal row is refused
    with its code and the in-memory filesystem is unchanged; a repeat gives the same."""
    sc = row
    # skip degenerate byte choices that would make "old" equal the garbage marker
    fs = MemoryFs()
    files = build(sc, old_p, old_t)
    jname = journal_path_for(Path(PROJECT_NAME)).name
    if sc.journal in ("truncated", "empty", "garbage", "bad_checksum", "not_utf8") and sc.journal != "empty":
        good = build(replace(sc, journal="valid"), old_p, old_t)[jname]
        files[jname] = _damage(good, cut, how)
    populate(fs, files)
    before = dict(fs.files)
    project = MEM_ROOT / PROJECT_NAME

    for _ in range(2):
        with pytest.raises(RecoveryRefusedError) as info:
            recover_if_needed(project, fs)
        assert info.value.refusal.code == sc.code
        assert fs.files == before
