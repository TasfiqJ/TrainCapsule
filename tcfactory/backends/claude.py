"""Subscription-only Claude adapter behind the backend-neutral contract."""

from __future__ import annotations

from datetime import UTC, datetime
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
from tcfactory.util import redact_sensitive


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

    async def run_stage(self, **kwargs: Any) -> Any:
        """Run the existing stage adapter without exposing provider objects to factory state."""

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

    @staticmethod
    def safe_exception(error: BaseException) -> RuntimeError:
        _ = error
        return RuntimeError(redact_sensitive(BackendRouteState.ROUTE_REFUSED.value))
