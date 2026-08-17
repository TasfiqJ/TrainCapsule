from __future__ import annotations

import json
import os
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from deployment.github_token_refresher import (
    RefreshFailure,
    RefreshPolicy,
    load_policy,
    promote,
    refresh,
)

NOW = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)


def _policy(tmp_path: Path) -> RefreshPolicy:
    private = tmp_path / "private"
    outbox = tmp_path / "outbox"
    target = tmp_path / "target"
    private.mkdir(mode=0o700)
    outbox.mkdir(mode=0o700)
    target.mkdir(mode=0o700)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = private / "key.pem"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    return RefreshPolicy.model_construct(
        schema_version="3.1",
        github_app_id=123,
        installation_id=456,
        repository="test-owner/isolated-canary",
        audience="https://api.github.com",
        permissions={
            "actions": "write",
            "checks": "read",
            "contents": "read",
        },
        private_key_path=str(key_path),
        outbox_token_path=str(outbox / "token"),
        outbox_metadata_path=str(outbox / "metadata.json"),
        target_token_path=str(target / "token"),
        target_metadata_path=str(target / "metadata.json"),
        refresh_before_seconds=600,
    )


def _identity(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())

    def lookup(_name: str) -> SimpleNamespace:
        return entry

    monkeypatch.setattr(
        "deployment.github_token_refresher.pwd.getpwnam",
        lookup,
    )


def test_policy_loader_accepts_the_repository_canonical_json_line(tmp_path: Path) -> None:
    policy = RefreshPolicy(
        github_app_id=123,
        installation_id=456,
        repository="test-owner/isolated-canary",
        audience="https://api.github.com",
        permissions={
            "actions": "write",
            "checks": "read",
            "contents": "read",
        },
        private_key_path="/var/lib/traincapsule-github-token/github-app-private-key.pem",
        outbox_token_path="/var/lib/traincapsule-github-token/outbox/token",
        outbox_metadata_path=(
            "/var/lib/traincapsule-github-token/outbox/token-metadata.json"
        ),
        target_token_path=(
            "/var/lib/traincapsule-canary-secrets/github-app-installation-token"
        ),
        target_metadata_path=(
            "/var/lib/traincapsule-canary-secrets/github-app-installation-token.json"
        ),
        refresh_before_seconds=600,
    )
    path = tmp_path / "policy.json"
    path.write_bytes(
        (
            json.dumps(
                policy.model_dump(mode="json", by_alias=True),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
    )
    path.chmod(0o444)
    assert load_policy(path, expected_owner_uid=os.getuid()) == policy


def test_scoped_refresh_rotation_and_promotion_never_log_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy = _policy(tmp_path)
    _identity(monkeypatch)
    token = "ghs_" + "a" * 40
    observed: dict[str, object] = {}

    def transport(request: object, timeout: int) -> tuple[int, bytes]:
        observed["request"] = request
        observed["timeout"] = timeout
        payload = {
            "token": token,
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        }
        return 201, json.dumps(payload).encode()

    metadata = refresh(policy, now=NOW, transport=transport)
    request = observed["request"]
    assert isinstance(request, urllib.request.Request)
    assert request.full_url == (
        "https://api.github.com/app/installations/456/access_tokens"
    )
    request_payload = json.loads(cast(bytes, request.data))
    assert request_payload == {
        "permissions": {
            "actions": "write",
            "checks": "read",
            "contents": "read",
        },
        "repositories": ["isolated-canary"],
    }
    assert metadata.expires_at == NOW + timedelta(hours=1)
    monkeypatch.setattr(
        "deployment.github_token_refresher.os.geteuid", lambda: 0
    )
    promoted = promote(policy, now=NOW)
    assert promoted == metadata
    assert Path(policy.target_token_path).read_text() == token
    assert Path(policy.target_token_path).stat().st_mode & 0o777 == 0o600
    assert token not in capsys.readouterr().out


def test_refresher_rejects_unsafe_key_expiry_and_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = _policy(tmp_path)
    _identity(monkeypatch)
    Path(policy.private_key_path).chmod(0o644)
    with pytest.raises(RefreshFailure, match="not trusted"):
        refresh(policy, now=NOW, transport=lambda _request, _timeout: (500, b"{}"))
    with pytest.raises(ValueError, match="permissions exceed"):
        RefreshPolicy.model_validate(
            {
                "schemaVersion": "3.1",
                "githubAppId": 123,
                "installationId": 456,
                "repository": "test-owner/isolated-canary",
                "audience": "https://api.github.com",
                "permissions": {"contents": "write"},
                "privateKeyPath": (
                    "/var/lib/traincapsule-github-token/github-app-private-key.pem"
                ),
                "outboxTokenPath": "/var/lib/traincapsule-github-token/outbox/token",
                "outboxMetadataPath": (
                    "/var/lib/traincapsule-github-token/outbox/token-metadata.json"
                ),
                "targetTokenPath": (
                    "/var/lib/traincapsule-canary-secrets/github-app-installation-token"
                ),
                "targetMetadataPath": (
                    "/var/lib/traincapsule-canary-secrets/"
                    "github-app-installation-token.json"
                ),
                "refreshBeforeSeconds": 600,
            }
        )
    with pytest.raises(ValueError, match="permissions exceed"):
        RefreshPolicy.model_validate(
            {
                "schemaVersion": "3.1",
                "githubAppId": 123,
                "installationId": 456,
                "repository": "test-owner/isolated-canary",
                "audience": "https://api.github.com",
                "permissions": {"actions": "write", "contents": "read"},
                "privateKeyPath": (
                    "/var/lib/traincapsule-github-token/github-app-private-key.pem"
                ),
                "outboxTokenPath": "/var/lib/traincapsule-github-token/outbox/token",
                "outboxMetadataPath": (
                    "/var/lib/traincapsule-github-token/outbox/token-metadata.json"
                ),
                "targetTokenPath": (
                    "/var/lib/traincapsule-canary-secrets/github-app-installation-token"
                ),
                "targetMetadataPath": (
                    "/var/lib/traincapsule-canary-secrets/"
                    "github-app-installation-token.json"
                ),
                "refreshBeforeSeconds": 600,
            }
        )


def test_expired_response_and_interrupted_promotion_preserve_old_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = _policy(tmp_path)
    _identity(monkeypatch)
    stale = json.dumps(
        {"token": "ghs_" + "b" * 40, "expires_at": (NOW + timedelta(minutes=5)).isoformat()}
    ).encode()
    with pytest.raises(RefreshFailure, match="already stale"):
        refresh(policy, now=NOW, transport=lambda _request, _timeout: (201, stale))

    fresh = json.dumps(
        {"token": "ghs_" + "c" * 40, "expires_at": (NOW + timedelta(hours=1)).isoformat()}
    ).encode()
    refresh(policy, now=NOW, transport=lambda _request, _timeout: (201, fresh))
    outbox_token = Path(policy.outbox_token_path)
    outbox_token.write_text("ghs_" + "d" * 40)
    outbox_token.chmod(0o600)
    monkeypatch.setattr(
        "deployment.github_token_refresher.os.geteuid", lambda: 0
    )
    with pytest.raises(RefreshFailure, match="promotion binding"):
        promote(policy, now=NOW)
    monkeypatch.setattr(
        "deployment.github_token_refresher.os.geteuid", lambda: os.getuid()
    )
    refresh(policy, now=NOW, transport=lambda _request, _timeout: (201, fresh))
    target = Path(policy.target_token_path)
    target.write_text("ghs_" + "o" * 40)
    target.chmod(0o600)
    monkeypatch.setattr(
        "deployment.github_token_refresher.os.geteuid", lambda: 0
    )
    real_replace = os.replace

    def fail_target(source: str | Path, destination: str | Path) -> None:
        if Path(destination) == target:
            raise OSError("simulated crash before atomic replacement")
        real_replace(source, destination)

    monkeypatch.setattr(
        "deployment.github_token_refresher.os.replace", fail_target
    )
    with pytest.raises(OSError, match="simulated crash"):
        promote(policy, now=NOW)
    assert target.read_text() == "ghs_" + "o" * 40
