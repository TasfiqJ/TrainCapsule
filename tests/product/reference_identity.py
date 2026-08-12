"""Independent stdlib reference used only by identity golden-vector tests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


def canonical_reference(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def digest_reference(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_reference(value)).hexdigest()


def identity_reference(payload: Mapping[str, object], identity_field: str) -> str:
    material = dict(payload)
    material.pop(identity_field, None)
    material.pop("createdAt", None)
    material.pop("created_at", None)
    if material.get("identityConflict") is False:
        material.pop("identityConflict")
    return digest_reference(material)
