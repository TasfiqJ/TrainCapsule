from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tcfactory.v3.rollback_rehearsal import RollbackAttestationError, rehearse


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Rollback Test")
    _git(repo, "config", "user.email", "rollback@example.invalid")
    tracked = repo / "tracked.txt"
    tracked.write_text("rollback bytes\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "rollback start")
    start = _git(repo, "rev-parse", "HEAD")
    tag_name = "safety/v3-start"
    _git(repo, "tag", "-a", tag_name, "-m", "V3 start")
    tag_object = _git(repo, "rev-parse", f"refs/tags/{tag_name}")
    _git(repo, "switch", "-c", "migration")
    (repo / "migration.txt").write_text("moving branch\n", encoding="utf-8")
    _git(repo, "add", "migration.txt")
    _git(repo, "commit", "-m", "migration work")

    snapshot = {
        "startingState": {
            "startingLocalHead": start,
            "startingOriginMain": start,
        },
        "safetyRef": {
            "name": tag_name,
            "tagObjectSha": tag_object,
            "peeledCommitSha": start,
        },
        "workingBranch": {"name": "migration", "startingSha": start},
    }
    snapshot_path = repo / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    transcript_path = repo / "transcript.json"
    transcript_path.write_text('{"result":"PASS","workItemId":"V3-MIG-002"}\n', encoding="utf-8")
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "workItemId": "V3-MIG-002",
        "safetyTag": {
            "name": tag_name,
            "objectType": "tag",
            "objectSha": tag_object,
            "peeledCommit": start,
        },
        "migrationBranch": {
            "ref": "refs/heads/migration",
            "attestedStartCommit": start,
            "semantics": "The tag and start SHA are immutable; this branch moves.",
        },
        "snapshotPath": "snapshot.json",
        "trackedInputs": [
            {
                "path": "tracked.txt",
                "bytes": len(tracked.read_bytes()),
                "sha256": hashlib.sha256(tracked.read_bytes()).hexdigest(),
            }
        ],
        "rollbackInstructions": {
            "operations": [
                "VERIFY_ANNOTATED_TAG",
                "VERIFY_BRANCH_START",
                "EXPORT_ARCHIVE_TO_DISPOSABLE_DIRECTORY",
                "VERIFY_SNAPSHOT_INPUTS",
                "DISCARD_DISPOSABLE_DIRECTORY",
            ],
            "operatorNote": (
                "Inspect only the disposable export and leave source and runtime untouched."
            ),
            "mutatesRepository": False,
            "accessesRuntime": False,
        },
        "evidence": {
            "transcriptPath": "transcript.json",
            "transcriptSha256": hashlib.sha256(transcript_path.read_bytes()).hexdigest(),
        },
    }
    attestation_path = repo / "attestation.json"
    attestation_path.write_text(json.dumps(payload), encoding="utf-8")
    return repo, attestation_path, payload


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_rehearsal_proves_annotated_tag_branch_start_and_no_mutation(tmp_path: Path) -> None:
    repo, attestation, _ = _fixture(tmp_path)
    result = rehearse(repo, attestation)
    assert result["result"] == "PASS"
    assert result["annotatedTagObject"] != result["peeledCommit"]
    assert result["attestedBranchStart"] == result["peeledCommit"]
    assert result["repositoryFingerprintBefore"] == result["repositoryFingerprintAfter"]
    assert result["repositoryMutation"] is False
    assert result["runtimeAccess"] is False
    assert result["runtimeMutation"] is False
    assert result["isolation"] == "DISPOSABLE_GIT_ARCHIVE"


def test_rehearsal_fails_closed_when_tag_is_missing(tmp_path: Path) -> None:
    repo, attestation, _ = _fixture(tmp_path)
    _git(repo, "tag", "-d", "safety/v3-start")
    with pytest.raises(RollbackAttestationError, match="git observation failed"):
        rehearse(repo, attestation)


def test_rehearsal_fails_closed_when_tag_object_moves(tmp_path: Path) -> None:
    repo, attestation, _ = _fixture(tmp_path)
    _git(repo, "tag", "-f", "-a", "safety/v3-start", "-m", "moved", "HEAD")
    with pytest.raises(RollbackAttestationError, match="annotated tag object moved"):
        rehearse(repo, attestation)


@pytest.mark.parametrize("field", ["peeledCommit", "attestedStartCommit"])
def test_rehearsal_fails_closed_on_wrong_peel_or_branch_start(
    tmp_path: Path, field: str
) -> None:
    repo, attestation, payload = _fixture(tmp_path)
    if field == "peeledCommit":
        safety_tag = payload["safetyTag"]
        assert isinstance(safety_tag, dict)
        safety_tag[field] = "0" * 40
    else:
        branch = payload["migrationBranch"]
        assert isinstance(branch, dict)
        branch[field] = "0" * 40
    _write(attestation, payload)
    with pytest.raises(RollbackAttestationError):
        rehearse(repo, attestation)


def test_rehearsal_rejects_unsafe_instructions(tmp_path: Path) -> None:
    repo, attestation, payload = _fixture(tmp_path)
    instructions = payload["rollbackInstructions"]
    assert isinstance(instructions, dict)
    instructions["operatorNote"] = "Reset the source repository before inspection."
    _write(attestation, payload)
    with pytest.raises(RollbackAttestationError, match="unsafe rollback instruction"):
        rehearse(repo, attestation)


def test_rehearsal_rejects_transcript_digest_mismatch(tmp_path: Path) -> None:
    repo, attestation, _ = _fixture(tmp_path)
    (repo / "transcript.json").write_text('{"result":"TAMPERED"}\n', encoding="utf-8")
    with pytest.raises(RollbackAttestationError, match="transcript digest mismatch"):
        rehearse(repo, attestation)
