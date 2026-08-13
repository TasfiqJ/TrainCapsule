"""Independent activation issuer; consumes only selector-signed exact-main evidence."""

from __future__ import annotations

import os
import pwd
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from .canonical import canonical_json_bytes
from .crypto import SignatureError, load_public_key, verify_model_signature
from .evaluator import IndependentVerifier, VerificationError
from .filesystem import TrustedPathError, open_trusted_root, read_bounded_file, strict_json_loads
from .models import ActivationSelectionEnvelope

SERVICE_USER = "traincapsule-verifier"
CONFIG_ROOT = Path("/etc/traincapsule-verifier")
STATE_ROOT = Path("/var/lib/traincapsule-verifier")
ACTIVATION_INBOX = STATE_ROOT / "activation-inbox"
ACTIVATION_OUTBOX = STATE_ROOT / "outbox"
REPOSITORY_BOUNDARY_ROOT = STATE_ROOT / "repository-boundary"
SELECTOR_PUBLIC_KEY = CONFIG_ROOT / "selector-public-key.pem"
_NAME = re.compile(r"^[A-Z0-9][A-Z0-9._:-]{2,127}\.activation-request\.json$")


def _process_inbox(
    names: tuple[str, ...], process: Callable[[str], None]
) -> tuple[int, int]:
    accepted = 0
    rejected = 0
    for name in names:
        try:
            process(name)
        except (
            OSError,
            SignatureError,
            TrustedPathError,
            ValidationError,
            ValueError,
            VerificationError,
        ):
            rejected += 1
            continue
        accepted += 1
    return accepted, rejected


def _process(name: str, service_uid: int) -> None:
    with open_trusted_root(ACTIVATION_INBOX, expected_uid=service_uid) as inbox:
        raw = read_bounded_file(inbox, name, maximum_bytes=5_000_000)
    strict_json_loads(raw)
    envelope = ActivationSelectionEnvelope.model_validate_json(raw, strict=True)
    if raw != canonical_json_bytes(envelope):
        raise VerificationError("activation selection envelope is not canonical")
    request = envelope.activation_request
    observation = envelope.observed_main
    if name != f"{request.request_id}.activation-request.json":
        raise VerificationError("activation request filename/identity mismatch")
    now = datetime.now(UTC)
    if observation.observed_at > now or observation.expires_at <= now:
        raise VerificationError("observed-main selector evidence is stale")
    if (
        observation.verified_main_sha != request.verified_main_sha
        or observation.source_generation_id != request.source_generation_id
        or observation.source_generation_digest != request.source_generation_digest
        or request.machine_policy_receipt.candidate_sha != request.verified_main_sha
    ):
        raise VerificationError("activation selector/request exact identity mismatch")
    key = load_public_key(SELECTOR_PUBLIC_KEY.read_bytes())
    verify_model_signature(observation, key)
    evidence_root = ACTIVATION_INBOX / f"{request.request_id}.evidence"
    with IndependentVerifier.from_external_roots(
        repository_root=REPOSITORY_BOUNDARY_ROOT,
        config_root=CONFIG_ROOT,
        state_root=STATE_ROOT / "state",
        private_root=STATE_ROOT / "private",
        receipt_root=ACTIVATION_OUTBOX,
        anchor_root=CONFIG_ROOT,
        oracle_root=STATE_ROOT / "oracle",
        authority_state_root=CONFIG_ROOT,
        config_owner_uid=0,
        verifier_owner_uid=service_uid,
    ) as verifier:
        verifier.issue_activation(
            request,
            observed_main_sha=observation.verified_main_sha,
            activation_root=evidence_root,
            repository_root=REPOSITORY_BOUNDARY_ROOT,
            activation_owner_uid=service_uid,
            now=now,
        )


def main() -> int:
    if sys.argv[1:] != ["process-inbox"]:
        print("usage: traincapsule-verifier-activation-issuer process-inbox", file=sys.stderr)
        return 2
    try:
        service_uid = pwd.getpwnam(SERVICE_USER).pw_uid
        if os.geteuid() != service_uid:
            raise VerificationError("activation issuer requires the verifier service identity")
        with open_trusted_root(ACTIVATION_INBOX, expected_uid=service_uid) as inbox:
            names = tuple(
                sorted(name for name in os.listdir(inbox.descriptor) if _NAME.fullmatch(name))
            )
        accepted, rejected = _process_inbox(
            names, lambda name: _process(name, service_uid)
        )
        if rejected:
            print(
                f"independent activation issuer rejected {rejected} stale or invalid request(s)",
                file=sys.stderr,
            )
        return 0 if accepted or not names else 1
    except (
        KeyError,
        OSError,
        SignatureError,
        TrustedPathError,
        ValidationError,
        ValueError,
        VerificationError,
    ):
        print("independent activation issuer rejected work", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
