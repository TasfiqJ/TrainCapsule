from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from .models import StageResult, TaskPacket
from .util import resolve_within, write_json
from .v3.base import DIGEST_PATTERN, SHA_PATTERN, V3Model, sha256_digest
from .v3.enums import Disposition
from .v3.work_items import WorkItem


class V3HandoffPayload(V3Model):
    schema_version: int = Field(default=3, ge=3, le=3)
    work_item_id: str
    lane: str
    milestone: str
    disposition: Disposition
    attempt: int = Field(ge=1)
    attempts_remaining: int = Field(ge=0)
    base_sha: str = Field(pattern=SHA_PATTERN.pattern)
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    backend_session_ref: str | None = None
    next_action: str = Field(min_length=1)
    findings: list[str]
    artifact_digests: dict[str, str]


class V3Handoff(V3Model):
    payload: V3HandoffPayload
    payload_digest: str = Field(pattern=DIGEST_PATTERN.pattern)

    def verify(self) -> None:
        if self.payload.canonical_digest() != self.payload_digest:
            raise ValueError("handoff payload digest mismatch")


def write_v3_handoff(
    *,
    artifact_root: Path,
    relative_path: str,
    work_item: WorkItem,
    disposition: Disposition,
    attempt: int,
    attempts_remaining: int,
    base_sha: str,
    candidate_sha: str,
    next_action: str,
    findings: list[str],
    artifacts: dict[str, Path],
    backend_session_ref: str | None = None,
) -> Path:
    """Write a digest-bound backend-neutral V3 handoff beneath its artifact root."""

    artifact_root.mkdir(parents=True, exist_ok=True)
    target = resolve_within(artifact_root, relative_path)
    artifact_digests: dict[str, str] = {}
    for name, path in artifacts.items():
        resolved = resolve_within(artifact_root, path, require_exists=True)
        artifact_digests[name] = sha256_digest(resolved.read_bytes())
    payload = V3HandoffPayload(
        work_item_id=work_item.work_item_id,
        lane=work_item.lane.value,
        milestone=work_item.milestone,
        disposition=disposition,
        attempt=attempt,
        attempts_remaining=attempts_remaining,
        base_sha=base_sha,
        candidate_sha=candidate_sha,
        backend_session_ref=backend_session_ref,
        next_action=next_action,
        findings=findings,
        artifact_digests=artifact_digests,
    )
    handoff = V3Handoff(payload=payload, payload_digest=payload.canonical_digest())
    write_json(target, handoff.model_dump(mode="json", by_alias=True))
    return target


def read_v3_handoff(path: Path) -> V3Handoff:
    handoff = V3Handoff.model_validate_json(path.read_text(encoding="utf-8"))
    handoff.verify()
    return handoff


def write_handoff(
    *,
    artifact_dir: Path,
    task: TaskPacket,
    result: StageResult | None,
    base_sha: str,
    candidate_sha: str,
    next_action: str,
    findings: list[str] | None = None,
) -> Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "task_id": task.task_id,
        "title": task.title,
        "risk_tier": task.risk_tier.value,
        "base_sha": base_sha,
        "candidate_sha": candidate_sha,
        "next_action": next_action,
        "findings": findings or [],
    }
    if result is not None:
        payload.update(
            {
                "completed_role": result.role.value,
                "verdict": result.verdict.value,
                "session_id": result.session_id,
                "model": result.model,
                "changed_files": result.changed_files,
                "commands_run": result.report.commands_run if result.report else [],
                "tests_run": result.report.tests_run if result.report else [],
                "limitations": result.report.limitations if result.report else [],
            }
        )
    json_path = artifact_dir / "HANDOFF.json"
    write_json(json_path, payload)
    md_path = artifact_dir / "HANDOFF.md"
    lines = [
        f"# Handoff — {task.task_id}",
        "",
        f"- Risk: `{task.risk_tier.value}`",
        f"- Base: `{base_sha}`",
        f"- Candidate: `{candidate_sha}`",
        f"- Next action: {next_action}",
    ]
    if result is not None:
        lines.extend(
            [
                f"- Completed role: `{result.role.value}`",
                f"- Verdict: `{result.verdict.value}`",
                f"- Model: `{result.model}`",
                f"- Session: `{result.session_id or 'unknown'}`",
            ]
        )
    if findings:
        lines.extend(["", "## Findings", *[f"- {item}" for item in findings]])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path
