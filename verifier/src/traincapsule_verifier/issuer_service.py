"""Private service-account issuer runner; never imported by the public client."""

from __future__ import annotations

import os
import pwd
import re
import sys
from pathlib import Path

from pydantic import ValidationError

from .evaluator import IndependentVerifier, VerificationError
from .filesystem import TrustedPathError, open_trusted_root, read_bounded_file, strict_json_loads
from .models import MachinePolicyReceipt, VerificationRequest

SERVICE_USER = "traincapsule-verifier"
CONFIG_ROOT = Path("/etc/traincapsule-verifier")
PUBLIC_STATE_ROOT = Path("/var/lib/traincapsule-verifier")
SERVICE_STATE_ROOT = PUBLIC_STATE_ROOT / "state"
PRIVATE_ROOT = PUBLIC_STATE_ROOT / "private"
ORACLE_ROOT = PUBLIC_STATE_ROOT / "oracle"
INBOX_ROOT = PUBLIC_STATE_ROOT / "inbox"
OUTBOX_ROOT = PUBLIC_STATE_ROOT / "outbox"
REPOSITORY_BOUNDARY_ROOT = PUBLIC_STATE_ROOT / "repository-boundary"
_REQUEST_NAME = re.compile(r"^[A-Z0-9][A-Z0-9._:-]{2,127}\.request\.json$")


def _load_request(name: str, service_uid: int) -> VerificationRequest:
    with open_trusted_root(INBOX_ROOT, expected_uid=service_uid) as inbox:
        raw = read_bounded_file(inbox, name, maximum_bytes=5_000_000)
    strict_json_loads(raw)
    try:
        return VerificationRequest.model_validate_json(raw, strict=True)
    except (ValidationError, ValueError) as exc:
        raise VerificationError("issuer inbox request is invalid") from exc


def _request_names(service_uid: int) -> tuple[str, ...]:
    with open_trusted_root(INBOX_ROOT, expected_uid=service_uid) as inbox:
        names = os.listdir(inbox.descriptor)
    return tuple(sorted(name for name in names if _REQUEST_NAME.fullmatch(name)))


def _issue_one(name: str, service_uid: int) -> None:
    request = _load_request(name, service_uid)
    prefix = name.removesuffix(".request.json")
    if request.request_id != prefix:
        raise VerificationError("issuer inbox filename does not match request identity")
    with IndependentVerifier.from_external_roots(
        repository_root=REPOSITORY_BOUNDARY_ROOT,
        config_root=CONFIG_ROOT,
        state_root=SERVICE_STATE_ROOT,
        private_root=PRIVATE_ROOT,
        receipt_root=OUTBOX_ROOT,
        anchor_root=CONFIG_ROOT,
        oracle_root=ORACLE_ROOT,
        authority_state_root=CONFIG_ROOT,
        config_owner_uid=0,
        verifier_owner_uid=service_uid,
    ) as verifier:
        with open_trusted_root(OUTBOX_ROOT, expected_uid=service_uid) as outbox:
            for existing_name in sorted(os.listdir(outbox.descriptor)):
                if not existing_name.startswith("MPOL:") or not existing_name.endswith(".json"):
                    continue
                try:
                    existing = MachinePolicyReceipt.model_validate_json(
                        read_bounded_file(outbox, existing_name), strict=True
                    )
                    if existing.request_digest != request.request_digest:
                        continue
                    verifier.verify_receipt(existing, request=request)
                    return
                except (ValidationError, ValueError, TrustedPathError):
                    continue
        verifier.issue_receipt(
            request,
            evidence_root=INBOX_ROOT / f"{prefix}.evidence",
            repository_root=REPOSITORY_BOUNDARY_ROOT,
            evidence_owner_uid=service_uid,
        )


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "process-inbox":
        print("usage: traincapsule-verifier-issuer process-inbox", file=sys.stderr)
        return 2
    try:
        service_uid = pwd.getpwnam(SERVICE_USER).pw_uid
        if os.geteuid() != service_uid:
            raise VerificationError("issuer must run as dedicated verifier service account")
        for name in _request_names(service_uid):
            _issue_one(name, service_uid)
        return 0
    except (KeyError, OSError, TrustedPathError, VerificationError):
        print("independent issuer service rejected work", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
