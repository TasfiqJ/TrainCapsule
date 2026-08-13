"""Descriptor-pinned owner-only service storage for Phase 6 mutable state."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path


class ServiceStorageError(RuntimeError):
    """A mutable service directory no longer matches its installed identity."""


@dataclass(frozen=True)
class TrustedServiceDirectory:
    path: Path
    owner_uid: int
    device: int
    inode: int
    mode: int = 0o700

    @classmethod
    def capture(
        cls, path: Path, *, owner_uid: int, mode: int = 0o700
    ) -> TrustedServiceDirectory:
        absolute = Path(os.path.abspath(path))
        try:
            metadata = absolute.lstat()
        except OSError as exc:
            raise ServiceStorageError("service directory is unavailable") from exc
        if (
            absolute.is_symlink()
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != owner_uid
            or stat.S_IMODE(metadata.st_mode) != mode
        ):
            raise ServiceStorageError("service directory owner, type, or mode is unsafe")
        return cls(
            path=absolute,
            owner_uid=owner_uid,
            device=metadata.st_dev,
            inode=metadata.st_ino,
            mode=mode,
        )

    def open_fd(self) -> int:
        """Revalidate pathname and descriptor identity on every mutable operation."""

        try:
            before = self.path.lstat()
            fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as exc:
            raise ServiceStorageError("service directory was replaced or removed") from exc
        try:
            after = os.fstat(fd)
            for metadata in (before, after):
                if (
                    not stat.S_ISDIR(metadata.st_mode)
                    or metadata.st_uid != self.owner_uid
                    or stat.S_IMODE(metadata.st_mode) != self.mode
                    or (metadata.st_dev, metadata.st_ino) != (self.device, self.inode)
                ):
                    raise ServiceStorageError("service directory identity changed after install")
            return fd
        except Exception:
            os.close(fd)
            raise
