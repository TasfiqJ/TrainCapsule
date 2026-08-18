from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tcfactory.backends import EngineeringAgentBackend
from tcfactory.backends.base import AgentTaskRequest
from tcfactory.backends.claude import ClaudeBackend
from tcfactory.backends.registry import resolve_executor_backend
from tcfactory.v3.configuration import ExecutorBackend, ExecutorConfig, load_executors_v3

ROOT = Path(__file__).resolve().parents[1]
DIGEST = "sha256:" + "0" * 64


def _configured_backend(**updates: object) -> ExecutorBackend:
    payload: dict[str, object] = {
        "adapter": "tcfactory.backends.claude.ClaudeBackend",
        "authentication": "subscription",
        "enabled": True,
        "maxConcurrentSessions": 2,
        "capabilities": [
            "repository_read",
            "bounded_repository_write",
            "deterministic_gate_execution",
        ],
        "durableStateOwnedByFactory": True,
    }
    payload.update(updates)
    return ExecutorBackend.model_validate(payload)


def _config(backend: ExecutorBackend | None = None) -> ExecutorConfig:
    return ExecutorConfig.model_validate(
        {
            "version": 3,
            "defaultBackend": "claude",
            "allowPaidUsage": False,
            "backends": {"claude": (backend or _configured_backend()).model_dump(by_alias=True)},
            "weeklyAllocationPercent": {"productImplementation": 100},
            "priorityUnderPressure": ["controlledProductCriticalPath"],
        }
    )


def _request(request_id: str) -> AgentTaskRequest:
    return AgentTaskRequest.model_validate(
        {
            "requestId": request_id,
            "workItemId": "V3-MIG-011",
            "role": "factory_repair",
            "taskPacket": {"workItemId": "V3-MIG-011"},
            "sourceContextManifest": {"version": 3},
            "allowedPaths": ["tcfactory/**"],
            "forbiddenPaths": ["config/**"],
            "networkPolicy": "DENY",
            "outputSchema": {"type": "object"},
            "controllerRepoRoot": str(ROOT),
            "candidateWorktree": str(ROOT),
            "artifactRoot": str(ROOT / ".test-artifacts"),
            "prompt": "Return a bounded result.",
            "systemPrompt": "Do not use network or secrets.",
            "schemaDigest": DIGEST,
            "contextDigest": DIGEST,
            "sourceDigest": DIGEST,
            "maxTurns": 1,
            "maxTokens": 1000,
            "maxCostUsdEquivalent": 0,
            "maxWallTimeSeconds": 1,
            "tools": ["Read"],
            "bashAllowlist": [],
            "networkAllowed": False,
        }
    )


def test_checked_in_executor_resolves_to_protocol_conformant_claude_adapter() -> None:
    configured = load_executors_v3(ROOT / "config/executors.yaml")
    backend = resolve_executor_backend(configured)

    assert isinstance(backend, EngineeringAgentBackend)
    assert isinstance(backend, ClaudeBackend)
    assert backend.capabilities().network_denial is True
    assert set(configured.backends["claude"].capabilities) == {
        "repository_read",
        "bounded_repository_write",
        "deterministic_gate_execution",
    }


def test_registry_rejects_unknown_disabled_and_misnamed_adapters() -> None:
    with pytest.raises(RuntimeError, match="not allowlisted"):
        resolve_executor_backend(
            _config(_configured_backend(adapter="example.invalid.Backend"))
        )

    disabled = _config().model_copy(
        update={
            "backends": {
                "claude": _configured_backend(enabled=False),
            }
        }
    )
    with pytest.raises(RuntimeError, match="disabled"):
        resolve_executor_backend(disabled)

    misnamed = _config().model_copy(
        update={
            "default_backend": "other",
            "backends": {"other": _configured_backend()},
        }
    )
    with pytest.raises(RuntimeError, match="does not match"):
        resolve_executor_backend(misnamed)


def test_registry_rejects_capability_drift_and_network_claim_is_absent() -> None:
    with pytest.raises(RuntimeError, match="capabilities do not match"):
        resolve_executor_backend(
            _config(_configured_backend(capabilities=["repository_read"]))
        )
    assert "web_research_when_policy_allows" not in load_executors_v3(
        ROOT / "config/executors.yaml"
    ).backends["claude"].capabilities


def test_claude_enforces_two_session_ceiling_and_releases_cancelled_slot() -> None:
    backend = ClaudeBackend(max_concurrent_sessions=2)
    first = backend.start(_request("AREQ-MIG011-001"))
    backend.start(_request("AREQ-MIG011-002"))
    with pytest.raises(RuntimeError, match="concurrent-session limit"):
        backend.start(_request("AREQ-MIG011-003"))

    backend.cancel(first)
    replacement = backend.start(_request("AREQ-MIG011-004"))
    assert replacement.request_id == "AREQ-MIG011-004"


def test_execute_releases_slot_when_pre_terminal_validation_fails() -> None:
    backend = ClaudeBackend(max_concurrent_sessions=1)
    with pytest.raises(ValueError):
        asyncio.run(backend.execute(_request("AREQ-MIG011-FAIL")))

    replacement = backend.start(_request("AREQ-MIG011-AFTER"))
    assert replacement.request_id == "AREQ-MIG011-AFTER"
