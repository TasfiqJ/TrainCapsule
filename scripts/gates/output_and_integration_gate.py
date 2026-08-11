from __future__ import annotations

import re
import sys
from typing import cast

from gate_common import ROOT, require_patterns, task_payload

CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".sh"}
PLACEHOLDERS = (
    re.compile(r"raise\s+NotImplementedError"),
    re.compile(r"\bIMPLEMENT\s+ME\b", re.IGNORECASE),
    re.compile(r"\bplaceholder\s+implementation\b", re.IGNORECASE),
    re.compile(r"return\s+['\"]TODO['\"]", re.IGNORECASE),
)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: output_and_integration_gate.py TASK_ID", file=sys.stderr)
        return 2
    task_id = sys.argv[1]
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

    if task_id == "T002":
        record_path = ROOT / "docs/research/T002_name_trademark_check.md"
        record = record_path.read_text(encoding="utf-8", errors="replace")
        if not re.search(
            r"Overall verdict:\s*(clear|conflicts_found|unknown)",
            record,
            re.IGNORECASE,
        ):
            print("T002 research record is missing a valid Overall verdict", file=sys.stderr)
            return 1
        if re.search(
            r"UNKNOWN[^\n]*(upgraded|converted|treated as)[^\n]*CLEAR",
            record,
            re.IGNORECASE,
        ):
            print("T002 research record silently upgrades UNKNOWN to CLEAR", file=sys.stderr)
            return 1

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
