"""A file changed outside Släktbusken is never overwritten (import save and recovery).

Every case runs the real ``ProjectService.save_project`` and the real recovery
on real files in a temporary directory. A ``FaultFs`` hook changes a file at an
exact filesystem operation of the save, or the test changes it between a crash
and the recovery.

Time points that are enumerated (Property 27):

* ``before_save``: the file is changed after the import was staged and before ``Spara``.
* ``during_save``: the file is changed before each single operation of the save
  (every point between two operations, S1 to S8).
* ``crash_then_recovery``: the save crashes before or after each single operation,
  the file is changed, then the real recovery runs.

Expected outcome while the save runs, by the first Digest_Verification of the file
that still follows the change:

* it comes before the project replace (S1 or S6): ``SaveConflict``; nothing is
  replaced and the attempt removes only its own artifacts;
* it comes after the project replace (S7, a translation file): ``ImportSaveUnfinished``;
  the project is new, the intent and the temporary files are kept and the next
  open refuses (T2) without changing a file;
* no digest check follows and the file is not replaced later (the change is after
  the last write to the file, or the file is not part of the save): the save ends
  normally and the file keeps the external bytes.

Documented limit (excluded from the enumeration, see ``classify``): the window
between the last digest check of a file and the ``replace`` that overwrites it.
For a translation file that is the S7 check-to-replace window and for the project
file the S6 check-to-project-replace window. A change inside that window cannot
be detected without an atomic compare-and-swap, which the operating system does
not offer. For a translation file the second check of S7 narrows it to two
consecutive operations; a change between the S6 check and the project replace
is caught by S7 as ``ImportSaveUnfinished`` (not as ``SaveConflict``).

**Validates: Requirements 20.7, 20.8, 20.10, 20.11, 20.16, 20.17, 20.18, 20.19, 20.20**
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from hypothesis import HealthCheck, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from slaktbusken.persistence import translation_io  # noqa: E402
from slaktbusken.persistence.file_io import FilePersistence  # noqa: E402
from slaktbusken.persistence.translation_io import (  # noqa: E402
    FamilyMapping,
    PersonMapping,
    PlaceMapping,
    SourceMapping,
    TranslationData,
    write_all,
)
from slaktbusken.services.commit.journal import sha256_hex  # noqa: E402
from slaktbusken.services.commit.recovery import RecoveryRefusedError  # noqa: E402
from slaktbusken.services.commit.translation_commit import (  # noqa: E402
    ABSENT,
    MSG_UNOWNED_STATE,
    ImportSaveUnfinished,
    SaveConflict,
    SaveFailed,
    recover_translation_intent,
)
from slaktbusken.services.edit_session import MSG_IMPORT_SAVE_UNFINISHED  # noqa: E402
from slaktbusken.services.import_service import ImportError as ImportServiceError  # noqa: E402
from slaktbusken.services.import_service import ImportService  # noqa: E402
from slaktbusken.services.project_service import (  # noqa: E402
    MERGE_UNFINISHED_MESSAGE,
    MergeNotFinishedError,
    PendingTranslation,
    ProjectService,
)
from slaktbusken.services.validation_service import ValidationService  # noqa: E402
from slaktbusken.ui.merge.recovery_dialogs import translation_edit_refusal  # noqa: E402
from tests.test_dataskydd.fault_fs import FaultFs, FsOp, SimulatedCrash  # noqa: E402

pytestmark = pytest.mark.mandatory_integrity

OLD_TITLE = "P"
PROJECT_NAME = "P.json.gz"
INTENT_NAME = PROJECT_NAME + ".import-intent.json"
TNAMES = ("persons.json", "places.json", "sources.json")
TARGETS = ("project", *TNAMES)
MUTATING = (
    "write_file_durable",
    "copy_file_durable",
    "replace",
    "remove",
    "rmtree",
    "mkdir",
    "create_exclusive",
)

_PROPERTY_SETTINGS = dict(
    deadline=None,
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


# ---------------------------------------------------------------------------
# Harness (copied from test_translation_commit.py, reduced to what is needed)
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
        old_data: TranslationData | None = None,
        absent: tuple[str, ...] = (),
    ) -> "Case":
        ProjectService().create_project(OLD_TITLE, root)
        folder = root / OLD_TITLE
        write_all(old_data if old_data is not None else standard_old_data(), folder / "translation")
        for name in absent:
            (folder / "translation" / name).unlink()
        data = standard_new_data()
        old_files = {
            n: (p.read_bytes() if (p := folder / "translation" / n).exists() else None)
            for n in TNAMES
        }
        return cls(folder, "Ny titel", (folder / PROJECT_NAME).read_bytes(), old_files, _encode(data), data)

    def relocated(self, root: Path) -> "Case":
        dest = root / OLD_TITLE
        shutil.copytree(self.folder, dest)
        return replace(self, folder=dest)

    def changed(self, name: str) -> bool:
        return self.old_files[name] != self.new_files[name]

    def stage(self, fs: FaultFs | None) -> ProjectService:
        ps = ProjectService()
        ps.open_project(self.project)
        ps._commit_fs = fs
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
        return ps, self.save_with(ps)

    @staticmethod
    def save_with(ps: ProjectService) -> BaseException | None:
        try:
            ps.save_project()
        except (
            SaveConflict,
            SaveFailed,
            ImportSaveUnfinished,
            MergeNotFinishedError,
            SimulatedCrash,
        ) as exc:
            return exc
        return None

    def dry_run_ops(self, workdir: Path) -> list[FsOp]:
        probe = self.relocated(workdir)
        fs = FaultFs()
        ps, exc = probe.save(fs)
        assert exc is None and not ps.is_dirty
        return list(fs.ops)

    # -- observation -------------------------------------------------------

    def project_is_new(self) -> bool:
        return FilePersistence.load(self.project).project.title == self.new_title

    def project_is_old(self) -> bool:
        return self.project.read_bytes() == self.old_project

    def files(self) -> dict[str, Optional[bytes]]:
        return {n: (p.read_bytes() if (p := self.tdir / n).exists() else None) for n in TNAMES}

    def artifacts(self) -> list[str]:
        return sorted(
            str(p.relative_to(self.folder))
            for p in self.folder.rglob("*")
            if p.is_file() and (p.name.endswith(".new") or p.name.endswith(".import-intent.json"))
        )

    def intent_exists(self) -> bool:
        return (self.folder / INTENT_NAME).exists()

    # -- the external change -----------------------------------------------

    def path_of(self, target: str) -> Path:
        return self.project if target == "project" else self.tdir / target

    def write_external(self, target: str, data: bytes) -> None:
        self.path_of(target).write_bytes(data)

    def rel(self, target: str) -> str:
        return PROJECT_NAME if target == "project" else f"translation/{target}"

    def restore(self, target: str) -> None:
        """Put the file back as it was before the import (the user restores it)."""
        path = self.path_of(target)
        old = self.old_project if target == "project" else self.old_files[target]
        if old is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(old)


def snapshot(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


def mutating(fs: FaultFs) -> list[FsOp]:
    return [o for o in fs.ops if o.name in MUTATING]


def refusal_of(ps: ProjectService, case: Case):
    with pytest.raises(RecoveryRefusedError) as refused:
        ps.open_project(case.project)
    return refused.value.refusal


def assert_refuses_unchanged(
    case: Case, code: str, *, expect_in_message: tuple[str, ...] = ()
) -> str:
    """The recovery refuses with ``code`` and changes no file, intent included."""
    before = snapshot(case.folder)
    refusal = refusal_of(ProjectService(), case)
    assert refusal.code == code
    assert snapshot(case.folder) == before
    for text in expect_in_message:
        assert text in refusal.message, text
    # A second attempt refuses the same way and still changes nothing.
    assert refusal_of(ProjectService(), case).code == code
    assert snapshot(case.folder) == before
    return refusal.message


def state_line(name: str, state: str) -> str:
    return f"{name}   ({state})"


def find(ops: list[FsOp], kind: str, base: str) -> FsOp:
    """First write of the temp file of ``base`` or replace/remove with target ``base``."""
    import re

    for op in ops:
        if kind == "write" and op.name == "write_file_durable" and re.fullmatch(
            rf"{re.escape(base)}\.[0-9a-zA-Z]+\.new", op.path.name
        ):
            return op
        if kind == "replace" and op.name == "replace" and op.target.name == base:
            return op
        if kind == "remove" and op.name == "remove" and op.path.name == base:
            return op
    raise AssertionError(f"no {kind} of {base} in {[str(o) for o in ops]}")


def digest_ops(ops: list[FsOp], base: str) -> list[int]:
    """Indices of the operations that read the content state of file ``base``."""
    return [o.index for o in ops if o.name in ("exists", "read_bytes") and o.path.name == base]


def r_project_index(ops: list[FsOp]) -> int:
    return find(ops, "replace", PROJECT_NAME).index


@pytest.fixture
def case(tmp_path: Path) -> Case:
    return Case.create(tmp_path / "live")


@pytest.fixture
def ops(case: Case, tmp_path: Path) -> list[FsOp]:
    return case.dry_run_ops(tmp_path / "probe")


def crash_at(case: Case, op: FsOp, *, after: bool) -> ProjectService:
    ps, exc = case.save(FaultFs(fail_at=op.index, kind="crash", after=after))
    assert isinstance(exc, SimulatedCrash)
    return ps


# ---------------------------------------------------------------------------
# Time points of the enumeration
# ---------------------------------------------------------------------------

EXTERNAL = b"EXTERNAL: changed outside Slaktbusken\n"


def classify(ops: list[FsOp], base: str, changed: bool, n: int) -> str:
    """What a change of file ``base`` just before operation ``n`` of the save leads to.

    ``conflict``: the next digest check is before the project replace (S1, S6).
    ``unfinished``: the next digest check is after the project replace (S7).
    ``window``: no digest check follows but the file is still replaced by this
    save (the documented check-to-replace window; not guaranteed).
    ``success``: the save no longer touches the file.
    """
    r_project = r_project_index(ops)
    nxt = next((k for k in digest_ops(ops, base) if k >= n), None)
    if nxt is not None:
        return "conflict" if nxt < r_project else "unfinished"
    replaced = [o.index for o in ops if o.name == "replace" and o.target.name == base]
    if replaced and n <= replaced[0]:
        return "window"
    return "success"


VARIANTS = {
    "standard": dict(),
    "sources_unchanged": dict(
        old_data=TranslationData(
            places=[PlaceMapping("Gammal plats", "place_0", "Gammal")],
            sources=[SourceMapping("@S1@", "source_1", "Kyrkbok")],
        )
    ),
    "places_absent": dict(absent=("places.json",)),
}
_ops_cache: dict[str, list[FsOp]] = {}


def variant_ops(variant: str) -> list[FsOp]:
    if variant not in _ops_cache:
        root = Path(tempfile.mkdtemp(prefix="dp27ops_"))
        try:
            _ops_cache[variant] = Case.create(root / "live", **VARIANTS[variant]).dry_run_ops(
                root / "probe"
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)
    return _ops_cache[variant]


_external = st.binary(max_size=48).map(lambda b: b"EXTERNAL:" + b)


def _base(target: str) -> str:
    return PROJECT_NAME if target == "project" else target


def _changed(case: Case, target: str) -> bool:
    return True if target == "project" else case.changed(target)


def check_conflict(case: Case, ps: ProjectService, exc, target: str, pre: dict[str, bytes], external: bytes):
    """A refused save: only the external change is on disk, nothing else was written."""
    assert isinstance(exc, SaveConflict), exc
    assert exc.files == (case.rel(target),)
    expected = dict(pre)
    expected[case.rel(target)] = external
    assert snapshot(case.folder) == expected
    assert ps.is_dirty and ps.pending_translation is not None
    assert not ps.import_save_unfinished
    assert case.rel(target) in exc.message and MSG_UNOWNED_STATE in exc.message


def check_refusal_message(case: Case, target: str, message: str, code: str) -> None:
    if target == "project":
        assert code == "T1"
        assert state_line(str(case.project), MSG_UNOWNED_STATE) in message
    else:
        assert code == "T2"
        assert state_line(case.rel(target), MSG_UNOWNED_STATE) in message


# ---------------------------------------------------------------------------
# Property 27
# ---------------------------------------------------------------------------


@settings(**_PROPERTY_SETTINGS)
@given(
    variant=st.sampled_from(sorted(VARIANTS)),
    target=st.sampled_from(TARGETS),
    external=_external,
)
def test_dp_property_27_change_before_save_is_never_overwritten(
    variant: str, target: str, external: bytes
) -> None:
    """**Validates: Requirements 20.7, 20.8, 20.10**

    A file changed after the import and before ``Spara`` refuses the save with a
    conflict naming the file; the file keeps its bytes, nothing is written.
    """
    root = Path(tempfile.mkdtemp(prefix="dp27a_"))
    try:
        case = Case.create(root / "live", **VARIANTS[variant])
        counting = FaultFs()
        ps = case.stage(counting)
        pre = snapshot(case.folder)
        case.write_external(target, external)
        exc = Case.save_with(ps)
        check_conflict(case, ps, exc, target, pre, external)
        assert mutating(counting) == []
    finally:
        shutil.rmtree(root, ignore_errors=True)


@settings(**_PROPERTY_SETTINGS)
@given(
    variant=st.sampled_from(sorted(VARIANTS)),
    target=st.sampled_from(TARGETS),
    external=_external,
    chooser=st.data(),
)
def test_dp_property_27_change_between_any_two_save_operations_is_never_overwritten(
    variant: str, target: str, external: bytes, chooser: st.DataObject
) -> None:
    """**Validates: Requirements 20.7, 20.8, 20.10, 20.11, 20.16**

    The file is changed before any single operation of the save. The save either
    refuses (conflict, or unfinished after the commit point) or no longer touches
    the file; in no case does it write over the external bytes.
    """
    ops_ = variant_ops(variant)
    base = _base(target)
    root = Path(tempfile.mkdtemp(prefix="dp27b_"))
    try:
        case = Case.create(root / "live", **VARIANTS[variant])
        changed = _changed(case, target)
        allowed = [
            o.index for o in ops_ if classify(ops_, base, changed, o.index) != "window"
        ]
        n = chooser.draw(st.sampled_from(allowed), label="operation before which the file changes")
        outcome = classify(ops_, base, changed, n)

        pre_case = case.relocated(root / "pre")  # same bytes as the staged state
        pre = snapshot(pre_case.folder)

        def change(_fs: FaultFs, _op: FsOp) -> None:
            case.write_external(target, external)

        fs = FaultFs(hook_at=n, hook=change)
        ps, exc = case.save(fs)
        assert fs.ops, "the save ran no operation"

        if outcome == "conflict":
            check_conflict(case, ps, exc, target, pre, external)
        elif outcome == "unfinished":
            assert target != "project"
            assert isinstance(exc, ImportSaveUnfinished), exc
            assert exc.files == (case.rel(target),)
            assert case.rel(target) in exc.message
            assert case.path_of(target).read_bytes() == external
            assert case.project_is_new() and case.intent_exists()
            assert ps.import_save_unfinished and not ps.is_dirty
            intent_before = (case.folder / INTENT_NAME).read_bytes()
            message = assert_refuses_unchanged(case, "T2")
            check_refusal_message(case, target, message, "T2")
            assert (case.folder / INTENT_NAME).read_bytes() == intent_before
        else:
            assert exc is None, exc
            assert case.path_of(target).read_bytes() == external
            assert case.artifacts() == []
            for name in TNAMES:
                if name != target:
                    assert case.files()[name] == case.new_files[name]
            if target != "project":
                assert case.project_is_new()
    finally:
        shutil.rmtree(root, ignore_errors=True)


@settings(**_PROPERTY_SETTINGS)
@given(
    variant=st.sampled_from(sorted(VARIANTS)),
    target=st.sampled_from(TARGETS),
    external=_external,
    after=st.booleans(),
    chooser=st.data(),
)
def test_dp_property_27_change_between_crash_and_recovery_is_never_overwritten(
    variant: str, target: str, external: bytes, after: bool, chooser: st.DataObject
) -> None:
    """**Validates: Requirements 20.7, 20.10, 20.11, 20.16, 20.17**

    The save crashes at any operation, the file is changed, the real recovery
    runs. When an intent explains the file the recovery refuses (T1 for the project
    file, T2 for a translation file) and changes no file. Otherwise it leaves the
    file with its external bytes.
    """
    ops_ = variant_ops(variant)
    root = Path(tempfile.mkdtemp(prefix="dp27c_"))
    try:
        case = Case.create(root / "live", **VARIANTS[variant])
        n = chooser.draw(st.integers(min_value=1, max_value=len(ops_)), label="crash point")
        _, exc = case.save(FaultFs(fail_at=n, kind="crash", after=after))
        assert isinstance(exc, SimulatedCrash)
        had_intent = case.intent_exists()
        case.write_external(target, external)

        if had_intent and _changed(case, target):
            message = assert_refuses_unchanged(case, "T1" if target == "project" else "T2")
            check_refusal_message(case, target, message, "T1" if target == "project" else "T2")
            assert case.path_of(target).read_bytes() == external
        else:
            recover_translation_intent(case.project)
            assert case.path_of(target).read_bytes() == external
            assert case.artifacts() == []
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# Save: translation file
# ---------------------------------------------------------------------------


def test_translation_file_changed_between_import_and_save_refuses_save(case: Case) -> None:
    counting = FaultFs()
    ps = case.stage(counting)
    pre = snapshot(case.folder)
    case.write_external("places.json", EXTERNAL)

    exc = Case.save_with(ps)

    check_conflict(case, ps, exc, "places.json", pre, EXTERNAL)
    assert case.files()["persons.json"] == case.old_files["persons.json"]
    assert case.files()["sources.json"] == case.old_files["sources.json"]
    assert mutating(counting) == [], "a refusal must not write anything"
    # The message tells what to do; after the file is restored the same save succeeds.
    assert "Spara igen" in exc.message
    case.restore("places.json")
    ps._commit_fs = None
    ps.save_project()
    assert case.project_is_new() and case.files() == case.new_files
    assert case.artifacts() == []


def test_translation_file_already_new_is_accepted_at_save(case: Case) -> None:
    (case.tdir / "places.json").write_bytes(case.new_files["places.json"])
    ps = case.stage(None)
    ps.save_project()
    assert not ps.is_dirty and ps.pending_translation is None
    assert case.project_is_new() and case.files() == case.new_files
    assert case.artifacts() == []


def test_translation_file_changed_before_commit_point_removes_own_artifacts(
    case: Case, ops: list[FsOp]
) -> None:
    foreign = case.tdir / "places.json.foreign1.new"  # not created by this attempt
    last_write = find(ops, "write", "sources.json").index
    s6 = next(k for k in digest_ops(ops, "places.json") if last_write < k < r_project_index(ops))
    fs = FaultFs(hook_at=s6, hook=lambda _f, _o: case.write_external("places.json", EXTERNAL))
    ps = case.stage(fs)  # opening removes strays, so the foreign file is made afterwards
    foreign.write_bytes(b"not ours")
    pre = snapshot(case.folder)
    pre["translation/places.json"] = EXTERNAL

    exc = Case.save_with(ps)

    assert isinstance(exc, SaveConflict) and exc.files == ("translation/places.json",)
    assert fs.triggered is False  # a hook, not a fault
    assert snapshot(case.folder) == pre
    # No intent and no own temp is left; only the foreign file remains.
    assert [a.replace("\\", "/") for a in case.artifacts()] == [f"translation/{foreign.name}"]
    assert ps.is_dirty and ps.pending_translation is not None and not ps.import_save_unfinished


def test_translation_file_changed_after_commit_point_preserves_intent(
    case: Case, ops: list[FsOp]
) -> None:
    s7 = next(k for k in digest_ops(ops, "places.json") if k > r_project_index(ops))
    fs = FaultFs(hook_at=s7, hook=lambda _f, _o: case.write_external("places.json", EXTERNAL))
    ps, exc = case.save(fs)

    assert isinstance(exc, ImportSaveUnfinished) and exc.files == ("translation/places.json",)
    assert "translation/places.json" in exc.message
    assert case.project_is_new()
    assert case.path_of("places.json").read_bytes() == EXTERNAL
    assert case.files()["persons.json"] == case.new_files["persons.json"]  # replaced before
    assert case.files()["sources.json"] == case.old_files["sources.json"]  # not reached
    assert case.intent_exists()
    intent = (case.folder / INTENT_NAME).read_bytes()
    after_save = snapshot(case.folder)
    assert ps.import_save_unfinished and not ps.is_dirty

    # Neither a further save nor the next open changes a file or the intent.
    with pytest.raises(MergeNotFinishedError):
        ps.save_project()
    assert snapshot(case.folder) == after_save
    assert_refuses_unchanged(case, "T2", expect_in_message=(state_line("translation/places.json", MSG_UNOWNED_STATE),))
    assert (case.folder / INTENT_NAME).read_bytes() == intent
    assert case.path_of("places.json").read_bytes() == EXTERNAL


# ---------------------------------------------------------------------------
# Save: project file
# ---------------------------------------------------------------------------


def test_project_file_changed_between_open_and_save_refuses_save(case: Case) -> None:
    counting = FaultFs()
    ps = case.stage(counting)
    pre = snapshot(case.folder)
    case.write_external("project", EXTERNAL)

    exc = Case.save_with(ps)

    check_conflict(case, ps, exc, "project", pre, EXTERNAL)
    assert case.project.read_bytes() == EXTERNAL
    assert case.files() == case.old_files
    assert mutating(counting) == []
    # Restored, the same save goes through.
    case.restore("project")
    ps._commit_fs = None
    ps.save_project()
    assert case.project_is_new() and case.files() == case.new_files


def test_project_file_changed_before_commit_point_removes_own_artifacts(
    case: Case, ops: list[FsOp]
) -> None:
    last_write = find(ops, "write", "sources.json").index
    s6 = next(k for k in digest_ops(ops, PROJECT_NAME) if last_write < k < r_project_index(ops))
    fs = FaultFs(hook_at=s6, hook=lambda _f, _o: case.write_external("project", EXTERNAL))
    ps = case.stage(fs)
    pre = snapshot(case.folder)

    exc = Case.save_with(ps)

    check_conflict(case, ps, exc, "project", pre, EXTERNAL)
    assert case.artifacts() == []
    assert case.files() == case.old_files


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------

CRASH_POINTS = {
    "intent published, project old": ("replace", INTENT_NAME),
    "project replaced": ("replace", PROJECT_NAME),
    "first translation file replaced": ("replace", "persons.json"),
}


@pytest.mark.parametrize("name", TNAMES)
@pytest.mark.parametrize("point", sorted(CRASH_POINTS))
def test_translation_file_changed_before_recovery_refuses_open(
    case: Case, ops: list[FsOp], point: str, name: str
) -> None:
    kind, base = CRASH_POINTS[point]
    crash_at(case, find(ops, kind, base), after=True)
    assert case.intent_exists()
    case.write_external(name, EXTERNAL)

    message = assert_refuses_unchanged(
        case, "T2", expect_in_message=(state_line(f"translation/{name}", MSG_UNOWNED_STATE),)
    )

    assert case.path_of(name).read_bytes() == EXTERNAL
    # The project file shown in the message is not the conflicting one.
    assert state_line(str(case.project), MSG_UNOWNED_STATE) not in message


@pytest.mark.parametrize("point", sorted(CRASH_POINTS))
def test_project_file_changed_before_recovery_refuses_open(
    case: Case, ops: list[FsOp], point: str
) -> None:
    kind, base = CRASH_POINTS[point]
    crash_at(case, find(ops, kind, base), after=True)
    case.write_external("project", EXTERNAL)

    assert_refuses_unchanged(
        case, "T1", expect_in_message=(state_line(str(case.project), MSG_UNOWNED_STATE),)
    )
    assert case.project.read_bytes() == EXTERNAL


@pytest.mark.parametrize("point", sorted(CRASH_POINTS))
def test_project_file_missing_before_recovery_refuses_open(
    case: Case, ops: list[FsOp], point: str
) -> None:
    kind, base = CRASH_POINTS[point]
    crash_at(case, find(ops, kind, base), after=True)
    case.project.unlink()

    assert_refuses_unchanged(
        case, "T1", expect_in_message=(state_line(str(case.project), "saknas"),)
    )
    assert not case.project.exists()  # the recovery did not recreate it


def _damaged(raw: bytes, how: str) -> bytes:
    if how == "truncated":
        return raw[: len(raw) // 2]
    if how == "empty":
        return b""
    if how == "flipped":
        mid = len(raw) // 2
        return raw[:mid] + bytes([raw[mid] ^ 0x01]) + raw[mid + 1 :]
    return b"\x00\xffnot json at all"


@pytest.mark.parametrize("how", ["truncated", "empty", "flipped", "garbage"])
@pytest.mark.parametrize("point", sorted(CRASH_POINTS))
def test_damaged_intent_refuses_open_and_is_kept_byte_identical(
    case: Case, ops: list[FsOp], point: str, how: str
) -> None:
    kind, base = CRASH_POINTS[point]
    crash_at(case, find(ops, kind, base), after=True)
    intent = case.folder / INTENT_NAME
    damaged = _damaged(intent.read_bytes(), how)
    intent.write_bytes(damaged)

    message = assert_refuses_unchanged(case, "T4")

    assert intent.read_bytes() == damaged
    assert "Importintentionen" in message and "skadad" in message
    assert str(intent) in message


# ---------------------------------------------------------------------------
# Messages, blocked states
# ---------------------------------------------------------------------------


def test_conflict_messages_name_files_and_state_in_swedish(case: Case, ops: list[FsOp]) -> None:
    # Save conflict naming two files.
    conflict = SaveConflict(["P.json.gz", "translation/places.json"])
    for text in (
        "Projektet sparades inte.",
        "har ändrats utanför Släktbusken",
        state_line("P.json.gz", MSG_UNOWNED_STATE).replace("   (", "  ("),
        state_line("translation/places.json", MSG_UNOWNED_STATE).replace("   (", "  ("),
        "Spara igen",
    ):
        assert text in conflict.message, text

    # Unfinished save after the commit point.
    unfinished = ImportSaveUnfinished(["translation/sources.json"])
    for text in ("Projektet är sparat", "translation/sources.json", "ändrats utanför Släktbusken"):
        assert text in unfinished.message, text

    # Refusal at open (T2 translation file, T1 project file, T1 missing, T4 damaged intent).
    crash_at(case, find(ops, "replace", PROJECT_NAME), after=True)
    case.write_external("places.json", EXTERNAL)
    t2 = refusal_of(ProjectService(), case).message
    for text in (
        "Projektet kunde inte öppnas.",
        "En tidigare sparning av en import avbröts",
        "Orsak: En översättningsfil stämmer varken med läget före eller efter sparningen.",
        state_line("translation/places.json", MSG_UNOWNED_STATE),
        state_line("translation/persons.json", "oförändrad"),
        str(case.folder / INTENT_NAME),
        "Alla dessa filer har lämnats orörda.",
        "Ta inte bort dem.",
    ):
        assert text in t2, text

    case.restore("places.json")
    case.write_external("project", EXTERNAL)
    t1 = refusal_of(ProjectService(), case).message
    assert "Orsak: Projektfilen stämmer varken med läget före eller efter sparningen." in t1
    assert state_line(str(case.project), MSG_UNOWNED_STATE) in t1

    case.project.unlink()
    assert state_line(str(case.project), "saknas") in refusal_of(ProjectService(), case).message

    (case.folder / INTENT_NAME).write_bytes(b"{")
    t4 = refusal_of(ProjectService(), case).message
    assert "Orsak: Importintentionen är skadad eller har ett okänt format." in t4


def test_conflict_refusal_blocks_normal_save(case: Case, ops: list[FsOp]) -> None:
    ps = crash_at(case, find(ops, "replace", PROJECT_NAME), after=True)
    case.write_external("places.json", EXTERNAL)
    ps._commit_fs = None
    with pytest.raises(RecoveryRefusedError):
        ps.open_project(case.project)  # the refusal is remembered for this path
    assert ps.is_merge_journal_pending()

    counting = FaultFs()
    ps._commit_fs = counting
    before = snapshot(case.folder)
    for _ in range(2):
        with pytest.raises(MergeNotFinishedError) as blocked:
            ps.save_project()
        assert str(blocked.value) == MERGE_UNFINISHED_MESSAGE
    assert snapshot(case.folder) == before
    assert mutating(counting) == []
    assert case.path_of("places.json").read_bytes() == EXTERNAL


@pytest.mark.parametrize("what", ["translation", "project", "missing", "damaged"])
def test_conflict_refusal_changes_no_file(case: Case, ops: list[FsOp], what: str) -> None:
    crash_at(case, find(ops, "replace", "persons.json"), after=True)  # project new, one file new
    if what == "translation":
        case.write_external("sources.json", EXTERNAL)
        code = "T2"
    elif what == "project":
        case.write_external("project", EXTERNAL)
        code = "T1"
    elif what == "missing":
        case.project.unlink()
        code = "T1"
    else:
        (case.folder / INTENT_NAME).write_bytes(b"damaged")
        code = "T4"
    temps_before = case.artifacts()
    assert any(a.endswith(".new") for a in temps_before)  # a leftover temp must survive too

    assert_refuses_unchanged(case, code)

    assert case.artifacts() == temps_before
    # In particular no translation file other than the conflicting one was written.
    for name in TNAMES:
        expected = EXTERNAL if (what == "translation" and name == "sources.json") else None
        if expected is not None:
            assert case.files()[name] == expected
        elif name == "persons.json":
            assert case.files()[name] == case.new_files[name]  # written by the crashed save
        else:
            assert case.files()[name] == case.old_files[name]


def test_unfinished_import_save_blocks_save_import_and_translation_editors(
    case: Case, ops: list[FsOp], tmp_path: Path
) -> None:
    s7 = next(k for k in digest_ops(ops, "places.json") if k > r_project_index(ops))
    fs = FaultFs(hook_at=s7, hook=lambda _f, _o: case.write_external("places.json", EXTERNAL))
    ps, exc = case.save(fs)
    assert isinstance(exc, ImportSaveUnfinished) and ps.import_save_unfinished
    before = snapshot(case.folder)

    # Save
    with pytest.raises(MergeNotFinishedError) as blocked:
        ps.save_project()
    assert str(blocked.value) == MSG_IMPORT_SAVE_UNFINISHED

    # Import (refused before the GEDCOM file is looked at)
    ged = tmp_path / "x.ged"
    ged.write_text("0 HEAD\n0 TRLR\n", encoding="utf-8")
    with pytest.raises(ImportServiceError) as refused_import:
        ImportService(ValidationService()).run(ps.data, ged, case.folder, ps)
    assert MSG_IMPORT_SAVE_UNFINISHED in str(refused_import.value)

    # Translation editors
    assert translation_edit_refusal(ps) == MSG_IMPORT_SAVE_UNFINISHED
    assert "Starta om Släktbusken" in MSG_IMPORT_SAVE_UNFINISHED

    assert snapshot(case.folder) == before
    assert case.path_of("places.json").read_bytes() == EXTERNAL
