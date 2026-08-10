from __future__ import annotations

import sys
from typing import cast

from gate_common import catalog_payload, require_patterns, task_payload


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: milestone_gate.py TASK_ID", file=sys.stderr)
        return 2
    task_id = sys.argv[1]
    task = task_payload(task_id)
    catalog = catalog_payload()
    tasks = catalog.get("tasks")
    if not isinstance(tasks, dict):
        print("task catalog has no tasks mapping", file=sys.stderr)
        return 1
    typed_tasks = cast(dict[str, object], tasks)
    current = typed_tasks.get(task_id)
    if not isinstance(current, dict):
        print(f"catalog lacks {task_id}", file=sys.stderr)
        return 1
    typed_current = cast(dict[str, object], current)
    milestone = typed_current.get("milestone")
    if not milestone:
        print(f"PASS {task_id}: no milestone checkpoint requested")
        return 0
    required: list[str] = []
    for candidate_id, raw in typed_tasks.items():
        if not isinstance(raw, dict):
            continue
        typed_raw = cast(dict[str, object], raw)
        if candidate_id == task_id or typed_raw.get("phase") == task.get("phase"):
            outputs = typed_raw.get("expected_outputs")
            if isinstance(outputs, list):
                required.extend(str(value) for value in cast(list[object], outputs))
        if candidate_id == task_id:
            break
    missing = require_patterns(required)
    if missing:
        print(
            f"milestone {milestone} is missing declared artifacts: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1
    print(f"PASS {task_id}: milestone {milestone} artifacts are present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
