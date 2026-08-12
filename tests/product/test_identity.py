from __future__ import annotations

from copy import deepcopy

from traincapsule_core import (
    build_environment_identity,
    build_workload_identity,
    canonical_json_bytes,
    redacted_environment_digest,
)
from traincapsule_core.models import CompletenessState, DataIdentityPolicy
from traincapsule_qualify import assess_completeness

from .reference_identity import canonical_reference, identity_reference

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def workload_material() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "sourceIdentity": {"repositoryDigest": DIGEST_A, "dirtyPatchDigest": None},
        "entrypoint": "train.py",
        "argumentsDigest": DIGEST_B,
        "containerImageDigest": None,
        "dependencyLockDigest": DIGEST_A,
        "framework": {"name": "pytorch", "version": "2.5.1"},
        "distributed": {
            "strategy": "ddp",
            "worldSize": 2,
            "processGroupsDigest": DIGEST_B,
        },
        "modelStructureDigest": None,
        "dataIdentity": {"policy": "CUSTOMER_ATTESTED", "manifestDigest": None},
        "checkpointPolicyDigest": None,
        "privacyClass": "CONFIDENTIAL",
        "createdAt": "2026-08-11T20:00:00Z",
    }


def environment_material() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "hostKernel": "Linux 6.8",
        "containerRuntime": "containerd 2.0",
        "python": "3.12.4",
        "pytorch": "2.5.1",
        "cudaRuntime": "12.4",
        "cudaDriver": "550.90",
        "nccl": "2.22",
        "gpuModel": "H100",
        "gpuCount": 2,
        "gpuFirmwareDigest": None,
        "topologyDigest": DIGEST_A,
        "scheduler": "slurm",
        "networkClass": "infiniband",
        "storageClass": "local-nvme",
        "environmentVariablesDigest": DIGEST_B,
        "redactionPolicyVersion": "v1",
        "materializationRecipeDigest": None,
        "createdAt": "2026-08-11T20:00:00Z",
    }


def test_canonical_json_matches_independent_reference_and_utf8_lf() -> None:
    value = {"z": "évidence", "a": [2, 1], "nested": {"b": False}}
    rendered = canonical_json_bytes(value)
    assert rendered == canonical_reference(value)
    assert rendered.endswith(b"\n")
    assert b"\r" not in rendered
    assert b"\xc3\xa9" in rendered
    assert rendered.startswith(b'{"a"')


def test_workload_identity_matches_independent_golden_vector() -> None:
    material = workload_material()
    identity = build_workload_identity(material)
    assert identity.workload_id == identity_reference(material, "workloadId")
    assert identity.data_identity.policy is DataIdentityPolicy.CUSTOMER_ATTESTED
    assert identity.data_identity.manifest_digest is None


def test_identity_ignores_field_order_and_supplied_timestamp_but_not_material_drift() -> None:
    first = workload_material()
    reordered = dict(reversed(list(first.items())))
    reordered["createdAt"] = "2030-01-01T00:00:00Z"
    assert build_workload_identity(first).workload_id == build_workload_identity(
        reordered
    ).workload_id

    drifted = deepcopy(first)
    drifted["entrypoint"] = "train_v2.py"
    assert build_workload_identity(first).workload_id != build_workload_identity(
        drifted
    ).workload_id


def test_environment_identity_matches_independent_reference() -> None:
    material = environment_material()
    identity = build_environment_identity(material)
    assert identity.environment_id == identity_reference(material, "environmentId")


def test_secret_values_are_redacted_before_environment_digest() -> None:
    first = redacted_environment_digest(
        {"API_TOKEN": "secret-one", "NCCL_DEBUG": "INFO"}, policy_version="v1"
    )
    second = redacted_environment_digest(
        {"API_TOKEN": "secret-two", "NCCL_DEBUG": "INFO"}, policy_version="v1"
    )
    changed_public = redacted_environment_digest(
        {"API_TOKEN": "secret-two", "NCCL_DEBUG": "WARN"}, policy_version="v1"
    )
    assert first == second
    assert changed_public != first


def test_customer_attestation_is_not_laundered_as_bound_identity() -> None:
    report = assess_completeness(
        case_id="CASE-ATTESTED",
        requirements={"data_identity": CompletenessState.IDENTITY_UNBOUND},
    )
    assert report.technical_result.value == "UNKNOWN"
    assert report.requirements[0].state is CompletenessState.IDENTITY_UNBOUND
