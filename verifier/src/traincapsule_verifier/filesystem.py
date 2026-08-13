"""Descriptor-anchored trusted file access and replay-safe nonce storage."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


class TrustedPathError(ValueError):
    pass


@dataclass(slots=True)
class TrustedRoot:
    """An opened directory identity that cannot be redirected by a later rename."""

    path: Path
    descriptor: int
    expected_uid: int
    device: int
    inode: int
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        descriptor = self.descriptor
        self._closed = True
        self.descriptor = -1
        os.close(descriptor)

    def __enter__(self) -> TrustedRoot:
        if self._closed:
            raise TrustedPathError("trusted directory is closed")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def __del__(self) -> None:
        with contextlib.suppress(OSError):
            self.close()

    def duplicate_descriptor(self) -> int:
        if self._closed:
            raise TrustedPathError("trusted directory is closed")
        descriptor = os.dup(self.descriptor)
        metadata = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) != (self.device, self.inode):
            os.close(descriptor)
            raise TrustedPathError("trusted directory identity changed")
        return descriptor


def assert_outside_repository(path: Path, repository_root: Path) -> Path:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(repository_root.resolve(strict=True))
    except ValueError:
        return resolved
    raise TrustedPathError("verifier trust material must be outside the candidate repository")


def _open_directory_identity(path: Path, expected_uid: int) -> TrustedRoot:
    if path.is_symlink():
        raise TrustedPathError("trusted root cannot be a symbolic link")
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved,
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise TrustedPathError("trusted root must be a directory")
        if metadata.st_uid != expected_uid:
            raise TrustedPathError("trusted root owner UID mismatch")
        if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise TrustedPathError("trusted root cannot be group/world writable")
        path_metadata = os.stat(resolved, follow_symlinks=False)
        if (metadata.st_dev, metadata.st_ino) != (path_metadata.st_dev, path_metadata.st_ino):
            raise TrustedPathError("trusted root identity changed during validation")
        return TrustedRoot(
            path=resolved,
            descriptor=descriptor,
            expected_uid=expected_uid,
            device=metadata.st_dev,
            inode=metadata.st_ino,
        )
    except Exception:
        os.close(descriptor)
        raise


def open_trusted_root(path: Path, *, expected_uid: int) -> TrustedRoot:
    return _open_directory_identity(path, expected_uid)


def assert_trusted_root(path: Path, *, expected_uid: int, repository_root: Path) -> TrustedRoot:
    if path.is_symlink():
        raise TrustedPathError("trusted root cannot be a symbolic link")
    resolved = assert_outside_repository(path, repository_root)
    return _open_directory_identity(resolved, expected_uid)


def _validate_relative(relative: str, *, single_component: bool = False) -> list[str]:
    if "\\" in relative or relative.startswith("/"):
        raise TrustedPathError("trusted file path must be normalized and relative")
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise TrustedPathError("trusted file path must be normalized and relative")
    if single_component and len(parts) != 1:
        raise TrustedPathError("output name must be one normalized path component")
    return parts


def _validate_opened(
    descriptor: int,
    *,
    expected_uid: int,
    require_directory: bool,
    maximum_bytes: int | None = None,
) -> os.stat_result:
    metadata = os.fstat(descriptor)
    expected_type = stat.S_ISDIR if require_directory else stat.S_ISREG
    if not expected_type(metadata.st_mode):
        raise TrustedPathError("trusted object has the wrong file type")
    if metadata.st_uid != expected_uid:
        raise TrustedPathError("trusted object owner UID mismatch")
    if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise TrustedPathError("trusted object cannot be group/world writable")
    if maximum_bytes is not None and metadata.st_size > maximum_bytes:
        raise TrustedPathError("trusted file exceeds size limit")
    return metadata


def open_trusted_file(
    root: TrustedRoot,
    relative: str,
    *,
    maximum_bytes: int = 10_000_000,
    require_executable: bool = False,
    required_mode: int | None = None,
    expected_file_uid: int | None = None,
) -> int:
    """Open a regular file relative to an already-anchored trusted root."""

    parts = _validate_relative(relative)
    root_descriptor = root.duplicate_descriptor()
    current = root_descriptor
    opened: list[int] = []
    try:
        for part in parts[:-1]:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current,
            )
            _validate_opened(child, expected_uid=root.expected_uid, require_directory=True)
            opened.append(child)
            current = child
        descriptor = os.open(
            parts[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=current,
        )
        try:
            metadata = _validate_opened(
                descriptor,
                expected_uid=(
                    root.expected_uid if expected_file_uid is None else expected_file_uid
                ),
                require_directory=False,
                maximum_bytes=maximum_bytes,
            )
            if require_executable and not metadata.st_mode & stat.S_IXUSR:
                raise TrustedPathError("trusted oracle runner is not owner-executable")
            if required_mode is not None and stat.S_IMODE(metadata.st_mode) != required_mode:
                raise TrustedPathError(f"trusted file mode must be {oct(required_mode)}")
            return descriptor
        except Exception:
            os.close(descriptor)
            raise
    finally:
        for opened_descriptor in reversed(opened):
            os.close(opened_descriptor)
        os.close(root_descriptor)


def _read_descriptor(descriptor: int, maximum_bytes: int) -> bytes:
    chunks: list[bytes] = []
    remaining = maximum_bytes + 1
    while remaining > 0:
        chunk = os.read(descriptor, min(remaining, 1_048_576))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b"".join(chunks)
    if len(data) > maximum_bytes:
        raise TrustedPathError("trusted file exceeds size limit")
    return data


def read_bounded_file(
    root: TrustedRoot,
    relative: str,
    *,
    maximum_bytes: int = 10_000_000,
    required_mode: int | None = None,
    expected_file_uid: int | None = None,
) -> bytes:
    descriptor = open_trusted_file(
        root,
        relative,
        maximum_bytes=maximum_bytes,
        required_mode=required_mode,
        expected_file_uid=expected_file_uid,
    )
    try:
        return _read_descriptor(descriptor, maximum_bytes)
    finally:
        os.close(descriptor)


def sha256_file(root: TrustedRoot, relative: str) -> str:
    return "sha256:" + hashlib.sha256(read_bounded_file(root, relative)).hexdigest()


def strict_json_loads(data: bytes, *, maximum_depth: int = 32) -> dict[str, Any]:
    if len(data) > 5_000_000:
        raise TrustedPathError("JSON document exceeds size limit")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise TrustedPathError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustedPathError("JSON document is malformed") from exc
    if not isinstance(value, dict):
        raise TrustedPathError("JSON document must be an object")

    def depth(item: object, level: int) -> None:
        if level > maximum_depth:
            raise TrustedPathError("JSON document exceeds nesting limit")
        if isinstance(item, dict):
            for nested in cast(dict[object, object], item).values():
                depth(nested, level + 1)
        elif isinstance(item, list):
            for nested in cast(list[object], item):
                depth(nested, level + 1)

    typed_value = cast(dict[str, Any], value)
    depth(typed_value, 1)
    return typed_value


class NonceStore:
    """Process-safe one-use nonce ledger under an anchored external state root."""

    def __init__(self, root: TrustedRoot) -> None:
        self.root = root

    def consume(self, nonce: str) -> None:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        root_descriptor = self.root.duplicate_descriptor()
        descriptor = os.open("consumed-nonces.json", flags, 0o600, dir_fd=root_descriptor)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != self.root.expected_uid:
                raise TrustedPathError("nonce ledger is not a trusted regular file")
            if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise TrustedPathError("nonce ledger cannot be group/world writable")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            raw = _read_descriptor(descriptor, 5_000_000)
            consumed: list[str]
            if raw:
                parsed = strict_json_loads(raw)
                values = parsed.get("consumed")
                if not isinstance(values, list):
                    raise TrustedPathError("nonce ledger has an invalid shape")
                untyped_values = cast(list[object], values)
                if not all(isinstance(item, str) for item in untyped_values):
                    raise TrustedPathError("nonce ledger has an invalid shape")
                consumed = cast(list[str], untyped_values)
            else:
                consumed = []
            if nonce in consumed:
                raise TrustedPathError("request nonce was already consumed")
            consumed.append(nonce)
            encoded = (
                json.dumps({"consumed": sorted(consumed)}, separators=(",", ":"), sort_keys=True)
                + "\n"
            ).encode()
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.ftruncate(descriptor, 0)
            view = memoryview(encoded)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise TrustedPathError("nonce ledger write did not progress")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
            os.close(root_descriptor)


def atomic_write_new(
    root: TrustedRoot,
    relative: str,
    data: bytes,
    *,
    mode: int = 0o600,
    owner_uid: int | None = None,
    owner_gid: int | None = None,
) -> Path:
    parts = _validate_relative(relative)
    root_descriptor = root.duplicate_descriptor()
    parent_descriptor = root_descriptor
    opened_directories: list[int] = []
    temporary = f".{parts[-1]}.{os.getpid()}.tmp"
    descriptor: int | None = None
    try:
        if (owner_uid is None) != (owner_gid is None):
            raise TrustedPathError("output owner UID/GID must be supplied together")
        expected_uid = owner_uid if owner_uid is not None else root.expected_uid
        for component in parts[:-1]:
            try:
                child = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=parent_descriptor,
                )
            except FileNotFoundError:
                os.mkdir(component, mode=0o700, dir_fd=parent_descriptor)
                if owner_uid is not None and owner_gid is not None:
                    os.chown(
                        component,
                        owner_uid,
                        owner_gid,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                child = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=parent_descriptor,
                )
            _validate_opened(child, expected_uid=expected_uid, require_directory=True)
            opened_directories.append(child)
            parent_descriptor = child
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
            dir_fd=parent_descriptor,
        )
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise TrustedPathError("verifier output write did not progress")
            view = view[written:]
        if owner_uid is not None and owner_gid is not None:
            os.fchown(descriptor, owner_uid, owner_gid)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.link(
            temporary,
            parts[-1],
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        os.unlink(temporary, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
        return root.path / relative
    except FileExistsError as exc:
        raise TrustedPathError("refusing to overwrite existing verifier output") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=parent_descriptor)
        for opened in reversed(opened_directories):
            os.close(opened)
        os.close(root_descriptor)
