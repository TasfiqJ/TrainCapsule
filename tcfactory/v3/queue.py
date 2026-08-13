"""Atomic typed queue storage for V3 work items."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
from collections import defaultdict
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import yaml
from pydantic import Field

from tcfactory.util import read_json, write_json
from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import Lane, WorkStatus
from tcfactory.v3.work_items import WorkItem, assert_status_transition
from tcfactory.yamlutil import load_yaml


class QueueLease(V3Model):
    """Durable, renewable ownership of one RUNNING V3 item."""

    version: int = Field(default=3, ge=3, le=3)
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    owner_id: str = Field(min_length=1, max_length=128)
    owner_process_identity: str | None = Field(default=None, min_length=1, max_length=160)
    lease_id: str = Field(pattern=r"^LEASE-[A-F0-9]{32}$")
    claimed_at: datetime
    expires_at: datetime
    generation: int = Field(default=1, ge=1)


class TransitionIntent(V3Model):
    """Write-ahead record that makes a cross-directory transition recoverable."""

    version: int = Field(default=3, ge=3, le=3)
    work_item_id: str
    source: WorkStatus
    target: WorkStatus
    updated_at: datetime


class QueuePolicyCompatibility(V3Model):
    """Read-only proof that a stopped queue entry needs explicit policy migration."""

    work_item_id: str
    path: str
    observed_digest: str
    compatible_digest: str
    status_preserved: bool
    applied: bool = False


class V3Queue:
    """Filesystem queue with explicit state directories and no implicit resume."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.archive_root = self.root / "archive/v2"
        self.lease_root = self.root / ".leases"
        self.transaction_root = self.root / ".transactions"
        self.lock_root = self.root / ".locks"

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
        self._ensure_directory(self.lease_root)
        self._ensure_directory(self.transaction_root)
        self._ensure_directory(self.lock_root)

    def _lease_path(self, work_item_id: str) -> Path:
        return self.lease_root / f"{work_item_id}.json"

    @staticmethod
    def _process_identity(pid: int) -> str | None:
        """Return a PID-reuse-safe Linux process identity when procfs is available."""

        try:
            raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            fields = raw.rpartition(")")[2].split()
            start_ticks = fields[19]
        except (IndexError, OSError):
            return None
        return f"linux-proc:{pid}:{start_ticks}"

    @classmethod
    def _lease_owner_is_alive(cls, lease: QueueLease) -> bool | None:
        identity = lease.owner_process_identity
        if identity is None:
            return None
        parts = identity.split(":")
        if len(parts) != 3 or parts[0] != "linux-proc" or not parts[1].isdigit():
            return False
        return cls._process_identity(int(parts[1])) == identity

    def _transaction_path(self, work_item_id: str) -> Path:
        return self.transaction_root / f"{work_item_id}.json"

    @contextmanager
    def _claim_lock(self, work_item_id: str) -> Generator[None]:
        """Serialize claim/lease CAS across controller processes; OS releases on crash."""

        self._ensure_directory(self.lock_root)
        lock_path = self.lock_root / f"{work_item_id}.lock"
        with lock_path.open("a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _paths(self, work_item_id: str) -> list[Path]:
        name = f"{work_item_id}.yaml"
        return [path for state in WorkStatus if (path := self._state_dir(state) / name).is_file()]

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
        with self._claim_lock(item.work_item_id):
            if self._paths(item.work_item_id):
                raise ValueError(f"duplicate queue work item: {item.work_item_id}")
            target = self._state_dir(item.status) / f"{item.work_item_id}.yaml"
            self._atomic_write(target, item)
            return target

    def bind_external_evidence(
        self,
        work_item_id: str,
        *,
        receipt_id: str,
        updated_at: datetime,
    ) -> Path:
        """Bind a controller-verified receipt before an outside-fact transition."""

        with self._claim_lock(work_item_id):
            source = self.locate(work_item_id)
            item = WorkItem.model_validate(load_yaml(source))
            if not item.external_receipt_required:
                raise ValueError("work item does not require external evidence")
            references = list(dict.fromkeys([*item.external_evidence_refs, receipt_id]))
            payload = item.model_dump(mode="python", by_alias=False)
            payload.update({"external_evidence_refs": references, "updated_at": updated_at})
            updated = WorkItem.model_validate(payload)
            self._atomic_write(source, updated)
            return source

    def _transition_owned(
        self,
        work_item_id: str,
        target: WorkStatus,
        *,
        updated_at: datetime,
    ) -> Path:
        """Transition while the caller holds the work-item OS lock."""

        source = self.locate(work_item_id)
        item = WorkItem.model_validate(load_yaml(source))
        assert_status_transition(item.status, target)
        # Re-validate after every state change. ``model_copy(update=...)`` alone skips
        # Pydantic validators and previously allowed COMPLETED to bypass evidence gates.
        payload = item.model_dump(mode="python", by_alias=False)
        payload.update({"status": target, "updated_at": updated_at})
        updated = WorkItem.model_validate(payload)
        destination = self._state_dir(target) / source.name
        self._ensure_directory(destination.parent)
        intent = TransitionIntent(
            work_item_id=work_item_id,
            source=item.status,
            target=target,
            updated_at=updated_at,
        )
        journal = self._transaction_path(work_item_id)
        write_json(journal, intent.model_dump(mode="json", by_alias=True))
        # The source record is first made semantically current, then moved atomically.
        # A crash in between is repaired from the write-ahead intent at startup.
        self._atomic_write(source, updated)
        os.replace(source, destination)
        journal.unlink(missing_ok=True)
        if target is not WorkStatus.RUNNING:
            self._lease_path(work_item_id).unlink(missing_ok=True)
        return destination

    def transition(
        self,
        work_item_id: str,
        target: WorkStatus,
        *,
        updated_at: datetime,
    ) -> Path:
        """Cross-process atomic state transition with a durable write-ahead intent."""

        with self._claim_lock(work_item_id):
            return self._transition_owned(
                work_item_id,
                target,
                updated_at=updated_at,
            )

    def reconcile_transactions(self) -> list[str]:
        """Complete interrupted transitions without guessing or discarding evidence."""

        repaired: list[str] = []
        if not self.transaction_root.is_dir():
            return repaired
        for journal in sorted(self.transaction_root.glob("V3-*.json")):
            intent = TransitionIntent.model_validate(read_json(journal, {}))
            name = f"{intent.work_item_id}.yaml"
            source = self._state_dir(intent.source) / name
            destination = self._state_dir(intent.target) / name
            if destination.is_file() and not source.exists():
                observed = WorkItem.model_validate(load_yaml(destination))
                if observed.status is not intent.target:
                    raise ValueError("transition destination has the wrong embedded status")
            elif source.is_file() and not destination.exists():
                observed = WorkItem.model_validate(load_yaml(source))
                if observed.status is not intent.target:
                    raise ValueError("transition source does not contain target state")
                self._ensure_directory(destination.parent)
                os.replace(source, destination)
            else:
                raise ValueError(f"ambiguous interrupted transition for {intent.work_item_id}")
            journal.unlink()
            repaired.append(intent.work_item_id)
        return repaired

    def items(self, *states: WorkStatus) -> list[WorkItem]:
        """Return typed queue state in stable order."""

        selected = states or tuple(WorkStatus)
        result: list[WorkItem] = []
        for state in selected:
            directory = self._state_dir(state)
            if not directory.is_dir():
                continue
            result.extend(
                WorkItem.model_validate(load_yaml(path))
                for path in sorted(directory.glob("V3-*.yaml"))
            )
        identifiers = [item.work_item_id for item in result]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate active V3 queue work item")
        return result

    def compatible_items(
        self,
        authoritative: Mapping[str, WorkItem],
        *states: WorkStatus,
    ) -> tuple[list[WorkItem], list[QueuePolicyCompatibility]]:
        """Read stopped legacy queue state without rewriting it or trusting stale policy."""

        selected = states or tuple(WorkStatus)
        result: list[WorkItem] = []
        compatibility: list[QueuePolicyCompatibility] = []
        for state in selected:
            directory = self._state_dir(state)
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("V3-*.yaml")):
                raw = load_yaml(path)
                try:
                    result.append(WorkItem.model_validate(raw))
                    continue
                except ValueError:
                    if not isinstance(raw, dict):
                        raise
                typed_raw = cast(dict[str, Any], raw)
                identifier = typed_raw.get("workItemId")
                if not isinstance(identifier, str) or identifier not in authoritative:
                    raise ValueError(f"queue policy migration has no authority for {path}")
                canonical = authoritative[identifier]
                payload = canonical.model_dump(mode="python", by_alias=False)
                for raw_name, model_name in (
                    ("status", "status"),
                    ("packetPath", "packet_path"),
                    ("externalEvidenceRefs", "external_evidence_refs"),
                    ("createdAt", "created_at"),
                    ("updatedAt", "updated_at"),
                ):
                    if raw_name in typed_raw:
                        payload[model_name] = typed_raw[raw_name]
                compatible = WorkItem.model_validate(payload)
                result.append(compatible)
                observed_bytes = path.read_bytes()
                compatible_bytes = compatible.canonical_json_bytes()
                compatibility.append(
                    QueuePolicyCompatibility(
                        work_item_id=identifier,
                        path=str(path),
                        observed_digest="sha256:" + hashlib.sha256(observed_bytes).hexdigest(),
                        compatible_digest=(
                            "sha256:" + hashlib.sha256(compatible_bytes).hexdigest()
                        ),
                        status_preserved=(compatible.status.value == typed_raw.get("status")),
                    )
                )
        identifiers = [item.work_item_id for item in result]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate active V3 queue work item")
        return result, compatibility

    def claim(
        self,
        work_item_id: str,
        *,
        owner_id: str,
        now: datetime,
        lease_seconds: int = 900,
    ) -> QueueLease:
        """Atomically claim a QUEUED item and bind it to an expiring lease."""

        if lease_seconds < 30 or lease_seconds > 14_400:
            raise ValueError("lease_seconds must be between 30 and 14400")
        with self._claim_lock(work_item_id):
            item = self.load(work_item_id)
            if item.status is not WorkStatus.QUEUED:
                raise ValueError("only QUEUED work may be claimed")
            lease_path = self._lease_path(work_item_id)
            if lease_path.exists():
                existing = QueueLease.model_validate(read_json(lease_path, {}))
                if existing.expires_at > now:
                    raise ValueError("work item already has an active lease")
                lease_path.unlink()
            lease = QueueLease(
                work_item_id=work_item_id,
                owner_id=owner_id,
                owner_process_identity=self._process_identity(os.getpid()),
                lease_id=f"LEASE-{uuid4().hex.upper()}",
                claimed_at=now,
                expires_at=now + timedelta(seconds=lease_seconds),
            )
            write_json(lease_path, lease.model_dump(mode="json", by_alias=True))
            try:
                self._transition_owned(work_item_id, WorkStatus.RUNNING, updated_at=now)
                # transition deliberately clears non-RUNNING leases only.
            except Exception:
                observed = read_json(lease_path, {})
                if observed.get("leaseId") == lease.lease_id:
                    lease_path.unlink(missing_ok=True)
                raise
            return lease

    def renew(
        self,
        work_item_id: str,
        *,
        lease_id: str,
        now: datetime,
        lease_seconds: int = 900,
    ) -> QueueLease:
        with self._claim_lock(work_item_id):
            if self.load(work_item_id).status is not WorkStatus.RUNNING:
                raise ValueError("only RUNNING work leases may be renewed")
            lease_path = self._lease_path(work_item_id)
            lease = QueueLease.model_validate(read_json(lease_path, {}))
            if lease.lease_id != lease_id or lease.expires_at <= now:
                raise ValueError("lease is missing, expired, or owned by another controller")
            renewed = lease.model_copy(
                update={
                    "expires_at": now + timedelta(seconds=lease_seconds),
                    "generation": lease.generation + 1,
                }
            )
            write_json(lease_path, renewed.model_dump(mode="json", by_alias=True))
            return renewed

    def recover_expired_claims(self, *, now: datetime) -> list[str]:
        """Move abandoned RUNNING work to an explicit scoped technical block."""

        recovered: list[str] = []
        for item in self.items(WorkStatus.RUNNING):
            with self._claim_lock(item.work_item_id):
                observed = self.load(item.work_item_id)
                if observed.status is not WorkStatus.RUNNING:
                    continue
                lease_path = self._lease_path(item.work_item_id)
                if not lease_path.is_file():
                    abandoned = True
                else:
                    lease = QueueLease.model_validate(read_json(lease_path, {}))
                    owner_alive = self._lease_owner_is_alive(lease)
                    abandoned = lease.expires_at <= now or owner_alive is False
                if abandoned:
                    self._transition_owned(
                        item.work_item_id,
                        WorkStatus.BLOCKED_TECHNICAL,
                        updated_at=now,
                    )
                    recovered.append(item.work_item_id)
        return recovered

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
        """Recover only expired or provably dead claims; preserve every live lease."""

        return self.recover_expired_claims(now=updated_at)

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
