"""V3.1 GitHub policy and automated pull-request publication entrypoints.

There is intentionally no direct-main push helper in this module.  The only mutating
transport is :class:`GhPublicationClient`, whose push method accepts a protected
candidate-branch prefix and rejects ``main``.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import ConfigDict, Field, field_validator, model_validator

from .gitops import current_sha
from .models import RiskTier, TaskPacket
from .util import read_json, run_command, sha256_file, write_json
from .v3.base import SHA_PATTERN, V3Model, sha256_digest
from .v3.publication import (
    MACHINE_POLICY_CHECK,
    AutomatedPRPublisher,
    ExternalReceiptAuthorizer,
    GhPublicationClient,
    PublicationError,
    PublicationTransaction,
    trusted_external_path,
)
from .v3.source_authority import validate_active_source_generation
from .yamlutil import load_yaml


class RemoteCIConfig(V3Model):
    enabled: Literal[True] = True
    required_workflows: list[str] = Field(
        default_factory=lambda: [
            "TrainCapsule / Factory quality",
            "TrainCapsule / Product unit",
            "TrainCapsule / Product contract",
            "TrainCapsule / Security",
            "TrainCapsule / Source-of-truth integrity",
            "TrainCapsule / Packaging install",
            "TrainCapsule / Docs and schemas",
            "TrainCapsule / Source freshness",
            MACHINE_POLICY_CHECK,
        ],
        min_length=1,
    )
    trusted_check_app_ids: dict[str, int | None] = Field(min_length=1)
    post_merge_required_workflows: list[str] = Field(min_length=1)
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
        if MACHINE_POLICY_CHECK not in normalized:
            raise ValueError("the independent machine-policy check is mandatory")
        return normalized

    @model_validator(mode="after")
    def check_id_roster(self) -> RemoteCIConfig:
        if set(self.trusted_check_app_ids) != set(self.required_workflows):
            raise ValueError("trusted GitHub App IDs must cover exactly the required checks")
        if (
            len(self.post_merge_required_workflows) != len(set(self.post_merge_required_workflows))
            or not set(self.post_merge_required_workflows).issubset(self.required_workflows)
            or MACHINE_POLICY_CHECK in self.post_merge_required_workflows
        ):
            raise ValueError(
                "post-merge checks must be a unique hosted-check subset of the required roster"
            )
        return self


class GitHubConfig(V3Model):
    schema_version: Literal["3.1"] = "3.1"
    enabled: bool = False
    remote: Literal["origin"] = "origin"
    base_branch: Literal["main"] = "main"
    visibility: Literal["public"] = "public"
    repository: str = Field(min_length=3, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    release_mode: Literal["AUTOMATED_PR_REQUIRED_CHECKS_MACHINE_RECEIPT_AUTO_MERGE"] = (
        "AUTOMATED_PR_REQUIRED_CHECKS_MACHINE_RECEIPT_AUTO_MERGE"
    )
    direct_main_push: Literal[False] = False
    candidate_branch_prefix: Literal["factory/"] = "factory/"
    pull_request_metadata_path: Literal["factory/state/latest-pull-request.json"] = (
        "factory/state/latest-pull-request.json"
    )
    transaction_path: Literal["publication-transactions"] = "publication-transactions"
    quarantine_path: Literal["publication-quarantine"] = "publication-quarantine"
    independent_receipt_root: str = Field(min_length=1)
    receipt_verifier_executable: str = Field(min_length=1)
    activation_receipt_path: str = Field(min_length=1)
    exact_head_sha_checks_required: Literal[True] = True
    independent_machine_policy_receipt_required: Literal[True] = True
    merge_queue_or_auto_merge_required: Literal[True] = True
    exact_merged_main_verification_required: Literal[True] = True
    publisher_capability: Literal["AUTOMATED_PR_V31_READY"] = "AUTOMATED_PR_V31_READY"
    retry_attempts: int = Field(default=5, ge=1, le=10)
    retry_backoff_seconds: int = Field(default=30, ge=1, le=3600)
    verify_remote_sha: Literal[True] = True
    commit_subject_max_chars: int = Field(default=50, ge=20, le=72)
    remote_ci: RemoteCIConfig

    @model_validator(mode="after")
    def external_paths(self) -> GitHubConfig:
        for value, label in (
            (self.independent_receipt_root, "independent receipt root"),
            (self.receipt_verifier_executable, "receipt verifier executable"),
            (self.activation_receipt_path, "activation receipt path"),
        ):
            if not Path(value).is_absolute():
                raise ValueError(f"{label} must be an absolute externally administered path")
        return self


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
    release_branch: str
    status: Literal["pending", "pass", "fail"]
    workflows: list[RequiredWorkflow]


class GitHubReleaseMetadata(V3Model):
    schema_version: Literal["3.1"] = "3.1"
    release_mode: Literal["AUTOMATED_PULL_REQUEST"] = "AUTOMATED_PULL_REQUEST"
    transaction_id: str
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    pull_request_number: int = Field(ge=1)
    pull_request_url: str
    merged_main_sha: str | None = Field(default=None, pattern=SHA_PATTERN.pattern)
    status: Literal[
        "PENDING_REQUIRED_CHECKS",
        "MERGED_MAIN_VERIFIED",
        "REJECTED_BEFORE_MAIN",
        "REVERTED_MAIN_VERIFIED",
        "HARD_STUCK",
    ]
    machine_policy_receipt_digest: str | None = None
    updated_at: datetime


class GitHubSyncError(PublicationError):
    pass


class GitHubDivergenceError(GitHubSyncError):
    pass


class RemoteCIFailure(GitHubSyncError):
    pass


GithubSyncError = GitHubSyncError


def validate_release_rule_types(rule_types: set[str]) -> None:
    required = {
        "required_status_checks",
        "pull_request",
        "non_fast_forward",
        "deletion",
    }
    missing = required - rule_types
    if missing:
        raise GitHubSyncError(
            f"main rules are missing required release controls: {sorted(missing)}"
        )
    if "update" in rule_types:
        raise GitHubSyncError(
            "GitHub restrict-updates would block bypass-free automated PR merges"
        )


def load_github_config(path: Path) -> GitHubConfig:
    if not path.is_file():
        raise GitHubSyncError("V3.1 GitHub configuration is missing")
    return GitHubConfig.model_validate(load_yaml(path))


def load_github_state(path: Path) -> GitHubSyncState:
    if not path.exists():
        return GitHubSyncState()
    raw = cast(dict[str, Any], read_json(path, {}))
    if raw.get("version") != 3:
        raw = {**raw, "version": 3}
    return GitHubSyncState.model_validate(raw)


def save_github_state(path: Path, state: GitHubSyncState) -> None:
    write_json(path, state.model_dump(mode="json"))


def record_verified_task(state_path: Path, *, task: TaskPacket | None = None) -> GitHubSyncState:
    state = load_github_state(state_path)
    state.tasks_since_push += 1
    state.pending = True
    if task is not None:
        state.last_task_id = task.task_id
        state.last_task_risk = task.risk_tier
    save_github_state(state_path, state)
    return state


def validate_publication_installation(config: GitHubConfig) -> None:
    """Fail closed before runtime when external publication authority is unavailable."""

    if not config.enabled:
        raise GitHubSyncError("automated pull-request publication is disabled")
    if shutil.which("gh") is None:
        raise GitHubSyncError("GitHub CLI is unavailable")
    missing_ids = [
        name for name, value in config.remote_ci.trusted_check_app_ids.items() if value is None
    ]
    if missing_ids:
        raise GitHubSyncError(f"trusted GitHub App IDs are not provisioned: {sorted(missing_ids)}")
    try:
        trusted_external_path(
            Path(config.independent_receipt_root),
            directory=True,
            label="independent machine-policy receipt root",
        )
        ExternalReceiptAuthorizer(Path(config.receipt_verifier_executable))
    except (FileNotFoundError, PublicationError) as exc:
        raise GitHubSyncError("independent verifier installation is not trusted") from exc


def validate_controller_activation(*, repo_root: Path, config: GitHubConfig) -> str:
    """Validate an externally signed exact-main activation receipt before autonomy."""

    validate_publication_installation(config)
    tracked = run_command(
        [
            "git",
            "diff",
            "--quiet",
            "HEAD",
            "--",
            "tcfactory",
            "config/factory.yaml",
            "config/github.yaml",
        ],
        cwd=repo_root,
        check=False,
    )
    untracked = run_command(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "tcfactory"],
        cwd=repo_root,
        check=False,
    )
    if tracked.returncode != 0 or untracked.returncode != 0 or untracked.stdout.strip():
        raise GitHubSyncError(
            "controller/publication code or active release configuration differs from exact HEAD"
        )
    active = validate_active_source_generation(repo_root)
    controller = repo_root / "tcfactory/v3/controller.py"
    config_path = repo_root / "config/factory.yaml"
    authorization = ExternalReceiptAuthorizer(
        Path(config.receipt_verifier_executable)
    ).verify_activation(
        Path(config.activation_receipt_path),
        expected_main_sha=current_sha(repo_root, "main"),
        source_generation_id=active.generation_id,
        source_generation_digest=f"sha256:{active.manifest_digest}",
        controller_binary_digest=f"sha256:{sha256_file(controller)}",
        controller_config_digest=f"sha256:{sha256_file(config_path)}",
    )
    return authorization.activation_receipt_digest


def validate_repository_release_controls(
    *, repo_root: Path, config: GitHubConfig
) -> dict[str, object]:
    """Observe, never mutate, the server-side controls required for autonomous merge."""

    validate_publication_installation(config)
    result = run_command(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{config.repository}/rulesets",
        ],
        cwd=repo_root,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        raise GitHubSyncError("server-side main protection/rules are unavailable")
    try:
        raw: object = json.loads(result.stdout)
    except ValueError as exc:
        raise GitHubSyncError("server-side main rules were invalid JSON") from exc
    if not isinstance(raw, list):
        raise GitHubSyncError("server-side main rules have the wrong shape")
    candidates: list[Mapping[str, object]] = []
    for raw_item in cast(list[object], raw):
        if isinstance(raw_item, dict):
            typed_item = cast(dict[str, object], raw_item)
            if isinstance(typed_item.get("id"), int):
                candidates.append(typed_item)
    exact: Mapping[str, object] | None = None
    for candidate in candidates:
        detail = run_command(
            ["gh", "api", f"repos/{config.repository}/rulesets/{candidate['id']}"],
            cwd=repo_root,
            check=False,
            timeout=60,
        )
        if detail.returncode != 0:
            continue
        parsed: object = json.loads(detail.stdout)
        if not isinstance(parsed, dict):
            continue
        typed_parsed = cast(dict[str, object], parsed)
        if typed_parsed.get("enforcement") != "active":
            continue
        conditions = typed_parsed.get("conditions")
        if not isinstance(conditions, dict):
            continue
        ref_name = cast(dict[str, object], conditions).get("ref_name")
        if not isinstance(ref_name, dict):
            continue
        include = cast(dict[str, object], ref_name).get("include")
        if isinstance(include, list) and any(
            isinstance(value, str) and value in {"~DEFAULT_BRANCH", "refs/heads/main"}
            for value in cast(list[object], include)
        ):
            exact = typed_parsed
            break
    if exact is None:
        raise GitHubSyncError("no active exact-main repository ruleset is installed")
    bypass = exact.get("bypass_actors")
    if not isinstance(bypass, list) or bypass:
        raise GitHubSyncError("main ruleset contains bypass actors")
    rules = exact.get("rules")
    if not isinstance(rules, list):
        raise GitHubSyncError("main ruleset rules are unavailable")
    rule_map: dict[str, Mapping[str, object]] = {}
    for raw_rule in cast(list[object], rules):
        if isinstance(raw_rule, dict):
            typed_rule = cast(dict[str, object], raw_rule)
            if isinstance(typed_rule.get("type"), str):
                rule_map[cast(str, typed_rule["type"])] = typed_rule
    validate_release_rule_types(set(rule_map))
    status_parameters = rule_map["required_status_checks"].get("parameters")
    if not isinstance(status_parameters, dict):
        raise GitHubSyncError("required status-check parameters are unavailable")
    raw_checks = cast(dict[str, object], status_parameters).get("required_status_checks")
    if not isinstance(raw_checks, list):
        raise GitHubSyncError("required status-check contexts are unavailable")
    observed_checks: dict[str, int] = {}
    for raw_check in cast(list[object], raw_checks):
        if not isinstance(raw_check, dict):
            continue
        typed_check = cast(dict[str, object], raw_check)
        context, integration_id = typed_check.get("context"), typed_check.get("integration_id")
        if isinstance(context, str) and isinstance(integration_id, int):
            observed_checks[context] = integration_id
    expected_checks = config.remote_ci.trusted_check_app_ids
    if any(value is None for value in expected_checks.values()):
        raise GitHubSyncError("every required check must bind a provisioned GitHub App ID")
    expected_exact = cast(dict[str, int], expected_checks)
    if observed_checks != expected_exact:
        raise GitHubSyncError("main ruleset required contexts/GitHub App IDs differ")
    repository_result = run_command(
        ["gh", "api", f"repos/{config.repository}"],
        cwd=repo_root,
        check=False,
        timeout=60,
    )
    if repository_result.returncode != 0:
        raise GitHubSyncError("repository merge policy is unavailable")
    repository_payload: object = json.loads(repository_result.stdout)
    if (
        not isinstance(repository_payload, dict)
        or cast(dict[str, object], repository_payload).get("allow_auto_merge") is not True
    ):
        raise GitHubSyncError("repository automatic merge is not enabled")
    observation_core = {
        "repository": config.repository,
        "baseBranch": "main",
        "rulesetId": exact["id"],
        "enforcement": exact["enforcement"],
        "requiredCheckAppIds": observed_checks,
        "bypassActorCount": 0,
        "deletionForbidden": True,
        "forcePushForbidden": True,
        "pullRequestRequired": True,
        "directBranchUpdatesForbidden": True,
        "autoMergeEnabled": True,
    }
    digest = sha256_digest(
        (json.dumps(observation_core, separators=(",", ":"), sort_keys=True) + "\n").encode()
    )
    receipt_path = Path("/var/lib/traincapsule-verifier/ruleset/current.json")
    verifier_path = Path("/usr/local/bin/traincapsule-verifier-verify-receipt")
    trusted_external_path(receipt_path, directory=False, label="ruleset observation receipt")
    trusted_external_path(verifier_path, directory=False, label="ruleset receipt verifier")
    verified = run_command(
        [
            str(verifier_path),
            "verify-ruleset-observation",
            "--receipt",
            str(receipt_path),
            "--repository",
            config.repository,
            "--observation-digest",
            digest,
        ],
        cwd=verifier_path.parent,
        check=False,
        timeout=60,
    )
    if verified.returncode != 0:
        raise GitHubSyncError("signed ruleset observation receipt is invalid or stale")
    return {
        "observedRuleTypes": sorted(rule_map),
        "configuredOnly": False,
        "rulesetId": exact["id"],
        "requiredCheckAppIds": observed_checks,
        "observationDigest": digest,
        "signedObservationPath": str(receipt_path),
    }


def build_automated_pr_publisher(
    *, repo_root: Path, state_root: Path, config: GitHubConfig | None = None
) -> AutomatedPRPublisher:
    from .v3.runtime_paths import ensure_v3_mutable_runtime, resolve_v3_runtime_paths

    active = config or load_github_config(repo_root / "config/github.yaml")
    runtime_paths = resolve_v3_runtime_paths(repo_root)
    if runtime_paths.state_root.resolve() != state_root.resolve():
        raise GitHubSyncError("publication state root differs from the canonical runtime root")
    ensure_v3_mutable_runtime(
        repo_root,
        runtime_paths,
        require_snapshot_alignment=False,
    )
    validate_publication_installation(active)
    validate_controller_activation(repo_root=repo_root, config=active)
    client = GhPublicationClient(
        runtime_paths.git_root,
        remote=active.remote,
        repository=active.repository,
        branch_prefix=active.candidate_branch_prefix,
    )
    return AutomatedPRPublisher(
        repo_root=repo_root,
        config=active,
        transaction_root=state_root / active.transaction_path,
        receipt_root=Path(active.independent_receipt_root),
        quarantine_root=state_root / active.quarantine_path,
        client=client,
        receipt_authorizer=ExternalReceiptAuthorizer(Path(active.receipt_verifier_executable)),
        git_root=runtime_paths.git_root,
    )


def reconcile_publications(*, repo_root: Path, state_root: Path) -> list[PublicationTransaction]:
    return build_automated_pr_publisher(
        repo_root=repo_root, state_root=state_root
    ).reconcile_pending()


def should_push(
    *,
    config: GitHubConfig,
    state: GitHubSyncState,
    task: TaskPacket | None,
    force: bool,
    now: datetime,
) -> bool:
    del config, state, task, force, now
    return False


def sync_github(
    *,
    repo_root: Path,
    config_path: Path,
    state_path: Path,
    task: TaskPacket | None = None,
    reason: str,
    force: bool = False,
) -> dict[str, Any]:
    """Legacy batching entrypoint: never publishes and never pushes any ref."""

    del repo_root, task, reason, force
    config = load_github_config(config_path)
    state = load_github_state(state_path)
    return {
        "status": "v3.1-pr-publisher-only",
        "pending": state.pending,
        "releaseMode": config.release_mode,
        "directMainPush": False,
        "message": "publication is owned by the exact-candidate V3.1 controller",
    }


def publication_metadata(transaction: PublicationTransaction) -> GitHubReleaseMetadata | None:
    if transaction.pull_request_number is None or transaction.pull_request_url is None:
        return None
    status = {
        "INVARIANTS_VERIFIED": "MERGED_MAIN_VERIFIED",
        "REVERTED": "REVERTED_MAIN_VERIFIED",
        "FAILED": "REJECTED_BEFORE_MAIN",
        "HARD_STUCK": "HARD_STUCK",
    }.get(transaction.phase.value, "PENDING_REQUIRED_CHECKS")
    return GitHubReleaseMetadata(
        transaction_id=transaction.transaction_id,
        candidate_sha=transaction.candidate_sha,
        pull_request_number=transaction.pull_request_number,
        pull_request_url=transaction.pull_request_url,
        merged_main_sha=transaction.merged_main_sha,
        status=cast(Any, status),
        machine_policy_receipt_digest=transaction.receipt_digest,
        updated_at=datetime.now(UTC),
    )
