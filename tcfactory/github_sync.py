from __future__ import annotations

import json
import re
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import ConfigDict, Field, field_validator

from .gitops import current_branch, current_sha
from .models import FactoryConfig, RiskTier, TaskPacket
from .util import read_json, redact_sensitive, run_command, slugify, write_json
from .v3.base import SHA_PATTERN, V3Model
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
    release_mode: Literal["pull_request"] = "pull_request"
    direct_main_push: Literal[False] = False
    release_branch_prefix: str = "release/traincapsule"
    release_metadata_path: Literal["factory/state/latest-release.json"] = (
        "factory/state/latest-release.json"
    )
    create_draft_pull_request: Literal[True] = True
    auto_merge_mechanical: Literal[False] = False
    auto_merge_standard: Literal[False] = False
    auto_merge_integration: Literal[False] = False
    auto_merge_trust_core: Literal[False] = False
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

    @field_validator("release_branch_prefix")
    @classmethod
    def valid_release_prefix(cls, value: str) -> str:
        prefix = value.rstrip("/")
        _validate_branch_name(f"{prefix}/candidate", allow_main=False)
        return prefix


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
    last_release_branch: str | None = None
    last_pull_request_url: str | None = None
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
    version: Literal[3] = 3
    release_mode: Literal["pull_request"] = "pull_request"
    base_branch: Literal["main"] = "main"
    candidate_ref: str
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    release_branch: str
    remote_release_sha: str = Field(pattern=SHA_PATTERN.pattern)
    pull_request_number: int = Field(gt=0)
    pull_request_url: str
    draft: Literal[True] = True
    auto_merge: Literal[False] = False
    required_workflow_status: RequiredWorkflowStatus
    updated_at: datetime


class GitHubSyncError(RuntimeError):
    pass


class GitHubDivergenceError(GitHubSyncError):
    pass


class RemoteCIFailure(GitHubSyncError):
    pass


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


def _ensure_release_branch_fast_forward(
    repo_root: Path,
    config: GitHubConfig,
    release_branch: str,
    candidate_sha: str,
) -> None:
    remote_sha = _remote_branch_sha(repo_root, config, release_branch)
    if remote_sha is None or remote_sha == candidate_sha:
        return
    observed = _fetch_branch(repo_root, config, release_branch)
    if observed != remote_sha or not _is_ancestor(repo_root, remote_sha, candidate_sha):
        raise GitHubDivergenceError(
            f"origin/{release_branch} diverged from candidate; force-push is prohibited"
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
    del repo_root, config, refspec
    raise GitHubSyncError("direct main push is disabled by the V3 pull-request release policy")


def push_release_branch_with_retry(
    repo_root: Path,
    config: GitHubConfig,
    *,
    candidate_sha: str,
    release_branch: str,
) -> None:
    if not re.fullmatch(SHA_PATTERN, candidate_sha):
        raise GitHubSyncError("candidate SHA must be a full lowercase commit SHA")
    _validate_branch_name(release_branch, allow_main=False)
    prefix = f"{config.release_branch_prefix}/"
    if not release_branch.startswith(prefix):
        raise GitHubSyncError(f"release branch must start with {prefix!r}")
    refspec = f"{candidate_sha}:refs/heads/{release_branch}"
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
        f"release branch push failed after {config.retry_attempts} attempts: {last_error}"
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
    release_branch: str,
) -> RequiredWorkflowStatus:
    matching = [
        run
        for run in _workflow_runs(repo_root, candidate_sha)
        if run.get("headSha") == candidate_sha
        and run.get("headBranch") == release_branch
        and run.get("event") == "pull_request"
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
    branch = release_branch or f"{config.release_branch_prefix}/unknown"
    deadline = time.monotonic() + config.remote_ci.timeout_seconds
    latest = required_workflow_status(repo_root, config, sha, branch)
    while latest.status == "pending" and time.monotonic() < deadline:
        time.sleep(config.remote_ci.poll_seconds)
        latest = required_workflow_status(repo_root, config, sha, branch)
    if latest.status == "pass":
        return latest.model_dump(mode="json", by_alias=True)
    if latest.status == "fail":
        raise RemoteCIFailure(f"required pull-request workflows failed for {sha[:12]}")
    message = f"timed out waiting for required pull-request workflows on {sha[:12]}"
    if config.remote_ci.fail_closed:
        raise RemoteCIFailure(message)
    return latest.model_dump(mode="json", by_alias=True)


def _pull_request_for_branch(
    repo_root: Path, config: GitHubConfig, release_branch: str
) -> dict[str, Any] | None:
    result = run_command(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--base",
            config.base_branch,
            "--head",
            release_branch,
            "--json",
            "number,url,isDraft,headRefOid,headRefName,baseRefName",
        ],
        cwd=repo_root,
        check=False,
    )
    if result.returncode != 0:
        raise GitHubSyncError(_safe_error(result, "gh pr list failed"))
    try:
        raw_values: object = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise GitHubSyncError("gh pr list returned invalid JSON") from exc
    if not isinstance(raw_values, list) or not raw_values:
        return None
    values = cast(list[object], raw_values)
    if len(values) != 1 or not isinstance(values[0], dict):
        raise GitHubSyncError(f"multiple open pull requests found for {release_branch}")
    return cast(dict[str, Any], values[0])


def _create_or_update_draft_pull_request(
    repo_root: Path,
    config: GitHubConfig,
    *,
    release_branch: str,
    candidate_sha: str,
    title: str,
    body: str,
) -> dict[str, Any]:
    safe_title = redact_sensitive(title).strip()[:120]
    safe_body = redact_sensitive(body).strip()
    existing = _pull_request_for_branch(repo_root, config, release_branch)
    if existing is None:
        result = run_command(
            [
                "gh",
                "pr",
                "create",
                "--draft",
                "--base",
                config.base_branch,
                "--head",
                release_branch,
                "--title",
                safe_title,
                "--body",
                safe_body,
            ],
            cwd=repo_root,
            check=False,
        )
        if result.returncode != 0:
            raise GitHubSyncError(_safe_error(result, "gh pr create failed"))
    else:
        if not existing.get("isDraft"):
            raise GitHubSyncError(
                "existing release pull request is not draft; automatic update refused"
            )
        number = str(existing.get("number"))
        result = run_command(
            ["gh", "pr", "edit", number, "--title", safe_title, "--body", safe_body],
            cwd=repo_root,
            check=False,
        )
        if result.returncode != 0:
            raise GitHubSyncError(_safe_error(result, "gh pr edit failed"))
    observed = _pull_request_for_branch(repo_root, config, release_branch)
    if observed is None:
        raise GitHubSyncError("draft pull request was not observable after create/update")
    if not observed.get("isDraft"):
        raise GitHubSyncError("release pull request must remain draft")
    if observed.get("headRefOid") != candidate_sha:
        raise GitHubSyncError(
            f"pull request head SHA mismatch: expected={candidate_sha}, "
            f"observed={observed.get('headRefOid')}"
        )
    return observed


def _default_pr_body(
    candidate_sha: str, release_branch: str, required_workflows: list[str], reason: str
) -> str:
    checks = "\n".join(f"- [ ] {name}" for name in required_workflows)
    return (
        "## TrainCapsule V3 release candidate\n\n"
        f"Candidate SHA: `{candidate_sha}`\n\n"
        f"Release branch: `{release_branch}`\n\n"
        f"Reason: {reason}\n\n"
        "### Required workflows\n\n"
        f"{checks}\n\n"
        "This pull request is intentionally draft. Auto-merge is disabled; an authorized human "
        "must decide whether to merge after required evidence passes.\n"
    )


def prepare_release_pull_request(
    *,
    repo_root: Path,
    config: GitHubConfig,
    candidate_ref: str,
    candidate_sha: str,
    release_branch: str,
    title: str,
    reason: str,
    metadata_path: Path,
    body: str | None = None,
) -> GitHubReleaseMetadata:
    if not config.enabled:
        raise GitHubSyncError("GitHub synchronization is disabled")
    _validate_branch_name(candidate_ref, allow_main=False)
    _validate_branch_name(release_branch, allow_main=False)
    if current_sha(repo_root, candidate_ref) != candidate_sha:
        raise GitHubSyncError("candidate branch no longer resolves to the verified candidate SHA")
    validate_github_ready(repo_root, config)
    _pre_push_checks(repo_root)
    _ensure_no_divergence(repo_root, config, candidate_sha)
    _ensure_release_branch_fast_forward(repo_root, config, release_branch, candidate_sha)
    if _remote_branch_sha(repo_root, config, release_branch) != candidate_sha:
        push_release_branch_with_retry(
            repo_root,
            config,
            candidate_sha=candidate_sha,
            release_branch=release_branch,
        )
    remote_sha = _remote_branch_sha(repo_root, config, release_branch)
    if remote_sha != candidate_sha:
        raise GitHubSyncError(
            f"remote exact-SHA verification failed: expected={candidate_sha}, observed={remote_sha}"
        )
    verified_remote_sha = cast(str, remote_sha)
    pr = _create_or_update_draft_pull_request(
        repo_root,
        config,
        release_branch=release_branch,
        candidate_sha=candidate_sha,
        title=title,
        body=body
        or _default_pr_body(
            candidate_sha, release_branch, config.remote_ci.required_workflows, reason
        ),
    )
    status = required_workflow_status(repo_root, config, candidate_sha, release_branch)
    metadata = GitHubReleaseMetadata(
        candidate_ref=candidate_ref,
        candidate_sha=candidate_sha,
        release_branch=release_branch,
        remote_release_sha=verified_remote_sha,
        pull_request_number=int(pr["number"]),
        pull_request_url=str(pr["url"]),
        required_workflow_status=status,
        updated_at=datetime.now(UTC),
    )
    write_json(metadata_path, metadata.model_dump(mode="json", by_alias=True))
    latest_path = Path(config.release_metadata_path)
    if not latest_path.is_absolute():
        latest_path = repo_root / latest_path
    write_json(latest_path, metadata.model_dump(mode="json", by_alias=True))
    return metadata


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


def record_verified_task(
    state_path: Path, *, task: TaskPacket | None = None
) -> GitHubSyncState:
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
        "status": "candidate-release-required",
        "candidate_sha": candidate_sha,
        "release_mode": config.release_mode,
        "direct_main_push": config.direct_main_push,
        "message": "use a verified candidate branch to create or update a draft release PR",
    }


def run_remote_ci(
    *,
    repo_root: Path,
    factory: FactoryConfig,
    task: TaskPacket,
    candidate_ref: str,
    candidate_sha: str,
    run_id: str,
    artifact_dir: Path,
) -> dict[str, object]:
    config = load_github_config(factory.resolve(repo_root, factory.github_config_path))
    release_branch = (
        f"{config.release_branch_prefix}/{slugify(task.task_id)}-{candidate_sha[:12]}"
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    metadata = prepare_release_pull_request(
        repo_root=repo_root,
        config=config,
        candidate_ref=candidate_ref,
        candidate_sha=candidate_sha,
        release_branch=release_branch,
        title=f"{task.task_id}: verified TrainCapsule candidate",
        reason=f"factory run {run_id}",
        metadata_path=artifact_dir / "release-metadata.json",
    )
    result = wait_for_remote_ci(
        repo_root,
        config,
        candidate_sha,
        release_branch=release_branch,
    )
    payload: dict[str, object] = {
        "required": True,
        "status": "pass",
        "candidate_sha": candidate_sha,
        "candidate_ref": candidate_ref,
        "release_branch": release_branch,
        "pull_request_url": metadata.pull_request_url,
        "draft": True,
        "auto_merge": False,
        "result": result,
    }
    write_json(artifact_dir / "remote-ci.json", payload)
    return payload
