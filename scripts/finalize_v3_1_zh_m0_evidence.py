#!/usr/bin/env python3
"""Validate independent V3.1 M0 prerequisites without ever self-attesting."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tcfactory.v3.external_evidence import (
    ExternalEvidenceVerificationError,
    assert_privileged_read_only,
    verify_detached_ed25519_signature,
)

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_CHECKS = frozenset(
    {
        "Factory quality",
        "Packaging install",
        "Product CI",
        "Security",
        "Docs and schemas",
        "Source-of-truth integrity",
        "Source freshness",
    }
)


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"independent receipt is unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"independent receipt is not an object: {path.name}")
    return cast(dict[str, Any], value)


def _common(receipt: dict[str, Any], *, kind: str, now: datetime) -> None:
    required = {
        "schemaVersion",
        "receiptType",
        "issuer",
        "candidateSha",
        "activeGenerationDigest",
        "sourceManifestDigest",
        "issuedAt",
        "expiresAt",
        "nonce",
        "revocationEpoch",
        "signature",
    }
    if not required.issubset(receipt):
        raise ValueError(f"{kind} receipt lacks mandatory signed fields")
    if receipt["schemaVersion"] != "3.1" or receipt["receiptType"] != kind:
        raise ValueError(f"{kind} receipt schema or type mismatch")
    if receipt["issuer"] != "INDEPENDENT_MACHINE_VERIFIER":
        raise ValueError(f"{kind} receipt issuer is not independent")
    for field in ("candidateSha",):
        value = receipt[field]
        if not isinstance(value, str) or len(value) != 40:
            raise ValueError(f"{kind} receipt {field} is malformed")
    for field in ("activeGenerationDigest", "sourceManifestDigest"):
        value = receipt[field]
        if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
            raise ValueError(f"{kind} receipt {field} is malformed")
    issued = datetime.fromisoformat(str(receipt["issuedAt"]).replace("Z", "+00:00"))
    expires = datetime.fromisoformat(str(receipt["expiresAt"]).replace("Z", "+00:00"))
    if issued > now or expires <= now or expires <= issued:
        raise ValueError(f"{kind} receipt is expired or not yet valid")
    if not isinstance(receipt["nonce"], str) or len(receipt["nonce"]) < 16:
        raise ValueError(f"{kind} receipt nonce is malformed")
    if not isinstance(receipt["revocationEpoch"], int) or receipt["revocationEpoch"] < 0:
        raise ValueError(f"{kind} receipt revocation epoch is malformed")
    signature = receipt["signature"]
    if not isinstance(signature, dict):
        raise ValueError(f"{kind} receipt lacks an Ed25519 signature declaration")
    typed_signature = cast(dict[str, object], signature)
    if typed_signature.get("algorithm") != "ed25519":
        raise ValueError(f"{kind} receipt lacks an Ed25519 signature declaration")


def _publication(receipt: dict[str, Any], *, now: datetime) -> None:
    _common(receipt, kind="V3_1_PR_PUBLICATION", now=now)
    pull_request_url = receipt.get("pullRequestUrl")
    if not isinstance(pull_request_url, str) or not pull_request_url.startswith(
        "https://github.com/"
    ):
        raise ValueError("publication receipt lacks a GitHub pull request URL")
    if receipt.get("pullRequestHeadSha") != receipt["candidateSha"]:
        raise ValueError("publication receipt PR head is not the candidate SHA")
    if receipt.get("mergedMainSha") != receipt["candidateSha"]:
        raise ValueError("publication receipt merge is not exact-SHA")
    raw_checks = receipt.get("requiredChecks")
    if not isinstance(raw_checks, dict):
        raise ValueError("publication receipt required-check set is incomplete")
    checks = cast(dict[str, object], raw_checks)
    if sorted(checks) != sorted(REQUIRED_CHECKS):
        raise ValueError("publication receipt required-check set is incomplete")
    if any(value != "success" for value in checks.values()):
        raise ValueError("publication receipt contains a non-success required check")


def main() -> int:
    trusted_value = os.getenv("TCF_V31_VERIFIER_ROOT", "").strip()
    if not trusted_value:
        print("BLOCKED_POLICY: V3.1 M0 independent receipts are missing", file=sys.stderr)
        return 2
    trusted_root = Path(trusted_value).expanduser().resolve()
    key_value = os.getenv("TCF_V31_VERIFIER_PUBLIC_KEY", "").strip()
    if not key_value:
        print("BLOCKED_POLICY: independent verifier public key is missing", file=sys.stderr)
        return 2
    public_key = Path(key_value).expanduser().resolve()
    try:
        trusted_root.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        print(
            "BLOCKED_POLICY: independent receipt root must be outside the repository",
            file=sys.stderr,
        )
        return 2
    required = {
        "source": trusted_root / "source-migration-receipt.json",
        "mechanical": trusted_root / "V3-MIG-019-mechanical.json",
        "standard": trusted_root / "V3-MIG-019-standard.json",
        "rehearsal": trusted_root / "V3-MIG-020-rehearsal.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        print(
            "BLOCKED_POLICY: V3.1 M0 independent receipts are missing: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2
    try:
        assert_privileged_read_only(trusted_root)
        assert_privileged_read_only(public_key)
        for path in required.values():
            signature = path.with_suffix(path.suffix + ".sig")
            if not signature.is_file():
                raise ValueError(f"detached signature is missing: {path.name}")
            assert_privileged_read_only(path)
            assert_privileged_read_only(signature)
            verify_detached_ed25519_signature(
                receipt=path,
                signature=signature,
                public_key=public_key,
            )
        now = datetime.now(UTC)
        source = _object(required["source"])
        _common(source, kind="V3_1_SOURCE_MIGRATION_AUTHORIZATION", now=now)
        for name in ("mechanical", "standard"):
            _publication(_object(required[name]), now=now)
        rehearsal = _object(required["rehearsal"])
        _common(rehearsal, kind="V3_1_RECOVERY_REHEARSAL", now=now)
        if rehearsal.get("outcome") != "PASSED" or rehearsal.get("restoredExactSha") is not True:
            raise ValueError("recovery rehearsal receipt does not prove exact-SHA restoration")
    except (ExternalEvidenceVerificationError, KeyError, TypeError, ValueError) as exc:
        print(f"BLOCKED_POLICY: {exc}", file=sys.stderr)
        return 2
    print(
        "BLOCKED_POLICY: prerequisites verify; Phase 1 finalizer never writes FINAL",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
