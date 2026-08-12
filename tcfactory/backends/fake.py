"""Deterministic contract-test backend; it never launches a model or network call."""

from __future__ import annotations

from datetime import UTC, datetime

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


class FakeBackend:
    def __init__(self, results: list[dict[str, object]] | None = None) -> None:
        self._results = list(results or [{}])
        self._sessions: dict[str, AgentSession] = {}
        self._requests: dict[str, AgentTaskRequest] = {}

    def capabilities(self) -> AgentCapabilityReport:
        return AgentCapabilityReport(
            backend="fake",
            structured_output=True,
            resume=True,
            cancellation=True,
            sandbox=True,
            network_denial=True,
            transcript_retention=TranscriptRetention.NONE,
            allowed_tools=["Read", "Bash"],
        )

    def start(self, request: AgentTaskRequest) -> AgentSession:
        ref = f"ASESS-FAKE-{len(self._sessions) + 1:04d}"
        session = AgentSession(
            session_ref=ref,
            backend="fake",
            request_id=request.request_id,
            state=SessionState.STARTED,
            started_at=datetime.now(UTC).isoformat(),
        )
        self._sessions[ref] = session
        self._requests[ref] = request
        return session

    def resume(self, session: AgentSession, handoff: Handoff) -> AgentRunResult:
        current = self._sessions.get(session.session_ref)
        if current is None:
            raise ValueError("unknown fake backend session")
        if current.state is SessionState.CANCELLED:
            raise ValueError("fake backend session was cancelled")
        output = self._results.pop(0) if self._results else {}
        completed = current.model_copy(update={"state": SessionState.COMPLETED})
        self._sessions[session.session_ref] = completed
        return AgentRunResult(
            session=completed,
            state=SessionState.COMPLETED,
            verdict=str(output.get("verdict", "pass")),
            structured_output=output,
            artifact_digests=handoff.artifact_digests,
            usage=self.usage_state(),
            redacted_summary="deterministic fake backend result",
        )

    def cancel(self, session: AgentSession) -> None:
        if session.session_ref not in self._sessions:
            raise ValueError("unknown fake backend session")
        self._sessions[session.session_ref] = session.model_copy(
            update={"state": SessionState.CANCELLED}
        )

    def usage_state(self) -> UsageState:
        return UsageState(
            route_state=BackendRouteState.AUTHENTICATED,
            subscription_capacity="fake-unlimited-no-cost",
            estimated_api_equivalent_usd=0.0,
            actual_charge_usd=0.0,
        )

    async def execute(self, request: AgentTaskRequest) -> AgentRunResult:
        """Execute one deterministic result without network, subprocesses, or a model."""

        session = self.start(request)
        output = self._results.pop(0) if self._results else {}
        completed = session.model_copy(update={"state": SessionState.COMPLETED})
        self._sessions[session.session_ref] = completed
        return AgentRunResult(
            session=completed,
            state=SessionState.COMPLETED,
            verdict=str(output.get("verdict", "pass")),
            structured_output=output,
            artifact_digests={},
            usage=self.usage_state(),
            redacted_summary="deterministic fake backend result",
        )
