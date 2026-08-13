from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

import tcfactory.github_sync as github_sync
import tcfactory.v3.publication as publication
from tcfactory.github_sync import GitHubConfig, load_github_config
from tcfactory.v3.publication import (
    ExternalReceiptAuthorizer,
    GhPublicationClient,
    PublicationError,
    trusted_external_path,
)

CANDIDATE = "b" * 40


def test_direct_main_publication_surfaces_do_not_exist() -> None:
    assert not hasattr(github_sync, "push_main_with_retry")
    assert not hasattr(github_sync, "MainOnlyPublisher")
    assert not hasattr(github_sync, "MainPublicationTransaction")
    source = Path(github_sync.__file__).read_text(encoding="utf-8")
    assert "fast_forward_main" not in source
    assert ":refs/heads/main" not in source


def test_candidate_push_rejects_main_force_tags_and_symbolic_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed: list[list[str]] = []

    def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        observed.append(args)
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr(publication, "run_command", fake_run)
    client = GhPublicationClient(
        tmp_path,
        remote="origin",
        repository="TasfiqJ/TrainCapsule",
        branch_prefix="factory/",
    )
    for branch in ("main", "refs/tags/release", "factory/../main", "other/candidate"):
        with pytest.raises(PublicationError):
            client.push_candidate_branch(sha=CANDIDATE, branch=branch)
    with pytest.raises(PublicationError, match="exact commit SHA"):
        client.push_candidate_branch(sha="HEAD", branch="factory/v3-rel-001/candidate")
    client.push_candidate_branch(sha=CANDIDATE, branch="factory/v3-rel-001/candidate")
    assert observed == [
        [
            "git",
            "push",
            "--porcelain",
            "origin",
            f"{CANDIDATE}:refs/heads/factory/v3-rel-001/candidate",
        ]
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("directMainPush", True),
        ("releaseMode", "owner_directed_main_only"),
        ("publisherCapability", "PENDING_PHASE_4"),
        ("candidateBranchPrefix", "main"),
    ],
)
def test_v31_config_rejects_legacy_or_unproven_release_modes(field: str, value: object) -> None:
    root = Path(__file__).resolve().parents[1]
    payload = load_github_config(root / "config/github.yaml").model_dump(mode="json", by_alias=True)
    payload[field] = value
    with pytest.raises(ValidationError):
        GitHubConfig.model_validate(payload)


def test_required_check_roster_cannot_omit_independent_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = load_github_config(root / "config/github.yaml").model_dump(mode="json", by_alias=True)
    remote = payload["remoteCi"]
    assert isinstance(remote, dict)
    remote["requiredWorkflows"] = ["TrainCapsule / Factory quality"]
    remote["trustedCheckAppIds"] = {"TrainCapsule / Factory quality": 15368}
    with pytest.raises(ValidationError, match="machine-policy"):
        GitHubConfig.model_validate(payload)


def test_release_rules_require_pr_controls_without_merge_deadlocking_update() -> None:
    valid = {"required_status_checks", "pull_request", "non_fast_forward", "deletion"}
    github_sync.validate_release_rule_types(valid)
    with pytest.raises(github_sync.GitHubSyncError, match="would block.*PR merges"):
        github_sync.validate_release_rule_types(valid | {"update"})
    with pytest.raises(github_sync.GitHubSyncError, match="missing required release controls"):
        github_sync.validate_release_rule_types({"non_fast_forward", "deletion"})


def test_pull_request_observation_cannot_launder_a_non_main_base() -> None:
    raw: dict[str, object] = {
        "number": 1,
        "url": "https://github.com/TasfiqJ/TrainCapsule/pull/1",
        "state": "OPEN",
        "isDraft": True,
        "headRefName": "factory/v3-rel-001/candidate",
        "headRefOid": CANDIDATE,
        "baseRefName": "attacker-controlled-base",
        "baseRefOid": "a" * 40,
        "mergedAt": None,
        "mergeCommit": None,
        "autoMergeRequest": None,
    }
    with pytest.raises(PublicationError, match="invalid types"):
        GhPublicationClient._pr(raw)  # pyright: ignore[reportPrivateUsage]


def test_external_verifier_paths_reject_symlink_substitution(tmp_path: Path) -> None:
    executable_link = tmp_path / "verifier"
    executable_link.symlink_to("/usr/bin/true")
    with pytest.raises(PublicationError, match="symlink"):
        ExternalReceiptAuthorizer(executable_link)

    receipt_root = tmp_path / "receipts"
    receipt_root.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(PublicationError, match="symlink"):
        trusted_external_path(receipt_root, directory=True, label="receipt root")
