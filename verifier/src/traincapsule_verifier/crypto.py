"""Ed25519 signing and verification with explicit key fingerprints."""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .canonical import unsigned_model_bytes
from .models import StrictModel
from .public_crypto import (
    SignatureError,
    load_public_key,
    public_key_fingerprint,
    verify_model_signature,
)

__all__ = [
    "SignatureError",
    "load_private_key",
    "load_public_key",
    "public_key_fingerprint",
    "sign_model",
    "verify_model_signature",
]


def sign_model(model: StrictModel, key: Ed25519PrivateKey) -> str:
    import base64

    return base64.b64encode(key.sign(unsigned_model_bytes(model))).decode("ascii")


def load_private_key(data: bytes) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(  # pyright: ignore[reportUnknownMemberType]
        data, password=None
    )
    if not isinstance(key, Ed25519PrivateKey):
        raise SignatureError("private key is not Ed25519")
    return key
