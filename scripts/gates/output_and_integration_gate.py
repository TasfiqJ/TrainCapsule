from __future__ import annotations

import re
import subprocess
import sys
from typing import cast

from gate_common import ROOT, require_patterns, task_payload

from tcfactory.research_policy import (
    ResearchPolicyError,
    parse_research_record,
    validate_evidence_manifest,
    validate_verdict_consistency,
)

CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".sh"}
PLACEHOLDERS = (
    re.compile(r"raise\s+NotImplementedError"),
    re.compile(r"\bIMPLEMENT\s+ME\b", re.IGNORECASE),
    re.compile(r"\bplaceholder\s+implementation\b", re.IGNORECASE),
    re.compile(r"return\s+['\"]TODO['\"]", re.IGNORECASE),
)


def _run_generic_research_evidence_gate(
    *, task_id: str, task: dict[str, object], outputs: list[object]
) -> int:
    pipeline = cast(list[dict[str, object]], task.get("pipeline") or [])
    research_stage = next(
        (stage for stage in pipeline if stage.get("role") == "research"),
        None,
    )
    if research_stage is None:
        print("research-evidence check requires a research stage", file=sys.stderr)
        return 1

    declared = [str(value).replace("\\", "/") for value in outputs]
    record_value = next(
        (
            value
            for value in declared
            if value.startswith("docs/research/") and value.endswith(".md")
        ),
        None,
    )
    manifest_value = next(
        (
            value
            for value in declared
            if value == f"docs/evidence/{task_id}/manifest.json"
        ),
        None,
    )
    plan_value = next(
        (
            value
            for value in declared
            if value == f"docs/evidence/{task_id}/query-plan.json"
        ),
        None,
    )
    missing_declarations = [
        label
        for label, value in (
            ("research record", record_value),
            ("evidence manifest", manifest_value),
            ("query plan", plan_value),
        )
        if value is None
    ]
    if missing_declarations:
        print(
            "research packet is missing standard output declarations: "
            + ", ".join(missing_declarations),
            file=sys.stderr,
        )
        return 1
    assert record_value is not None
    assert manifest_value is not None
    assert plan_value is not None
    record_path = ROOT / record_value
    manifest_path = ROOT / manifest_value
    plan_path = ROOT / plan_value
    missing_files = [
        str(path.relative_to(ROOT))
        for path in (record_path, manifest_path, plan_path)
        if not path.is_file()
    ]
    if missing_files:
        print(
            "research evidence bundle is missing: " + ", ".join(missing_files),
            file=sys.stderr,
        )
        return 1

    record = record_path.read_text(encoding="utf-8", errors="replace")
    try:
        _verdict, labels = parse_research_record(record)
    except ResearchPolicyError as exc:
        print(f"research record is invalid: {exc}", file=sys.stderr)
        return 1
    consistency_errors = validate_verdict_consistency(record)
    if consistency_errors:
        print("; ".join(consistency_errors), file=sys.stderr)
        return 1
    allowed_domains = {
        str(value).lower()
        for value in cast(list[object], research_stage.get("allowed_domains") or [])
    }
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    manifest_errors = validate_evidence_manifest(
        repo_root=ROOT,
        manifest_path=manifest_path,
        labels=labels,
        allowed_domains=allowed_domains,
        task_id=task_id,
        query_plan_path=plan_path,
        current_candidate_sha=head,
        require_version=2,
    )
    if manifest_errors:
        print("; ".join(manifest_errors), file=sys.stderr)
        return 1
    print(f"PASS {task_id}: version-2 research evidence contract is reproducible")
    return 0


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        print("usage: output_and_integration_gate.py TASK_ID [CHECK]", file=sys.stderr)
        return 2
    task_id = sys.argv[1]
    check = sys.argv[2] if len(sys.argv) == 3 else "all"
    task = task_payload(task_id)
    outputs = task.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        print("task has no declared outputs", file=sys.stderr)
        return 1
    typed_outputs = cast(list[object], outputs)
    missing = require_patterns(str(value) for value in typed_outputs)
    if missing:
        print("declared outputs are missing: " + ", ".join(missing), file=sys.stderr)
        return 1

    violations: list[str] = []
    for raw in typed_outputs:
        pattern = str(raw).replace("**", "*")
        base = pattern.split("*", 1)[0].rstrip("/")
        root = ROOT / base if base else ROOT
        candidates = [root] if root.is_file() else list(root.rglob("*")) if root.exists() else []
        for path in candidates:
            if not path.is_file() or path.suffix.lower() not in CODE_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in PLACEHOLDERS:
                if marker.search(text):
                    violations.append(str(path.relative_to(ROOT)))
                    break
    if violations:
        print(
            "placeholder implementation found in: " + ", ".join(sorted(set(violations))),
            file=sys.stderr,
        )
        return 1

    if check == "research-evidence":
        return _run_generic_research_evidence_gate(
            task_id=task_id,
            task=task,
            outputs=typed_outputs,
        )

    if task_id == "T002":
        record_path = ROOT / "docs/research/T002_name_trademark_check.md"
        manifest_path = ROOT / "docs/evidence/T002/manifest.json"
        supported = {
            "all",
            "file-present",
            "verdict-labeled",
            "no-silent-upgrade",
            "evidence-reproducible",
        }
        if check not in supported:
            print(f"unsupported T002 research check: {check}", file=sys.stderr)
            return 1
        if check in {"all", "file-present"}:
            missing_research = [
                str(path.relative_to(ROOT))
                for path in (record_path, manifest_path)
                if not path.is_file()
            ]
            if missing_research:
                print(
                    "T002 research bundle is missing: " + ", ".join(missing_research),
                    file=sys.stderr,
                )
                return 1
        if not record_path.is_file():
            print("T002 research record is missing", file=sys.stderr)
            return 1
        record = record_path.read_text(encoding="utf-8", errors="replace")
        try:
            _verdict, labels = parse_research_record(record)
        except ResearchPolicyError as exc:
            print(f"T002 research record is invalid: {exc}", file=sys.stderr)
            return 1
        if check in {"all", "no-silent-upgrade"}:
            consistency_errors = validate_verdict_consistency(record)
            if consistency_errors:
                print("; ".join(consistency_errors), file=sys.stderr)
                return 1
        if check in {"all", "evidence-reproducible"}:
            pipeline = cast(list[dict[str, object]], task.get("pipeline") or [])
            research_stage: dict[str, object] = {}
            for candidate_stage in pipeline:
                if candidate_stage.get("role") == "research":
                    research_stage = candidate_stage
                    break
            allowed_domains = {
                str(value).lower()
                for value in cast(list[object], research_stage.get("allowed_domains") or [])
            }
            manifest_errors = validate_evidence_manifest(
                repo_root=ROOT,
                manifest_path=manifest_path,
                labels=labels,
                allowed_domains=allowed_domains,
            )
            if manifest_errors:
                print("; ".join(manifest_errors), file=sys.stderr)
                return 1
    elif len(sys.argv) == 3:
        print(f"task-specific CHECK is unsupported for {task_id}", file=sys.stderr)
        return 2

    # Static, task-specific path requirements. These never execute model-authored commands.
    required_by_task: dict[str, tuple[str, ...]] = {
        "T001": (
            "SOURCE_PRECEDENCE.md",
            "docs/source-of-truth/final-2026-08-09/FINAL_MANIFEST.json",
            ".factory/source-locks/FINAL_MANIFEST.json",
        ),
        "T008": ("PUBLIC_INCIDENT_CORPUS/index.json",),
        "T013": ("schemas/**/*workload*.*", "schemas/**/*change*.*"),
        "T017": ("schemas/**/*evidence*.*", "tests/**/*provenance*.*"),
        "T022": ("packages/cli/**/*", "tests/**/*cli*.*"),
        "T024": ("schemas/**/*adapter*.*", "tests/**/*adapter*.*"),
        "T031": ("tests/security/**/*",),
        "T040": (
            "incident-packs/pre_collective_lifecycle_v1/**/*",
            "tests/fault-injection/**/*",
        ),
        "T061": ("packages/reducer/**/*", "tests/property/**/*"),
        "T062": ("packages/reducer/**/*", "tests/property/**/*"),
        "T065": ("packages/reducer/**/*", "tests/property/**/*"),
        "T076": ("containers/**/*", "tests/security/**/*"),
        "T080": ("schemas/**/*tcap*.*", "packages/exchange/**/*"),
        "T082": ("tests/replay/**/*",),
        "T084": ("packages/recovery/**/*", "tests/fault-injection/**/*"),
        "T090": ("schemas/**/*contract*.*", "packages/contracts/**/*"),
        "T094": ("tests/qualification/**/*", "packages/qualify/**/*"),
        "T095": (
            "incident-packs/checkpoint_resume_state_v1/**/*",
            "tests/fault-injection/**/*",
        ),
        "T098": ("tests/qualification/**/*", "tests/replay/**/*"),
        "T105": ("packages/cli/**/*", "tests/e2e/**/*"),
        "T106": ("apps/local-viewer/**/*", "tests/e2e/**/*"),
    }
    extra_missing = require_patterns(required_by_task.get(task_id, ()))
    if extra_missing:
        print(
            "real-integration evidence is missing: " + ", ".join(extra_missing),
            file=sys.stderr,
        )
        return 1
    print(f"PASS {task_id}: declared outputs and static integration evidence are present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
