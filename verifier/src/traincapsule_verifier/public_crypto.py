"""Public-key-only Ed25519 primitives for the public verifier process."""

from __future__ import annotations

import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .canonical import sha256_digest, unsigned_model_bytes
from .models import StrictModel


class SignatureError(ValueError):
    pass


def public_key_fingerprint(key: Ed25519PublicKey) -> str:
    raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return sha256_digest(raw)


def verify_model_signature(model: StrictModel, key: Ed25519PublicKey) -> None:
    signature = getattr(model, "signature", None)
    if not isinstance(signature, str):
        raise SignatureError("signed model lacks a signature")
    try:
        decoded = base64.b64decode(signature, validate=True)
        key.verify(decoded, unsigned_model_bytes(model))
    except (ValueError, InvalidSignature) as exc:
        raise SignatureError("Ed25519 signature is invalid") from exc


def load_public_key(data: bytes) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(data)  # pyright: ignore[reportUnknownMemberType]
    if not isinstance(key, Ed25519PublicKey):
        raise SignatureError("public key is not Ed25519")
    return key
