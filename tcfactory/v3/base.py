"""Shared strict and deterministic primitives for TrainCapsule V3 records."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def to_camel(value: str) -> str:
    """Translate one internal snake_case name to the V3 wire format."""

    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


def sha256_digest(data: bytes) -> str:
    """Return the canonical prefixed SHA-256 representation."""

    return f"sha256:{hashlib.sha256(data).hexdigest()}"


class V3Model(BaseModel):
    """Base for repository records with strict shape and controlled vocabularies."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    def canonical_json_bytes(self) -> bytes:
        """Serialize deterministically for immutable evidence and signatures."""

        payload = self.model_dump(mode="json", by_alias=True, exclude_none=False)
        return (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            + "\n"
        ).encode("utf-8")

    def canonical_digest(self) -> str:
        """Digest the deterministic wire representation."""

        return sha256_digest(self.canonical_json_bytes())


def verify_bound_payloads(
    expected: Mapping[str, str],
    actual: Mapping[str, bytes],
) -> None:
    """Fail closed if a bound payload is absent, substituted, or unexpected."""

    missing = set(expected) - set(actual)
    unexpected = set(actual) - set(expected)
    if missing or unexpected:
        raise ValueError(
            f"bound artifact set mismatch: missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )
    mismatched = [
        name for name, digest in expected.items() if sha256_digest(actual[name]) != digest
    ]
    if mismatched:
        raise ValueError(f"bound artifact digest mismatch: {sorted(mismatched)}")


def json_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """Generate a stable draft-2020-12-compatible Pydantic schema payload."""

    schema = model.model_json_schema(by_alias=True, mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return schema
