from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tcfactory.catalog import compile_v3_packet
from tcfactory.cli import app
from tcfactory.completion import evaluate_v3_milestone_completion
from tcfactory.context import ContextPolicyError, build_v3_context_manifest
from tcfactory.handoffs import read_v3_handoff, write_v3_handoff
from tcfactory.peer_messaging import PeerMessage, PeerMessageError, validate_peer_artifact
from tcfactory.util import (
    atomic_write_text,
    redact_sensitive,
    resolve_within,
    sanitized_subprocess_env,
    single_writer_lock,
)
from tcfactory.v3.base import sha256_digest
from tcfactory.v3.configuration import validate_v3_configuration
from tcfactory.v3.enums import (
    Disposition,
    Lane,
    MilestoneStatus,
    MilestoneType,
    WorkKind,
    WorkStatus,
)
from tcfactory.v3.milestones import Milestone, MilestoneRoadmap
from tcfactory.v3.pipeline_services import (
    FindingOwner,
    V3Finding,
    assert_factory_repair_scope,
    route_finding,
)
from tcfactory.v3.planning import (
    PacketPolicyError,
    V3TaskPacket,
    load_cached_packet,
    write_packet,
)
from tcfactory.v3.work_items import WorkItem, WorkItemCollection
from tcfactory.value import DecisionValueOutcome, apply_v3_value_decision
from tcfactory.yamlutil import load_yaml

ROOT = Path(__file__).resolve().parents[1]
DIGEST = "sha256:" + "0" * 64
SHA = "0" * 40


def _roadmap() -> WorkItemCollection:
    return WorkItemCollection.model_validate(load_yaml(ROOT / "factory/roadmap/work_items.yaml"))


def _milestones() -> MilestoneRoadmap:
    return MilestoneRoadmap.model_validate(load_yaml(ROOT / "factory/roadmap/milestones.yaml"))


def _packet() -> V3TaskPacket:
    item = next(
        item
        for item in _roadmap().work_items
        if item.automatable and item.lane is Lane.FACTORY
    )
    return compile_v3_packet(
        item=item,
        source_documents=["docs/source-of-truth/v3-2026-08-11/FACTORY_LOOP_REDESIGN_SPEC.md"],
        allowed_paths=["factory/generated/**"],
        outputs=["factory/generated/result.json"],
        acceptance_criteria=["The exact deterministic fixture passes."],
        non_goals=["Do not change product runtime code."],
        oracle="Compare the generated record to the checked-in golden fixture.",
        rollback="Remove the generated record and revert the candidate commit.",
        stop_conditions=["Stop after one repeated counterexample."],
        stop_disposition="NARROW",
        source_digest=DIGEST,
        context_digest=DIGEST,
        base_sha=SHA,
    )


def _work_item_for_milestone(milestone: str, status: WorkStatus) -> WorkItem:
    source = next(item for item in _roadmap().work_items if item.automatable)
    payload = source.model_dump(mode="json", by_alias=True)
    payload.update(
        {
            "milestone": milestone,
            "dependsOn": [],
            "softDependsOn": [],
            "status": status.value,
            "externalReceiptRequired": False,
            "externalEvidenceRefs": [],
        }
    )
    return WorkItem.model_validate(payload)


def test_v3_packet_compiler_is_bounded_digest_bound_and_reusable(tmp_path: Path) -> None:
    packet = _packet()
    assert len(packet.acceptance_criteria) <= 12
    assert len(packet.outputs) <= 8
    assert len(packet.source_documents) <= 8
    assert packet.template.endswith("-v3")

    path = tmp_path / "packet.yaml"
    write_packet(path, packet)
    assert load_cached_packet(path, packet) == packet

    changed = V3TaskPacket.model_validate(
        {**packet.model_dump(mode="json", by_alias=True), "contextDigest": sha256_digest(b"new")}
    )
    assert load_cached_packet(path, changed) is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "acceptanceCriteria",
            ["Every product requirement is complete."],
            "universal",
        ),
        (
            "acceptanceCriteria",
            ["The system is production-ready."],
            "generic production",
        ),
        (
            "outputs",
            ["outside/result.json"],
            "not writable",
        ),
    ],
)
def test_v3_packet_rejects_policy_violations(field: str, value: object, message: str) -> None:
    packet = _packet()
    payload = packet.model_dump(mode="json", by_alias=True)
    payload[field] = value
    with pytest.raises((PacketPolicyError, ValueError), match=message):
        V3TaskPacket.model_validate(payload)


def test_v3_packet_rejects_mixed_product_factory_scope() -> None:
    packet = _packet()
    payload = packet.model_dump(mode="json", by_alias=True)
    payload["allowedPaths"] = ["factory/generated/**", "packages/traincapsule-core/**"]
    with pytest.raises(ValueError, match="mix product and factory"):
        V3TaskPacket.model_validate(payload)


def test_external_work_cannot_compile_as_ai_packet() -> None:
    item = next(item for item in _roadmap().work_items if not item.automatable)
    with pytest.raises(PacketPolicyError, match="requires external evidence"):
        compile_v3_packet(
            item=item,
            source_documents=["docs/CONTEXT_INDEX.yaml"],
            allowed_paths=["factory/generated/**"],
            outputs=[],
            acceptance_criteria=["A trusted external receipt exists."],
            non_goals=["Do not synthesize the receipt."],
            oracle="External trust-root signature verification.",
            rollback="Preserve the wait state.",
            stop_conditions=["Stop without a trusted receipt."],
            stop_disposition="WAITING_EXTERNAL",
            source_digest=DIGEST,
            context_digest=DIGEST,
            base_sha=SHA,
        )


def test_v3_context_is_scoped_digest_bound_and_freshness_aware() -> None:
    item = next(item for item in _roadmap().work_items if item.automatable)
    manifest = build_v3_context_manifest(
        repo_root=ROOT,
        work_item=item,
        role="planner",
        requested_groups=["factory_control"],
        max_context_chars=200_000,
    )
    assert manifest.entries
    assert all(entry.authority_class for entry in manifest.entries)
    authority_paths = [entry.path for entry in manifest.entries[:2]]
    assert authority_paths == [
        "config/active_generation.yaml",
        "docs/source-of-truth/v3.1-zh-2026-08-12/FINAL_MANIFEST_V3_1_ZH.json",
    ]
    assert manifest.entries[0].authority_sections == [
        "§generationId",
        "§manifestPath",
        "§mixedNormativeGenerationPolicy",
    ]
    assert manifest.entries[1].authority_sections == [
        "§documents",
        "§supersession",
        "§integrity",
    ]
    assert all((ROOT / entry.path).is_file() for entry in manifest.entries)
    assert "advisory_career" in manifest.excluded_groups
    assert manifest.source_digest.startswith("sha256:")

    with pytest.raises(ContextPolicyError, match="recheck_required"):
        build_v3_context_manifest(
            repo_root=ROOT,
            work_item=item,
            role="planner",
            requested_groups=["current_facts"],
            max_context_chars=200_000,
        )
    fresh = build_v3_context_manifest(
        repo_root=ROOT,
        work_item=item,
        role="planner",
        requested_groups=["current_facts"],
        max_context_chars=200_000,
        freshness_receipts={"current_facts": datetime.now(UTC)},
    )
    current_fact_entries = [
        entry for entry in fresh.entries if entry.freshness_policy != "manifest_locked"
    ]
    assert current_fact_entries
    assert all(entry.freshness_status == "CURRENT" for entry in current_fact_entries)


def test_milestone_completion_is_bounded_and_external_truth_is_not_simulated() -> None:
    item = _work_item_for_milestone("M0_FACTORY_MIGRATED", WorkStatus.PASSED_ENGINEERING)
    roadmap = WorkItemCollection(active_milestone=item.milestone, work_items=[item])
    raw = _milestones().milestone("M0_FACTORY_MIGRATED").model_dump(
        mode="json", by_alias=True
    )
    raw.update(
        {
            "type": MilestoneType.ENGINEERING.value,
            "status": MilestoneStatus.ACTIVE.value,
        }
    )
    milestone = Milestone.model_validate(raw)
    result = evaluate_v3_milestone_completion(
        milestone=milestone,
        work_items=roadmap,
        deterministic_evidence={item.work_item_id: ["gate.json"]},
        independent_review_refs=[],
        machine_policy_receipt_refs=[],
        trusted_external_receipt_refs=[],
    )
    assert result.decision is MilestoneStatus.COMPLETED

    m3_item = _work_item_for_milestone("M3_PAID_PREFLIGHT", WorkStatus.PASSED_ENGINEERING)
    m3 = _milestones().milestone("M3_PAID_PREFLIGHT")
    external = evaluate_v3_milestone_completion(
        milestone=m3,
        work_items=WorkItemCollection(active_milestone=m3.milestone_id, work_items=[m3_item]),
        deterministic_evidence={m3_item.work_item_id: ["controlled.json"]},
        independent_review_refs=["review.json"],
        machine_policy_receipt_refs=[],
        trusted_external_receipt_refs=[],
        controlled_fixture_only=True,
    )
    assert external.decision is MilestoneStatus.WAITING_EXTERNAL


def test_milestone_machine_policy_gap_stays_active_until_receipt_exists() -> None:
    source = next(
        item
        for item in _roadmap().work_items
        if item.kind is WorkKind.MACHINE_POLICY_REVIEW
    )
    payload = source.model_dump(mode="json", by_alias=True)
    payload.update(
        {
            "milestone": "M0_FACTORY_MIGRATED",
            "dependsOn": [],
            "softDependsOn": [],
            "status": WorkStatus.PASSED_ENGINEERING.value,
        }
    )
    item = WorkItem.model_validate(payload)
    milestone_payload = _milestones().milestone("M0_FACTORY_MIGRATED").model_dump(
        mode="json", by_alias=True
    )
    milestone_payload["type"] = MilestoneType.ENGINEERING.value
    milestone = Milestone.model_validate(milestone_payload)
    collection = WorkItemCollection(
        active_milestone=milestone.milestone_id,
        work_items=[item],
    )
    blocked = evaluate_v3_milestone_completion(
        milestone=milestone,
        work_items=collection,
        deterministic_evidence={item.work_item_id: ["policy-gate.json"]},
        independent_review_refs=["independent-verifier.json"],
        machine_policy_receipt_refs=[],
        trusted_external_receipt_refs=[],
    )
    assert blocked.decision is MilestoneStatus.ACTIVE
    assert any("machine-policy receipt" in failure for failure in blocked.deterministic_failures)

    complete = evaluate_v3_milestone_completion(
        milestone=milestone,
        work_items=collection,
        deterministic_evidence={item.work_item_id: ["policy-gate.json"]},
        independent_review_refs=["independent-verifier.json"],
        machine_policy_receipt_refs=["machine-policy.json"],
        trusted_external_receipt_refs=[],
    )
    assert complete.decision is MilestoneStatus.COMPLETED


def test_value_outcomes_are_terminal_and_never_append_work() -> None:
    item = next(item for item in _roadmap().work_items if item.lane is Lane.PRODUCT)
    result = apply_v3_value_decision(
        item,
        outcome=DecisionValueOutcome.NATIVE_WORKFLOW_SUFFICIENT,
        rationale="The provider-native command produces the same decision artifact.",
        evidence_refs=["native-comparison.json"],
    )
    assert result.resulting_status is WorkStatus.NATIVE_SUFFICIENT
    assert result.appended_work_item_ids == []


def test_findings_are_owner_routed_and_factory_authority_is_protected() -> None:
    advisory = route_finding(
        V3Finding(
            finding_id="FIND-ONE",
            summary="Consider renaming the helper.",
            artifact_path="tcfactory/helper.py",
            advisory=True,
        )
    )
    assert advisory.owner is FindingOwner.FACTORY
    assert advisory.blocking is False
    with pytest.raises(ValueError, match="protected authority"):
        assert_factory_repair_scope(["docs/source-of-truth/v3-2026-08-11/file.md"])


def test_atomic_paths_redaction_and_single_writer_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "record.json"
    atomic_write_text(target, "one\n")
    atomic_write_text(target, "two\n", keep_previous=True)
    assert target.read_text() == "two\n"
    assert target.with_suffix(".json.previous").read_text() == "one\n"
    with pytest.raises(ValueError, match="escapes"):
        resolve_within(tmp_path, "../escape")

    lock = tmp_path / "writer.lock"
    with (
        single_writer_lock(lock),
        pytest.raises(RuntimeError, match="already held"),
        single_writer_lock(lock),
    ):
        pass

    monkeypatch.setenv("SOME_API_TOKEN", "sk-secretvalue123")
    monkeypatch.setenv("SAFE_FOR_TEST", "safe")
    assert "SOME_API_TOKEN" not in sanitized_subprocess_env(inherit=["SOME_API_TOKEN"])
    assert "[REDACTED]" in redact_sensitive("Bearer abcdefghijklmnop")


def test_peer_artifacts_and_handoffs_are_digest_bound(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    artifact = root / "review.json"
    artifact.write_text("{}\n")
    message = PeerMessage(
        task_id="TASK1",
        kind="finding",
        artifact_path="review.json",
        artifact_digest=sha256_digest(artifact.read_bytes()),
        summary="Bound review",
    )
    assert validate_peer_artifact(message, root) == artifact
    bad = message.model_copy(update={"artifact_digest": DIGEST})
    with pytest.raises(PeerMessageError, match="digest mismatch"):
        validate_peer_artifact(bad, root)

    item = next(item for item in _roadmap().work_items if item.automatable)
    path = write_v3_handoff(
        artifact_root=root,
        relative_path="handoff.json",
        work_item=item,
        disposition=Disposition.KEEP,
        attempt=1,
        attempts_remaining=1,
        base_sha=SHA,
        candidate_sha="1" * 40,
        next_action="Run the bounded verifier.",
        findings=[],
        artifacts={"review": artifact},
    )
    assert read_v3_handoff(path).payload.work_item_id == item.work_item_id


def test_v3_operator_cli_is_read_only_and_explains_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["config", "validate", "--repo", str(ROOT)])
    assert result.exit_code == 0
    explain = runner.invoke(
        app,
        ["config", "explain", "factory.repository.releaseMode", "--repo", str(ROOT)],
    )
    assert explain.exit_code == 0
    assert "AUTOMATED_PR_REQUIRED_CHECKS_MACHINE_RECEIPT_AUTO_MERGE" in explain.stdout
    assert runner.invoke(app, ["migrate", "--repo", str(ROOT)]).exit_code == 2
    dry = runner.invoke(app, ["migrate", "--dry-run", "--repo", str(ROOT)])
    assert dry.exit_code == 0
    assert '"mutation": false' in dry.stdout.lower()

    monkeypatch.setenv("TCF_RELEASE_MODE", "direct")
    with pytest.raises(ValueError, match="protected V3 environment overrides"):
        validate_v3_configuration(ROOT)
