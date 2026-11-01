"""Self-tests for the fault-injection filesystem wrappers (task 13.16)."""

from __future__ import annotations

from pathlib import Path

import pytest

from slaktbusken.services.commit.fs_ops import CommitFs
from tests.helpers.fault_fs import (
    FAULT_KINDS,
    CountingFs,
    CrashError,
    FaultFs,
    MemoryFs,
    PowerLossFs,
    SimulatedCrash,
    assert_snapshots_equal,
    diff_snapshots,
    snapshot_dir,
)


def _workload(fs: CommitFs, d: Path) -> None:
    """A small commit-like sequence: write, copy, replace, remove."""
    fs.write_file_durable(d / "a.tmp", b"AAAA-new")
    fs.copy_file_durable(d / "b.txt", d / "b.bak")
    fs.replace(d / "a.tmp", d / "a.txt")
    fs.fsync_dir(d)
    fs.remove(d / "b.bak")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "a.txt").write_bytes(b"AAAA-old")
    (tmp_path / "b.txt").write_bytes(b"BBBB")
    return tmp_path


def test_wrappers_implement_protocol(tmp_path: Path) -> None:
    for fs in (CountingFs(), FaultFs(1, "crash_before"), PowerLossFs(), MemoryFs()):
        assert isinstance(fs, CommitFs)


def test_crash_error_is_base_exception_alias() -> None:
    assert CrashError is SimulatedCrash
    assert not issubclass(SimulatedCrash, Exception)


def test_counting_fs_numbers_operations(project: Path) -> None:
    fs = CountingFs()
    _workload(fs, project)
    assert fs.names() == ["write_file_durable", "copy_file_durable", "replace", "fsync_dir", "remove"]
    assert [op.index for op in fs.ops] == [1, 2, 3, 4, 5]
    assert fs.op_count == 5
    assert (project / "a.txt").read_bytes() == b"AAAA-new"


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_crash_before_leaves_op_undone(project: Path, n: int) -> None:
    fs = FaultFs(n, "crash_before")
    with pytest.raises(SimulatedCrash):
        _workload(fs, project)
    assert fs.triggered
    assert fs.op_count == n  # nothing after the crash ran
    if n == 3:  # replace not executed
        assert (project / "a.txt").read_bytes() == b"AAAA-old"


def test_crash_after_executes_the_operation(project: Path) -> None:
    fs = FaultFs(3, "crash_after")
    with pytest.raises(SimulatedCrash):
        _workload(fs, project)
    assert (project / "a.txt").read_bytes() == b"AAAA-new"
    assert (project / "b.bak").exists()


def test_io_error_before_and_after(project: Path) -> None:
    fs = FaultFs(1, "io_error_before")
    with pytest.raises(OSError):
        _workload(fs, project)
    assert not (project / "a.tmp").exists()

    fs = FaultFs(1, "io_error_after")
    with pytest.raises(OSError):
        _workload(fs, project)
    assert (project / "a.tmp").read_bytes() == b"AAAA-new"


def test_partial_write_tears_file_then_crashes(project: Path) -> None:
    fs = FaultFs(1, "partial_write")
    with pytest.raises(SimulatedCrash):
        _workload(fs, project)
    assert (project / "a.tmp").read_bytes() == b"AAAA"  # half of 8 bytes


def test_partial_write_on_non_write_op_is_crash_before(project: Path) -> None:
    fs = FaultFs(3, "partial_write")
    with pytest.raises(SimulatedCrash):
        _workload(fs, project)
    assert (project / "a.txt").read_bytes() == b"AAAA-old"


def test_persistent_permission_error_fails_every_replace(project: Path) -> None:
    fs = FaultFs(1, "permission_error_persistent")
    for _ in range(3):
        with pytest.raises(PermissionError):
            fs.replace(project / "b.txt", project / "c.txt")
    assert (project / "b.txt").exists() and not (project / "c.txt").exists()
    assert fs.exists(project / "b.txt")  # other operations still work


def test_fault_beyond_last_operation_never_triggers(project: Path) -> None:
    fs = FaultFs(99, "crash_before")
    _workload(fs, project)
    assert not fs.triggered


def test_all_kinds_are_constructible_and_unknown_rejected() -> None:
    for kind in FAULT_KINDS:
        FaultFs(1, kind)
    with pytest.raises(ValueError):
        FaultFs(1, "nope")
    with pytest.raises(ValueError):
        FaultFs(0, "crash_before")


def test_power_loss_mid_write_truncates_to_prefix_reproducibly(project: Path) -> None:
    results = []
    for _ in range(2):
        (project / "a.tmp").unlink(missing_ok=True)
        fs = PowerLossFs(seed=7, crash_at=1, crash_phase="mid")
        with pytest.raises(SimulatedCrash):
            _workload(fs, project)
        data = (project / "a.tmp").read_bytes()
        assert b"AAAA-new".startswith(data)
        results.append(data)
    assert results[0] == results[1]
    seen = set()
    for seed in range(40):
        fs = PowerLossFs(seed=seed, crash_at=1, crash_phase="mid")
        with pytest.raises(SimulatedCrash):
            fs.write_file_durable(project / "t.tmp", b"0123456789")
        seen.add(len((project / "t.tmp").read_bytes()))
    assert len(seen) > 3


def test_power_loss_reverts_unflushed_rename(project: Path) -> None:
    reverted = kept = 0
    for seed in range(20):
        (project / "a.txt").write_bytes(b"AAAA-old")
        (project / "a.tmp").write_bytes(b"AAAA-new")
        fs = PowerLossFs(seed=seed, replace_is_durable=False)
        fs.replace(project / "a.tmp", project / "a.txt")  # no fsync_dir
        fs.materialise()
        if (project / "a.txt").read_bytes() == b"AAAA-old":
            reverted += 1
            assert (project / "a.tmp").read_bytes() == b"AAAA-new"
        else:
            kept += 1
            assert not (project / "a.tmp").exists()
    assert reverted and kept


def test_power_loss_fsync_dir_makes_rename_durable(project: Path) -> None:
    for seed in range(10):
        (project / "a.txt").write_bytes(b"AAAA-old")
        (project / "a.tmp").write_bytes(b"AAAA-new")
        fs = PowerLossFs(seed=seed, replace_is_durable=False)
        fs.replace(project / "a.tmp", project / "a.txt")
        fs.fsync_dir(project)
        fs.materialise()
        assert (project / "a.txt").read_bytes() == b"AAAA-new"


def test_power_loss_after_phase_crashes_with_op_done(project: Path) -> None:
    fs = PowerLossFs(crash_at=3, crash_phase="after")
    with pytest.raises(SimulatedCrash):
        _workload(fs, project)
    assert (project / "a.txt").read_bytes() == b"AAAA-new"
    assert fs.materialised


def test_memory_fs_behaves_like_a_filesystem() -> None:
    d = Path("proj")
    fs = MemoryFs({d / "a.txt": b"old"})
    assert fs.exists(d / "a.txt") and fs.stat(d / "a.txt").st_size == 3
    fs.write_file_durable(d / "a.tmp", b"new!")
    fs.copy_file_durable(d / "a.txt", d / "a.bak")
    fs.replace(d / "a.tmp", d / "a.txt")
    fs.fsync_dir(d)
    assert fs.read_bytes(d / "a.txt") == b"new!"
    assert fs.listdir(d) == ["a.bak", "a.txt"]
    with pytest.raises(FileExistsError):
        fs.create_exclusive(d / "a.txt")
    fs.create_exclusive(d / "lock")
    fs.remove(d / "a.bak")
    fs.remove(d / "missing")  # tolerated like RealFs
    with pytest.raises(FileNotFoundError):
        fs.read_bytes(d / "a.bak")
    fs.rmtree(d)
    assert not fs.exists(d / "a.txt") and not fs.exists(d)


def test_memory_fs_works_under_fault_wrapper() -> None:
    fs = FaultFs(2, "crash_before", inner=MemoryFs({Path("p/a"): b"x"}))
    fs.exists(Path("p/a"))
    with pytest.raises(SimulatedCrash):
        fs.read_bytes(Path("p/a"))


def test_snapshot_detects_any_byte_difference(project: Path) -> None:
    (project / "sub").mkdir()
    (project / "sub" / "c.txt").write_bytes(b"cc")
    before = snapshot_dir(project)
    assert before["sub"] is None and before["sub/c.txt"] == b"cc"
    assert_snapshots_equal(before, snapshot_dir(project))

    (project / "sub" / "c.txt").write_bytes(b"cd")
    (project / "new").write_bytes(b"")
    (project / "b.txt").unlink()
    assert diff_snapshots(before, snapshot_dir(project)) == [
        "removed: b.txt",
        "added: new",
        "changed: sub/c.txt",
    ]
    with pytest.raises(AssertionError):
        assert_snapshots_equal(before, snapshot_dir(project))
