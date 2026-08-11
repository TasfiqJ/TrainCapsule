from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

import tcfactory.completion as completion_module
from tcfactory.completion import (
    CompletionBlocked,
    _audit_lens,  # pyright: ignore[reportPrivateUsage]
    _prior_reports_for,  # pyright: ignore[reportPrivateUsage]
    _validate_completion_report,  # pyright: ignore[reportPrivateUsage]
    deterministic_completion_check,
)
from tcfactory.feature_ledger import FeatureItem, FeatureLedger
from tcfactory.models import (
    CompletionAuditReport,
    CompletionVerdict,
    CompletionWorkItem,
    FactoryConfig,
)
from tcfactory.yamlutil import load_yaml

ROOT = Path(__file__).resolve().parents[1]


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("candidate\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "candidate"], cwd=path, check=True)


def test_completion_check_requires_paths_and_commands(tmp_path: Path) -> None:
    (tmp_path / "present.txt").write_text("ok", encoding="utf-8")
    definition = {
        "required_paths": ["present.txt", "missing.txt"],
        "required_globs": ["*.txt", "capsules/**/capsule.json"],
        "required_commands": [
            {"name": "passes", "command": "test -f present.txt", "timeout_seconds": 5},
            {"name": "fails", "command": "exit 7", "timeout_seconds": 5},
        ],
    }
    failures = deterministic_completion_check(tmp_path, definition)
    assert any("Missing required path: missing.txt" in value for value in failures)
    assert any(
        "No files matched required glob: capsules/**/capsule.json" in value for value in failures
    )
    assert any("Completion command 'fails' failed (7)" in value for value in failures)
    assert not any("passes" in value for value in failures)


def test_version_three_completion_requires_executable_outcome_proofs(tmp_path: Path) -> None:
    failures = deterministic_completion_check(tmp_path, {"version": 3})
    assert failures == ["Version 3 completion definition has no outcome_proofs"]


def test_outcome_proof_must_run_and_emit_raw_evidence(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    evidence = ".factory/gate-results/product-proof/first-value/result.json"
    script = tmp_path / "proof.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf 'fresh proof\\n' > \"$TCF_PRODUCT_PROOF_OUTPUT_DIR/result.json\"\n"
        "digest=$(sha256sum \"$TCF_PRODUCT_PROOF_OUTPUT_DIR/result.json\" | cut -d' ' -f1)\n"
        "printf '{\"schema_version\":\"traincapsule.product-proof/v1\","
        "\"proof_id\":\"%s\",\"candidate_sha\":\"%s\",\"status\":\"pass\","
        "\"environment_digest\":\"test-env\",\"oracle_version\":\"test-oracle-v1\","
        "\"artifacts\":{\"result.json\":\"%s\"}}\\n' "
        "\"$TCF_PRODUCT_PROOF_ID\" \"$TCF_PRODUCT_PROOF_CANDIDATE_SHA\" \"$digest\" "
        "> \"$TCF_PRODUCT_PROOF_OUTPUT_DIR/manifest.json\"\n",
        encoding="utf-8",
    )
    definition = {
        "version": 3,
        "outcome_proofs": [
            {
                "id": "first-value",
                "command": "bash proof.sh",
                "timeout_seconds": 5,
                "evidence_root": ".factory/gate-results/product-proof/first-value",
                "evidence_globs": [evidence],
            }
        ],
    }
    assert deterministic_completion_check(tmp_path, definition) == []


def test_outcome_proof_rejects_success_without_evidence(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    stale_root = tmp_path / ".factory/gate-results/product-proof/first-value"
    stale_root.mkdir(parents=True)
    (stale_root / "manifest.json").write_text("{}\n", encoding="utf-8")
    (stale_root / "result.json").write_text("stale\n", encoding="utf-8")
    definition = {
        "version": 3,
        "outcome_proofs": [
            {
                "id": "first-value",
                "command": "true",
                "timeout_seconds": 5,
                "evidence_root": ".factory/gate-results/product-proof/first-value",
                "evidence_globs": [".factory/gate-results/product-proof/first-value/**"],
            }
        ],
    }
    failures = deterministic_completion_check(tmp_path, definition)
    assert any("produced no manifest.json" in value for value in failures)


def test_outcome_proof_rejects_wrong_candidate_binding(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    script = tmp_path / "wrong-proof.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf 'proof\\n' > \"$TCF_PRODUCT_PROOF_OUTPUT_DIR/result.json\"\n"
        "digest=$(sha256sum \"$TCF_PRODUCT_PROOF_OUTPUT_DIR/result.json\" | cut -d' ' -f1)\n"
        "printf '{\"schema_version\":\"traincapsule.product-proof/v1\","
        "\"proof_id\":\"first-value\",\"candidate_sha\":\"wrong\","
        "\"status\":\"pass\",\"environment_digest\":\"env\","
        "\"oracle_version\":\"oracle\",\"artifacts\":{\"result.json\":\"%s\"}}\\n' "
        "\"$digest\" > \"$TCF_PRODUCT_PROOF_OUTPUT_DIR/manifest.json\"\n",
        encoding="utf-8",
    )
    definition = {
        "version": 3,
        "outcome_proofs": [
            {
                "id": "first-value",
                "command": "bash wrong-proof.sh",
                "timeout_seconds": 5,
                "evidence_root": ".factory/gate-results/product-proof/first-value",
                "evidence_globs": [
                    ".factory/gate-results/product-proof/first-value/result.json"
                ],
            }
        ],
    }

    failures = deterministic_completion_check(tmp_path, definition)

    assert any("wrong candidate_sha" in value for value in failures)


@pytest.mark.parametrize("contradiction", ["missing_items", "blockers"])
def test_complete_report_cannot_carry_unresolved_work(contradiction: str) -> None:
    payload: dict[str, object] = {
        "verdict": CompletionVerdict.COMPLETE,
        "summary": "complete",
        "completed_evidence": ["factory/completion/evidence.json"],
    }
    if contradiction == "missing_items":
        payload["missing_items"] = [
            CompletionWorkItem(
                task_id="AUTO001",
                outcome="Finish the missing production behavior",
                phase="completion",
                lead_role="Builder",
            )
        ]
    else:
        payload["blockers"] = ["A required production behavior remains blocked"]
    report = CompletionAuditReport.model_validate(payload)

    with pytest.raises(CompletionBlocked, match=contradiction):
        _validate_completion_report(report, label="primary-audit")


def test_completion_audits_are_blind_and_only_adjudicator_sees_reports() -> None:
    reports = [
        CompletionAuditReport(
            verdict=CompletionVerdict.INCOMPLETE,
            summary="missing work",
            missing_items=[
                CompletionWorkItem(
                    task_id="AUTO001",
                    outcome="Finish the missing production behavior",
                    phase="completion",
                    lead_role="Builder",
                )
            ],
        )
    ]

    for label in ("primary-audit", "adversarial-audit", "third-audit"):
        assert _prior_reports_for(label, reports) == []
    assert _prior_reports_for("completion-adjudicator", reports) is reports


def test_completion_audits_have_orthogonal_evidence_lenses() -> None:
    primary = _audit_lens("primary audit")
    adversarial = _audit_lens("adversarial audit")
    third = _audit_lens("third audit")
    adjudicator = _audit_lens("completion adjudicator")

    assert len({primary, adversarial, third, adjudicator}) == 4
    assert "traceability" in primary
    assert "falsify" in adversarial
    assert "buyer and operator journeys" in third
    assert "Reconcile" in adjudicator


def test_completion_audit_wiring_keeps_reviews_blind_until_adjudication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, list[CompletionAuditReport]] = {}

    def report(task_id: str) -> CompletionAuditReport:
        return CompletionAuditReport(
            verdict=CompletionVerdict.INCOMPLETE,
            summary=f"missing {task_id}",
            missing_items=[
                CompletionWorkItem(
                    task_id=task_id,
                    outcome="Finish a missing production behavior",
                    phase="completion",
                    lead_role="Builder",
                )
            ],
        )

    async def fake_review(**kwargs: object) -> CompletionAuditReport:
        label = str(kwargs["label"])
        prior = kwargs["prior_reports"]
        assert isinstance(prior, list)
        captured[label] = prior
        return {
            "primary-audit": report("AUTO001"),
            "adversarial-audit": report("AUTO002"),
            "completion-adjudicator": report("AUTO003"),
        }[label]

    def fake_load_definition(*_: object) -> dict[str, object]:
        return {}

    def fake_deterministic_check(*_: object) -> list[str]:
        return []

    def fake_append_missing_items(**_: object) -> list[str]:
        return ["AUTO003"]

    def no_op(*_: object) -> None:
        return None

    monkeypatch.setattr(completion_module, "load_definition", fake_load_definition)
    monkeypatch.setattr(
        completion_module, "deterministic_completion_check", fake_deterministic_check
    )
    monkeypatch.setattr(completion_module, "_one_review", fake_review)
    monkeypatch.setattr(
        completion_module,
        "_append_missing_items",
        fake_append_missing_items,
    )
    monkeypatch.setattr(completion_module, "save_feature_ledger", no_op)
    monkeypatch.setattr(completion_module, "commit_all", no_op)
    def fixed_sha(_repo_root: Path, _ref: str = "HEAD") -> str:
        return "a" * 40

    monkeypatch.setattr(completion_module, "current_sha", fixed_sha)
    ledger = FeatureLedger(
        source_of_truth="test",
        tasks=[
            FeatureItem(
                task_id="T001",
                outcome="existing build work",
                lead_role="Builder",
                phase="build",
                status="passed",
            )
        ],
    )

    outcome, added, audited_sha = asyncio.run(
        completion_module.audit_and_expand_or_complete(
            repo_root=tmp_path,
            config=FactoryConfig(auth_mode="unrestricted"),
            ledger=ledger,
            audits_required=2,
        )
    )

    assert outcome == "expanded"
    assert added == ["AUTO003"]
    assert audited_sha == "a" * 40
    assert captured["primary-audit"] == []
    assert captured["adversarial-audit"] == []
    assert len(captured["completion-adjudicator"]) == 2


def test_product_completion_requires_commercialization_ready_production_evidence() -> None:
    definition = load_yaml(ROOT / "factory/product_definition_of_done.yaml")
    required_paths = set(definition["required_paths"])
    assert {
        "docs/product/BUYER_AND_USER_WORKFLOWS.md",
        "docs/product/INSTALL_DEPLOY_UPGRADE.md",
        "docs/product/OPERATIONS_SUPPORT_AND_FAILURES.md",
        "docs/product/COMMERCIAL_READINESS.md",
        "docs/product/EXTERNAL_VALIDATION_PACKET.md",
    }.issubset(required_paths)

    readiness = definition["commercial_readiness_evidence_required"]
    assert any("economic buyer" in item for item in readiness)
    assert any("privacy-safe" in item for item in readiness)
    assert any("EXTERNAL_VALIDATION_REQUIRED" in item for item in readiness)

    quality_floor = definition["quality_floor"]
    assert any("mock-only" in item for item in quality_floor)
    assert any("end-to-end" in item for item in quality_floor)

    founder_execution = definition["founder_brief_execution_required"]
    assert any("company_product_brief" in item for item in founder_execution)
    assert any(
        "ordinary ambiguity is not an operator blocker" in item for item in founder_execution
    )
    assert any(
        "expansion count is not a product-scope ceiling" in item for item in founder_execution
    )


def test_company_product_brief_routes_the_supplied_business_and_build_corpus() -> None:
    contexts = load_yaml(ROOT / "docs/CONTEXT_INDEX.yaml")["contexts"]
    brief = set(contexts["company_product_brief"])
    assert {
        "docs/source-of-truth/final-2026-08-09/00_EXECUTIVE_BUILD_DECISION.md",
        "docs/source-of-truth/final-2026-08-09/03_PRODUCT_STRATEGY_AND_REQUIREMENTS.md",
        "docs/source-of-truth/final-2026-08-09/04_TECHNICAL_ARCHITECTURE.md",
        "docs/source-of-truth/final-2026-08-09/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC.md",
        "docs/source-of-truth/final-2026-08-09/08_ACQUISITION_THESIS.md",
        "docs/source-of-truth/final-2026-08-09/09_CAREER_AND_HIRING_THESIS.md",
        "docs/source-of-truth/final-2026-08-09/12_ROADMAP_BACKLOG_AND_MASTER_BUILD_PROMPT.md",
        "docs/source-of-truth/final-2026-08-09/14_CLAUDE_CODE_MASTER_BUILD_PROMPT.md",
        "docs/source-of-truth/final-2026-08-09/TRAINCAPSULE_FINAL_MASTER_PLAN.md",
    }.issubset(brief)


def test_private_completion_gate_runs_outside_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    from tcfactory.completion import run_private_completion_gate
    from tcfactory.models import FactoryConfig

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("candidate\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "baseline",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    private = tmp_path / "private"
    private.mkdir()
    runner = private / "run.sh"
    runner.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'test "$1" = product-completion\n'
        'test "$2" = "$TCF_CANDIDATE_WORKTREE"\n'
        'test "$TCF_TASK_ID" = PRODUCT_COMPLETION\n',
        encoding="utf-8",
    )
    runner.chmod(0o700)
    monkeypatch.setenv("TCF_PRIVATE_GATE_RUNNER", str(runner))
    config = FactoryConfig(auth_mode="unrestricted")
    payload = run_private_completion_gate(
        repo_root=repo,
        config=config,
        run_id="completion-test",
    )
    assert payload["passed"] is True


def test_private_completion_gate_cannot_certify_a_reset_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    from tcfactory.completion import run_private_completion_gate

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    for message, content in (("baseline", "baseline\n"), ("candidate", "candidate\n")):
        (repo / "README.md").write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-m",
                message,
            ],
            cwd=repo,
            check=True,
            capture_output=True,
        )
    private = tmp_path / "private"
    private.mkdir()
    runner = private / "run.sh"
    runner.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'git -C "$2" reset --hard HEAD^\n',
        encoding="utf-8",
    )
    runner.chmod(0o700)
    monkeypatch.setenv("TCF_PRIVATE_GATE_RUNNER", str(runner))

    with pytest.raises(CompletionBlocked, match="changed the candidate worktree HEAD"):
        run_private_completion_gate(
            repo_root=repo,
            config=FactoryConfig(auth_mode="unrestricted"),
            run_id="completion-reset-test",
        )
