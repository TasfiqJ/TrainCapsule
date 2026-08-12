"""Process-wide ownership for the only active V3 controller."""

from __future__ import annotations

import fcntl
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


class ControllerLockError(RuntimeError):
    """Raised when another process owns the V3 controller lifetime."""


@contextmanager
def controller_process_lock(path: Path) -> Generator[None]:
    """Hold one non-blocking OS lock for the caller's entire controller lifetime."""

    requested = path.expanduser()
    requested.parent.mkdir(parents=True, exist_ok=True)
    if requested.parent.is_symlink() or requested.is_symlink():
        raise ControllerLockError("controller lock directory cannot be a symlink")
    resolved = requested.resolve()
    with resolved.open("a+b") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ControllerLockError("another V3 controller process is already active") from exc
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
