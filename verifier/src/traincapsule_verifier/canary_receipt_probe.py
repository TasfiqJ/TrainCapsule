"""Ephemeral cryptographic negative probe for the Phase 16 receipt canary."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .crypto import sign_model
from .models import (
    CommercialCeiling,
    EngineeringCeiling,
    GateResult,
    MachinePolicyReceipt,
    NativeDisposition,
    PolicyDecision,
    ValueDisposition,
)
from .public_crypto import SignatureError, verify_model_signature

DIGEST = "sha256:" + "a" * 64
SHA = "a" * 40


def _receipt(
    key: Ed25519PrivateKey, *, now: datetime, expired: bool = False
) -> MachinePolicyReceipt:
    issued = now - timedelta(hours=2) if expired else now - timedelta(minutes=1)
    expires = now - timedelta(hours=1) if expired else now + timedelta(minutes=15)
    unsigned = MachinePolicyReceipt(
        schema_version="3.1",
        receipt_id="MPOL:CANARY:NEGATIVES",
        policy_id="POLICY:CANARY",
        policy_version="3.1",
        issuer_id="ISSUER:EPHEMERAL",
        issuer_key_id="KEY:EPHEMERAL",
        issued_at=issued,
        expires_at=expires,
        revocation_epoch=1,
        nonce="ephemeral-canary-nonce",
        request_digest=DIGEST,
        work_item_id="V3-MIG-019",
        milestone_id="M0_SOURCE_INSTALLATION",
        lane="FACTORY",
        risk_tier="TRUST_CORE",
        candidate_sha=SHA,
        candidate_tree_sha=SHA,
        base_sha=SHA,
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_generation_digest=DIGEST,
        context_manifest_digest=DIGEST,
        task_packet_digest=DIGEST,
        candidate_manifest_digest=DIGEST,
        checkpoint_digest=DIGEST,
        required_gate_results={"GATE:CANARY": GateResult.PASS},
        private_gate_suite_id="GATES:PRIVATE",
        private_gate_runner_digest=DIGEST,
        independent_oracle_ids=["ORACLE:CANARY"],
        raw_evidence_artifact_hashes=[DIGEST],
        native_substitute_disposition=NativeDisposition.INCREMENTAL_VALUE,
        decision_value_disposition=ValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED,
        engineering_maturity_ceiling=EngineeringCeiling.PASSED,
        commercial_maturity_ceiling=CommercialCeiling.PILOT_ELIGIBLE,
        allowed_claims=["CLAIM:CANARY"],
        publication_scope=["canary/result.json"],
        decision=PolicyDecision.PASS,
        signature_algorithm="ed25519",
        signature="A" * 88,
    )
    return unsigned.model_copy(update={"signature": sign_model(unsigned, key)})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args()
    if not args.artifact_root.is_dir() or args.artifact_root.is_symlink():
        return 2
    now = datetime.now(UTC)
    key = Ed25519PrivateKey.generate()
    valid = _receipt(key, now=now)
    verify_model_signature(valid, key.public_key())
    invalid = valid.model_copy(update={"signature": "A" * 88})
    invalid_rejected = False
    try:
        verify_model_signature(invalid, key.public_key())
    except SignatureError:
        invalid_rejected = True
    expired = _receipt(key, now=now, expired=True)
    verify_model_signature(expired, key.public_key())
    revoked_ids = {valid.receipt_id}
    result = {
        "missingRejected": not (args.artifact_root / "missing-receipt.json").exists(),
        "invalidRejected": invalid_rejected,
        "expiredRejected": expired.expires_at <= now,
        "revokedRejected": valid.receipt_id in revoked_ids,
        "validSignatureAccepted": True,
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if all(result.values()) else 3


if __name__ == "__main__":
    raise SystemExit(main())
