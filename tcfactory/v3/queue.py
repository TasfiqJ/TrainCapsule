"""Atomic typed queue storage for V3 work items."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml

from tcfactory.v3.enums import Lane, WorkStatus
from tcfactory.v3.work_items import WorkItem, assert_status_transition
from tcfactory.yamlutil import load_yaml


class V3Queue:
    """Filesystem queue with explicit state directories and no implicit resume."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.archive_root = self.root / "archive/v2"

    def _state_dir(self, state: WorkStatus) -> Path:
        return self.root / state.value.lower()

    def _ensure_directory(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        if directory.is_symlink():
            raise ValueError(f"queue directory cannot be a symlink: {directory}")

    def initialize(self) -> None:
        """Create the complete empty V3 state namespace without enqueueing work."""

        for state in WorkStatus:
            self._ensure_directory(self._state_dir(state))
        self._ensure_directory(self.archive_root)

    def _paths(self, work_item_id: str) -> list[Path]:
        name = f"{work_item_id}.yaml"
        return [
            path
            for state in WorkStatus
            if (path := self._state_dir(state) / name).is_file()
        ]

    def locate(self, work_item_id: str) -> Path:
        paths = self._paths(work_item_id)
        if len(paths) != 1:
            raise ValueError(
                f"expected exactly one queue entry for {work_item_id}; found {len(paths)}"
            )
        return paths[0]

    def load(self, work_item_id: str) -> WorkItem:
        return WorkItem.model_validate(load_yaml(self.locate(work_item_id)))

    def _atomic_write(self, path: Path, item: WorkItem) -> None:
        self._ensure_directory(path.parent)
        temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
        payload = item.model_dump(mode="json", by_alias=True, exclude_none=False)
        rendered = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
        temporary.write_text(rendered, encoding="utf-8", newline="\n")
        os.replace(temporary, path)

    def put(self, item: WorkItem) -> Path:
        if self._paths(item.work_item_id):
            raise ValueError(f"duplicate queue work item: {item.work_item_id}")
        target = self._state_dir(item.status) / f"{item.work_item_id}.yaml"
        self._atomic_write(target, item)
        return target

    def transition(
        self,
        work_item_id: str,
        target: WorkStatus,
        *,
        updated_at: datetime,
    ) -> Path:
        source = self.locate(work_item_id)
        item = WorkItem.model_validate(load_yaml(source))
        assert_status_transition(item.status, target)
        updated = item.model_copy(update={"status": target, "updated_at": updated_at})
        destination = self._state_dir(target) / source.name
        self._ensure_directory(destination.parent)
        os.replace(source, destination)
        self._atomic_write(destination, updated)
        return destination

    def by_lane(self) -> dict[Lane, list[WorkItem]]:
        result: dict[Lane, list[WorkItem]] = defaultdict(list)
        for state in WorkStatus:
            directory = self._state_dir(state)
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("V3-*.yaml")):
                item = WorkItem.model_validate(load_yaml(path))
                result[item.lane].append(item)
        return {
            lane: sorted(items, key=lambda item: item.work_item_id)
            for lane, items in result.items()
        }

    def recover_interrupted(self, *, updated_at: datetime) -> list[str]:
        """Move interrupted running items to an explicit technical block, never READY."""

        running = self._state_dir(WorkStatus.RUNNING)
        if not running.is_dir():
            return []
        recovered: list[str] = []
        for path in sorted(running.glob("V3-*.yaml")):
            item = WorkItem.model_validate(load_yaml(path))
            self.transition(
                item.work_item_id,
                WorkStatus.BLOCKED_TECHNICAL,
                updated_at=updated_at,
            )
            recovered.append(item.work_item_id)
        return recovered

    def archive_v2(
        self,
        source: Path,
        *,
        archive_id: str,
        captured_at: datetime | None = None,
    ) -> Path:
        """Copy legacy queue evidence into an immutable archive without enqueueing it."""

        source = source.resolve()
        if not source.is_dir():
            raise ValueError("legacy queue archive source must be a directory")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", archive_id):
            raise ValueError("legacy queue archive ID contains unsafe characters")
        if source == self.root or source in self.root.parents or self.root in source.parents:
            raise ValueError("legacy queue archive source must be a separate directory")
        source_files = sorted(item for item in source.rglob("*") if item.is_file())
        symlinks = sorted(item for item in source.rglob("*") if item.is_symlink())
        if symlinks:
            raise ValueError(
                "legacy queue archive source contains symlinks: "
                f"{[path.relative_to(source).as_posix() for path in symlinks]}"
            )
        files: list[dict[str, str | int]] = []
        source_hasher = hashlib.sha256()
        for path in source_files:
            relative = path.relative_to(source).as_posix()
            payload = path.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            files.append({"path": relative, "sha256": digest, "bytes": len(payload)})
            source_hasher.update(relative.encode("utf-8") + b"\0")
            source_hasher.update(digest.encode("ascii") + b"\0")
            source_hasher.update(str(len(payload)).encode("ascii") + b"\n")

        target = self.archive_root / archive_id
        if target.exists():
            manifest_path = target / "ARCHIVE_MANIFEST.json"
            if manifest_path.is_file():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("sourceDigest") == f"sha256:{source_hasher.hexdigest()}":
                    return target
            raise ValueError(f"legacy queue archive already exists with other evidence: {target}")
        self._ensure_directory(target.parent)
        observed_at = captured_at or datetime.now(UTC)
        if observed_at.tzinfo is None:
            raise ValueError("archive captured_at must be timezone-aware")
        temporary = target.parent / f".{archive_id}.{uuid4().hex}.tmp"
        shutil.copytree(source, temporary, symlinks=False)
        manifest: dict[str, object] = {
            "version": 3,
            "archiveId": archive_id,
            "capturedAt": observed_at.astimezone(UTC).isoformat(),
            "sourceLabel": source.name,
            "sourceDigest": f"sha256:{source_hasher.hexdigest()}",
            "autoResume": False,
            "files": files,
        }
        try:
            (temporary / "ARCHIVE_MANIFEST.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return target
