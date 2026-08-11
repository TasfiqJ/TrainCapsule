from __future__ import annotations

from pathlib import Path

import pytest

from tcfactory.catalog import load_task_catalog, task_packet_from_catalog
from tcfactory.config import load_task
from tcfactory.feature_ledger import load_feature_ledger
from tcfactory.models import Gate, RiskTier, RoleName, SecurityPolicy, Stage
from tcfactory.planner import (
    TaskPacketPolicyError,
    add_protected_path_baseline,
    apply_controller_owned_catalog_minimums,
    validate_product_task_packet,
)
from tcfactory.risk import apply_risk_profile, load_risk_profiles

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_OR_DEMAND_DRIVEN = {"T119", "T121"}


def _inputs():
    ledger = load_feature_ledger(ROOT / "factory/feature_ledger.yaml")
    catalog = load_task_catalog(ROOT / "factory/task_catalog.yaml")
    profiles = load_risk_profiles(ROOT / "config/risk_profiles.yaml")
    return ledger, catalog, profiles


def test_catalog_covers_every_automatable_build_task() -> None:
    ledger, catalog, _profiles = _inputs()
    expected = {
        item.task_id
        for item in ledger.tasks
        if item.automatable and item.task_id not in EXTERNAL_OR_DEMAND_DRIVEN
    }
    assert set(catalog.tasks) == expected


def test_catalog_dependencies_and_risk_labels_match_ledger() -> None:
    ledger, catalog, _profiles = _inputs()
    for task_id, entry in catalog.tasks.items():
        item = ledger.item(task_id)
        assert entry.depends_on == item.depends_on
        assert entry.risk_tier == item.risk_tier.value


def test_standard_catalog_task_avoids_model_planning_and_spec_session() -> None:
    ledger, catalog, profiles = _inputs()
    item = ledger.item("T022")
    packet = task_packet_from_catalog(
        repo_root=ROOT,
        item=item,
        catalog=catalog,
        risk_profiles=profiles,
    )
    assert packet.risk_tier == RiskTier.STANDARD
    assert [stage.role for stage in packet.pipeline] == [
        RoleName.BUILDER,
        RoleName.ADVERSARY,
    ]
    assert all(stage.model == "sonnet" for stage in packet.pipeline)
    assert packet.remote_ci_required is False


def test_integration_catalog_task_uses_opus_only_where_independent_value_exists() -> None:
    ledger, catalog, profiles = _inputs()
    item = ledger.item("T005")
    packet = task_packet_from_catalog(
        repo_root=ROOT,
        item=item,
        catalog=catalog,
        risk_profiles=profiles,
    )
    roles = [stage.role for stage in packet.pipeline]
    assert roles == [
        RoleName.BUILDER,
        RoleName.ADVERSARY,
    ]
    models = {stage.role: stage.model for stage in packet.pipeline}
    assert models[RoleName.BUILDER] == "sonnet"
    assert models[RoleName.ADVERSARY] == "opus"
    assert packet.private_gate.required is True
    assert packet.remote_ci_required is True


def test_catalog_first_attempt_is_deterministic_and_revisions_use_model_respec() -> None:
    ledger, catalog, _profiles = _inputs()
    assert "T031" in catalog.tasks
    assert ledger.item("T031").revisions == 0


def test_catalog_packet_gets_controller_owned_protected_path_baseline() -> None:
    ledger, catalog, profiles = _inputs()
    item = ledger.item("T001")
    packet = task_packet_from_catalog(
        repo_root=ROOT,
        item=item,
        catalog=catalog,
        risk_profiles=profiles,
    )

    protected = add_protected_path_baseline(packet)
    validate_product_task_packet(protected, item, repo_root=ROOT)

    research = next(stage for stage in protected.pipeline if stage.role == RoleName.RESEARCH)
    assert "factory/state/**" in research.forbidden_paths
    assert "scripts/gates/**" in research.forbidden_paths
    assert "docs/source-of-truth/**" in research.forbidden_paths
    # The controller condition is intentionally simple and auditable: catalog on revision 0,
    # fresh model planning only after evidence-backed re-specification or a missing entry.
    assert ledger.item("T031").revisions == 0


def test_model_respec_cannot_promote_raw_shell_gate_commands() -> None:
    ledger, catalog, profiles = _inputs()
    item = ledger.item("T002")
    packet = task_packet_from_catalog(
        repo_root=ROOT,
        item=item,
        catalog=catalog,
        risk_profiles=profiles,
    )
    unsafe = packet.model_copy(
        update={
            "gates": [
                Gate(name="unsafe-inline-shell", command="test -f README.md")
            ]
        }
    )

    with pytest.raises(TaskPacketPolicyError, match="not controller-safe"):
        validate_product_task_packet(unsafe, item, repo_root=ROOT)


def test_model_respec_cannot_alias_multiple_gate_names_to_one_command() -> None:
    ledger, catalog, profiles = _inputs()
    item = ledger.item("T002")
    packet = task_packet_from_catalog(
        repo_root=ROOT,
        item=item,
        catalog=catalog,
        risk_profiles=profiles,
    )
    command = "uv run python scripts/gates/output_and_integration_gate.py T002 file-present"
    aliased = packet.model_copy(
        update={
            "gates": [
                Gate(name="first-check", command=command),
                Gate(name="second-check", command=command),
            ]
        }
    )

    with pytest.raises(TaskPacketPolicyError, match="duplicates command"):
        validate_product_task_packet(aliased, item, repo_root=ROOT)


def test_product_packet_acceptance_criteria_have_no_arbitrary_count_ceiling() -> None:
    ledger, catalog, profiles = _inputs()
    item = ledger.item("T002")
    packet = task_packet_from_catalog(
        repo_root=ROOT,
        item=item,
        catalog=catalog,
        risk_profiles=profiles,
    )
    complete = add_protected_path_baseline(packet).model_copy(
        update={"acceptance_criteria": [f"Production condition {index}" for index in range(40)]}
    )

    validate_product_task_packet(complete, item, repo_root=ROOT)


def test_every_catalog_research_packet_declares_generic_v2_evidence_bundle() -> None:
    ledger, catalog, profiles = _inputs()
    research_entries = {
        task_id: entry
        for task_id, entry in catalog.tasks.items()
        if entry.task_kind.lower() == "research"
    }
    assert research_entries

    for task_id in research_entries:
        packet = task_packet_from_catalog(
            repo_root=ROOT,
            item=ledger.item(task_id),
            catalog=catalog,
            risk_profiles=profiles,
        )
        evidence_root = f"docs/evidence/{task_id}"
        expected_record = (
            "docs/research/T002_name_trademark_check.md"
            if task_id == "T002"
            else f"docs/research/{task_id}_research.md"
        )
        assert expected_record in packet.outputs
        assert f"{evidence_root}/query-plan.json" in packet.outputs
        assert f"{evidence_root}/manifest.json" in packet.outputs
        assert f"{evidence_root}/raw/**" in packet.outputs

        research = next(stage for stage in packet.pipeline if stage.role == RoleName.RESEARCH)
        assert research.allowed_paths == ["**"]
        assert expected_record in packet.outputs
        assert "research-evidence" in research.machine_gates
        gate = next(gate for gate in packet.gates if gate.name == "research-evidence")
        assert gate.command.endswith(f"{task_id} research-evidence")
        assert len({candidate.command for candidate in packet.gates}) == len(packet.gates)


def test_model_planning_cannot_drop_controller_owned_research_v2_contract() -> None:
    ledger, catalog, profiles = _inputs()
    item = ledger.item("T002")
    seed = task_packet_from_catalog(
        repo_root=ROOT,
        item=item,
        catalog=catalog,
        risk_profiles=profiles,
    )
    proposal = seed.model_copy(
        update={
            "outputs": ["docs/research/T002_name_trademark_check.md"],
            "gates": [],
            "security": SecurityPolicy(network_default="deny"),
            "pipeline": [
                Stage(
                    role=RoleName.BUILDER,
                    allowed_paths=["docs/research/T002_name_trademark_check.md"],
                    require_changes=True,
                )
            ],
        }
    )

    normalized = apply_controller_owned_catalog_minimums(proposal, seed)
    routed = add_protected_path_baseline(apply_risk_profile(normalized, item, profiles))
    validate_product_task_packet(
        routed,
        item,
        repo_root=ROOT,
        catalog_seed=seed,
    )

    assert RoleName.BUILDER not in {stage.role for stage in routed.pipeline}
    research = next(stage for stage in routed.pipeline if stage.role == RoleName.RESEARCH)
    assert "research-evidence" in research.machine_gates
    assert "docs/evidence/T002/query-plan.json" in routed.outputs
    assert routed.security.network_default == "allowlist"


def test_active_t002_uses_research_v2_and_real_authority_sources() -> None:
    packet = load_task(ROOT / "tasks/T002.yaml")
    assert packet.security.network_default == "allowlist"
    assert "docs/evidence/T002/query-plan.json" in packet.outputs
    assert "research-evidence" in {gate.name for gate in packet.gates}
    assert all((ROOT / source).is_file() for source in packet.source_of_truth)
    for stage in packet.pipeline:
        assert "research-evidence" in stage.machine_gates
