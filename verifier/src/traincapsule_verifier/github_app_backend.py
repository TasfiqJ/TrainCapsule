"""Concrete idempotent GitHub App Checks API backend."""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .check_publisher import (
    CheckDeliveryReceipt,
    CheckEvent,
    CheckPublisherPolicy,
    CheckPublisherUnavailable,
    CheckPublishRequest,
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class GitHubAppHTTPBackend:
    """HTTPS-only GitHub App backend; credentials never enter repository code or events."""

    def __init__(
        self,
        *,
        policy: CheckPublisherPolicy,
        private_key_path: Path,
        events: Sequence[CheckEvent] = (),
        api_root: str = "https://api.github.com",
        timeout_seconds: int = 30,
    ) -> None:
        if api_root != "https://api.github.com":
            raise ValueError("GitHub App backend API root is fixed to official HTTPS")
        if private_key_path.is_symlink() or not private_key_path.is_file():
            raise CheckPublisherUnavailable("GitHub App credential is unavailable")
        mode = private_key_path.stat().st_mode & 0o777
        if mode & 0o077:
            raise CheckPublisherUnavailable("GitHub App credential permissions are unsafe")
        key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise CheckPublisherUnavailable("GitHub App credential is not an RSA private key")
        self.policy = policy
        self.key = key
        self.events = tuple(events)
        self.api_root = api_root
        self.timeout_seconds = timeout_seconds
        self._installation_token: str | None = None

    @property
    def backend_id(self) -> str:
        return self.policy.backend_id

    @property
    def github_app_id(self) -> int:
        return self.policy.github_app_id

    def _app_jwt(self) -> str:
        now = int(time.time())
        header = _b64url(b'{"alg":"RS256","typ":"JWT"}')
        payload = _b64url(
            json.dumps(
                {"iat": now - 30, "exp": now + 540, "iss": self.github_app_id},
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        )
        unsigned = f"{header}.{payload}".encode()
        signature = self.key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256())
        return f"{header}.{payload}.{_b64url(signature)}"

    def _json_request(
        self, method: str, path: str, *, payload: dict[str, object] | None = None, app: bool = False
    ) -> object:
        token = self._app_jwt() if app else self._installation_access_token()
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        request = urllib.request.Request(
            self.api_root + path,
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "TrainCapsule-Independent-Verifier/3.1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status < 200 or response.status >= 300:
                    raise CheckPublisherUnavailable("GitHub App API returned a non-success status")
                return json.loads(response.read(2_000_000))
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise CheckPublisherUnavailable("GitHub App API is unavailable") from exc

    def _installation_access_token(self) -> str:
        if self._installation_token is not None:
            return self._installation_token
        response = self._json_request(
            "POST",
            f"/app/installations/{self.policy.installation_id}/access_tokens",
            payload={},
            app=True,
        )
        if not isinstance(response, dict):
            raise CheckPublisherUnavailable("GitHub App installation token response is invalid")
        typed_response = cast(dict[str, object], response)
        if not isinstance(typed_response.get("token"), str):
            raise CheckPublisherUnavailable("GitHub App installation token response is invalid")
        self._installation_token = cast(str, typed_response["token"])
        return self._installation_token

    def poll(self, *, after_event_id: str | None, limit: int) -> Sequence[CheckEvent]:
        events = self.events
        if after_event_id is not None:
            events = tuple(event for event in events if event.event_id > after_event_id)
        return events[:limit]

    def lookup(self, *, request: CheckPublishRequest) -> CheckDeliveryReceipt | None:
        response = self._json_request(
            "GET",
            f"/repos/{self.policy.repository}/commits/{request.candidate_sha}/check-runs",
        )
        if not isinstance(response, dict):
            raise CheckPublisherUnavailable("GitHub check lookup response is invalid")
        typed_response = cast(dict[str, object], response)
        if not isinstance(typed_response.get("check_runs"), list):
            raise CheckPublisherUnavailable("GitHub check lookup response is invalid")
        for item in cast(list[object], typed_response["check_runs"]):
            if isinstance(item, dict):
                typed_item = cast(dict[str, object], item)
            else:
                continue
            if typed_item.get("external_id") == request.action_digest:
                output = typed_item.get("output")
                if not isinstance(output, dict):
                    raise CheckPublisherUnavailable("GitHub check output binding is missing")
                typed_output = cast(dict[str, object], output)
                external_id = typed_item.get("id")
                if typed_output.get("summary") != request.receipt_digest or not isinstance(
                    external_id, int
                ):
                    raise CheckPublisherUnavailable("GitHub check output binding conflicts")
                return CheckDeliveryReceipt(
                    schema_version="3.1",
                    action_digest=request.action_digest,
                    backend_id=request.backend_id,
                    repository=request.repository,
                    github_app_id=request.github_app_id,
                    installation_id=request.installation_id,
                    external_check_id=str(external_id),
                    check_name=request.check_name,
                    candidate_sha=request.candidate_sha,
                    conclusion=request.conclusion,
                    receipt_id=request.receipt_id,
                    receipt_digest=request.receipt_digest,
                )
        return None

    def publish(self, request: CheckPublishRequest) -> CheckDeliveryReceipt:
        delivery = CheckDeliveryReceipt(
            schema_version="3.1",
            action_digest=request.action_digest,
            backend_id=request.backend_id,
            repository=request.repository,
            github_app_id=request.github_app_id,
            installation_id=request.installation_id,
            external_check_id="PENDING",
            check_name=request.check_name,
            candidate_sha=request.candidate_sha,
            conclusion=request.conclusion,
            receipt_id=request.receipt_id,
            receipt_digest=request.receipt_digest,
        )
        response = self._json_request(
            "POST",
            f"/repos/{request.repository}/check-runs",
            payload={
                "name": request.check_name,
                "head_sha": request.candidate_sha,
                "status": "completed",
                "conclusion": request.conclusion,
                "external_id": request.action_digest,
                "output": {
                    "title": "Independent machine-policy receipt verified",
                    "summary": request.receipt_digest,
                },
            },
        )
        if not isinstance(response, dict):
            raise CheckPublisherUnavailable("GitHub check creation response is invalid")
        typed_response = cast(dict[str, object], response)
        external_id = typed_response.get("id")
        if not isinstance(external_id, int):
            raise CheckPublisherUnavailable("GitHub check creation response is invalid")
        return delivery.model_copy(update={"external_check_id": str(external_id)})
