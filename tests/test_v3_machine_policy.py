from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tcfactory.v3.enums import PolicyScope, WorkStatus
from tcfactory.v3.pipeline_services import (
    MachinePolicyGateReceipt,
    TrustedMachinePolicyRecord,
    evaluate_machine_policy_gate,
)

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
DIGEST = "sha256:" + ("a" * 64)
SHA = "b" * 40


def _record(**updates: bool) -> TrustedMachinePolicyRecord:
    receipt = MachinePolicyGateReceipt.model_validate(
        {
            "issuer": "INDEPENDENT_MACHINE_POLICY_VERIFIER",
            "scope": "ROADMAP_EXPANSION",
            "candidateSha": SHA,
            "artifactDigests": {"review": DIGEST},
            "authorityManifestDigest": DIGEST,
            "issuedAt": NOW - timedelta(minutes=1),
            "expiresAt": NOW + timedelta(minutes=5),
            "nonce": "unique-policy-nonce-0001",
            "revocationEpoch": 7,
            "signature": {
                "algorithm": "ed25519",
                "keyId": "phase3-independent-key",
                "value": "detached-signature-is-verified-outside-the-agent",
            },
        }
    )
    values = {
        "receipt": receipt,
        "signature_valid": True,
        "issuer_authorized": True,
        "source_agent_writable": False,
        "nonce_fresh": True,
        "revoked": False,
    }
    values.update(updates)
    return TrustedMachinePolicyRecord.model_validate(values)


def test_machine_policy_gate_requires_independently_verified_record() -> None:
    blocked = evaluate_machine_policy_gate(
        None,
        scope=PolicyScope.ROADMAP_EXPANSION,
        candidate_sha=SHA,
        artifact_digests={"review": DIGEST},
        authority_manifest_digest=DIGEST,
        now=NOW,
    )
    assert blocked.passed is False
    assert blocked.state is WorkStatus.BLOCKED_POLICY

    for invalid in (
        {"signature_valid": False},
        {"issuer_authorized": False},
        {"source_agent_writable": True},
        {"nonce_fresh": False},
        {"revoked": True},
    ):
        with pytest.raises(ValueError):
            evaluate_machine_policy_gate(
                _record(**invalid),
                scope=PolicyScope.ROADMAP_EXPANSION,
                candidate_sha=SHA,
                artifact_digests={"review": DIGEST},
                authority_manifest_digest=DIGEST,
                now=NOW,
            )


def test_machine_policy_gate_binds_scope_candidate_artifacts_and_authority() -> None:
    decision = evaluate_machine_policy_gate(
        _record(),
        scope=PolicyScope.ROADMAP_EXPANSION,
        candidate_sha=SHA,
        artifact_digests={"review": DIGEST},
        authority_manifest_digest=DIGEST,
        now=NOW,
    )
    assert decision.passed is True

    with pytest.raises(ValueError, match="candidate SHA mismatch"):
        evaluate_machine_policy_gate(
            _record(),
            scope=PolicyScope.ROADMAP_EXPANSION,
            candidate_sha="c" * 40,
            artifact_digests={"review": DIGEST},
            authority_manifest_digest=DIGEST,
            now=NOW,
        )
