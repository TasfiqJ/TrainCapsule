"""Short-lived read-only GitHub App authentication for independent observers."""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from typing import cast

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint_read_only_installation_token(
    *, app_id: int, installation_id: int, private_key_base64: str
) -> str:
    """Mint one bounded installation token without accepting PAT credentials."""

    if app_id <= 0 or installation_id <= 0:
        raise ValueError("GitHub App identity is invalid")
    try:
        key_raw = base64.b64decode(private_key_base64, validate=True)
        key = serialization.load_pem_private_key(key_raw, password=None)
    except (ValueError, TypeError) as exc:
        raise ValueError("GitHub App credential is invalid") from exc
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
        raise ValueError("GitHub App credential must be RSA-2048 or stronger")
    now = int(time.time())
    header = _b64url(b'{"alg":"RS256","typ":"JWT"}')
    payload = _b64url(
        json.dumps(
            {"iat": now - 30, "exp": now + 540, "iss": app_id},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    unsigned = f"{header}.{payload}".encode()
    signature = key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256())
    request = urllib.request.Request(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        data=b"{}",
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {header}.{payload}.{_b64url(signature)}",
            "Content-Type": "application/json",
            "User-Agent": "TrainCapsule-Independent-Observer/3.1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result: object = json.loads(response.read(1_000_000))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise ValueError("GitHub App installation token is unavailable") from exc
    if not isinstance(result, dict):
        raise ValueError("GitHub App installation token response is invalid")
    typed_result = cast(dict[str, object], result)
    if not isinstance(typed_result.get("token"), str):
        raise ValueError("GitHub App installation token response is invalid")
    return cast(str, typed_result["token"])
