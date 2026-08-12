"""Subscription-only Claude adapter behind the backend-neutral contract."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tcfactory.auth import assert_max_oauth_only, sanitized_agent_environment
from tcfactory.backends.base import (
    AgentCapabilityReport,
    AgentRunResult,
    AgentSession,
    AgentTaskRequest,
    BackendRouteState,
    Handoff,
    SessionState,
    TranscriptRetention,
    UsageState,
)
from tcfactory.config import load_factory_config, load_roles
from tcfactory.models import (
    FactoryConfig,
    RiskTier,
    RoleName,
    SecurityPolicy,
    Stage,
    TaskPacket,
)
from tcfactory.util import redact_sensitive, sha256_file, write_json
from tcfactory.v3.planning import V3TaskPacket


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
            resume=True,
            cancellation=True,
            sandbox=True,
            network_denial=True,
            transcript_retention=TranscriptRetention.REDACTED_SUMMARY,
            allowed_tools=["Read", "Glob", "Grep", "Bash"],
        )

    def start(self, request: AgentTaskRequest) -> AgentSession:
        if request.network_policy != "DENY" or request.network_allowed:
            raise ValueError("Claude V3 execution requires an explicit DENY network policy")
        state = self.credentials.state()
        if state is not BackendRouteState.AUTHENTICATED:
            raise RuntimeError(state.value)
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
        return UsageState(
            route_state=route,
            subscription_capacity=(
                "available" if route is BackendRouteState.AUTHENTICATED else "unavailable"
            ),
            estimated_api_equivalent_usd=0.0,
            actual_charge_usd=0.0,
        )

    async def execute(self, request: AgentTaskRequest) -> AgentRunResult:
        """Execute a V3 request through the existing SDK adapter behind this boundary."""

        session = self.start(request)
        repo_root = Path(request.controller_repo_root).resolve()
        worktree = Path(request.candidate_worktree).resolve()
        artifact_root = Path(request.artifact_root).resolve()
        packet = V3TaskPacket.model_validate(request.task_packet)
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
        self.require_execution_security(factory, compatibility_packet)
        roles = load_roles(repo_root / factory.roles_path)
        result_artifact = artifact_root / role.value
        result_artifact.mkdir(parents=True, exist_ok=True)
        try:
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
            )
            result_path = result_artifact / "backend-result.json"
            write_json(result_path, result.model_dump(mode="json"))
            completed = session.model_copy(
                update={
                    "state": (
                        SessionState.COMPLETED
                        if result.verdict.value == "pass"
                        else SessionState.FAILED
                    )
                }
            )
            self._sessions[session.session_ref] = completed
            return AgentRunResult(
                session=completed,
                state=completed.state,
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
                redacted_summary=redact_sensitive(
                    result.error or result.terminal_reason or result.verdict.value
                ),
            )
        except Exception:
            failed = session.model_copy(update={"state": SessionState.FAILED})
            self._sessions[session.session_ref] = failed
            return AgentRunResult(
                session=failed,
                state=SessionState.FAILED,
                verdict="blocked",
                structured_output=None,
                artifact_digests={},
                usage=self.usage_state(),
                redacted_summary="backend execution failed safely",
                error_state=BackendRouteState.ROUTE_REFUSED,
            )

    @staticmethod
    def safe_exception(error: BaseException) -> RuntimeError:
        _ = error
        return RuntimeError(redact_sensitive(BackendRouteState.ROUTE_REFUSED.value))
