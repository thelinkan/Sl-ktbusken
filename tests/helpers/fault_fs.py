"""Fault-injection filesystem wrappers for the merge commit protocol tests.

Implements design 13.9. All wrappers implement the ``CommitFs`` protocol from
``slaktbusken.services.commit.fs_ops`` and wrap another ``CommitFs`` (a
``RealFs`` without retry sleeps by default).

* ``CountingFs``  records every operation in order (1-based numbering).
* ``FaultFs``     raises at operation ``n`` (crash before/after, I/O error
                  before/after, partial write, persistent permission error).
* ``PowerLossFs`` tracks un-synced data and, on a crash, rewrites the disk to a
                  possible post-crash state (seeded, reproducible).
* ``MemoryFs``    in-memory ``CommitFs`` for table-driven classifier tests.

Helpers: ``snapshot_dir`` / ``diff_snapshots`` / ``assert_snapshots_equal`` for
byte-for-byte directory comparison (refusal tests).

``SimulatedCrash`` derives from ``BaseException`` so ordinary ``except
Exception`` handlers in the code under test cannot swallow it. ``CrashError`` is
an alias.
"""

from __future__ import annotations

import os
import random
import stat as _stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from slaktbusken.services.commit.fs_ops import CommitFs, RealFs

__all__ = [
    "SimulatedCrash",
    "CrashError",
    "FAULT_KINDS",
    "OP_NAMES",
    "FsOp",
    "CountingFs",
    "FaultFs",
    "PowerLossFs",
    "MemoryFs",
    "snapshot_dir",
    "diff_snapshots",
    "assert_snapshots_equal",
]


class SimulatedCrash(BaseException):
    """Raised to model a process crash at an operation boundary."""


CrashError = SimulatedCrash

OP_NAMES: tuple[str, ...] = (
    "exists",
    "read_bytes",
    "write_file_durable",
    "copy_file_durable",
    "replace",
    "remove",
    "rmtree",
    "fsync_dir",
    "stat",
    "listdir",
    "create_exclusive",
)
_WRITE_OPS = ("write_file_durable", "copy_file_durable")

FAULT_KINDS: tuple[str, ...] = (
    "crash_before",
    "crash_after",
    "io_error_before",
    "io_error_after",
    "permission_error_persistent",
    "partial_write",
)


@dataclass(frozen=True)
class FsOp:
    """One recorded operation. ``index`` is 1-based."""

    index: int
    name: str
    args: tuple[Any, ...]

    def __str__(self) -> str:  # readable in assertion messages
        return f"#{self.index} {self.name}({', '.join(str(a) for a in self.args)})"


def _no_sleep(_: float) -> None:
    return None


class _FsWrapper:
    """Delegating base. Subclasses override ``_pre`` / ``_post``."""

    def __init__(self, inner: CommitFs | None = None) -> None:
        self.inner: CommitFs = inner if inner is not None else RealFs(delays=(), sleep=_no_sleep)
        self.ops: list[FsOp] = []

    # -- hooks ---------------------------------------------------------
    def _pre(self, op: FsOp) -> None:
        pass

    def _post(self, op: FsOp, result: Any) -> None:
        pass

    def _invoke(self, name: str, *args: Any) -> Any:
        op = FsOp(len(self.ops) + 1, name, args)
        self.ops.append(op)
        self._pre(op)
        result = getattr(self.inner, name)(*args)
        self._post(op, result)
        return result

    @property
    def op_count(self) -> int:
        return len(self.ops)

    # -- CommitFs ------------------------------------------------------
    def exists(self, path: Path) -> bool:
        return self._invoke("exists", path)

    def read_bytes(self, path: Path) -> bytes:
        return self._invoke("read_bytes", path)

    def write_file_durable(self, path: Path, data: bytes) -> None:
        return self._invoke("write_file_durable", path, data)

    def copy_file_durable(self, src: Path, dst: Path) -> None:
        return self._invoke("copy_file_durable", src, dst)

    def replace(self, src: Path, dst: Path) -> None:
        return self._invoke("replace", src, dst)

    def remove(self, path: Path) -> None:
        return self._invoke("remove", path)

    def rmtree(self, path: Path) -> None:
        return self._invoke("rmtree", path)

    def fsync_dir(self, path: Path) -> None:
        return self._invoke("fsync_dir", path)

    def stat(self, path: Path) -> os.stat_result:
        return self._invoke("stat", path)

    def listdir(self, path: Path) -> list[str]:
        return self._invoke("listdir", path)

    def create_exclusive(self, path: Path) -> None:
        return self._invoke("create_exclusive", path)


class CountingFs(_FsWrapper):
    """Records every operation; a dry run yields the numbered list of N ops."""

    def names(self) -> list[str]:
        return [op.name for op in self.ops]


class FaultFs(_FsWrapper):
    """Inject a fault at operation ``n`` (1-based).

    Kinds:
      crash_before / crash_after   raise ``SimulatedCrash`` before / after op n.
      io_error_before / _after     raise ``OSError`` before / after op n.
      permission_error_persistent  every ``replace`` from op n on raises
                                   ``PermissionError`` (op itself not executed).
      partial_write                at a write op n, write half the bytes
                                   (not fsynced) then crash; at any other op
                                   behaves as ``crash_before`` (nothing to tear).

    ``triggered`` tells whether the fault fired (False when n > N).
    """

    def __init__(self, n: int, kind: str, inner: CommitFs | None = None) -> None:
        if kind not in FAULT_KINDS:
            raise ValueError(f"unknown fault kind: {kind!r}")
        if n < 1:
            raise ValueError("n is 1-based")
        super().__init__(inner)
        self.n = n
        self.kind = kind
        self.triggered = False

    def _pre(self, op: FsOp) -> None:
        k = self.kind
        if k == "permission_error_persistent":
            if op.name == "replace" and op.index >= self.n:
                self.triggered = True
                raise PermissionError(13, "simulated persistent permission error", str(op.args[1]))
            return
        if op.index != self.n:
            return
        if k == "crash_before":
            self.triggered = True
            raise SimulatedCrash(str(op))
        if k == "io_error_before":
            self.triggered = True
            raise OSError(5, f"simulated I/O error before {op}")
        if k == "partial_write":
            self.triggered = True
            if op.name == "write_file_durable":
                path, data = op.args
                _write_plain(path, data[: len(data) // 2])
            elif op.name == "copy_file_durable":
                src, dst = op.args
                data = self.inner.read_bytes(src)
                _write_plain(dst, data[: len(data) // 2])
            raise SimulatedCrash(f"partial write at {op}")

    def _post(self, op: FsOp, result: Any) -> None:
        if op.index != self.n:
            return
        if self.kind == "crash_after":
            self.triggered = True
            raise SimulatedCrash(f"after {op}")
        if self.kind == "io_error_after":
            self.triggered = True
            raise OSError(5, f"simulated I/O error after {op}")


def _write_plain(path: Path, data: bytes) -> None:
    """Write without fsync; used to leave torn files on disk."""
    with open(path, "wb") as fh:
        fh.write(data)


@dataclass
class _PendingRename:
    src: Path
    dst: Path
    prev: bytes | None  # previous content of dst (None: absent)
    content: bytes


@dataclass
class _UnsyncedWrite:
    path: Path
    data: bytes


class PowerLossFs(_FsWrapper):
    """Models un-synced data on top of a real directory.

    The wrapped fs always holds the volatile (latest) view. The wrapper tracks:
      * renames not yet followed by ``fsync_dir`` of the destination directory
        (only when ``replace_is_durable=False``; ``RealFs.replace`` is
        write-through, hence the default True),
      * writes interrupted before their fsync (``crash_phase="mid"`` at a
        write op).
    ``materialise()`` rewrites the disk to one possible post-crash state: each
    pending rename is reverted with probability 1/2 (when ``revert_renames``),
    and each un-synced write is truncated to a random prefix (possibly empty).
    Choices come from ``random.Random(seed)`` so failures are reproducible.

    ``crash_at`` (1-based) with ``crash_phase`` in before / mid / after raises
    ``SimulatedCrash`` at that op and materialises automatically. Without
    ``crash_at`` call ``materialise()`` yourself after catching a crash raised
    elsewhere (e.g. by an outer ``FaultFs``).
    """

    def __init__(
        self,
        inner: CommitFs | None = None,
        *,
        seed: int = 0,
        crash_at: int | None = None,
        crash_phase: str = "before",
        revert_renames: bool = True,
        replace_is_durable: bool = True,
    ) -> None:
        if crash_phase not in ("before", "mid", "after"):
            raise ValueError(f"unknown crash phase: {crash_phase!r}")
        super().__init__(inner)
        self.seed = seed
        self.rng = random.Random(seed)
        self.crash_at = crash_at
        self.crash_phase = crash_phase
        self.revert_renames = revert_renames
        self.replace_is_durable = replace_is_durable
        self.pending_renames: list[_PendingRename] = []
        self.unsynced_writes: list[_UnsyncedWrite] = []
        self.materialised = False
        self.log: list[str] = []
        self._last_replace: tuple[bytes | None, bytes] = (None, b"")

    def _pre(self, op: FsOp) -> None:
        if op.name == "replace" and not self.replace_is_durable:
            src, dst = op.args
            prev = self.inner.read_bytes(dst) if self.inner.exists(dst) else None
            self._last_replace = (prev, self.inner.read_bytes(src) if self.inner.exists(src) else b"")
        if op.index != self.crash_at:
            return
        if self.crash_phase == "before":
            self._crash(op, "before")
        elif self.crash_phase == "mid" and op.name in _WRITE_OPS:
            if op.name == "write_file_durable":
                path, data = op.args
            else:
                src, path = op.args
                data = self.inner.read_bytes(src)
            _write_plain(path, data)
            self.unsynced_writes.append(_UnsyncedWrite(Path(path), data))
            self._crash(op, "mid")
        elif self.crash_phase == "mid":
            self._crash(op, "mid")  # no tearable data: same as before

    def _post(self, op: FsOp, result: Any) -> None:
        if op.name == "replace" and not self.replace_is_durable:
            src, dst = op.args
            prev, content = self._last_replace
            self.pending_renames.append(_PendingRename(Path(src), Path(dst), prev, content))
        elif op.name == "fsync_dir":
            d = Path(op.args[0])
            self.pending_renames = [r for r in self.pending_renames if Path(r.dst).parent != d]
        elif op.name in _WRITE_OPS:
            # completed durable writes are synced; drop stale unsynced entries
            target = Path(op.args[-1] if op.name == "copy_file_durable" else op.args[0])
            self.unsynced_writes = [w for w in self.unsynced_writes if w.path != target]
        if op.index == self.crash_at and self.crash_phase == "after":
            self._crash(op, "after")

    def _crash(self, op: FsOp, phase: str) -> None:
        self.materialise()
        raise SimulatedCrash(f"power loss {phase} {op}")

    def materialise(self) -> None:
        """Rewrite the disk to a possible post-crash state. Idempotent."""
        if self.materialised:
            return
        self.materialised = True
        for r in reversed(self.pending_renames):
            if self.revert_renames and self.rng.random() < 0.5:
                self.log.append(f"revert rename {r.src} -> {r.dst}")
                if r.prev is None:
                    self.inner.remove(r.dst)
                else:
                    self.inner.write_file_durable(r.dst, r.prev)
                self.inner.write_file_durable(r.src, r.content)
            else:
                self.log.append(f"keep rename {r.src} -> {r.dst}")
        for w in self.unsynced_writes:
            if not self.inner.exists(w.path):
                continue
            cut = self.rng.randint(0, len(w.data))
            self.log.append(f"truncate {w.path} to {cut}/{len(w.data)}")
            self.inner.write_file_durable(w.path, w.data[:cut])
        self.pending_renames = []
        self.unsynced_writes = []


# ---------------------------------------------------------------------------
# In-memory CommitFs
# ---------------------------------------------------------------------------


class MemoryFs:
    """In-memory ``CommitFs``; no disk access. Paths are compared as ``Path``."""

    def __init__(self, files: dict[Path | str, bytes] | None = None) -> None:
        self.files: dict[Path, bytes] = {}
        self.dirs: set[Path] = {Path(".")}
        self.synced_dirs: list[Path] = []
        for p, data in (files or {}).items():
            self.add_file(p, data)

    def add_file(self, path: Path | str, data: bytes) -> None:
        p = Path(path)
        self.mkdir(p.parent)
        self.files[p] = data

    def mkdir(self, path: Path | str) -> None:
        p = Path(path)
        while True:
            self.dirs.add(p)
            if p.parent == p:
                break
            p = p.parent

    def _need_parent(self, p: Path) -> None:
        if p.parent not in self.dirs:
            raise FileNotFoundError(2, "No such directory", str(p.parent))

    def exists(self, path: Path) -> bool:
        p = Path(path)
        return p in self.files or p in self.dirs

    def read_bytes(self, path: Path) -> bytes:
        try:
            return self.files[Path(path)]
        except KeyError:
            raise FileNotFoundError(2, "No such file", str(path)) from None

    def write_file_durable(self, path: Path, data: bytes) -> None:
        p = Path(path)
        self._need_parent(p)
        if p in self.dirs:
            raise IsADirectoryError(21, "Is a directory", str(p))
        self.files[p] = bytes(data)

    def copy_file_durable(self, src: Path, dst: Path) -> None:
        self.write_file_durable(dst, self.read_bytes(src))

    def replace(self, src: Path, dst: Path) -> None:
        s, d = Path(src), Path(dst)
        data = self.read_bytes(s)
        self._need_parent(d)
        del self.files[s]
        self.files[d] = data

    def remove(self, path: Path) -> None:
        self.files.pop(Path(path), None)

    def rmtree(self, path: Path) -> None:
        p = Path(path)
        if p not in self.dirs:
            return
        self.files = {f: d for f, d in self.files.items() if p not in f.parents}
        self.dirs = {d for d in self.dirs if d != p and p not in d.parents}

    def fsync_dir(self, path: Path) -> None:
        if Path(path) not in self.dirs:
            raise FileNotFoundError(2, "No such directory", str(path))
        self.synced_dirs.append(Path(path))

    def stat(self, path: Path) -> os.stat_result:
        p = Path(path)
        if p in self.files:
            mode, size = _stat.S_IFREG | 0o644, len(self.files[p])
        elif p in self.dirs:
            mode, size = _stat.S_IFDIR | 0o755, 0
        else:
            raise FileNotFoundError(2, "No such file", str(path))
        return os.stat_result((mode, 0, 0, 1, 0, 0, size, 0, 0, 0))

    def listdir(self, path: Path) -> list[str]:
        p = Path(path)
        if p not in self.dirs:
            raise FileNotFoundError(2, "No such directory", str(path))
        names = {c.name for c in list(self.files) + list(self.dirs) if c.parent == p and c != p}
        return sorted(names)

    def create_exclusive(self, path: Path) -> None:
        p = Path(path)
        self._need_parent(p)
        if self.exists(p):
            raise FileExistsError(17, "File exists", str(p))
        self.files[p] = b""


# ---------------------------------------------------------------------------
# Directory snapshots
# ---------------------------------------------------------------------------


def snapshot_dir(root: Path | str) -> dict[str, bytes | None]:
    """Byte-for-byte snapshot: relative posix path -> content (None for dirs)."""
    base = Path(root)
    snap: dict[str, bytes | None] = {}
    for dirpath, dirnames, filenames in os.walk(base):
        dp = Path(dirpath)
        for name in dirnames:
            snap[(dp / name).relative_to(base).as_posix()] = None
        for name in filenames:
            snap[(dp / name).relative_to(base).as_posix()] = (dp / name).read_bytes()
    return snap


def diff_snapshots(before: dict[str, bytes | None], after: dict[str, bytes | None]) -> list[str]:
    """Human-readable differences; empty list when identical."""
    out: list[str] = []
    for key in sorted(set(before) | set(after)):
        if key not in after:
            out.append(f"removed: {key}")
        elif key not in before:
            out.append(f"added: {key}")
        elif before[key] != after[key]:
            out.append(f"changed: {key}")
    return out


def assert_snapshots_equal(before: dict[str, bytes | None], after: dict[str, bytes | None]) -> None:
    diffs = diff_snapshots(before, after)
    assert not diffs, "directory differs: " + "; ".join(diffs)
