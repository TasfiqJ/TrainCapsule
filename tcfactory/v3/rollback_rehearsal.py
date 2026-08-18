"""Fail-closed, read-only rollback rehearsal for V3-MIG-002."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any, cast


class RollbackAttestationError(RuntimeError):
    """The rollback attestation cannot be proven from the observed repository."""


_SAFE_OPERATIONS = (
    "VERIFY_ANNOTATED_TAG",
    "VERIFY_BRANCH_START",
    "EXPORT_ARCHIVE_TO_DISPOSABLE_DIRECTORY",
    "VERIFY_SNAPSHOT_INPUTS",
    "DISCARD_DISPOSABLE_DIRECTORY",
)
_UNSAFE_INSTRUCTION_TOKENS = (
    "checkout",
    "clean",
    "reset",
    "restore",
    "switch",
    "update-ref",
    "worktree add",
    "rm ",
)


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RollbackAttestationError(f"{label} must be a mapping")
    return cast(dict[str, Any], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RollbackAttestationError(f"{label} must be a non-empty string")
    return value


def _git(repo: Path, *args: str, binary: bool = False) -> str | bytes:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=not binary
        )
    except subprocess.CalledProcessError as exc:
        raise RollbackAttestationError(f"git observation failed: {' '.join(args)}") from exc
    return completed.stdout


def _repository_fingerprint(repo: Path) -> str:
    """Bind all refs, HEAD, index, and tracked worktree changes without writing."""

    parts: list[bytes] = []
    for args in (
        ("rev-parse", "HEAD"),
        ("for-each-ref", "--format=%(refname)%00%(objectname)%00%(objecttype)"),
        ("status", "--porcelain=v1", "-z", "--untracked-files=no"),
        ("ls-files", "--stage", "-z"),
    ):
        value = _git(repo, *args, binary=True)
        assert isinstance(value, bytes)
        parts.append(b"\x00".join(arg.encode("utf-8") for arg in args) + b"\x00" + value)
    return hashlib.sha256(b"\xff".join(parts)).hexdigest()


def _verify_instructions(attestation: dict[str, Any]) -> None:
    instructions = _mapping(attestation.get("rollbackInstructions"), "rollbackInstructions")
    operations = instructions.get("operations")
    if operations != list(_SAFE_OPERATIONS):
        raise RollbackAttestationError(
            "rollback instructions must be the exact read-only/disposable operation sequence"
        )
    prose = _text(instructions.get("operatorNote"), "rollbackInstructions.operatorNote")
    lowered = prose.casefold()
    token = next((item for item in _UNSAFE_INSTRUCTION_TOKENS if item in lowered), None)
    if token is not None:
        raise RollbackAttestationError(f"unsafe rollback instruction token: {token.strip()}")
    if instructions.get("mutatesRepository") is not False:
        raise RollbackAttestationError("rollback instructions must forbid repository mutation")
    if instructions.get("accessesRuntime") is not False:
        raise RollbackAttestationError("rollback instructions must forbid runtime access")


def _verify_transcript(repo: Path, attestation: dict[str, Any]) -> None:
    evidence = _mapping(attestation.get("evidence"), "evidence")
    relative = Path(_text(evidence.get("transcriptPath"), "evidence.transcriptPath"))
    if relative.is_absolute() or ".." in relative.parts:
        raise RollbackAttestationError("transcript path must stay inside the repository")
    path = repo / relative
    expected = _text(evidence.get("transcriptSha256"), "evidence.transcriptSha256")
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise RollbackAttestationError("transcriptSha256 must be a lowercase SHA-256")
    observed = hashlib.sha256(path.read_bytes()).hexdigest()
    if observed != expected:
        raise RollbackAttestationError(
            f"rollback transcript digest mismatch: observed {observed}, expected {expected}"
        )


def rehearse(repo: Path, attestation_path: Path) -> dict[str, object]:
    """Rehearse rollback in an exported archive and return deterministic evidence."""

    attestation = _mapping(
        json.loads(attestation_path.read_text(encoding="utf-8")), "V3-MIG-002 attestation"
    )
    if attestation.get("workItemId") != "V3-MIG-002":
        raise RollbackAttestationError("attestation is not bound to V3-MIG-002")
    _verify_instructions(attestation)
    _verify_transcript(repo, attestation)

    tag = _mapping(attestation.get("safetyTag"), "safetyTag")
    tag_name = _text(tag.get("name"), "safetyTag.name")
    tag_ref = f"refs/tags/{tag_name}"
    expected_tag_object = _text(tag.get("objectSha"), "safetyTag.objectSha")
    expected_peeled = _text(tag.get("peeledCommit"), "safetyTag.peeledCommit")
    observed_tag_object = str(_git(repo, "rev-parse", "--verify", tag_ref)).strip()
    if observed_tag_object != expected_tag_object:
        raise RollbackAttestationError(
            "annotated tag object moved: "
            f"observed {observed_tag_object}, expected {expected_tag_object}"
        )
    if str(_git(repo, "cat-file", "-t", tag_ref)).strip() != "tag":
        raise RollbackAttestationError("rollback safety ref must be an annotated tag object")
    observed_peeled = str(_git(repo, "rev-parse", "--verify", f"{tag_ref}^{{commit}}")).strip()
    if observed_peeled != expected_peeled:
        raise RollbackAttestationError(
            f"annotated tag peeled to {observed_peeled}, expected {expected_peeled}"
        )

    branch = _mapping(attestation.get("migrationBranch"), "migrationBranch")
    branch_ref = _text(branch.get("ref"), "migrationBranch.ref")
    expected_start = _text(branch.get("attestedStartCommit"), "migrationBranch.attestedStartCommit")
    if expected_start != expected_peeled:
        raise RollbackAttestationError("branch start must equal the immutable tag's peeled commit")
    branch_tip = str(_git(repo, "rev-parse", "--verify", branch_ref)).strip()
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", expected_start, branch_tip], cwd=repo, check=False
    )
    if ancestor.returncode != 0:
        raise RollbackAttestationError("attested branch start is not an ancestor of the branch tip")
    merge_base = str(_git(repo, "merge-base", expected_start, branch_tip)).strip()
    if merge_base != expected_start:
        raise RollbackAttestationError("migration branch does not start from the attested commit")

    before = _repository_fingerprint(repo)
    snapshot_path = Path(_text(attestation.get("snapshotPath"), "snapshotPath"))
    snapshot = _mapping(json.loads((repo / snapshot_path).read_text(encoding="utf-8")), "snapshot")
    baseline_start = _mapping(snapshot.get("startingState"), "snapshot.startingState")
    baseline_tag = _mapping(snapshot.get("safetyRef"), "snapshot.safetyRef")
    baseline_branch = _mapping(snapshot.get("workingBranch"), "snapshot.workingBranch")
    if (
        baseline_start.get("startingLocalHead") != expected_peeled
        or baseline_start.get("startingOriginMain") != expected_peeled
        or baseline_tag.get("name") != tag_name
        or baseline_tag.get("tagObjectSha") != expected_tag_object
        or baseline_tag.get("peeledCommitSha") != expected_peeled
        or baseline_branch.get("name") != branch_ref.removeprefix("refs/heads/")
        or baseline_branch.get("startingSha") != expected_start
    ):
        raise RollbackAttestationError(
            "V3.1 Phase-0 baseline is not bound to the attested tag, branch, and start commit"
        )
    raw_tracked_inputs: object = attestation.get("trackedInputs")
    if not isinstance(raw_tracked_inputs, list) or not raw_tracked_inputs:
        raise RollbackAttestationError("snapshot trackedInputs must be non-empty")
    tracked_inputs = cast(list[object], raw_tracked_inputs)

    with tempfile.TemporaryDirectory(prefix="traincapsule-v3-mig-002-") as temporary:
        temporary_root = Path(temporary)
        archive = temporary_root / "rollback.tar"
        with archive.open("wb") as output:
            completed = subprocess.run(
                ["git", "archive", "--format=tar", expected_peeled],
                cwd=repo,
                check=False,
                stdout=output,
                stderr=subprocess.PIPE,
            )
        if completed.returncode != 0:
            raise RollbackAttestationError("failed to export the attested rollback commit")
        export = temporary_root / "export"
        export.mkdir()
        with tarfile.open(archive, "r") as reader:
            reader.extractall(export, filter="data")
        for item in tracked_inputs:
            record = _mapping(item, "trackedInputs entry")
            relative = Path(_text(record.get("path"), "tracked input path"))
            expected_bytes: object = record.get("bytes")
            if not isinstance(expected_bytes, int) or isinstance(expected_bytes, bool):
                raise RollbackAttestationError(
                    f"tracked input byte count must be an integer: {relative}"
                )
            expected_digest = _text(record.get("sha256"), "tracked input sha256")
            blob = (export / relative).read_bytes()
            if len(blob) != expected_bytes:
                raise RollbackAttestationError(f"rollback byte-count mismatch: {relative}")
            if hashlib.sha256(blob).hexdigest() != expected_digest:
                raise RollbackAttestationError(f"rollback digest mismatch: {relative}")

    after = _repository_fingerprint(repo)
    if after != before:
        raise RollbackAttestationError("rollback rehearsal mutated repository state")
    return {
        "workItemId": "V3-MIG-002",
        "result": "PASS",
        "annotatedTagObject": observed_tag_object,
        "peeledCommit": observed_peeled,
        "attestedBranchStart": expected_start,
        "observedBranchTip": branch_tip,
        "repositoryFingerprintBefore": before,
        "repositoryFingerprintAfter": after,
        "trackedInputsVerified": len(tracked_inputs),
        "repositoryMutation": False,
        "runtimeAccess": False,
        "runtimeMutation": False,
        "isolation": "DISPOSABLE_GIT_ARCHIVE",
    }
