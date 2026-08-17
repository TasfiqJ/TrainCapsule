"""Deployment-side GitHub App installation-token refresher for the live canary.

The unprivileged refresher alone reads the App private key and writes a private
outbox.  A separate root invocation promotes a validated, unexpired token to the
controller-owned target.  Token bytes are never printed or placed in metadata.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pwd
import stat
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar, Literal, cast

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pydantic import BaseModel, ConfigDict, Field, model_validator

POLICY_PATH = Path("/etc/traincapsule-canary-runner/github-token-refresher.json")
REFRESHER_USER = "traincapsule-github-token"
CONTROLLER_USER = "traincapsule-controller"


class RefreshFailure(RuntimeError):
    """A fail-closed policy, API, token, or promotion failure."""


class _Strict(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        alias_generator=lambda name: "".join(
            [name.split("_")[0], *(part.title() for part in name.split("_")[1:])]
        ),
        populate_by_name=True,
        extra="forbid",
        strict=True,
    )


class RefreshPolicy(_Strict):
    schema_version: Literal["3.1"] = "3.1"
    github_app_id: int = Field(gt=0)
    installation_id: int = Field(gt=0)
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    audience: Literal["https://api.github.com"]
    permissions: dict[str, Literal["read", "write"]]
    private_key_path: Literal[
        "/var/lib/traincapsule-github-token/github-app-private-key.pem"
    ]
    outbox_token_path: Literal["/var/lib/traincapsule-github-token/outbox/token"]
    outbox_metadata_path: Literal[
        "/var/lib/traincapsule-github-token/outbox/token-metadata.json"
    ]
    target_token_path: Literal[
        "/var/lib/traincapsule-canary-secrets/github-app-installation-token"
    ]
    target_metadata_path: Literal[
        "/var/lib/traincapsule-canary-secrets/github-app-installation-token.json"
    ]
    refresh_before_seconds: int = Field(ge=300, le=1800)

    @model_validator(mode="after")
    def exact_scope(self) -> RefreshPolicy:
        if self.permissions != {
            "actions": "write",
            "checks": "read",
            "contents": "read",
        }:
            raise ValueError("GitHub App token permissions exceed the isolated canary scope")
        return self


class TokenMetadata(_Strict):
    schema_version: Literal["3.1"] = "3.1"
    github_app_id: int
    installation_id: int
    repository: str
    permissions: dict[str, Literal["read", "write"]]
    token_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    issued_at: datetime
    expires_at: datetime


Transport = Callable[[urllib.request.Request, int], tuple[int, bytes]]


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _trusted_file(path: Path, *, owner_uid: int, mode: int, maximum: int) -> bytes:
    observed = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != owner_uid
        or observed.st_nlink != 1
        or stat.S_IMODE(observed.st_mode) != mode
        or observed.st_size <= 0
        or observed.st_size > maximum
    ):
        raise RefreshFailure("GitHub token refresher input is not trusted")
    return path.read_bytes()


def load_policy(path: Path = POLICY_PATH, *, expected_owner_uid: int = 0) -> RefreshPolicy:
    raw = _trusted_file(path, owner_uid=expected_owner_uid, mode=0o444, maximum=64_000)
    try:
        policy = RefreshPolicy.model_validate_json(raw, strict=True)
    except ValueError as exc:
        raise RefreshFailure("GitHub token refresher policy is invalid") from exc
    parsed = json.loads(raw)
    expected = (
        json.dumps(parsed, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    if raw != expected:
        raise RefreshFailure("GitHub token refresher policy is not exact")
    return policy


def _default_transport(request: urllib.request.Request, timeout: int) -> tuple[int, bytes]:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read(1_000_000)


def _app_jwt(policy: RefreshPolicy, key: rsa.RSAPrivateKey, now: datetime) -> str:
    timestamp = int(now.timestamp())
    header = _b64url(b'{"alg":"RS256","typ":"JWT"}')
    payload = _b64url(
        json.dumps(
            {"exp": timestamp + 540, "iat": timestamp - 30, "iss": policy.github_app_id},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    unsigned = f"{header}.{payload}".encode()
    signature = key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64url(signature)}"


def _atomic(path: Path, raw: bytes, mode: int) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.pending")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def refresh(
    policy: RefreshPolicy,
    *,
    now: datetime | None = None,
    transport: Transport = _default_transport,
) -> TokenMetadata:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    refresher_uid = pwd.getpwnam(REFRESHER_USER).pw_uid
    if os.geteuid() != refresher_uid:
        raise RefreshFailure("refresh must run as the dedicated token principal")
    key_raw = _trusted_file(
        Path(policy.private_key_path),
        owner_uid=refresher_uid,
        mode=0o600,
        maximum=64_000,
    )
    try:
        key = serialization.load_pem_private_key(key_raw, password=None)
    except ValueError as exc:
        raise RefreshFailure("GitHub App private key is invalid") from exc
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
        raise RefreshFailure("GitHub App private key is not an adequate RSA key")
    request = urllib.request.Request(
        f"{policy.audience}/app/installations/{policy.installation_id}/access_tokens",
        data=json.dumps(
            {
                "permissions": policy.permissions,
                "repositories": [policy.repository.split("/", 1)[1]],
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode(),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {_app_jwt(policy, key, current)}",
            "Content-Type": "application/json",
            "User-Agent": "TrainCapsule-Canary-Token-Refresher/3.1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        status, raw = transport(request, 30)
        payload: object = json.loads(raw)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise RefreshFailure("GitHub App token API is unavailable") from exc
    if not isinstance(payload, dict) or status != 201:
        raise RefreshFailure("GitHub App token API rejected the scoped request")
    response = cast(dict[str, object], payload)
    token = response.get("token")
    expiry = response.get("expires_at")
    try:
        expires = datetime.fromisoformat(str(expiry).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise RefreshFailure("GitHub App token expiry is invalid") from exc
    if (
        not isinstance(token, str)
        or not token.startswith("ghs_")
        or not 20 <= len(token) <= 4096
        or any(character in token for character in "\x00\r\n")
        or expires <= current + timedelta(seconds=policy.refresh_before_seconds)
        or expires > current + timedelta(hours=2)
    ):
        raise RefreshFailure("GitHub App token response is unsafe or already stale")
    metadata = TokenMetadata(
        github_app_id=policy.github_app_id,
        installation_id=policy.installation_id,
        repository=policy.repository,
        permissions=policy.permissions,
        token_digest="sha256:" + hashlib.sha256(token.encode()).hexdigest(),
        issued_at=current,
        expires_at=expires,
    )
    _atomic(Path(policy.outbox_token_path), token.encode(), 0o600)
    _atomic(
        Path(policy.outbox_metadata_path),
        (metadata.model_dump_json(by_alias=True) + "\n").encode(),
        0o600,
    )
    return metadata


def promote(policy: RefreshPolicy, *, now: datetime | None = None) -> TokenMetadata:
    if os.geteuid() != 0:
        raise RefreshFailure("GitHub App token promotion requires root")
    refresher_uid = pwd.getpwnam(REFRESHER_USER).pw_uid
    token = _trusted_file(
        Path(policy.outbox_token_path), owner_uid=refresher_uid, mode=0o600, maximum=4096
    )
    metadata_raw = _trusted_file(
        Path(policy.outbox_metadata_path),
        owner_uid=refresher_uid,
        mode=0o600,
        maximum=64_000,
    )
    try:
        metadata = TokenMetadata.model_validate_json(metadata_raw, strict=True)
    except ValueError as exc:
        raise RefreshFailure("GitHub App token metadata is invalid") from exc
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if (
        metadata.github_app_id != policy.github_app_id
        or metadata.installation_id != policy.installation_id
        or metadata.repository != policy.repository
        or metadata.permissions != policy.permissions
        or metadata.token_digest != "sha256:" + hashlib.sha256(token).hexdigest()
        or metadata.expires_at <= current + timedelta(seconds=policy.refresh_before_seconds)
        or not token.startswith(b"ghs_")
        or any(value in token for value in (b"\x00", b"\r", b"\n"))
    ):
        raise RefreshFailure("GitHub App token promotion binding is invalid")
    controller = pwd.getpwnam(CONTROLLER_USER)
    target = Path(policy.target_token_path)
    metadata_target = Path(policy.target_metadata_path)
    _atomic(metadata_target, metadata_raw, 0o400)
    os.chown(metadata_target, controller.pw_uid, controller.pw_gid, follow_symlinks=False)
    # Commit the credential last.  A crash beforehand leaves the previous usable token;
    # a crash before its chown leaves the replacement root-only and therefore fail-closed.
    _atomic(target, token, 0o600)
    os.chown(target, controller.pw_uid, controller.pw_gid, follow_symlinks=False)
    return metadata


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="traincapsule-github-token-refresher")
    parser.add_argument("action", choices=("refresh", "promote"))
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    args = parser.parse_args(argv)
    try:
        policy = load_policy(args.policy)
        if args.action == "refresh":
            refresh(policy)
        else:
            promote(policy)
        return 0
    except (OSError, RefreshFailure):
        print("GitHub App token refresh failed closed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
