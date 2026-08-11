from __future__ import annotations

import inspect
from pathlib import Path

from tcfactory.config import load_factory_config
from tcfactory.models import (
    AgentReport,
    Gate,
    ReviewFinding,
    RoleName,
    Stage,
    StageResult,
    TaskPacket,
    Verdict,
)
from tcfactory.pipeline import (
    _execute_stage,  # pyright: ignore[reportPrivateUsage]
    findings_from_result,
    repository_finding_paths,
    review_failure_fingerprint,
    route_repair_findings,
)

ROOT = Path(__file__).resolve().parents[1]


def _result(report: AgentReport) -> StageResult:
    return StageResult(
        task_id="T900",
        run_id="run",
        role=RoleName.ADVERSARY,
        attempt=1,
        model="opus",
        verdict=report.verdict,
        report=report,
        artifact_dir="factory/artifacts/T900/run/adversary-a1",
    )


def test_only_blocking_structured_findings_control_repair_routing(tmp_path: Path) -> None:
    product = tmp_path / "packages" / "api" / "service.py"
    controller = tmp_path / "tcfactory" / "pipeline.py"
    product.parent.mkdir(parents=True)
    controller.parent.mkdir(parents=True)
    product.write_text("product\n", encoding="utf-8")
    controller.write_text("controller\n", encoding="utf-8")

    report = AgentReport(
        verdict=Verdict.FAIL,
        summary="One product defect and one advisory controller observation.",
        findings=["ADVISORY: tcfactory/pipeline.py was inspected and is sound."],
        limitations=["tcfactory/pipeline.py may be simplified later."],
        next_actions=["Consider a future tcfactory/pipeline.py refactor."],
        review_findings=[
            ReviewFinding(
                summary="The supported API returns the wrong truth state.",
                blocking=True,
                severity="high",
                criterion_id="AC-API-1",
                owner_class="product",
                repair_paths=["packages/api/service.py"],
                counterexample="Run the API fixture and observe UNKNOWN become PASS.",
                failing_evidence=["pytest tests/api/test_service.py -q"],
            ),
            ReviewFinding(
                summary="Controller naming could be clearer.",
                blocking=False,
                severity="info",
                owner_class="factory",
                repair_paths=["tcfactory/pipeline.py"],
            ),
        ],
    )

    findings = findings_from_result(_result(report))
    assert repository_finding_paths(tmp_path, findings) == ["packages/api/service.py"]
    assert all("future" not in finding.lower() for finding in findings)


def test_nonblocking_structured_review_cannot_invent_a_repair_target(tmp_path: Path) -> None:
    path = tmp_path / "tcfactory" / "pipeline.py"
    path.parent.mkdir(parents=True)
    path.write_text("controller\n", encoding="utf-8")
    report = AgentReport(
        verdict=Verdict.FAIL,
        summary="Invalid verifier report.",
        review_findings=[
            ReviewFinding(
                summary="Verified sound.",
                blocking=False,
                severity="info",
                owner_class="factory",
                repair_paths=["tcfactory/pipeline.py"],
            )
        ],
    )

    findings = findings_from_result(_result(report))
    assert repository_finding_paths(tmp_path, findings) == []
    assert "without a blocking structured finding" in findings[0]


def test_mixed_advisory_controller_citation_repairs_product_in_scope(tmp_path: Path) -> None:
    for relative in ("packages/api/service.py", "tcfactory/pipeline.py"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n", encoding="utf-8")
    task = TaskPacket(
        task_id="T900",
        title="Fix API",
        phase="P0",
        goal="Correct the API truth state",
        source_of_truth=["README.md"],
        acceptance_criteria=["API truth is correct"],
        outputs=["packages/api/service.py"],
        stop_conditions=["Authority missing"],
        gates=[Gate(name="quality", command="true")],
        pipeline=[
            Stage(
                role=RoleName.BUILDER,
                allowed_paths=["packages/**"],
                forbidden_paths=["tcfactory/**"],
                machine_gates=["quality"],
            ),
            Stage(role=RoleName.ADVERSARY, read_only=True, forbidden_paths=["**"]),
        ],
    )
    routing = route_repair_findings(
        repo_root=tmp_path,
        task=task,
        findings=[
            "BLOCKING: packages/api/service.py returns PASS for UNKNOWN.",
            "NON-BLOCKING: tcfactory/pipeline.py was inspected and is sound.",
        ],
    )
    assert routing.repairable_paths == ["packages/api/service.py"]
    assert routing.blocked_by_scope is False
    assert routing.controller_owned_gaps == []


def test_factory_declares_claude_led_node_execution() -> None:
    config = load_factory_config(ROOT / "config/factory.yaml")
    assert config.execution_mode == "claude_led_nodes"
    assert config.work_until_done is True
    assert config.allow_paid_usage is False


def test_reviewer_no_progress_fingerprint_is_order_stable_and_candidate_bound() -> None:
    first = review_failure_fingerprint(
        role=RoleName.ADVERSARY,
        candidate_sha="a" * 40,
        findings=["HIGH: wrong truth state", "Evidence: pytest failed"],
    )
    reordered = review_failure_fingerprint(
        role=RoleName.ADVERSARY,
        candidate_sha="a" * 40,
        findings=[" evidence:   pytest FAILED ", "high: WRONG truth state"],
    )
    progressed = review_failure_fingerprint(
        role=RoleName.ADVERSARY,
        candidate_sha="b" * 40,
        findings=["HIGH: wrong truth state", "Evidence: pytest failed"],
    )
    assert first == reordered
    assert first != progressed


def test_existing_valid_candidate_is_not_forced_to_create_a_cosmetic_diff() -> None:
    source = inspect.getsource(_execute_stage)
    assert "declared PASS but produced no repository change" not in source
    assert "Deterministic gates, not file motion" in source
