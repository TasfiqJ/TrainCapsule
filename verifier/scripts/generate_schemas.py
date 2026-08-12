#!/usr/bin/env python3
"""Generate exact public schemas for the independent verifier distribution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Final

from pydantic import BaseModel
from traincapsule_verifier.models import (
    ActivationReceipt,
    ActivationRequest,
    AuthorityAnchor,
    CheckAuthorization,
    InstallationAttestation,
    MachinePolicyReceipt,
    OracleExecutionResult,
    RevocationList,
    TrustedEvidenceManifest,
    VerificationRequest,
    VerifierPolicy,
)

ROOT: Final = Path(__file__).resolve().parents[1]
SCHEMA_ROOT: Final = ROOT / "schemas"
SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    "activation-receipt.schema.json": ActivationReceipt,
    "activation-request.schema.json": ActivationRequest,
    "authority-anchor.schema.json": AuthorityAnchor,
    "check-authorization.schema.json": CheckAuthorization,
    "installation-attestation.schema.json": InstallationAttestation,
    "machine-policy-receipt.schema.json": MachinePolicyReceipt,
    "oracle-execution-result.schema.json": OracleExecutionResult,
    "revocation-list.schema.json": RevocationList,
    "trusted-evidence-manifest.schema.json": TrustedEvidenceManifest,
    "verification-request.schema.json": VerificationRequest,
    "verifier-policy.schema.json": VerifierPolicy,
}


def rendered_schemas() -> dict[str, bytes]:
    rendered: dict[str, bytes] = {}
    for name, model in sorted(SCHEMAS.items()):
        schema = model.model_json_schema(by_alias=True, mode="validation")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"https://traincapsule.local/schemas/verifier/v3.1/{name}"
        rendered[name] = (
            json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        ).encode("utf-8")
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = rendered_schemas()
    if args.check:
        observed = {path.name for path in SCHEMA_ROOT.glob("*.schema.json")}
        stale = [
            name
            for name, content in expected.items()
            if not (SCHEMA_ROOT / name).is_file() or (SCHEMA_ROOT / name).read_bytes() != content
        ]
        if stale or observed != set(expected):
            raise SystemExit(
                f"independent verifier schemas are stale: {stale}; observed={sorted(observed)}"
            )
        print(f"PASS: {len(expected)} independent verifier schemas match exactly")
        return 0
    SCHEMA_ROOT.mkdir(parents=True, exist_ok=True)
    for name, content in expected.items():
        (SCHEMA_ROOT / name).write_bytes(content)
    print(f"Wrote {len(expected)} independent verifier schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
