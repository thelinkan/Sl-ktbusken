"""Fault-injection tests of the import save protocol (S1 to S8) and its recovery.

Every case runs the real ``ProjectService.save_project`` and the real recovery
(``ProjectService.open_project``) on real files in a temporary directory. A
``FaultFs`` raises an ``OSError`` or a ``SimulatedCrash`` at a chosen filesystem
operation. Each case asserts the two allowed end states (old project with the
old translation files, or new project with the new translation files), that no
intent or temporary file remains once recovery completed and, for exceptions,
the in-process state (dirty and pending kept before the commit point;
Import_Save_Unfinished after it).

**Validates: Requirements 20.6, 20.9, 20.16, 20.21**
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Optional

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from slaktbusken.persistence import translation_io
from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.persistence.translation_io import (
    FamilyMapping,
    PersonMapping,
    PlaceMapping,
    SourceMapping,
    TranslationData,
    write_all,
)
from slaktbusken.services.commit.journal import sha256_hex
from slaktbusken.services.commit.recovery import RecoveryRefusedError
from slaktbusken.services.commit.translation_commit import (
    ABSENT,
    MSG_RECOVERY_COMPLETED,
    MSG_RECOVERY_ROLLED_BACK,
    TRANSLATION_FILES,
    ImportSaveUnfinished,
    SaveConflict,
    SaveFailed,
)
from slaktbusken.services.project_service import (
    MergeNotFinishedError,
    PendingTranslation,
    ProjectService,
)
from tests.test_dataskydd.fault_fs import FaultFs, FsOp, SimulatedCrash

pytestmark = pytest.mark.mandatory_integrity

OLD_TITLE = "P"
PROJECT_NAME = "P.json.gz"
INTENT_NAME = PROJECT_NAME + ".import-intent.json"
TNAMES = ("persons.json", "places.json", "sources.json")

_PROPERTY_SETTINGS = dict(
    deadline=None,
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _encode(data: TranslationData) -> dict[str, bytes]:
    return {
        "persons.json": translation_io.dumps_persons(
            data.persons, data.families, data.person_aliases
        ),
        "places.json": translation_io.dumps_places(data.places),
        "sources.json": translation_io.dumps_sources(data.sources),
    }


def standard_new_data() -> TranslationData:
    return TranslationData(
        persons=[PersonMapping("@I1@", "person_1", "fp1")],
        families=[FamilyMapping("@F1@", "family_1")],
        places=[PlaceMapping("Ljusdal", "place_1", "Ljusdal")],
        sources=[SourceMapping("@S1@", "source_1", "Kyrkbok")],
    )


def standard_old_data() -> TranslationData:
    return TranslationData(places=[PlaceMapping("Gammal plats", "place_0", "Gammal")])


@dataclass
class Case:
    """A project on disk with a staged import, plus what the end state must be."""

    folder: Path
    new_title: str
    old_project: bytes
    old_files: dict[str, Optional[bytes]]
    new_files: dict[str, bytes]
    new_data: TranslationData

    @property
    def project(self) -> Path:
        return self.folder / PROJECT_NAME

    @property
    def tdir(self) -> Path:
        return self.folder / "translation"

    @classmethod
    def create(
        cls,
        root: Path,
        *,
        new_data: TranslationData | None = None,
        old_data: TranslationData | None = None,
        new_title: str = "Ny titel",
        absent: tuple[str, ...] = (),
    ) -> "Case":
        ProjectService().create_project(OLD_TITLE, root)
        folder = root / OLD_TITLE
        write_all(old_data if old_data is not None else standard_old_data(), folder / "translation")
        for name in absent:
            (folder / "translation" / name).unlink()
        data = new_data if new_data is not None else standard_new_data()
        old_files = {
            n: (p.read_bytes() if (p := folder / "translation" / n).exists() else None)
            for n in TNAMES
        }
        return cls(
            folder,
            new_title,
            (folder / PROJECT_NAME).read_bytes(),
            old_files,
            _encode(data),
            data,
        )

    def relocated(self, root: Path) -> "Case":
        """A copy of the folder (and of the expectations) under ``root``."""
        dest = root / OLD_TITLE
        shutil.copytree(self.folder, dest)
        return replace(self, folder=dest)

    # -- the save ----------------------------------------------------------

    def stage(self, fs: FaultFs | None) -> ProjectService:
        """Open the project, change it and stage the import (nothing is saved)."""
        ps = ProjectService()
        ps.open_project(self.project)
        ps._commit_fs = fs  # the save under test goes through the fault filesystem
        ps.data.project.title = self.new_title
        base = {
            f"translation/{n}": (sha256_hex(b) if b is not None else ABSENT)
            for n, b in self.old_files.items()
        }
        ps.adopt_working_copy(ps.data, PendingTranslation(self.new_data, base), "import")
        assert ps.is_dirty and ps.pending_translation is not None
        return ps

    def save(self, fs: FaultFs):
        """Run the save; return (service, raised exception or None)."""
        ps = self.stage(fs)
        try:
            ps.save_project()
        except (
            SaveConflict,
            SaveFailed,
            ImportSaveUnfinished,
            MergeNotFinishedError,  # the journal check failed: nothing was written
            SimulatedCrash,
        ) as exc:
            return ps, exc
        return ps, None

    def dry_run_ops(self, workdir: Path) -> list[FsOp]:
        """The operations of a fault-free save (on a throw-away copy)."""
        probe = self.relocated(workdir)
        fs = FaultFs()
        ps, exc = probe.save(fs)
        assert exc is None
        assert not ps.is_dirty
        return list(fs.ops)

    # -- observation -------------------------------------------------------

    def project_is_new(self) -> bool:
        return FilePersistence.load(self.project).project.title == self.new_title

    def project_is_old(self) -> bool:
        return self.project.read_bytes() == self.old_project

    def files(self) -> dict[str, Optional[bytes]]:
        return {
            n: (p.read_bytes() if (p := self.tdir / n).exists() else None) for n in TNAMES
        }

    def artifacts(self) -> list[str]:
        return sorted(
            str(p.relative_to(self.folder))
            for p in self.folder.rglob("*")
            if p.is_file() and (p.name.endswith(".new") or p.name.endswith(".import-intent.json"))
        )

    def intent_exists(self) -> bool:
        return (self.folder / INTENT_NAME).exists()

    def assert_allowed_end_state(self) -> None:
        files = self.files()
        old = files == self.old_files
        new = files == self.new_files
        assert (self.project_is_old() and old) or (self.project_is_new() and new), (
            f"project old={self.project_is_old()} new={self.project_is_new()}; "
            f"translation files old={old} new={new}"
        )

    def recover(self) -> str:
        """Open with the real filesystem (runs the recovery); return its message."""
        ps = ProjectService()
        ps.open_project(self.project)
        assert not ps.import_save_unfinished
        return ps.last_recovery_message

    def settle(self) -> str:
        """Run the real recovery and assert the end state; return the message."""
        had_intent = self.intent_exists()
        was_new = self.project_is_new()
        message = self.recover()
        if not had_intent:
            assert message == ""
        else:
            assert message == (MSG_RECOVERY_COMPLETED if was_new else MSG_RECOVERY_ROLLED_BACK)
        self.assert_allowed_end_state()
        assert self.artifacts() == []
        return message

    def assert_in_process_state(self, ps: ProjectService, exc: BaseException | None) -> None:
        """The in-process state after an ordinary exception (or success)."""
        if exc is None:
            assert not ps.is_dirty and ps.pending_translation is None
            assert not ps.import_save_unfinished
        elif self.project_is_new():
            assert isinstance(exc, ImportSaveUnfinished)
            assert not ps.is_dirty
            assert ps.pending_translation is None
            assert ps.import_save_unfinished
        else:
            assert isinstance(exc, (SaveFailed, SaveConflict, MergeNotFinishedError))
            assert ps.is_dirty
            assert ps.pending_translation is not None
            assert not ps.import_save_unfinished


def check_fault(case: Case, fs: FaultFs, *, expect_triggered: bool = True) -> None:
    """Save under ``fs``, check the in-process state, then recover and check the files."""
    ps, exc = case.save(fs)
    if expect_triggered:
        assert fs.triggered, "the fault never fired"
    if fs.kind == "exception":
        assert not isinstance(exc, SimulatedCrash)
        case.assert_in_process_state(ps, exc)
        if isinstance(exc, (SaveFailed, SaveConflict, MergeNotFinishedError)):
            # Before the commit point the attempt cleans up after itself.
            assert case.project_is_old() and case.files() == case.old_files
            assert case.artifacts() == []
    else:
        assert isinstance(exc, SimulatedCrash)
    case.settle()


def _named(op: FsOp, name: str, base: str) -> bool:
    """A write of the temporary file of ``base``."""
    return op.name == name and re.fullmatch(rf"{re.escape(base)}\.[0-9a-zA-Z]+\.new", op.path.name) is not None


def find(ops: list[FsOp], kind: str, base: str, *, after: int = 0) -> FsOp:
    """First write of the temp file of ``base`` or replace/remove with target ``base``."""
    for op in ops:
        if op.index <= after:
            continue
        if kind == "write" and _named(op, "write_file_durable", base):
            return op
        if kind == "replace" and op.name == "replace" and op.target.name == base:
            return op
        if kind == "remove" and op.name == "remove" and op.path.name == base:
            return op
    raise AssertionError(f"no {kind} of {base} in {[str(o) for o in ops]}")


@pytest.fixture
def case(tmp_path: Path) -> Case:
    return Case.create(tmp_path / "live")


@pytest.fixture
def ops(case: Case, tmp_path: Path) -> list[FsOp]:
    return case.dry_run_ops(tmp_path / "probe")


KINDS = ["exception", "crash"]


# ---------------------------------------------------------------------------
# Order of the protocol
# ---------------------------------------------------------------------------


def test_save_writes_intent_project_translation_in_order(ops: list[FsOp]) -> None:
    w_intent = find(ops, "write", INTENT_NAME)
    r_intent = find(ops, "replace", INTENT_NAME)
    w_project = find(ops, "write", PROJECT_NAME)
    w_files = [find(ops, "write", n) for n in TNAMES]
    r_project = find(ops, "replace", PROJECT_NAME)
    r_files = [find(ops, "replace", n) for n in TNAMES]
    rm_intent = find(ops, "remove", INTENT_NAME)

    order = [w_intent, r_intent, w_project, *w_files, r_project, *r_files, rm_intent]
    assert [o.index for o in order] == sorted(o.index for o in order)
    assert len({o.index for o in order}) == len(order)
    # The intent is the first write and its removal the last mutating operation.
    mutating = [o for o in ops if o.name in ("write_file_durable", "replace", "remove")]
    assert mutating[0] is w_intent
    assert mutating[-1] is rm_intent


# ---------------------------------------------------------------------------
# Failures before the commit point
# ---------------------------------------------------------------------------


def test_save_failure_before_project_replace_restores_state(case: Case, ops: list[FsOp]) -> None:
    fs = FaultFs(fail_at=find(ops, "replace", PROJECT_NAME).index, kind="exception")
    ps, exc = case.save(fs)
    assert isinstance(exc, SaveFailed) and not exc.unresolved
    assert case.project_is_old() and case.files() == case.old_files
    assert case.artifacts() == []
    assert ps.is_dirty and ps.pending_translation is not None
    assert not ps.import_save_unfinished
    # Nothing is lost: the same service saves once the fault is gone.
    ps._commit_fs = None
    ps.save_project()
    assert case.project_is_new() and case.files() == case.new_files
    assert case.artifacts() == []
    assert not ps.is_dirty and ps.pending_translation is None


@pytest.mark.parametrize("kind", KINDS)
def test_save_fault_before_intent(case: Case, ops: list[FsOp], kind: str) -> None:
    fs = FaultFs(fail_at=find(ops, "write", INTENT_NAME).index, kind=kind)
    check_fault(case, fs)
    assert case.project_is_old() and case.files() == case.old_files


@pytest.mark.parametrize("kind", KINDS)
def test_save_fault_after_intent(case: Case, ops: list[FsOp], kind: str) -> None:
    # The intent is in place; the project temp file is not written yet.
    fs = FaultFs(fail_at=find(ops, "write", PROJECT_NAME).index, kind=kind)
    ps, exc = case.save(fs)
    if kind == "crash":
        assert case.intent_exists()
    case.assert_in_process_state(ps, exc) if kind == "exception" else None
    case.settle()
    assert case.project_is_old() and case.files() == case.old_files


@pytest.mark.parametrize("kind", KINDS)
def test_save_fault_after_project_write(case: Case, ops: list[FsOp], kind: str) -> None:
    fs = FaultFs(fail_at=find(ops, "write", PROJECT_NAME).index, kind=kind, after=True)
    check_fault(case, fs)
    assert case.project_is_old() and case.files() == case.old_files


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("name", TNAMES)
def test_save_fault_after_each_translation_write(
    case: Case, ops: list[FsOp], name: str, kind: str
) -> None:
    fs = FaultFs(fail_at=find(ops, "write", name).index, kind=kind, after=True)
    check_fault(case, fs)
    # The project file is still old, so the save was rolled back.
    assert case.project_is_old() and case.files() == case.old_files


# ---------------------------------------------------------------------------
# Failures after the commit point
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_save_fault_before_intent_removal(case: Case, ops: list[FsOp], kind: str) -> None:
    fs = FaultFs(fail_at=find(ops, "remove", INTENT_NAME).index, kind=kind)
    ps, exc = case.save(fs)
    # Project and translation files are already new; only the intent is left.
    assert case.project_is_new() and case.files() == case.new_files
    assert case.intent_exists()
    if kind == "exception":
        case.assert_in_process_state(ps, exc)
        assert ps.import_save_unfinished
    case.settle()
    assert case.project_is_new() and case.files() == case.new_files


# ---------------------------------------------------------------------------
# A fault at every filesystem call
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("after", [False, True])
def test_save_fault_at_every_fs_call_as_exception(
    case: Case, ops: list[FsOp], tmp_path: Path, after: bool
) -> None:
    for op in ops:
        trial = case.relocated(tmp_path / f"e{int(after)}_{op.index}")
        fs = FaultFs(fail_at=op.index, kind="exception", after=after)
        try:
            check_fault(trial, fs)
        except AssertionError as err:
            raise AssertionError(f"exception {'after' if after else 'before'} {op}: {err}") from err


@pytest.mark.parametrize("kind, after", [("crash", False), ("crash", True), ("torn", False)])
def test_save_fault_at_every_fs_call_as_crash(
    case: Case, ops: list[FsOp], tmp_path: Path, kind: str, after: bool
) -> None:
    for op in ops:
        trial = case.relocated(tmp_path / f"c{kind}{int(after)}_{op.index}")
        fs = FaultFs(fail_at=op.index, kind=kind, after=after)
        try:
            check_fault(trial, fs)
        except AssertionError as err:
            raise AssertionError(f"{kind} {'after' if after else 'before'} {op}: {err}") from err


def test_crash_at_every_save_step_recovers_consistently(
    case: Case, ops: list[FsOp], tmp_path: Path
) -> None:
    """Crash at each step S2 to S8 (before and after it); the message matches the state."""
    steps = {
        "S2 write intent": find(ops, "write", INTENT_NAME),
        "S3 publish intent": find(ops, "replace", INTENT_NAME),
        "S4 write project": find(ops, "write", PROJECT_NAME),
        **{f"S5 write {n}": find(ops, "write", n) for n in TNAMES},
        "S6 replace project": find(ops, "replace", PROJECT_NAME),
        **{f"S7 replace {n}": find(ops, "replace", n) for n in TNAMES},
        "S8 remove intent": find(ops, "remove", INTENT_NAME),
    }
    for label, op in steps.items():
        for kind, after in (("crash", False), ("crash", True), ("torn", False)):
            trial = case.relocated(tmp_path / f"s{op.index}{kind}{int(after)}")
            fs = FaultFs(fail_at=op.index, kind=kind, after=after)
            _, exc = trial.save(fs)
            assert isinstance(exc, SimulatedCrash), label
            was_new = trial.project_is_new()
            # The commit point is the replace of the project file.
            expected_new = op.index > steps["S6 replace project"].index or (
                op.index == steps["S6 replace project"].index and after
            )
            assert was_new == expected_new, f"{label} {kind} after={after}"
            trial.settle()
            assert trial.project_is_new() == was_new, f"{label} {kind} after={after}"


# ---------------------------------------------------------------------------
# Faults and crashes during recovery
# ---------------------------------------------------------------------------


def _crashed_states(case: Case, ops: list[FsOp], workdir: Path) -> dict[str, Case]:
    points = {
        "intent published": find(ops, "replace", INTENT_NAME),
        "project replaced": find(ops, "replace", PROJECT_NAME),
        "one file replaced": find(ops, "replace", "persons.json"),
        "all files replaced": find(ops, "replace", "sources.json"),
    }
    states = {}
    for label, op in points.items():
        trial = case.relocated(workdir / f"state{op.index}")
        _, exc = trial.save(FaultFs(fail_at=op.index, kind="crash", after=True))
        assert isinstance(exc, SimulatedCrash)
        states[label] = trial
    return states


def test_recovery_fault_at_every_fs_call(case: Case, ops: list[FsOp], tmp_path: Path) -> None:
    states = _crashed_states(case, ops, tmp_path / "crashed")
    for label, crashed in states.items():
        # Count the operations of a fault-free recovery on a copy.
        probe = crashed.relocated(tmp_path / f"probe_{label}")
        counting = FaultFs()
        ps = ProjectService(commit_fs=counting)
        ps.open_project(probe.project)
        total = counting.op_count
        assert total > 0
        for n in range(1, total + 1):
            for kind, after in (("exception", False), ("exception", True), ("crash", False), ("crash", True), ("torn", False)):
                trial = crashed.relocated(tmp_path / f"r_{label}_{n}_{kind}{int(after)}")
                fs = FaultFs(fail_at=n, kind=kind, after=after)
                ps = ProjectService(commit_fs=fs)
                try:
                    ps.open_project(trial.project)
                except (OSError, SimulatedCrash, RecoveryRefusedError):
                    pass
                where = f"{label}: {kind} {'after' if after else 'before'} op {n} ({fs.ops[n - 1]})"
                assert fs.triggered or after or kind == "torn", where
                try:
                    trial.settle()
                except AssertionError as err:
                    raise AssertionError(f"{where}: {err}") from err


def test_recovery_is_idempotent_after_crash(case: Case, ops: list[FsOp], tmp_path: Path) -> None:
    states = _crashed_states(case, ops, tmp_path / "crashed")
    for label, crashed in states.items():
        first = crashed.recover()
        snapshot = (crashed.project.read_bytes(), crashed.files())
        assert first in (MSG_RECOVERY_COMPLETED, MSG_RECOVERY_ROLLED_BACK), label
        assert crashed.artifacts() == []
        crashed.assert_allowed_end_state()
        # A second open finds nothing to do and changes nothing.
        assert crashed.recover() == ""
        assert (crashed.project.read_bytes(), crashed.files()) == snapshot

    # A crash in the middle of the recovery, then the recovery again (twice).
    fresh = _crashed_states(case, ops, tmp_path / "crashed_again")["project replaced"]
    redo = fresh.relocated(tmp_path / "redo")
    probe_fs = FaultFs()
    ProjectService(commit_fs=probe_fs).open_project(fresh.relocated(tmp_path / "probe2").project)
    first_replace = next(op.index for op in probe_fs.ops if op.name == "replace")
    fs = FaultFs(fail_at=first_replace, kind="crash", after=True)
    with pytest.raises(SimulatedCrash):
        ProjectService(commit_fs=fs).open_project(redo.project)
    assert redo.recover() == MSG_RECOVERY_COMPLETED
    assert redo.recover() == ""
    assert redo.project_is_new() and redo.files() == redo.new_files
    assert redo.artifacts() == []


# ---------------------------------------------------------------------------
# The two decisions of the recovery
# ---------------------------------------------------------------------------


def test_open_completes_translation_when_project_is_new(case: Case, ops: list[FsOp]) -> None:
    fs = FaultFs(fail_at=find(ops, "replace", PROJECT_NAME).index, kind="crash", after=True)
    _, exc = case.save(fs)
    assert isinstance(exc, SimulatedCrash)
    assert case.project_is_new() and case.files() == case.old_files  # half done
    assert case.intent_exists()

    assert case.recover() == MSG_RECOVERY_COMPLETED
    assert case.project_is_new() and case.files() == case.new_files
    assert case.artifacts() == []


def test_open_discards_intent_when_project_is_old(case: Case, ops: list[FsOp]) -> None:
    fs = FaultFs(fail_at=find(ops, "replace", PROJECT_NAME).index, kind="crash")
    _, exc = case.save(fs)
    assert isinstance(exc, SimulatedCrash)
    assert case.project_is_old() and case.files() == case.old_files
    assert case.intent_exists()

    assert case.recover() == MSG_RECOVERY_ROLLED_BACK
    assert case.project_is_old() and case.files() == case.old_files
    assert case.artifacts() == []


# ---------------------------------------------------------------------------
# A file changed at an exact point (callback hook)
# ---------------------------------------------------------------------------


def test_file_changed_before_commit_point_is_a_conflict_and_is_kept(
    case: Case, ops: list[FsOp]
) -> None:
    external = b'{"mappings": ["changed outside"]}\n'

    def change(_fs: FaultFs, _op: FsOp) -> None:
        (case.tdir / "places.json").write_bytes(external)

    # Just before the second Digest_Verification (S6): the first call after the last temp write.
    last_write = find(ops, "write", "sources.json").index
    verify = next(o for o in ops if o.index > last_write and o.name == "exists")
    fs = FaultFs(hook_at=verify.index, hook=change)
    ps, exc = case.save(fs)
    assert isinstance(exc, SaveConflict) and "translation/places.json" in exc.files
    assert case.project_is_old()
    assert (case.tdir / "places.json").read_bytes() == external
    assert case.artifacts() == []
    assert ps.is_dirty and ps.pending_translation is not None


def test_file_changed_after_commit_point_is_kept_and_open_refuses(
    case: Case, ops: list[FsOp]
) -> None:
    external = b'{"mappings": ["changed outside"]}\n'
    r_project = find(ops, "replace", PROJECT_NAME).index
    check = next(
        o for o in ops if o.index > r_project and o.name == "exists" and o.path.name == "persons.json"
    )

    def change(_fs: FaultFs, _op: FsOp) -> None:
        (case.tdir / "persons.json").write_bytes(external)

    fs = FaultFs(hook_at=check.index, hook=change)
    ps, exc = case.save(fs)
    assert isinstance(exc, ImportSaveUnfinished) and exc.files == ("translation/persons.json",)
    assert ps.import_save_unfinished and not ps.is_dirty
    assert case.project_is_new()
    assert (case.tdir / "persons.json").read_bytes() == external
    assert case.intent_exists()
    with pytest.raises(RecoveryRefusedError) as refused:
        case.recover()
    assert refused.value.refusal.code == "T2"
    assert (case.tdir / "persons.json").read_bytes() == external
    assert case.intent_exists()


# ---------------------------------------------------------------------------
# Property 24
# ---------------------------------------------------------------------------

_text = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=10)
_persons = st.lists(
    st.builds(PersonMapping, gedcom_id=_text, app_id=_text, fingerprint=st.none() | _text),
    max_size=3,
)
_families = st.lists(st.builds(FamilyMapping, gedcom_id=_text, app_id=_text), max_size=2)
_places = st.lists(
    st.builds(PlaceMapping, gedcom_place=_text, app_id=_text, name=_text), max_size=3
)
_sources = st.lists(
    st.builds(SourceMapping, gedcom_id=_text, app_id=_text, title=_text), max_size=3
)
_translation = st.builds(
    TranslationData, persons=_persons, families=_families, places=_places, sources=_sources
)


@settings(**_PROPERTY_SETTINGS)
@given(
    new_data=_translation,
    old_data=_translation,
    title_suffix=st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=8),
    absent=st.lists(st.sampled_from(TNAMES), unique=True, max_size=2),
    kind=st.sampled_from(["exception", "crash", "torn"]),
    after=st.booleans(),
    chooser=st.data(),
)
def test_dp_property_24_save_with_pending_translation_is_crash_consistent(
    new_data: TranslationData,
    old_data: TranslationData,
    title_suffix: str,
    absent: list[str],
    kind: str,
    after: bool,
    chooser: st.DataObject,
) -> None:
    """**Validates: Requirements 20.6, 20.9, 20.16, 20.21**

    For any project content, any pending translation and any single fault at
    any filesystem call of the save, the files after recovery are either the old
    project with the old translation files or the new project with the new ones,
    and no intent or temporary file remains.
    """
    root = Path(tempfile.mkdtemp(prefix="dp24_"))
    try:
        case = Case.create(
            root / "live",
            new_data=new_data,
            old_data=old_data,
            new_title=OLD_TITLE + title_suffix,
            absent=tuple(absent),
        )
        total = len(case.dry_run_ops(root / "probe"))
        n = chooser.draw(st.integers(min_value=1, max_value=total), label="fault point")
        trial = case.relocated(root / "trial")
        check_fault(trial, FaultFs(fail_at=n, kind=kind, after=after))
    finally:
        shutil.rmtree(root, ignore_errors=True)
