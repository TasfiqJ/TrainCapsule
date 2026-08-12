"""Canonical serialization primitives for independent signatures and digests."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def canonical_json_bytes(value: BaseModel | dict[str, Any]) -> bytes:
    payload = (
        value.model_dump(mode="json", by_alias=True, exclude_none=False)
        if isinstance(value, BaseModel)
        else value
    )
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def unsigned_model_bytes(value: BaseModel) -> bytes:
    payload = value.model_dump(mode="json", by_alias=True, exclude_none=False)
    payload.pop("signature", None)
    return canonical_json_bytes(payload)


def sha256_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def model_digest(value: BaseModel) -> str:
    return sha256_digest(canonical_json_bytes(value))
