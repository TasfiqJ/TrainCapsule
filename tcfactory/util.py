from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"(?:token|secret|password|credential|authorization|cookie|api[_-]?key|account[_-]?id)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE = re.compile(
    r"(?i)(?:bearer\s+|(?:sk|ghp|github_pat|oauth)[-_])[A-Za-z0-9._-]{8,}"
)
_SAFE_ENV_KEYS = {
    "CI",
    "COLORTERM",
    "LANG",
    "LC_ALL",
    "NO_COLOR",
    "PATH",
    "PYTHONPATH",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TMP",
    "TZ",
    "UV_CACHE_DIR",
    "VIRTUAL_ENV",
    "WINDIR",
}


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return value[:96] or "run"


def run_command(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        timeout=timeout,
        env=merged_env,
        text=True,
        input=input_text,
        capture_output=True,
    )


def sanitized_subprocess_env(
    extra: dict[str, str] | None = None,
    *,
    inherit: Iterable[str] = _SAFE_ENV_KEYS,
) -> dict[str, str]:
    """Build a child environment without controller credentials or secret paths."""

    allowed = {key.upper() for key in inherit}
    result = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in allowed and not _SENSITIVE_KEY.search(key)
    }
    for key, value in (extra or {}).items():
        if _SENSITIVE_KEY.search(key):
            raise ValueError(f"refusing sensitive subprocess environment key: {key}")
        result[key] = value
    return result


def redact_sensitive(value: str) -> str:
    """Redact credentials and host-specific home paths from exportable text."""

    redacted = _SENSITIVE_VALUE.sub("[REDACTED]", value)
    candidates = {
        os.environ.get("HOME"),
        os.environ.get("USERPROFILE"),
        os.environ.get("CODEX_HOME"),
    }
    for raw in sorted((item for item in candidates if item), key=len, reverse=True):
        redacted = redacted.replace(str(raw), "[USER_HOME]")
        redacted = redacted.replace(str(raw).replace("\\", "/"), "[USER_HOME]")
    return redacted


def resolve_within(
    root: Path,
    raw_path: str | Path,
    *,
    require_exists: bool = False,
    reject_symlinks: bool = True,
) -> Path:
    """Resolve a path beneath ``root`` and reject escapes or symlink surprises."""

    resolved_root = root.resolve(strict=True)
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = resolved_root / candidate
    resolved = candidate.resolve(strict=require_exists)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"path escapes permitted root: {raw_path}")
    if reject_symlinks:
        current = candidate
        while current != resolved_root and current != current.parent:
            if current.is_symlink():
                raise ValueError(f"symlink path component is not permitted: {raw_path}")
            current = current.parent
    return resolved


def _sync_parent(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_bytes(path: Path, payload: bytes, *, keep_previous: bool = False) -> None:
    """Durably replace a file using a same-directory temporary generation."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if keep_previous and path.is_file():
        previous = path.with_suffix(path.suffix + ".previous")
        atomic_write_bytes(previous, path.read_bytes(), keep_previous=False)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        _sync_parent(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def atomic_write_text(path: Path, value: str, *, keep_previous: bool = False) -> None:
    atomic_write_bytes(path, value.encode("utf-8"), keep_previous=keep_previous)


@contextmanager
def single_writer_lock(path: Path) -> Any:
    """Acquire a fail-fast process lock represented by an exclusive file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"single-writer lock is already held: {path}") from exc
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode())
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        path.unlink(missing_ok=True)


def append_jsonl_locked(path: Path, payload: dict[str, Any]) -> None:
    """Append a complete JSON event while holding a per-file writer lock."""

    line = json.dumps(payload, sort_keys=True, default=str) + "\n"
    lock = path.with_suffix(path.suffix + ".lock")
    with single_writer_lock(lock):
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        atomic_write_text(path, existing + line)


def write_json(path: Path, value: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
    )


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def path_matches(path: str, patterns: Iterable[str]) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return any(fnmatch.fnmatch(normalized, pattern.lstrip("./")) for pattern in patterns)
