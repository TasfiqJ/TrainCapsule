from __future__ import annotations

import asyncio
import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from tcfactory.backends import (
    AgentTaskRequest,
    BackendRouteState,
    ClaudeBackend,
    ClaudeCredentialProvider,
    EngineeringAgentBackend,
    FakeBackend,
    Handoff,
    SessionState,
)
from tcfactory.checkpoints import (
    CheckpointBudget,
    CheckpointError,
    CheckpointStore,
    V3Checkpoint,
)
from tcfactory.config import load_factory_config
from tcfactory.models import FactoryConfig, RoleName, SecurityPolicy, TaskPacket
from tcfactory.structured_runner import (
    run_structured_read_only_review,
    validate_bash_command,
)
from tcfactory.util import atomic_write_text, redact_sensitive
from tcfactory.v3.base import sha256_digest
from tcfactory.v3.enums import Lane

ROOT = Path(__file__).resolve().parents[1]
DIGEST = "sha256:" + "0" * 64
SHA = "0" * 40


class ReviewResult(BaseModel):
    verdict: str
    finding: str


def _request(**updates: object) -> AgentTaskRequest:
    payload: dict[str, object] = {
        "requestId": "AREQ-TEST-001",
        "workItemId": "V3-MIG-001",
        "role": "adversary",
        "taskPacket": {"workItemId": "V3-MIG-001"},
        "sourceContextManifest": {"version": 3},
        "allowedPaths": ["tcfactory/**"],
        "forbiddenPaths": ["config/**"],
        "networkPolicy": "DENY",
        "outputSchema": {"type": "object"},
        "controllerRepoRoot": "/workspace/controller",
        "candidateWorktree": "/workspace/candidate",
        "artifactRoot": "/workspace/artifacts",
        "prompt": "Inspect the bounded candidate and return the schema.",
        "systemPrompt": "Do not mutate files or use the network.",
        "schemaDigest": DIGEST,
        "contextDigest": DIGEST,
        "sourceDigest": DIGEST,
        "maxTurns": 4,
        "maxTokens": 4000,
        "maxCostUsdEquivalent": 0,
        "maxWallTimeSeconds": 60,
        "tools": ["Read"],
        "bashAllowlist": [],
        "networkAllowed": False,
    }
    payload.update(updates)
    return AgentTaskRequest.model_validate(payload)


def _checkpoint(generation: int = 1, candidate_sha: str = SHA) -> V3Checkpoint:
    now = datetime.now(UTC)
    return V3Checkpoint(
        generation=generation,
        work_item_id="V3-MIG-001",
        lane=Lane.FACTORY,
        milestone="M0_FACTORY_MIGRATED",
        backend_session_ref="ASESS-FAKE-0001",
        budget=CheckpointBudget(
            max_turns=8,
            max_wall_time_seconds=120,
            plan_attempts_remaining=1,
            repair_cycles_remaining=2,
            restarts_remaining=1,
        ),
        context_digest=DIGEST,
        source_digest=DIGEST,
        candidate_sha=candidate_sha,
        approval_state="NOT_REQUIRED",
        active=True,
        created_at=now,
        updated_at=now,
    )


def _handoff() -> Handoff:
    return Handoff(
        work_item_id="V3-MIG-001",
        lane="FACTORY",
        milestone="M0_FACTORY_MIGRATED",
        task_kind="MIGRATION",
        disposition="KEEP",
        decision_contribution="Bounded deterministic fixture.",
        source_digest=DIGEST,
        context_digest=DIGEST,
        candidate_sha=SHA,
        next_authorized_transition="PASSED_ENGINEERING",
        artifact_digests={},
        findings=[],
        attempts_remaining=1,
        external_evidence_required=False,
    )


def test_fake_backend_satisfies_protocol_and_is_deterministic() -> None:
    backend = FakeBackend([{"verdict": "pass", "finding": "none"}])
    assert isinstance(backend, EngineeringAgentBackend)
    assert backend.capabilities().network_denial is True
    session = backend.start(_request())
    result = backend.resume(
        session,
        _handoff(),
    )
    assert result.state is SessionState.COMPLETED
    assert result.structured_output == {"verdict": "pass", "finding": "none"}
    assert result.usage.actual_charge_usd == 0

    second = backend.start(_request(requestId="AREQ-TEST-002"))
    backend.cancel(second)
    with pytest.raises(ValueError, match="cancelled"):
        backend.resume(
            second,
            _handoff(),
        )


@pytest.mark.parametrize(
    "secret",
    [
        "Bearer abcdefghijklmnopqrstuvwxyz",
        "oauth-secret-token-value",
        "/home/user/.config/traincapsule/claude-oauth-token",
        "account_id=customer-12345",
        "TCF_PRIVATE_GATE_RUNNER=/controller/private-gate",
    ],
)
def test_backend_request_rejects_secret_or_account_material(secret: str) -> None:
    with pytest.raises(ValueError, match="credential, account, or controller-secret"):
        _request(prompt=f"Do work with {secret}")


def test_request_export_never_contains_prompt_or_local_path() -> None:
    request = _request()
    exported = json.dumps(request.exportable_summary())
    assert request.prompt not in exported
    assert request.candidate_worktree not in exported
    assert "systemPrompt" not in exported
    redacted = redact_sensitive(
        "account_id=customer-42 /home/user/.config/traincapsule/claude-oauth-token"
    )
    assert "customer-42" not in redacted
    assert "claude-oauth-token" not in redacted


def test_claude_provider_exposes_only_backend_neutral_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def expired(**_: object) -> None:
        raise RuntimeError("token at /private/controller/claude-oauth-token expired")

    monkeypatch.setattr("tcfactory.backends.claude.assert_max_oauth_only", expired)
    provider = ClaudeCredentialProvider()
    assert provider.state() is BackendRouteState.AUTH_EXPIRED
    with pytest.raises(RuntimeError) as captured:
        provider.sdk_environment()
    assert str(captured.value) == "AUTH_EXPIRED"
    assert "token" not in str(ClaudeBackend.safe_exception(RuntimeError("sk-secretvalue")))


def test_claude_adapter_rejects_any_weakened_network_or_sandbox_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ClaudeCredentialProvider()
    monkeypatch.setattr(
        provider,
        "state",
        lambda: BackendRouteState.AUTHENTICATED,
    )
    backend = ClaudeBackend(provider)
    with pytest.raises(ValueError, match="explicit DENY"):
        backend.start(_request(networkPolicy="ALLOWLIST"))

    denied = TaskPacket.model_construct(security=SecurityPolicy())
    ClaudeBackend.require_execution_security(FactoryConfig(), denied)
    allowlisted = TaskPacket.model_construct(
        security=SecurityPolicy(network_default="allowlist")
    )
    with pytest.raises(RuntimeError, match="network-default deny"):
        ClaudeBackend.require_execution_security(FactoryConfig(), allowlisted)
    with pytest.raises(RuntimeError, match="requires the sandbox"):
        ClaudeBackend.require_execution_security(
            FactoryConfig(sandbox_enabled=False),
            denied,
        )
    with pytest.raises(RuntimeError, match="fail when the sandbox"):
        ClaudeBackend.require_execution_security(
            FactoryConfig(),
            TaskPacket.model_construct(
                security=SecurityPolicy(fail_if_sandbox_unavailable=False)
            ),
        )


def test_structured_runner_routes_fake_backend_without_model_usage(tmp_path: Path) -> None:
    backend = FakeBackend([{"verdict": "pass", "finding": "none"}])
    result = asyncio.run(
        run_structured_read_only_review(
            repo_root=ROOT,
            cwd=ROOT,
            config=load_factory_config(ROOT / "config/factory.yaml"),
            prompt="Inspect the bounded fixture.",
            system_prompt="Return only the result schema.",
            model="fake",
            effort="low",
            max_turns=3,
            max_budget_usd=1.0,
            schema=ReviewResult.model_json_schema(),
            result_type=ReviewResult,
            artifact_dir=tmp_path / "review",
            role=RoleName.ADVERSARY,
            task_id="V3-MIG-001",
            run_id="TEST001",
            backend=backend,
            max_wall_time_seconds=30,
            bash_allowlist=[],
        )
    )
    assert result == ReviewResult(verdict="pass", finding="none")
    exported = (tmp_path / "review/request-summary.json").read_text()
    assert "Inspect the bounded fixture" not in exported
    assert not (tmp_path / "review/transcript.jsonl").exists()


def test_bash_allowlist_rejects_compound_and_unlisted_commands() -> None:
    validate_bash_command("git diff --stat", ["git diff"])
    with pytest.raises(ValueError, match="outside"):
        validate_bash_command("curl https://example.test", ["git diff"])
    with pytest.raises(ValueError, match="compound"):
        validate_bash_command("git diff && curl example.test", ["git diff"])


def test_v3_checkpoint_envelope_and_previous_generation_recovery(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints")
    first = _checkpoint()
    path = store.save_v3(first)
    raw = json.loads(path.read_text())
    assert raw["schemaVersion"] == 3
    assert raw["contentDigest"].startswith("sha256:")

    second = _checkpoint(generation=2, candidate_sha="1" * 40)
    store.save_v3(second)
    previous = path.with_suffix(".json.previous")
    assert previous.exists()
    atomic_write_text(path, '{"partial":')
    with pytest.raises(CheckpointError, match="blocks recovery"):
        store.load_v3(first.work_item_id)
    assert list((store.root / "quarantine").glob("*.json"))
    store.recover_previous(first.work_item_id)
    recovered = store.load_v3(first.work_item_id)
    assert recovered is not None
    assert recovered.generation == 1


def test_v3_checkpoint_rejects_incompatible_stale_and_duplicate_active_work(
    tmp_path: Path,
) -> None:
    incompatible_store = CheckpointStore(tmp_path / "incompatible")
    bad = incompatible_store.path_for("V3-MIG-001")
    atomic_write_text(bad, json.dumps({"schemaVersion": 2, "checkpoint": {}}))
    with pytest.raises(CheckpointError, match="blocks recovery"):
        incompatible_store.load_v3("V3-MIG-001")

    stale_store = CheckpointStore(tmp_path / "stale")
    stale_store.save_v3(_checkpoint())
    with pytest.raises(CheckpointError, match="blocks recovery"):
        stale_store.load_v3("V3-MIG-001", observed_candidate_sha="2" * 40)

    duplicate_store = CheckpointStore(tmp_path / "duplicate")
    original = duplicate_store.save_v3(_checkpoint())
    duplicate = duplicate_store.path_for("V3-ALT-999")
    atomic_write_text(duplicate, original.read_text())
    with pytest.raises(CheckpointError, match="duplicate active V3 work"):
        duplicate_store.list_active_v3()


def test_structured_runner_has_no_unbounded_or_raw_sdk_serialization_branch() -> None:
    source = inspect.getsource(run_structured_read_only_review)
    assert "subscription_unbounded" not in source
    assert "_message_to_json" not in source
    assert "transcript.jsonl" not in source
    assert "asyncio.timeout" in source
    assert sha256_digest(b"contract").startswith("sha256:")
