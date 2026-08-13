"""Fixed-root request bridge entrypoint intended only for the root broker unit."""

from __future__ import annotations

import os
import pwd
import sys
from pathlib import Path

from .canonical import canonical_json_bytes
from .filesystem import open_trusted_root
from .request_broker import RequestSubmissionError, RootRequestBroker

STATE_ROOT = Path("/var/lib/traincapsule-verifier")
CONTROLLER_OUTBOX = STATE_ROOT / "controller-outbox"
SERVICE_INBOX = STATE_ROOT / "inbox"
JOURNAL_ROOT = STATE_ROOT / "request-journal"
CONTROLLER_USER = "traincapsule-controller"
SERVICE_USER = "traincapsule-verifier"


def main() -> int:
    if os.geteuid() != 0:
        print("root request broker rejected execution", file=sys.stderr)
        return 1
    if len(sys.argv) not in {2, 3} or sys.argv[1] not in {"submit", "process-outbox"}:
        print(
            "usage: traincapsule-verifier-request-broker "
            "submit REQUEST.request.json | process-outbox",
            file=sys.stderr,
        )
        return 2
    if sys.argv[1] == "submit" and len(sys.argv) != 3:
        print("root request broker rejected arguments", file=sys.stderr)
        return 2
    if sys.argv[1] == "process-outbox" and len(sys.argv) != 2:
        print("root request broker rejected arguments", file=sys.stderr)
        return 2
    try:
        controller = pwd.getpwnam(CONTROLLER_USER)
        service = pwd.getpwnam(SERVICE_USER)
        if controller.pw_uid == service.pw_uid:
            raise RequestSubmissionError(
                "controller and issuer service identities must be distinct"
            )
        with (
            open_trusted_root(CONTROLLER_OUTBOX, expected_uid=controller.pw_uid) as outbox,
            open_trusted_root(SERVICE_INBOX, expected_uid=service.pw_uid) as inbox,
            open_trusted_root(JOURNAL_ROOT, expected_uid=0) as journal,
        ):
            broker = RootRequestBroker(
                controller_outbox=outbox,
                service_inbox=inbox,
                journal_root=journal,
                service_uid=service.pw_uid,
                service_gid=service.pw_gid,
            )
            names = (
                [sys.argv[2]]
                if sys.argv[1] == "submit"
                else sorted(
                    name
                    for name in os.listdir(outbox.descriptor)
                    if name.endswith(".request.json")
                )
            )
            results = [broker.submit(name) for name in names]
        payload = {
            "state": "PROCESSED",
            "count": len(results),
            "submissions": [
                result.model_dump(mode="json", by_alias=True) for result in results
            ],
        }
        sys.stdout.buffer.write(canonical_json_bytes(payload))
        return 0
    except (KeyError, OSError, ValueError, RequestSubmissionError):
        print("root request broker rejected submission", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
