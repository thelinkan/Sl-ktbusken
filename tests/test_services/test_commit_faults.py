"""Crash atomicity of the Merge_Transaction (task 13.13, Mandatory group d).

Property 40: a merge commit is all-or-nothing whatever operation fails or
crashes. Requirements 7.12, 27.16, 27.17, 27.18, 27.19, 30.9.

The real ``MergeEngine`` (and through it ``MergeTransaction`` and the recovery
function) runs on a real directory through the fault-injection filesystems of
``tests/helpers/fault_fs.py``. Every operation number N of a dry run is a fault
point. After each fault the disk is observed, mapped to a row of design table C
(Decision tables, 13.8) and the observed result of a restart (a new
``ProjectService`` and ``open_project``) must equal that row's decision.

Never skipped, not marked ``slow``.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pytest
from hypothesis import given, settings, strategies as st

from slaktbusken.model.person import Name, Person
from slaktbusken.persistence import translation_io
from slaktbusken.persistence.translation_io import PersonMapping
from slaktbusken.services.commit.fs_ops import RealFs
from slaktbusken.services.commit.journal import (
    JournalState,
    read_journal,
    sha256_hex,
    temp_path_for,
)
from slaktbusken.services.commit.preflight import journal_path_for, lock_path_for
from slaktbusken.services.commit.recovery import RecoveryRefusedError
from slaktbusken.services.id_registry import retired_person_ids
from slaktbusken.services.merge_engine import MergeEngine
from slaktbusken.services.merge_planner import MergeDecisions, build_plan
from slaktbusken.services.project_service import ProjectService
from tests.helpers.fault_fs import (
    CountingFs,
    FaultFs,
    PowerLossFs,
    SimulatedCrash,
    snapshot_dir,
)

pytestmark = pytest.mark.mandatory_integrity

SURVIVOR, RETIRED = "person_1", "person_2"
RETIRED_XREF = "@I2@"

FAULT_KINDS = (
    "crash_before",
    "crash_after",
    "io_error_before",
    "io_error_after",
    "partial_write",
    "permission_error_persistent",
)
POWER_LOSS_PHASES = ("before", "mid", "after")


# ---------------------------------------------------------------------------
# Project construction
# ---------------------------------------------------------------------------


def _person(pid: str, given: str) -> Person:
    return Person(id=pid, sex="F", names=[Name("birth", given, "Berg")])


def _build_template(root: Path, with_persons: bool) -> Path:
    """A saved project with two duplicate persons; returns the project file."""
    svc = ProjectService()
    svc.create_project("Test", root)
    svc.data.persons.extend([_person(SURVIVOR, "Anna"), _person(RETIRED, "Anna")])
    if with_persons:
        translation_io.write_persons(
            [PersonMapping(RETIRED_XREF, RETIRED, "fp2")],
            [],
            svc.project_path.parent / "translation" / "persons.json",
        )
    else:
        (svc.project_path.parent / "translation" / "persons.json").unlink(missing_ok=True)
    svc._dirty = True
    svc.save_project()
    return svc.project_path


@pytest.fixture(scope="module")
def templates(tmp_path_factory: pytest.TempPathFactory) -> dict[bool, Path]:
    return {
        flag: _build_template(tmp_path_factory.mktemp(f"template_{int(flag)}"), flag)
        for flag in (True, False)
    }


@dataclass
class Case:
    """One working copy of the template project."""

    project: Path
    with_persons: bool
    old_project: bytes
    old_persons: Optional[bytes]

    @property
    def directory(self) -> Path:
        return self.project.parent

    @property
    def persons_file(self) -> Path:
        return self.directory / "translation" / "persons.json"


def _copy_case(templates: dict[bool, Path], with_persons: bool, workdir: Path) -> Case:
    template = templates[with_persons]
    dst = workdir / template.parent.name
    shutil.copytree(template.parent, dst)
    project = dst / template.name
    persons = dst / "translation" / "persons.json"
    return Case(
        project,
        with_persons,
        project.read_bytes(),
        persons.read_bytes() if persons.exists() else None,
    )


def _open(case: Case) -> ProjectService:
    svc = ProjectService()
    svc.open_project(case.project)
    return svc


def _plan(svc: ProjectService):
    translation = translation_io.read_all(svc.project_path.parent / "translation")
    decisions = MergeDecisions(SURVIVOR, RETIRED, survivor_id=SURVIVOR, survivor_confirmed=True)
    plan = build_plan(svc.data, translation, decisions, svc.content_revision)
    assert plan.can_execute, [c.message for c in plan.blocking]
    return plan


def _dry_run(templates: dict[bool, Path], with_persons: bool) -> CountingFs:
    with tempfile.TemporaryDirectory() as tmp:
        case = _copy_case(templates, with_persons, Path(tmp))
        svc = _open(case)
        counting = CountingFs()
        outcome = MergeEngine(svc, None, fs=counting).execute(_plan(svc))
        assert outcome.success, outcome.message
        return counting


# ---------------------------------------------------------------------------
# Observation of a disk state and mapping to table C
# ---------------------------------------------------------------------------

_REAL = RealFs(delays=(), sleep=lambda _s: None)

UNCHANGED, MERGED, REFUSE = "unchanged", "merged", "refuse"


def _hash(path: Path) -> Optional[str]:
    return sha256_hex(path.read_bytes()) if path.exists() else None


def _observe(case: Case) -> tuple[str, str]:
    """Map the current disk state to ``(table C row, expected result)``.

    Fails when the state belongs to no row of table C.
    """
    old_p = sha256_hex(case.old_project)
    old_t = sha256_hex(case.old_persons) if case.old_persons is not None else None
    p_hash, t_hash = _hash(case.project), _hash(case.persons_file)
    jr = read_journal(_REAL, case.project)

    if jr.state is JournalState.DAMAGED:
        pytest.fail(f"no row of table C: damaged journal ({jr.reason})")

    if jr.state is JournalState.ABSENT:
        p_old = p_hash == old_p
        t_old = t_hash == old_t  # also True when absent before and still absent
        if not case.with_persons:
            assert t_hash is None, "persons.json appeared although it is not a target"
        if p_old and t_old:
            return "0-7", UNCHANGED
        if not p_old and (not case.with_persons or not t_old):
            return "14-16", MERGED
        pytest.fail("no row of table C: journal absent but targets in different states")

    journal = jr.journal
    assert journal is not None
    by_role = {t.role: t for t in journal.targets}
    assert set(by_role) == ({"persons", "project"} if case.with_persons else {"project"})

    def state(role: str) -> tuple[str, bool, bool]:
        e = by_role[role]
        target = case.directory / e.target
        h = _hash(target)
        if h == e.new_sha256:
            cur = "NEW"
        elif (h is None and not e.existed_before) or h == e.old_sha256:
            cur = "OLD"
        else:
            pytest.fail(f"no row of table C: {e.target} matches neither state")
        tmp = case.directory / e.tmp
        tmp_ok = _hash(tmp) == e.new_sha256
        bak_ok = bool(e.backup) and _hash(case.directory / e.backup) == e.old_sha256
        return cur, tmp_ok, bak_ok

    p_cur, p_tmp, p_bak = state("project")
    if not case.with_persons:
        if p_cur == "NEW":
            return "13", MERGED
        return ("8-10", MERGED) if p_tmp else ("8b", UNCHANGED)

    t_cur, t_tmp, t_bak = state("persons")
    if (t_cur, p_cur) == ("NEW", "NEW"):
        return "13", MERGED
    if (t_cur, p_cur) == ("OLD", "OLD"):
        return ("8-10", MERGED) if (t_tmp and p_tmp) else ("8b", UNCHANGED)
    if (t_cur, p_cur) == ("NEW", "OLD"):
        if p_tmp:
            return "11", MERGED
        return ("11b", UNCHANGED) if t_bak else ("11c", REFUSE)
    # T OLD, P NEW: the reordering rows
    if t_tmp:
        return "12b", MERGED
    return ("12c", UNCHANGED) if p_bak else ("12c-refuse", REFUSE)


_ARTIFACT_SUFFIXES = (".new", ".restore", ".merge.lock", ".merge-journal.json", ".tmp")


def _leftovers(directory: Path) -> list[str]:
    found: list[str] = []
    for path in directory.rglob("*"):
        name = path.name
        if name.startswith(".merge-backup-") or name.endswith(_ARTIFACT_SUFFIXES):
            found.append(path.relative_to(directory).as_posix())
    return found


def _assert_restart(case: Case, expected: str, journal_present: bool) -> None:
    """Restart (new service, open) and check the all-or-nothing invariants."""
    before = snapshot_dir(case.directory)

    if expected == REFUSE:
        with pytest.raises(RecoveryRefusedError):
            ProjectService().open_project(case.project)
        assert snapshot_dir(case.directory) == before  # untouched
        return

    svc = ProjectService()
    svc.open_project(case.project)

    # Outcome message exactly when a journal existed.
    assert bool(svc.last_recovery_message) == journal_present, svc.last_recovery_message

    # No leftover journal, temp file, backup directory or lock.
    assert _leftovers(case.directory) == []
    assert not journal_path_for(case.project).exists()
    assert not lock_path_for(case.project).exists()
    assert not svc.is_merge_journal_pending()

    # All-or-nothing by checksum.
    p_new = sha256_hex(case.project.read_bytes()) != sha256_hex(case.old_project)
    persons_file = case.persons_file
    if case.with_persons:
        t_new = sha256_hex(persons_file.read_bytes()) != sha256_hex(case.old_persons)
        assert t_new == p_new, "project file and persons.json are in different states"
    else:
        assert not persons_file.exists()
    assert p_new == (expected == MERGED)
    if expected == UNCHANGED:
        assert case.project.read_bytes() == case.old_project
        if case.old_persons is not None:
            assert persons_file.read_bytes() == case.old_persons

    # The project loads and has the expected content.
    ids = [p.id for p in svc.data.persons]
    assert not svc.is_dirty
    if expected == MERGED:
        assert SURVIVOR in ids and RETIRED not in ids
        assert [h.merged_person_id for h in svc.data.merge_history] == [RETIRED]
        assert RETIRED in retired_person_ids(svc.data)
    else:
        assert SURVIVOR in ids and RETIRED in ids
        assert svc.data.merge_history == []

    # No orphaned mapping or alias; re-import does not resurrect the person.
    translation = translation_io.read_all(case.directory / "translation")
    assert all(m.app_id in ids for m in translation.persons)
    assert all(a.person_id in ids for a in translation.person_aliases)
    if case.with_persons:
        if expected == MERGED:
            assert [m for m in translation.persons if m.app_id == RETIRED] == []
            assert [(a.gedcom_id, a.person_id) for a in translation.person_aliases] == [
                (RETIRED_XREF, SURVIVOR)
            ]
        else:
            assert [(m.gedcom_id, m.app_id) for m in translation.persons] == [
                (RETIRED_XREF, RETIRED)
            ]
            assert translation.person_aliases == []

    # Recovery is idempotent: a second open changes nothing and reports nothing.
    settled = snapshot_dir(case.directory)
    again = ProjectService()
    again.open_project(case.project)
    assert again.last_recovery_message == ""
    assert snapshot_dir(case.directory) == settled


# ---------------------------------------------------------------------------
# Running one fault case
# ---------------------------------------------------------------------------


def _run_case(
    templates: dict[bool, Path],
    with_persons: bool,
    make_fs: Callable[[], object],
    workdir: Path,
) -> tuple[str, str]:
    case = _copy_case(templates, with_persons, workdir)
    svc = _open(case)
    plan = _plan(svc)
    revision, dirty = svc.revision, svc.is_dirty
    assert not dirty
    fs = make_fs()

    crashed = False
    outcome = None
    try:
        outcome = MergeEngine(svc, None, fs=fs).execute(plan)
    except SimulatedCrash:
        crashed = True

    if not crashed:
        assert outcome is not None
        if outcome.success:
            assert not svc.is_dirty and svc.revision == revision + 1
            assert RETIRED not in [p.id for p in svc.data.persons]
        else:
            # A failed merge leaves memory, the dirty flag and revision unchanged.
            assert outcome.message
            assert not svc.is_dirty and svc.revision == revision
            assert RETIRED in [p.id for p in svc.data.persons]

    row, expected = _observe(case)
    journal_present = journal_path_for(case.project).exists()
    if not crashed and outcome is not None and outcome.success:
        assert expected == MERGED, f"engine reported success but disk is row {row}"
    _assert_restart(case, expected, journal_present)
    return row, expected


def _fault_fs_factory(kind: str, n: int) -> Callable[[], object]:
    if kind == "power_loss":
        raise AssertionError("use _power_loss_factory")
    return lambda: FaultFs(n, kind, RealFs(delays=(), sleep=lambda _s: None))


def _power_loss_factory(n: int, phase: str, seed: int) -> Callable[[], object]:
    return lambda: PowerLossFs(
        RealFs(delays=(), sleep=lambda _s: None), seed=seed, crash_at=n, crash_phase=phase
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("with_persons", [True, False], ids=["with_persons", "no_persons"])
def test_crash_matrix_every_operation(
    templates: dict[bool, Path], with_persons: bool, tmp_path: Path
) -> None:
    """Every operation number, every fault kind (and power loss), table C rows."""
    counting = _dry_run(templates, with_persons)
    total = counting.op_count
    assert total > 10

    rows_seen: set[str] = set()
    counter = 0

    def run(make_fs: Callable[[], object], label: str) -> None:
        nonlocal counter
        counter += 1
        workdir = tmp_path / f"c{counter}"
        workdir.mkdir()
        try:
            row, expected = _run_case(templates, with_persons, make_fs, workdir)
        except BaseException as exc:  # add the fault point to any failure
            raise AssertionError(f"fault point {label}: {type(exc).__name__}: {exc}") from exc
        rows_seen.add(row)
        shutil.rmtree(workdir, ignore_errors=True)

    for n in range(1, total + 1):
        op = counting.ops[n - 1]
        for kind in FAULT_KINDS:
            if kind == "permission_error_persistent" and op.name != "replace":
                continue  # only replace operations can raise it; other n repeat a replace case
            if kind == "partial_write" and op.name not in (
                "write_file_durable",
                "copy_file_durable",
            ):
                continue  # behaves as crash_before elsewhere
            run(_fault_fs_factory(kind, n), f"{kind}@{n} ({op})")
        for phase in POWER_LOSS_PHASES:
            if phase == "mid" and op.name not in ("write_file_durable", "copy_file_durable"):
                continue
            for seed in (1, 2):
                run(_power_loss_factory(n, phase, seed), f"power_loss/{phase}/{seed}@{n} ({op})")

    # Every observed state maps to a row of table C (checked in _observe); the
    # protocol must at least reach the unchanged and merged outcomes.
    assert {"0-7", "14-16"} <= rows_seen or {"0-7", "13"} <= rows_seen
    if with_persons:
        assert "11" in rows_seen, rows_seen  # between the two replaces
    assert any(r in rows_seen for r in ("8-10", "8b")), rows_seen


def _persons_and_project_replace(case_ops: CountingFs, case: Case) -> tuple[int, int]:
    t = next(
        op.index for op in case_ops.ops if op.name == "replace" and op.args[1].name == "persons.json"
    )
    p = next(
        op.index
        for op in case_ops.ops
        if op.name == "replace" and op.args[1].name == case.project.name
    )
    return t, p


def _crash_after(templates: dict[bool, Path], workdir: Path, replace_of: str) -> tuple[Case, bytes]:
    """Crash right after the replace of ``persons.json`` or of the project file."""
    with tempfile.TemporaryDirectory() as tmp:
        probe = _copy_case(templates, True, Path(tmp))
        dry = _dry_run(templates, True)
        t_idx, p_idx = _persons_and_project_replace(dry, probe)
    case = _copy_case(templates, True, workdir)
    svc = _open(case)
    plan = _plan(svc)
    n = t_idx if replace_of == "persons" else p_idx
    with pytest.raises(SimulatedCrash):
        MergeEngine(svc, None, fs=FaultFs(n, "crash_after", RealFs(delays=(), sleep=lambda _s: None))).execute(plan)
    journal = read_journal(_REAL, case.project).journal
    assert journal is not None
    new_t = next(t for t in journal.targets if t.role == "persons")
    return case, new_t.new_sha256.encode()


def _corrupt(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0xFF
    path.write_bytes(bytes(data))


@pytest.mark.parametrize("variant", ["11", "11b", "11c", "12b", "12c"])
def test_reordering_rows_of_table_c(templates: dict[bool, Path], tmp_path: Path, variant: str) -> None:
    """Rows 11, 11b, 11c, 12b and 12c: points between the two replaces and reordering."""
    if variant.startswith("11"):
        case, _ = _crash_after(templates, tmp_path, "persons")
        journal = read_journal(_REAL, case.project).journal
        assert journal is not None
        by_role = {t.role: t for t in journal.targets}
        if variant in ("11b", "11c"):
            _corrupt(case.directory / by_role["project"].tmp)  # Temp P unusable
        if variant == "11c":
            (case.directory / by_role["persons"].backup).unlink()  # backup of T missing
        expected_row = variant
        expected = {"11": MERGED, "11b": UNCHANGED, "11c": REFUSE}[variant]
    else:
        case, _ = _crash_after(templates, tmp_path, "project")
        journal = read_journal(_REAL, case.project).journal
        assert journal is not None
        by_role = {t.role: t for t in journal.targets}
        new_persons = case.persons_file.read_bytes()
        # Rename of P persisted, rename of T lost: T back to old, new content in Temp T.
        case.persons_file.write_bytes(case.old_persons)
        temp_t = case.directory / by_role["persons"].tmp
        temp_t.write_bytes(new_persons)
        if variant == "12c":
            _corrupt(temp_t)  # Temp T unusable
        expected_row = variant
        expected = {"12b": MERGED, "12c": UNCHANGED}[variant]

    row, observed = _observe(case)
    assert row == expected_row and observed == expected
    _assert_restart(case, observed, journal_present=True)


def test_property_40_crash_atomicity() -> None:
    """**Validates: Requirements 7.12, 27.16, 27.17, 27.18, 27.19, 30.9**"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        templates_ = {
            flag: _build_template(root / f"template_{int(flag)}", flag) for flag in (True, False)
        }
        totals = {flag: _dry_run(templates_, flag).op_count for flag in (True, False)}

        counter = [0]

        @settings(max_examples=60, deadline=None)
        @given(
            with_persons=st.booleans(),
            kind=st.sampled_from((*FAULT_KINDS, "power_loss")),
            position=st.floats(min_value=0.0, max_value=1.0),
            phase=st.sampled_from(POWER_LOSS_PHASES),
            seed=st.integers(min_value=0, max_value=1000),
        )
        def check(with_persons: bool, kind: str, position: float, phase: str, seed: int) -> None:
            n = 1 + int(position * (totals[with_persons] - 1))
            counter[0] += 1
            workdir = root / f"w{counter[0]}"
            workdir.mkdir()
            if kind == "power_loss":
                make_fs = _power_loss_factory(n, phase, seed)
            else:
                make_fs = _fault_fs_factory(kind, n)
            _run_case(templates_, with_persons, make_fs, workdir)
            shutil.rmtree(workdir, ignore_errors=True)

        check()


# ---------------------------------------------------------------------------
# Task 13.14: recovery is deterministic and idempotent (Property 41)
# Requirements 27.16, 27.17, 27.21. Helpers are local to this section.
# ---------------------------------------------------------------------------

from slaktbusken.services.commit.recovery import recover_if_needed  # noqa: E402

_REC_KINDS = ("crash_before", "crash_after", "partial_write", "io_error_after")


def _interrupt(
    templates: dict[bool, Path],
    with_persons: bool,
    kind: str,
    n: int,
    workdir: Path,
    *,
    phase: str = "before",
    seed: int = 0,
) -> Case:
    """Run the merge until a fault at operation ``n`` and leave the disk as is."""
    case = _copy_case(templates, with_persons, workdir)
    svc = _open(case)
    plan = _plan(svc)
    fs = (
        _power_loss_factory(n, phase, seed)()
        if kind == "power_loss"
        else _fault_fs_factory(kind, n)()
    )
    try:
        MergeEngine(svc, None, fs=fs).execute(plan)
    except SimulatedCrash:
        pass
    return case


def _recover(project: Path, fs: object = None) -> tuple[str, Optional[str], str]:
    """One recovery run as a comparable value."""
    try:
        outcome = recover_if_needed(project, fs)  # type: ignore[arg-type]
    except RecoveryRefusedError as exc:
        return ("refused", exc.refusal.code, "")
    if outcome is None:
        return ("none", None, "")
    return ("ok", outcome.kind.value, outcome.message)


def _distinct_interrupted_states(
    templates: dict[bool, Path], with_persons: bool, base: Path
) -> list[tuple[str, Path]]:
    """One interrupted disk state per (table C row, fault kind), copied to ``base``."""
    total = _dry_run(templates, with_persons).op_count
    found: dict[tuple[str, str, str], Path] = {}
    for n in range(1, total + 1):
        for kind in _REC_KINDS:
            work = base / f"s{len(found)}_{kind}_{n}"
            work.mkdir(parents=True)
            case = _interrupt(templates, with_persons, kind, n, work)
            row, expected = _observe(case)
            key = (row, expected, "journal" if journal_path_for(case.project).exists() else "none")
            if key in found:
                shutil.rmtree(work, ignore_errors=True)
            else:
                found[key] = case.project
    return [(f"{k[0]}/{k[2]}", p) for k, p in sorted(found.items())]


def _clone(project: Path, dest: Path) -> Path:
    shutil.copytree(project.parent, dest)
    return dest / project.name


@pytest.mark.parametrize("with_persons", [True, False], ids=["with_persons", "no_persons"])
def test_recovery_idempotent(
    templates: dict[bool, Path], with_persons: bool, tmp_path: Path
) -> None:
    """Running recovery twice changes nothing the second time (every fault point)."""
    total = _dry_run(templates, with_persons).op_count
    checked = 0
    for n in range(1, total + 1):
        for kind in _REC_KINDS:
            work = tmp_path / f"{kind}_{n}"
            work.mkdir()
            case = _interrupt(templates, with_persons, kind, n, work)
            label = f"{kind}@{n}"
            first = _recover(case.project)
            settled = snapshot_dir(case.directory)
            second = _recover(case.project)
            if first[0] == "refused":
                assert second == first, label  # a refusal is repeatable and read-only
            else:
                assert second == ("none", None, ""), f"{label}: second run reported {second}"
            assert snapshot_dir(case.directory) == settled, f"{label}: second recovery changed the disk"
            if first[0] != "refused":
                assert _leftovers(case.directory) == [], label
            checked += 1
            shutil.rmtree(work, ignore_errors=True)
    assert checked > 10


@pytest.mark.parametrize("with_persons", [True, False], ids=["with_persons", "no_persons"])
def test_crash_during_recovery_converges(
    templates: dict[bool, Path], with_persons: bool, tmp_path: Path
) -> None:
    """A crash or I/O error injected into recovery itself: the next recovery
    reaches the same final disk state as an undisturbed recovery."""
    states = _distinct_interrupted_states(templates, with_persons, tmp_path / "states")
    assert len(states) >= 3
    disturbed_runs = 0
    old_case = _copy_case(templates, with_persons, tmp_path / "old")
    case_old = (old_case.old_project, old_case.old_persons)
    for label, project in states:
        reference = _clone(project, tmp_path / f"ref_{disturbed_runs}_{len(label)}")
        ref_result = _recover(reference)
        ref_snapshot = snapshot_dir(reference.parent)
        if ref_result[0] == "refused":
            continue  # recovery performs no writes: nothing to interrupt

        counting = CountingFs()
        probe = _clone(project, tmp_path / f"probe_{disturbed_runs}_{len(label)}")
        _recover(probe, counting)
        assert counting.op_count > 0

        for n in range(1, counting.op_count + 1):
            for kind in ("crash_before", "crash_after", "io_error_before", "partial_write"):
                dest = _clone(project, tmp_path / f"d{disturbed_runs}")
                disturbed_runs += 1
                fs = FaultFs(n, kind, RealFs(delays=(), sleep=lambda _s: None))
                try:
                    recover_if_needed(dest, fs)
                except (SimulatedCrash, OSError, RecoveryRefusedError):
                    pass
                where = f"state {label}, {kind}@{n} ({counting.ops[n - 1]})"
                again = _recover(dest)
                assert again[0] != "refused", f"{where}: next recovery refused ({again[1]})"
                if kind == "io_error_before":
                    # A transient read error can legitimately steer recovery onto the
                    # damaged-journal path (table B); only all-or-nothing is required.
                    case = Case(dest, with_persons, case_old[0], case_old[1])
                    p_new = dest.read_bytes() != case.old_project
                    if with_persons:
                        t_new = case.persons_file.read_bytes() != case.old_persons
                        assert t_new == p_new, f"{where}: mixed project/persons state"
                    assert _leftovers(dest.parent) == [], where
                else:
                    assert snapshot_dir(dest.parent) == ref_snapshot, (
                        f"{where}: final disk differs from undisturbed recovery"
                    )
                # and it is settled: one more run changes nothing
                assert _recover(dest) == ("none", None, ""), where
                shutil.rmtree(dest.parent, ignore_errors=True)
    assert disturbed_runs > 20


def test_property_41_recovery_deterministic() -> None:
    """**Validates: Requirements 27.16, 27.17, 27.21**

    The same interrupted state always recovers to the same result (outcome and
    final disk), and recovering again changes nothing.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        templates_ = {
            flag: _build_template(root / f"template_{int(flag)}", flag) for flag in (True, False)
        }
        totals = {flag: _dry_run(templates_, flag).op_count for flag in (True, False)}
        counter = [0]

        @settings(max_examples=60, deadline=None)
        @given(
            with_persons=st.booleans(),
            kind=st.sampled_from((*FAULT_KINDS, "power_loss")),
            position=st.floats(min_value=0.0, max_value=1.0),
            phase=st.sampled_from(POWER_LOSS_PHASES),
            seed=st.integers(min_value=0, max_value=1000),
        )
        def check(with_persons: bool, kind: str, position: float, phase: str, seed: int) -> None:
            n = 1 + int(position * (totals[with_persons] - 1))
            counter[0] += 1
            work = root / f"w{counter[0]}"
            work.mkdir()
            case = _interrupt(templates_, with_persons, kind, n, work, phase=phase, seed=seed)
            a = _clone(case.project, work / "copy_a")
            b = _clone(case.project, work / "copy_b")
            res_a, res_b = _recover(a), _recover(b)
            assert res_a == res_b
            assert snapshot_dir(a.parent) == snapshot_dir(b.parent)
            settled = snapshot_dir(a.parent)
            again = _recover(a)
            assert again == (("refused", res_a[1], "") if res_a[0] == "refused" else ("none", None, ""))
            assert snapshot_dir(a.parent) == settled
            shutil.rmtree(work, ignore_errors=True)

        check()
