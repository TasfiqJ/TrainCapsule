from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROW = re.compile(
    r"^\|\s*(T\d{3})\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$"
)


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: generate_task_ledger.py ROADMAP.md OUTPUT_DIR")

    roadmap = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    content = roadmap.read_text(encoding="utf-8")
    tasks: list[dict[str, str]] = []

    for line in content.splitlines():
        match = ROW.match(line)
        if not match:
            continue
        task_id, epic, priority, role, title = (part.strip() for part in match.groups())
        tasks.append(
            {
                "id": task_id,
                "epic": epic,
                "priority": priority,
                "role": role,
                "title": title,
                "status": "planned",
                "truth_state": "NOT_STARTED",
            }
        )

    expected = [f"T{number:03d}" for number in range(1, 125)]
    actual = [task["id"] for task in tasks]
    if actual != expected:
        raise SystemExit(f"task ledger mismatch: expected T001-T124, got {len(actual)} rows")

    digest = hashlib.sha256(roadmap.read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    tasks_dir = output / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    ledger = {
        "schema_version": "1.0",
        "product": "TrainCapsule",
        "source": "12_ROADMAP_BACKLOG_AND_MASTER_BUILD_PROMPT.md",
        "source_sha256": digest,
        "task_count": len(tasks),
        "activation_status": "BLOCKED_PENDING_FACTORY_CALIBRATION",
        "tasks": tasks,
    }
    (output / "roadmap.json").write_text(
        json.dumps(ledger, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    for task in tasks:
        (tasks_dir / f"{task['id']}.json").write_text(
            json.dumps(task, indent=2) + "\n", encoding="utf-8", newline="\n"
        )

    print(f"generated {len(tasks)} tasks from {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
