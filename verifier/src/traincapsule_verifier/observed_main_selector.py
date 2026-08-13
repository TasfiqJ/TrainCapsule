"""Selector-only exact-main observer and activation-envelope producer."""

from __future__ import annotations

import json
import os
import pwd
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from .canonical import canonical_json_bytes, model_digest, sha256_digest
from .crypto import load_private_key, sign_model
from .filesystem import atomic_write_new, open_trusted_root, read_bounded_file
from .github_app_readonly import mint_read_only_installation_token
from .models import (
    ActivationRequest,
    ActivationSelectionEnvelope,
    ObservedMainReceipt,
    RulesetObservationReceipt,
)
from .public_crypto import load_public_key, verify_model_signature

SELECTOR_USER = "traincapsule-selector"
ROOT = Path("/var/lib/traincapsule-verifier")
CONFIG = Path("/etc/traincapsule-verifier")
REQUEST_ROOT = ROOT / "activation-requests"
SELECTOR_OUTBOX = ROOT / "selector-outbox"
SELECTOR_KEY = ROOT / "selector-private/private-key.pem"
RULESET_RECEIPT = ROOT / "ruleset/current.json"
RULESET_PUBLIC_KEY = CONFIG / "ruleset-public-key.pem"
SELECTOR_POLICY = CONFIG / "activation-selector.json"


def _github_json(path: str, token: str) -> object:
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "TrainCapsule-Activation-Selector/3.1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read(2_000_000))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise ValueError("selector GitHub observation is unavailable") from exc


def verified_check_digests(
    check_runs: list[object], required_checks: dict[str, int]
) -> dict[str, str]:
    observed: dict[str, str] = {}
    for raw in check_runs:
        if not isinstance(raw, dict):
            continue
        item = cast(dict[str, object], raw)
        app = item.get("app")
        app_observed = cast(dict[str, object], app).get("id") if isinstance(app, dict) else None
        name = item.get("name")
        if (
            isinstance(name, str)
            and item.get("conclusion") == "success"
            and app_observed == required_checks.get(name)
            and isinstance(item.get("id"), int)
        ):
            observed[name] = sha256_digest(canonical_json_bytes(item))
    if set(observed) != set(required_checks):
        raise ValueError("selector required checks are missing or spoofed")
    return observed


def _select(request_raw: bytes, *, selector_uid: int) -> None:
    with open_trusted_root(CONFIG, expected_uid=0) as config_root:
        policy_raw = read_bounded_file(config_root, SELECTOR_POLICY.name)
        ruleset_public_key_raw = read_bounded_file(config_root, RULESET_PUBLIC_KEY.name)
    policy = json.loads(policy_raw)
    if not isinstance(policy, dict):
        raise ValueError("activation selector policy is invalid")
    typed_policy = cast(dict[str, object], policy)
    repository = typed_policy.get("repository")
    required_check_app_ids = typed_policy.get("requiredCheckAppIds")
    app_id = typed_policy.get("githubAppId")
    installation_id = typed_policy.get("installationId")
    credential_env = typed_policy.get("privateKeyEnvironment")
    if (
        not isinstance(repository, str)
        or not isinstance(required_check_app_ids, dict)
        or not isinstance(app_id, int)
        or not isinstance(installation_id, int)
        or not isinstance(credential_env, str)
    ):
        raise ValueError("activation selector policy is incomplete")
    private_key = os.environ.get(credential_env)
    if not private_key:
        raise ValueError("activation selector GitHub App credential is unavailable")
    token = mint_read_only_installation_token(
        app_id=app_id,
        installation_id=installation_id,
        private_key_base64=private_key,
    )
    required_checks_raw = cast(dict[str, object], required_check_app_ids)
    if not required_checks_raw or any(
        not isinstance(app_id, int) for app_id in required_checks_raw.values()
    ):
        raise ValueError("activation selector required check/App mapping is invalid")
    required_checks = {
        name: cast(int, app_id) for name, app_id in required_checks_raw.items()
    }
    request = ActivationRequest.model_validate_json(request_raw, strict=True)
    branch: object = _github_json(f"/repos/{repository}/branches/main", token)
    if not isinstance(branch, dict):
        raise ValueError("selector main observation is invalid")
    branch_payload = cast(dict[str, object], branch)
    commit = branch_payload.get("commit")
    if not isinstance(commit, dict):
        raise ValueError("selector main commit is unavailable")
    commit_sha = cast(dict[str, object], commit).get("sha")
    if commit_sha != request.verified_main_sha:
        raise ValueError("selector observed main does not match activation request")
    checks: object = _github_json(
        f"/repos/{repository}/commits/{request.verified_main_sha}/check-runs", token
    )
    if not isinstance(checks, dict):
        raise ValueError("selector required-check observation is invalid")
    typed_checks = cast(dict[str, object], checks)
    if not isinstance(typed_checks.get("check_runs"), list):
        raise ValueError("selector required-check observation is invalid")
    observed = verified_check_digests(
        cast(list[object], typed_checks["check_runs"]), required_checks
    )
    with open_trusted_root(ROOT / "ruleset", expected_uid=0) as ruleset_root:
        ruleset_raw = read_bounded_file(ruleset_root, RULESET_RECEIPT.name)
    ruleset = RulesetObservationReceipt.model_validate_json(ruleset_raw, strict=True)
    verify_model_signature(ruleset, load_public_key(ruleset_public_key_raw))
    now = datetime.now(UTC)
    if (
        ruleset.repository != repository
        or ruleset.observed_at > now
        or ruleset.expires_at <= now
        or ruleset.required_check_app_ids != required_checks
    ):
        raise ValueError("selector ruleset observation is invalid or stale")
    commit_detail: object = _github_json(
        f"/repos/{repository}/git/commits/{request.verified_main_sha}", token
    )
    if not isinstance(commit_detail, dict):
        raise ValueError("selector main tree observation is invalid")
    tree = cast(dict[str, object], commit_detail).get("tree")
    tree_sha = cast(dict[str, object], tree).get("sha") if isinstance(tree, dict) else None
    if not isinstance(tree_sha, str):
        raise ValueError("selector main tree SHA is unavailable")
    machine_policy_app_id = required_checks.get("TrainCapsule / Machine policy")
    if not isinstance(machine_policy_app_id, int):
        raise ValueError("selector Machine-policy App ID is unavailable")
    provisional = ObservedMainReceipt(
        schema_version="3.1",
        observation_id=f"OBS:{request.request_id}",
        repository=repository,
        verified_main_sha=request.verified_main_sha,
        verified_main_tree_sha=tree_sha,
        source_generation_id=request.source_generation_id,
        source_generation_digest=request.source_generation_digest,
        ruleset_observation_digest=model_digest(ruleset),
        required_check_digests=observed,
        github_app_id=machine_policy_app_id,
        observed_at=now,
        expires_at=min(request.machine_policy_receipt.expires_at, now + timedelta(minutes=15)),
        issuer_id="SELECTOR:EXACT-MAIN",
        issuer_key_id="KEY:SELECTOR:ACTIVE",
        signature_algorithm="ed25519",
        signature="A" * 88,
    )
    with open_trusted_root(SELECTOR_KEY.parent, expected_uid=selector_uid) as key_root:
        private_key = load_private_key(read_bounded_file(key_root, SELECTOR_KEY.name))
    signed = provisional.model_copy(
        update={"signature": sign_model(provisional, private_key)}
    )
    envelope = ActivationSelectionEnvelope(
        schema_version="3.1", activation_request=request, observed_main=signed
    )
    with open_trusted_root(SELECTOR_OUTBOX, expected_uid=selector_uid) as inbox:
        atomic_write_new(
            inbox,
            f"{request.request_id}.activation-request.json",
            canonical_json_bytes(envelope),
        )


def main() -> int:
    if sys.argv[1:] != ["process-requests"]:
        print(
            "usage: traincapsule-verifier-observed-main-selector process-requests",
            file=sys.stderr,
        )
        return 2
    try:
        selector_uid = pwd.getpwnam(SELECTOR_USER).pw_uid
        if os.geteuid() != selector_uid:
            raise ValueError("selector requires its dedicated service identity")
        with open_trusted_root(REQUEST_ROOT, expected_uid=selector_uid) as root:
            names = sorted(name for name in os.listdir(root.descriptor) if name.endswith(".json"))
            requests = [read_bounded_file(root, name, maximum_bytes=5_000_000) for name in names]
        selected = 0
        rejected = 0
        for request_raw in requests:
            try:
                _select(request_raw, selector_uid=selector_uid)
                selected += 1
            except (KeyError, OSError, ValueError):
                rejected += 1
        if rejected:
            print(
                "independent observed-main selector rejected "
                f"{rejected} stale or invalid request(s)",
                file=sys.stderr,
            )
        return 0 if selected else 1
    except (KeyError, OSError, ValueError):
        print("independent observed-main selector rejected work", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
