"""Canonical product identity with deterministic, policy-versioned redaction."""

from __future__ import annotations

import re
from collections.abc import Mapping

from .base import digest_json
from .models import EnvironmentIdentity, WorkloadIdentity

_SECRET_NAME = re.compile(
    r"(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY|CREDENTIAL)", re.IGNORECASE
)


def _identity_material(payload: Mapping[str, object], identity_field: str) -> dict[str, object]:
    material = dict(payload)
    material.pop(identity_field, None)
    material.pop("createdAt", None)
    material.pop("created_at", None)
    return material


def build_workload_identity(payload: Mapping[str, object]) -> WorkloadIdentity:
    raw = dict(payload)
    raw["workloadId"] = digest_json(_identity_material(raw, "workloadId"))
    return WorkloadIdentity.model_validate(raw)


def build_environment_identity(payload: Mapping[str, object]) -> EnvironmentIdentity:
    raw = dict(payload)
    raw["environmentId"] = digest_json(_identity_material(raw, "environmentId"))
    return EnvironmentIdentity.model_validate(raw)


def redacted_environment_digest(
    variables: Mapping[str, str],
    *,
    policy_version: str,
) -> str:
    redacted = {
        name: "<redacted>" if _SECRET_NAME.search(name) else value
        for name, value in sorted(variables.items())
    }
    return digest_json({"policyVersion": policy_version, "variables": redacted})
