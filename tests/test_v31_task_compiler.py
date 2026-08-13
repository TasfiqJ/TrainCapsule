from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from tcfactory.v3.task_compiler_v31 import (
    AgentExecutionReportV31,
    CompiledTaskContractV31,
    CriterionResultV31,
    ExecutionVerdict,
    MaterializedOutputV31,
    NextAuthorizedAction,
    ResourceUsageV31,
    ResumeState,
    TaskCompilationError,
    TruthState,
    compile_task_contract_v31,
    execution_report_schema,
    tool_policy_for_request,
    validate_execution_report_v31,
)
from tcfactory.v3.work_items import WorkItem

DIGEST_1 = "sha256:" + "1" * 64
DIGEST_2 = "sha256:" + "2" * 64
DIGEST_3 = "sha256:" + "3" * 64
BASE_SHA = "a" * 40
CANDIDATE_SHA = "b" * 40


def _contract(**item_updates: object) -> CompiledTaskContractV31:
    return compile_task_contract_v31(
        _work_item(**item_updates),
        task_packet_digest=DIGEST_1,
        source_generation_id="v3.1-zh-2026-08-12",
        source_digest=DIGEST_2,
        context_digest=DIGEST_3,
    )


def _work_item(**updates: object) -> WorkItem:
    now = datetime.now(UTC).isoformat()
    payload: dict[str, object] = {
        "version": 3,
        "workItemId": "V3-PROD-001",
        "title": "Bounded work",
        "lane": "PRODUCT",
        "kind": "CODE",
        "milestone": "M1_NATIVE_PREFLIGHT",
        "decisionContribution": "Establish one bounded decision input.",
        "customerOutcome": "A truthful local result.",
        "dependsOn": [],
        "softDependsOn": [],
        "blocksCommercialRelease": False,
        "priority": 80,
        "riskTier": "STANDARD",
        "maturityTarget": {
            "engineering": "CONTROLLED_VALIDATED",
            "commercial": "NATIVE_ADVANTAGE_UNPROVEN",
        },
        "disposition": "KEEP",
        "status": "READY",
        "ownerType": "AI",
        "automatable": True,
        "packetPath": "specs/v3/V3-PROD-001.yaml",
        "evidenceRequired": ["controlled fixture"],
        "externalReceiptRequired": False,
        "retryPolicy": {
            "maxPlanAttempts": 2,
            "maxCandidateRepairCycles": 3,
        },
        "createdAt": now,
        "updatedAt": now,
    }
    payload.update(updates)
    return WorkItem.model_validate_json(json.dumps(payload))


def _materialize(
    contract: CompiledTaskContractV31, candidate_root: Path
) -> MaterializedOutputV31:
    declaration = contract.outputs[0]
    target = candidate_root / declaration.path
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(
            {
                "schemaVersion": "3.1",
                "workItemId": contract.work_item_id,
                "requestId": "AREQ-V3_PROD_001",
                "verdict": "PASS",
                "evidenceDigests": [contract.task_packet_digest],
                "summary": "Required bounded result.",
                "limitations": [],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    payload = target.read_bytes()
    return MaterializedOutputV31(
        schema_version="3.1",
        output_id=declaration.output_id,
        path=declaration.path,
        schema_id=declaration.schema_id,
        content_digest="sha256:" + hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def _report(
    contract: CompiledTaskContractV31, output: MaterializedOutputV31
) -> AgentExecutionReportV31:
    return AgentExecutionReportV31(
        schema_version="3.1",
        request_id="AREQ-V3_PROD_001",
        work_item_id=contract.work_item_id,
        role="implementation-owner",
        owner_class="CANDIDATE_AGENT",
        base_sha=BASE_SHA,
        candidate_sha=CANDIDATE_SHA,
        source_generation_id=contract.source_generation_id,
        source_digest=contract.source_digest,
        context_digest=contract.context_digest,
        task_packet_digest=contract.task_packet_digest,
        verdict=ExecutionVerdict.PASS,
        truth_state=TruthState.CLEAR,
        criterion_results=[
            CriterionResultV31(
                schema_version="3.1",
                criterion_id="CRIT:OUTPUT:VALID",
                passed=True,
                evidence_digests=[output.content_digest],
                explanation="Required output is present and digest-bound.",
            )
        ],
        findings=[],
        finding_fingerprints=[],
        changed_files=[output.path],
        commands_run=[],
        tests_run=[],
        outputs=[output],
        artifact_digests=[output.content_digest],
        external_receipt_refs=[],
        native_disposition="NOT_APPLICABLE",
        value_disposition="NOT_EVALUATED",
        limitations=[],
        resource_usage=ResourceUsageV31(
            schema_version="3.1",
            wall_time_seconds=1,
            turns=1,
            tokens=1000,
            cost_usd_equivalent=0,
        ),
        session_ref="SESSION:V3:PROD:001",
        resume_state=ResumeState.NOT_REQUIRED,
        next_authorized_action=NextAuthorizedAction.VERIFY,
    )


def test_compiler_derives_tools_from_work_mutability_not_role() -> None:
    code_contract = _contract()
    read_only = tool_policy_for_request(code_contract, mutating_owner=False)
    mutating = tool_policy_for_request(code_contract, mutating_owner=True)
    assert "Write" not in read_only.allowed_tools
    assert "Edit" not in read_only.allowed_tools
    assert {"Write", "Edit"}.issubset(mutating.allowed_tools)
    assert all(rule.executable in {"git", "uv"} for rule in mutating.bash_rules)
    assert not any(
        forbidden in {rule.executable, *rule.argument_prefix}
        for rule in mutating.bash_rules
        for forbidden in ("push", "gh", "sudo", "systemctl", "verifier")
    )

    product_research = _contract(kind="RESEARCH")
    assert {"Write", "Edit"}.issubset(
        tool_policy_for_request(product_research, mutating_owner=True).allowed_tools
    )
    market_research = _contract(
        workItemId="V3-MKT-001",
        lane="MARKET",
        kind="RESEARCH",
        packetPath="specs/v3/V3-MKT-001.yaml",
    )
    assert {"Write", "Edit"}.issubset(
        tool_policy_for_request(market_research, mutating_owner=True).allowed_tools
    )
    assert market_research.outputs[0].path.startswith("docs/market/v3-mkt-001/")


@pytest.mark.parametrize(
    ("work_item_id", "lane", "kind", "schema_id"),
    [
        (
            "V3-PROD-029",
            "PRODUCT",
            "CODE",
            "traincapsule.v3.1.support-policy-evidence",
        ),
        (
            "V3-REPEAT-006",
            "MARKET",
            "RESEARCH",
            "traincapsule.v3.1.delivery-economics-evidence",
        ),
        (
            "V3-PACK-002",
            "PRODUCT",
            "CODE",
            "traincapsule.v3.1.third-same-family-case-evidence",
        ),
        (
            "V3-TRUST-005",
            "TRUST",
            "SPECIFICATION",
            "traincapsule.v3.1.reduction-boundary-evidence",
        ),
    ],
)
def test_semantic_work_items_require_strict_typed_outputs(
    work_item_id: str, lane: str, kind: str, schema_id: str
) -> None:
    contract = _contract(workItemId=work_item_id, lane=lane, kind=kind)
    declarations = [output for output in contract.outputs if output.schema_id == schema_id]
    assert len(declarations) == 1
    assert declarations[0].required is True
    assert declarations[0].content_digest_required is True


def test_compiler_outputs_are_stable_scoped_and_digest_bound() -> None:
    first = _contract()
    second = _contract()
    assert first == second
    assert first.contract_digest == second.contract_digest
    assert first.outputs[0].required
    assert first.outputs[0].content_digest_required
    assert first.outputs[0].output_id == "OUT:V3:PROD:001:RESULT"
    assert first.outputs[0].path.startswith("docs/evidence/product/")
    assert "docs/source-of-truth/**" in first.forbidden_paths

    tampered = first.model_dump(mode="json", by_alias=True)
    tampered["outputs"][0]["path"] = "docs/source-of-truth/forged.json"
    with pytest.raises(ValidationError):
        type(first).model_validate(tampered)


def test_strict_report_reopens_and_verifies_required_output(tmp_path: Path) -> None:
    contract = _contract()
    output = _materialize(contract, tmp_path)
    report = _report(contract, output)
    validate_execution_report_v31(report, contract, candidate_root=tmp_path)

    target = tmp_path / output.path
    target.write_text('{"result":"substituted"}\n', encoding="utf-8")
    with pytest.raises(TaskCompilationError, match="size mismatch|digest mismatch"):
        validate_execution_report_v31(report, contract, candidate_root=tmp_path)


def test_report_rejects_missing_undeclared_and_out_of_scope_outputs(tmp_path: Path) -> None:
    contract = _contract()
    output = _materialize(contract, tmp_path)
    report = _report(contract, output)

    missing = report.model_copy(update={"outputs": []})
    with pytest.raises(TaskCompilationError, match="missing required outputs"):
        validate_execution_report_v31(missing, contract, candidate_root=tmp_path)

    undeclared = output.model_copy(update={"output_id": "OUT:V3:PROD:001:EXTRA"})
    extra = report.model_copy(update={"outputs": [output, undeclared]})
    with pytest.raises(TaskCompilationError, match="undeclared outputs"):
        validate_execution_report_v31(extra, contract, candidate_root=tmp_path)

    escaped = report.model_copy(
        update={"changed_files": ["docs/source-of-truth/v3.1-zh-2026-08-12/README.md"]}
    )
    with pytest.raises(TaskCompilationError, match="outside task scope|forbidden"):
        validate_execution_report_v31(escaped, contract, candidate_root=tmp_path)


def test_output_rejects_schema_invalid_and_symlink_substitution(tmp_path: Path) -> None:
    contract = _contract()
    output = _materialize(contract, tmp_path)
    target = tmp_path / output.path

    invalid = b'{"schemaVersion":"3.1","verdict":"PASS"}\n'
    target.write_bytes(invalid)
    invalid_output = output.model_copy(
        update={
            "content_digest": "sha256:" + hashlib.sha256(invalid).hexdigest(),
            "size_bytes": len(invalid),
        }
    )
    with pytest.raises(TaskCompilationError, match="does not match"):
        validate_execution_report_v31(
            _report(contract, invalid_output), contract, candidate_root=tmp_path
        )

    outside = tmp_path.parent / "outside-task-result.json"
    outside.write_bytes(invalid)
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises(TaskCompilationError, match="missing or unsafe"):
        validate_execution_report_v31(
            _report(contract, invalid_output), contract, candidate_root=tmp_path
        )


def test_read_only_report_cannot_claim_mutation_and_pass_is_coherent(tmp_path: Path) -> None:
    contract = _contract()
    output = _materialize(contract, tmp_path)
    report = _report(contract, output)

    read_only = report.model_copy(update={"owner_class": "READ_ONLY_REVIEWER"})
    with pytest.raises(TaskCompilationError, match="read-only reviewer"):
        validate_execution_report_v31(read_only, contract, candidate_root=tmp_path)

    failed_criterion = report.model_copy(
        update={
            "criterion_results": [
                report.criterion_results[0].model_copy(update={"passed": False})
            ]
        }
    )
    with pytest.raises(TaskCompilationError, match="blocking or failed evidence"):
        validate_execution_report_v31(failed_criterion, contract, candidate_root=tmp_path)


def test_report_schema_is_strict_and_not_generic() -> None:
    schema = execution_report_schema()
    assert schema["additionalProperties"] is False
    required = set(cast(list[str], schema.get("required", [])))
    assert {
        "verdict",
        "truthState",
        "criterionResults",
        "findings",
        "changedFiles",
        "commandsRun",
        "outputs",
        "resourceUsage",
        "nextAuthorizedAction",
    }.issubset(required)

    payload = json.loads(
        _report(
            _contract(),
            MaterializedOutputV31(
                schema_version="3.1",
                output_id="OUT:V3:PROD:001:RESULT",
                path="docs/evidence/product/v3-prod-001/result.json",
                schema_id="traincapsule.v3.1.task-result",
                content_digest=DIGEST_1,
                size_bytes=1,
            ),
        ).model_dump_json(by_alias=True)
    )
    payload["candidateMaySelfCertify"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AgentExecutionReportV31.model_validate(payload)
