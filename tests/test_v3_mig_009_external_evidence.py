"""Cryptographic acceptance evidence for V3-MIG-009.

These tests exercise the production exact-byte OpenSSL verifier with real
Ed25519 keys.  Only the root-ownership predicate is replaced because pytest's
temporary directory is deliberately owned by the unprivileged test user.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator

import tcfactory.v3.external_evidence as evidence_module
from tcfactory.v3.enums import ArtifactLocationClass, EvidenceType, SignatureAlgorithm
from tcfactory.v3.external_evidence import (
    EvidenceArtifact,
    EvidenceIssuer,
    EvidenceSignature,
    ExternalEvidenceAuthorityAnchor,
    ExternalEvidenceReceipt,
    ExternalEvidenceRevocationList,
    ExternalEvidenceVerificationError,
    load_verified_external_evidence_payload,
)
from tcfactory.v3.external_evidence_authority import (
    ExternalEvidenceAuthorityLedger,
    ExternalEvidenceAuthorityState,
    key_fingerprint,
    load_external_evidence_authority_state,
)

ROOT = Path(__file__).resolve().parents[1]
SUBJECT = "V3-MKT-901"
NOW = datetime(2026, 8, 18, 12, tzinfo=UTC)
AUTHORITY_ID = "AUTHORITY:V3-MIG-009"
ISSUER_ID = "ISSUER:V3-MIG-009"
KEY_ID = "KEY:V3-MIG-009"


@dataclass(frozen=True)
class InstalledAuthority:
    trusted_root: Path
    public_key: Path
    state: Path
    environment: dict[str, str]


class SchemaValidator(Protocol):
    def validate(self, instance: object) -> None: ...


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _receipt(
    *,
    subject_id: str = SUBJECT,
    algorithm: SignatureAlgorithm = SignatureAlgorithm.ED25519,
) -> ExternalEvidenceReceipt:
    return ExternalEvidenceReceipt(
        receipt_id="XREC-V3-MIG-009",
        evidence_type=EvidenceType.CUSTOMER_CONVERSATION,
        subject_id=subject_id,
        issuer=EvidenceIssuer(id=ISSUER_ID, authority="independent test issuer"),
        issued_at=NOW - timedelta(minutes=2),
        observed_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(days=1),
        revocation_epoch=1,
        revoked=False,
        nonce="9" * 32,
        outcome="bounded independently signed observation",
        artifacts=[
            EvidenceArtifact(
                name="observation.json",
                digest="sha256:" + "a" * 64,
                location_class=ArtifactLocationClass.TRUSTED_EXTERNAL,
            )
        ],
        limitations=["Cryptographic integration fixture; no commercial claim."],
        signature=EvidenceSignature(
            algorithm=algorithm,
            key_id=KEY_ID,
            value="detached-signature-in-companion-file",
        ),
        synthetic_test_only=False,
    )


def _write_signed(path: Path, raw: bytes, key: Ed25519PrivateKey) -> None:
    path.write_bytes(raw)
    path.with_suffix(path.suffix + ".sig").write_bytes(key.sign(raw))


def _install_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    receipt: ExternalEvidenceReceipt | None = None,
    revoked_nonces: tuple[str, ...] = (),
    signing_key: Ed25519PrivateKey | None = None,
    verification_key: Ed25519PrivateKey | None = None,
) -> InstalledAuthority:
    signer = signing_key or Ed25519PrivateKey.generate()
    verifier_key = verification_key or signer
    public_raw = verifier_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    trusted_root = tmp_path / "trusted-external-authority"
    trusted_root.mkdir()
    public_key = tmp_path / "external-evidence-ed25519.pub"
    public_key.write_bytes(public_raw)
    state_path = tmp_path / "external-evidence-authority-state.json"

    bound_receipt = receipt or _receipt()
    revocations = ExternalEvidenceRevocationList(
        authority_id=AUTHORITY_ID,
        issuer_id=ISSUER_ID,
        key_id=KEY_ID,
        epoch=1,
        previous_list_digest=None,
        issued_at=NOW - timedelta(minutes=3),
        expires_at=NOW + timedelta(days=1),
        revoked_receipt_ids=[],
        revoked_nonces=list(revoked_nonces),
    )
    revocation_raw = revocations.canonical_json_bytes()
    anchor = ExternalEvidenceAuthorityAnchor(
        authority_id=AUTHORITY_ID,
        issuer_id=ISSUER_ID,
        key_id=KEY_ID,
        epoch=1,
        current_revocation_digest=_digest(revocation_raw),
        previous_revocation_digest=None,
        issued_at=NOW - timedelta(minutes=3),
        expires_at=NOW + timedelta(days=1),
    )
    anchor_raw = anchor.canonical_json_bytes()

    _write_signed(trusted_root / f"{SUBJECT}.json", bound_receipt.canonical_json_bytes(), signer)
    _write_signed(trusted_root / "revocation-list.json", revocation_raw, signer)
    _write_signed(trusted_root / "authority-anchor.json", anchor_raw, signer)

    ledger = ExternalEvidenceAuthorityLedger(
        entries=[
            ExternalEvidenceAuthorityState(
                authority_id=AUTHORITY_ID,
                epoch=1,
                anchor_digest=_digest(anchor_raw),
                revocation_list_digest=_digest(revocation_raw),
                key_fingerprint=key_fingerprint(public_raw),
                previous_state_digest=None,
                advanced_at=NOW - timedelta(minutes=2),
            )
        ]
    )
    state_path.write_bytes(ledger.canonical_json_bytes())

    # The production trust check requires uid 0.  The integration fixture is
    # unprivileged, so preserve all parsing/chain checks while substituting the
    # current uid only at this OS ownership boundary.
    def accept_fixture_ownership(path: Path) -> None:
        path.stat()

    def load_fixture_authority_state(path: Path) -> ExternalEvidenceAuthorityLedger:
        return load_external_evidence_authority_state(
            path, expected_owner_uid=os.getuid()
        )

    monkeypatch.setattr(
        evidence_module, "_assert_privileged_read_only", accept_fixture_ownership
    )
    monkeypatch.setattr(
        evidence_module,
        "load_external_evidence_authority_state",
        load_fixture_authority_state,
    )
    environment = {
        "V3_MIG_009_ROOT": str(trusted_root),
        "V3_MIG_009_KEY": str(public_key),
        "V3_MIG_009_STATE": str(state_path),
    }
    return InstalledAuthority(trusted_root, public_key, state_path, environment)


def _load(installed: InstalledAuthority):
    return load_verified_external_evidence_payload(
        repo_root=installed.trusted_root.parent / "repository",
        subject_id=SUBJECT,
        trusted_root_environment_variable="V3_MIG_009_ROOT",
        trusted_public_key_environment_variable="V3_MIG_009_KEY",
        trusted_authority_state_environment_variable="V3_MIG_009_STATE",
        environment=installed.environment,
        now=NOW,
    )


def test_real_ed25519_receipt_revocation_and_anchor_verify_as_one_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = _install_authority(tmp_path, monkeypatch)

    payload = _load(installed)

    assert payload.record.receipt.subject_id == SUBJECT
    assert payload.record.signature_valid is True
    assert payload.record.source_agent_writable is False
    assert payload.canonical_digest == _digest(payload.canonical_bytes)
    assert set(payload.authority_payloads) == {
        "receipt",
        "receipt-signature",
        "revocation-list",
        "revocation-list-signature",
        "authority-anchor",
        "authority-anchor-signature",
        "monotonic-authority-state",
        "authority-public-key",
    }
    assert all(
        payload.authority_digests[name] == _digest(raw)
        for name, raw in payload.authority_payloads.items()
    )


@pytest.mark.parametrize("target", ["receipt", "signature"])
def test_real_ed25519_rejects_tampered_receipt_or_detached_signature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    installed = _install_authority(tmp_path, monkeypatch)
    receipt_path = installed.trusted_root / f"{SUBJECT}.json"
    signature_path = receipt_path.with_suffix(".json.sig")
    if target == "receipt":
        receipt_path.write_bytes(receipt_path.read_bytes() + b" ")
    else:
        signature = bytearray(signature_path.read_bytes())
        signature[-1] ^= 0x01
        signature_path.write_bytes(signature)

    with pytest.raises(ExternalEvidenceVerificationError, match="signature verification failed"):
        _load(installed)


def test_real_ed25519_rejects_receipts_signed_by_the_wrong_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = _install_authority(
        tmp_path,
        monkeypatch,
        signing_key=Ed25519PrivateKey.generate(),
        verification_key=Ed25519PrivateKey.generate(),
    )

    with pytest.raises(ExternalEvidenceVerificationError, match="signature verification failed"):
        _load(installed)


def test_signed_revocation_list_rejects_a_revoked_nonce(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = _install_authority(
        tmp_path,
        monkeypatch,
        revoked_nonces=("9" * 32,),
    )

    with pytest.raises(ExternalEvidenceVerificationError, match="receipt is revoked"):
        _load(installed)


def test_validly_signed_receipt_still_requires_the_exact_subject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = _install_authority(
        tmp_path,
        monkeypatch,
        receipt=_receipt(subject_id="V3-MKT-902"),
    )

    with pytest.raises(ExternalEvidenceVerificationError, match="subject does not match"):
        _load(installed)


def test_validly_signed_receipt_must_declare_ed25519(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = _install_authority(
        tmp_path,
        monkeypatch,
        receipt=_receipt(algorithm=SignatureAlgorithm.EXTERNAL_TRUSTED_ROOT),
    )

    with pytest.raises(ExternalEvidenceVerificationError, match="does not declare Ed25519"):
        _load(installed)


def test_task_specific_engineering_evidence_is_schema_valid_and_digest_bound() -> None:
    schema = cast(
        dict[str, Any],
        json.loads(
            (ROOT / "docs/migrations/evidence/V3-MIG-009.schema.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    evidence = cast(
        dict[str, Any],
        json.loads(
            (ROOT / "docs/migrations/evidence/V3-MIG-009.json").read_text(
                encoding="utf-8"
            )
        ),
    )

    validator = cast(SchemaValidator, Draft202012Validator(schema))
    validator.validate(evidence)
    unsigned: dict[str, Any] = {
        key: value for key, value in evidence.items() if key != "evidenceDigest"
    }
    canonical = json.dumps(
        unsigned, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    assert evidence["evidenceDigest"] == _digest(canonical)
    assert evidence["authorityClaim"] == "NONE"
    assert evidence["verification"]["cryptoBoundary"] == "REAL_ED25519_EXACT_BYTES"
