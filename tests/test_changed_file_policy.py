import pytest

from tcfactory.gates import PathPolicyError, validate_changed_paths


def test_allowed_path_passes() -> None:
    validate_changed_paths(
        ["packages/trust/status.py"],
        allowed=["packages/trust/**"],
        forbidden=["docs/source-of-truth/**"],
        read_only=False,
    )


def test_forbidden_path_fails() -> None:
    with pytest.raises(PathPolicyError):
        validate_changed_paths(
            ["incident-packs/pre_collective_lifecycle_v1/contract.yaml"],
            allowed=["packages/**", "incident-packs/**"],
            forbidden=["incident-packs/**"],
            read_only=False,
        )


def test_read_only_stage_fails_on_any_change() -> None:
    with pytest.raises(PathPolicyError):
        validate_changed_paths(["README.md"], allowed=[], forbidden=[], read_only=True)
