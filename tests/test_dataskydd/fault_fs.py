"""Fault-injecting ``CommitFs`` for the save-protocol and recovery tests.

``FaultFs`` wraps a real ``CommitFs`` (``RealFs`` without retry sleeps by
default), numbers every operation from 1 and can:

* fail at operation ``fail_at`` with an ``OSError`` (``kind="exception"``) or a
  ``SimulatedCrash`` (``kind="crash"``), before the operation runs (default) or
  after it ran (``after=True``);
* tear a write: with ``kind="torn"`` a write at ``fail_at`` leaves half of the
  bytes on disk and then crashes (any other operation behaves as a crash before it);
* run ``hook(fs, op)`` before operation ``hook_at`` (or before the first
  operation for which ``hook_when(op)`` is true), so a test can change a file at
  an exact point of the protocol.

``SimulatedCrash`` derives from ``BaseException`` so the ``except Exception``
handlers of the code under test cannot swallow it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from slaktbusken.services.commit.fs_ops import CommitFs, RealFs

__all__ = ["FaultFs", "FsOp", "SimulatedCrash", "FAULT_KINDS"]

FAULT_KINDS: tuple[str, ...] = ("exception", "crash", "torn")


class SimulatedCrash(BaseException):
    """Models a process crash at an operation boundary."""


@dataclass(frozen=True)
class FsOp:
    """One operation. ``index`` is 1-based."""

    index: int
    name: str
    args: tuple[Any, ...]

    @property
    def path(self) -> Path:
        """The (first) path argument; for ``replace`` the source."""
        return self.args[0]

    @property
    def target(self) -> Path:
        """The path that is written or replaced (destination of ``replace``)."""
        return self.args[1] if self.name in ("replace", "copy_file_durable") else self.args[0]

    def __str__(self) -> str:
        shown = ", ".join(a.name if isinstance(a, Path) else "<bytes>" for a in self.args)
        return f"#{self.index} {self.name}({shown})"


def _no_sleep(_: float) -> None:
    return None


class FaultFs:
    """Counting ``CommitFs`` wrapper with fault and hook injection."""

    def __init__(
        self,
        inner: CommitFs | None = None,
        *,
        fail_at: Optional[int] = None,
        kind: str = "exception",
        after: bool = False,
        hook_at: Optional[int] = None,
        hook_when: Optional[Callable[[FsOp], bool]] = None,
        hook: Optional[Callable[["FaultFs", FsOp], None]] = None,
    ) -> None:
        if kind not in FAULT_KINDS:
            raise ValueError(f"unknown fault kind: {kind!r}")
        if fail_at is not None and fail_at < 1:
            raise ValueError("fail_at is 1-based")
        self.inner: CommitFs = inner if inner is not None else RealFs(delays=(), sleep=_no_sleep)
        self.ops: list[FsOp] = []
        self.fail_at = fail_at
        self.kind = kind
        self.after = after
        self.triggered = False
        self._hook_at = hook_at
        self._hook_when = hook_when
        self._hook = hook
        self._hook_done = False

    # -- helpers ------------------------------------------------------------

    @property
    def op_count(self) -> int:
        return len(self.ops)

    def _fail(self, op: FsOp, phase: str) -> None:
        self.triggered = True
        if self.kind == "exception":
            raise OSError(5, f"simulated I/O error {phase} {op}")
        raise SimulatedCrash(f"{phase} {op}")

    def _invoke(self, name: str, *args: Any) -> Any:
        op = FsOp(len(self.ops) + 1, name, args)
        self.ops.append(op)
        if self._hook is not None and not self._hook_done:
            if (self._hook_at is not None and op.index == self._hook_at) or (
                self._hook_when is not None and self._hook_when(op)
            ):
                self._hook_done = True
                self._hook(self, op)
        if op.index == self.fail_at and not self.after:
            if self.kind == "torn" and name == "write_file_durable":
                path, data = args
                with open(path, "wb") as fh:  # no fsync: a torn file
                    fh.write(data[: len(data) // 2])
            self._fail(op, "before")
        result = getattr(self.inner, name)(*args)
        if op.index == self.fail_at and self.after:
            self._fail(op, "after")
        return result

    # -- CommitFs -----------------------------------------------------------

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

    def mkdir(self, path: Path) -> None:
        return self._invoke("mkdir", path)
