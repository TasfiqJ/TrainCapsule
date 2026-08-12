from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, NoReturn, cast

from pydantic import ConfigDict, Field, field_validator, model_validator

from .gates import run_private_gate
from .gitops import current_branch, current_sha, fast_forward_main
from .models import RiskTier, TaskPacket
from .util import read_json, redact_sensitive, run_command, sha256_file, write_json
from .v3.base import SHA_PATTERN, V3Model
from .v3.candidate_manifest import CandidateManifest
from .yamlutil import load_yaml

_BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._/-]{0,126}[A-Za-z0-9])?$")


class RemoteCIConfig(V3Model):
    enabled: bool = True
    required_workflows: list[str] = Field(
        default_factory=lambda: [
            "TrainCapsule / Factory quality",
            "TrainCapsule / Product unit",
            "TrainCapsule / Product contract",
            "TrainCapsule / Security",
            "TrainCapsule / Source-of-truth integrity",
        ],
        min_length=1,
    )
    required_risk_tiers: list[RiskTier] = Field(
        default_factory=lambda: [RiskTier.INTEGRATION, RiskTier.TRUST_CORE]
    )
    timeout_seconds: int = Field(default=1800, ge=60, le=14_400)
    poll_seconds: int = Field(default=20, ge=5, le=300)
    fail_closed: Literal[True] = True

    @field_validator("required_workflows")
    @classmethod
    def unique_workflows(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("required workflow names must be non-empty and unique")
        return normalized


class GitHubConfig(V3Model):
    version: Literal[3] = 3
    enabled: bool = False
    remote: Literal["origin"] = "origin"
    base_branch: Literal["main"] = "main"
    branch: Literal["main"] = "main"
    visibility: Literal["private"] = "private"
    repository: str | None = None
    release_mode: Literal["owner_directed_main_only"] = "owner_directed_main_only"
    direct_main_push: Literal[True] = True
    release_metadata_path: Literal["factory/state/latest-release.json"] = (
        "factory/state/latest-release.json"
    )
    push_after_verified_tasks: int = Field(default=3, ge=1, le=50)
    push_interval_seconds: int = Field(default=3600, ge=60, le=86_400)
    push_before_quota_pause: bool = True
    push_at_completion: bool = True
    immediate_risk_tiers: list[RiskTier] = Field(
        default_factory=lambda: [RiskTier.INTEGRATION, RiskTier.TRUST_CORE]
    )
    retry_attempts: int = Field(default=5, ge=1, le=10)
    retry_backoff_seconds: int = Field(default=30, ge=1, le=3600)
    verify_remote_sha: Literal[True] = True
    commit_subject_max_chars: int = Field(default=50, ge=20, le=72)
    remote_ci: RemoteCIConfig = Field(default_factory=RemoteCIConfig)


class GitHubSyncState(V3Model):
    model_config = ConfigDict(
        alias_generator=None,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    version: Literal[3] = 3
    tasks_since_push: int = 0
    last_push_at: datetime | None = None
    last_pushed_sha: str | None = None
    last_reason: str | None = None
    last_error: str | None = None
    pending: bool = False
    last_task_id: str | None = None
    last_task_risk: RiskTier | None = None
    last_required_workflow_status: Literal["pending", "pass", "fail"] | None = None


class RequiredWorkflow(V3Model):
    name: str
    status: Literal["missing", "queued", "in_progress", "completed"]
    conclusion: str | None = None
    url: str | None = None


class RequiredWorkflowStatus(V3Model):
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    release_branch: Literal["main"] = "main"
    status: Literal["pending", "pass", "fail"]
    workflows: list[RequiredWorkflow]


class GitHubReleaseMetadata(V3Model):
    version: Literal[3] = 3
    release_mode: Literal["owner_directed_main_only"] = "owner_directed_main_only"
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    publication_branch: Literal["main"] = "main"
    remote_main_sha: str = Field(pattern=SHA_PATTERN.pattern)
    status: Literal["PUBLISHED_MAIN_VERIFIED", "REVERTED_AND_QUARANTINED", "POST_PUSH_PENDING"]
    machine_policy_receipt: str
    revert_sha: str | None = Field(default=None, pattern=SHA_PATTERN.pattern)
    required_workflow_status: RequiredWorkflowStatus
    updated_at: datetime


class GitHubSyncError(RuntimeError):
    pass


class GitHubDivergenceError(GitHubSyncError):
    pass


class RemoteCIFailure(GitHubSyncError):
    pass


class MainOnlyMachineReceipt(V3Model):
    version: Literal[3] = 3
    policy: Literal["OWNER_DIRECTED_MAIN_ONLY"] = "OWNER_DIRECTED_MAIN_ONLY"
    work_item_id: str
    base_sha: str = Field(pattern=SHA_PATTERN.pattern)
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    candidate_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    packet_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    context_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    checkpoint_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    gate_digests: dict[str, str] = Field(min_length=1)
    owner_directives_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    local_gate_evidence: dict[str, str] = Field(min_length=1)
    private_gate_evidence: dict[str, str]
    created_at: datetime
    retry_budget: int = Field(ge=1, le=5)


PublicationPhase = Literal[
    "PREPARED",
    "LOCAL_PROMOTED",
    "REMOTE_PUSHED",
    "HOSTED_PENDING",
    "REVERT_REQUIRED",
    "REVERT_LOCAL",
    "REVERT_PUSHED",
    "VERIFIED",
    "REVERTED",
    "HARD_STUCK",
]


class MainPublicationTransaction(V3Model):
    """Crash-recoverable exact-SHA main publication transaction."""

    version: Literal[3] = 3
    transaction_id: str = Field(pattern=r"^MPUB-[A-Z0-9_-]+$")
    work_item_id: str
    base_sha: str = Field(pattern=SHA_PATTERN.pattern)
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    phase: PublicationPhase
    receipt_path: str
    machine_receipt: MainOnlyMachineReceipt
    revert_sha: str | None = Field(default=None, pattern=SHA_PATTERN.pattern)
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def receipt_matches_transaction(self) -> MainPublicationTransaction:
        if (
            self.machine_receipt.work_item_id != self.work_item_id
            or self.machine_receipt.base_sha != self.base_sha
            or self.machine_receipt.candidate_sha != self.candidate_sha
        ):
            raise ValueError("publication transaction and machine receipt identity mismatch")
        if self.phase in {"REVERT_LOCAL", "REVERT_PUSHED", "REVERTED"} and not self.revert_sha:
            raise ValueError("revert publication phase requires a revert SHA")
        return self

    @property
    def terminal(self) -> bool:
        return self.phase in {"VERIFIED", "REVERTED", "HARD_STUCK"}

    @property
    def final_sha(self) -> str | None:
        if self.phase == "VERIFIED":
            return self.candidate_sha
        if self.phase == "REVERTED":
            return self.revert_sha
        return None


class MainOnlyPublisher:
    """Exact-SHA main-only publication with automatic quarantine and revert."""

    def __init__(
        self,
        *,
        repo_root: Path,
        config: GitHubConfig,
        receipt_root: Path,
        quarantine_root: Path,
        local_gate_command: tuple[str, ...] = ("bash", "scripts/gates/full_quality.sh"),
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.config = config
        self.receipt_root = receipt_root.resolve()
        self.quarantine_root = quarantine_root.resolve()
        if not local_gate_command:
            raise ValueError("at least one deterministic local gate command is required")
        self.local_gate_command = local_gate_command
        self._prepared: dict[str, tuple[dict[str, str], dict[str, str]]] = {}

    def _transaction_root(self) -> Path:
        return self.receipt_root / "publication-transactions"

    def _transaction_path(self, candidate_sha: str) -> Path:
        return self._transaction_root() / f"{candidate_sha}.json"

    def _receipt_path(self, transaction: MainPublicationTransaction) -> Path:
        path = Path(transaction.receipt_path).expanduser().resolve()
        try:
            path.relative_to(self.receipt_root)
        except ValueError:
            self._hard_stop("publication receipt path escaped the trusted state root")
        return path

    def _save_transaction(
        self,
        transaction: MainPublicationTransaction,
        phase: PublicationPhase | None = None,
        **updates: object,
    ) -> MainPublicationTransaction:
        payload = {**updates, "updated_at": datetime.now(UTC)}
        if phase is not None:
            payload["phase"] = phase
        updated = transaction.model_copy(update=payload)
        write_json(
            self._transaction_path(updated.candidate_sha),
            updated.model_dump(mode="json", by_alias=True),
        )
        return updated

    def _refresh_migration_marker(
        self, *, transaction: MainPublicationTransaction, final_sha: str
    ) -> None:
        marker_path = self.quarantine_root.parent / "MIGRATION_COMPLETE_V3.json"
        if not marker_path.exists():
            return
        payload = read_json(marker_path, {})
        if not isinstance(payload, dict):
            self._hard_stop("migration marker became unreadable during publication")
        marker = cast(dict[str, Any], payload)
        current = marker.get("completedSha")
        allowed = {transaction.base_sha, transaction.candidate_sha, final_sha}
        if current not in allowed:
            self._hard_stop("migration marker SHA is ambiguous during publication recovery")
        manifest = self.repo_root / "docs/source-of-truth/v3-2026-08-11/FINAL_MANIFEST_V3.json"
        directives = self.repo_root / "config/owner_directives.yaml"
        if marker.get("sourceManifestSha256") != sha256_file(manifest):
            self._hard_stop("migration marker source digest changed during publication")
        if marker.get("ownerDirectivesSha256") != sha256_file(directives):
            self._hard_stop("migration marker owner-directive digest changed during publication")
        marker["completedSha"] = final_sha
        write_json(marker_path, marker)

    def _tree_sha(self, commit_sha: str) -> str:
        return current_sha(self.repo_root, f"{commit_sha}^{{tree}}")

    def _assert_revert_tree(self, transaction: MainPublicationTransaction, revert_sha: str) -> None:
        if self._tree_sha(revert_sha) != self._tree_sha(transaction.base_sha):
            self._hard_stop("automatic revert tree does not match the pre-promotion base")

    def _metadata_path(self) -> Path:
        path = Path(self.config.release_metadata_path)
        return path if path.is_absolute() else self.repo_root / path

    def _write_metadata(
        self,
        *,
        candidate_sha: str,
        remote_sha: str,
        status: Literal["PUBLISHED_MAIN_VERIFIED", "REVERTED_AND_QUARANTINED", "POST_PUSH_PENDING"],
        receipt_path: Path,
        workflows: RequiredWorkflowStatus,
        revert_sha: str | None = None,
    ) -> GitHubReleaseMetadata:
        metadata = GitHubReleaseMetadata(
            candidate_sha=candidate_sha,
            remote_main_sha=remote_sha,
            status=status,
            machine_policy_receipt=str(receipt_path),
            revert_sha=revert_sha,
            required_workflow_status=workflows,
            updated_at=datetime.now(UTC),
        )
        write_json(self._metadata_path(), metadata.model_dump(mode="json", by_alias=True))
        return metadata

    def prepare_candidate(
        self, *, item: Any, candidate_sha: str, candidate_worktree: Path
    ) -> dict[str, Path]:
        if current_sha(candidate_worktree) != candidate_sha:
            raise GitHubSyncError("candidate worktree does not match the exact candidate SHA")
        local = run_command(
            list(self.local_gate_command),
            cwd=candidate_worktree,
            check=False,
            timeout=14_400,
        )
        if local.returncode != 0:
            raise GitHubSyncError(_safe_error(local, "deterministic local gates failed"))
        local_evidence = {
            "candidateSha": candidate_sha,
            "command": " ".join(self.local_gate_command),
            "outputDigest": "sha256:"
            + hashlib.sha256(
                ((local.stdout or "") + "\n" + (local.stderr or "")).encode()
            ).hexdigest(),
        }
        gate_root = self.receipt_root / "pre-promotion" / str(item.work_item_id)
        local_path = gate_root / f"local-{candidate_sha}.json"
        write_json(local_path, local_evidence)
        evidence_paths = {"deterministic-local": local_path}
        private_evidence: dict[str, str] = {}
        private_runner_value = os.getenv("TCF_PRIVATE_GATE_RUNNER")
        if private_runner_value:
            private_artifacts = self.receipt_root / "private-gates" / str(item.work_item_id)
            result = run_private_gate(
                runner=Path(private_runner_value),
                suite="full-release",
                cwd=candidate_worktree,
                repo_root=self.repo_root,
                artifact_dir=private_artifacts,
                timeout_seconds=14_400,
                task_id=str(item.work_item_id),
                run_id=f"publish-{candidate_sha[:12]}",
                candidate_sha=candidate_sha,
            )
            if not result.passed:
                raise GitHubSyncError("configured private pre-promotion gate failed")
            private_evidence = {
                "candidateSha": candidate_sha,
                "suite": "full-release",
                "resultDigest": f"sha256:{sha256_file(Path(result.stdout_path))}",
            }
            private_path = gate_root / f"private-{candidate_sha}.json"
            write_json(private_path, private_evidence)
            evidence_paths["configured-private"] = private_path
        if current_sha(candidate_worktree) != candidate_sha:
            raise GitHubSyncError("pre-promotion gates mutated the exact candidate")
        self._prepared[candidate_sha] = (local_evidence, private_evidence)
        return evidence_paths

    def _push_main(self, sha: str) -> None:
        for attempt in range(1, self.config.retry_attempts + 1):
            result = run_command(
                ["git", "push", self.config.remote, f"{sha}:refs/heads/main"],
                cwd=self.repo_root,
                check=False,
                timeout=300,
            )
            if result.returncode == 0:
                return
            if attempt == self.config.retry_attempts:
                raise GitHubSyncError("finite main-only push retry budget exhausted")
            time.sleep(self.config.retry_backoff_seconds * attempt)

    def _create_local_revert(self, transaction: MainPublicationTransaction) -> str:
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        write_json(
            self.quarantine_root
            / f"{transaction.work_item_id}-{transaction.candidate_sha[:12]}.json",
            {
                "version": 3,
                "workItemId": transaction.work_item_id,
                "baseSha": transaction.base_sha,
                "candidateSha": transaction.candidate_sha,
                "reason": redact_sensitive(transaction.failure_reason or "hosted checks failed"),
                "automaticResume": False,
                "quarantinedAt": datetime.now(UTC).isoformat(),
            },
        )
        result = run_command(
            ["git", "read-tree", "--reset", "-u", f"{transaction.base_sha}^{{tree}}"],
            cwd=self.repo_root,
            check=False,
            timeout=300,
        )
        if result.returncode != 0:
            self._hard_stop("hosted CI failed and automatic revert tree restore failed")
        commit = run_command(
            [
                "git",
                "commit",
                "-m",
                f"revert: quarantine {transaction.work_item_id} {transaction.candidate_sha[:12]}",
            ],
            cwd=self.repo_root,
            check=False,
            timeout=300,
        )
        if commit.returncode != 0:
            self._hard_stop("hosted CI failed and automatic revert commit failed")
        revert_sha = current_sha(self.repo_root, "main")
        self._assert_revert_tree(transaction, revert_sha)
        return revert_sha

    def _complete_verified(
        self,
        transaction: MainPublicationTransaction,
        workflows: RequiredWorkflowStatus,
    ) -> MainPublicationTransaction:
        receipt_path = self._receipt_path(transaction)
        self._write_metadata(
            candidate_sha=transaction.candidate_sha,
            remote_sha=transaction.candidate_sha,
            status="PUBLISHED_MAIN_VERIFIED",
            receipt_path=receipt_path,
            workflows=workflows,
        )
        transaction = self._save_transaction(transaction, "VERIFIED")
        self._refresh_migration_marker(transaction=transaction, final_sha=transaction.candidate_sha)
        return transaction

    def _complete_reverted(
        self,
        transaction: MainPublicationTransaction,
        workflows: RequiredWorkflowStatus,
    ) -> MainPublicationTransaction:
        if transaction.revert_sha is None:
            self._hard_stop("revert completion lacks a durable revert SHA")
        revert_sha = transaction.revert_sha
        self._assert_revert_tree(transaction, revert_sha)
        self._write_metadata(
            candidate_sha=transaction.candidate_sha,
            remote_sha=revert_sha,
            status="REVERTED_AND_QUARANTINED",
            receipt_path=Path(transaction.receipt_path),
            workflows=workflows,
            revert_sha=revert_sha,
        )
        transaction = self._save_transaction(transaction, "REVERTED")
        self._refresh_migration_marker(transaction=transaction, final_sha=revert_sha)
        return transaction

    def _reconcile_transaction(
        self, transaction: MainPublicationTransaction
    ) -> MainPublicationTransaction:
        """Resume one durable publication without repeating a completed side effect."""

        if transaction.phase == "HARD_STUCK":
            raise RemoteCIFailure("publication transaction is HARD_STUCK")
        receipt_path = self._receipt_path(transaction)
        if receipt_path.exists():
            observed_receipt = MainOnlyMachineReceipt.model_validate(read_json(receipt_path, {}))
            if observed_receipt != transaction.machine_receipt:
                self._hard_stop("machine policy receipt changed during publication recovery")
        else:
            write_json(
                receipt_path,
                transaction.machine_receipt.model_dump(mode="json", by_alias=True),
            )
        if transaction.phase in {"VERIFIED", "REVERTED"}:
            final_sha = transaction.final_sha
            if final_sha is None:
                self._hard_stop("terminal publication transaction lacks a final SHA")
            if (
                current_sha(self.repo_root, "main") != final_sha
                or _remote_branch_sha(self.repo_root, self.config, "main") != final_sha
            ):
                self._hard_stop("terminal publication no longer matches exact local/remote main")
            if transaction.phase == "REVERTED":
                self._assert_revert_tree(transaction, final_sha)
            self._refresh_migration_marker(transaction=transaction, final_sha=final_sha)
            return transaction

        local_sha = current_sha(self.repo_root, "main")
        remote_sha = _remote_branch_sha(self.repo_root, self.config, "main")
        if remote_sha is None:
            self._hard_stop("origin/main is missing during publication recovery")

        if transaction.phase == "PREPARED":
            if (local_sha, remote_sha) == (transaction.base_sha, transaction.base_sha):
                fast_forward_main(
                    self.repo_root,
                    "main",
                    expected_base_sha=transaction.base_sha,
                    final_sha=transaction.candidate_sha,
                )
                local_sha = transaction.candidate_sha
            elif local_sha != transaction.candidate_sha or remote_sha not in {
                transaction.base_sha,
                transaction.candidate_sha,
            }:
                self._hard_stop("ambiguous PREPARED publication state")
            transaction = self._save_transaction(transaction, "LOCAL_PROMOTED")

        if transaction.phase == "LOCAL_PROMOTED":
            local_sha = current_sha(self.repo_root, "main")
            remote_sha = cast(str, _remote_branch_sha(self.repo_root, self.config, "main"))
            if local_sha != transaction.candidate_sha:
                self._hard_stop("local main changed during candidate push recovery")
            if remote_sha == transaction.base_sha:
                self._push_main(transaction.candidate_sha)
            elif remote_sha != transaction.candidate_sha:
                self._hard_stop("remote main diverged during candidate push recovery")
            transaction = self._save_transaction(transaction, "REMOTE_PUSHED")

        if transaction.phase in {"REMOTE_PUSHED", "HOSTED_PENDING"}:
            local_sha = current_sha(self.repo_root, "main")
            remote_sha = cast(str, _remote_branch_sha(self.repo_root, self.config, "main"))
            if (local_sha, remote_sha) != (
                transaction.candidate_sha,
                transaction.candidate_sha,
            ):
                self._hard_stop("candidate SHA is ambiguous before hosted-check recovery")
            pending = required_workflow_status(
                self.repo_root, self.config, transaction.candidate_sha, "main"
            )
            self._write_metadata(
                candidate_sha=transaction.candidate_sha,
                remote_sha=transaction.candidate_sha,
                status="POST_PUSH_PENDING",
            receipt_path=self._receipt_path(transaction),
                workflows=pending,
            )
            transaction = self._save_transaction(transaction, "HOSTED_PENDING")
            try:
                hosted = wait_for_remote_ci(
                    self.repo_root,
                    self.config,
                    transaction.candidate_sha,
                    release_branch="main",
                )
            except RemoteCIFailure as error:
                transaction = self._save_transaction(
                    transaction,
                    "REVERT_REQUIRED",
                    failure_reason=redact_sensitive(str(error)),
                )
            else:
                return self._complete_verified(
                    transaction, RequiredWorkflowStatus.model_validate(hosted)
                )

        if transaction.phase == "REVERT_REQUIRED":
            local_sha = current_sha(self.repo_root, "main")
            remote_sha = cast(str, _remote_branch_sha(self.repo_root, self.config, "main"))
            if local_sha == transaction.candidate_sha:
                if remote_sha != transaction.candidate_sha:
                    self._hard_stop("remote main changed before automatic revert")
                revert_sha = self._create_local_revert(transaction)
            elif remote_sha == transaction.candidate_sha:
                self._assert_revert_tree(transaction, local_sha)
                revert_sha = local_sha
            else:
                self._hard_stop("ambiguous local state during automatic revert recovery")
            transaction = self._save_transaction(transaction, "REVERT_LOCAL", revert_sha=revert_sha)

        if transaction.phase == "REVERT_LOCAL":
            if transaction.revert_sha is None:
                self._hard_stop("local revert phase lacks a revert SHA")
            revert_sha = transaction.revert_sha
            local_sha = current_sha(self.repo_root, "main")
            remote_sha = cast(str, _remote_branch_sha(self.repo_root, self.config, "main"))
            if local_sha != revert_sha:
                self._hard_stop("local revert SHA changed before push recovery")
            self._assert_revert_tree(transaction, revert_sha)
            if remote_sha == transaction.candidate_sha:
                self._push_main(revert_sha)
            elif remote_sha != revert_sha:
                self._hard_stop("remote main diverged during revert push recovery")
            transaction = self._save_transaction(transaction, "REVERT_PUSHED")

        if transaction.phase == "REVERT_PUSHED":
            if transaction.revert_sha is None:
                self._hard_stop("pushed revert phase lacks a revert SHA")
            revert_sha = transaction.revert_sha
            if (
                current_sha(self.repo_root, "main") != revert_sha
                or _remote_branch_sha(self.repo_root, self.config, "main") != revert_sha
            ):
                self._hard_stop("revert exact-SHA verification failed during recovery")
            failed = required_workflow_status(
                self.repo_root, self.config, transaction.candidate_sha, "main"
            )
            return self._complete_reverted(transaction, failed)

        return transaction

    def reconcile_transaction(
        self, transaction: MainPublicationTransaction
    ) -> MainPublicationTransaction:
        try:
            return self._reconcile_transaction(transaction)
        except RemoteCIFailure as error:
            latest = transaction
            path = self._transaction_path(transaction.candidate_sha)
            if path.exists():
                latest = MainPublicationTransaction.model_validate(read_json(path, {}))
            self._save_transaction(
                latest,
                "HARD_STUCK",
                failure_reason=redact_sensitive(str(error)),
            )
            raise

    def reconcile_pending(self) -> dict[str, object]:
        root = self._transaction_root()
        if not root.exists():
            return {"status": "NO_PUBLICATION_TRANSACTION"}
        try:
            transactions: list[MainPublicationTransaction] = []
            for path in sorted(root.glob("*.json")):
                transaction = MainPublicationTransaction.model_validate(read_json(path, {}))
                if path.resolve() != self._transaction_path(
                    transaction.candidate_sha
                ).resolve():
                    self._hard_stop("publication transaction filename is ambiguous")
                transactions.append(transaction)
        except ValueError:
            self._hard_stop("publication transaction record is corrupt or ambiguous")
        nonterminal = [item for item in transactions if not item.terminal]
        if len(nonterminal) > 1:
            for item in nonterminal:
                self._save_transaction(
                    item,
                    "HARD_STUCK",
                    failure_reason="multiple nonterminal publication transactions",
                )
            self._hard_stop("multiple nonterminal main publication transactions exist")
        if nonterminal:
            transaction = self.reconcile_transaction(nonterminal[0])
        elif transactions:
            transaction = max(transactions, key=lambda item: item.created_at)
            transaction = self.reconcile_transaction(transaction)
        else:
            return {"status": "NO_PUBLICATION_TRANSACTION"}
        return {
            "status": transaction.phase,
            "candidateSha": transaction.candidate_sha,
            "finalSha": transaction.final_sha,
        }

    def _transaction_result(self, transaction: MainPublicationTransaction) -> dict[str, object]:
        if transaction.phase == "VERIFIED":
            return {
                "status": "PUBLISHED_MAIN_VERIFIED",
                "candidateSha": transaction.candidate_sha,
                "branch": "main",
                "machinePolicyReceipt": transaction.receipt_path,
            }
        if transaction.phase == "REVERTED":
            return {
                "status": "REVERTED_AND_QUARANTINED",
                "candidateSha": transaction.candidate_sha,
                "revertSha": transaction.revert_sha,
                "machinePolicyReceipt": transaction.receipt_path,
            }
        self._hard_stop("publication reconciliation returned a nonterminal phase")

    def _hard_stop(self, reason: str) -> NoReturn:
        state_root = self.quarantine_root.parent
        write_json(
            state_root / "HARD_STUCK.json",
            {
                "version": 3,
                "reason": redact_sensitive(reason),
                "automaticResume": False,
                "detectedAt": datetime.now(UTC).isoformat(),
            },
        )
        (state_root / "STOP").write_text(
            "main-only publication recovery failed\n", encoding="utf-8"
        )
        raise RemoteCIFailure(reason)

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
    ) -> dict[str, object]:
        if current_branch(self.repo_root) != "main":
            raise GitHubSyncError("main-only publisher must run from main")
        if not self.config.enabled:
            raise GitHubSyncError("main-only publication is disabled")
        transaction_path = self._transaction_path(candidate_sha)
        if transaction_path.exists():
            existing = MainPublicationTransaction.model_validate(read_json(transaction_path, {}))
            if existing.candidate_sha != candidate_sha or existing.work_item_id != str(
                item.work_item_id
            ):
                self._hard_stop("publication transaction identity mismatch")
            completed = self.reconcile_transaction(existing)
            return self._transaction_result(completed)
        observed = current_sha(self.repo_root, candidate_sha)
        if observed != candidate_sha:
            raise GitHubSyncError("candidate SHA is not locally resolvable")
        if current_sha(self.repo_root, candidate_ref) != candidate_sha:
            raise GitHubSyncError("candidate ref does not match the exact candidate SHA")
        manifest = CandidateManifest.model_validate(read_json(candidate_manifest_path, {}))
        expected_bindings = {
            "candidate": candidate_sha,
            "packet": packet_digest,
            "context": context_digest,
            "checkpoint": checkpoint_digest,
        }
        observed_bindings = {
            "candidate": manifest.candidate_sha,
            "packet": manifest.packet_digest,
            "context": manifest.context_digest,
            "checkpoint": manifest.checkpoint_digest,
        }
        if observed_bindings != expected_bindings:
            raise GitHubSyncError("candidate manifest bindings changed before publication")
        if {gate.name: gate.evidence_digest for gate in manifest.gates} != gate_digests:
            raise GitHubSyncError("candidate manifest gate bindings changed before publication")
        base_sha = current_sha(self.repo_root, "main")
        validate_github_ready(self.repo_root, self.config)
        _pre_push_checks(self.repo_root)
        _ensure_no_divergence(self.repo_root, self.config, candidate_sha)
        prepared = self._prepared.pop(candidate_sha, None)
        if prepared is None:
            raise GitHubSyncError("candidate lacks exact-SHA pre-promotion gate evidence")
        local_evidence, private_evidence = prepared
        owner_directives = self.repo_root / "config/owner_directives.yaml"
        receipt = MainOnlyMachineReceipt(
            work_item_id=str(item.work_item_id),
            base_sha=base_sha,
            candidate_sha=candidate_sha,
            candidate_manifest_digest=f"sha256:{sha256_file(candidate_manifest_path)}",
            packet_digest=packet_digest,
            source_digest=source_digest,
            context_digest=context_digest,
            checkpoint_digest=checkpoint_digest,
            gate_digests=gate_digests,
            owner_directives_digest=f"sha256:{sha256_file(owner_directives)}",
            local_gate_evidence=local_evidence,
            private_gate_evidence=private_evidence,
            created_at=datetime.now(UTC),
            retry_budget=self.config.retry_attempts,
        )
        receipt_path = self.receipt_root / f"{item.work_item_id}-{candidate_sha[:12]}.json"
        created_at = datetime.now(UTC)
        transaction = MainPublicationTransaction(
            transaction_id=(
                f"MPUB-{str(item.work_item_id).replace('-', '_')}-{candidate_sha[:12].upper()}"
            ),
            work_item_id=str(item.work_item_id),
            base_sha=base_sha,
            candidate_sha=candidate_sha,
            phase="PREPARED",
            receipt_path=str(receipt_path),
            machine_receipt=receipt,
            created_at=created_at,
            updated_at=created_at,
        )
        transaction = self._save_transaction(transaction)
        completed = self.reconcile_transaction(transaction)
        return self._transaction_result(completed)


# Backward-compatible spelling retained for older pipeline imports.
GithubSyncError = GitHubSyncError


def _validate_branch_name(branch: str, *, allow_main: bool) -> None:
    invalid = (
        not _BRANCH_PATTERN.fullmatch(branch)
        or ".." in branch
        or "//" in branch
        or "@{" in branch
        or branch.endswith(".lock")
        or branch.startswith("/")
        or branch.endswith("/")
    )
    if invalid or (branch == "main" and not allow_main):
        raise GitHubSyncError(f"unsafe or prohibited branch name: {branch!r}")


def load_github_config(path: Path) -> GitHubConfig:
    if not path.exists():
        return GitHubConfig(enabled=False)
    raw = load_yaml(path)
    return GitHubConfig.model_validate(raw)


def load_github_state(path: Path) -> GitHubSyncState:
    if not path.exists():
        return GitHubSyncState()
    raw = cast(dict[str, Any], read_json(path, {}))
    if raw.get("version") != 3:
        raw = {**raw, "version": 3}
    return GitHubSyncState.model_validate(raw)


def save_github_state(path: Path, state: GitHubSyncState) -> None:
    write_json(path, state.model_dump(mode="json"))


def _safe_error(result: Any, fallback: str) -> str:
    return redact_sensitive(str(result.stderr).strip() or str(result.stdout).strip() or fallback)


def _gh_ready(repo_root: Path, config: GitHubConfig) -> dict[str, str]:
    if shutil.which("gh") is None:
        raise GitHubSyncError("GitHub CLI `gh` is not installed")
    status = run_command(
        ["gh", "auth", "status", "--hostname", "github.com"], cwd=repo_root, check=False
    )
    if status.returncode != 0:
        raise GitHubSyncError("GitHub CLI is not authenticated; rerun scripts/configure_github.sh")
    remotes = run_command(["git", "remote"], cwd=repo_root).stdout.splitlines()
    if config.remote not in remotes:
        raise GitHubSyncError(f"Git remote {config.remote!r} is not configured")

    view = run_command(
        ["gh", "repo", "view", "--json", "nameWithOwner,visibility,url"],
        cwd=repo_root,
        check=False,
    )
    if view.returncode != 0:
        raise GitHubSyncError(_safe_error(view, "gh repo view failed"))
    try:
        metadata = json.loads(view.stdout)
    except json.JSONDecodeError as exc:
        raise GitHubSyncError("GitHub repository metadata was not valid JSON") from exc
    visibility = str(metadata.get("visibility", "")).lower()
    if visibility != config.visibility:
        raise GitHubSyncError(
            f"Configured repository must remain private; GitHub reports {visibility or 'unknown'}"
        )
    observed_repo = str(metadata.get("nameWithOwner", ""))
    if config.repository and observed_repo.lower() != config.repository.lower():
        raise GitHubSyncError(
            f"Configured GitHub repository {config.repository!r} does not match {observed_repo!r}"
        )
    return {
        "name_with_owner": observed_repo,
        "visibility": visibility,
        "url": str(metadata.get("url", "")),
    }


def _tracked_tree_is_clean(repo_root: Path) -> bool:
    result = run_command(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo_root, check=False
    )
    return result.returncode == 0 and not result.stdout.strip()


def validate_github_ready(repo_root: Path, config: GitHubConfig) -> dict[str, str]:
    if not config.enabled:
        raise GitHubSyncError("GitHub synchronization is disabled")
    if not _tracked_tree_is_clean(repo_root):
        raise GitHubSyncError("Tracked repository changes must be committed before GitHub release")
    branch = current_branch(repo_root)
    if branch != config.base_branch:
        raise GitHubSyncError(
            f"Release orchestration requires branch {config.base_branch!r}; "
            f"current branch is {branch!r}"
        )
    return _gh_ready(repo_root, config)


def _remote_branch_sha(repo_root: Path, config: GitHubConfig, branch: str) -> str | None:
    _validate_branch_name(branch, allow_main=True)
    if branch != "main":
        raise GitHubSyncError("V3 remote inspection is restricted to refs/heads/main")
    result = run_command(
        ["git", "ls-remote", config.remote, f"refs/heads/{branch}"],
        cwd=repo_root,
        check=False,
    )
    if result.returncode != 0:
        raise GitHubSyncError(_safe_error(result, "git ls-remote failed"))
    line = result.stdout.strip()
    return line.split()[0] if line else None


def _remote_sha(repo_root: Path, config: GitHubConfig) -> str | None:
    return _remote_branch_sha(repo_root, config, config.base_branch)


def _fetch_branch(repo_root: Path, config: GitHubConfig, branch: str) -> str:
    _validate_branch_name(branch, allow_main=True)
    if branch != "main":
        raise GitHubSyncError("V3 remote fetch is restricted to refs/heads/main")
    remote_ref = f"refs/remotes/{config.remote}/{branch}"
    result = run_command(
        ["git", "fetch", "--no-tags", config.remote, f"refs/heads/{branch}:{remote_ref}"],
        cwd=repo_root,
        check=False,
    )
    if result.returncode != 0:
        raise GitHubSyncError(_safe_error(result, f"git fetch failed for {branch}"))
    return current_sha(repo_root, remote_ref)


def _is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    return (
        run_command(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=repo_root,
            check=False,
        ).returncode
        == 0
    )


def _ensure_no_divergence(repo_root: Path, config: GitHubConfig, candidate_sha: str) -> None:
    remote_main = _remote_sha(repo_root, config)
    if remote_main is None:
        raise GitHubDivergenceError("origin/main is missing; release base cannot be verified")
    observed = _fetch_branch(repo_root, config, config.base_branch)
    if observed != remote_main or not _is_ancestor(repo_root, remote_main, candidate_sha):
        raise GitHubDivergenceError(
            "origin/main is not an ancestor of the exact candidate; release refused without force"
        )


def _pre_push_checks(repo_root: Path) -> None:
    script = repo_root / "scripts" / "verify_no_secrets.sh"
    if script.exists():
        result = run_command(["bash", str(script)], cwd=repo_root, check=False)
        if result.returncode != 0:
            raise GitHubSyncError(_safe_error(result, "secret scan failed"))
    fsck = run_command(["git", "fsck", "--no-dangling"], cwd=repo_root, check=False)
    if fsck.returncode != 0:
        raise GitHubSyncError(_safe_error(fsck, "git fsck failed"))


def push_main_with_retry(repo_root: Path, config: GitHubConfig, refspec: str) -> None:
    match = re.fullmatch(rf"({SHA_PATTERN.pattern[1:-1]}):refs/heads/main", refspec)
    if match is None:
        raise GitHubSyncError("owner directives permit only an exact-SHA main refspec")
    last_error = ""
    for attempt in range(1, config.retry_attempts + 1):
        result = run_command(
            ["git", "push", "--porcelain", config.remote, refspec],
            cwd=repo_root,
            check=False,
        )
        if result.returncode == 0:
            return
        last_error = _safe_error(result, "git push failed")
        if attempt < config.retry_attempts:
            time.sleep(config.retry_backoff_seconds * attempt)
    raise GitHubSyncError(
        f"main-only push failed after {config.retry_attempts} attempts: {last_error}"
    )


def _workflow_runs(repo_root: Path, sha: str) -> list[dict[str, Any]]:
    result = run_command(
        [
            "gh",
            "run",
            "list",
            "--commit",
            sha,
            "--limit",
            "100",
            "--json",
            "databaseId,status,conclusion,workflowName,headSha,headBranch,event,createdAt,url",
        ],
        cwd=repo_root,
        check=False,
    )
    if result.returncode != 0:
        raise GitHubSyncError(_safe_error(result, "gh run list failed"))
    try:
        value = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise GitHubSyncError("gh run list returned invalid JSON") from exc
    return cast(list[dict[str, Any]], value) if isinstance(value, list) else []


def _run_created_at(run: dict[str, Any]) -> datetime:
    value = run.get("createdAt")
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=UTC)


def required_workflow_status(
    repo_root: Path,
    config: GitHubConfig,
    candidate_sha: str,
    release_branch: str = "main",
) -> RequiredWorkflowStatus:
    if release_branch != "main":
        raise GitHubSyncError("owner directives forbid monitoring a non-main branch")
    matching = [
        run
        for run in _workflow_runs(repo_root, candidate_sha)
        if run.get("headSha") == candidate_sha
        and run.get("headBranch") == "main"
        and run.get("event") in {"push", "workflow_dispatch"}
    ]
    workflows: list[RequiredWorkflow] = []
    for name in config.remote_ci.required_workflows:
        runs = [run for run in matching if run.get("workflowName") == name]
        runs.sort(key=_run_created_at, reverse=True)
        if not runs:
            workflows.append(RequiredWorkflow(name=name, status="missing"))
            continue
        latest = runs[0]
        status = str(latest.get("status") or "queued")
        if status not in {"queued", "in_progress", "completed"}:
            status = "queued"
        workflows.append(
            RequiredWorkflow(
                name=name,
                status=cast(Literal["queued", "in_progress", "completed"], status),
                conclusion=str(latest.get("conclusion")) if latest.get("conclusion") else None,
                url=str(latest.get("url")) if latest.get("url") else None,
            )
        )
    failed = any(item.status == "completed" and item.conclusion != "success" for item in workflows)
    passed = all(item.status == "completed" and item.conclusion == "success" for item in workflows)
    overall: Literal["pending", "pass", "fail"] = (
        "fail" if failed else "pass" if passed else "pending"
    )
    return RequiredWorkflowStatus(
        candidate_sha=candidate_sha,
        release_branch=release_branch,
        status=overall,
        workflows=workflows,
    )


def wait_for_remote_ci(
    repo_root: Path,
    config: GitHubConfig,
    sha: str,
    *,
    release_branch: str | None = None,
    not_before: datetime | None = None,
) -> dict[str, Any]:
    del not_before
    branch = release_branch or "main"
    if branch != "main":
        raise GitHubSyncError("owner directives forbid non-main CI publication")
    deadline = time.monotonic() + config.remote_ci.timeout_seconds
    latest = required_workflow_status(repo_root, config, sha, branch)
    while latest.status == "pending" and time.monotonic() < deadline:
        time.sleep(config.remote_ci.poll_seconds)
        latest = required_workflow_status(repo_root, config, sha, branch)
    if latest.status == "pass":
        return latest.model_dump(mode="json", by_alias=True)
    if latest.status == "fail":
        raise RemoteCIFailure(f"required main workflows failed for {sha[:12]}")
    message = f"timed out waiting for required main workflows on {sha[:12]}"
    if config.remote_ci.fail_closed:
        raise RemoteCIFailure(message)
    return latest.model_dump(mode="json", by_alias=True)


def should_push(
    *,
    config: GitHubConfig,
    state: GitHubSyncState,
    task: TaskPacket | None,
    force: bool,
    now: datetime,
) -> bool:
    if not config.enabled or state.tasks_since_push <= 0:
        return False
    if force:
        return True
    if task is not None and task.risk_tier in config.immediate_risk_tiers:
        return True
    if state.tasks_since_push >= config.push_after_verified_tasks:
        return True
    if state.pending and state.last_push_at is not None:
        return (now - state.last_push_at).total_seconds() >= config.push_interval_seconds
    return False


def record_verified_task(state_path: Path, *, task: TaskPacket | None = None) -> GitHubSyncState:
    state = load_github_state(state_path)
    state.tasks_since_push += 1
    state.pending = True
    if task is not None:
        state.last_task_id = task.task_id
        state.last_task_risk = task.risk_tier
    save_github_state(state_path, state)
    return state


def sync_github(
    *,
    repo_root: Path,
    config_path: Path,
    state_path: Path,
    task: TaskPacket | None = None,
    reason: str,
    force: bool = False,
) -> dict[str, Any]:
    config = load_github_config(config_path)
    state = load_github_state(state_path)
    if not config.enabled:
        return {"status": "disabled"}
    now = datetime.now(UTC)
    if not should_push(config=config, state=state, task=task, force=force, now=now):
        return {"status": "deferred", "tasks_since_push": state.tasks_since_push}
    candidate_sha = current_sha(repo_root, config.base_branch)
    state.last_reason = reason
    state.pending = True
    save_github_state(state_path, state)
    return {
        "status": "main-only-controller-required",
        "candidate_sha": candidate_sha,
        "release_mode": config.release_mode,
        "direct_main_push": config.direct_main_push,
        "message": "use V3Controller and MainOnlyPublisher for exact-SHA main publication",
    }
