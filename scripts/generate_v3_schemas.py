#!/usr/bin/env python3
"""Generate and verify checked-in TrainCapsule V3 factory schemas."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

from pydantic import BaseModel

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tcfactory.backends.base import (
    AgentCapabilityReport,
    AgentRunResult,
    AgentTaskRequest,
    UsageState,
)
from tcfactory.checkpoints import V3Checkpoint
from tcfactory.completion import MilestoneCompletionDecision
from tcfactory.context import V3ContextManifest
from tcfactory.handoffs import V3Handoff
from tcfactory.v3.approvals import HumanApprovalRecord
from tcfactory.v3.base import json_schema_for
from tcfactory.v3.candidate_manifest import CandidateManifest
from tcfactory.v3.configuration import (
    AutonomyV3Config,
    CommercialMaturityConfig,
    ExecutorConfig,
    ExternalEvidenceConfig,
    FactoryV3Config,
    MilestonePolicyConfig,
)
from tcfactory.v3.dispositions import DispositionLedger
from tcfactory.v3.external_evidence import ExternalEvidenceReceipt
from tcfactory.v3.migrations import LegacyMigrationMap
from tcfactory.v3.milestones import MilestoneRoadmap
from tcfactory.v3.pipeline_services import ReleaseCandidate, V3Finding
from tcfactory.v3.planning import V3TaskPacket
from tcfactory.v3.recovery import FindingCounter, HardStuckRecord
from tcfactory.v3.retry_policy import RetryPolicy
from tcfactory.v3.scheduler import SchedulerConfig
from tcfactory.v3.work_items import WorkItem, WorkItemCollection
from tcfactory.value import DecisionValueResult

SCHEMA_ROOT: Final = ROOT / "schemas/factory/v3"
SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    "agent-capabilities.schema.json": AgentCapabilityReport,
    "agent-run-result.schema.json": AgentRunResult,
    "agent-task-request.schema.json": AgentTaskRequest,
    "autonomy-config.schema.json": AutonomyV3Config,
    "candidate-manifest.schema.json": CandidateManifest,
    "checkpoint.schema.json": V3Checkpoint,
    "commercial-maturity-config.schema.json": CommercialMaturityConfig,
    "dispositions.schema.json": DispositionLedger,
    "executors-config.schema.json": ExecutorConfig,
    "external-evidence-config.schema.json": ExternalEvidenceConfig,
    "external-evidence-receipt.schema.json": ExternalEvidenceReceipt,
    "factory-config.schema.json": FactoryV3Config,
    "finding.schema.json": V3Finding,
    "finding-counter.schema.json": FindingCounter,
    "hard-stuck.schema.json": HardStuckRecord,
    "human-approval.schema.json": HumanApprovalRecord,
    "handoff.schema.json": V3Handoff,
    "legacy-migration.schema.json": LegacyMigrationMap,
    "milestones.schema.json": MilestoneRoadmap,
    "milestone-completion.schema.json": MilestoneCompletionDecision,
    "milestone-policy-config.schema.json": MilestonePolicyConfig,
    "retry-policy.schema.json": RetryPolicy,
    "release-candidate.schema.json": ReleaseCandidate,
    "scheduler.schema.json": SchedulerConfig,
    "work-item-v3.schema.json": WorkItem,
    "work-items.schema.json": WorkItemCollection,
    "task-packet.schema.json": V3TaskPacket,
    "usage-state.schema.json": UsageState,
    "context-manifest.schema.json": V3ContextManifest,
    "decision-value.schema.json": DecisionValueResult,
}


def rendered_schemas() -> dict[str, str]:
    rendered: dict[str, str] = {}
    for name, model in SCHEMAS.items():
        schema = json_schema_for(model)
        schema["$id"] = f"https://traincapsule.local/schemas/factory/v3/{name}"
        rendered[name] = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = rendered_schemas()
    if args.check:
        stale = [
            name
            for name, content in expected.items()
            if not (SCHEMA_ROOT / name).is_file()
            or (SCHEMA_ROOT / name).read_text(encoding="utf-8") != content
        ]
        if stale:
            raise SystemExit(f"V3 factory schemas are stale: {', '.join(stale)}")
        print(f"PASS: {len(expected)} V3 factory schemas match their Pydantic models")
        return 0
    SCHEMA_ROOT.mkdir(parents=True, exist_ok=True)
    for name, content in expected.items():
        (SCHEMA_ROOT / name).write_text(content, encoding="utf-8", newline="\n")
    print(f"Wrote {len(expected)} V3 factory schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
