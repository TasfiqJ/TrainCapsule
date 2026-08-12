"""Descriptor-relative filesystem helpers for security-sensitive local paths."""

from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path


def open_directory_fd(path: Path, *, create: bool) -> int:
    """Open a directory without following any symlink in its ancestry."""
    absolute = path.absolute()
    if os.open not in os.supports_dir_fd or os.mkdir not in os.supports_dir_fd:
        raise OSError("secure directory-relative filesystem operations are unavailable")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(absolute.anchor, flags)
    try:
        for component in absolute.parts[1:]:
            if component in {"", "."}:
                continue
            if component == "..":
                raise OSError("parent traversal is forbidden in secure filesystem paths")
            if create:
                with suppress(FileExistsError):
                    os.mkdir(component, 0o700, dir_fd=descriptor)
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        os.close(descriptor)
        raise
