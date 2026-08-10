from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    MetricDirection,
    TaskPacket,
    ValueAssessment,
    ValueContract,
    ValueEvidenceClass,
    ValueGateMode,
    ValueStatus,
)
from .util import write_json


class ValueGateError(RuntimeError):
    pass


class ValueEvidence(BaseModel):
    """Machine-readable evidence emitted by a task's deterministic measurement command."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    metric: str
    baseline_value: float | None = None
    observed_value: float | None = None
    passed: bool | None = None
    conditions: dict[str, bool] = Field(default_factory=dict)
    measurement_unit: str | None = None
    method: str
    measurement_command: str | None = None
    source_commit: str | None = None
    environment_digest: str | None = None
    preregistered_contract_sha256: str | None = None
    sample_size: int | None = Field(default=None, ge=1)
    raw_artifacts: list[str] = Field(default_factory=list)
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    evidence_classes: list[ValueEvidenceClass] = Field(default_factory=list[ValueEvidenceClass])
    falsification_results: dict[str, bool] = Field(default_factory=dict)
    external_verification: str | None = None
    limitations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ValueGateResult:
    assessment: ValueAssessment
    evidence: ValueEvidence | None


def _safe_repo_path(repo_root: Path, raw: str) -> Path:
    path = (repo_root / raw).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueGateError(f"Value evidence escapes repository: {raw}") from exc
    return path


def _load_evidence(repo_root: Path, contract: ValueContract) -> ValueEvidence:
    if not contract.evidence_path:
        raise ValueGateError("Value contract has no evidence path")
    path = _safe_repo_path(repo_root, contract.evidence_path)
    if not path.is_file():
        raise ValueGateError(f"Required value evidence is missing: {contract.evidence_path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueGateError(f"Value evidence is unreadable: {path}: {exc}") from exc
    evidence = ValueEvidence.model_validate(raw)
    if evidence.metric != contract.primary_metric:
        raise ValueGateError(
            f"Value evidence metric {evidence.metric!r} does not match predeclared metric "
            f"{contract.primary_metric!r}"
        )
    return evidence


def value_contract_digest(contract: ValueContract) -> str:
    payload = json.dumps(
        contract.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _git_head(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueGateError(f"Cannot identify candidate commit: {result.stderr.strip()}")
    return result.stdout.strip()


def _verify_measured_evidence(
    *, repo_root: Path, contract: ValueContract, evidence: ValueEvidence
) -> None:
    if not evidence.method.strip():
        raise ValueGateError("Measured value evidence has no method")
    if not (evidence.measurement_command or "").strip():
        raise ValueGateError("Measured value evidence has no executable measurement_command")
    if not evidence.source_commit:
        raise ValueGateError("Measured value evidence has no source_commit")
    candidate_head = _git_head(repo_root)
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", evidence.source_commit, candidate_head],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if ancestry.returncode != 0:
        raise ValueGateError(
            "Value evidence source_commit is not an ancestor of the exact candidate under review"
        )
    expected_contract = value_contract_digest(contract)
    if evidence.preregistered_contract_sha256 != expected_contract:
        raise ValueGateError(
            "Value evidence was not generated against the frozen predeclared contract digest"
        )
    required_classes = set(contract.required_evidence_classes)
    observed_classes = set(evidence.evidence_classes)
    missing_classes = sorted(value.value for value in required_classes - observed_classes)
    if missing_classes:
        raise ValueGateError(f"Value evidence is missing required classes: {missing_classes}")
    if not evidence.raw_artifacts:
        raise ValueGateError("Measured value evidence must name raw, inspectable artifacts")
    for raw in evidence.raw_artifacts:
        path = _safe_repo_path(repo_root, raw)
        if not path.is_file():
            raise ValueGateError(f"Value raw artifact is missing: {raw}")
        expected_hash = evidence.artifact_hashes.get(raw)
        if not expected_hash:
            raise ValueGateError(f"Value raw artifact has no recorded SHA-256: {raw}")
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise ValueGateError(f"Value raw artifact digest mismatch: {raw}")
    missing_falsifications = [
        item
        for item in contract.falsification_criteria
        if evidence.falsification_results.get(item) is not True
    ]
    if missing_falsifications:
        raise ValueGateError(
            "The evidence did not execute every predeclared falsification attempt: "
            + "; ".join(missing_falsifications)
        )


def _relative_improvement(*, direction: MetricDirection, baseline: float, observed: float) -> float:
    """Return signed percentage improvement, where positive is better.

    When the baseline is zero, an absolute delta is used because a relative percentage is
    undefined. The unit remains whatever the contract declares and must be interpreted in the
    threshold rationale.
    """

    if direction == MetricDirection.INCREASE:
        delta = observed - baseline
    elif direction == MetricDirection.DECREASE:
        delta = baseline - observed
    else:
        raise ValueGateError(f"Relative improvement unsupported for {direction.value}")
    if baseline == 0:
        return delta
    return (delta / abs(baseline)) * 100.0


def evaluate_value_contract(
    *, repo_root: Path, task: TaskPacket, artifact_dir: Path | None = None
) -> ValueGateResult:
    """Evaluate the task's predeclared materiality contract without model judgment.

    This gate intentionally distinguishes technical materiality from commercial validation.
    A technically significant result may pass while `commercially_validated` remains false.
    An external contract can only pass after real, independently verifiable behavior evidence;
    an LLM report or synthetic persona is never accepted as a substitute.
    """

    contract = task.value_contract
    evidence: ValueEvidence | None = None

    if not contract.required or contract.mode == ValueGateMode.NOT_REQUIRED:
        assessment = ValueAssessment(
            status=ValueStatus.PASS,
            summary="Value gate is explicitly not required for this internal control task.",
            contract_mode=contract.mode,
            primary_metric=contract.primary_metric,
            threshold=contract.minimum_material_improvement,
            commercially_validated=False,
        )
    elif contract.mode == ValueGateMode.FOUNDATIONAL:
        required_text = [
            contract.target_user,
            contract.job_to_be_done,
            contract.customer_outcome,
            contract.causal_mechanism,
            contract.parent_milestone or "",
            contract.revenue_linkage,
        ]
        if any(not value.strip() for value in required_text):
            assessment = ValueAssessment(
                status=ValueStatus.FAIL,
                summary="Foundational task does not identify a complete user-value chain.",
                contract_mode=contract.mode,
                primary_metric=contract.primary_metric,
                threshold=contract.minimum_material_improvement,
                limitations=["Missing target user, job, mechanism, milestone, or revenue linkage."],
                redesign_actions=["Rewrite the value contract before implementing the feature."],
            )
        else:
            assessment = ValueAssessment(
                status=ValueStatus.PASS,
                summary=(
                    "Foundational capability is tied to a predeclared sellable milestone. "
                    "This is dependency evidence, not proof of customer demand."
                ),
                contract_mode=contract.mode,
                primary_metric=contract.primary_metric,
                evidence_classes=[ValueEvidenceClass.FOUNDATIONAL],
                threshold=contract.minimum_material_improvement,
                limitations=[
                    "Commercial willingness to pay remains unproven until external "
                    "revealed-preference evidence exists."
                ],
                commercially_validated=False,
            )
    elif contract.mode == ValueGateMode.MEASURED:
        evidence = _load_evidence(repo_root, contract)
        if evidence.task_id != task.task_id:
            raise ValueGateError(
                f"Value evidence task_id={evidence.task_id!r} does not match {task.task_id!r}"
            )
        _verify_measured_evidence(repo_root=repo_root, contract=contract, evidence=evidence)
        baseline = (
            evidence.baseline_value
            if evidence.baseline_value is not None
            else contract.baseline_value
        )
        observed = evidence.observed_value
        threshold = contract.minimum_material_improvement
        if contract.metric_direction == MetricDirection.BINARY:
            condition_results = [
                evidence.conditions.get(name) is True for name in contract.required_conditions
            ]
            all_conditions = all(condition_results) if contract.required_conditions else True
            material = 1.0 if evidence.passed is True and all_conditions else 0.0
            passed = (
                evidence.passed is True and all_conditions and material >= float(threshold or 1.0)
            )
        else:
            if baseline is None or observed is None or threshold is None:
                raise ValueGateError(
                    "Measured non-binary evidence requires baseline, observed value, and threshold"
                )
            material = _relative_improvement(
                direction=contract.metric_direction,
                baseline=baseline,
                observed=observed,
            )
            passed = material >= threshold
        status = ValueStatus.PASS if passed else ValueStatus.REDESIGN
        assessment = ValueAssessment(
            status=status,
            summary=(
                "Predeclared materiality threshold passed."
                if passed
                else "Feature works technically but misses the predeclared materiality threshold."
            ),
            contract_mode=contract.mode,
            primary_metric=contract.primary_metric,
            baseline_value=baseline,
            observed_value=observed,
            material_improvement=material,
            threshold=threshold,
            evidence_paths=[contract.evidence_path] if contract.evidence_path else [],
            evidence_classes=evidence.evidence_classes,
            falsification_attempts=list(evidence.falsification_results),
            limitations=[
                *evidence.limitations,
                *[
                    f"Required condition failed or missing: {name}"
                    for name in contract.required_conditions
                    if evidence.conditions.get(name) is not True
                ],
            ],
            redesign_actions=(
                []
                if passed
                else [
                    "Return to specification and change the mechanism, scope, or target outcome.",
                    "Do not lower the threshold after seeing the result unless a new ADR "
                    "justifies it with external evidence.",
                ]
            ),
            commercially_validated=False,
        )
    elif contract.mode == ValueGateMode.EXTERNAL:
        try:
            evidence = _load_evidence(repo_root, contract)
        except ValueGateError as exc:
            assessment = ValueAssessment(
                status=ValueStatus.EXTERNAL_EVIDENCE_REQUIRED,
                summary=(
                    "External adoption, maintainer confirmation, or payment evidence is not "
                    "yet present. "
                    "The autonomous builder must wait rather than manufacture it."
                ),
                contract_mode=contract.mode,
                primary_metric=contract.primary_metric,
                evidence_paths=[contract.evidence_path] if contract.evidence_path else [],
                limitations=[str(exc)],
                commercially_validated=False,
            )
            if artifact_dir is not None:
                artifact_dir.mkdir(parents=True, exist_ok=True)
                write_json(
                    artifact_dir / "value-assessment.json",
                    assessment.model_dump(mode="json"),
                )
            return ValueGateResult(assessment=assessment, evidence=None)
        external_classes = {
            ValueEvidenceClass.EXTERNAL_USAGE,
            ValueEvidenceClass.PAID,
            ValueEvidenceClass.UPSTREAM,
        }
        has_external_class = bool(set(evidence.evidence_classes) & external_classes)
        verified = (evidence.external_verification or "").strip().lower() in {
            "verified",
            "maintainer-confirmed",
            "paid",
            "renewed",
        }
        if has_external_class and verified:
            assessment = ValueAssessment(
                status=ValueStatus.PASS,
                summary="Real external behavior evidence satisfies the declared commercial gate.",
                contract_mode=contract.mode,
                primary_metric=contract.primary_metric,
                evidence_paths=[contract.evidence_path] if contract.evidence_path else [],
                evidence_classes=evidence.evidence_classes,
                limitations=evidence.limitations,
                commercially_validated=ValueEvidenceClass.PAID in evidence.evidence_classes,
            )
        else:
            assessment = ValueAssessment(
                status=ValueStatus.EXTERNAL_EVIDENCE_REQUIRED,
                summary=(
                    "The product can be technically complete, but customer demand or "
                    "ecosystem adoption "
                    "cannot be manufactured by the autonomous builder."
                ),
                contract_mode=contract.mode,
                primary_metric=contract.primary_metric,
                evidence_paths=[contract.evidence_path] if contract.evidence_path else [],
                evidence_classes=evidence.evidence_classes,
                limitations=[
                    *evidence.limitations,
                    "No independently verified usage, maintainer, or paid "
                    "revealed-preference signal was found.",
                ],
                commercially_validated=False,
            )
    else:  # pragma: no cover - exhaustive enum guard
        raise ValueGateError(f"Unsupported value gate mode: {contract.mode}")

    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        write_json(artifact_dir / "value-assessment.json", assessment.model_dump(mode="json"))
        if evidence is not None:
            write_json(
                artifact_dir / "value-evidence-normalized.json", evidence.model_dump(mode="json")
            )
    return ValueGateResult(assessment=assessment, evidence=evidence)


def assert_material_value(
    *, repo_root: Path, task: TaskPacket, artifact_dir: Path | None = None
) -> ValueGateResult:
    result = evaluate_value_contract(repo_root=repo_root, task=task, artifact_dir=artifact_dir)
    if result.assessment.status in {ValueStatus.FAIL, ValueStatus.REDESIGN, ValueStatus.UNKNOWN}:
        raise ValueGateError(result.assessment.summary)
    if (
        task.value_contract.mode != ValueGateMode.EXTERNAL
        and result.assessment.status == ValueStatus.EXTERNAL_EVIDENCE_REQUIRED
    ):
        raise ValueGateError(result.assessment.summary)
    return result
