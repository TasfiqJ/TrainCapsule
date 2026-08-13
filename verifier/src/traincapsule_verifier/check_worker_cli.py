"""Credential-gated service entrypoint for Machine-policy GitHub checks."""

from __future__ import annotations

import os
import pwd
import sys
from pathlib import Path

from .canonical import model_digest
from .check_publisher import CheckEvent, CheckPublisherPolicy, CheckPublisherWorker
from .filesystem import open_trusted_root
from .github_app_backend import GitHubAppHTTPBackend
from .models import MachinePolicyReceipt
from .public_verifier import PublicVerifier

ROOT = Path("/var/lib/traincapsule-verifier")
CONFIG = Path("/etc/traincapsule-verifier")
POLICY_PATH = CONFIG / "check-publisher.json"
PRIVATE_KEY = ROOT / "github-app/private-key.pem"
SERVICE_USER = "traincapsule-verifier"


def main() -> int:
    if sys.argv[1:] != ["process-receipts"]:
        print("usage: traincapsule-verifier-check-worker process-receipts", file=sys.stderr)
        return 2
    try:
        service_uid = pwd.getpwnam(SERVICE_USER).pw_uid
        if os.geteuid() != service_uid:
            raise ValueError("check worker requires verifier service identity")
        policy = CheckPublisherPolicy.model_validate_json(POLICY_PATH.read_bytes(), strict=True)
        events: list[CheckEvent] = []
        for path in sorted((ROOT / "receipts").glob("MPOL:*.json")):
            receipt = MachinePolicyReceipt.model_validate_json(path.read_bytes(), strict=True)
            events.append(
                CheckEvent(
                    schema_version="3.1",
                    event_id=f"CHECK:{receipt.receipt_id}",
                    repository=policy.repository,
                    github_app_id=policy.github_app_id,
                    installation_id=policy.installation_id,
                    candidate_sha=receipt.candidate_sha,
                    candidate_tree_sha=receipt.candidate_tree_sha,
                    base_sha=receipt.base_sha,
                    work_item_id=receipt.work_item_id,
                    candidate_manifest_digest=receipt.candidate_manifest_digest,
                    receipt_id=receipt.receipt_id,
                    receipt_digest=model_digest(receipt),
                )
            )
        backend = GitHubAppHTTPBackend(policy=policy, private_key_path=PRIVATE_KEY, events=events)
        with (
            PublicVerifier.from_public_roots(
                repository_root=ROOT / "repository-boundary",
                config_root=CONFIG,
                state_root=CONFIG,
                receipt_root=ROOT / "receipts",
                expected_owner_uid=0,
            ) as verifier,
            open_trusted_root(ROOT / "check-journal", expected_uid=service_uid) as journal,
        ):
            results = CheckPublisherWorker(
                verifier=verifier, policy=policy, journal_root=journal, backend=backend
            ).run_once(limit=100)
        if any(result.state == "WAITING_EXTERNAL_CHANNEL" for result in results):
            return 75
        return 0
    except (KeyError, OSError, ValueError):
        print("GitHub App check worker rejected execution", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
