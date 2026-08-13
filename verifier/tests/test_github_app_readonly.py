from __future__ import annotations

import base64
import json
import urllib.request
from types import TracebackType

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from traincapsule_verifier.github_app_readonly import mint_read_only_installation_token


class _Response:
    def __enter__(self) -> _Response:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        return None

    def read(self, _maximum: int) -> bytes:
        return b'{"token":"short-lived-installation-token"}'


def test_read_only_observer_mints_installation_token_without_pat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = generate_private_key(public_exponent=65537, key_size=2048)
    encoded = base64.b64encode(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    ).decode()
    observed: list[urllib.request.Request] = []

    def open_request(request: urllib.request.Request, *, timeout: int) -> _Response:
        assert timeout == 30
        observed.append(request)
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", open_request)
    token = mint_read_only_installation_token(
        app_id=4580794,
        installation_id=153427520,
        private_key_base64=encoded,
    )
    assert token == "short-lived-installation-token"
    assert len(observed) == 1
    request = observed[0]
    assert request.full_url.endswith("/app/installations/153427520/access_tokens")
    authorization = request.headers["Authorization"]
    assert authorization.startswith("Bearer ")
    jwt = authorization.removeprefix("Bearer ")
    assert len(jwt.split(".")) == 3
    assert json.loads(base64.urlsafe_b64decode(jwt.split(".")[0] + "==")) == {
        "alg": "RS256",
        "typ": "JWT",
    }


def test_read_only_observer_rejects_pat_or_non_key_text() -> None:
    with pytest.raises(ValueError, match="credential is invalid"):
        mint_read_only_installation_token(
            app_id=4580794,
            installation_id=153427520,
            private_key_base64=base64.b64encode(b"ghp_not_allowed").decode(),
        )
