from __future__ import annotations

import json
import sys
from pathlib import Path

from tcfactory.config import load_task
from tcfactory.gates import PathPolicyError, gate_argv


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: validate_proposal.py PACKET TASK_ID DEPENDENCIES_JSON")
    packet = load_task(Path(sys.argv[1]))
    expected_task = sys.argv[2]
    expected_dependencies = json.loads(sys.argv[3])
    if packet.task_id != expected_task:
        raise SystemExit(f"task_id must be {expected_task}, found {packet.task_id}")
    if packet.depends_on != expected_dependencies:
        raise SystemExit(
            f"depends_on must be {expected_dependencies!r}, found {packet.depends_on!r}"
        )
    if len(packet.acceptance_criteria) > 25:
        raise SystemExit("acceptance_criteria exceeds hard ceiling of 25")
    for gate in packet.gates:
        try:
            gate_argv(gate.command, cwd=Path.cwd().resolve())
        except PathPolicyError as exc:
            raise SystemExit(f"gate {gate.name!r} is not controller-safe: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
