from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tcfactory.backends.base import (
    AgentTaskRequest,
    BackendRouteState,
    BackendTerminalDisposition,
    BashCommandRule,
)
from tcfactory.backends.claude import (
    ClaudeBackend,
    ClaudeCredentialProvider,
    load_backend_terminal_record,
    validate_planning_packet,
)
from tcfactory.backends.fake import FakeBackend
from tcfactory.claude_runner import (
    expire_redacted_event_summaries,
    redacted_event_summary,
    resolve_sdk_tools,
)
from tcfactory.models import PauseKind, QuotaPauseRecord
from tcfactory.quota import QuotaLimitPause
from tcfactory.v3.enums import Lane, RiskTier, WorkKind
from tcfactory.v3.planning import V3TaskPacket
from tcfactory.v3.task_compiler_v31 import compile_task_contract_v31
from tcfactory.v3.work_items import WorkItemCollection
from tcfactory.yamlutil import load_yaml

ROOT = Path(__file__).resolve().parents[1]
DIGEST = "sha256:" + "0" * 64


def _packet() -> V3TaskPacket:
    return V3TaskPacket(
        work_item_id="V3-MIG-001",
        title="Backend timeout fixture",
        lane=Lane.FACTORY,
        milestone="M0_FACTORY_MIGRATED",
        kind=WorkKind.MIGRATION,
        risk_tier=RiskTier.MECHANICAL,
        template="bounded",
        goal="Prove a bounded backend policy.",
        decision_contribution="One backend-boundary decision.",
        non_goals=["Do not use a model or network."],
        acceptance_criteria=["A typed terminal record is durable."],
        outputs=[],
        source_documents=["config/factory.yaml"],
        allowed_paths=["tcfactory/**"],
        forbidden_paths=["config/**"],
        oracle="Deterministic local test.",
        rollback="Delete disposable test artifacts.",
        stop_conditions=["Stop at the wall-clock deadline."],
        stop_disposition="TIMEOUT",
        work_item_digest=DIGEST,
        source_digest=DIGEST,
        context_digest=DIGEST,
        compiler_digest=DIGEST,
        base_sha="0" * 40,
    )


def _request(tmp_path: Path, **updates: object) -> AgentTaskRequest:
    payload: dict[str, object] = {
        "requestId": "AREQ-BACKEND-TIMEOUT",
        "workItemId": "V3-MIG-001",
        "role": "factory_repair",
        "taskPacket": _packet().model_dump(mode="json", by_alias=True),
        "sourceContextManifest": {"version": 3},
        "allowedPaths": ["tcfactory/**"],
        "forbiddenPaths": ["config/**"],
        "networkPolicy": "DENY",
        "outputSchema": {"type": "object"},
        "controllerRepoRoot": str(ROOT),
        "candidateWorktree": str(ROOT),
        "artifactRoot": str(tmp_path),
        "prompt": "Return the bounded structured result.",
        "systemPrompt": "Do not use network or secrets.",
        "schemaDigest": DIGEST,
        "contextDigest": DIGEST,
        "sourceDigest": DIGEST,
        "maxTurns": 2,
        "maxTokens": 2000,
        "maxCostUsdEquivalent": 0,
        "maxWallTimeSeconds": 1,
        "tools": ["Read"],
        "bashAllowlist": [],
        "networkAllowed": False,
    }
    payload.update(updates)
    return AgentTaskRequest.model_validate(payload)


def test_claude_accepts_exact_compiled_task_contract_envelope(tmp_path: Path) -> None:
    packet = _packet()
    collection = WorkItemCollection.model_validate(
        load_yaml(ROOT / "factory/roadmap/work_items.yaml")
    )
    contract = compile_task_contract_v31(
        collection.item("V3-MIG-001"),
        task_packet_digest=packet.canonical_digest(),
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_digest=packet.source_digest,
        context_digest=packet.context_digest,
    )
    task_packet = packet.model_dump(mode="json", by_alias=True)
    task_packet["taskContract"] = contract.model_dump(mode="json", by_alias=True)
    request = _request(tmp_path, taskPacket=task_packet)

    assert validate_planning_packet(request) == packet


def test_claude_rejects_mismatched_compiled_task_contract_envelope(
    tmp_path: Path,
) -> None:
    packet = _packet()
    collection = WorkItemCollection.model_validate(
        load_yaml(ROOT / "factory/roadmap/work_items.yaml")
    )
    contract = compile_task_contract_v31(
        collection.item("V3-MIG-001"),
        task_packet_digest=packet.canonical_digest(),
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_digest=packet.source_digest,
        context_digest=packet.context_digest,
    )
    task_packet = packet.model_dump(mode="json", by_alias=True)
    task_packet["taskContract"] = contract.model_dump(mode="json", by_alias=True)
    request = _request(tmp_path, taskPacket=task_packet, contextDigest="sha256:" + "1" * 64)

    with pytest.raises(ValueError, match="does not bind"):
        validate_planning_packet(request)


def _authenticated_backend(monkeypatch: pytest.MonkeyPatch) -> ClaudeBackend:
    provider = ClaudeCredentialProvider()
    monkeypatch.setattr(provider, "state", lambda: BackendRouteState.AUTHENTICATED)
    return ClaudeBackend(provider)


def test_capabilities_do_not_claim_non_durable_resume_or_cancellation() -> None:
    claude = ClaudeBackend()
    report = claude.capabilities()
    assert report.resume is False
    assert report.cancellation is False
    assert report.overall_wall_clock_timeout is True
    assert report.bash_argument_allowlist is True
    assert report.durable_terminal_records is True
    assert FakeBackend().capabilities().resume is False


def test_claude_overall_timeout_writes_typed_durable_terminal_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _authenticated_backend(monkeypatch)
    captured: dict[str, object] = {}

    async def never_returns(**kwargs: object) -> None:
        captured.update(kwargs)
        await asyncio.sleep(10)

    monkeypatch.setattr(backend, "run_stage", never_returns)
    result = asyncio.run(backend.execute(_request(tmp_path)))

    assert result.state.value == "FAILED"
    assert result.terminal_disposition is BackendTerminalDisposition.TIMEOUT
    assert result.terminal_record_digest is not None
    terminal = tmp_path / "factory_repair/backend-terminal.json"
    payload = json.loads(terminal.read_text(encoding="utf-8"))
    assert payload["disposition"] == "TIMEOUT"
    assert payload["state"] == "FAILED"
    assert payload["redactedSummary"] == "backend overall wall-clock deadline exceeded"
    assert captured["strict_tool_allowlist"] is True
    assert captured["bash_allowlist"] == []
    record = load_backend_terminal_record(
        terminal,
        expected_digest=result.terminal_record_digest,
        expected_request_id="AREQ-BACKEND-TIMEOUT",
        expected_session_ref=result.session.session_ref,
    )
    assert record.disposition is BackendTerminalDisposition.TIMEOUT

    payload["requestId"] = "AREQ-SUBSTITUTED"
    terminal.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="digest mismatch"):
        load_backend_terminal_record(
            terminal,
            expected_digest=result.terminal_record_digest,
        )


def test_auth_expiry_and_quota_are_typed_durable_subscription_only_pauses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expired_provider = ClaudeCredentialProvider()
    monkeypatch.setattr(
        expired_provider,
        "state",
        lambda: BackendRouteState.AUTH_EXPIRED,
    )
    expired = asyncio.run(ClaudeBackend(expired_provider).execute(_request(tmp_path / "auth")))
    assert expired.terminal_disposition is BackendTerminalDisposition.AUTH_EXPIRED
    assert expired.error_state is BackendRouteState.AUTH_EXPIRED
    assert expired.usage.retry_at is not None
    assert expired.usage.actual_charge_usd == 0
    assert expired.terminal_record_digest is not None

    backend = _authenticated_backend(monkeypatch)
    resume_at = datetime.now(UTC) + timedelta(minutes=15)

    async def quota_pause(**kwargs: object) -> None:
        del kwargs
        raise QuotaLimitPause(
            QuotaPauseRecord(
                kind=PauseKind.FIVE_HOUR,
                detected_at=datetime.now(UTC),
                resume_at=resume_at,
                message="subscription capacity unavailable",
                source="test",
            )
        )

    monkeypatch.setattr(backend, "run_stage", quota_pause)
    quota = asyncio.run(backend.execute(_request(tmp_path / "quota")))
    assert quota.terminal_disposition is BackendTerminalDisposition.QUOTA_WAIT
    assert quota.error_state is BackendRouteState.QUOTA_WAIT
    assert quota.usage.retry_at == resume_at.isoformat()
    assert quota.usage.actual_charge_usd == 0


def test_request_requires_typed_bash_rules_and_exact_tool_pairing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-empty executable/argument allowlist"):
        _request(tmp_path, tools=["Read", "Bash"])
    with pytest.raises(ValueError):
        _request(tmp_path, tools=["Read", "Bash"], bashAllowlist=["git diff"])
    request = _request(
        tmp_path,
        tools=["Read", "Bash"],
        bashAllowlist=[{"executable": "git", "argumentPrefix": ["diff"]}],
    )
    assert request.bash_allowlist == [
        BashCommandRule(executable="git", argumentPrefix=["diff"])
    ]


def test_strict_backend_tools_cannot_be_expanded_by_autopilot_or_features() -> None:
    tools = resolve_sdk_tools(
        ["Read"],
        ["WebFetch", "Agent"],
        work_until_done=True,
        read_only=False,
        strict_tool_allowlist=True,
    )
    assert tools == ["Read"]


def test_claude_rejects_network_tools_before_provider_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _authenticated_backend(monkeypatch)
    request = _request(tmp_path, tools=["Read", "WebFetch"])
    with pytest.raises(ValueError, match="unsupported tools: WebFetch"):
        backend.start(request)


@pytest.mark.parametrize(
    ("command", "rules", "allowed"),
    [
        ("git diff --stat", [{"executable": "git", "argumentPrefix": ["diff"]}], True),
        ("git status", [{"executable": "git", "argumentPrefix": ["diff"]}], False),
        (
            "git diff && curl https://example.test",
            [{"executable": "git", "argumentPrefix": ["diff"]}],
            False,
        ),
        ("sh -c 'git diff'", [{"executable": "git", "argumentPrefix": ["diff"]}], False),
        ("git diff --stat", [], False),
    ],
)
def test_pretool_hook_enforces_executable_and_argument_prefix(
    tmp_path: Path,
    command: str,
    rules: list[dict[str, object]],
    allowed: bool,
) -> None:
    hook = ROOT / ".claude/hooks/path_guard.py"
    environment = {
        **os.environ,
        "TCF_REPO_ROOT": str(tmp_path),
        "TCF_ALLOWED_PATHS_JSON": "[]",
        "TCF_FORBIDDEN_PATHS_JSON": "[]",
        "TCF_ALLOWED_DOMAINS_JSON": "[]",
        "TCF_BASH_RULES_JSON": json.dumps(rules),
        "TCF_READ_ONLY": "1",
    }
    completed = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    assert completed.returncode == 0
    denied = "permissionDecision" in completed.stdout
    assert denied is not allowed


def test_event_retention_is_structured_redacted_metadata_only() -> None:
    class ProviderEvent:
        subtype = "success"
        terminal_reason = "complete"
        num_turns = 2
        duration_ms = 25
        prompt = "Bearer secret-token-that-must-not-survive"
        structured_output = {"customer": "private"}

    summary = redacted_event_summary(ProviderEvent())
    assert summary == {
        "eventType": "ProviderEvent",
        "evidenceMode": "LIVE_VALIDATION",
        "subtype": "success",
        "terminalReason": "complete",
        "numTurns": 2,
        "durationMs": 25,
    }
    source = (ROOT / "tcfactory/claude_runner.py").read_text(encoding="utf-8")
    assert "transcript.jsonl" not in source
    assert "claude-stderr.log" not in source
    assert "backend-stderr-redacted.log" in source
    assert "safe_line = redact_sensitive(line)" in source
    assert "_message_to_json" not in source
    assert datetime.now(UTC).tzinfo is not None


def test_redacted_event_retention_expires_only_bounded_summary_files(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    expired = tmp_path / "old/backend-events-redacted.jsonl"
    expired_session = tmp_path / "old/session-events.jsonl"
    expired_stderr = tmp_path / "old/backend-stderr-redacted.log"
    current = tmp_path / "new/backend-events-redacted.jsonl"
    unrelated = tmp_path / "old/candidate-manifest.json"
    for path in (expired, expired_session, expired_stderr, current, unrelated):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    old_timestamp = (now - timedelta(days=31)).timestamp()
    os.utime(expired, (old_timestamp, old_timestamp))
    os.utime(expired_session, (old_timestamp, old_timestamp))
    os.utime(expired_stderr, (old_timestamp, old_timestamp))
    os.utime(unrelated, (old_timestamp, old_timestamp))
    current_timestamp = (now - timedelta(days=1)).timestamp()
    os.utime(current, (current_timestamp, current_timestamp))

    removed = expire_redacted_event_summaries(tmp_path, now=now, retention_days=30)

    assert removed == sorted([expired, expired_session, expired_stderr])
    assert not expired.exists()
    assert not expired_session.exists()
    assert not expired_stderr.exists()
    assert current.exists()
    assert unrelated.exists()
