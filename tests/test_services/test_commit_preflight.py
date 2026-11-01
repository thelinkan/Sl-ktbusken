"""Pre-flight tests of the merge commit (task 13.21, Requirement 27.20).

Each refusal must name the file, change nothing in memory or on disk and leave
the project in a state where the wizard can simply be retried (the wizard stays
open; the engine reports a failed outcome and has adopted nothing).

Only the test that needs Windows file-sharing semantics is platform-conditional;
it carries ``windows_only`` and the single permitted ``skipif`` condition.
"""

from __future__ import annotations

import functools
import os
import stat
import sys
from pathlib import Path

import pytest

from slaktbusken.model.person import Name, Person
from slaktbusken.persistence import translation_io
from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.services.commit.preflight import DiskUsage, Preflight
from slaktbusken.services.commit.transaction import CommitRefused, MergeTransaction
from slaktbusken.services.merge_engine import MergeEngine
from slaktbusken.services.merge_planner import MergeDecisions, build_plan
from slaktbusken.services.project_service import ProjectService
from tests.helpers.fault_fs import CountingFs, FaultFs, snapshot_dir

SURVIVOR, RETIRED = "person_1", "person_2"


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _person(pid: str) -> Person:
    return Person(id=pid, sex="F", names=[Name("birth", "Anna", "Berg")])


def _open_project(root: Path) -> ProjectService:
    svc = ProjectService()
    svc.create_project("Test", root)
    svc.data.persons.extend([_person(SURVIVOR), _person(RETIRED)])
    (svc.project_path.parent / "translation" / "persons.json").unlink(missing_ok=True)
    svc._dirty = True
    svc.save_project()
    reopened = ProjectService()
    reopened.open_project(svc.project_path)
    return reopened


def _plan(svc: ProjectService):
    translation = translation_io.read_all(svc.project_path.parent / "translation")
    decisions = MergeDecisions(SURVIVOR, RETIRED, survivor_id=SURVIVOR, survivor_confirmed=True)
    plan = build_plan(svc.data, translation, decisions, svc.content_revision)
    assert plan.can_execute, [c.message for c in plan.blocking]
    return plan


def _state(svc: ProjectService) -> tuple:
    return (
        FilePersistence.encode(svc.data),
        svc.revision,
        svc.content_revision,
        svc.is_saved_state(),
    )


def _assert_refused_unchanged(svc: ProjectService, outcome, before_state, before_disk, *names: str):
    assert outcome.success is False
    assert outcome.step == "pre-flight"
    for name in names:
        assert name in outcome.message, outcome.message
    assert _state(svc) == before_state, "memory changed"
    assert snapshot_dir(svc.project_path.parent) == before_disk, "disk changed"
    # The wizard stays open: nothing is adopted and the project is still in a
    # saved state, so the same plan can be executed again after the cause is fixed.
    assert svc.is_saved_state()


@pytest.fixture
def svc(tmp_path: Path) -> ProjectService:
    return _open_project(tmp_path / "proj")


# ---------------------------------------------------------------------------
# Read-only target
# ---------------------------------------------------------------------------


def test_read_only_target_refused(svc: ProjectService) -> None:
    project = svc.project_path
    plan = _plan(svc)
    os.chmod(project, stat.S_IREAD)
    try:
        before_state, before_disk = _state(svc), snapshot_dir(project.parent)
        outcome = MergeEngine(svc).execute(plan)
        _assert_refused_unchanged(svc, outcome, before_state, before_disk, project.name, "skrivskyddad")
    finally:
        os.chmod(project, stat.S_IWRITE | stat.S_IREAD)
    # After the cause is removed the same plan executes.
    assert MergeEngine(svc).execute(plan).success


# ---------------------------------------------------------------------------
# Second handle without write sharing (Windows only)
# ---------------------------------------------------------------------------


def _open_without_write_sharing(path: Path):
    """Open ``path`` with GENERIC_READ and FILE_SHARE_READ only (Windows)."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    generic_read, share_read, open_existing = 0x80000000, 0x1, 3
    handle = kernel32.CreateFileW(str(path), generic_read, share_read, None, open_existing, 0x80, None)
    if handle in (None, wintypes.HANDLE(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    return kernel32, handle


@pytest.mark.windows_only
@pytest.mark.skipif(sys.platform != "win32", reason="Kräver Windows")
def test_second_handle_without_write_sharing_refused(svc: ProjectService) -> None:
    project = svc.project_path
    plan = _plan(svc)
    kernel32, handle = _open_without_write_sharing(project)
    try:
        before_state, before_disk = _state(svc), snapshot_dir(project.parent)
        outcome = MergeEngine(svc).execute(plan)
        _assert_refused_unchanged(svc, outcome, before_state, before_disk, project.name)
    finally:
        kernel32.CloseHandle(handle)
    assert MergeEngine(svc).execute(plan).success


# ---------------------------------------------------------------------------
# Directory without create permission (FaultFs)
# ---------------------------------------------------------------------------


def _first_create_exclusive_index(svc: ProjectService, plan) -> int:
    """Operation number of the lock creation, found with a dry run on a copy."""
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        copy_root = Path(tmp) / "copy"
        shutil.copytree(svc.project_path.parent, copy_root)
        copy = ProjectService()
        copy.open_project(copy_root / svc.project_path.name)
        counting = CountingFs()
        assert MergeEngine(copy, fs=counting).execute(_plan(copy)).success
        return next(op.index for op in counting.ops if op.name == "create_exclusive")


def test_directory_without_create_permission_refused(svc: ProjectService) -> None:
    plan = _plan(svc)
    n = _first_create_exclusive_index(svc, plan)
    fault = FaultFs(n, "io_error_before")
    before_state, before_disk = _state(svc), snapshot_dir(svc.project_path.parent)
    outcome = MergeEngine(svc, fs=fault).execute(plan)
    assert fault.triggered
    _assert_refused_unchanged(svc, outcome, before_state, before_disk, "Låsfilen", ".merge.lock")


def test_unwritable_directory_probe_names_directory(tmp_path: Path) -> None:
    missing = tmp_path / "saknas"
    refusals = Preflight.check([], missing, 0, disk_usage=lambda _p: DiskUsage(10**12, 0, 10**12))
    assert any("saknas" in r and "temporära filer" in r for r in refusals), refusals
    assert not missing.exists()


# ---------------------------------------------------------------------------
# Insufficient space (disk_usage stub)
# ---------------------------------------------------------------------------


def test_insufficient_space_refused(svc: ProjectService) -> None:
    project = svc.project_path
    stub = functools.partial(Preflight.check, disk_usage=lambda _p: DiskUsage(10**9, 10**9 - 10, 10))
    transaction = MergeTransaction(project, preflight=stub)
    before_disk = snapshot_dir(project.parent)
    before_state = _state(svc)
    with pytest.raises(CommitRefused) as excinfo:
        transaction.commit(project.read_bytes(), None, revision_before=svc.revision)
    message = "\n".join(excinfo.value.messages)
    assert project.name in message
    assert "diskutrymme" in message
    assert snapshot_dir(project.parent) == before_disk, "disk changed"
    assert _state(svc) == before_state, "memory changed"


# ---------------------------------------------------------------------------
# Lock / journal left behind
# ---------------------------------------------------------------------------


def test_existing_lock_file_refused_and_preserved(svc: ProjectService) -> None:
    project = svc.project_path
    lock = project.with_name(project.name + ".merge.lock")
    lock.write_bytes(b"")
    before_disk = snapshot_dir(project.parent)
    before_state = _state(svc)
    outcome = MergeEngine(svc).execute(_plan(svc))
    _assert_refused_unchanged(svc, outcome, before_state, before_disk, lock.name)
