"""Filesystem operations used by the merge commit protocol (Qt-free).

``CommitFs`` is the small protocol the commit and recovery code talks to, so
tests can substitute fault-injecting implementations. ``RealFs`` is the real
implementation with fsync and, on Windows, retry on sharing violations.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

# Delays (seconds) between retries: 25 ms .. 1600 ms, about 3 s in total.
RETRY_DELAYS: tuple[float, ...] = (0.025, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6)
# Windows error codes: access denied, sharing violation, lock violation.
_RETRY_WINERRORS = (5, 32, 33)

_MOVEFILE_REPLACE_EXISTING = 0x1
_MOVEFILE_WRITE_THROUGH = 0x8


def _is_retryable(exc: OSError) -> bool:
    if isinstance(exc, PermissionError):
        return True
    return getattr(exc, "winerror", None) in _RETRY_WINERRORS


def retry_io(
    op: Callable[[], object],
    *,
    delays: tuple[float, ...] = RETRY_DELAYS,
    sleep: Callable[[float], None] = time.sleep,
):
    """Run ``op``, retrying on transient sharing violations.

    Makes one attempt per delay plus one final attempt; the last error is
    raised when the budget is spent. Non-retryable errors propagate at once.
    """
    for delay in delays:
        try:
            return op()
        except OSError as exc:
            if not _is_retryable(exc):
                raise
            sleep(delay)
    return op()


def _move_write_through(src: str, dst: str) -> bool:
    """Windows MoveFileExW with write-through. False when unavailable."""
    try:
        import ctypes

        move = ctypes.windll.kernel32.MoveFileExW  # type: ignore[attr-defined]
    except (ImportError, AttributeError, OSError):
        return False
    ok = move(
        ctypes.c_wchar_p(src),
        ctypes.c_wchar_p(dst),
        _MOVEFILE_REPLACE_EXISTING | _MOVEFILE_WRITE_THROUGH,
    )
    if not ok:
        err = ctypes.get_last_error() or ctypes.GetLastError()  # type: ignore[attr-defined]
        raise ctypes.WinError(err)  # type: ignore[attr-defined]
    return True


def replace_with_retry(
    src: str | os.PathLike[str],
    dst: str | os.PathLike[str],
    *,
    delays: tuple[float, ...] = RETRY_DELAYS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Atomically replace ``dst`` with ``src``; retry on Windows sharing errors."""
    s, d = os.fspath(src), os.fspath(dst)

    def attempt() -> None:
        if sys.platform == "win32" and _move_write_through(s, d):
            return
        os.replace(s, d)

    retry_io(attempt, delays=delays, sleep=sleep)


@runtime_checkable
class CommitFs(Protocol):
    """Filesystem operations the commit protocol is allowed to use."""

    def exists(self, path: Path) -> bool: ...
    def read_bytes(self, path: Path) -> bytes: ...
    def write_file_durable(self, path: Path, data: bytes) -> None: ...
    def copy_file_durable(self, src: Path, dst: Path) -> None: ...
    def replace(self, src: Path, dst: Path) -> None: ...
    def remove(self, path: Path) -> None: ...
    def rmtree(self, path: Path) -> None: ...
    def fsync_dir(self, path: Path) -> None: ...
    def stat(self, path: Path) -> os.stat_result: ...
    def listdir(self, path: Path) -> list[str]: ...
    def create_exclusive(self, path: Path) -> None: ...
    def mkdir(self, path: Path) -> None: ...


class RealFs:
    """``CommitFs`` on the real filesystem."""

    def __init__(
        self,
        *,
        delays: tuple[float, ...] = RETRY_DELAYS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._delays = delays
        self._sleep = sleep

    def _retry(self, op: Callable[[], object]):
        return retry_io(op, delays=self._delays, sleep=self._sleep)

    def exists(self, path: Path) -> bool:
        return os.path.exists(path)

    def read_bytes(self, path: Path) -> bytes:
        def op() -> bytes:
            with open(path, "rb") as fh:
                return fh.read()

        return self._retry(op)  # type: ignore[return-value]

    def write_file_durable(self, path: Path, data: bytes) -> None:
        with open(path, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())

    def copy_file_durable(self, src: Path, dst: Path) -> None:
        self.write_file_durable(dst, self.read_bytes(src))

    def replace(self, src: Path, dst: Path) -> None:
        replace_with_retry(src, dst, delays=self._delays, sleep=self._sleep)
        self.fsync_dir(Path(dst).parent)

    def remove(self, path: Path) -> None:
        def op() -> None:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

        self._retry(op)

    def rmtree(self, path: Path) -> None:
        def op() -> None:
            shutil.rmtree(path, ignore_errors=False)

        if os.path.exists(path):
            self._retry(op)

    def fsync_dir(self, path: Path) -> None:
        # Windows cannot open a directory with os.open; skip there.
        if sys.platform == "win32":
            return
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def stat(self, path: Path) -> os.stat_result:
        return os.stat(path)

    def listdir(self, path: Path) -> list[str]:
        return os.listdir(path)

    def mkdir(self, path: Path) -> None:
        """Create one directory (parent must exist); FileExistsError if present."""
        os.mkdir(path)

    def create_exclusive(self, path: Path) -> None:
        """Create ``path`` with O_CREAT|O_EXCL; FileExistsError if present."""
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
