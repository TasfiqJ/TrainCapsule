from __future__ import annotations

import re
import sys
from typing import cast

from gate_common import ROOT, task_payload

REQUIRED_SPEC_HEADINGS = (
    "goal",
    "authority",
    "acceptance criteria",
    "non-goals",
    "verification",
    "failure",
)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: contract_gate.py TASK_ID", file=sys.stderr)
        return 2
    task_id = sys.argv[1]
    task = task_payload(task_id)
    if task.get("task_id") != task_id:
        print(f"task_id mismatch: {task.get('task_id')!r} != {task_id!r}", file=sys.stderr)
        return 1
    criteria = task.get("acceptance_criteria")
    if not isinstance(criteria, list):
        print("acceptance_criteria must contain 1-25 items", file=sys.stderr)
        return 1
    typed_criteria = cast(list[object], criteria)
    if not 1 <= len(typed_criteria) <= 25:
        print("acceptance_criteria must contain 1-25 items", file=sys.stderr)
        return 1
    pipeline = task.get("pipeline")
    if not isinstance(pipeline, list) or not pipeline:
        print("pipeline is empty", file=sys.stderr)
        return 1
    has_specification = any(
        isinstance(stage, dict) and cast(dict[str, object], stage).get("role") == "specification"
        for stage in cast(list[object], pipeline)
    )
    if not has_specification:
        print(f"PASS {task_id}: deterministic packet has no specification stage")
        return 0
    spec = ROOT / "specs" / "tasks" / f"{task_id}.md"
    if not spec.is_file():
        print(f"missing frozen task specification: {spec.relative_to(ROOT)}", file=sys.stderr)
        return 1
    text = spec.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    missing = [
        heading
        for heading in REQUIRED_SPEC_HEADINGS
        if not re.search(rf"^#+\s+.*{re.escape(heading)}", lowered, re.MULTILINE)
    ]
    if missing:
        print(f"specification missing headings: {', '.join(missing)}", file=sys.stderr)
        return 1
    if task_id.lower() not in lowered:
        print("specification does not name its task ID", file=sys.stderr)
        return 1
    if "unknown" not in lowered and task.get("risk_tier") in {"integration", "trust", "trust_core"}:
        print("critical specification must define UNKNOWN/authority handling", file=sys.stderr)
        return 1
    print(f"PASS {task_id}: frozen task contract is present and structurally complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
