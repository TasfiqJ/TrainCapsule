from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import stat
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, model_validator

from tcfactory.v3.base import DIGEST_PATTERN, SHA_PATTERN, sha256_digest
from tcfactory.v3.completion_artifacts import SEMANTIC_OUTPUT_SPECS
from tcfactory.v3.completion_verification import (
    DeliveryMeasurement,
    ReductionCandidateInput,
)
from tcfactory.v3.contracts_v31 import (
    DecisionValueResultV31,
    NativeSubstituteBenchmarkV31,
    V31Model,
)
from tcfactory.v3.enums import Lane, WorkKind
from tcfactory.v3.native_value_gate import NativeValueGatePolicyV31
from tcfactory.v3.traincheck_differential import TrainCheckDifferentialRequest
from tcfactory.v3.work_items import WorkItem


class TaskCompilationError(RuntimeError):
    pass


class EvidenceClass(StrEnum):
    ENGINEERING = "ENGINEERING"
    RESEARCH = "RESEARCH"
    TRUST = "TRUST"
    FACTORY = "FACTORY"


class ExecutionVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class TruthState(StrEnum):
    CLEAR = "CLEAR"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class FindingSeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingOwnerClass(StrEnum):
    CANDIDATE = "CANDIDATE"
    FACTORY = "FACTORY"
    MACHINE_POLICY_AUTHORITY = "MACHINE_POLICY_AUTHORITY"
    EXTERNAL_SYSTEM = "EXTERNAL_SYSTEM"
    UNKNOWN = "UNKNOWN"


class ResumeState(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    RESUMABLE = "RESUMABLE"
    EXHAUSTED = "EXHAUSTED"
    UNSUPPORTED = "UNSUPPORTED"


class NextAuthorizedAction(StrEnum):
    VERIFY = "VERIFY"
    REPAIR = "REPAIR"
    RESUME = "RESUME"
    REPLAN = "REPLAN"
    BLOCK_POLICY = "BLOCK_POLICY"
    BLOCK_EXTERNAL = "BLOCK_EXTERNAL"
    NONE = "NONE"


class OutputDeclarationV31(V31Model):
    output_id: str = Field(pattern=r"^OUT:V3:[A-Z]+:[0-9]{3}:[A-Z_]+$")
    path: str = Field(min_length=1, max_length=512)
    schema_id: str = Field(pattern=r"^traincapsule\.v3\.1\.[a-z0-9.-]+$")
    required: bool
    evidence_class: EvidenceClass
    mutating_owner: Literal["CANDIDATE_AGENT", "CONTROLLER"]
    readers: list[str] = Field(min_length=1, max_length=16)
    content_digest_required: bool
    external_authority_required: bool
    maximum_bytes: int = Field(ge=1, le=100_000_000)

    @model_validator(mode="after")
    def normalized_path_and_readers(self) -> OutputDeclarationV31:
        _validate_relative_path(self.path)
        if len(self.readers) != len(set(self.readers)):
            raise ValueError("output readers must be unique")
        return self


class BashCommandRuleV31(V31Model):
    executable: Literal["git", "uv"]
    argument_prefix: list[str] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def deny_mutating_or_privileged_commands(self) -> BashCommandRuleV31:
        joined = " ".join([self.executable, *self.argument_prefix]).lower()
        forbidden = {
            " push",
            " commit",
            " checkout",
            " switch",
            " branch",
            " reset",
            " clean",
            "gh ",
            "sudo",
            "service",
            "systemctl",
            "verifier",
        }
        if any(token in joined for token in forbidden):
            raise ValueError("candidate command policy contains a forbidden operation")
        return self


class ToolPolicyV31(V31Model):
    mutating_owner: bool
    allowed_tools: list[str] = Field(min_length=1, max_length=8)
    bash_rules: list[BashCommandRuleV31] = Field(max_length=16)

    @model_validator(mode="after")
    def tools_match_mutability(self) -> ToolPolicyV31:
        tools = set(self.allowed_tools)
        if len(tools) != len(self.allowed_tools):
            raise ValueError("allowed tools must be unique")
        if self.mutating_owner:
            if not {"Write", "Edit"}.issubset(tools):
                raise ValueError("mutating owner requires Write and Edit")
        elif {"Write", "Edit"} & tools:
            raise ValueError("read-only request cannot receive Write or Edit")
        if ("Bash" in tools) != bool(self.bash_rules):
            raise ValueError("Bash tool and command rules must be declared together")
        return self


class CompiledTaskContractV31(V31Model):
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    lane: Lane
    work_kind: WorkKind
    task_packet_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    source_generation_id: str = Field(min_length=1, max_length=128)
    source_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    context_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    allowed_write_paths: list[str] = Field(min_length=1, max_length=32)
    forbidden_paths: list[str] = Field(min_length=1, max_length=64)
    mutating_work_item: bool
    outputs: list[OutputDeclarationV31] = Field(min_length=1, max_length=16)
    read_only_tools: ToolPolicyV31
    mutating_tools: ToolPolicyV31 | None
    contract_digest: str = Field(pattern=DIGEST_PATTERN.pattern)

    @model_validator(mode="after")
    def coherent_contract(self) -> CompiledTaskContractV31:
        for pattern in [*self.allowed_write_paths, *self.forbidden_paths]:
            _validate_scope_pattern(pattern)
        if self.read_only_tools.mutating_owner:
            raise ValueError("readOnlyTools cannot be a mutating-owner policy")
        if self.mutating_work_item != (self.mutating_tools is not None):
            raise ValueError("mutating work and mutating tool policy disagree")
        output_ids = [output.output_id for output in self.outputs]
        if len(output_ids) != len(set(output_ids)):
            raise ValueError("output IDs must be unique")
        output_paths = [output.path for output in self.outputs]
        if len(output_paths) != len(set(output_paths)):
            raise ValueError("output paths must be unique")
        for output in self.outputs:
            if not _matches_any(output.path, self.allowed_write_paths):
                raise ValueError(f"declared output is outside task scope: {output.path}")
            if _matches_any(output.path, self.forbidden_paths):
                raise ValueError(f"declared output is forbidden: {output.path}")
        expected = _contract_digest(self.model_dump(mode="json", by_alias=True), omit_digest=True)
        if self.contract_digest != expected:
            raise ValueError("task contract digest mismatch")
        return self


class CriterionResultV31(V31Model):
    criterion_id: str = Field(pattern=r"^CRIT:[A-Z0-9:_-]+$")
    passed: bool
    evidence_digests: list[str] = Field(min_length=1, max_length=32)
    explanation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_evidence_digests(self) -> CriterionResultV31:
        _validate_digest_list(self.evidence_digests, "criterion evidence")
        return self


class AgentFindingV31(V31Model):
    finding_id: str = Field(pattern=r"^FIND:[A-Z0-9:_-]+$")
    severity: FindingSeverity
    blocking: bool
    criterion_id: str = Field(pattern=r"^CRIT:[A-Z0-9:_-]+$")
    fingerprint: str = Field(pattern=DIGEST_PATTERN.pattern)
    evidence_digests: list[str] = Field(min_length=1, max_length=32)
    expected: str = Field(min_length=1, max_length=4000)
    observed: str = Field(min_length=1, max_length=4000)
    owner_class: FindingOwnerClass
    minimal_repair: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_evidence_digests(self) -> AgentFindingV31:
        _validate_digest_list(self.evidence_digests, "finding evidence")
        return self


class CommandResultV31(V31Model):
    executable: str = Field(pattern=r"^[a-zA-Z0-9._+-]+$")
    arguments: list[str] = Field(max_length=64)
    exit_code: int = Field(ge=0, le=255)
    stdout_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    stderr_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    wall_time_seconds: float = Field(ge=0, le=14_400)


class TestResultV31(V31Model):
    test_id: str = Field(min_length=1, max_length=256)
    passed: bool
    evidence_digest: str = Field(pattern=DIGEST_PATTERN.pattern)


class MaterializedOutputV31(V31Model):
    output_id: str = Field(pattern=r"^OUT:V3:[A-Z]+:[0-9]{3}:[A-Z_]+$")
    path: str = Field(min_length=1, max_length=512)
    schema_id: str = Field(pattern=r"^traincapsule\.v3\.1\.[a-z0-9.-]+$")
    content_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    size_bytes: int = Field(ge=1, le=100_000_000)

    @model_validator(mode="after")
    def normalized_path(self) -> MaterializedOutputV31:
        _validate_relative_path(self.path)
        return self


class ResourceUsageV31(V31Model):
    wall_time_seconds: float = Field(ge=0, le=14_400)
    turns: int = Field(ge=0, le=200)
    tokens: int = Field(ge=0, le=250_000)
    cost_usd_equivalent: float = Field(ge=0, le=100)


class TaskResultArtifactV31(V31Model):
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    request_id: str = Field(pattern=r"^AREQ-[A-Z0-9_-]+$")
    verdict: ExecutionVerdict
    evidence_digests: list[str] = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=4000)
    limitations: list[str] = Field(max_length=64)

    @model_validator(mode="after")
    def validate_evidence_digests(self) -> TaskResultArtifactV31:
        _validate_digest_list(self.evidence_digests, "task-result evidence")
        return self


class AgentExecutionReportV31(V31Model):
    request_id: str = Field(pattern=r"^AREQ-[A-Z0-9_-]+$")
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    role: str = Field(min_length=1, max_length=64)
    owner_class: Literal["CANDIDATE_AGENT", "READ_ONLY_REVIEWER"]
    base_sha: str = Field(pattern=SHA_PATTERN.pattern)
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    source_generation_id: str = Field(min_length=1, max_length=128)
    source_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    context_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    task_packet_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    verdict: ExecutionVerdict
    truth_state: TruthState
    criterion_results: list[CriterionResultV31] = Field(min_length=1, max_length=128)
    findings: list[AgentFindingV31] = Field(max_length=256)
    finding_fingerprints: list[str] = Field(max_length=256)
    changed_files: list[str] = Field(max_length=512)
    commands_run: list[CommandResultV31] = Field(max_length=256)
    tests_run: list[TestResultV31] = Field(max_length=256)
    outputs: list[MaterializedOutputV31] = Field(max_length=16)
    artifact_digests: list[str] = Field(max_length=512)
    external_receipt_refs: list[str] = Field(max_length=64)
    native_disposition: str = Field(min_length=1, max_length=128)
    value_disposition: str = Field(min_length=1, max_length=128)
    limitations: list[str] = Field(max_length=64)
    resource_usage: ResourceUsageV31
    session_ref: str = Field(min_length=1, max_length=256)
    resume_state: ResumeState
    next_authorized_action: NextAuthorizedAction

    @model_validator(mode="after")
    def internally_coherent(self) -> AgentExecutionReportV31:
        for path in self.changed_files:
            _validate_relative_path(path)
        _validate_digest_list(self.finding_fingerprints, "finding fingerprints")
        _validate_digest_list(self.artifact_digests, "artifact digests")
        if len(self.finding_fingerprints) != len(set(self.finding_fingerprints)):
            raise ValueError("finding fingerprints must be unique")
        if {finding.fingerprint for finding in self.findings} != set(self.finding_fingerprints):
            raise ValueError("finding fingerprint index does not match findings")
        return self


_MUTATING_KINDS = {
    WorkKind.CODE,
    WorkKind.SPECIFICATION,
    WorkKind.RESEARCH,
    WorkKind.CONTROLLED_EXPERIMENT,
    WorkKind.MAINTENANCE,
    WorkKind.MIGRATION,
}

_LANE_WRITE_PATHS: dict[Lane, tuple[str, ...]] = {
    Lane.PRODUCT: (
        "packages/traincapsule-*/**",
        "schemas/product/**",
        "tests/product/**",
        "examples/product/**",
        "docs/product/**",
        "docs/evidence/product/**",
    ),
    Lane.MARKET: (
        "docs/market/**",
        "docs/evidence/market/**",
        "factory/external-evidence/market-metadata/**",
    ),
    Lane.COMPETITOR: (
        "docs/research/**",
        "docs/evidence/competitors/**",
        "factory/external-evidence/competitor-metadata/**",
    ),
    Lane.TRUST: (
        "tests/**",
        "docs/evidence/trust/**",
        "docs/threat-models/**",
        "factory/private-gate-requests/**",
    ),
    Lane.FACTORY: (
        "tcfactory/**",
        "config/**",
        "scripts/**",
        "prompts/**",
        "schemas/factory/**",
        "tests/test_v3_*.py",
        "docs/migrations/**",
    ),
}

_FORBIDDEN_PATHS = (
    "docs/source-of-truth/**",
    ".github/**",
    ".git/**",
    "verifier/**",
    "factory/policy/**",
    "config/active_generation.yaml",
)

_EVIDENCE_CLASS = {
    Lane.PRODUCT: EvidenceClass.ENGINEERING,
    Lane.MARKET: EvidenceClass.RESEARCH,
    Lane.COMPETITOR: EvidenceClass.RESEARCH,
    Lane.TRUST: EvidenceClass.TRUST,
    Lane.FACTORY: EvidenceClass.FACTORY,
}


def lane_path_policy_v31(item: WorkItem) -> tuple[list[str], list[str]]:
    return list(_LANE_WRITE_PATHS[item.lane]), list(_FORBIDDEN_PATHS)


def compile_task_contract_v31(
    item: WorkItem,
    *,
    task_packet_digest: str,
    source_generation_id: str,
    source_digest: str,
    context_digest: str,
) -> CompiledTaskContractV31:
    if not item.automatable:
        raise TaskCompilationError("non-automatable work cannot be compiled for a candidate agent")
    if item.kind in {
        WorkKind.EXTERNAL_EVIDENCE,
        WorkKind.COMMERCIAL_EXPERIMENT,
        WorkKind.MACHINE_POLICY_REVIEW,
    }:
        raise TaskCompilationError(
            "external or machine-policy authority work is not candidate-agent work"
        )

    mutating = item.kind in _MUTATING_KINDS
    allowed_paths = list(_LANE_WRITE_PATHS[item.lane])
    outputs = output_declarations_for_item_v31(item)
    read_only_tools = ToolPolicyV31(
        schema_version="3.1",
        mutating_owner=False,
        allowed_tools=["Read", "Glob", "Grep", "Bash"],
        bash_rules=_bash_rules(),
    )
    mutating_tools = (
        ToolPolicyV31(
            schema_version="3.1",
            mutating_owner=True,
            allowed_tools=["Read", "Glob", "Grep", "Bash", "Write", "Edit"],
            bash_rules=_bash_rules(),
        )
        if mutating
        else None
    )
    payload = {
        "schemaVersion": "3.1",
        "workItemId": item.work_item_id,
        "lane": item.lane.value,
        "workKind": item.kind.value,
        "taskPacketDigest": task_packet_digest,
        "sourceGenerationId": source_generation_id,
        "sourceDigest": source_digest,
        "contextDigest": context_digest,
        "allowedWritePaths": allowed_paths,
        "forbiddenPaths": list(_FORBIDDEN_PATHS),
        "mutatingWorkItem": mutating,
        "outputs": [entry.model_dump(mode="json", by_alias=True) for entry in outputs],
        "readOnlyTools": read_only_tools.model_dump(mode="json", by_alias=True),
        "mutatingTools": (
            mutating_tools.model_dump(mode="json", by_alias=True)
            if mutating_tools is not None
            else None
        ),
    }
    payload["contractDigest"] = _contract_digest(payload)
    return CompiledTaskContractV31.model_validate_json(json.dumps(payload))


def output_declarations_for_item_v31(item: WorkItem) -> list[OutputDeclarationV31]:
    result_path = _result_path(item)
    output_id = "OUT:" + item.work_item_id.replace("-", ":") + ":RESULT"
    declarations = [
        OutputDeclarationV31(
            schema_version="3.1",
            output_id=output_id,
            path=result_path,
            schema_id="traincapsule.v3.1.task-result",
            required=True,
            evidence_class=_EVIDENCE_CLASS[item.lane],
            mutating_owner="CANDIDATE_AGENT",
            readers=["CONTROLLER", "VERIFIER"],
            content_digest_required=True,
            external_authority_required=False,
            maximum_bytes=10_000_000,
        )
    ]
    semantic_output = SEMANTIC_OUTPUT_SPECS.get(item.work_item_id)
    if semantic_output is not None:
        declarations.append(
            OutputDeclarationV31(
                schema_version="3.1",
                output_id=semantic_output.output_id,
                path=semantic_output.relative_path,
                schema_id=semantic_output.schema_id,
                required=True,
                evidence_class=_EVIDENCE_CLASS[item.lane],
                mutating_owner="CANDIDATE_AGENT",
                readers=["CONTROLLER", "VERIFIER"],
                content_digest_required=True,
                external_authority_required=False,
                maximum_bytes=2_000_000,
            )
        )
    derived_inputs = {
        "V3-TRUST-005": (
            (
                "OUT:V3:TRUST:005:LEGAL_REDUCTION_INPUT",
                "docs/evidence/trust/v3-trust-005/legal-reduction-input.json",
                "traincapsule.v3.1.reduction-candidate-input",
            ),
            (
                "OUT:V3:TRUST:005:ILLEGAL_REDUCTION_INPUT",
                "docs/evidence/trust/v3-trust-005/illegal-reduction-input.json",
                "traincapsule.v3.1.reduction-candidate-input",
            ),
        ),
        "V3-REPEAT-006": (
            (
                "OUT:V3:REPEAT:006:ORIGINAL_DELIVERY",
                "docs/evidence/market/v3-repeat-006/original-delivery.json",
                "traincapsule.v3.1.delivery-measurement",
            ),
            (
                "OUT:V3:REPEAT:006:PROPOSED_DELIVERY",
                "docs/evidence/market/v3-repeat-006/proposed-delivery.json",
                "traincapsule.v3.1.delivery-measurement",
            ),
        ),
    }
    for derived_id, derived_path, schema_id in derived_inputs.get(item.work_item_id, ()):
        declarations.append(
            OutputDeclarationV31(
                schema_version="3.1",
                output_id=derived_id,
                path=derived_path,
                schema_id=schema_id,
                required=True,
                evidence_class=_EVIDENCE_CLASS[item.lane],
                mutating_owner="CANDIDATE_AGENT",
                readers=["CONTROLLER", "VERIFIER"],
                content_digest_required=True,
                external_authority_required=False,
                maximum_bytes=2_000_000,
            )
        )
    if item.kind is WorkKind.CONTROLLED_EXPERIMENT:
        slug = item.work_item_id.lower()
        root = {
            Lane.PRODUCT: f"docs/evidence/product/{slug}/native-value-runtime",
            Lane.MARKET: f"docs/evidence/market/{slug}/native-value-runtime",
            Lane.COMPETITOR: f"docs/evidence/competitors/{slug}/native-value-runtime",
            Lane.TRUST: f"docs/evidence/trust/{slug}/native-value-runtime",
            Lane.FACTORY: f"docs/migrations/evidence/{slug}/native-value-runtime",
        }[item.lane]
        declarations.extend(
            OutputDeclarationV31(
                schema_version="3.1",
                output_id=("OUT:" + item.work_item_id.replace("-", ":") + f":{suffix}"),
                path=f"{root}/{filename}",
                schema_id=schema_id,
                required=True,
                evidence_class=_EVIDENCE_CLASS[item.lane],
                mutating_owner="CANDIDATE_AGENT",
                readers=["CONTROLLER", "VERIFIER"],
                content_digest_required=True,
                external_authority_required=False,
                maximum_bytes=10_000_000,
            )
            for suffix, filename, schema_id in (
                (
                    "NATIVE_BENCHMARK",
                    "native-substitute-benchmark.json",
                    "traincapsule.v3.1.native-substitute-benchmark",
                ),
                (
                    "DECISION_VALUE",
                    "decision-value-result.json",
                    "traincapsule.v3.1.decision-value",
                ),
                (
                    "NATIVE_VALUE_POLICY",
                    "native-value-gate-policy.json",
                    "traincapsule.v3.1.native-value-gate-policy",
                ),
            )
        )
        if item.work_item_id == "V3-COMP-005":
            declarations.append(
                OutputDeclarationV31(
                    schema_version="3.1",
                    output_id="OUT:V3:COMP:005:TRAINCHECK_REQUEST",
                    path=f"{root}/traincheck-differential-request.json",
                    schema_id="traincapsule.v3.1.traincheck-differential-request",
                    required=True,
                    evidence_class=EvidenceClass.RESEARCH,
                    mutating_owner="CANDIDATE_AGENT",
                    readers=["CONTROLLER", "VERIFIER"],
                    content_digest_required=True,
                    external_authority_required=True,
                    maximum_bytes=1_000_000,
                )
            )
    return declarations


def tool_policy_for_request(
    contract: CompiledTaskContractV31, *, mutating_owner: bool
) -> ToolPolicyV31:
    if mutating_owner:
        if contract.mutating_tools is None:
            raise TaskCompilationError("read-only work item cannot grant mutation tools")
        return contract.mutating_tools
    return contract.read_only_tools


def validate_execution_report_v31(
    report: AgentExecutionReportV31,
    contract: CompiledTaskContractV31,
    *,
    candidate_root: Path,
    tool_policy: ToolPolicyV31 | None = None,
    expected_request_id: str | None = None,
    expected_role: str | None = None,
    expected_base_sha: str | None = None,
    expected_candidate_sha: str | None = None,
    expected_context_digest: str | None = None,
    actual_changed_files: list[str] | None = None,
) -> None:
    if report.work_item_id != contract.work_item_id:
        raise TaskCompilationError("execution report work item does not match contract")
    if report.source_generation_id != contract.source_generation_id:
        raise TaskCompilationError("execution report source generation does not match contract")
    for name in ("source_digest", "task_packet_digest"):
        if getattr(report, name) != getattr(contract, name):
            raise TaskCompilationError(f"execution report {name} does not match contract")
    required_context_digest = expected_context_digest or contract.context_digest
    if report.context_digest != required_context_digest:
        raise TaskCompilationError("execution report context_digest does not match request")
    expected_values = {
        "request_id": expected_request_id,
        "role": expected_role,
        "base_sha": expected_base_sha,
        "candidate_sha": expected_candidate_sha,
    }
    for name, expected in expected_values.items():
        if expected is not None and getattr(report, name) != expected:
            raise TaskCompilationError(f"execution report {name} does not match request")
    read_only_roles = {"audit", "adversary", "security", "integration_scout", "release"}
    expected_owner = "READ_ONLY_REVIEWER" if report.role in read_only_roles else "CANDIDATE_AGENT"
    if report.owner_class != expected_owner:
        raise TaskCompilationError(
            "execution report owner class does not match its role; "
            "a read-only reviewer cannot act as the candidate owner"
        )
    for reference in report.external_receipt_refs:
        parts = reference.split("@", 1)
        if (
            len(parts) != 2
            or not parts[0].startswith("XREC-")
            or DIGEST_PATTERN.fullmatch(parts[1]) is None
        ):
            raise TaskCompilationError("external receipt reference must be XREC-ID@sha256:<digest>")
    if report.owner_class == "READ_ONLY_REVIEWER" and report.changed_files:
        raise TaskCompilationError("read-only reviewer reported candidate mutations")
    for changed_file in report.changed_files:
        if not _matches_any(changed_file, contract.allowed_write_paths):
            raise TaskCompilationError(f"changed file is outside task scope: {changed_file}")
        if _matches_any(changed_file, contract.forbidden_paths):
            raise TaskCompilationError(f"changed file is forbidden: {changed_file}")
    if actual_changed_files is not None and sorted(report.changed_files) != sorted(
        actual_changed_files
    ):
        raise TaskCompilationError("execution report changed files do not match candidate diff")
    if tool_policy is not None:
        for command in report.commands_run:
            matching_rules = [
                rule
                for rule in tool_policy.bash_rules
                if command.executable == rule.executable
                and command.arguments[: len(rule.argument_prefix)] == rule.argument_prefix
            ]
            if not matching_rules:
                raise TaskCompilationError(
                    f"execution report contains undeclared command: {command.executable}"
                )

    declared = {output.output_id: output for output in contract.outputs}
    materialized = {output.output_id: output for output in report.outputs}
    if len(materialized) != len(report.outputs):
        raise TaskCompilationError("execution report contains duplicate output IDs")
    undeclared = sorted(set(materialized) - set(declared))
    if undeclared:
        raise TaskCompilationError(f"execution report contains undeclared outputs: {undeclared}")
    missing = sorted(
        output_id
        for output_id, declaration in declared.items()
        if declaration.required and output_id not in materialized
    )
    if missing:
        raise TaskCompilationError(f"execution report is missing required outputs: {missing}")
    for output_id, output in materialized.items():
        declaration = declared[output_id]
        if output.path != declaration.path or output.schema_id != declaration.schema_id:
            raise TaskCompilationError(f"output declaration mismatch: {output_id}")
        _verify_materialized_output(candidate_root, output, declaration)

    blocking = any(finding.blocking for finding in report.findings)
    criteria_pass = all(result.passed for result in report.criterion_results)
    if report.verdict is ExecutionVerdict.PASS:
        if blocking or not criteria_pass:
            raise TaskCompilationError("PASS report contains blocking or failed evidence")
        if report.truth_state is not TruthState.CLEAR:
            raise TaskCompilationError("PASS report requires CLEAR truth state")
        if report.next_authorized_action is not NextAuthorizedAction.VERIFY:
            raise TaskCompilationError("PASS report may authorize only verification")


def execution_report_schema() -> dict[str, object]:
    return AgentExecutionReportV31.model_json_schema(by_alias=True)


def _bash_rules() -> list[BashCommandRuleV31]:
    return [
        BashCommandRuleV31(
            schema_version="3.1", executable="git", argument_prefix=["diff", "--check"]
        ),
        BashCommandRuleV31(
            schema_version="3.1",
            executable="git",
            argument_prefix=["diff", "--name-only"],
        ),
        BashCommandRuleV31(
            schema_version="3.1", executable="uv", argument_prefix=["run", "pytest"]
        ),
        BashCommandRuleV31(
            schema_version="3.1",
            executable="uv",
            argument_prefix=["run", "ruff", "check"],
        ),
        BashCommandRuleV31(
            schema_version="3.1", executable="uv", argument_prefix=["run", "pyright"]
        ),
    ]


def _result_path(item: WorkItem) -> str:
    slug = item.work_item_id.lower()
    if item.lane is Lane.PRODUCT:
        return f"docs/evidence/product/{slug}/result.json"
    if item.lane is Lane.MARKET:
        return f"docs/market/{slug}/research-result.json"
    if item.lane is Lane.COMPETITOR:
        return f"docs/research/{slug}/capability-result.json"
    if item.lane is Lane.TRUST:
        return f"docs/evidence/trust/{slug}/result.json"
    return f"docs/migrations/evidence/{slug}/result.json"


def _verify_materialized_output(
    candidate_root: Path,
    output: MaterializedOutputV31,
    declaration: OutputDeclarationV31,
) -> None:
    candidate_root = candidate_root.resolve(strict=True)
    parts = PurePosixPath(output.path).parts
    root_fd = os.open(candidate_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    current_fd = root_fd
    opened: list[int] = []
    try:
        for part in parts[:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current_fd,
            )
            opened.append(next_fd)
            current_fd = next_fd
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current_fd)
        opened.append(file_fd)
        observed = os.fstat(file_fd)
        if not stat.S_ISREG(observed.st_mode):
            raise TaskCompilationError(f"materialized output is not a regular file: {output.path}")
        if observed.st_size != output.size_bytes or observed.st_size > declaration.maximum_bytes:
            raise TaskCompilationError(f"materialized output size mismatch: {output.path}")
        chunks: list[bytes] = []
        remaining = declaration.maximum_bytes + 1
        while remaining > 0:
            chunk = os.read(file_fd, min(1_048_576, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise TaskCompilationError(
            f"materialized output is missing or unsafe: {output.path}"
        ) from exc
    finally:
        for descriptor in reversed(opened):
            os.close(descriptor)
        os.close(root_fd)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    if digest != output.content_digest:
        raise TaskCompilationError(f"materialized output digest mismatch: {output.path}")
    validators = {
        "traincapsule.v3.1.task-result": TaskResultArtifactV31,
        "traincapsule.v3.1.native-substitute-benchmark": NativeSubstituteBenchmarkV31,
        "traincapsule.v3.1.decision-value": DecisionValueResultV31,
        "traincapsule.v3.1.native-value-gate-policy": NativeValueGatePolicyV31,
        "traincapsule.v3.1.traincheck-differential-request": (TrainCheckDifferentialRequest),
        "traincapsule.v3.1.delivery-measurement": DeliveryMeasurement,
        "traincapsule.v3.1.reduction-candidate-input": ReductionCandidateInput,
        **{spec.schema_id: spec.model for spec in SEMANTIC_OUTPUT_SPECS.values()},
    }
    validator = validators.get(output.schema_id)
    if validator is not None:
        try:
            validated = validator.model_validate_json(payload, strict=True)
            if (
                output.schema_id != "traincapsule.v3.1.task-result"
                and payload != validated.canonical_json_bytes()
            ):
                raise TaskCompilationError(
                    f"materialized output is not canonical JSON: {output.path}"
                )
        except (UnicodeDecodeError, ValueError) as exc:
            raise TaskCompilationError(
                f"materialized output does not match {output.schema_id}: {output.path}"
            ) from exc
    else:
        raise TaskCompilationError(f"unsupported output schema: {output.schema_id}")


def _validate_relative_path(value: str) -> None:
    if "\\" in value or value.startswith("/"):
        raise ValueError("path must be normalized and repository-relative")
    path = PurePosixPath(value)
    if not value or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("path must be normalized and cannot traverse")


def _validate_scope_pattern(value: str) -> None:
    _validate_relative_path(value.replace("*", "x"))


def _matches_any(path: str, patterns: list[str] | tuple[str, ...]) -> bool:
    _validate_relative_path(path)
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _validate_digest_list(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    for value in values:
        if DIGEST_PATTERN.fullmatch(value) is None:
            raise ValueError(f"{label} contains an invalid digest")


def _contract_digest(payload: Mapping[str, object], *, omit_digest: bool = False) -> str:
    canonical = dict(payload)
    if omit_digest:
        canonical.pop("contractDigest", None)
    return sha256_digest(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


TASK_COMPILER_CONTRACTS = {
    "task-result-artifact": TaskResultArtifactV31,
    "task-output-declaration": OutputDeclarationV31,
    "task-tool-policy": ToolPolicyV31,
    "compiled-task-contract": CompiledTaskContractV31,
    "agent-execution-report": AgentExecutionReportV31,
}
