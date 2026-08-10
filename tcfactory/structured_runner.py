from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, TypeVar, cast

from claude_agent_sdk import EffortLevel, SandboxSettings
from pydantic import BaseModel

from .auth import assert_max_oauth_only, sanitized_agent_environment
from .ledger import Ledger
from .models import (
    AgentReport,
    FactoryConfig,
    PauseKind,
    RoleName,
    StageResult,
    Verdict,
)
from .quota import (
    AuthenticationPause,
    QuotaLimitPause,
    classify_failure_texts,
    disposition_from_rate_limit_info,
)
from .util import write_json

T = TypeVar("T", bound=BaseModel)


def _message_to_json(message: object) -> dict[str, Any]:
    if is_dataclass(message) and not isinstance(message, type):
        data = asdict(message)
    elif hasattr(message, "__dict__"):
        data = dict(vars(message))
    else:
        data = {"repr": repr(message)}
    data["_type"] = type(message).__name__
    return data


async def run_structured_read_only_review[T: BaseModel](
    *,
    repo_root: Path,
    cwd: Path,
    config: FactoryConfig,
    prompt: str,
    system_prompt: str,
    model: str,
    effort: str,
    max_turns: int,
    max_budget_usd: float,
    schema: dict[str, Any],
    result_type: type[T],
    artifact_dir: Path,
    role: RoleName,
    task_id: str,
    run_id: str,
) -> T:
    """Run one fresh, read-only Claude session and enforce structured output.

    The caller supplies a disposable Git worktree as ``cwd``. The session never resumes
    another chat. Quota messages are classified into a durable pause that the autopilot can
    sleep through and retry later.
    """

    try:
        assert_max_oauth_only(require_long_lived_token=True)
    except RuntimeError as exc:
        raise AuthenticationPause(str(exc)) from exc
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
    except ImportError as exc:
        raise RuntimeError("claude-agent-sdk is not installed") from exc

    ledger = Ledger(config.resolve(repo_root, config.ledger_path), config.monthly_budget_usd)
    ledger.assert_budget(max_budget_usd)

    artifact_dir.mkdir(parents=True, exist_ok=True)
    transcript = artifact_dir / "transcript.jsonl"
    stderr_path = artifact_dir / "claude-stderr.log"
    environment = sanitized_agent_environment(
        {
            "TCF_TASK_ID": task_id,
            "TCF_ACTIVE_ROLE": role.value,
            "TCF_REPO_ROOT": str(cwd.resolve()),
            "TCF_READ_ONLY": "1",
            "TCF_NETWORK_MODE": "deny",
            "TCF_ALLOWED_PATHS_JSON": "[]",
            "TCF_FORBIDDEN_PATHS_JSON": '["**"]',
            "TCF_ALLOWED_DOMAINS_JSON": "[]",
            "CLAUDE_CODE_MAX_RETRIES": "4",
            "API_TIMEOUT_MS": "300000",
            "CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS": "180000",
            "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1",
        }
    )

    def stderr_sink(line: str) -> None:
        with stderr_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            if not line.endswith("\n"):
                handle.write("\n")

    options = ClaudeAgentOptions(
        cwd=cwd,
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": system_prompt,
            "exclude_dynamic_sections": True,
        },
        setting_sources=["project"],
        tools=["Read", "Grep", "Glob", "Bash"],
        allowed_tools=["Read", "Grep", "Glob", "Bash"],
        disallowed_tools=["Write", "Edit", "WebFetch", "WebSearch", "Agent"],
        permission_mode="dontAsk",
        model=model,
        effort=cast(EffortLevel, effort),
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        output_format={"type": "json_schema", "schema": schema},
        env=environment,
        strict_mcp_config=True,
        mcp_servers={},
        sandbox=cast(
            SandboxSettings,
            {
                "enabled": True,
                "autoAllowBashIfSandboxed": True,
                "failIfUnavailable": True,
                "allowUnsandboxedCommands": False,
                "network": {
                    "allowedDomains": [],
                    "allowLocalBinding": False,
                    "allowAllUnixSockets": False,
                    "allowUnixSockets": [],
                },
            },
        ),
        stderr=stderr_sink,
        enable_file_checkpointing=False,
    )

    result_message: ResultMessage | None = None
    caught_error: str | None = None
    machine_limit = None
    try:
        async for message in query(prompt=prompt, options=options):
            with transcript.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(_message_to_json(message), default=str) + "\n")
            if type(message).__name__ == "RateLimitEvent":
                machine_limit = disposition_from_rate_limit_info(
                    getattr(message, "rate_limit_info", None),
                    quota_fallback_wait_seconds=config.quota_fallback_wait_seconds,
                    transient_retry_seconds=config.transient_retry_seconds,
                )
                if machine_limit is not None:
                    break
            if isinstance(message, ResultMessage):
                result_message = message
    except Exception as exc:  # noqa: BLE001
        caught_error = f"{type(exc).__name__}: {exc}"

    if machine_limit is not None:
        if machine_limit.kind == PauseKind.AUTHENTICATION:
            raise AuthenticationPause(machine_limit.message)
        raise QuotaLimitPause(machine_limit.as_record())

    stderr_text = stderr_path.read_text(encoding="utf-8") if stderr_path.exists() else ""
    terminal_reason = result_message.terminal_reason if result_message else ""
    errors = (
        json.dumps(getattr(result_message, "errors", None), default=str) if result_message else ""
    )
    disposition = classify_failure_texts(
        [
            ("exception", caught_error or ""),
            ("terminal_reason", terminal_reason or ""),
            ("result_errors", errors),
            ("stderr", stderr_text[-100_000:]),
        ],
        quota_fallback_wait_seconds=config.quota_fallback_wait_seconds,
        transient_retry_seconds=config.transient_retry_seconds,
    )
    if disposition is not None:
        if disposition.kind.value == "authentication":
            raise AuthenticationPause(disposition.message)
        raise QuotaLimitPause(disposition.as_record())
    if caught_error:
        raise RuntimeError(caught_error)
    if result_message is None:
        raise RuntimeError("Structured review returned no ResultMessage")
    if result_message.is_error or result_message.subtype != "success":
        raise RuntimeError(
            "Structured review failed: "
            f"subtype={result_message.subtype}, terminal_reason={result_message.terminal_reason}, "
            f"errors={errors}"
        )

    result = result_type.model_validate(result_message.structured_output)
    write_json(artifact_dir / "structured-result.json", result.model_dump(mode="json"))
    usage_payload = {
        "session_id": result_message.session_id,
        "total_cost_usd": float(result_message.total_cost_usd or 0.0),
        "num_turns": int(result_message.num_turns or 0),
        "duration_ms": int(result_message.duration_ms or 0),
        "usage": result_message.usage or {},
        "model_usage": result_message.model_usage or {},
    }
    write_json(artifact_dir / "usage.json", usage_payload)

    ledger.append(
        StageResult(
            task_id=task_id,
            run_id=run_id,
            role=role,
            attempt=1,
            model=model,
            verdict=Verdict.PASS,
            report=AgentReport(
                verdict=Verdict.PASS,
                summary="Structured read-only review completed.",
                evidence=[str(artifact_dir / "structured-result.json")],
            ),
            session_id=result_message.session_id,
            total_cost_usd=float(result_message.total_cost_usd or 0.0),
            num_turns=int(result_message.num_turns or 0),
            duration_ms=int(result_message.duration_ms or 0),
            usage=dict(result_message.usage or {}),
            model_usage=dict(result_message.model_usage or {}),
            terminal_reason=result_message.terminal_reason,
            artifact_dir=str(artifact_dir),
        )
    )
    return result
