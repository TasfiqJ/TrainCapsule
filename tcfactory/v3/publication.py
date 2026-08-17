"""Crash-safe V3.1 automated pull-request publication.

This module deliberately knows only the independent verifier's public receipt and
check-authorization wire formats.  It cannot import or execute private oracle logic.
"""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, NoReturn, Protocol, cast

from pydantic import AwareDatetime, Field, model_validator

from tcfactory.gates import run_private_gate
from tcfactory.gitops import current_sha
from tcfactory.util import (
    read_json,
    redact_sensitive,
    run_command,
    sanitized_subprocess_env,
    sha256_file,
    write_json,
)
from tcfactory.v3.base import DIGEST_PATTERN, SHA_PATTERN, V3Model
from tcfactory.v3.candidate_freeze import (
    CandidateFreezeError,
    FrozenCandidate,
    assert_frozen_candidate,
    quarantine_tainted_evidence,
)
from tcfactory.v3.candidate_manifest import CandidateManifest
from tcfactory.v3.contracts_v31 import ActivationReceiptV31, MachinePolicyReceiptV31
from tcfactory.v3.private_gate import (
    PRIVATE_GATE_PUBLIC_KEY,
    PRIVATE_GATE_RUNNER,
    PrivateGateVerificationError,
    validate_private_gate_installation,
    verify_private_gate_receipt,
)

_BRANCH = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._/-]{0,126}[A-Za-z0-9])?$")
_WORK_ITEM = re.compile(r"^V3-[A-Z]+-[0-9]{3}$")
MACHINE_POLICY_CHECK = "TrainCapsule / Machine policy"


def _default_candidate_freezer(
    path: Path, candidate_sha: str, candidate_tree_sha: str
) -> FrozenCandidate:
    return assert_frozen_candidate(
        path,
        expected_candidate_sha=candidate_sha,
        expected_candidate_tree_sha=candidate_tree_sha,
    )


class PublicationError(RuntimeError):
    """A publication invariant was not satisfied."""


class PublicationCredentialUnavailable(PublicationError):
    """The non-interactive publication identity is absent or no longer valid."""


class PublicationPending(PublicationError):
    """A required external observation has not completed yet."""


def trusted_external_path(
    path: Path, *, directory: bool, label: str
) -> tuple[Path, os.stat_result]:
    """Resolve one externally administered path without accepting writable/symlink ancestry."""

    absolute = Path(os.path.abspath(path))
    resolved = absolute.resolve(strict=True)
    if absolute != resolved:
        raise PublicationError(f"{label} path or ancestor must not be a symlink")
    observed = resolved.lstat()
    expected_type = stat.S_ISDIR(observed.st_mode) if directory else stat.S_ISREG(observed.st_mode)
    if not expected_type:
        kind = "directory" if directory else "regular file"
        raise PublicationError(f"{label} must be a {kind}")
    if os.name != "nt":
        for anchored in (resolved, *resolved.parents):
            anchored_stat = anchored.lstat()
            if anchored_stat.st_uid != 0 or anchored_stat.st_mode & 0o022:
                raise PublicationError(
                    f"{label} and every ancestor must be root-owned and not group/world-writable"
                )
    return resolved, observed


class PublicationPhase(StrEnum):
    PREPARED = "PREPARED"
    BRANCH_PUSHED = "BRANCH_PUSHED"
    PR_OPEN = "PR_OPEN"
    CHECKS_PENDING = "CHECKS_PENDING"
    POLICY_PENDING = "POLICY_PENDING"
    READY_TO_MERGE = "READY_TO_MERGE"
    AUTO_MERGE_REQUESTED = "AUTO_MERGE_REQUESTED"
    MERGED = "MERGED"
    MAIN_VERIFIED = "MAIN_VERIFIED"
    INVARIANTS_VERIFIED = "INVARIANTS_VERIFIED"
    REVERT_REQUIRED = "REVERT_REQUIRED"
    REVERT_BRANCH_PUSHED = "REVERT_BRANCH_PUSHED"
    REVERT_PR_OPEN = "REVERT_PR_OPEN"
    REVERT_CHECKS_PENDING = "REVERT_CHECKS_PENDING"
    REVERT_POLICY_PENDING = "REVERT_POLICY_PENDING"
    REVERT_MERGE_REQUESTED = "REVERT_MERGE_REQUESTED"
    REVERTED = "REVERTED"
    FAILED = "FAILED"
    HARD_STUCK = "HARD_STUCK"


class CheckObservation(V3Model):
    name: str = Field(min_length=1, max_length=200)
    head_sha: str = Field(pattern=SHA_PATTERN.pattern)
    app_id: int = Field(ge=1)
    event: Literal["pull_request", "merge_group", "push"]
    status: Literal["queued", "in_progress", "completed"]
    conclusion: str | None = None
    url: str | None = None


class PullRequestObservation(V3Model):
    number: int = Field(ge=1)
    url: str = Field(pattern=r"^https://github\.com/.+/pull/[1-9][0-9]*$")
    base_branch: Literal["main"] = "main"
    base_sha: str = Field(pattern=SHA_PATTERN.pattern)
    head_branch: str
    head_sha: str = Field(pattern=SHA_PATTERN.pattern)
    state: Literal["OPEN", "CLOSED", "MERGED"]
    is_draft: bool
    auto_merge_enabled: bool = False
    merge_queue_entry_id: str | None = None
    merged_sha: str | None = Field(default=None, pattern=SHA_PATTERN.pattern)


class PublicCheckAuthorization(V3Model):
    """Exact public output emitted by the independent receipt verifier."""

    schema_version: Literal["3.1"] = "3.1"
    check_name: Literal["TrainCapsule / Machine policy"]
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    conclusion: Literal["success"]
    receipt_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    receipt_digest: str = Field(pattern=DIGEST_PATTERN.pattern)


class AuthorizedReceipt(V3Model):
    authorization: PublicCheckAuthorization
    receipt: MachinePolicyReceiptV31


class PublicActivationAuthorization(V3Model):
    schema_version: Literal["3.1"] = "3.1"
    verified: Literal[True]
    verified_main_sha: str = Field(pattern=SHA_PATTERN.pattern)
    activation_receipt_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    activation_receipt_digest: str = Field(pattern=DIGEST_PATTERN.pattern)


class PublicationTransaction(V3Model):
    schema_version: Literal["3.1"] = "3.1"
    transaction_id: str = Field(pattern=r"^PRPUB-[A-Z0-9_-]+$")
    work_item_id: str = Field(pattern=_WORK_ITEM.pattern)
    base_sha: str = Field(pattern=SHA_PATTERN.pattern)
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    candidate_tree_sha: str = Field(pattern=SHA_PATTERN.pattern)
    candidate_worktree: str = Field(min_length=1)
    candidate_branch: str
    candidate_manifest_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    expected_machine_policy_receipt_id: str | None = None
    expected_machine_policy_receipt_digest: str | None = Field(
        default=None, pattern=DIGEST_PATTERN.pattern
    )
    expected_release_authorization_envelope_digest: str | None = Field(
        default=None, pattern=DIGEST_PATTERN.pattern
    )
    phase: PublicationPhase
    pull_request_number: int | None = Field(default=None, ge=1)
    pull_request_url: str | None = None
    receipt_id: str | None = None
    receipt_digest: str | None = Field(default=None, pattern=DIGEST_PATTERN.pattern)
    merged_main_sha: str | None = Field(default=None, pattern=SHA_PATTERN.pattern)
    merged_main_tree_sha: str | None = Field(default=None, pattern=SHA_PATTERN.pattern)
    revert_sha: str | None = Field(default=None, pattern=SHA_PATTERN.pattern)
    revert_branch: str | None = None
    revert_pull_request_number: int | None = Field(default=None, ge=1)
    revert_pull_request_url: str | None = None
    revert_receipt_id: str | None = None
    revert_receipt_digest: str | None = Field(default=None, pattern=DIGEST_PATTERN.pattern)
    reverted_main_sha: str | None = Field(default=None, pattern=SHA_PATTERN.pattern)
    failure_reason: str | None = None
    attempt: int = Field(default=1, ge=1, le=20)
    maximum_attempts: int = Field(default=5, ge=1, le=20)
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def coherent(self) -> PublicationTransaction:
        if self.updated_at < self.created_at or self.attempt > self.maximum_attempts:
            raise ValueError("publication timestamps or retry budget are inconsistent")
        if self.pull_request_number is None and self.pull_request_url is not None:
            raise ValueError("pull-request URL requires a number")
        if self.phase not in {
            PublicationPhase.PREPARED,
            PublicationPhase.BRANCH_PUSHED,
            PublicationPhase.FAILED,
            PublicationPhase.HARD_STUCK,
        } and (self.pull_request_number is None or self.pull_request_url is None):
            raise ValueError("opened publication phase requires a pull request")
        if (self.receipt_id is None) != (self.receipt_digest is None):
            raise ValueError("receipt identity and digest must be recorded together")
        if (self.expected_machine_policy_receipt_id is None) != (
            self.expected_machine_policy_receipt_digest is None
        ):
            raise ValueError("expected receipt identity and digest must be recorded together")
        if (
            self.phase
            in {
                PublicationPhase.MERGED,
                PublicationPhase.MAIN_VERIFIED,
                PublicationPhase.INVARIANTS_VERIFIED,
                PublicationPhase.REVERT_REQUIRED,
                PublicationPhase.REVERT_BRANCH_PUSHED,
                PublicationPhase.REVERT_PR_OPEN,
                PublicationPhase.REVERT_CHECKS_PENDING,
                PublicationPhase.REVERT_POLICY_PENDING,
                PublicationPhase.REVERT_MERGE_REQUESTED,
                PublicationPhase.REVERTED,
            }
            and self.merged_main_sha is None
        ):
            raise ValueError("post-merge phase requires the exact merged-main SHA")
        return self

    @property
    def terminal(self) -> bool:
        return self.phase in {
            PublicationPhase.INVARIANTS_VERIFIED,
            PublicationPhase.REVERTED,
            PublicationPhase.FAILED,
            PublicationPhase.HARD_STUCK,
        }


class ReceiptAuthorizer(Protocol):
    def authorize(
        self,
        receipt_path: Path,
        *,
        candidate_sha: str,
        candidate_tree_sha: str,
        base_sha: str,
        work_item_id: str,
        candidate_manifest_digest: str,
    ) -> AuthorizedReceipt: ...


class PublicationClient(Protocol):
    def remote_branch_sha(self, branch: str) -> str | None: ...

    def push_candidate_branch(self, *, sha: str, branch: str) -> None: ...

    def find_pull_request(
        self, *, head_branch: str, base_branch: str, marker: str
    ) -> PullRequestObservation | None: ...

    def create_draft_pull_request(
        self, *, head_branch: str, base_branch: str, title: str, body: str
    ) -> PullRequestObservation: ...

    def pull_request(self, number: int) -> PullRequestObservation: ...

    def checks(
        self, *, sha: str, pull_request_number: int | None
    ) -> Sequence[CheckObservation]: ...

    def mark_ready(self, *, number: int, expected_head_sha: str) -> None: ...

    def enable_auto_merge(self, *, number: int, expected_head_sha: str) -> None: ...

    def close_pull_request(self, *, number: int, reason: str) -> None: ...

    def commit_tree_sha(self, sha: str) -> str: ...

    def create_revert_commit(self, *, merged_sha: str, base_sha: str, message: str) -> str: ...


def _safe_branch(branch: str, *, prefix: str, allow_main: bool = False) -> str:
    invalid = (
        not _BRANCH.fullmatch(branch)
        or ".." in branch
        or "//" in branch
        or "@{" in branch
        or branch.endswith(".lock")
        or branch.startswith("/")
        or branch.endswith("/")
    )
    if (
        invalid
        or (branch == "main" and not allow_main)
        or (not allow_main and not branch.startswith(prefix))
    ):
        raise PublicationError(f"unsafe or prohibited publication branch: {branch!r}")
    return branch


class ExternalReceiptAuthorizer:
    """Invoke a separately installed public verifier client and validate its public output."""

    def __init__(self, executable: Path) -> None:
        self.executable, observed = trusted_external_path(
            executable, directory=False, label="receipt verifier"
        )
        self._executable_identity = (observed.st_dev, observed.st_ino)

    def authorize(
        self,
        receipt_path: Path,
        *,
        candidate_sha: str,
        candidate_tree_sha: str,
        base_sha: str,
        work_item_id: str,
        candidate_manifest_digest: str,
    ) -> AuthorizedReceipt:
        executable_now = self.executable.lstat()
        if (executable_now.st_dev, executable_now.st_ino) != self._executable_identity:
            raise PublicationError("receipt verifier identity changed after installation preflight")
        receipt_path, receipt_stat = trusted_external_path(
            receipt_path, directory=False, label="machine-policy receipt"
        )
        receipt_bytes = receipt_path.read_bytes()
        try:
            receipt = MachinePolicyReceiptV31.model_validate_json(
                receipt_bytes, strict=True
            )
        except ValueError as exc:
            raise PublicationError("machine-policy receipt is not valid JSON") from exc
        expected = {
            "candidate_sha": candidate_sha,
            "candidate_tree_sha": candidate_tree_sha,
            "base_sha": base_sha,
            "work_item_id": work_item_id,
            "candidate_manifest_digest": candidate_manifest_digest,
        }
        for field, value in expected.items():
            if getattr(receipt, field) != value:
                raise PublicationError(f"machine-policy receipt {field} mismatch")
        result = run_command(
            [
                str(self.executable),
                "verify-receipt",
                "--receipt",
                str(receipt_path.resolve(strict=True)),
                "--candidate-sha",
                candidate_sha,
                "--candidate-tree-sha",
                candidate_tree_sha,
                "--base-sha",
                base_sha,
                "--work-item-id",
                work_item_id,
                "--candidate-manifest-digest",
                candidate_manifest_digest,
            ],
            cwd=self.executable.parent,
            check=False,
            timeout=60,
            env=sanitized_subprocess_env(),
        )
        if result.returncode != 0:
            raise PublicationError("independent receipt verifier rejected the receipt")
        receipt_after = receipt_path.lstat()
        if (receipt_after.st_dev, receipt_after.st_ino) != (
            receipt_stat.st_dev,
            receipt_stat.st_ino,
        ) or receipt_path.read_bytes() != receipt_bytes:
            raise PublicationError("machine-policy receipt changed during verification")
        if len(result.stdout.encode()) > 65_536:
            raise PublicationError("independent receipt verifier output exceeded its bound")
        try:
            authorization = PublicCheckAuthorization.model_validate_json(
                result.stdout, strict=True
            )
        except ValueError as exc:
            raise PublicationError(
                "independent verifier returned an invalid public authorization"
            ) from exc
        actual_digest = receipt.canonical_digest()
        if (
            authorization.candidate_sha != candidate_sha
            or authorization.receipt_id != receipt.receipt_id
            or authorization.receipt_digest != actual_digest
        ):
            raise PublicationError("public check authorization is not bound to the exact receipt")
        return AuthorizedReceipt(authorization=authorization, receipt=receipt)

    def verify_activation(
        self,
        activation_path: Path,
        *,
        expected_main_sha: str,
        source_generation_id: str,
        source_generation_digest: str,
        controller_binary_digest: str,
        controller_config_digest: str,
    ) -> PublicActivationAuthorization:
        executable_now = self.executable.lstat()
        if (executable_now.st_dev, executable_now.st_ino) != self._executable_identity:
            raise PublicationError("receipt verifier identity changed after installation preflight")
        activation_path, observed = trusted_external_path(
            activation_path, directory=False, label="activation receipt"
        )
        raw_bytes = activation_path.read_bytes()
        try:
            receipt = ActivationReceiptV31.model_validate_json(raw_bytes, strict=True)
        except ValueError as exc:
            raise PublicationError("activation receipt contract is invalid") from exc
        expected = {
            "verified_main_sha": expected_main_sha,
            "source_generation_id": source_generation_id,
            "source_generation_digest": source_generation_digest,
            "controller_binary_digest": controller_binary_digest,
            "controller_config_digest": controller_config_digest,
        }
        for field, value in expected.items():
            if getattr(receipt, field) != value:
                raise PublicationError(f"activation receipt {field} mismatch")
        result = run_command(
            [
                str(self.executable),
                "verify-activation",
                "--receipt",
                str(activation_path.resolve(strict=True)),
                "--main-sha",
                expected_main_sha,
                "--source-generation-id",
                source_generation_id,
                "--source-generation-digest",
                source_generation_digest,
                "--controller-binary-digest",
                controller_binary_digest,
                "--controller-config-digest",
                controller_config_digest,
            ],
            cwd=self.executable.parent,
            check=False,
            timeout=60,
            env=sanitized_subprocess_env(),
        )
        observed_after = activation_path.lstat()
        if (
            result.returncode != 0
            or (observed_after.st_dev, observed_after.st_ino) != (observed.st_dev, observed.st_ino)
            or activation_path.read_bytes() != raw_bytes
        ):
            raise PublicationError("external verifier rejected or raced the activation receipt")
        if len(result.stdout.encode()) > 65_536:
            raise PublicationError("activation verifier output exceeded its bound")
        try:
            authorization = PublicActivationAuthorization.model_validate_json(
                result.stdout, strict=True
            )
        except ValueError as exc:
            raise PublicationError("activation verifier output has the wrong shape") from exc
        if (
            authorization.verified_main_sha != expected_main_sha
            or authorization.activation_receipt_id != receipt.receipt_id
            or authorization.activation_receipt_digest != receipt.canonical_digest()
        ):
            raise PublicationError("activation authorization is not bound to the exact receipt")
        return authorization


class GhPublicationClient:
    """Minimal GitHub transport; every mutating operation is PR-branch scoped."""

    def __init__(
        self, repo_root: Path, *, remote: str, repository: str, branch_prefix: str
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.remote = remote
        self.repository = repository
        self.branch_prefix = branch_prefix

    def _run(self, args: list[str]) -> Any:
        result = run_command(args, cwd=self.repo_root, check=False, timeout=300)
        if result.returncode != 0:
            error = redact_sensitive(str(result.stderr) or "GitHub command failed")
            normalized = error.casefold()
            credential_markers = (
                "gh auth login",
                "gh auth status",
                "not logged into any github hosts",
                "authentication required",
                "http 401",
                "bad credentials",
            )
            if args and args[0] == "gh" and any(
                marker in normalized for marker in credential_markers
            ):
                raise PublicationCredentialUnavailable(
                    "non-interactive GitHub publication credential is unavailable"
                )
            raise PublicationError(error)
        return result

    def _json(self, args: list[str]) -> object:
        result = self._run(args)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise PublicationError("GitHub returned invalid JSON") from exc

    def remote_branch_sha(self, branch: str) -> str | None:
        _safe_branch(branch, prefix=self.branch_prefix, allow_main=branch == "main")
        result = self._run(["git", "ls-remote", self.remote, f"refs/heads/{branch}"])
        line = result.stdout.strip()
        return line.split()[0] if line else None

    def push_candidate_branch(self, *, sha: str, branch: str) -> None:
        if not re.fullmatch(SHA_PATTERN, sha):
            raise PublicationError("publication source must be an exact commit SHA")
        _safe_branch(branch, prefix=self.branch_prefix)
        self._run(["git", "push", "--porcelain", self.remote, f"{sha}:refs/heads/{branch}"])

    @staticmethod
    def _pr(raw: Mapping[str, object]) -> PullRequestObservation:
        merged = raw.get("mergedAt") is not None or raw.get("state") == "MERGED"
        commit = raw.get("mergeCommit")
        commit_map = cast(dict[str, object], commit) if isinstance(commit, dict) else {}
        merged_sha_raw = commit_map.get("oid")
        merged_sha = merged_sha_raw if isinstance(merged_sha_raw, str) else None
        auto_merge = raw.get("autoMergeRequest")
        number = raw.get("number")
        url = raw.get("url")
        head_branch = raw.get("headRefName")
        head_sha = raw.get("headRefOid")
        base_branch = raw.get("baseRefName")
        base_sha = raw.get("baseRefOid")
        state_raw = "MERGED" if merged else raw.get("state")
        is_draft = raw.get("isDraft", False)
        if (
            not isinstance(number, int)
            or not isinstance(url, str)
            or not isinstance(head_branch, str)
            or not isinstance(head_sha, str)
            or base_branch != "main"
            or not isinstance(base_sha, str)
            or state_raw not in {"OPEN", "CLOSED", "MERGED"}
            or not isinstance(is_draft, bool)
        ):
            raise PublicationError("GitHub pull-request fields have invalid types")
        return PullRequestObservation(
            number=number,
            url=url,
            base_branch="main",
            head_branch=head_branch,
            head_sha=head_sha,
            base_sha=base_sha,
            state=cast(Literal["OPEN", "CLOSED", "MERGED"], state_raw),
            is_draft=is_draft,
            auto_merge_enabled=auto_merge is not None,
            merge_queue_entry_id=cast(str | None, raw.get("mergeQueueEntryId")),
            merged_sha=merged_sha,
        )

    def find_pull_request(
        self, *, head_branch: str, base_branch: str, marker: str
    ) -> PullRequestObservation | None:
        _safe_branch(head_branch, prefix=self.branch_prefix)
        raw = self._json(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                self.repository,
                "--state",
                "all",
                "--head",
                head_branch,
                "--base",
                base_branch,
                "--limit",
                "10",
                "--json",
                "number,url,state,isDraft,headRefName,headRefOid,baseRefName,baseRefOid,"
                "mergedAt,mergeCommit,autoMergeRequest,body",
            ]
        )
        if not isinstance(raw, list):
            raise PublicationError("GitHub pull-request listing has the wrong shape")
        matches: list[dict[str, object]] = []
        for item in cast(list[object], raw):
            if not isinstance(item, dict):
                continue
            candidate = cast(dict[str, object], item)
            if marker in str(candidate.get("body", "")):
                matches.append(candidate)
        if len(matches) > 1:
            raise PublicationError("multiple pull requests match one publication transaction")
        return self._pr(matches[0]) if matches else None

    def create_draft_pull_request(
        self, *, head_branch: str, base_branch: str, title: str, body: str
    ) -> PullRequestObservation:
        _safe_branch(head_branch, prefix=self.branch_prefix)
        self._run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                self.repository,
                "--draft",
                "--base",
                base_branch,
                "--head",
                head_branch,
                "--title",
                title,
                "--body",
                body,
            ]
        )
        found = self.find_pull_request(
            head_branch=head_branch, base_branch=base_branch, marker=body.splitlines()[0]
        )
        if found is None:
            raise PublicationError("created pull request could not be reconciled")
        return found

    def pull_request(self, number: int) -> PullRequestObservation:
        raw = self._json(
            [
                "gh",
                "pr",
                "view",
                str(number),
                "--repo",
                self.repository,
                "--json",
                "number,url,state,isDraft,headRefName,headRefOid,baseRefName,baseRefOid,"
                "mergedAt,mergeCommit,autoMergeRequest",
            ]
        )
        if not isinstance(raw, dict):
            raise PublicationError("GitHub pull-request observation has the wrong shape")
        return self._pr(cast(dict[str, object], raw))

    def checks(self, *, sha: str, pull_request_number: int | None) -> Sequence[CheckObservation]:
        raw = self._json(
            [
                "gh",
                "api",
                "--paginate",
                "-H",
                "Accept: application/vnd.github+json",
                f"repos/{self.repository}/commits/{sha}/check-runs?per_page=100",
            ]
        )
        if not isinstance(raw, dict):
            raise PublicationError("GitHub check-run observation has the wrong shape")
        raw_map = cast(dict[str, object], raw)
        check_runs = raw_map.get("check_runs")
        if not isinstance(check_runs, list):
            raise PublicationError("GitHub check-run observation has the wrong shape")
        observations: list[CheckObservation] = []
        for raw_item in cast(list[object], check_runs):
            item = cast(dict[str, object], raw_item) if isinstance(raw_item, dict) else None
            if not isinstance(item, dict):
                continue
            app_raw = item.get("app")
            suite_raw = item.get("check_suite")
            app = cast(dict[str, object], app_raw) if isinstance(app_raw, dict) else {}
            suite = cast(dict[str, object], suite_raw) if isinstance(suite_raw, dict) else {}
            prs_raw = item.get("pull_requests", suite.get("pull_requests", []))
            prs = cast(list[object], prs_raw) if isinstance(prs_raw, list) else []
            event: Literal["pull_request", "merge_group", "push"] = "push"
            if pull_request_number is not None and any(
                isinstance(pr, dict)
                and cast(dict[str, object], pr).get("number") == pull_request_number
                for pr in prs
            ):
                event = "pull_request"
            name = item.get("name")
            head_sha = item.get("head_sha")
            app_id = app.get("id")
            status = item.get("status")
            conclusion = item.get("conclusion")
            url = item.get("details_url")
            if (
                not isinstance(name, str)
                or not isinstance(head_sha, str)
                or not isinstance(app_id, int)
                or status not in {"queued", "in_progress", "completed"}
            ):
                raise PublicationError("GitHub check-run fields have invalid types")
            observations.append(
                CheckObservation(
                    name=name,
                    head_sha=head_sha,
                    app_id=app_id,
                    event=event,
                    status=cast(Literal["queued", "in_progress", "completed"], status),
                    conclusion=conclusion if isinstance(conclusion, str) else None,
                    url=url if isinstance(url, str) else None,
                )
            )
        return observations

    def mark_ready(self, *, number: int, expected_head_sha: str) -> None:
        observed = self.pull_request(number)
        if observed.head_sha != expected_head_sha:
            raise PublicationError("pull-request head changed before ready transition")
        if observed.is_draft:
            self._run(["gh", "pr", "ready", str(number), "--repo", self.repository])

    def enable_auto_merge(self, *, number: int, expected_head_sha: str) -> None:
        observed = self.pull_request(number)
        if observed.head_sha != expected_head_sha:
            raise PublicationError("pull-request head changed before auto-merge")
        if not observed.auto_merge_enabled and observed.state == "OPEN":
            self._run(
                ["gh", "pr", "merge", str(number), "--repo", self.repository, "--auto", "--squash"]
            )

    def close_pull_request(self, *, number: int, reason: str) -> None:
        observed = self.pull_request(number)
        if observed.state == "OPEN":
            self._run(
                [
                    "gh",
                    "pr",
                    "close",
                    str(number),
                    "--repo",
                    self.repository,
                    "--comment",
                    redact_sensitive(reason),
                ]
            )

    def commit_tree_sha(self, sha: str) -> str:
        result = self._run(["git", "rev-parse", f"{sha}^{{tree}}"])
        tree = result.stdout.strip()
        if not re.fullmatch(SHA_PATTERN, tree):
            raise PublicationError("commit tree observation is not an exact SHA")
        return tree

    def create_revert_commit(self, *, merged_sha: str, base_sha: str, message: str) -> str:
        tree = self.commit_tree_sha(base_sha)
        result = self._run(["git", "commit-tree", tree, "-p", merged_sha, "-m", message])
        sha = result.stdout.strip()
        if not re.fullmatch(SHA_PATTERN, sha):
            raise PublicationError("revert commit creation did not return an exact SHA")
        return sha


class AutomatedPRPublisher:
    """Automated exact-SHA PR publication with durable reconciliation and revert PRs."""

    def __init__(
        self,
        *,
        repo_root: Path,
        config: Any,
        transaction_root: Path,
        receipt_root: Path,
        quarantine_root: Path,
        client: PublicationClient,
        receipt_authorizer: ReceiptAuthorizer,
        git_root: Path | None = None,
        local_gate_command: tuple[str, ...] = ("bash", "scripts/gates/full_quality.sh"),
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        candidate_freezer: Callable[[Path, str, str], FrozenCandidate] | None = None,
        anchor_main_observer: Callable[[], str] | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.git_root = (git_root or repo_root).resolve()
        self.config = config
        self.transaction_root = transaction_root.resolve()
        self.receipt_root = receipt_root.resolve()
        self.quarantine_root = quarantine_root.resolve()
        self.client = client
        self.receipt_authorizer = receipt_authorizer
        self.local_gate_command = local_gate_command
        self.clock = clock
        self.candidate_freezer: Callable[[Path, str, str], FrozenCandidate] = (
            candidate_freezer or _default_candidate_freezer
        )
        self._prepared: dict[str, dict[str, str]] = {}
        self.anchor_main_observer = anchor_main_observer or (
            lambda: current_sha(self.git_root, "refs/heads/main")
        )
        if getattr(config, "publisher_capability", None) != "AUTOMATED_PR_V31_READY":
            raise PublicationError("automated PR publisher capability is not active")
        if getattr(config, "direct_main_push", True) is not False:
            raise PublicationError("direct main publication is forbidden")
        names = set(getattr(config.remote_ci, "required_workflows", []))
        if MACHINE_POLICY_CHECK not in names:
            raise PublicationError("independent machine-policy check is not required")
        trusted = getattr(config.remote_ci, "trusted_check_app_ids", {})
        if names != set(trusted):
            raise PublicationError("every required check must bind one trusted GitHub App ID")

    def _path(self, candidate_sha: str) -> Path:
        return self.transaction_root / f"{candidate_sha}.json"

    def _save(
        self, tx: PublicationTransaction, phase: PublicationPhase | None = None, **updates: object
    ) -> PublicationTransaction:
        values = {**updates, "updated_at": self.clock()}
        if phase is not None:
            values["phase"] = phase
        updated = tx.model_copy(update=values)
        updated = PublicationTransaction.model_validate(updated.model_dump(mode="python"))
        write_json(
            self._path(updated.candidate_sha), updated.model_dump(mode="json", by_alias=True)
        )
        return updated

    def _hard(self, tx: PublicationTransaction, reason: str) -> NoReturn:
        self._save(tx, PublicationPhase.HARD_STUCK, failure_reason=redact_sensitive(reason))
        raise PublicationError(f"publication is HARD_STUCK: {reason}")

    def _receipt_path(self, work_item_id: str, sha: str) -> Path:
        return self.receipt_root / "machine-policy" / work_item_id / f"{sha}.json"

    def _assert_transaction_candidate_frozen(self, tx: PublicationTransaction) -> None:
        try:
            self.candidate_freezer(
                Path(tx.candidate_worktree), tx.candidate_sha, tx.candidate_tree_sha
            )
        except CandidateFreezeError as exc:
            self._hard(tx, f"candidate freeze invariant failed: {exc}")

    def prepare_candidate(
        self, *, item: Any, candidate_sha: str, candidate_worktree: Path
    ) -> Mapping[str, Path]:
        try:
            frozen = assert_frozen_candidate(
                candidate_worktree, expected_candidate_sha=candidate_sha
            )
        except CandidateFreezeError as exc:
            raise PublicationError("candidate is not frozen before pre-promotion gates") from exc
        root = self.transaction_root / "pre-promotion" / str(item.work_item_id)
        local = run_command(
            list(self.local_gate_command), cwd=candidate_worktree, check=False, timeout=14_400
        )
        if local.returncode != 0:
            raise PublicationError("deterministic local gates failed")
        local_path = root / f"local-{candidate_sha}.json"
        local_payload = {
            "candidateSha": candidate_sha,
            "outputDigest": "sha256:"
            + __import__("hashlib")
            .sha256(((local.stdout or "") + "\n" + (local.stderr or "")).encode())
            .hexdigest(),
        }
        write_json(local_path, local_payload)
        try:
            self.candidate_freezer(
                candidate_worktree, candidate_sha, frozen.candidate_tree_sha
            )
        except CandidateFreezeError as exc:
            quarantine_tainted_evidence(
                {"deterministic-local": local_path},
                quarantine_root=self.quarantine_root / candidate_sha / "candidate-mutated",
                reason=str(exc),
            )
            raise PublicationError("deterministic gate mutated the frozen candidate") from exc
        private_evidence: dict[str, Path] = {"deterministic-local": local_path}
        try:
            runner, public_key = validate_private_gate_installation(
                self.repo_root, runner=PRIVATE_GATE_RUNNER, public_key=PRIVATE_GATE_PUBLIC_KEY
            )
            private_root = root / "private"
            private_root.mkdir(parents=True, exist_ok=True)
            receipt = private_root / f"{candidate_sha}.receipt.json"
            signature = private_root / f"{candidate_sha}.receipt.json.sig"
            result = run_private_gate(
                runner=runner,
                suite="full-release",
                cwd=candidate_worktree,
                repo_root=self.repo_root,
                artifact_dir=private_root,
                timeout_seconds=14_400,
                task_id=str(item.work_item_id),
                run_id=f"publish-{candidate_sha[:12]}",
                candidate_sha=candidate_sha,
                receipt_path=receipt,
                signature_path=signature,
            )
            private_evidence.update(
                {
                "deterministic-local": local_path,
                "private-gate-receipt": receipt,
                "private-gate-signature": signature,
                "private-gate-result": Path(result.stdout_path),
                }
            )
            try:
                self.candidate_freezer(
                    candidate_worktree, candidate_sha, frozen.candidate_tree_sha
                )
            except CandidateFreezeError as exc:
                quarantine_tainted_evidence(
                    private_evidence,
                    quarantine_root=self.quarantine_root / candidate_sha / "candidate-mutated",
                    reason=str(exc),
                )
                raise PublicationError("private gate mutated the frozen candidate") from exc
            if not result.passed:
                raise PublicationError("configured private pre-promotion gate failed")
            verified = verify_private_gate_receipt(
                repo_root=self.repo_root,
                runner=runner,
                public_key=public_key,
                receipt_path=receipt,
                signature_path=signature,
                result_path=Path(result.stdout_path),
                expected_candidate_sha=candidate_sha,
                expected_work_item_id=str(item.work_item_id),
            )
            self.candidate_freezer(
                candidate_worktree, candidate_sha, frozen.candidate_tree_sha
            )
        except PrivateGateVerificationError as exc:
            raise PublicationError("mandatory private pre-promotion gate rejected") from exc
        except CandidateFreezeError as exc:
            quarantine_tainted_evidence(
                private_evidence,
                quarantine_root=self.quarantine_root / candidate_sha / "candidate-mutated",
                reason=str(exc),
            )
            raise PublicationError("private gate verification tainted the candidate") from exc
        private_path = root / f"private-{candidate_sha}.json"
        write_json(
            private_path, {"candidateSha": candidate_sha, "runnerDigest": verified.runner_digest}
        )
        try:
            self.candidate_freezer(
                candidate_worktree, candidate_sha, frozen.candidate_tree_sha
            )
        except CandidateFreezeError as exc:
            quarantine_tainted_evidence(
                {
                    **private_evidence,
                    "configured-private": private_path,
                },
                quarantine_root=self.quarantine_root / candidate_sha / "candidate-mutated",
                reason=str(exc),
            )
            raise PublicationError("pre-promotion evidence was tainted by mutation") from exc
        self._prepared[candidate_sha] = {
            "deterministic-local": f"sha256:{sha256_file(local_path)}",
            "configured-private": f"sha256:{sha256_file(private_path)}",
        }
        return {
            "deterministic-local": local_path,
            "configured-private": private_path,
            "private-gate-receipt": receipt,
            "private-gate-signature": signature,
            "private-gate-result": Path(result.stdout_path),
        }

    def _verify_checks(
        self, sha: str, pr: int | None, *, post_merge: bool = False
    ) -> Literal["pass", "pending", "fail"]:
        observations = self.client.checks(sha=sha, pull_request_number=pr)
        trusted: Mapping[str, int] = self.config.remote_ci.trusted_check_app_ids
        states: list[str] = []
        roster = (
            self.config.remote_ci.post_merge_required_workflows
            if post_merge
            else self.config.remote_ci.required_workflows
        )
        for name in roster:
            matches = [
                check
                for check in observations
                if check.name == name
                and check.head_sha == sha
                and check.app_id == trusted[name]
                and check.event in ({"push"} if post_merge else {"pull_request", "merge_group"})
            ]
            if not matches:
                states.append("pending")
            elif any(
                check.status == "completed" and check.conclusion != "success" for check in matches
            ):
                states.append("fail")
            elif any(
                check.status == "completed" and check.conclusion == "success" for check in matches
            ):
                states.append("pass")
            else:
                states.append("pending")
        return (
            "fail"
            if "fail" in states
            else "pass"
            if all(state == "pass" for state in states)
            else "pending"
        )

    def _authorize(
        self, tx: PublicationTransaction, *, sha: str, manifest_digest: str
    ) -> AuthorizedReceipt:
        return self.receipt_authorizer.authorize(
            self._receipt_path(tx.work_item_id, sha),
            candidate_sha=sha,
            candidate_tree_sha=self.client.commit_tree_sha(sha),
            base_sha=tx.base_sha,
            work_item_id=tx.work_item_id,
            candidate_manifest_digest=manifest_digest,
        )

    def _pr(self, tx: PublicationTransaction, *, revert: bool = False) -> PullRequestObservation:
        number = tx.revert_pull_request_number if revert else tx.pull_request_number
        expected = tx.revert_sha if revert else tx.candidate_sha
        branch = tx.revert_branch if revert else tx.candidate_branch
        if number is None or expected is None or branch is None:
            return cast(
                PullRequestObservation, self._hard(tx, "publication PR identity is incomplete")
            )
        observed = self.client.pull_request(number)
        expected_base = tx.merged_main_sha if revert else tx.base_sha
        if (
            observed.head_sha != expected
            or observed.head_branch != branch
            or observed.base_branch != "main"
            or observed.base_sha != expected_base
        ):
            return cast(PullRequestObservation, self._hard(tx, "pull-request identity changed"))
        return observed

    def _premerge_fail(self, tx: PublicationTransaction, reason: str) -> PublicationTransaction:
        if tx.pull_request_number is not None:
            self.client.close_pull_request(number=tx.pull_request_number, reason=reason)
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        write_json(
            self.quarantine_root / f"{tx.work_item_id}-{tx.candidate_sha[:12]}.json",
            {
                "schemaVersion": "3.1",
                "workItemId": tx.work_item_id,
                "candidateSha": tx.candidate_sha,
                "reason": redact_sensitive(reason),
                "mainChanged": False,
                "recordedAt": self.clock().isoformat(),
            },
        )
        return self._save(tx, PublicationPhase.FAILED, failure_reason=redact_sensitive(reason))

    def reconcile_transaction(self, tx: PublicationTransaction) -> PublicationTransaction:
        if tx.phase is PublicationPhase.HARD_STUCK:
            raise PublicationError("publication transaction is HARD_STUCK")
        if tx.terminal:
            return tx
        before_merge = {
            PublicationPhase.PREPARED,
            PublicationPhase.BRANCH_PUSHED,
            PublicationPhase.PR_OPEN,
            PublicationPhase.CHECKS_PENDING,
            PublicationPhase.POLICY_PENDING,
            PublicationPhase.READY_TO_MERGE,
        }
        if tx.phase in before_merge and self.client.remote_branch_sha("main") != tx.base_sha:
            return self._premerge_fail(tx, "main moved from the receipt-bound base SHA")
        if tx.phase is PublicationPhase.PREPARED:
            if tx.expected_machine_policy_receipt_id is not None:
                try:
                    preauthorized = self._authorize(
                        tx,
                        sha=tx.candidate_sha,
                        manifest_digest=tx.candidate_manifest_digest,
                    )
                except (FileNotFoundError, PublicationPending):
                    return tx
                except PublicationError as exc:
                    return self._premerge_fail(tx, str(exc))
                if (
                    preauthorized.authorization.receipt_id
                    != tx.expected_machine_policy_receipt_id
                    or preauthorized.authorization.receipt_digest
                    != tx.expected_machine_policy_receipt_digest
                ):
                    return self._premerge_fail(
                        tx,
                        "publication receipt differs from the pre-authorized Phase 11 receipt",
                    )
                tx = self._save(
                    tx,
                    receipt_id=preauthorized.authorization.receipt_id,
                    receipt_digest=preauthorized.authorization.receipt_digest,
                )
                self._assert_transaction_candidate_frozen(tx)
            remote = self.client.remote_branch_sha(tx.candidate_branch)
            if remote is None:
                self._assert_transaction_candidate_frozen(tx)
                self.client.push_candidate_branch(sha=tx.candidate_sha, branch=tx.candidate_branch)
            elif remote != tx.candidate_sha:
                return self._hard(tx, "candidate branch already points to another SHA")
            tx = self._save(tx, PublicationPhase.BRANCH_PUSHED)
        if tx.phase is PublicationPhase.BRANCH_PUSHED:
            marker = f"<!-- {tx.transaction_id} -->"
            pr = self.client.find_pull_request(
                head_branch=tx.candidate_branch, base_branch="main", marker=marker
            )
            if pr is None:
                self._assert_transaction_candidate_frozen(tx)
                pr = self.client.create_draft_pull_request(
                    head_branch=tx.candidate_branch,
                    base_branch="main",
                    title=f"factory: {tx.work_item_id} {tx.candidate_sha[:12]}",
                    body=(
                        f"{marker}\nAutomated V3.1 exact-SHA candidate. "
                        "No human approval is requested."
                    ),
                )
            if pr.head_sha != tx.candidate_sha or pr.head_branch != tx.candidate_branch:
                return self._hard(tx, "created pull request does not bind the exact candidate")
            tx = self._save(
                tx, PublicationPhase.PR_OPEN, pull_request_number=pr.number, pull_request_url=pr.url
            )
        if tx.phase in {PublicationPhase.PR_OPEN, PublicationPhase.CHECKS_PENDING}:
            self._pr(tx)
            status = self._verify_checks(tx.candidate_sha, tx.pull_request_number)
            if status == "fail":
                return self._premerge_fail(tx, "required pre-merge check failed")
            if status == "pending":
                return self._save(tx, PublicationPhase.CHECKS_PENDING)
            tx = self._save(tx, PublicationPhase.POLICY_PENDING)
        if tx.phase is PublicationPhase.POLICY_PENDING:
            try:
                authorized = self._authorize(
                    tx, sha=tx.candidate_sha, manifest_digest=tx.candidate_manifest_digest
                )
            except (FileNotFoundError, PublicationPending):
                return tx
            except PublicationError as exc:
                return self._premerge_fail(tx, str(exc))
            if tx.expected_machine_policy_receipt_id is not None and (
                authorized.authorization.receipt_id
                != tx.expected_machine_policy_receipt_id
                or authorized.authorization.receipt_digest
                != tx.expected_machine_policy_receipt_digest
            ):
                return self._premerge_fail(
                    tx, "publication receipt differs from the pre-authorized Phase 11 receipt"
                )
            self._assert_transaction_candidate_frozen(tx)
            tx = self._save(
                tx,
                PublicationPhase.READY_TO_MERGE,
                receipt_id=authorized.authorization.receipt_id,
                receipt_digest=authorized.authorization.receipt_digest,
            )
        if tx.phase is PublicationPhase.READY_TO_MERGE:
            assert tx.pull_request_number is not None
            self._assert_transaction_candidate_frozen(tx)
            self.client.mark_ready(
                number=tx.pull_request_number, expected_head_sha=tx.candidate_sha
            )
            self._assert_transaction_candidate_frozen(tx)
            self.client.enable_auto_merge(
                number=tx.pull_request_number, expected_head_sha=tx.candidate_sha
            )
            tx = self._save(tx, PublicationPhase.AUTO_MERGE_REQUESTED)
        if tx.phase is PublicationPhase.AUTO_MERGE_REQUESTED:
            assert tx.pull_request_number is not None
            preview = self.client.pull_request(tx.pull_request_number)
            if preview.state == "OPEN" and self.client.remote_branch_sha("main") != tx.base_sha:
                return self._premerge_fail(
                    tx, "main moved while the automated pull request awaited merge"
                )
            pr = self._pr(tx)
            if pr.state == "CLOSED":
                return self._premerge_fail(tx, "pull request closed without merge")
            if pr.state != "MERGED" or pr.merged_sha is None:
                return tx
            tx = self._save(tx, PublicationPhase.MERGED, merged_main_sha=pr.merged_sha)
        if tx.phase is PublicationPhase.MERGED:
            assert tx.merged_main_sha is not None
            remote = self.client.remote_branch_sha("main")
            if remote != tx.merged_main_sha:
                return self._hard(tx, "remote main does not equal the exact merged PR SHA")
            # The controller's Git anchor has no remote or credentials.  A separate root-owned,
            # observed-main updater must import the verified commit and atomically advance main.
            # Until that happens this remains a durable active transaction and no completion or
            # post-merge assertion is possible.
            try:
                anchored_main = self.anchor_main_observer()
            except Exception:  # noqa: BLE001 - absence is a durable pending condition
                return tx
            if anchored_main != tx.merged_main_sha:
                return tx
            tx = self._save(
                tx,
                PublicationPhase.MAIN_VERIFIED,
                merged_main_tree_sha=self.client.commit_tree_sha(tx.merged_main_sha),
            )
        if tx.phase is PublicationPhase.MAIN_VERIFIED:
            assert tx.merged_main_sha is not None
            status = self._verify_checks(tx.merged_main_sha, None, post_merge=True)
            if status == "fail":
                tx = self._save(
                    tx,
                    PublicationPhase.REVERT_REQUIRED,
                    failure_reason="post-merge invariant check failed",
                )
            elif status == "pending":
                return tx
            else:
                return self._save(tx, PublicationPhase.INVARIANTS_VERIFIED)
        if tx.phase is PublicationPhase.REVERT_REQUIRED:
            assert tx.merged_main_sha is not None
            if tx.revert_sha is None or tx.revert_branch is None:
                revert_sha = self.client.create_revert_commit(
                    merged_sha=tx.merged_main_sha,
                    base_sha=tx.base_sha,
                    message=f"revert: quarantine {tx.work_item_id} {tx.candidate_sha[:12]}",
                )
                branch = (
                    f"{self.config.candidate_branch_prefix}revert/"
                    f"{tx.work_item_id.lower()}/{revert_sha[:12]}"
                )
                tx = self._save(
                    tx,
                    PublicationPhase.REVERT_REQUIRED,
                    revert_sha=revert_sha,
                    revert_branch=branch,
                )
            else:
                revert_sha = tx.revert_sha
                branch = tx.revert_branch
            remote = self.client.remote_branch_sha(branch)
            if remote is None:
                self.client.push_candidate_branch(sha=revert_sha, branch=branch)
            elif remote != revert_sha:
                return self._hard(tx, "revert branch already points to another SHA")
            tx = self._save(
                tx,
                PublicationPhase.REVERT_BRANCH_PUSHED,
                revert_sha=revert_sha,
                revert_branch=branch,
            )
        if tx.phase is PublicationPhase.REVERT_BRANCH_PUSHED:
            assert tx.revert_branch is not None and tx.revert_sha is not None
            marker = f"<!-- {tx.transaction_id}-REVERT -->"
            pr = self.client.find_pull_request(
                head_branch=tx.revert_branch, base_branch="main", marker=marker
            )
            if pr is None:
                pr = self.client.create_draft_pull_request(
                    head_branch=tx.revert_branch,
                    base_branch="main",
                    title=f"revert: {tx.work_item_id} {tx.candidate_sha[:12]}",
                    body=f"{marker}\nAutomated verified revert after post-merge invariant failure.",
                )
            if pr.head_sha != tx.revert_sha:
                return self._hard(tx, "revert pull request does not bind the exact revert SHA")
            tx = self._save(
                tx,
                PublicationPhase.REVERT_PR_OPEN,
                revert_pull_request_number=pr.number,
                revert_pull_request_url=pr.url,
            )
        if tx.phase in {PublicationPhase.REVERT_PR_OPEN, PublicationPhase.REVERT_CHECKS_PENDING}:
            assert tx.revert_sha is not None
            self._pr(tx, revert=True)
            status = self._verify_checks(tx.revert_sha, tx.revert_pull_request_number)
            if status == "fail":
                return self._hard(tx, "automatic revert pull request failed required checks")
            if status == "pending":
                return self._save(tx, PublicationPhase.REVERT_CHECKS_PENDING)
            tx = self._save(tx, PublicationPhase.REVERT_POLICY_PENDING)
        if tx.phase is PublicationPhase.REVERT_POLICY_PENDING:
            assert tx.revert_sha is not None
            try:
                authorized = self._authorize(
                    tx, sha=tx.revert_sha, manifest_digest=tx.candidate_manifest_digest
                )
            except (FileNotFoundError, PublicationPending):
                return tx
            except PublicationError as exc:
                return self._hard(tx, f"automatic revert policy rejected: {exc}")
            tx = self._save(
                tx,
                revert_receipt_id=authorized.authorization.receipt_id,
                revert_receipt_digest=authorized.authorization.receipt_digest,
            )
            assert tx.revert_pull_request_number is not None
            revert_sha = tx.revert_sha
            if revert_sha is None:
                return self._hard(tx, "revert policy phase lacks the exact revert SHA")
            self.client.mark_ready(
                number=tx.revert_pull_request_number, expected_head_sha=revert_sha
            )
            self.client.enable_auto_merge(
                number=tx.revert_pull_request_number, expected_head_sha=revert_sha
            )
            tx = self._save(tx, PublicationPhase.REVERT_MERGE_REQUESTED)
        if tx.phase is PublicationPhase.REVERT_MERGE_REQUESTED:
            pr = self._pr(tx, revert=True)
            if pr.state != "MERGED" or pr.merged_sha is None:
                return tx
            if self.client.remote_branch_sha("main") != pr.merged_sha:
                return self._hard(tx, "remote main does not equal the exact merged revert SHA")
            try:
                anchored_main = self.anchor_main_observer()
            except Exception:  # noqa: BLE001 - absence is a durable pending condition
                return tx
            if anchored_main != pr.merged_sha:
                return tx
            if self.client.commit_tree_sha(pr.merged_sha) != self.client.commit_tree_sha(
                tx.base_sha
            ):
                return self._hard(
                    tx, "merged revert tree does not restore the exact pre-publication tree"
                )
            return self._save(tx, PublicationPhase.REVERTED, reverted_main_sha=pr.merged_sha)
        return tx

    def reconcile_pending(self) -> list[PublicationTransaction]:
        results: list[PublicationTransaction] = []
        if not self.transaction_root.is_dir():
            return results
        for path in sorted(self.transaction_root.glob("*.json")):
            tx = PublicationTransaction.model_validate(read_json(path, {}))
            results.append(self.reconcile_transaction(tx))
        return results

    def publish(
        self,
        *,
        item: Any,
        candidate_ref: str,
        candidate_sha: str,
        candidate_worktree: Path,
        candidate_manifest_path: Path,
        packet_digest: str,
        source_digest: str,
        context_digest: str,
        checkpoint_digest: str,
        gate_digests: dict[str, str],
        expected_candidate_tree_sha: str,
        expected_machine_policy_receipt_id: str | None = None,
        expected_machine_policy_receipt_digest: str | None = None,
        expected_release_authorization_envelope_digest: str | None = None,
        lease_guard: Callable[[], None] | None = None,
    ) -> Mapping[str, object]:
        if lease_guard is None:
            raise PublicationError("publication requires an active lease guard")
        lease_guard()
        del source_digest
        path = self._path(candidate_sha)
        if path.is_file():
            tx = PublicationTransaction.model_validate(read_json(path, {}))
            if (
                tx.candidate_sha != candidate_sha
                or tx.work_item_id != str(item.work_item_id)
                or tx.candidate_manifest_digest != f"sha256:{sha256_file(candidate_manifest_path)}"
                or tx.candidate_tree_sha != expected_candidate_tree_sha
                or Path(tx.candidate_worktree).resolve() != candidate_worktree.resolve()
                or tx.expected_machine_policy_receipt_id
                != expected_machine_policy_receipt_id
                or tx.expected_machine_policy_receipt_digest
                != expected_machine_policy_receipt_digest
                or tx.expected_release_authorization_envelope_digest
                != expected_release_authorization_envelope_digest
            ):
                self._hard(tx, "publication retry identity or manifest changed")
        else:
            try:
                frozen = assert_frozen_candidate(
                    candidate_worktree,
                    expected_candidate_sha=candidate_sha,
                    expected_candidate_tree_sha=expected_candidate_tree_sha,
                )
            except CandidateFreezeError as exc:
                raise PublicationError("candidate is not frozen before publication") from exc
            if current_sha(self.git_root, candidate_ref) != candidate_sha:
                raise PublicationError(
                    "candidate ref/worktree does not match the exact candidate SHA"
                )
            manifest = CandidateManifest.model_validate(read_json(candidate_manifest_path, {}))
            if (
                manifest.candidate_sha != candidate_sha
                or manifest.candidate_tree_sha != expected_candidate_tree_sha
                or manifest.packet_digest != packet_digest
                or manifest.context_digest != context_digest
                or manifest.checkpoint_digest != checkpoint_digest
                or {gate.name: gate.evidence_digest for gate in manifest.gates} != gate_digests
            ):
                raise PublicationError("candidate manifest bindings changed before publication")
            if self._prepared.pop(candidate_sha, None) is None:
                raise PublicationError("candidate lacks exact-SHA pre-promotion gate evidence")
            work_item_id = str(item.work_item_id)
            branch = (
                f"{self.config.candidate_branch_prefix}{work_item_id.lower()}/{candidate_sha[:12]}"
            )
            _safe_branch(branch, prefix=self.config.candidate_branch_prefix)
            now = self.clock()
            tx = PublicationTransaction(
                transaction_id=(
                    f"PRPUB-{work_item_id.replace('-', '_')}-{candidate_sha[:12].upper()}"
                ),
                work_item_id=work_item_id,
                base_sha=manifest.base_sha,
                candidate_sha=candidate_sha,
                candidate_tree_sha=frozen.candidate_tree_sha,
                candidate_worktree=str(candidate_worktree.resolve()),
                candidate_branch=branch,
                candidate_manifest_digest=f"sha256:{sha256_file(candidate_manifest_path)}",
                expected_machine_policy_receipt_id=expected_machine_policy_receipt_id,
                expected_machine_policy_receipt_digest=expected_machine_policy_receipt_digest,
                expected_release_authorization_envelope_digest=(
                    expected_release_authorization_envelope_digest
                ),
                phase=PublicationPhase.PREPARED,
                maximum_attempts=self.config.retry_attempts,
                created_at=now,
                updated_at=now,
            )
            tx = self._save(tx)
        # Advance all immediately available phases, then yield a durable pending
        # transaction to the controller.  Hosted-check polling is a restart-safe
        # controller recheck, never a process-local sleep loop.
        while not tx.terminal:
            lease_guard()
            before = tx.phase
            tx = self.reconcile_transaction(tx)
            if tx.phase == before:
                break
        status = {
            PublicationPhase.INVARIANTS_VERIFIED: "MERGED_MAIN_VERIFIED",
            PublicationPhase.REVERTED: "REVERTED_MAIN_VERIFIED",
            PublicationPhase.FAILED: "REJECTED_BEFORE_MAIN",
            PublicationPhase.HARD_STUCK: "HARD_STUCK",
        }.get(tx.phase, "PENDING_REQUIRED_CHECKS")
        return {
            "status": status,
            "transactionId": tx.transaction_id,
            "candidateSha": tx.candidate_sha,
            "pullRequestNumber": tx.pull_request_number,
            "pullRequestUrl": tx.pull_request_url,
            "machinePolicyReceiptDigest": tx.receipt_digest,
            "mergedMainSha": tx.merged_main_sha,
            "phase": tx.phase.value,
        }
