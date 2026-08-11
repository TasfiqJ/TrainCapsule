from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
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
from .v3.base import V3Model
from .v3.enums import Lane, WorkKind, WorkStatus
from .v3.enums import RiskTier as V3RiskTier
from .v3.work_items import WorkItem


class ValueGateError(RuntimeError):
    pass


class DecisionValueOutcome(StrEnum):
    NATIVE_WORKFLOW_SUFFICIENT = "NATIVE_WORKFLOW_SUFFICIENT"
    NO_INCREMENTAL_DECISION_VALUE = "NO_INCREMENTAL_DECISION_VALUE"
    TECHNICALLY_VALID_BUT_NOT_ECONOMIC = "TECHNICALLY_VALID_BUT_NOT_ECONOMIC"
    INCREMENTAL_DECISION_VALUE_DEMONSTRATED = "INCREMENTAL_DECISION_VALUE_DEMONSTRATED"
    EXTERNAL_EVIDENCE_REQUIRED = "EXTERNAL_EVIDENCE_REQUIRED"


class DecisionValueResult(V3Model):
    work_item_id: str
    evaluated: bool
    outcome: DecisionValueOutcome
    resulting_status: WorkStatus
    rationale: str = Field(min_length=1)
    evidence_refs: list[str]
    appended_work_item_ids: list[str] = Field(default_factory=list[str], max_length=0)


def requires_decision_value_gate(item: WorkItem) -> bool:
    """Return whether V3 policy requires a decision-level value judgment."""

    text = f"{item.title} {item.decision_contribution} {item.customer_outcome}".lower()
    if item.kind is WorkKind.MAINTENANCE or item.risk_tier is V3RiskTier.MECHANICAL:
        return False
    if item.lane is Lane.PRODUCT:
        return True
    if item.kind in {
        WorkKind.COMMERCIAL_EXPERIMENT,
        WorkKind.CONTROLLED_EXPERIMENT,
        WorkKind.EXTERNAL_EVIDENCE,
    }:
        return True
    return any(
        marker in text
        for marker in ("integration", "pack", "performance", "economic", "commercial")
    )


def apply_v3_value_decision(
    item: WorkItem,
    *,
    outcome: DecisionValueOutcome,
    rationale: str,
    evidence_refs: list[str],
) -> DecisionValueResult:
    """Apply one terminal/bounded V3 value outcome without creating more work."""

    evaluated = requires_decision_value_gate(item)
    if not evaluated:
        outcome = DecisionValueOutcome.INCREMENTAL_DECISION_VALUE_DEMONSTRATED
        resulting = WorkStatus.PASSED_ENGINEERING
        rationale = f"Inherited milestone necessity; engineering acceptance applies. {rationale}"
    elif outcome is DecisionValueOutcome.NATIVE_WORKFLOW_SUFFICIENT:
        resulting = WorkStatus.NATIVE_SUFFICIENT
    elif outcome in {
        DecisionValueOutcome.NO_INCREMENTAL_DECISION_VALUE,
        DecisionValueOutcome.TECHNICALLY_VALID_BUT_NOT_ECONOMIC,
    }:
        resulting = WorkStatus.REJECTED_VALUE
    elif outcome is DecisionValueOutcome.EXTERNAL_EVIDENCE_REQUIRED:
        resulting = WorkStatus.WAITING_EXTERNAL
    else:
        resulting = WorkStatus.PASSED_ENGINEERING
    if evaluated and not evidence_refs:
        raise ValueGateError("decision-level value outcomes require evidence references")
    return DecisionValueResult(
        work_item_id=item.work_item_id,
        evaluated=evaluated,
        outcome=outcome,
        resulting_status=resulting,
        rationale=rationale,
        evidence_refs=evidence_refs,
        appended_work_item_ids=[],
    )


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
    external_issuer: str | None = None
    external_reference: str | None = None
    external_observed_at: datetime | None = None
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


def _load_external_evidence(
    repo_root: Path, task: TaskPacket
) -> tuple[ValueEvidence, Path, Path]:
    """Load a maintainer-controlled receipt that is outside the candidate repository.

    External adoption, payment, and maintainer confirmation are facts the autonomous
    builder cannot attest for itself.  The receipt root is deliberately supplied by the
    trusted launcher and must not resolve inside the repository.
    """

    root_value = os.getenv("TCF_EXTERNAL_VALUE_RECEIPT_DIR", "").strip()
    public_key_value = os.getenv("TCF_EXTERNAL_VALUE_PUBLIC_KEY", "").strip()
    if not root_value:
        raise ValueGateError(
            "TCF_EXTERNAL_VALUE_RECEIPT_DIR is unset; external truth remains unverified"
        )
    if not public_key_value:
        raise ValueGateError(
            "TCF_EXTERNAL_VALUE_PUBLIC_KEY is unset; external truth remains unverified"
        )
    root = Path(root_value).expanduser().resolve()
    public_key = Path(public_key_value).expanduser().resolve()
    try:
        root.relative_to(repo_root.resolve())
    except ValueError:
        pass
    else:
        raise ValueGateError("External value receipts must live outside the candidate repository")
    for protected in (root, public_key):
        _assert_privileged_read_only(protected)
    path = (root / f"{task.task_id}.json").resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:  # pragma: no cover - task IDs are schema constrained
        raise ValueGateError("External value receipt path escapes its trusted root") from exc
    if not path.is_file():
        raise ValueGateError(f"Trusted external value receipt is missing for {task.task_id}")
    signature = path.with_suffix(path.suffix + ".sig")
    for protected in (path, signature):
        _assert_privileged_read_only(protected)
    _verify_external_receipt_signature(
        receipt=path,
        signature=signature,
        public_key=public_key,
    )
    try:
        evidence = ValueEvidence.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueGateError(f"Trusted external value receipt is unreadable: {exc}") from exc
    if evidence.metric != task.value_contract.primary_metric:
        raise ValueGateError(
            f"External receipt metric {evidence.metric!r} does not match "
            f"{task.value_contract.primary_metric!r}"
        )
    return evidence, root, path


def _assert_privileged_read_only(path: Path) -> None:
    """Require external truth material to be immutable to the unprivileged factory account."""

    for protected in (path, *path.parents):
        try:
            metadata = protected.stat()
        except OSError as exc:
            raise ValueGateError(
                f"Trusted external evidence path is unavailable: {protected}"
            ) from exc
        if metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise ValueGateError(
                "Trusted external evidence and every parent must be root-owned and not "
                f"group/world writable: {protected}"
            )


def _verify_external_receipt_signature(
    *, receipt: Path, signature: Path, public_key: Path
) -> None:
    """Verify an Ed25519 detached signature using the launcher-pinned public key."""

    key_type = subprocess.run(
        ["/usr/bin/openssl", "pkey", "-pubin", "-in", str(public_key), "-text", "-noout"],
        text=True,
        capture_output=True,
        check=False,
    )
    if key_type.returncode != 0 or "ED25519" not in (key_type.stdout + key_type.stderr).upper():
        raise ValueGateError("External value public key is not a valid Ed25519 public key")
    verified = subprocess.run(
        [
            "/usr/bin/openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(public_key),
            "-rawin",
            "-in",
            str(receipt),
            "-sigfile",
            str(signature),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if verified.returncode != 0:
        raise ValueGateError("External value receipt signature verification failed")


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
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if dirty.returncode != 0 or dirty.stdout.strip():
        raise ValueGateError("Value evidence can certify only a clean committed candidate")
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
    for raw, expected_hash in evidence.artifact_hashes.items():
        path = _safe_repo_path(repo_root, raw)
        if expected_hash == "DELETED":
            if path.exists():
                raise ValueGateError(
                    f"Value evidence says changed path was deleted but it exists: {raw}"
                )
            continue
        if len(expected_hash) != 64 or any(
            char not in "0123456789abcdef" for char in expected_hash
        ):
            raise ValueGateError(f"Value artifact has invalid SHA-256: {raw}")
        if not path.is_file():
            raise ValueGateError(f"Value artifact is missing: {raw}")
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise ValueGateError(f"Value artifact digest mismatch: {raw}")
    for raw in evidence.raw_artifacts:
        if raw not in evidence.artifact_hashes:
            raise ValueGateError(f"Value raw artifact has no recorded SHA-256: {raw}")

    changed = subprocess.run(
        ["git", "diff", "--name-only", "-z", f"{evidence.source_commit}..{candidate_head}"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if changed.returncode != 0:
        raise ValueGateError("Cannot enumerate the candidate surface covered by value evidence")
    changed_paths = {
        value.decode("utf-8", errors="strict")
        for value in changed.stdout.split(b"\0")
        if value
    }
    evidence_path = contract.evidence_path or ""
    uncovered = sorted(changed_paths - {evidence_path} - set(evidence.artifact_hashes))
    if uncovered:
        raise ValueGateError(
            "Value evidence does not hash every candidate change since source_commit: "
            + ", ".join(uncovered)
        )
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


def _verify_external_evidence(
    *, repo_root: Path, task: TaskPacket, evidence: ValueEvidence, receipt_root: Path
) -> None:
    contract = task.value_contract
    if evidence.task_id != task.task_id:
        raise ValueGateError(
            f"External receipt task_id={evidence.task_id!r} does not match {task.task_id!r}"
        )
    if evidence.source_commit != _git_head(repo_root):
        raise ValueGateError("External receipt is not bound to the exact candidate SHA")
    if evidence.preregistered_contract_sha256 != value_contract_digest(contract):
        raise ValueGateError("External receipt is not bound to the frozen value contract")
    required_classes = set(contract.required_evidence_classes)
    observed_classes = set(evidence.evidence_classes)
    missing_classes = sorted(value.value for value in required_classes - observed_classes)
    if missing_classes:
        raise ValueGateError(f"External receipt is missing required classes: {missing_classes}")
    if evidence.passed is not True:
        raise ValueGateError("External receipt does not record a passing attributable outcome")
    method = evidence.method.strip().lower()
    if not method or any(
        term in method for term in ("self-authored", "model-written", "synthetic")
    ):
        raise ValueGateError("External receipt method is missing or self-authored/synthetic")
    if not (evidence.external_issuer or "").strip():
        raise ValueGateError("External receipt has no attributable issuer")
    if not (evidence.external_reference or "").strip():
        raise ValueGateError("External receipt has no independently inspectable reference")
    if evidence.external_observed_at is None:
        raise ValueGateError("External receipt has no observation timestamp")
    observed_at = evidence.external_observed_at
    if observed_at.tzinfo is None:
        raise ValueGateError("External receipt timestamp must include a timezone")
    if observed_at.astimezone(UTC) > datetime.now(UTC):
        raise ValueGateError("External receipt timestamp is in the future")
    if not evidence.raw_artifacts:
        raise ValueGateError("External receipt has no inspectable raw artifacts")
    for raw in evidence.raw_artifacts:
        path = (receipt_root / raw).resolve()
        try:
            path.relative_to(receipt_root)
        except ValueError as exc:
            raise ValueGateError(
                f"External artifact escapes the trusted receipt root: {raw}"
            ) from exc
        _assert_privileged_read_only(path)
        expected_hash = evidence.artifact_hashes.get(raw)
        if not expected_hash or len(expected_hash) != 64:
            raise ValueGateError(f"External artifact has no valid SHA-256: {raw}")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise ValueGateError(f"External artifact is missing or has the wrong digest: {raw}")
    missing_falsifications = [
        item
        for item in contract.falsification_criteria
        if evidence.falsification_results.get(item) is not True
    ]
    if missing_falsifications:
        raise ValueGateError(
            "External receipt did not execute every predeclared falsification attempt: "
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
            evidence = _load_evidence(repo_root, contract)
            if evidence.task_id != task.task_id:
                raise ValueGateError(
                    f"Value evidence task_id={evidence.task_id!r} does not match "
                    f"{task.task_id!r}"
                )
            _verify_measured_evidence(
                repo_root=repo_root,
                contract=contract,
                evidence=evidence,
            )
            failed_conditions = [
                name
                for name in contract.required_conditions
                if evidence.conditions.get(name) is not True
            ]
            capability_passed = evidence.passed is True and not failed_conditions
            assessment = ValueAssessment(
                status=(ValueStatus.PASS if capability_passed else ValueStatus.REDESIGN),
                summary=(
                    "Candidate-bound foundational capability evidence passed. This proves a "
                    "technical dependency, not customer demand."
                    if capability_passed
                    else "Foundational capability evidence is missing or falsified."
                ),
                contract_mode=contract.mode,
                primary_metric=contract.primary_metric,
                evidence_paths=[contract.evidence_path] if contract.evidence_path else [],
                evidence_classes=evidence.evidence_classes,
                falsification_attempts=list(evidence.falsification_results),
                threshold=contract.minimum_material_improvement,
                limitations=[
                    *evidence.limitations,
                    *[
                        f"Required condition failed or missing: {name}"
                        for name in failed_conditions
                    ],
                    "Commercial willingness to pay remains unproven until external "
                    "revealed-preference evidence exists."
                ],
                redesign_actions=(
                    []
                    if capability_passed
                    else ["Return the failed conditions and raw artifacts to the Claude owner."]
                ),
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
            evidence, receipt_root, receipt_path = _load_external_evidence(repo_root, task)
            _verify_external_evidence(
                repo_root=repo_root,
                task=task,
                evidence=evidence,
                receipt_root=receipt_root,
            )
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
                evidence_paths=[],
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
                evidence_paths=[str(receipt_path)],
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
                evidence_paths=[str(receipt_path)],
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
