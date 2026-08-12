#!/usr/bin/env python3
"""Generate or verify the committed TrainCapsule product JSON schemas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from traincapsule_core.base import product_json_schema
from traincapsule_core.models import (
    EligibilityDecision,
    EnvironmentIdentity,
    EvidenceArtifact,
    EvidenceCompletenessReport,
    IncidentCase,
    NativeFinding,
    WorkloadIdentity,
)
from traincapsule_ingest_pytorch import FlightRecorderImport
from traincapsule_qualify import NativeBaseline, PreflightInputs

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "schemas/product"
MODELS: dict[str, type[BaseModel]] = {
    "eligibility-decision.schema.json": EligibilityDecision,
    "environment-identity.schema.json": EnvironmentIdentity,
    "evidence-artifact.schema.json": EvidenceArtifact,
    "evidence-completeness-report.schema.json": EvidenceCompletenessReport,
    "flight-recorder-import.schema.json": FlightRecorderImport,
    "incident-case.schema.json": IncidentCase,
    "native-baseline.schema.json": NativeBaseline,
    "native-finding.schema.json": NativeFinding,
    "preflight-inputs.schema.json": PreflightInputs,
    "workload-identity.schema.json": WorkloadIdentity,
}


def rendered_schema(model: type[BaseModel]) -> bytes:
    schema: dict[str, Any] = product_json_schema(model)
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []
    if not args.check:
        SCHEMA_ROOT.mkdir(parents=True, exist_ok=True)
    for filename, model in sorted(MODELS.items()):
        destination = SCHEMA_ROOT / filename
        expected = rendered_schema(model)
        if args.check:
            if not destination.is_file() or destination.read_bytes() != expected:
                failures.append(filename)
        else:
            destination.write_bytes(expected)
    if failures:
        print("stale product schemas: " + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
