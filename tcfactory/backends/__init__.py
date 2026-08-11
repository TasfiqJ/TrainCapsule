"""TrainCapsule backend-neutral executor adapters."""

from tcfactory.backends.base import (
    AgentCapabilityReport,
    AgentRunResult,
    AgentSession,
    AgentTaskRequest,
    BackendRouteState,
    EngineeringAgentBackend,
    Handoff,
    SessionState,
    UsageState,
)
from tcfactory.backends.claude import ClaudeBackend, ClaudeCredentialProvider
from tcfactory.backends.fake import FakeBackend

__all__ = [
    "AgentCapabilityReport",
    "AgentRunResult",
    "AgentSession",
    "AgentTaskRequest",
    "BackendRouteState",
    "ClaudeBackend",
    "ClaudeCredentialProvider",
    "EngineeringAgentBackend",
    "FakeBackend",
    "Handoff",
    "SessionState",
    "UsageState",
]
