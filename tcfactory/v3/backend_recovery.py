"""Evidence-preserving recovery for fixed controller-owned backend defects."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from tcfactory.checkpoints import CheckpointStore, V3Checkpoint
from tcfactory.claude_runner import CLAUDE_SANDBOX_CONFIG_REPAIR
from tcfactory.util import atomic_write_bytes
from tcfactory.v3.base import sha256_digest
from tcfactory.v3.enums import WorkStatus
from tcfactory.v3.queue import V3Queue
from tcfactory.v3.work_items import WorkItemCollection

_LEGACY_SANDBOX_FAILURE = b"bwrap: Can't mkdir /var/lib/.claude: Read-only file system"
_MAX_BACKEND_RESULT_BYTES = 2_000_000


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def _bound_backend_result(
    checkpoint: V3Checkpoint, *, runtime_root: Path
) -> tuple[Path, bytes] | None:
    artifact_root = Path(checkpoint.artifact_root or "")
    if not artifact_root.is_absolute() or not checkpoint.active_role:
        return None
    expected_root = (runtime_root / "artifacts/v3" / checkpoint.work_item_id).resolve()
    try:
        resolved_root = artifact_root.resolve(strict=True)
    except OSError:
        return None
    if not resolved_root.is_relative_to(expected_root) or artifact_root.is_symlink():
        return None
    result = resolved_root / checkpoint.active_role / "backend-result.json"
    try:
        result_stat = result.stat()
    except OSError:
        return None
    if (
        result.is_symlink()
        or not result.is_file()
        or result_stat.st_size > _MAX_BACKEND_RESULT_BYTES
    ):
        return None
    raw = result.read_bytes()
    return (result, raw) if _LEGACY_SANDBOX_FAILURE in raw else None


def _eligible(
    checkpoint: V3Checkpoint, *, runtime_root: Path, current_main_sha: str
) -> tuple[Path, bytes] | None:
    session = checkpoint.backend_session
    if (
        checkpoint.active
        or checkpoint.candidate_sha == current_main_sha
        or session is None
        or session.backend != "claude"
        or session.state.value != "FAILED"
        or checkpoint.circuit_breaker_reason is None
        or "finding" not in checkpoint.circuit_breaker_reason
        or "repeated" not in checkpoint.circuit_breaker_reason
    ):
        return None
    return _bound_backend_result(checkpoint, runtime_root=runtime_root)


def _write_journal(path: Path, payload: dict[str, object]) -> None:
    atomic_write_bytes(path, _canonical(payload))


def _finish_recovery(
    *,
    queue: V3Queue,
    checkpoints: CheckpointStore,
    work_item_id: str,
    now: datetime,
    journal_path: Path,
    journal: dict[str, object],
) -> bool:
    active = checkpoints.path_for(work_item_id)
    previous = active.with_suffix(active.suffix + ".previous")
    for source, key in ((active, "checkpointDigest"), (previous, "previousDigest")):
        expected = journal.get(key)
        if expected is None:
            continue
        archive = journal_path.parent / source.name
        if not archive.is_file() or sha256_digest(archive.read_bytes()) != expected:
            raise RuntimeError("backend recovery archive identity changed")
        if source.exists():
            if source.is_symlink() or sha256_digest(source.read_bytes()) != expected:
                raise RuntimeError("backend recovery source changed after preparation")
            source.unlink()
    item = queue.load(work_item_id)
    if item.status is WorkStatus.BLOCKED_TECHNICAL:
        queue.transition(work_item_id, WorkStatus.READY, updated_at=now)
    elif item.status is not WorkStatus.READY:
        raise RuntimeError("backend recovery queue state changed unexpectedly")
    committed = {**journal, "phase": "COMMITTED", "committedAt": now.isoformat()}
    _write_journal(journal_path, committed)
    return True


def recover_repaired_claude_sandbox_blocks(
    *,
    collection: WorkItemCollection,
    queue: V3Queue,
    checkpoints: CheckpointStore,
    runtime_root: Path,
    current_main_sha: str,
    now: datetime,
) -> list[str]:
    """Reopen only failures conclusively caused by the repaired sandbox home defect."""

    if CLAUDE_SANDBOX_CONFIG_REPAIR != "claude-native-credential-boundary-v3":
        raise RuntimeError("Claude sandbox repair marker is unavailable")
    recovered: list[str] = []
    recovery_root = checkpoints.root / "recovery-archive" / (
        f"{current_main_sha[:12]}-{CLAUDE_SANDBOX_CONFIG_REPAIR}"
    )
    recovery_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(recovery_root, 0o700)
    for item in collection.work_items:
        journal_path = recovery_root / f"{item.work_item_id}.journal.json"
        if journal_path.is_file():
            journal = json.loads(journal_path.read_bytes())
            if (
                journal.get("repairMarker") != CLAUDE_SANDBOX_CONFIG_REPAIR
                or journal.get("workItemId") != item.work_item_id
                or journal.get("recoveryMainSha") != current_main_sha
            ):
                raise RuntimeError("backend recovery journal identity changed")
            if journal.get("phase") == "COMMITTED":
                continue
            if _finish_recovery(
                queue=queue,
                checkpoints=checkpoints,
                work_item_id=item.work_item_id,
                now=now,
                journal_path=journal_path,
                journal=journal,
            ):
                recovered.append(item.work_item_id)
            continue
        if item.status is not WorkStatus.BLOCKED_TECHNICAL:
            continue
        checkpoint = checkpoints.load_v3(item.work_item_id)
        if checkpoint is None:
            continue
        matched = _eligible(
            checkpoint, runtime_root=runtime_root, current_main_sha=current_main_sha
        )
        if matched is None:
            continue
        result_path, result_raw = matched
        checkpoint_path = checkpoints.path_for(item.work_item_id)
        previous_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".previous")
        checkpoint_raw = checkpoint_path.read_bytes()
        previous_raw = previous_path.read_bytes() if previous_path.is_file() else None
        journal: dict[str, object] = {
            "schemaVersion": "3.1",
            "phase": "PREPARED",
            "workItemId": item.work_item_id,
            "repairMarker": CLAUDE_SANDBOX_CONFIG_REPAIR,
            "recoveryMainSha": current_main_sha,
            "failedCandidateSha": checkpoint.candidate_sha,
            "checkpointDigest": sha256_digest(checkpoint_raw),
            "previousDigest": sha256_digest(previous_raw) if previous_raw is not None else None,
            "backendResultPath": str(result_path),
            "backendResultDigest": sha256_digest(result_raw),
            "preparedAt": now.isoformat(),
        }
        _write_journal(journal_path, journal)
        atomic_write_bytes(recovery_root / checkpoint_path.name, checkpoint_raw)
        if previous_raw is not None:
            atomic_write_bytes(recovery_root / previous_path.name, previous_raw)
        journal = {**journal, "phase": "ARCHIVED"}
        _write_journal(journal_path, journal)
        if _finish_recovery(
            queue=queue,
            checkpoints=checkpoints,
            work_item_id=item.work_item_id,
            now=now,
            journal_path=journal_path,
            journal=journal,
        ):
            recovered.append(item.work_item_id)
    return recovered
