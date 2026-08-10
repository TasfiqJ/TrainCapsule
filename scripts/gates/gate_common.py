from __future__ import annotations

import fnmatch
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT))
from tcfactory.yamlutil import load_yaml as strict_load_yaml  # noqa: E402


def load_yaml(path: Path) -> object:
    return strict_load_yaml(path)


def task_path(task_id: str) -> Path:
    direct = ROOT / "tasks" / f"{task_id}.yaml"
    if direct.is_file():
        return direct
    matches = list((ROOT / "factory" / "queue").glob(f"*/{task_id}.yaml"))
    if matches:
        return matches[0]
    raise SystemExit(f"Task packet not found for {task_id}")


def task_payload(task_id: str) -> dict[str, object]:
    value = load_yaml(task_path(task_id))
    if not isinstance(value, dict):
        raise SystemExit(f"Task packet is not a mapping: {task_id}")
    return cast(dict[str, object], value)


def catalog_payload() -> dict[str, object]:
    value = load_yaml(ROOT / "factory" / "task_catalog.yaml")
    if not isinstance(value, dict):
        raise SystemExit("Task catalog is not a mapping")
    return cast(dict[str, object], value)


def tracked_and_untracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    files: list[Path] = []
    for raw in result.stdout.splitlines():
        path = ROOT / raw
        if path.is_file():
            files.append(path)
    return files


def match_files(pattern: str) -> list[Path]:
    # Remove only an explicit current-directory prefix. ``str.lstrip("./")`` removes every
    # leading dot and slash character and therefore corrupts authoritative hidden paths such as
    # ``.factory/external-evidence/T001.json`` into ``factory/...``.
    normalized = pattern.replace("\\", "/").removeprefix("./")
    if "*" not in normalized and "?" not in normalized and "[" not in normalized:
        path = ROOT / normalized
        return [path] if path.exists() else []
    return [
        path
        for path in tracked_and_untracked_files()
        if fnmatch.fnmatch(path.relative_to(ROOT).as_posix(), normalized)
    ]


def require_patterns(patterns: Iterable[str]) -> list[str]:
    missing: list[str] = []
    for pattern in patterns:
        if not match_files(pattern):
            missing.append(pattern)
    return missing
