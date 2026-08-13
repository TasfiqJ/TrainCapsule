"""Fixed-root receipt broker entrypoint intended only for a root-owned service unit."""

from __future__ import annotations

import os
import pwd
import sys
from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes
from .filesystem import open_trusted_root
from .public_verifier import PublicVerifier
from .receipt_broker import (
    ReceiptPromotionError,
    ReceiptPromotionResult,
    RootReceiptBroker,
)

CONFIG_ROOT = Path("/etc/traincapsule-verifier")
STATE_ROOT = Path("/var/lib/traincapsule-verifier")
OUTBOX_ROOT = STATE_ROOT / "outbox"
PUBLIC_ROOT = STATE_ROOT / "receipts"
REPOSITORY_BOUNDARY_ROOT = STATE_ROOT / "repository-boundary"
SERVICE_USER = "traincapsule-verifier"


def promotion_payload(
    results: list[ReceiptPromotionResult], *, single: bool
) -> dict[str, Any]:
    serialized = [result.model_dump(mode="json", by_alias=True) for result in results]
    return serialized[0] if single else {"promotions": serialized}


def main() -> int:
    if os.geteuid() != 0:
        print("root receipt broker rejected execution", file=sys.stderr)
        return 1
    if len(sys.argv) not in {2, 3} or sys.argv[1] not in {"promote", "process-outbox"}:
        print(
            "usage: traincapsule-verifier-broker promote RECEIPT.json | process-outbox",
            file=sys.stderr,
        )
        return 2
    try:
        service_uid = pwd.getpwnam(SERVICE_USER).pw_uid
        with (
            PublicVerifier.from_public_roots(
                repository_root=REPOSITORY_BOUNDARY_ROOT,
                config_root=CONFIG_ROOT,
                state_root=CONFIG_ROOT,
                receipt_root=PUBLIC_ROOT,
                expected_owner_uid=0,
            ) as verifier,
            open_trusted_root(OUTBOX_ROOT, expected_uid=service_uid) as outbox,
            open_trusted_root(PUBLIC_ROOT, expected_uid=0) as public,
        ):
            broker = RootReceiptBroker(
                verifier=verifier, outbox_root=outbox, public_root=public
            )
            names = (
                (sys.argv[2],)
                if sys.argv[1] == "promote"
                else tuple(
                    sorted(
                        name
                        for name in os.listdir(outbox.descriptor)
                        if name.endswith(".json") and not name.startswith(".")
                    )
                )
            )
            results = [broker.promote(name) for name in names]
        payload = promotion_payload(results, single=sys.argv[1] == "promote")
        sys.stdout.buffer.write(canonical_json_bytes(payload))
        return 0
    except (KeyError, OSError, ValueError, ReceiptPromotionError):
        print("root receipt broker rejected promotion", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
