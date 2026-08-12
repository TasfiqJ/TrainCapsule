from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from traincapsule_core import (
    build_environment_identity,
    build_workload_identity,
    canonical_json_bytes,
    redacted_environment_digest,
)
from traincapsule_core.models import IdentityStrength

from .reference_identity import canonical_reference, identity_reference

ROOT = Path(__file__).resolve().parents[2]
WORKLOAD_VECTOR = "sha256:c84088d6ab6a489c01b070a10a30adad682fe6b6f78fd2b85b4e674865e035ab"
ENVIRONMENT_VECTOR = "sha256:30fbb83d6cb1c44d106ea48bd9527976da4e7edb0c5016f8f9b379550f6c18ea"


def workload_material() -> dict[str, object]:
    raw: object = json.loads((ROOT / "examples/product/workload-identity-input.json").read_bytes())
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


def environment_material() -> dict[str, object]:
    raw: object = json.loads(
        (ROOT / "examples/product/environment-identity-input.json").read_bytes()
    )
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


def test_canonical_json_matches_independent_reference_and_utf8_lf() -> None:
    value = {"z": "évidence", "a": [2, 1], "nested": {"b": False}}
    rendered = canonical_json_bytes(value)
    assert rendered == canonical_reference(value)
    assert rendered.endswith(b"\n") and b"\r" not in rendered
    assert b"\xc3\xa9" in rendered and rendered.startswith(b'{"a"')


def test_fixed_committed_identity_vectors_match_independent_oracle() -> None:
    workload = build_workload_identity(workload_material())
    environment = build_environment_identity(environment_material())
    assert workload.workload_id == WORKLOAD_VECTOR
    assert environment.environment_id == ENVIRONMENT_VECTOR
    assert workload.workload_id == identity_reference(
        workload.model_dump(mode="json", by_alias=True), "workloadId"
    )
    assert environment.environment_id == identity_reference(
        environment.model_dump(mode="json", by_alias=True), "environmentId"
    )


def test_identity_ignores_field_order_and_timestamp_but_detects_material_drift() -> None:
    first = workload_material()
    reordered = dict(reversed(list(first.items())))
    reordered["createdAt"] = "2030-01-01T00:00:00Z"
    assert (
        build_workload_identity(first).workload_id == build_workload_identity(reordered).workload_id
    )
    drifted = deepcopy(first)
    drifted["entrypoint"] = "train_v2.py"
    assert (
        build_workload_identity(first).workload_id != build_workload_identity(drifted).workload_id
    )


def test_redaction_is_enforced_and_policy_versioned() -> None:
    first = workload_material()
    changed_secret = deepcopy(first)
    variables = changed_secret["relevantEnvironmentVariables"]
    assert isinstance(variables, dict)
    variables["SERVICE_TOKEN"] = "different-secret"
    assert (
        build_workload_identity(first).workload_id
        == build_workload_identity(changed_secret).workload_id
    )
    changed_public = deepcopy(first)
    public_variables = changed_public["relevantEnvironmentVariables"]
    assert isinstance(public_variables, dict)
    public_variables["NCCL_DEBUG"] = "WARN"
    assert (
        build_workload_identity(first).workload_id
        != build_workload_identity(changed_public).workload_id
    )
    with pytest.raises(ValueError, match="unsupported redaction policy"):
        redacted_environment_digest({}, policy_version="unknown")
    supplied = deepcopy(first)
    supplied["relevantEnvironmentDigest"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="does not match redacted variables"):
        build_workload_identity(supplied)

    embedded_first = deepcopy(first)
    embedded_variables = embedded_first["relevantEnvironmentVariables"]
    assert isinstance(embedded_variables, dict)
    embedded_variables["DATABASE_URL"] = "postgres://user:secret-one@db.example/app"
    embedded_second = deepcopy(embedded_first)
    second_variables = embedded_second["relevantEnvironmentVariables"]
    assert isinstance(second_variables, dict)
    second_variables["DATABASE_URL"] = "postgres://user:secret-two@db.example/app"
    assert (
        build_workload_identity(embedded_first).workload_id
        == build_workload_identity(embedded_second).workload_id
    )


@pytest.mark.parametrize(
    ("policy", "digest", "strength"),
    [
        ("FULL_DIGEST", "sha256:" + "a" * 64, IdentityStrength.FULLY_VERIFIED),
        ("MANIFEST_DIGEST", "sha256:" + "a" * 64, IdentityStrength.PARTIALLY_VERIFIED),
        ("CUSTOMER_ATTESTED", None, IdentityStrength.CUSTOMER_ATTESTED),
        ("UNAVAILABLE", None, IdentityStrength.UNVERIFIED),
    ],
)
def test_data_policy_derives_identity_strength(
    policy: str, digest: str | None, strength: IdentityStrength
) -> None:
    material = workload_material()
    material["dataIdentity"] = {"policy": policy, "manifestDigest": digest}
    assert build_workload_identity(material).identity_strength is strength


def test_conflict_is_explicit_and_supplied_strength_is_ignored() -> None:
    material = workload_material()
    material["identityConflict"] = True
    assert build_workload_identity(material).identity_strength is IdentityStrength.CONFLICTING
    material = workload_material()
    material["identityStrength"] = "FULLY_VERIFIED"
    assert build_workload_identity(material).identity_strength is IdentityStrength.FULLY_VERIFIED


@pytest.mark.parametrize(
    ("policy", "digest", "strength"),
    [
        ("FULL_DIGEST", "sha256:" + "a" * 64, IdentityStrength.FULLY_VERIFIED),
        ("MANIFEST_DIGEST", "sha256:" + "a" * 64, IdentityStrength.PARTIALLY_VERIFIED),
        ("CUSTOMER_ATTESTED", None, IdentityStrength.CUSTOMER_ATTESTED),
        ("UNAVAILABLE", None, IdentityStrength.UNVERIFIED),
    ],
)
def test_environment_identity_strength_is_derived_without_attestation_laundering(
    policy: str, digest: str | None, strength: IdentityStrength
) -> None:
    material = environment_material()
    material["identityPolicy"] = policy
    material["identityEvidenceDigest"] = digest
    material["identityStrength"] = "FULLY_VERIFIED"
    assert build_environment_identity(material).identity_strength is strength
