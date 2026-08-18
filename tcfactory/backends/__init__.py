"""TrainCapsule backend-neutral executor adapters."""

from tcfactory.backends.base import (
    AgentCapabilityReport,
    AgentRunResult,
    AgentSession,
    AgentTaskRequest,
    BackendRouteState,
    BackendTerminalDisposition,
    BashCommandRule,
    EngineeringAgentBackend,
    ExecutionEvidenceMode,
    Handoff,
    SessionState,
    UsageState,
)
from tcfactory.backends.claude import ClaudeBackend, ClaudeCredentialProvider
from tcfactory.backends.fake import FakeBackend
from tcfactory.backends.registry import resolve_executor_backend

__all__ = [
    "AgentCapabilityReport",
    "AgentRunResult",
    "AgentSession",
    "AgentTaskRequest",
    "BackendRouteState",
    "BackendTerminalDisposition",
    "BashCommandRule",
    "ClaudeBackend",
    "ClaudeCredentialProvider",
    "EngineeringAgentBackend",
    "ExecutionEvidenceMode",
    "FakeBackend",
    "Handoff",
    "SessionState",
    "UsageState",
    "resolve_executor_backend",
]
