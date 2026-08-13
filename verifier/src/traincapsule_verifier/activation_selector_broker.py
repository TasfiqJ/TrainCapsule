"""Root copy-only broker for selector-signed activation envelopes."""

from __future__ import annotations

import os
import pwd
import sys
from collections.abc import Callable
from pathlib import Path

from .canonical import canonical_json_bytes, sha256_digest
from .filesystem import atomic_write_new, open_trusted_root, read_bounded_file
from .models import ActivationSelectionEnvelope
from .public_crypto import SignatureError, load_public_key, verify_model_signature

ROOT = Path("/var/lib/traincapsule-verifier")
CONFIG = Path("/etc/traincapsule-verifier")


def _process_selections(
    names: tuple[str, ...], process: Callable[[str], None]
) -> tuple[int, int]:
    accepted = 0
    rejected = 0
    for name in names:
        try:
            process(name)
        except (OSError, SignatureError, ValueError):
            rejected += 1
            continue
        accepted += 1
    return accepted, rejected


def main() -> int:
    if sys.argv[1:] != ["process-outbox"]:
        print(
            "usage: traincapsule-verifier-activation-selector-broker process-outbox",
            file=sys.stderr,
        )
        return 2
    try:
        if os.geteuid() != 0:
            raise ValueError("activation selector broker requires root")
        selector = pwd.getpwnam("traincapsule-selector")
        service = pwd.getpwnam("traincapsule-verifier")
        public_key = load_public_key((CONFIG / "selector-public-key.pem").read_bytes())
        with (
            open_trusted_root(ROOT / "selector-outbox", expected_uid=selector.pw_uid) as source,
            open_trusted_root(
                ROOT / "activation-requests", expected_uid=selector.pw_uid
            ) as requests,
            open_trusted_root(ROOT / "activation-inbox", expected_uid=service.pw_uid) as target,
        ):
            names = tuple(
                sorted(
                    name
                    for name in os.listdir(source.descriptor)
                    if name.endswith(".activation-request.json")
                )
            )

            def copy_selection(name: str) -> None:
                raw = read_bounded_file(source, name, maximum_bytes=5_000_000)
                envelope = ActivationSelectionEnvelope.model_validate_json(raw, strict=True)
                if raw != canonical_json_bytes(envelope):
                    raise ValueError("activation selector envelope is not canonical")
                verify_model_signature(envelope.observed_main, public_key)
                request = envelope.activation_request
                evidence = f"{request.request_id}.evidence"
                payloads = {
                    request.machine_environment_path: request.machine_environment_digest,
                    request.controller_binary_path: request.controller_binary_digest,
                    request.controller_config_path: request.controller_config_digest,
                }
                for relative, expected in payloads.items():
                    content = read_bounded_file(
                        requests, f"{evidence}/{relative}", maximum_bytes=20_000_000
                    )
                    if sha256_digest(content) != expected:
                        raise ValueError("selector activation evidence digest mismatch")
                    try:
                        atomic_write_new(
                            target,
                            f"{evidence}/{relative}",
                            content,
                            owner_uid=service.pw_uid,
                            owner_gid=service.pw_gid,
                        )
                    except ValueError:
                        if read_bounded_file(target, f"{evidence}/{relative}") != content:
                            raise
                try:
                    atomic_write_new(
                        target,
                        name,
                        raw,
                        owner_uid=service.pw_uid,
                        owner_gid=service.pw_gid,
                    )
                except ValueError:
                    if read_bounded_file(target, name) != raw:
                        raise

            accepted, rejected = _process_selections(names, copy_selection)
        if rejected:
            print(
                f"activation selector broker rejected {rejected} stale or invalid selection(s)",
                file=sys.stderr,
            )
        return 0 if accepted or not names else 1
    except (KeyError, OSError, SignatureError, ValueError):
        print("activation selector broker rejected work", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
