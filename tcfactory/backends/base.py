"""Backend-neutral engineering-agent contract and export-safe records."""

from __future__ import annotations

import re
import shlex
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import Field, model_validator

from tcfactory.util import redact_sensitive
from tcfactory.v3.base import DIGEST_PATTERN, V3Model

_FORBIDDEN_PROMPT_MATERIAL = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._-]{8,}|(?:sk|ghp|github_pat|oauth)[-_][A-Za-z0-9._-]{8,}|"
    r"claude-oauth-token|\.config[/\\]traincapsule|TCF_PRIVATE_GATE_RUNNER|"
    r"(?:account|organization)[_-]?id\s*[:=]\s*\S+)"
)


class BackendRouteState(StrEnum):
    AUTHENTICATED = "AUTHENTICATED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    QUOTA_WAIT = "QUOTA_WAIT"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    TIMEOUT = "TIMEOUT"
    ROUTE_REFUSED = "ROUTE_REFUSED"


class SessionState(StrEnum):
    STARTED = "STARTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TranscriptRetention(StrEnum):
    NONE = "NONE"
    REDACTED_SUMMARY = "REDACTED_SUMMARY"


class ExecutionEvidenceMode(StrEnum):
    SIMULATION = "SIMULATION"
    CONTROLLED_VALIDATION = "CONTROLLED_VALIDATION"
    LIVE_VALIDATION = "LIVE_VALIDATION"
    EXTERNAL_VALIDATION = "EXTERNAL_VALIDATION"


class BackendTerminalDisposition(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    QUOTA_WAIT = "QUOTA_WAIT"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    CANCELLED = "CANCELLED"
    ROUTE_REFUSED = "ROUTE_REFUSED"


class BashCommandRule(V3Model):
    executable: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
    argument_prefix: list[str] = Field(alias="argumentPrefix", max_length=16)

    def permits(self, command: str) -> bool:
        try:
            arguments = shlex.split(command, posix=True)
        except ValueError:
            return False
        if not arguments or arguments[0] != self.executable:
            return False
        expected = self.argument_prefix
        return arguments[1 : 1 + len(expected)] == expected


class AgentCapabilityReport(V3Model):
    backend: str
    structured_output: bool
    resume: bool
    cancellation: bool
    sandbox: bool
    network_denial: bool
    transcript_retention: TranscriptRetention
    allowed_tools: list[str]
    overall_wall_clock_timeout: bool = False
    bash_argument_allowlist: bool = False
    durable_terminal_records: bool = False


class AgentTaskRequest(V3Model):
    request_id: str = Field(pattern=r"^AREQ-[A-Z0-9_-]+$")
    work_item_id: str
    role: str
    task_packet: dict[str, Any]
    source_context_manifest: dict[str, Any]
    allowed_paths: list[str] = Field(min_length=1, max_length=32)
    forbidden_paths: list[str] = Field(default_factory=list[str], max_length=64)
    network_policy: str = Field(pattern=r"^(DENY|ALLOWLIST)$")
    output_schema: dict[str, Any]
    controller_repo_root: str
    candidate_worktree: str
    artifact_root: str
    prompt: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    schema_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    context_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    source_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    max_turns: int = Field(ge=1, le=200)
    max_tokens: int = Field(ge=1000, le=250_000)
    max_cost_usd_equivalent: float = Field(ge=0, le=100)
    max_wall_time_seconds: int = Field(ge=1, le=14_400)
    allowed_tools: list[str] = Field(alias="tools")
    bash_allowlist: list[BashCommandRule] = Field(max_length=16)
    network_allowed: bool = False

    @model_validator(mode="after")
    def reject_secret_material(self) -> AgentTaskRequest:
        combined = (
            f"{self.prompt}\n{self.system_prompt}\n{self.candidate_worktree}\n"
            f"{self.artifact_root}\n{self.controller_repo_root}"
        )
        if _FORBIDDEN_PROMPT_MATERIAL.search(combined):
            raise ValueError("request contains credential, account, or controller-secret material")
        if self.network_allowed:
            raise ValueError("backend-neutral V3 requests deny network by default")
        if self.network_policy == "DENY" and self.network_allowed:
            raise ValueError("DENY network policy cannot enable network")
        if "Bash" in self.allowed_tools and not self.bash_allowlist:
            raise ValueError("Bash requires a non-empty executable/argument allowlist")
        if "Bash" not in self.allowed_tools and self.bash_allowlist:
            raise ValueError("Bash rules are invalid when the Bash tool is disabled")
        identities = [
            (rule.executable, tuple(rule.argument_prefix)) for rule in self.bash_allowlist
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("Bash executable/argument rules must be unique")
        return self

    def exportable_summary(self) -> dict[str, object]:
        """Return metadata only; prompts and local paths are never serialized."""

        return {
            "requestId": self.request_id,
            "workItemId": self.work_item_id,
            "role": self.role,
            "schemaDigest": self.schema_digest,
            "contextDigest": self.context_digest,
            "sourceDigest": self.source_digest,
            "maxTurns": self.max_turns,
            "maxTokens": self.max_tokens,
            "maxCostUsdEquivalent": self.max_cost_usd_equivalent,
            "maxWallTimeSeconds": self.max_wall_time_seconds,
            "networkPolicy": self.network_policy,
            "networkAllowed": False,
        }


class AgentSession(V3Model):
    session_ref: str = Field(pattern=r"^ASESS-[A-Z0-9_-]+$")
    backend: str
    request_id: str
    state: SessionState
    started_at: str


class Handoff(V3Model):
    schema_version: int = Field(default=3, ge=3, le=3)
    work_item_id: str
    lane: str
    milestone: str
    task_kind: str
    disposition: str
    decision_contribution: str
    source_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    context_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    candidate_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    candidate_manifest_digest: str | None = Field(default=None, pattern=DIGEST_PATTERN.pattern)
    next_authorized_transition: str
    artifact_digests: dict[str, str]
    findings: list[dict[str, Any]]
    attempts_remaining: int = Field(ge=0)
    circuit_breaker_state: str | None = None
    external_evidence_required: bool


class UsageState(V3Model):
    route_state: BackendRouteState
    subscription_capacity: str
    retry_at: str | None = None
    estimated_api_equivalent_usd: float = Field(default=0.0, ge=0)
    actual_charge_usd: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def subscription_only(self) -> UsageState:
        if self.actual_charge_usd != 0:
            raise ValueError("V3 backend usage may not fall back to paid metered execution")
        if self.route_state in {
            BackendRouteState.AUTH_EXPIRED,
            BackendRouteState.QUOTA_WAIT,
            BackendRouteState.INFRASTRUCTURE,
            BackendRouteState.TIMEOUT,
        } and not self.retry_at:
            raise ValueError("retryable backend route states require retryAt")
        return self


class AgentRunResult(V3Model):
    session: AgentSession
    state: SessionState
    verdict: str
    structured_output: dict[str, Any] | None = None
    artifact_digests: dict[str, str]
    usage: UsageState
    redacted_summary: str
    evidence_mode: ExecutionEvidenceMode
    terminal_disposition: BackendTerminalDisposition
    terminal_record_digest: str | None = Field(
        default=None, pattern=DIGEST_PATTERN.pattern
    )
    error_state: BackendRouteState | None = None

    @model_validator(mode="after")
    def export_safe(self) -> AgentRunResult:
        object.__setattr__(self, "redacted_summary", redact_sensitive(self.redacted_summary))
        if _FORBIDDEN_PROMPT_MATERIAL.search(self.redacted_summary):
            raise ValueError("run result summary contains forbidden secret material")
        if self.terminal_disposition is BackendTerminalDisposition.COMPLETED and (
            self.state is not SessionState.COMPLETED
        ):
            raise ValueError("COMPLETED disposition requires a completed session")
        if self.terminal_disposition is BackendTerminalDisposition.TIMEOUT:
            if self.state is not SessionState.FAILED:
                raise ValueError("TIMEOUT disposition requires a failed session")
            if self.terminal_record_digest is None:
                raise ValueError("TIMEOUT disposition requires a durable terminal record")
        retryable = {
            BackendTerminalDisposition.AUTH_EXPIRED: BackendRouteState.AUTH_EXPIRED,
            BackendTerminalDisposition.QUOTA_WAIT: BackendRouteState.QUOTA_WAIT,
            BackendTerminalDisposition.INFRASTRUCTURE: BackendRouteState.INFRASTRUCTURE,
            BackendTerminalDisposition.TIMEOUT: BackendRouteState.TIMEOUT,
        }
        expected_route = retryable.get(self.terminal_disposition)
        if expected_route is not None:
            if self.state is not SessionState.FAILED:
                raise ValueError("retryable backend disposition requires a failed session")
            if self.error_state is not expected_route:
                raise ValueError("backend disposition and route state do not match")
            if self.usage.route_state is not expected_route or not self.usage.retry_at:
                raise ValueError("retryable backend result requires a typed retryAt route")
            if self.terminal_record_digest is None:
                raise ValueError("retryable backend result requires a durable terminal record")
        return self


@runtime_checkable
class EngineeringAgentBackend(Protocol):
    def capabilities(self) -> AgentCapabilityReport: ...

    def start(self, request: AgentTaskRequest) -> AgentSession: ...

    def resume(self, session: AgentSession, handoff: Handoff) -> AgentRunResult: ...

    def cancel(self, session: AgentSession) -> None: ...

    def usage_state(self) -> UsageState: ...

    async def execute(self, request: AgentTaskRequest) -> AgentRunResult: ...
