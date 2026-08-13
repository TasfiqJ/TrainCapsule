from __future__ import annotations

import asyncio
import json
import shlex
from pathlib import Path
from typing import Any, TypeVar, cast

from claude_agent_sdk import EffortLevel, SandboxSettings
from pydantic import BaseModel

from .auth import sanitized_agent_environment
from .backends.base import (
    AgentTaskRequest,
    BackendRouteState,
    BashCommandRule,
    EngineeringAgentBackend,
    Handoff,
    SessionState,
)
from .backends.claude import ClaudeCredentialProvider
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
from .util import redact_sensitive, write_json
from .v3.base import sha256_digest

T = TypeVar("T", bound=BaseModel)


DEFAULT_BASH_ALLOWLIST = (
    "git status",
    "git diff",
    "git show",
    "python -m pytest",
    "uv run pytest",
)


def validate_bash_command(command: str, allowlist: list[str]) -> None:
    normalized = " ".join(command.split())
    if any(marker in normalized for marker in (";", "&&", "||", "`", "$(")):
        raise ValueError("compound or substituting Bash commands are forbidden")
    rules = [_bash_rule(item) for item in allowlist]
    if not any(rule.permits(normalized) for rule in rules):
        raise ValueError(f"Bash command is outside the explicit allowlist: {normalized}")


def _bash_rule(command: str) -> BashCommandRule:
    arguments = shlex.split(command, posix=True)
    if not arguments:
        raise ValueError("Bash allowlist command cannot be empty")
    return BashCommandRule(executable=arguments[0], argumentPrefix=arguments[1:])


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
    backend: EngineeringAgentBackend | None = None,
    max_wall_time_seconds: int = 1800,
    bash_allowlist: list[str] | None = None,
) -> T:
    """Run one fresh, read-only Claude session and enforce structured output.

    The caller supplies a disposable Git worktree as ``cwd``. The session never resumes
    another chat. Quota messages are classified into a durable pause that the autopilot can
    sleep through and retry later.
    """

    if max_wall_time_seconds <= 0 or max_wall_time_seconds > 14_400:
        raise ValueError("structured review wall time must be finite and <= 14400 seconds")
    allowed_bash: list[str] = (
        list(DEFAULT_BASH_ALLOWLIST) if bash_allowlist is None else bash_allowlist
    )
    schema_digest = sha256_digest(
        (json.dumps(schema, separators=(",", ":"), sort_keys=True) + "\n").encode()
    )
    if backend is not None:
        request = AgentTaskRequest(
            request_id=f"AREQ-{run_id.upper().replace('-', '_')}-{role.value.upper()}",
            work_item_id=task_id,
            role=role.value,
            task_packet={"taskId": task_id, "role": role.value, "readOnly": True},
            source_context_manifest={
                "sourceDigest": sha256_digest(system_prompt.encode()),
                "contextDigest": sha256_digest(prompt.encode()),
            },
            allowed_paths=["**"],
            forbidden_paths=["**"],
            network_policy="DENY",
            output_schema=schema,
            controller_repo_root=str(cwd.resolve()),
            candidate_worktree=str(cwd.resolve()),
            artifact_root=str(artifact_dir.resolve()),
            prompt=prompt,
            system_prompt=system_prompt,
            schema_digest=schema_digest,
            context_digest=sha256_digest(prompt.encode()),
            source_digest=sha256_digest(system_prompt.encode()),
            max_turns=max_turns,
            max_tokens=max(1000, max_turns * 1500),
            max_cost_usd_equivalent=max_budget_usd,
            max_wall_time_seconds=max_wall_time_seconds,
            tools=[
                "Read",
                "Grep",
                "Glob",
                *(["Bash"] if allowed_bash else []),
            ],
            bash_allowlist=[_bash_rule(command) for command in allowed_bash],
            network_allowed=False,
        )
        session = backend.start(request)
        handoff = Handoff(
            work_item_id=task_id,
            lane="TRUST",
            milestone="LEGACY_STRUCTURED_REVIEW",
            task_kind="RESEARCH",
            disposition="KEEP",
            decision_contribution="Produce the bounded structured review result.",
            source_digest=request.source_digest,
            context_digest=request.context_digest,
            candidate_sha="0" * 40,
            next_authorized_transition="COMPLETE_REVIEW",
            artifact_digests={},
            findings=[],
            attempts_remaining=0,
            external_evidence_required=False,
        )
        run_result = backend.resume(session, handoff)
        if run_result.state is not SessionState.COMPLETED:
            raise RuntimeError((run_result.error_state or BackendRouteState.ROUTE_REFUSED).value)
        result = result_type.model_validate(run_result.structured_output)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        write_json(artifact_dir / "structured-result.json", result.model_dump(mode="json"))
        write_json(artifact_dir / "usage.json", run_result.usage.model_dump(mode="json"))
        write_json(artifact_dir / "request-summary.json", request.exportable_summary())
        return result

    credential_state = ClaudeCredentialProvider(require_long_lived_token=True).state()
    if credential_state is not BackendRouteState.AUTHENTICATED:
        raise AuthenticationPause(credential_state.value)
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
    except ImportError as exc:
        raise RuntimeError("claude-agent-sdk is not installed") from exc

    ledger = Ledger(config.resolve(repo_root, config.ledger_path), config.monthly_budget_usd)
    ledger.assert_budget(max_budget_usd)
    effective_turns = min(max_turns, 200)
    effective_budget = max_budget_usd

    artifact_dir.mkdir(parents=True, exist_ok=True)
    transcript = artifact_dir / "transcript-summary.json"
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
            handle.write(redact_sensitive(line))
            if not line.endswith("\n"):
                handle.write("\n")

    options = ClaudeAgentOptions(
        cwd=cwd,
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": (
                system_prompt
                + "\n\nBash is restricted to these command prefixes: "
                + ", ".join(allowed_bash)
            ),
            "exclude_dynamic_sections": True,
        },
        setting_sources=["project"],
        tools=["Read", "Grep", "Glob", *(["Bash"] if allowed_bash else [])],
        allowed_tools=["Read", "Grep", "Glob", *(["Bash"] if allowed_bash else [])],
        disallowed_tools=["Write", "Edit", "WebFetch", "WebSearch", "Agent"],
        permission_mode="dontAsk",
        model=model,
        effort=cast(EffortLevel, effort),
        max_turns=effective_turns,
        max_budget_usd=effective_budget,
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
    message_counts: dict[str, int] = {}
    try:
        async with asyncio.timeout(max_wall_time_seconds):
            async for message in query(prompt=prompt, options=options):
                message_type = type(message).__name__
                message_counts[message_type] = message_counts.get(message_type, 0) + 1
                if message_type == "RateLimitEvent":
                    machine_limit = disposition_from_rate_limit_info(
                        getattr(message, "rate_limit_info", None),
                        quota_fallback_wait_seconds=config.quota_fallback_wait_seconds,
                        transient_retry_seconds=config.transient_retry_seconds,
                    )
                    if machine_limit is not None:
                        break
                if isinstance(message, ResultMessage):
                    result_message = message
    except TimeoutError:
        caught_error = "structured review exceeded its finite wall-time ceiling"
    except Exception as exc:  # noqa: BLE001
        caught_error = f"{type(exc).__name__}: {redact_sensitive(str(exc))}"
    write_json(
        transcript,
        {
            "retention": "REDACTED_SUMMARY",
            "messageTypes": message_counts,
            "promptStored": False,
            "sdkMessagesStored": False,
        },
    )

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
    backend_session_ref = (
        "ASESS-CLAUDE-"
        + sha256_digest(str(result_message.session_id).encode()).split(":", 1)[1][:16].upper()
    )
    usage_payload = {
        "backend_session_ref": backend_session_ref,
        "estimated_api_equivalent_usd": float(result_message.total_cost_usd or 0.0),
        "actual_subscription_charge_usd": 0.0,
        "num_turns": int(result_message.num_turns or 0),
        "duration_ms": int(result_message.duration_ms or 0),
        "route_state": BackendRouteState.AUTHENTICATED.value,
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
            session_id=backend_session_ref,
            total_cost_usd=float(result_message.total_cost_usd or 0.0),
            num_turns=int(result_message.num_turns or 0),
            duration_ms=int(result_message.duration_ms or 0),
            usage={},
            model_usage={},
            terminal_reason=result_message.terminal_reason,
            artifact_dir=str(artifact_dir),
        )
    )
    return result
