from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import StageResult, TaskPacket
from .util import write_json


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
