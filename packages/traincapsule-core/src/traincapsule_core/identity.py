"""Canonical identity with mandatory deterministic, policy-versioned redaction."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import cast

from .base import digest_json
from .models import (
    DataIdentityPolicy,
    EnvironmentIdentity,
    IdentityStrength,
    WorkloadIdentity,
)

_SECRET_NAME = re.compile(
    r"(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY|CREDENTIAL|AUTH|COOKIE)",
    re.IGNORECASE,
)
_URL_CREDENTIAL = re.compile(r"(?P<prefix>[a-z][a-z0-9+.-]*://[^:/@\s]+:)[^@/\s]+@", re.I)
_ASSIGNMENT_SECRET = re.compile(
    r"(?i)(?P<prefix>(?:password|passwd|token|secret|api[_-]?key)=)[^&;\s]+"
)
_AUTH_VALUE = re.compile(r"(?i)^(?:bearer|basic)\s+\S+$")
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
SUPPORTED_REDACTION_POLICIES = frozenset({"traincapsule-redaction-v1"})


def _identity_material(payload: Mapping[str, object], identity_field: str) -> dict[str, object]:
    material = dict(payload)
    material.pop(identity_field, None)
    material.pop("createdAt", None)
    material.pop("created_at", None)
    return material


def redacted_environment_digest(variables: Mapping[str, str], *, policy_version: str) -> str:
    if policy_version not in SUPPORTED_REDACTION_POLICIES:
        raise ValueError(f"unsupported redaction policy: {policy_version}")

    def redact(name: str, value: str) -> str:
        if _SECRET_NAME.search(name) or _AUTH_VALUE.match(value) or _PRIVATE_KEY.search(value):
            return "<redacted>"
        value = _URL_CREDENTIAL.sub(r"\g<prefix><redacted>@", value)
        return _ASSIGNMENT_SECRET.sub(r"\g<prefix><redacted>", value)

    redacted = {name: redact(name, value) for name, value in sorted(variables.items())}
    return digest_json({"policyVersion": policy_version, "variables": redacted})


def _string_mapping(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object of decision-relevant string variables")
    result: dict[str, str] = {}
    for name, raw_value in cast(Mapping[object, object], value).items():
        if not isinstance(name, str) or not isinstance(raw_value, str):
            raise ValueError(f"{label} must contain string names and values")
        result[name] = raw_value
    return result


def build_workload_identity(payload: Mapping[str, object]) -> WorkloadIdentity:
    raw = dict(payload)
    policy_version = raw.get("redactionPolicyVersion")
    if not isinstance(policy_version, str):
        raise ValueError("redactionPolicyVersion is required")
    variables = _string_mapping(
        raw.pop("relevantEnvironmentVariables", None), "relevantEnvironmentVariables"
    )
    supplied = raw.pop("relevantEnvironmentDigest", None)
    computed = redacted_environment_digest(variables, policy_version=policy_version)
    if supplied is not None and supplied != computed:
        raise ValueError("supplied relevantEnvironmentDigest does not match redacted variables")
    raw["relevantEnvironmentDigest"] = computed
    data = raw.get("dataIdentity")
    if not isinstance(data, Mapping):
        raise ValueError("dataIdentity is required")
    policy = DataIdentityPolicy(cast(Mapping[str, object], data).get("policy"))
    strength = {
        DataIdentityPolicy.FULL_DIGEST: IdentityStrength.FULLY_VERIFIED,
        DataIdentityPolicy.MANIFEST_DIGEST: IdentityStrength.PARTIALLY_VERIFIED,
        DataIdentityPolicy.CUSTOMER_ATTESTED: IdentityStrength.CUSTOMER_ATTESTED,
        DataIdentityPolicy.UNAVAILABLE: IdentityStrength.UNVERIFIED,
    }[policy]
    if raw.pop("identityConflict", False) is True:
        strength = IdentityStrength.CONFLICTING
    raw["identityStrength"] = strength.value
    raw["workloadId"] = digest_json(_identity_material(raw, "workloadId"))
    return WorkloadIdentity.model_validate(raw)


def build_environment_identity(payload: Mapping[str, object]) -> EnvironmentIdentity:
    raw = dict(payload)
    policy_version = raw.get("redactionPolicyVersion")
    if not isinstance(policy_version, str):
        raise ValueError("redactionPolicyVersion is required")
    variables = _string_mapping(raw.pop("environmentVariables", None), "environmentVariables")
    supplied = raw.pop("environmentVariablesDigest", None)
    computed = redacted_environment_digest(variables, policy_version=policy_version)
    if supplied is not None and supplied != computed:
        raise ValueError("supplied environmentVariablesDigest does not match redacted variables")
    raw["environmentVariablesDigest"] = computed
    policy = DataIdentityPolicy(raw.get("identityPolicy"))
    strength = {
        DataIdentityPolicy.FULL_DIGEST: IdentityStrength.FULLY_VERIFIED,
        DataIdentityPolicy.MANIFEST_DIGEST: IdentityStrength.PARTIALLY_VERIFIED,
        DataIdentityPolicy.CUSTOMER_ATTESTED: IdentityStrength.CUSTOMER_ATTESTED,
        DataIdentityPolicy.UNAVAILABLE: IdentityStrength.UNVERIFIED,
    }[policy]
    if raw.pop("identityConflict", False) is True:
        strength = IdentityStrength.CONFLICTING
    raw["identityStrength"] = strength.value
    raw["environmentId"] = digest_json(_identity_material(raw, "environmentId"))
    return EnvironmentIdentity.model_validate(raw)
