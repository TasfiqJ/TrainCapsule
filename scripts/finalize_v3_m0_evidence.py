#!/usr/bin/env python3
"""Run and bind the final reproducible M0 migration acceptance commands."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tcfactory.util import sha256_file  # noqa: E402
from tcfactory.v3.migration_evidence import (  # noqa: E402
    EVIDENCE_ROOT,
    EXPECTED_EVIDENCE_TYPES,
    EXPECTED_EXECUTIONS,
    M0_PREREQUISITE_IDS,
    TRANSCRIPT_ROOT,
    EvidenceExecution,
    FinalMigrationEvidence,
    authority_digests,
    implementation_tree_binding,
    transcript_counts,
    validate_repository_evidence,
)


@dataclass(frozen=True)
class CommandSpec:
    command_id: str
    command: tuple[str, ...]


TRUTH_BOUNDARIES: Final[dict[str, str]] = {
    "V3-MIG-016": "Machine policy replaces human/PR approval only; no external fact is created.",
    "V3-MIG-017": (
        "The rehearsal verifies repository rollback bytes only; it does not mutate Git or runtime."
    ),
    "V3-MIG-018": (
        "Deterministic tests observe controller contracts without starting runtime or a model."
    ),
    "V3-MIG-019": (
        "The simulation uses local fakes and cannot create GPU, customer, or commercial evidence."
    ),
    "V3-MIG-020": (
        "Complete pre-evidence acceptance passed and completion binds only the four prerequisites."
    ),
}
PLANS: Final[dict[str, tuple[str, tuple[CommandSpec, ...], str]]] = {
    work_item_id: (
        EXPECTED_EVIDENCE_TYPES[work_item_id],
        tuple(CommandSpec(command_id, command) for command_id, command in executions),
        TRUTH_BOUNDARIES[work_item_id],
    )
    for work_item_id, executions in EXPECTED_EXECUTIONS.items()
}


def _write_transcript(
    work_item_id: str,
    index: int,
    spec: CommandSpec,
    completed: subprocess.CompletedProcess[str],
    passed_count: int,
    failed_count: int,
) -> Path:
    path = ROOT / TRANSCRIPT_ROOT / f"{work_item_id}-{index:02d}-{spec.command_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "transcriptVersion": 1,
        "command": list(spec.command),
        "workingDirectory": ".",
        "exitCode": completed.returncode,
        "passedCount": passed_count,
        "failedCount": failed_count,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _run(work_item_id: str, specs: tuple[CommandSpec, ...]) -> list[EvidenceExecution]:
    executions: list[EvidenceExecution] = []
    for index, spec in enumerate(specs, start=1):
        completed = subprocess.run(
            list(spec.command), cwd=ROOT, check=False, capture_output=True, text=True
        )
        passed, failed = transcript_counts(
            list(spec.command), completed.returncode, completed.stdout, completed.stderr
        )
        transcript = _write_transcript(
            work_item_id, index, spec, completed, passed, failed
        )
        if completed.returncode != 0:
            print(completed.stdout, end="", file=sys.stderr)
            print(completed.stderr, end="", file=sys.stderr)
            raise RuntimeError(
                f"{work_item_id}/{spec.command_id} failed; transcript preserved at {transcript}"
            )
        executions.append(
            EvidenceExecution(
                command_id=spec.command_id,
                command=list(spec.command),
                exit_code=completed.returncode,
                result="PASS",
                passed_count=passed,
                failed_count=failed,
                failure_attribution="NONE",
                transcript_path=transcript.relative_to(ROOT).as_posix(),
                transcript_sha256=sha256_file(transcript),
            )
        )
    return executions


def _write_receipt(record: FinalMigrationEvidence) -> None:
    path = ROOT / EVIDENCE_ROOT / f"{record.work_item_id}.json"
    path.write_text(
        json.dumps(record.model_dump(mode="json", by_alias=True), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    binding = implementation_tree_binding(ROOT)
    authority = authority_digests(ROOT)
    recorded_at = datetime.now(UTC)
    for work_item_id, (evidence_type, specs, truth_boundary) in PLANS.items():
        executions = _run(work_item_id, specs)
        inputs = (
            {
                prerequisite: sha256_file(ROOT / EVIDENCE_ROOT / f"{prerequisite}.json")
                for prerequisite in M0_PREREQUISITE_IDS
            }
            if work_item_id == "V3-MIG-020"
            else {}
        )
        _write_receipt(
            FinalMigrationEvidence(
                work_item_id=work_item_id,
                result="PASS",
                evidence_type=evidence_type,
                recorded_at=recorded_at,
                binding=binding,
                authority_digests=authority,
                executions=executions,
                evidence_inputs=inputs,
                truth_boundary=truth_boundary,
            )
        )
    count = validate_repository_evidence(ROOT)
    digest = hashlib.sha256(
        b"".join(
            (ROOT / EVIDENCE_ROOT / f"{work_item_id}.json").read_bytes()
            for work_item_id in PLANS
        )
    ).hexdigest()
    print(f"PASS: finalized {count} nonrecursive M0 evidence records; set={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
