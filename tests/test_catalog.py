from __future__ import annotations

from pathlib import Path

import pytest

from tcfactory.catalog import load_task_catalog, task_packet_from_catalog
from tcfactory.feature_ledger import load_feature_ledger
from tcfactory.models import Gate, RiskTier, RoleName
from tcfactory.planner import (
    TaskPacketPolicyError,
    add_protected_path_baseline,
    validate_product_task_packet,
)
from tcfactory.risk import load_risk_profiles

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
        RoleName.RELEASE,
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
        RoleName.SPECIFICATION,
        RoleName.BUILDER,
        RoleName.ADVERSARY,
        RoleName.AUDIT,
        RoleName.RELEASE,
    ]
    models = {stage.role: stage.model for stage in packet.pipeline}
    assert models[RoleName.SPECIFICATION] == "opus"
    assert models[RoleName.BUILDER] == "sonnet"
    assert models[RoleName.ADVERSARY] == "opus"
    assert models[RoleName.AUDIT] == "sonnet"
    assert models[RoleName.RELEASE] == "sonnet"
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
    assert "docs/TrainCapsule_Matrix_Definitive_Master_Plan_v1.0.md" in (
        research.forbidden_paths
    )
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
