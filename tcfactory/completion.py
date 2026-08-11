from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, cast

import yaml

from .feature_ledger import FeatureItem, FeatureLedger, save_feature_ledger
from .gates import PrivateGateError, run_private_gate
from .gitops import changed_files, cleanup_worktree, commit_all, create_worktree, current_sha
from .models import (
    COMPLETION_AUDIT_JSON_SCHEMA,
    CompletionAuditReport,
    CompletionVerdict,
    CompletionWorkItem,
    FactoryConfig,
    RoleName,
)
from .structured_runner import run_structured_read_only_review
from .util import run_command, utc_stamp, write_json
from .yamlutil import load_yaml


class CompletionBlocked(RuntimeError):
    pass


def _proof_root(repo_root: Path, raw: object) -> Path:
    relative = str(raw or "").strip()
    if not relative:
        raise CompletionBlocked("Outcome proof has no isolated evidence_root")
    root = (repo_root / relative).resolve()
    protected_root = (repo_root / ".factory/gate-results/product-proof").resolve()
    try:
        root.relative_to(protected_root)
    except ValueError as exc:
        raise CompletionBlocked(
            f"Outcome proof evidence_root escapes the isolated proof area: {relative}"
        ) from exc
    if root == protected_root:
        raise CompletionBlocked("Outcome proof must use its own child evidence_root")
    return root


def _validate_proof_manifest(*, root: Path, proof_id: str, candidate_sha: str) -> str | None:
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return f"Outcome proof {proof_id!r} produced no manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"Outcome proof {proof_id!r} manifest is unreadable: {exc}"
    if not isinstance(payload, dict):
        return f"Outcome proof {proof_id!r} manifest is not a mapping"
    typed_payload = cast(dict[str, object], payload)
    expected = {
        "schema_version": "traincapsule.product-proof/v1",
        "proof_id": proof_id,
        "candidate_sha": candidate_sha,
        "status": "pass",
    }
    for key, value in expected.items():
        if typed_payload.get(key) != value:
            return f"Outcome proof {proof_id!r} manifest has wrong {key}"
    for key in ("environment_digest", "oracle_version"):
        observed = typed_payload.get(key)
        if not isinstance(observed, str) or not observed.strip():
            return f"Outcome proof {proof_id!r} manifest has no {key}"
    artifacts = typed_payload.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        return f"Outcome proof {proof_id!r} manifest has no hashed artifacts"
    for raw_path, raw_digest in cast(dict[object, object], artifacts).items():
        if not isinstance(raw_path, str) or not isinstance(raw_digest, str):
            return f"Outcome proof {proof_id!r} manifest has an invalid artifact entry"
        path = (root / raw_path).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            return f"Outcome proof {proof_id!r} artifact escapes evidence_root: {raw_path}"
        if (
            len(raw_digest) != 64
            or any(char not in "0123456789abcdef" for char in raw_digest)
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != raw_digest
        ):
            return f"Outcome proof {proof_id!r} artifact is missing or has wrong digest: {raw_path}"
    return None


def load_definition(repo_root: Path, config: FactoryConfig) -> dict[str, Any]:
    path = config.resolve(repo_root, config.definition_of_done_path)
    if not path.exists():
        raise CompletionBlocked(f"Product definition of done not found: {path}")
    payload = load_yaml(path)
    if not isinstance(payload, dict):
        raise CompletionBlocked("Product definition of done must be a YAML mapping")
    return cast(dict[str, Any], payload)


def deterministic_completion_check(
    repo_root: Path,
    definition: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    for value in cast(list[object], definition.get("required_paths", [])):
        path = repo_root / str(value)
        if not path.exists():
            failures.append(f"Missing required path: {value}")
    for pattern in cast(list[object], definition.get("required_globs", [])):
        if not list(repo_root.glob(str(pattern))):
            failures.append(f"No files matched required glob: {pattern}")
    for item in cast(list[object], definition.get("required_commands", [])):
        if isinstance(item, str):
            name, command, timeout = item, item, 1800
        elif isinstance(item, dict):
            typed_item = cast(dict[str, object], item)
            name = str(typed_item.get("name") or typed_item.get("command") or "completion command")
            command = str(typed_item["command"])
            timeout = int(str(typed_item.get("timeout_seconds", 1800)))
        else:
            failures.append(f"Invalid required_commands entry: {item!r}")
            continue
        completed = run_command(
            ["bash", "-lc", command],
            cwd=repo_root,
            check=False,
            timeout=timeout,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout)[-1500:]
            failures.append(
                f"Completion command {name!r} failed ({completed.returncode}): {detail}"
            )

    # Version 3 definitions promote product/value claims from auditor prompt prose to
    # executable, criterion-addressed journey proofs. These commands are controller-owned;
    # product work must produce their raw artifacts rather than declaring itself complete.
    if int(definition.get("version", 1)) >= 3:
        proofs = cast(list[object], definition.get("outcome_proofs", []))
        if not proofs:
            failures.append("Version 3 completion definition has no outcome_proofs")
        seen_ids: set[str] = set()
        for item in proofs:
            if not isinstance(item, dict):
                failures.append(f"Invalid outcome_proofs entry: {item!r}")
                continue
            proof = cast(dict[str, object], item)
            proof_id = str(proof.get("id") or "").strip()
            command = str(proof.get("command") or "").strip()
            evidence_globs = [
                str(value) for value in cast(list[object], proof.get("evidence_globs", []))
            ]
            if not proof_id or proof_id in seen_ids:
                failures.append(f"Outcome proof has missing or duplicate id: {proof_id!r}")
                continue
            seen_ids.add(proof_id)
            if not command:
                failures.append(f"Outcome proof {proof_id!r} has no executable command")
                continue
            if not evidence_globs:
                failures.append(f"Outcome proof {proof_id!r} has no raw evidence globs")
                continue
            try:
                evidence_root = _proof_root(repo_root, proof.get("evidence_root"))
            except CompletionBlocked as exc:
                failures.append(f"Outcome proof {proof_id!r}: {exc}")
                continue
            if evidence_root.exists():
                shutil.rmtree(evidence_root)
            evidence_root.mkdir(parents=True, exist_ok=True)
            candidate_sha = current_sha(repo_root)
            completed = run_command(
                ["bash", "-lc", command],
                cwd=repo_root,
                check=False,
                timeout=int(str(proof.get("timeout_seconds", 1800))),
                env={
                    "TCF_PRODUCT_PROOF_OUTPUT_DIR": str(evidence_root),
                    "TCF_PRODUCT_PROOF_CANDIDATE_SHA": candidate_sha,
                    "TCF_PRODUCT_PROOF_ID": proof_id,
                },
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout)[-1500:]
                failures.append(
                    f"Outcome proof {proof_id!r} failed ({completed.returncode}): {detail}"
                )
                continue
            manifest_error = _validate_proof_manifest(
                root=evidence_root,
                proof_id=proof_id,
                candidate_sha=candidate_sha,
            )
            if manifest_error:
                failures.append(manifest_error)
                continue
            for pattern in evidence_globs:
                matches = [path.resolve() for path in repo_root.glob(pattern) if path.is_file()]
                inside_root: list[Path] = []
                for path in matches:
                    try:
                        path.relative_to(evidence_root)
                    except ValueError:
                        continue
                    inside_root.append(path)
                if not inside_root:
                    failures.append(
                        f"Outcome proof {proof_id!r} produced no evidence matching {pattern}"
                    )
    return failures


def _audit_prompt(
    *,
    definition: dict[str, Any],
    ledger: FeatureLedger,
    prior_reports: list[CompletionAuditReport],
    role: str,
) -> str:
    prior = [report.model_dump(mode="json") for report in prior_reports]
    lens = _audit_lens(role)
    return f"""Perform a read-only {role} of whether the automatable TrainCapsule
commercialization-ready production build is complete.

AUDIT LENS:
{lens}

Authority order:
1. the complete company_product_brief context in docs/CONTEXT_INDEX.yaml
2. docs/source-of-truth/final-2026-08-09/12_ROADMAP_BACKLOG_AND_MASTER_BUILD_PROMPT.md
3. accepted ADRs and versioned specifications in the repository
4. factory/product_definition_of_done.yaml
5. factory/feature_ledger.yaml
6. executable repository state and evidence artifacts

The supplied corpus is the founder-level company and product brief. Synthesize its buyer,
product, architecture, trust, acquisition, operating, roadmap, and build intent. Do not
treat a missing preference, a task boundary, or multiple defensible implementation options
as an operator blocker: choose the strongest evidence-backed production option, require an
ADR when the choice is materially consequential, and continue.

Do not infer completion from line count, generated prose, dashboards, self-reported
confidence, or a green unit suite alone. Inspect actual implementation paths, schemas,
tests, adapters, release evidence, supported packaging, frontend/backend integration,
clean installation, upgrade and rollback behavior, operator diagnostics, security and
privacy controls, representative performance, and milestone artifacts.

The word COMPLETE means the full automatable production product is installable, usable,
operable, supportable, and independently inspectable for its declared buyer and user. A
collection of components, green unit tests, generated documentation, or a local developer
demo is not a product. COMPLETE does not mean customers paid, a maintainer merged a PR,
funding exists, or an acquisition is likely. Those external facts must never be invented;
the build must instead be ready to collect attributable pilot, usage, and payment evidence.

DEFINITION OF DONE:
```yaml
{yaml.safe_dump(definition, sort_keys=False)}
```

CURRENT FEATURE LEDGER:
```yaml
{yaml.safe_dump(ledger.model_dump(mode="json"), sort_keys=False)}
```

PRIOR INDEPENDENT REPORTS TO CHALLENGE OR RECONCILE:
```json
{json.dumps(prior, indent=2)}
```

Rules:
- Return COMPLETE only when every automatable requirement has concrete inspectable
  evidence and deterministic completion commands are appropriate to run.
- Require a clean supported install-to-first-value journey, the declared Close/Qualify/
  Exchange user workflows, realistic failure and recovery behavior, operator-facing
  diagnostics, upgrade/rollback evidence, security/privacy review, representative
  performance evidence, release artifacts, and actionable user/operator documentation.
- Require commercialization readiness: a concrete buyer, painful job, differentiated
  outcome, packaging hypothesis, measurable value instrumentation, and a ready-to-run
  external pilot/validation packet. Do not confuse these artifacts with proof of demand.
- Treat documentation-only, screenshot-only, mock-only, happy-path-only, or model-authored
  evidence as insufficient for runtime, operational, usability, or commercial claims.
- Return INCOMPLETE with complete dependency-ordered production work items when
  implementation remains. Each item may cross components when necessary to deliver a
  coherent end-to-end user outcome.
- New task IDs must be unique uppercase IDs beginning with AUTO and a zero-padded number,
  such as AUTO001.
- Each missing item must be coherent enough to specify, build, attack, audit, and release
  as a real outcome. Do not fragment work to minimize diff size, acceptance count, context,
  or session length.
- Dependencies may reference existing ledger IDs or earlier missing items in the same report.
- Do not add speculative enterprise surface area merely to appear valuable. Add only work
  needed for the protected buyer workflow, production quality, supportability, measurable
  differentiation, or external validation readiness.
- Return BLOCKED only for a genuine external or normative blocker that cannot be resolved
  through further repository research, an autonomous product/engineering decision, an ADR,
  or another research/specification task.
- Never claim commercial validation, maintainer confirmation, or customer adoption
  without external evidence.
"""


def _audit_lens(role: str) -> str:
    """Give blind completion reviewers distinct, evidence-first assignments."""

    normalized = role.lower()
    if "adversarial" in normalized:
        return (
            "Try to falsify completion. Construct counterexamples for false-green gates, "
            "documentation-only capability claims, unsupported clean-install or recovery "
            "claims, and commercial-readiness theatre."
        )
    if "third" in normalized:
        return (
            "Trace the supported buyer and operator journeys end to end, concentrating on "
            "installation, first value, failure diagnosis, recovery, upgrade, rollback, "
            "supportability, and measurable pilot readiness."
        )
    if "adjudicator" in normalized:
        return (
            "Reconcile the independent reports against repository evidence. Preserve every "
            "unresolved counterexample, deduplicate equivalent work, and never decide by vote."
        )
    return (
        "Build a requirement-to-evidence traceability matrix. Verify every automatable "
        "definition-of-done claim against executable behavior and attributable artifacts."
    )


def _prior_reports_for(
    label: str, reports: list[CompletionAuditReport]
) -> list[CompletionAuditReport]:
    """Keep evidence audits blind; only the explicit adjudicator may compare reports."""

    return reports if label == "completion-adjudicator" else []


def _system_prompt(role: str) -> str:
    return (
        f"You are the {role} in a lights-out AI software factory. You are read-only and "
        "independent from all builder sessions. Inspect files and run non-mutating commands. "
        "Do not write, edit, commit, install packages, use the network, invoke subagents, or "
        "change tests. Prevent premature completion and architecture theatre. Return only the "
        "enforced structured output."
    )


def _reports_agree_complete(reports: list[CompletionAuditReport]) -> bool:
    return bool(reports) and all(report.verdict == CompletionVerdict.COMPLETE for report in reports)


def _validate_completion_report(report: CompletionAuditReport, *, label: str) -> None:
    """Reject internally contradictory completion verdicts before they affect the roadmap."""

    if report.verdict == CompletionVerdict.COMPLETE:
        contradictions: list[str] = []
        if report.missing_items:
            contradictions.append("missing_items")
        if report.blockers:
            contradictions.append("blockers")
        if contradictions:
            raise CompletionBlocked(
                f"Completion reviewer {label} returned COMPLETE with unresolved "
                + " and ".join(contradictions)
            )


def _needs_adjudicator(reports: list[CompletionAuditReport]) -> bool:
    verdicts = {report.verdict for report in reports}
    if len(verdicts) != 1:
        return True
    if verdicts == {CompletionVerdict.INCOMPLETE}:
        normalized = [
            sorted(
                (item.task_id, item.outcome, tuple(item.depends_on))
                for item in report.missing_items
            )
            for report in reports
        ]
        return any(value != normalized[0] for value in normalized[1:])
    return False


def _validate_new_items(ledger: FeatureLedger, items: list[CompletionWorkItem]) -> None:
    existing = {item.task_id for item in ledger.tasks}
    proposed = {item.task_id for item in items}
    if len(proposed) != len(items):
        raise CompletionBlocked("Completion audit proposed duplicate task IDs")
    for item in items:
        if item.task_id in existing:
            raise CompletionBlocked(f"Completion audit attempted to redefine {item.task_id}")
        unknown = [dep for dep in item.depends_on if dep not in existing and dep not in proposed]
        if unknown:
            raise CompletionBlocked(
                f"Completion item {item.task_id} has unknown dependencies: {unknown}"
            )


def _append_missing_items(
    *,
    ledger: FeatureLedger,
    items: list[CompletionWorkItem],
    audit_artifact: str,
) -> list[str]:
    _validate_new_items(ledger, items)
    added: list[str] = []
    for draft in items:
        ready = set(draft.depends_on).issubset(ledger.passed_ids())
        ledger.tasks.append(
            FeatureItem(
                task_id=draft.task_id,
                outcome=draft.outcome,
                lead_role=draft.lead_role,
                phase=draft.phase,
                depends_on=draft.depends_on,
                status="ready" if ready else "blocked",
                packet_path=None,
                trust_core=draft.trust_core,
                auto_enqueue_allowed=True,
                automatable=True,
                completion_kind="build",
                evidence_required=draft.evidence_required,
                evidence=[],
                notes=[
                    "Added by independent product-completion audit.",
                    f"Audit artifact: {audit_artifact}",
                    *[f"Required evidence: {value}" for value in draft.evidence_required],
                ],
            )
        )
        added.append(draft.task_id)
    ledger.refresh_readiness()
    return added


async def _one_review(
    *,
    repo_root: Path,
    config: FactoryConfig,
    definition: dict[str, Any],
    ledger: FeatureLedger,
    prior_reports: list[CompletionAuditReport],
    run_id: str,
    label: str,
    role_name: RoleName,
) -> CompletionAuditReport:
    base_sha = current_sha(repo_root, "main")
    worktree = create_worktree(
        repo_root,
        config.resolve(repo_root, config.worktree_dir),
        task_id="PRODUCT_COMPLETION",
        run_id=run_id,
        role=label,
        attempt=1,
        base_sha=base_sha,
    )
    artifact_dir = config.resolve(repo_root, config.completion_dir) / run_id / label
    try:
        report = await run_structured_read_only_review(
            repo_root=repo_root,
            cwd=worktree.path,
            config=config,
            prompt=_audit_prompt(
                definition=definition,
                ledger=ledger,
                prior_reports=prior_reports,
                role=label.replace("-", " "),
            ),
            system_prompt=_system_prompt(label.replace("-", " ")),
            model=config.completion_audit_model,
            effort="high",
            max_turns=config.completion_audit_max_turns,
            max_budget_usd=config.completion_audit_budget_usd,
            schema=COMPLETION_AUDIT_JSON_SCHEMA,
            result_type=CompletionAuditReport,
            artifact_dir=artifact_dir,
            role=role_name,
            task_id="PRODUCT_COMPLETION",
            run_id=run_id,
        )
        _validate_completion_report(report, label=label)
        mutations = changed_files(worktree.path, base_sha)
        if mutations:
            raise CompletionBlocked(
                f"Read-only completion auditor modified its worktree: {mutations}"
            )
        return report
    finally:
        cleanup_worktree(repo_root, worktree, delete_branch=True)


def run_private_completion_gate(
    *,
    repo_root: Path,
    config: FactoryConfig,
    run_id: str,
    candidate_sha: str | None = None,
) -> dict[str, Any]:
    """Run the external hidden product-completion suite against a clean main worktree."""

    runner_value = os.getenv(config.private_gate_runner_env)
    if not runner_value:
        raise CompletionBlocked(
            f"{config.private_gate_runner_env} is unset; private completion cannot be certified"
        )
    runner = Path(runner_value).expanduser()
    base_sha = candidate_sha or current_sha(repo_root, "main")
    worktree = create_worktree(
        repo_root,
        config.resolve(repo_root, config.worktree_dir),
        task_id="PRODUCT_COMPLETION",
        run_id=run_id,
        role="private-gate",
        attempt=1,
        base_sha=base_sha,
    )
    artifact_dir = config.resolve(repo_root, config.completion_dir) / run_id / "private-gate"
    try:
        observed_head_before = current_sha(worktree.path)
        if observed_head_before != base_sha:
            raise CompletionBlocked(
                "Private-completion worktree was not created at the requested candidate SHA: "
                f"{observed_head_before} != {base_sha}"
            )
        try:
            result = run_private_gate(
                runner=runner,
                suite="product-completion",
                cwd=worktree.path,
                repo_root=repo_root,
                artifact_dir=artifact_dir,
                timeout_seconds=14_400,
                task_id="PRODUCT_COMPLETION",
                run_id=run_id,
                candidate_sha=base_sha,
            )
        except PrivateGateError as exc:
            raise CompletionBlocked(str(exc)) from exc
        observed_head_after = current_sha(worktree.path)
        if observed_head_after != base_sha:
            raise CompletionBlocked(
                "External product-completion gate changed the candidate worktree HEAD: "
                f"{observed_head_after} != {base_sha}"
            )
        mutations = changed_files(worktree.path, base_sha)
        if mutations:
            raise CompletionBlocked(
                f"External product-completion gate modified its candidate worktree: {mutations}"
            )
        payload = {
            "suite": "product-completion",
            "candidate_sha": base_sha,
            "observed_head_before": observed_head_before,
            "observed_head_after": observed_head_after,
            "passed": result.passed,
            "result": result.model_dump(mode="json"),
        }
        write_json(artifact_dir / "private-completion-result.json", payload)
        return payload
    finally:
        cleanup_worktree(repo_root, worktree, delete_branch=True)


async def audit_and_expand_or_complete(
    *,
    repo_root: Path,
    config: FactoryConfig,
    ledger: FeatureLedger,
    audits_required: int = 2,
) -> tuple[str, list[str], str]:
    """Independently challenge product completion, then complete or expand the roadmap."""

    if not ledger.build_complete():
        raise CompletionBlocked("Completion audit may run only after current build tasks pass")
    audited_sha = current_sha(repo_root, "main")
    definition = load_definition(repo_root, config)
    deterministic_failures = deterministic_completion_check(repo_root, definition)
    run_id = utc_stamp()
    root = config.resolve(repo_root, config.completion_dir) / run_id
    write_json(
        root / "deterministic-precheck.json",
        {"audited_sha": audited_sha, "failures": deterministic_failures},
    )

    reports: list[CompletionAuditReport] = []
    labels = ["primary-audit", "adversarial-audit", "third-audit"]
    for index in range(audits_required):
        reports.append(
            await _one_review(
                repo_root=repo_root,
                config=config,
                definition=definition,
                ledger=ledger,
                # Completion auditors are independent evidence channels. Only the
                # adjudicator receives prior reports; otherwise later auditors anchor
                # on model prose instead of inspecting the candidate themselves.
                prior_reports=_prior_reports_for(labels[index], reports),
                run_id=run_id,
                label=labels[index],
                role_name=RoleName.COMPLETION_AUDIT,
            )
        )

    final_report: CompletionAuditReport | None = None
    if _needs_adjudicator(reports):
        final_report = await _one_review(
            repo_root=repo_root,
            config=config,
            definition=definition,
            ledger=ledger,
            prior_reports=_prior_reports_for("completion-adjudicator", reports),
            run_id=run_id,
            label="completion-adjudicator",
            role_name=RoleName.COMPLETION_ADJUDICATOR,
        )

    observed_sha = current_sha(repo_root, "main")
    if observed_sha != audited_sha:
        raise CompletionBlocked(
            "Main changed during completion audit; the unaudited candidate cannot be completed: "
            f"{observed_sha} != {audited_sha}"
        )

    private_completion: dict[str, Any] | None = None
    if _reports_agree_complete(reports) and not deterministic_failures:
        private_completion = run_private_completion_gate(
            repo_root=repo_root,
            config=config,
            run_id=run_id,
            candidate_sha=audited_sha,
        )
        if private_completion.get("passed") is not True:
            result = private_completion.get("result")
            detail = "external hidden product-completion suite returned nonzero"
            if isinstance(result, dict):
                stderr_path = cast(dict[str, object], result).get("stderr_path")
                if isinstance(stderr_path, str) and Path(stderr_path).is_file():
                    detail = (
                        Path(stderr_path).read_text(encoding="utf-8", errors="replace")[-1500:]
                        or detail
                    )
            deterministic_failures.append(f"Private product-completion gate failed: {detail}")

    write_json(
        root / "audit-set.json",
        {
            "audited_sha": audited_sha,
            "audits": [report.model_dump(mode="json") for report in reports],
            "adjudicator": final_report.model_dump(mode="json") if final_report else None,
            "deterministic_failures": deterministic_failures,
            "private_completion": private_completion,
        },
    )

    decision = final_report or reports[-1]
    if _reports_agree_complete(reports) and not deterministic_failures:
        evidence = list(
            dict.fromkeys(value for report in reports for value in report.completed_evidence)
        )
        evidence.append(str((root / "private-gate").relative_to(repo_root)))
        write_json(
            root / "PRODUCT_BUILD_COMPLETE_AUDIT.json",
            {
                "audited_sha": audited_sha,
                "evidence": evidence,
                "audit_root": str(root),
                "private_completion": private_completion,
            },
        )
        return "complete", evidence, audited_sha

    if decision.verdict == CompletionVerdict.BLOCKED:
        raise CompletionBlocked("; ".join(decision.blockers) or decision.summary)

    if decision.verdict == CompletionVerdict.COMPLETE and deterministic_failures:
        used_ids = {item.task_id for item in ledger.tasks}
        generated_ids: list[str] = []
        cursor = 1
        for _failure in deterministic_failures:
            while f"AUTO{cursor:03d}" in used_ids:
                cursor += 1
            task_id = f"AUTO{cursor:03d}"
            used_ids.add(task_id)
            generated_ids.append(task_id)
            cursor += 1
        missing = [
            CompletionWorkItem(
                task_id=task_id,
                outcome=f"Resolve deterministic product completion failure: {failure}",
                phase="Completion remediation",
                lead_role="Builder",
                depends_on=[],
                trust_core=True,
                evidence_required=[failure],
            )
            for task_id, failure in zip(generated_ids, deterministic_failures, strict=True)
        ]
    else:
        missing = decision.missing_items

    if not missing:
        details = deterministic_failures or [report.summary for report in reports]
        raise CompletionBlocked(
            "Completion was not independently established and no bounded missing work was "
            f"provided: {details}"
        )

    added = _append_missing_items(
        ledger=ledger,
        items=missing,
        audit_artifact=str(root.relative_to(repo_root)),
    )
    ledger_path = config.resolve(repo_root, config.feature_ledger_path)
    save_feature_ledger(ledger_path, ledger)
    commit_all(repo_root, "expand roadmap")
    write_json(
        root / "ROADMAP_EXPANDED.json",
        {
            "added_task_ids": added,
            "missing_items": [item.model_dump(mode="json") for item in missing],
        },
    )
    return "expanded", added, audited_sha
