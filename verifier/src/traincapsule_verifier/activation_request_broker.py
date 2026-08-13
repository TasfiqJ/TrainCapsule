"""Root copy-only broker from controller activation outbox to selector intake."""

from __future__ import annotations

import os
import pwd
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

from .canonical import canonical_json_bytes, sha256_digest
from .filesystem import TrustedRoot, atomic_write_new, open_trusted_root, read_bounded_file
from .models import ActivationRequest

ROOT = Path("/var/lib/traincapsule-verifier")
CONFIG = Path("/etc/traincapsule-verifier")


def _process_requests(
    names: tuple[str, ...], process: Callable[[str], None]
) -> tuple[int, int]:
    accepted = 0
    rejected = 0
    for name in names:
        try:
            process(name)
        except (OSError, ValueError):
            rejected += 1
            continue
        accepted += 1
    return accepted, rejected


def _copy_request(
    name: str,
    *,
    source: TrustedRoot,
    target: TrustedRoot,
    selector: pwd.struct_passwd,
) -> None:
    raw = read_bounded_file(source, name, maximum_bytes=5_000_000)
    request = ActivationRequest.model_validate_json(raw, strict=True)
    if name != f"{request.request_id}.activation-request.json":
        raise ValueError("activation request filename/identity mismatch")
    if raw != canonical_json_bytes(request):
        raise ValueError("activation request is not canonical")
    evidence = f"{request.request_id}.evidence"
    payloads = {
        request.machine_environment_path: request.machine_environment_digest,
        request.controller_binary_path: request.controller_binary_digest,
        request.controller_config_path: request.controller_config_digest,
    }
    for relative, expected in payloads.items():
        content = read_bounded_file(
            source, f"{evidence}/{relative}", maximum_bytes=20_000_000
        )
        if sha256_digest(content) != expected:
            raise ValueError("activation request evidence digest mismatch")
        try:
            atomic_write_new(
                target,
                f"{evidence}/{relative}",
                content,
                owner_uid=selector.pw_uid,
                owner_gid=selector.pw_gid,
            )
        except ValueError:
            if read_bounded_file(target, f"{evidence}/{relative}") != content:
                raise
    try:
        atomic_write_new(
            target,
            name,
            raw,
            owner_uid=selector.pw_uid,
            owner_gid=selector.pw_gid,
        )
    except ValueError:
        if read_bounded_file(target, name) != raw:
            raise


def main() -> int:
    if sys.argv[1:] != ["process-outbox"]:
        print(
            "usage: traincapsule-verifier-activation-request-broker process-outbox",
            file=sys.stderr,
        )
        return 2
    try:
        if os.geteuid() != 0:
            raise ValueError("activation request broker requires root")
        with open_trusted_root(CONFIG, expected_uid=0) as config:
            import json

            policy: object = json.loads(
                read_bounded_file(config, "controller-principal.json")
            )
        if not isinstance(policy, dict) or not isinstance(
            cast(dict[str, object], policy).get("principal"), str
        ):
            raise ValueError("controller principal policy is invalid")
        controller = pwd.getpwnam(cast(str, cast(dict[str, object], policy)["principal"]))
        selector = pwd.getpwnam("traincapsule-selector")
        with (
            open_trusted_root(
                ROOT / "activation-controller-outbox", expected_uid=controller.pw_uid
            ) as source,
            open_trusted_root(
                ROOT / "activation-requests", expected_uid=selector.pw_uid
            ) as target,
        ):
            names = tuple(
                sorted(
                    name
                    for name in os.listdir(source.descriptor)
                    if name.endswith(".activation-request.json")
                )
            )
            accepted, rejected = _process_requests(
                names,
                lambda name: _copy_request(
                    name,
                    source=source,
                    target=target,
                    selector=selector,
                ),
            )
        if rejected:
            print(
                f"activation request broker rejected {rejected} request(s)",
                file=sys.stderr,
            )
        return 0 if accepted or not names else 1
    except (KeyError, OSError, ValueError):
        print("activation request broker rejected work", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
