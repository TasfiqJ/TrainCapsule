"""Subscription-only Claude adapter behind the backend-neutral contract."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tcfactory.auth import assert_max_oauth_only, sanitized_agent_environment
from tcfactory.backends.base import (
    AgentCapabilityReport,
    AgentRunResult,
    AgentSession,
    AgentTaskRequest,
    BackendRouteState,
    BackendTerminalDisposition,
    ExecutionEvidenceMode,
    Handoff,
    SessionState,
    TranscriptRetention,
    UsageState,
)
from tcfactory.claude_runner import expire_redacted_event_summaries
from tcfactory.config import load_factory_config, load_roles
from tcfactory.models import (
    FactoryConfig,
    RiskTier,
    RoleName,
    SecurityPolicy,
    Stage,
    TaskPacket,
)
from tcfactory.quota import AuthenticationPause, QuotaLimitPause
from tcfactory.util import redact_sensitive, sha256_file, write_json
from tcfactory.v3.base import V3Model
from tcfactory.v3.planning import V3TaskPacket


def validate_planning_packet(request: AgentTaskRequest) -> V3TaskPacket:
    from tcfactory.v3.task_compiler_v31 import CompiledTaskContractV31

    payload = dict(request.task_packet)
    contract_payload = payload.pop("taskContract", None)
    packet = V3TaskPacket.model_validate(payload)
    if contract_payload is None:
        return packet
    contract = CompiledTaskContractV31.model_validate_json(
        json.dumps(contract_payload, sort_keys=True, separators=(",", ":"))
    )
    if (
        contract.work_item_id != request.work_item_id
        or contract.work_item_id != packet.work_item_id
        or contract.task_packet_digest != packet.canonical_digest()
        or contract.source_digest != request.source_digest
        or contract.context_digest != request.context_digest
    ):
        raise ValueError("compiled task contract does not bind the backend request")
    return packet


class ClaudeCredentialProvider:
    """Keep Claude credentials controller-private and expose only route state."""

    def __init__(self, *, require_long_lived_token: bool = False) -> None:
        self.require_long_lived_token = require_long_lived_token

    def state(self) -> BackendRouteState:
        try:
            assert_max_oauth_only(require_long_lived_token=self.require_long_lived_token)
        except RuntimeError:
            return BackendRouteState.AUTH_EXPIRED
        return BackendRouteState.AUTHENTICATED

    def sdk_environment(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Return the private SDK environment; callers must never serialize it."""

        if self.state() is not BackendRouteState.AUTHENTICATED:
            raise RuntimeError(BackendRouteState.AUTH_EXPIRED.value)
        return sanitized_agent_environment(extra)


class BackendTerminalRecord(V3Model):
    request_id: str
    session_ref: str
    state: SessionState
    disposition: BackendTerminalDisposition
    evidence_mode: ExecutionEvidenceMode
    redacted_summary: str
    retry_at: datetime | None = None
    completed_at: datetime


def load_backend_terminal_record(
    path: Path,
    *,
    expected_digest: str,
    expected_request_id: str | None = None,
    expected_session_ref: str | None = None,
) -> BackendTerminalRecord:
    """Load a terminal record only when its bytes and identity remain bound."""

    if path.is_symlink() or not path.is_file():
        raise RuntimeError("backend terminal record is missing or untrusted")
    actual_digest = f"sha256:{sha256_file(path)}"
    if actual_digest != expected_digest:
        raise RuntimeError("backend terminal record digest mismatch")
    try:
        record = BackendTerminalRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("backend terminal record is invalid") from exc
    if expected_request_id is not None and record.request_id != expected_request_id:
        raise RuntimeError("backend terminal record request mismatch")
    if expected_session_ref is not None and record.session_ref != expected_session_ref:
        raise RuntimeError("backend terminal record session mismatch")
    return record


class ClaudeBackend:
    def __init__(self, credentials: ClaudeCredentialProvider | None = None) -> None:
        self.credentials = credentials or ClaudeCredentialProvider()
        self._sessions: dict[str, AgentSession] = {}
        self._requests: dict[str, AgentTaskRequest] = {}
        self._counter = 0

    def capabilities(self) -> AgentCapabilityReport:
        return AgentCapabilityReport(
            backend="claude",
            structured_output=True,
            resume=False,
            cancellation=False,
            sandbox=True,
            network_denial=True,
            transcript_retention=TranscriptRetention.REDACTED_SUMMARY,
            allowed_tools=["Read", "Glob", "Grep", "Write", "Edit", "Bash"],
            overall_wall_clock_timeout=True,
            bash_argument_allowlist=True,
            durable_terminal_records=True,
        )

    def start(self, request: AgentTaskRequest) -> AgentSession:
        if request.network_policy != "DENY" or request.network_allowed:
            raise ValueError("Claude V3 execution requires an explicit DENY network policy")
        unsupported_tools = set(request.allowed_tools) - set(self.capabilities().allowed_tools)
        if unsupported_tools:
            names = ", ".join(sorted(unsupported_tools))
            raise ValueError(f"Claude V3 execution rejects unsupported tools: {names}")
        self._counter += 1
        session = AgentSession(
            session_ref=f"ASESS-CLAUDE-{self._counter:04d}",
            backend="claude",
            request_id=request.request_id,
            state=SessionState.STARTED,
            started_at=datetime.now(UTC).isoformat(),
        )
        self._sessions[session.session_ref] = session
        self._requests[session.session_ref] = request
        return session

    def resume(self, session: AgentSession, handoff: Handoff) -> AgentRunResult:
        """Refuse implicit SDK execution; ``run_stage`` is the async legacy adapter."""

        if session.session_ref not in self._sessions:
            raise ValueError("unknown Claude backend session")
        return AgentRunResult(
            session=session,
            state=SessionState.FAILED,
            verdict="blocked",
            artifact_digests=handoff.artifact_digests,
            usage=self.usage_state(),
            redacted_summary="Claude execution requires the async run_stage adapter.",
            evidence_mode=ExecutionEvidenceMode.LIVE_VALIDATION,
            terminal_disposition=BackendTerminalDisposition.ROUTE_REFUSED,
            error_state=BackendRouteState.ROUTE_REFUSED,
        )

    @staticmethod
    def require_execution_security(config: FactoryConfig, task: TaskPacket) -> None:
        if not config.sandbox_enabled:
            raise RuntimeError("Claude V3 execution requires the sandbox")
        if config.unsandbox_mutating_roles or task.security.allow_unsandboxed_commands:
            raise RuntimeError("Claude V3 execution forbids unsandboxed commands")
        if task.security.network_default != "deny":
            raise RuntimeError("Claude V3 execution requires network-default deny")
        if not task.security.fail_if_sandbox_unavailable:
            raise RuntimeError("Claude V3 execution must fail when the sandbox is unavailable")

    async def run_stage(self, **kwargs: Any) -> Any:
        """Run the existing stage adapter without exposing provider objects to factory state."""

        config = kwargs.get("config")
        task = kwargs.get("task")
        if not isinstance(config, FactoryConfig) or not isinstance(task, TaskPacket):
            raise RuntimeError("Claude stage requires typed factory and task security policy")
        self.require_execution_security(config, task)
        from tcfactory.claude_runner import run_agent_stage

        return await run_agent_stage(**kwargs)

    def cancel(self, session: AgentSession) -> None:
        current = self._sessions.get(session.session_ref)
        if current is None:
            raise ValueError("unknown Claude backend session")
        self._sessions[session.session_ref] = current.model_copy(
            update={"state": SessionState.CANCELLED}
        )

    def usage_state(self) -> UsageState:
        route = self.credentials.state()
        retry_at = (
            (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
            if route is not BackendRouteState.AUTHENTICATED
            else None
        )
        return UsageState(
            route_state=route,
            subscription_capacity=(
                "available" if route is BackendRouteState.AUTHENTICATED else "unavailable"
            ),
            retry_at=retry_at,
            estimated_api_equivalent_usd=0.0,
            actual_charge_usd=0.0,
        )

    async def execute(self, request: AgentTaskRequest) -> AgentRunResult:
        """Execute a V3 request through the existing SDK adapter behind this boundary."""

        session = self.start(request)
        repo_root = Path(request.controller_repo_root).resolve()
        worktree = Path(request.candidate_worktree).resolve()
        artifact_root = Path(request.artifact_root).resolve()
        expire_redacted_event_summaries(artifact_root)
        packet = validate_planning_packet(request)
        role = RoleName(request.role)
        stage = Stage(
            role=role,
            max_turns=request.max_turns,
            max_budget_usd=request.max_cost_usd_equivalent or 0.01,
            task_budget_tokens=request.max_tokens,
            tools=request.allowed_tools,
            allowed_paths=request.allowed_paths,
            forbidden_paths=request.forbidden_paths,
            read_only=role
            in {
                RoleName.ADVERSARY,
                RoleName.AUDIT,
                RoleName.SECURITY,
                RoleName.INTEGRATION_SCOUT,
                RoleName.RELEASE,
            },
        )
        risk = {
            "MECHANICAL": RiskTier.MECHANICAL,
            "STANDARD": RiskTier.STANDARD,
            "INTEGRATION": RiskTier.INTEGRATION,
            "TRUST_CORE": RiskTier.TRUST_CORE,
            "EXTERNAL": RiskTier.TRUST_CORE,
        }[packet.risk_tier.value]
        compatibility_packet = TaskPacket(
            task_id=packet.work_item_id,
            title=packet.title,
            phase=packet.milestone,
            goal=packet.goal,
            decision_contribution=packet.decision_contribution,
            oracle=packet.oracle,
            rollback=packet.rollback,
            source_of_truth=packet.source_documents,
            depends_on=[],
            non_goals=packet.non_goals,
            acceptance_criteria=packet.acceptance_criteria,
            outputs=packet.outputs,
            stop_conditions=packet.stop_conditions,
            pipeline=[stage],
            risk_tier=risk,
            remote_ci_required=True,
            github_push=True,
            task_budget_usd=max(request.max_cost_usd_equivalent, 0.01),
            auto_merge=False,
            security=SecurityPolicy(
                network_default="deny",
                allow_unsandboxed_commands=False,
                fail_if_sandbox_unavailable=True,
            ),
        )
        factory = load_factory_config(repo_root / "config/factory.yaml")
        # The controller repository is a signed, read-only source snapshot.  Legacy
        # Claude runner defaults put operational journals below ``factory/`` in the
        # repository, so scope those mutable paths to this controller-owned artifact
        # root before invoking the runner.  Absolute paths preserve the runner's
        # existing resolution behavior while keeping candidate source and authority
        # material immutable.
        runtime_root = artifact_root / "backend-runtime"
        factory = factory.model_copy(
            update={
                "peer_message_dir": str(runtime_root / "messages"),
                "heartbeat_path": str(runtime_root / "heartbeat.json"),
                "event_log_path": str(runtime_root / "events.jsonl"),
            }
        )
        self.require_execution_security(factory, compatibility_packet)
        roles = load_roles(repo_root / factory.roles_path)
        result_artifact = artifact_root / role.value
        result_artifact.mkdir(parents=True, exist_ok=True)
        terminal_path = result_artifact / "backend-terminal.json"

        def terminal_result(
            *,
            state: SessionState,
            disposition: BackendTerminalDisposition,
            summary: str,
            verdict: str = "blocked",
            structured_output: dict[str, object] | None = None,
            artifact_digests: dict[str, str] | None = None,
            usage: UsageState | None = None,
            error_state: BackendRouteState | None = None,
            retry_at: datetime | None = None,
        ) -> AgentRunResult:
            safe_summary = redact_sensitive(summary)
            terminal = BackendTerminalRecord(
                request_id=request.request_id,
                session_ref=session.session_ref,
                state=state,
                disposition=disposition,
                evidence_mode=ExecutionEvidenceMode.LIVE_VALIDATION,
                redacted_summary=safe_summary,
                retry_at=retry_at,
                completed_at=datetime.now(UTC),
            )
            write_json(terminal_path, terminal.model_dump(mode="json", by_alias=True))
            completed_session = session.model_copy(update={"state": state})
            self._sessions[session.session_ref] = completed_session
            digest = f"sha256:{sha256_file(terminal_path)}"
            return AgentRunResult(
                session=completed_session,
                state=state,
                verdict=verdict,
                structured_output=structured_output,
                artifact_digests={
                    **(artifact_digests or {}),
                    f"{role.value}/backend-terminal.json": digest,
                },
                usage=usage or self.usage_state(),
                redacted_summary=safe_summary,
                evidence_mode=ExecutionEvidenceMode.LIVE_VALIDATION,
                terminal_disposition=disposition,
                terminal_record_digest=digest,
                error_state=error_state,
            )
        route = self.credentials.state()
        if route is not BackendRouteState.AUTHENTICATED:
            retry_at = datetime.now(UTC) + timedelta(minutes=5)
            return terminal_result(
                state=SessionState.FAILED,
                disposition=BackendTerminalDisposition.AUTH_EXPIRED,
                summary="backend authentication route is unavailable",
                error_state=BackendRouteState.AUTH_EXPIRED,
                retry_at=retry_at,
                usage=UsageState(
                    route_state=BackendRouteState.AUTH_EXPIRED,
                    subscription_capacity="unavailable",
                    retry_at=retry_at.isoformat(),
                ),
            )
        try:
            async with asyncio.timeout(request.max_wall_time_seconds):
                result = await self.run_stage(
                    repo_root=repo_root,
                    worktree=worktree,
                    config=factory,
                    task=compatibility_packet,
                    stage=stage,
                    role_config=roles[role],
                    global_prompt_path=factory.global_prompt,
                    run_id=request.request_id.lower(),
                    attempt=1,
                    artifact_dir=result_artifact,
                    base_sha=packet.base_sha,
                    system_prompt_override=request.system_prompt,
                    task_prompt_override=request.prompt,
                    bash_allowlist=request.bash_allowlist,
                    strict_tool_allowlist=True,
                )
            result_path = result_artifact / "backend-result.json"
            write_json(result_path, result.model_dump(mode="json"))
            completed_state = (
                SessionState.COMPLETED
                if result.verdict.value == "pass"
                else SessionState.FAILED
            )
            return terminal_result(
                state=completed_state,
                disposition=(
                    BackendTerminalDisposition.COMPLETED
                    if completed_state is SessionState.COMPLETED
                    else BackendTerminalDisposition.FAILED
                ),
                verdict=result.verdict.value,
                structured_output=result.model_dump(mode="json"),
                artifact_digests={
                    f"{role.value}/backend-result.json": f"sha256:{sha256_file(result_path)}"
                },
                usage=UsageState(
                    route_state=BackendRouteState.AUTHENTICATED,
                    subscription_capacity="subscription",
                    estimated_api_equivalent_usd=result.total_cost_usd,
                    actual_charge_usd=0.0,
                ),
                summary=result.error or result.terminal_reason or result.verdict.value,
            )
        except QuotaLimitPause as exc:
            retry_at = exc.record.resume_at
            return terminal_result(
                state=SessionState.FAILED,
                disposition=BackendTerminalDisposition.QUOTA_WAIT,
                summary="subscription capacity is temporarily unavailable",
                error_state=BackendRouteState.QUOTA_WAIT,
                retry_at=retry_at,
                usage=UsageState(
                    route_state=BackendRouteState.QUOTA_WAIT,
                    subscription_capacity="unavailable",
                    retry_at=retry_at.isoformat(),
                ),
            )
        except AuthenticationPause:
            retry_at = datetime.now(UTC) + timedelta(minutes=5)
            return terminal_result(
                state=SessionState.FAILED,
                disposition=BackendTerminalDisposition.AUTH_EXPIRED,
                summary="backend authentication expired during execution",
                error_state=BackendRouteState.AUTH_EXPIRED,
                retry_at=retry_at,
                usage=UsageState(
                    route_state=BackendRouteState.AUTH_EXPIRED,
                    subscription_capacity="unavailable",
                    retry_at=retry_at.isoformat(),
                ),
            )
        except TimeoutError:
            retry_at = datetime.now(UTC) + timedelta(minutes=2)
            return terminal_result(
                state=SessionState.FAILED,
                disposition=BackendTerminalDisposition.TIMEOUT,
                summary="backend overall wall-clock deadline exceeded",
                error_state=BackendRouteState.TIMEOUT,
                retry_at=retry_at,
                usage=UsageState(
                    route_state=BackendRouteState.TIMEOUT,
                    subscription_capacity="unknown",
                    retry_at=retry_at.isoformat(),
                ),
            )
        except Exception:
            retry_at = datetime.now(UTC) + timedelta(minutes=2)
            return terminal_result(
                state=SessionState.FAILED,
                disposition=BackendTerminalDisposition.INFRASTRUCTURE,
                summary="backend execution failed safely",
                error_state=BackendRouteState.INFRASTRUCTURE,
                retry_at=retry_at,
                usage=UsageState(
                    route_state=BackendRouteState.INFRASTRUCTURE,
                    subscription_capacity="unknown",
                    retry_at=retry_at.isoformat(),
                ),
            )

    @staticmethod
    def safe_exception(error: BaseException) -> RuntimeError:
        _ = error
        return RuntimeError(redact_sensitive(BackendRouteState.ROUTE_REFUSED.value))
