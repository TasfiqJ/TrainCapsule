"""V3.1 GitHub policy and exact-SHA direct-main publication entrypoints."""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import ConfigDict, Field, field_validator, model_validator

from .gitops import current_sha, trusted_repository_git_command
from .models import RiskTier, TaskPacket
from .util import read_json, run_command, write_json
from .v3.base import SHA_PATTERN, V3Model, sha256_digest
from .v3.installed_runtime import load_installed_controller_runtime
from .v3.publication import (
    MACHINE_POLICY_CHECK,
    DirectMainPublisher,
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
    release_mode: Literal["DIRECT_MAIN_EXACT_SHA_MACHINE_RECEIPT_POST_PUSH_VERIFY"] = (
        "DIRECT_MAIN_EXACT_SHA_MACHINE_RECEIPT_POST_PUSH_VERIFY"
    )
    direct_main_push: Literal[True] = True
    transaction_path: Literal["publication-transactions"] = "publication-transactions"
    quarantine_path: Literal["publication-quarantine"] = "publication-quarantine"
    independent_receipt_root: str = Field(min_length=1)
    receipt_verifier_executable: str = Field(min_length=1)
    activation_receipt_path: str = Field(min_length=1)
    exact_head_sha_checks_required: Literal[True] = True
    independent_machine_policy_receipt_required: Literal[True] = True
    merge_queue_or_auto_merge_required: Literal[False] = False
    exact_merged_main_verification_required: Literal[True] = True
    publisher_capability: Literal["DIRECT_MAIN_V31_READY"] = "DIRECT_MAIN_V31_READY"
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
    release_mode: Literal["DIRECT_MAIN"] = "DIRECT_MAIN"
    transaction_id: str
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
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
    required = {"non_fast_forward", "deletion"}
    missing = required - rule_types
    if missing:
        raise GitHubSyncError(
            f"main rules are missing required release controls: {sorted(missing)}"
        )
    forbidden = {"update", "pull_request", "required_status_checks"} & rule_types
    if forbidden:
        raise GitHubSyncError(
            f"main rules contain controls incompatible with direct publication: {sorted(forbidden)}"
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
        raise GitHubSyncError("direct-main publication is disabled")
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
        trusted_repository_git_command(
            repo_root,
            "diff",
            "--quiet",
            "HEAD",
            "--",
            "tcfactory",
            "config/factory.yaml",
            "config/github.yaml",
        ),
        cwd=repo_root,
        check=False,
    )
    untracked = run_command(
        trusted_repository_git_command(
            repo_root,
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "tcfactory",
        ),
        cwd=repo_root,
        check=False,
    )
    if tracked.returncode != 0 or untracked.returncode != 0 or untracked.stdout.strip():
        raise GitHubSyncError(
            "controller/publication code or active release configuration differs from exact HEAD"
        )
    active = validate_active_source_generation(repo_root)
    controller_digest, config_digest = installed_activation_digests()
    authorization = ExternalReceiptAuthorizer(
        Path(config.receipt_verifier_executable)
    ).verify_activation(
        Path(config.activation_receipt_path),
        expected_main_sha=current_sha(repo_root, "main"),
        source_generation_id=active.generation_id,
        source_generation_digest=f"sha256:{active.manifest_digest}",
        controller_binary_digest=controller_digest,
        controller_config_digest=config_digest,
    )
    return authorization.activation_receipt_digest


def installed_activation_digests() -> tuple[str, str]:
    """Attest the exact installed runtime/config bytes signed for activation."""
    installed_runtime, runtime_manifest_raw = load_installed_controller_runtime()
    effective_config_raw = Path(installed_runtime.effective_config.path).read_bytes()
    config_digest = sha256_digest(effective_config_raw)
    if config_digest != installed_runtime.effective_config.digest:
        raise GitHubSyncError("installed controller effective config digest mismatch")
    return sha256_digest(runtime_manifest_raw), config_digest


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
        return validate_signed_repository_release_controls(config=config)
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
    observed_checks: dict[str, int] = {}
    observation_core: dict[str, object] = {
        "repository": config.repository,
        "baseBranch": "main",
        "rulesetId": exact["id"],
        "enforcement": exact["enforcement"],
        "requiredCheckAppIds": {},
        "bypassActorCount": 0,
        "deletionForbidden": True,
        "forcePushForbidden": True,
        "pullRequestRequired": False,
        "directBranchUpdatesForbidden": False,
        "autoMergeEnabled": False,
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


def validate_signed_repository_release_controls(
    *,
    config: GitHubConfig,
    receipt_path: Path = Path("/var/lib/traincapsule-verifier/ruleset/current.json"),
    verifier_path: Path = Path("/usr/local/bin/traincapsule-verifier-verify-receipt"),
) -> dict[str, object]:
    """Verify the root-promoted ruleset observation without controller credentials."""

    trusted_external_path(receipt_path, directory=False, label="ruleset observation receipt")
    trusted_external_path(verifier_path, directory=False, label="ruleset receipt verifier")
    try:
        raw: object = json.loads(receipt_path.read_bytes())
    except (OSError, ValueError) as exc:
        raise GitHubSyncError("signed ruleset observation is unavailable") from exc
    if not isinstance(raw, dict):
        raise GitHubSyncError("signed ruleset observation has the wrong shape")
    payload = cast(dict[str, object], raw)
    raw_checks = payload.get("requiredCheckAppIds")
    if not isinstance(raw_checks, dict):
        raise GitHubSyncError("signed ruleset observation check roster is unavailable")
    observed_checks = {
        key: value
        for key, value in cast(dict[object, object], raw_checks).items()
        if isinstance(key, str) and type(value) is int
    }
    if observed_checks:
        raise GitHubSyncError("direct-main ruleset must not contain required-check rules")
    if (
        payload.get("repository") != config.repository
        or payload.get("baseBranch") != "main"
        or payload.get("enforcement") != "active"
        or type(payload.get("rulesetId")) is not int
        or payload.get("bypassActorCount") != 0
        or payload.get("deletionForbidden") is not True
        or payload.get("forcePushForbidden") is not True
        or payload.get("pullRequestRequired") is not False
        or payload.get("directBranchUpdatesForbidden") is not False
        or payload.get("autoMergeEnabled") is not False
    ):
        raise GitHubSyncError("signed ruleset observation does not enforce exact main")
    observation_core = {
        "repository": config.repository,
        "baseBranch": "main",
        "rulesetId": payload["rulesetId"],
        "enforcement": "active",
        "requiredCheckAppIds": observed_checks,
        "bypassActorCount": 0,
        "deletionForbidden": True,
        "forcePushForbidden": True,
        "pullRequestRequired": False,
        "directBranchUpdatesForbidden": False,
        "autoMergeEnabled": False,
    }
    digest = sha256_digest(
        (json.dumps(observation_core, separators=(",", ":"), sort_keys=True) + "\n").encode()
    )
    if payload.get("observationDigest") != digest:
        raise GitHubSyncError("signed ruleset observation digest mismatch")
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
        "observedRuleTypes": ["deletion", "non_fast_forward"],
        "configuredOnly": False,
        "rulesetId": payload["rulesetId"],
        "requiredCheckAppIds": observed_checks,
        "observationDigest": digest,
        "signedObservationPath": str(receipt_path),
    }


def build_direct_main_publisher(
    *, repo_root: Path, state_root: Path, config: GitHubConfig | None = None
) -> DirectMainPublisher:
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
    )
    return DirectMainPublisher(
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
    return build_direct_main_publisher(
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
        "status": "v3.1-direct-main-publisher",
        "pending": state.pending,
        "releaseMode": config.release_mode,
        "directMainPush": True,
        "message": "publication is owned by the exact-candidate V3.1 controller",
    }


def publication_metadata(transaction: PublicationTransaction) -> GitHubReleaseMetadata | None:
    status = {
        "INVARIANTS_VERIFIED": "MERGED_MAIN_VERIFIED",
        "REVERTED": "REVERTED_MAIN_VERIFIED",
        "FAILED": "REJECTED_BEFORE_MAIN",
        "HARD_STUCK": "HARD_STUCK",
    }.get(transaction.phase.value, "PENDING_REQUIRED_CHECKS")
    return GitHubReleaseMetadata(
        transaction_id=transaction.transaction_id,
        candidate_sha=transaction.candidate_sha,
        merged_main_sha=transaction.merged_main_sha,
        status=cast(Any, status),
        machine_policy_receipt_digest=transaction.receipt_digest,
        updated_at=datetime.now(UTC),
    )
