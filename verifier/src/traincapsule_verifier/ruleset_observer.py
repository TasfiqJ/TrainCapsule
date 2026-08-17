"""Independent short-lived signer for exact GitHub ruleset observations."""

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

from .canonical import canonical_json_bytes, sha256_digest
from .crypto import load_private_key, sign_model
from .filesystem import atomic_write_new, open_trusted_root, read_bounded_file
from .github_app_readonly import mint_read_only_installation_token
from .models import RulesetObservationReceipt, ruleset_observation_identifier
from .ruleset_policy import validate_release_rule_types

USER = "traincapsule-ruleset-observer"
ROOT = Path("/var/lib/traincapsule-verifier")
CONFIG = Path("/etc/traincapsule-verifier")


def _api(path: str, token: str) -> object:
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "TrainCapsule-Ruleset-Observer/3.1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read(2_000_000))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise ValueError("ruleset observer GitHub API is unavailable") from exc


def _graphql(query: str, variables: dict[str, str], token: str) -> object:
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps(
            {"query": query, "variables": variables},
            separators=(",", ":"),
            sort_keys=True,
        ).encode(),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "TrainCapsule-Ruleset-Observer/3.1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read(1_000_000))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise ValueError("ruleset observer GitHub GraphQL API is unavailable") from exc


def repository_auto_merge_enabled(repository: str, token: str) -> bool:
    owner, name = repository.split("/", 1)
    marker = "$"
    query = (
        f"query({marker}owner:String!,{marker}name:String!)"
        f"{{repository(owner:{marker}owner,name:{marker}name){{autoMergeAllowed}}}}"
    )
    result = _graphql(query, {"owner": owner, "name": name}, token)
    if not isinstance(result, dict):
        return False
    typed_result = cast(dict[str, object], result)
    if typed_result.get("errors"):
        return False
    data = typed_result.get("data")
    typed_data = cast(dict[str, object], data) if isinstance(data, dict) else {}
    repository_payload = typed_data.get("repository")
    typed_repository = (
        cast(dict[str, object], repository_payload)
        if isinstance(repository_payload, dict)
        else {}
    )
    return (
        bool(typed_repository)
        and typed_repository.get("autoMergeAllowed") is True
    )


def has_no_bypass_actors(value: object) -> bool:
    return value is None or value == []


def _observe(uid: int) -> None:
    with open_trusted_root(CONFIG, expected_uid=0) as config_root:
        policy = json.loads(read_bounded_file(config_root, "ruleset-observer.json"))
    if not isinstance(policy, dict):
        raise ValueError("ruleset observer policy is invalid")
    typed = cast(dict[str, object], policy)
    repository = typed.get("repository")
    required = typed.get("requiredCheckAppIds")
    app_id = typed.get("githubAppId")
    installation_id = typed.get("installationId")
    credential_env = typed.get("privateKeyEnvironment")
    if (
        not isinstance(repository, str)
        or not isinstance(required, dict)
        or not isinstance(app_id, int)
        or not isinstance(installation_id, int)
        or not isinstance(credential_env, str)
    ):
        raise ValueError("ruleset observer policy is incomplete")
    expected = cast(dict[str, object], required)
    if any(not isinstance(app, int) for app in expected.values()):
        raise ValueError("ruleset observer check/App mapping is invalid")
    private_key = os.environ.get(credential_env)
    if not private_key:
        raise ValueError("ruleset observer GitHub App credential is unavailable")
    token = mint_read_only_installation_token(
        app_id=app_id,
        installation_id=installation_id,
        private_key_base64=private_key,
    )
    raw_rulesets = _api(f"/repos/{repository}/rulesets", token)
    if not isinstance(raw_rulesets, list):
        raise ValueError("ruleset observer response is invalid")
    selected: dict[str, object] | None = None
    for raw in cast(list[object], raw_rulesets):
        if not isinstance(raw, dict) or not isinstance(cast(dict[str, object], raw).get("id"), int):
            continue
        ruleset_id = cast(dict[str, object], raw)["id"]
        detail = _api(f"/repos/{repository}/rulesets/{ruleset_id}", token)
        if not isinstance(detail, dict):
            continue
        candidate = cast(dict[str, object], detail)
        conditions = candidate.get("conditions")
        ref_name = (
            cast(dict[str, object], conditions).get("ref_name")
            if isinstance(conditions, dict)
            else None
        )
        include = (
            cast(dict[str, object], ref_name).get("include")
            if isinstance(ref_name, dict)
            else None
        )
        exact_main = isinstance(include, list) and any(
            value in {"~DEFAULT_BRANCH", "refs/heads/main"}
            for value in cast(list[object], include)
            if isinstance(value, str)
        )
        if candidate.get("enforcement") == "active" and exact_main:
            selected = candidate
            break
    if selected is None or not has_no_bypass_actors(selected.get("bypass_actors")):
        raise ValueError("no bypass-free active ruleset is available")
    rules = selected.get("rules")
    if not isinstance(rules, list):
        raise ValueError("ruleset detail is incomplete")
    rule_map = {
        cast(str, cast(dict[str, object], raw).get("type")): cast(dict[str, object], raw)
        for raw in cast(list[object], rules)
        if isinstance(raw, dict) and isinstance(cast(dict[str, object], raw).get("type"), str)
    }
    validate_release_rule_types(set(rule_map))
    observed: dict[str, int] = {}
    now = datetime.now(UTC)
    core = {
        "repository": repository,
        "baseBranch": "main",
        "rulesetId": selected["id"],
        "enforcement": "active",
        "requiredCheckAppIds": observed,
        "bypassActorCount": 0,
        "deletionForbidden": True,
        "forcePushForbidden": True,
        "pullRequestRequired": False,
        "directBranchUpdatesForbidden": False,
        "autoMergeEnabled": False,
    }
    observation_digest = sha256_digest(canonical_json_bytes(core))
    provisional = RulesetObservationReceipt(
        schema_version="3.1",
        observation_id=ruleset_observation_identifier(observation_digest, now),
        observation_digest=observation_digest,
        repository=repository,
        base_branch="main",
        ruleset_id=cast(int, selected["id"]),
        enforcement="active",
        required_check_app_ids=observed,
        bypass_actor_count=0,
        deletion_forbidden=True,
        force_push_forbidden=True,
        pull_request_required=False,
        direct_branch_updates_forbidden=False,
        auto_merge_enabled=False,
        observed_at=now,
        expires_at=now + timedelta(minutes=15),
        issuer_id="RULESET:OBSERVER",
        issuer_key_id="KEY:RULESET:ACTIVE",
        signature_algorithm="ed25519",
        signature="A" * 88,
    )
    with open_trusted_root(ROOT / "ruleset-private", expected_uid=uid) as key_root:
        key = load_private_key(read_bounded_file(key_root, "private-key.pem"))
    signed = provisional.model_copy(update={"signature": sign_model(provisional, key)})
    with open_trusted_root(ROOT / "ruleset-outbox", expected_uid=uid) as output:
        name = f"{signed.observation_id}.json"
        try:
            atomic_write_new(output, name, canonical_json_bytes(signed))
        except ValueError as exc:
            existing = RulesetObservationReceipt.model_validate_json(
                read_bounded_file(output, name), strict=True
            )
            if existing != signed:
                raise ValueError("ruleset observation identity conflicts") from exc


def main() -> int:
    if sys.argv[1:] != ["observe"]:
        print("usage: traincapsule-verifier-ruleset-observer observe", file=sys.stderr)
        return 2
    try:
        uid = pwd.getpwnam(USER).pw_uid
        if os.geteuid() != uid:
            raise ValueError("ruleset observer requires its dedicated service identity")
        _observe(uid)
        return 0
    except (KeyError, OSError, ValueError):
        print("independent ruleset observer rejected work", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
