import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

import tcfactory.value as value_module
from tcfactory.models import (
    Gate,
    MetricDirection,
    RoleName,
    Stage,
    TaskPacket,
    ValueContract,
    ValueEvidenceClass,
    ValueGateMode,
    ValueStatus,
)
from tcfactory.value import ValueGateError, evaluate_value_contract, value_contract_digest
from tcfactory.value_policy import contract_for_task, load_value_policy

ROOT = Path(__file__).resolve().parents[1]


def _accept_privileged_path(_path: Path) -> None:
    return None


def _accept_external_signature(
    *, receipt: Path, signature: Path, public_key: Path
) -> None:
    del receipt, signature, public_key


def test_every_catalog_task_has_predeclared_value_contract() -> None:
    policy = load_value_policy(ROOT / "config/value_policy.yaml")
    for task_id in ("T001", "T041", "T119", "T124"):
        contract = contract_for_task(policy, task_id)
        assert contract.target_user
        assert contract.customer_outcome
        assert contract.revenue_linkage
        assert "lines of code" in contract.prohibited_proxies


def test_measured_milestone_has_frozen_threshold() -> None:
    policy = load_value_policy(ROOT / "config/value_policy.yaml")
    contract = contract_for_task(policy, "T012")
    assert contract.mode == ValueGateMode.MEASURED
    assert contract.minimum_material_improvement is not None
    assert contract.evidence_path
    assert contract.falsification_criteria
    assert "target_user_outcome_demonstrated_end_to_end" in contract.required_conditions
    assert "protected_source_requirements_satisfied" in contract.required_conditions
    assert "component completion without a usable supported workflow" in contract.prohibited_proxies
    assert any("target user cannot complete" in item for item in contract.falsification_criteria)


def test_external_demand_cannot_be_synthesized() -> None:
    policy = load_value_policy(ROOT / "config/value_policy.yaml")
    contract = contract_for_task(policy, "T119")
    assert contract.mode == ValueGateMode.EXTERNAL
    assert contract.required_evidence_classes


def test_foundational_contract_gets_a_machine_evidence_path() -> None:
    policy = load_value_policy(ROOT / "config/value_policy.yaml")
    contract = contract_for_task(policy, "T001")
    assert contract.mode == ValueGateMode.FOUNDATIONAL
    assert contract.evidence_path == "docs/evidence/T001/capability-value.json"


def _foundation_task(contract: ValueContract) -> TaskPacket:
    return TaskPacket(
        task_id="T900",
        title="Foundation",
        phase="P0",
        goal="Prove one dependency",
        source_of_truth=["README.md"],
        acceptance_criteria=["Dependency works"],
        outputs=[contract.evidence_path or ""],
        stop_conditions=["Authority missing"],
        gates=[Gate(name="quality", command="true")],
        pipeline=[
            Stage(
                role=RoleName.BUILDER,
                allowed_paths=["**"],
                machine_gates=["quality"],
            )
        ],
        value_contract=contract,
    )


def test_foundational_value_cannot_pass_from_prose_alone(tmp_path: Path) -> None:
    contract = ValueContract(
        mode=ValueGateMode.FOUNDATIONAL,
        parent_milestone="sellable workflow",
        evidence_path="docs/evidence/T900/capability-value.json",
        required_conditions=["real boundary works"],
        falsification_criteria=["negative control rejects corruption"],
    )
    with pytest.raises(ValueGateError, match="Required value evidence is missing"):
        evaluate_value_contract(repo_root=tmp_path, task=_foundation_task(contract))


def test_foundational_value_pass_requires_hashed_candidate_evidence(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("authority\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    contract = ValueContract(
        mode=ValueGateMode.FOUNDATIONAL,
        parent_milestone="sellable workflow",
        evidence_path="docs/evidence/T900/capability-value.json",
        required_conditions=["real boundary works"],
        falsification_criteria=["negative control rejects corruption"],
    )
    raw_path = tmp_path / "docs/evidence/T900/raw/result.json"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text('{"observed":"real boundary"}\n', encoding="utf-8")
    evidence_path = tmp_path / (contract.evidence_path or "")
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(
            {
                "task_id": "T900",
                "metric": contract.primary_metric,
                "passed": True,
                "conditions": {"real boundary works": True},
                "method": "Execute the real dependency boundary and a corrupt control.",
                "measurement_command": "pytest tests/e2e/test_boundary.py",
                "source_commit": head,
                "preregistered_contract_sha256": value_contract_digest(contract),
                "raw_artifacts": ["docs/evidence/T900/raw/result.json"],
                "artifact_hashes": {
                    "docs/evidence/T900/raw/result.json": hashlib.sha256(
                        raw_path.read_bytes()
                    ).hexdigest()
                },
                "evidence_classes": [ValueEvidenceClass.FOUNDATIONAL.value],
                "falsification_results": {
                    "negative control rejects corruption": True
                },
            }
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "docs/evidence/T900"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "candidate evidence"], cwd=tmp_path, check=True)

    result = evaluate_value_contract(repo_root=tmp_path, task=_foundation_task(contract))
    assert result.assessment.status == ValueStatus.PASS


def test_value_evidence_rejects_later_unhashed_candidate_change(tmp_path: Path) -> None:
    test_foundational_value_pass_requires_hashed_candidate_evidence(tmp_path)
    (tmp_path / "product.py").write_text("changed after measurement\n", encoding="utf-8")
    subprocess.run(["git", "add", "product.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "unattested product change"], cwd=tmp_path, check=True)
    contract = ValueContract(
        mode=ValueGateMode.FOUNDATIONAL,
        parent_milestone="sellable workflow",
        evidence_path="docs/evidence/T900/capability-value.json",
        required_conditions=["real boundary works"],
        falsification_criteria=["negative control rejects corruption"],
    )

    with pytest.raises(ValueGateError, match="does not hash every candidate change"):
        evaluate_value_contract(repo_root=tmp_path, task=_foundation_task(contract))


def test_external_value_requires_trusted_exact_sha_attributable_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("candidate\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "candidate"], cwd=repo, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    contract = ValueContract(
        mode=ValueGateMode.EXTERNAL,
        metric_direction=MetricDirection.EXTERNAL,
        evidence_path="external/T900.json",
        parent_milestone="real pilot",
        required_evidence_classes=[ValueEvidenceClass.EXTERNAL_USAGE],
        falsification_criteria=["usage was generated by the builder"],
    )
    task = _foundation_task(contract)
    receipts = tmp_path / "maintainer-receipts"
    raw = receipts / "raw/pilot-export.json"
    raw.parent.mkdir(parents=True)
    raw.write_text('{"attributable_sessions": 3}\n', encoding="utf-8")
    receipt = {
        "task_id": task.task_id,
        "metric": contract.primary_metric,
        "passed": True,
        "method": "Maintainer-imported attributable pilot telemetry",
        "source_commit": head,
        "preregistered_contract_sha256": value_contract_digest(contract),
        "raw_artifacts": ["raw/pilot-export.json"],
        "artifact_hashes": {
            "raw/pilot-export.json": hashlib.sha256(raw.read_bytes()).hexdigest()
        },
        "evidence_classes": [ValueEvidenceClass.EXTERNAL_USAGE.value],
        "falsification_results": {"usage was generated by the builder": True},
        "external_verification": "verified",
        "external_issuer": "pilot-operator-001",
        "external_reference": "pilot-export-2026-08-11",
        "external_observed_at": datetime.now(UTC).isoformat(),
    }
    (receipts / f"{task.task_id}.json").write_text(json.dumps(receipt), encoding="utf-8")
    monkeypatch.setenv("TCF_EXTERNAL_VALUE_RECEIPT_DIR", str(receipts))
    monkeypatch.setenv("TCF_EXTERNAL_VALUE_PUBLIC_KEY", str(tmp_path / "public.pem"))
    monkeypatch.setattr(value_module, "_assert_privileged_read_only", _accept_privileged_path)
    monkeypatch.setattr(
        value_module,
        "_verify_external_receipt_signature",
        _accept_external_signature,
    )

    result = evaluate_value_contract(repo_root=repo, task=task)

    assert result.assessment.status == ValueStatus.PASS
    assert result.assessment.commercially_validated is False


@pytest.mark.parametrize(
    ("task_id", "method"),
    [("WRONG_TASK", "Maintainer-imported evidence"), ("T900", "self-authored synthetic data")],
)
def test_external_value_rejects_wrong_task_or_self_authored_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    task_id: str,
    method: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("candidate\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "candidate"], cwd=repo, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True
    ).stdout.strip()
    contract = ValueContract(
        mode=ValueGateMode.EXTERNAL,
        metric_direction=MetricDirection.EXTERNAL,
        evidence_path="external/T900.json",
        required_evidence_classes=[ValueEvidenceClass.PAID],
    )
    task = _foundation_task(contract)
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    raw = receipts / "raw.json"
    raw.write_text("{}\n", encoding="utf-8")
    (receipts / "T900.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "metric": contract.primary_metric,
                "passed": True,
                "method": method,
                "source_commit": head,
                "preregistered_contract_sha256": value_contract_digest(contract),
                "raw_artifacts": ["raw.json"],
                "artifact_hashes": {"raw.json": hashlib.sha256(raw.read_bytes()).hexdigest()},
                "evidence_classes": [ValueEvidenceClass.PAID.value],
                "external_verification": "paid",
                "external_issuer": "claimed-issuer",
                "external_reference": "claimed-reference",
                "external_observed_at": datetime.now(UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TCF_EXTERNAL_VALUE_RECEIPT_DIR", str(receipts))
    monkeypatch.setenv("TCF_EXTERNAL_VALUE_PUBLIC_KEY", str(tmp_path / "public.pem"))
    monkeypatch.setattr(value_module, "_assert_privileged_read_only", _accept_privileged_path)
    monkeypatch.setattr(
        value_module,
        "_verify_external_receipt_signature",
        _accept_external_signature,
    )

    result = evaluate_value_contract(repo_root=repo, task=task)

    assert result.assessment.status == ValueStatus.EXTERNAL_EVIDENCE_REQUIRED
    assert result.assessment.commercially_validated is False


def test_external_receipt_signature_rejects_tampering(tmp_path: Path) -> None:
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    receipt = tmp_path / "T900.json"
    signature = tmp_path / "T900.json.sig"
    receipt.write_text('{"task_id":"T900"}\n', encoding="utf-8")
    subprocess.run(
        ["/usr/bin/openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "/usr/bin/openssl",
            "pkey",
            "-in",
            str(private_key),
            "-pubout",
            "-out",
            str(public_key),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "/usr/bin/openssl",
            "pkeyutl",
            "-sign",
            "-inkey",
            str(private_key),
            "-rawin",
            "-in",
            str(receipt),
            "-out",
            str(signature),
        ],
        check=True,
        capture_output=True,
    )
    value_module._verify_external_receipt_signature(  # pyright: ignore[reportPrivateUsage]
        receipt=receipt,
        signature=signature,
        public_key=public_key,
    )

    receipt.write_text('{"task_id":"T900","paid":true}\n', encoding="utf-8")
    with pytest.raises(ValueGateError, match="signature verification failed"):
        value_module._verify_external_receipt_signature(  # pyright: ignore[reportPrivateUsage]
            receipt=receipt,
            signature=signature,
            public_key=public_key,
        )


def test_external_truth_path_must_be_privileged_read_only(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}\n", encoding="utf-8")
    receipt.chmod(0o666)

    with pytest.raises(ValueGateError, match="root-owned"):
        value_module._assert_privileged_read_only(  # pyright: ignore[reportPrivateUsage]
            receipt
        )
