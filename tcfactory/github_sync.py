from __future__ import annotations

import json
import shutil
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from .gitops import current_branch, current_sha, is_clean
from .models import FactoryConfig, RiskTier, TaskPacket
from .util import read_json, run_command, write_json
from .yamlutil import load_yaml


class RemoteCIConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    workflow_name: str = "AI factory quality"
    required_risk_tiers: list[RiskTier] = Field(
        default_factory=lambda: [RiskTier.INTEGRATION, RiskTier.TRUST_CORE]
    )
    timeout_seconds: int = Field(default=1800, ge=60, le=14_400)
    poll_seconds: int = Field(default=20, ge=5, le=300)
    fail_closed: bool = True


class GitHubConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    enabled: bool = False
    remote: Literal["origin"] = "origin"
    branch: Literal["main"] = "main"
    visibility: str = "private"
    repository: str | None = None
    push_after_verified_tasks: int = Field(default=3, ge=1, le=50)
    push_interval_seconds: int = Field(default=3600, ge=60, le=86_400)
    push_before_quota_pause: bool = True
    push_at_completion: bool = True
    immediate_risk_tiers: list[RiskTier] = Field(
        default_factory=lambda: [RiskTier.INTEGRATION, RiskTier.TRUST_CORE]
    )
    retry_attempts: int = Field(default=5, ge=1, le=10)
    retry_backoff_seconds: int = Field(default=30, ge=1, le=3600)
    verify_remote_sha: bool = True
    wait_for_main_ci_after_push: bool = True
    commit_subject_max_chars: int = Field(default=50, ge=20, le=72)
    remote_ci: RemoteCIConfig = Field(default_factory=RemoteCIConfig)


class GitHubSyncState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    tasks_since_push: int = 0
    last_push_at: datetime | None = None
    last_pushed_sha: str | None = None
    last_reason: str | None = None
    last_error: str | None = None
    pending: bool = False
    last_task_id: str | None = None
    last_task_risk: RiskTier | None = None


class GitHubSyncError(RuntimeError):
    pass


class GitHubDivergenceError(GitHubSyncError):
    pass


class RemoteCIFailure(GitHubSyncError):
    pass


# Backward-compatible spelling retained for older pipeline imports.
GithubSyncError = GitHubSyncError


def load_github_config(path: Path) -> GitHubConfig:
    if not path.exists():
        return GitHubConfig(enabled=False)
    raw = load_yaml(path)
    return GitHubConfig.model_validate(raw)


def load_github_state(path: Path) -> GitHubSyncState:
    if not path.exists():
        return GitHubSyncState()
    return GitHubSyncState.model_validate(read_json(path, {}))


def save_github_state(path: Path, state: GitHubSyncState) -> None:
    write_json(path, state.model_dump(mode="json"))


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
        raise GitHubSyncError(view.stderr.strip() or "gh repo view failed")
    try:
        metadata = json.loads(view.stdout)
    except json.JSONDecodeError as exc:
        raise GitHubSyncError("GitHub repository metadata was not valid JSON") from exc
    visibility = str(metadata.get("visibility", "")).lower()
    if config.visibility == "private" and visibility != "private":
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


def validate_github_ready(repo_root: Path, config: GitHubConfig) -> dict[str, str]:
    if not config.enabled:
        raise GitHubSyncError("GitHub synchronization is disabled")
    if not is_clean(repo_root):
        raise GitHubSyncError("Repository must be clean before GitHub synchronization")
    branch = current_branch(repo_root)
    if branch != config.branch:
        raise GitHubSyncError(
            f"GitHub sync requires branch {config.branch!r}; current branch is {branch!r}"
        )
    return _gh_ready(repo_root, config)


def _remote_sha(repo_root: Path, config: GitHubConfig) -> str | None:
    result = run_command(
        ["git", "ls-remote", config.remote, f"refs/heads/{config.branch}"],
        cwd=repo_root,
        check=False,
    )
    if result.returncode != 0:
        raise GitHubSyncError(result.stderr.strip() or "git ls-remote failed")
    line = result.stdout.strip()
    return line.split()[0] if line else None


def _ensure_no_divergence(repo_root: Path, config: GitHubConfig, local_sha: str) -> None:
    remote_head = _remote_sha(repo_root, config)
    if remote_head is None or remote_head == local_sha:
        return
    fetch = run_command(
        ["git", "fetch", "--prune", config.remote, config.branch],
        cwd=repo_root,
        check=False,
    )
    if fetch.returncode != 0:
        raise GitHubSyncError(fetch.stderr.strip() or "git fetch failed")
    remote_ref = f"refs/remotes/{config.remote}/{config.branch}"
    if (
        run_command(
            ["git", "show-ref", "--verify", "--quiet", remote_ref],
            cwd=repo_root,
            check=False,
        ).returncode
        != 0
    ):
        return
    remote_sha = current_sha(repo_root, remote_ref)
    if remote_sha == local_sha:
        return
    remote_is_ancestor = (
        run_command(
            ["git", "merge-base", "--is-ancestor", remote_sha, local_sha],
            cwd=repo_root,
            check=False,
        ).returncode
        == 0
    )
    if not remote_is_ancestor:
        raise GitHubDivergenceError(
            f"{config.remote}/{config.branch} is not an ancestor of local {config.branch}. "
            "The factory refuses to overwrite human or external work and never force-pushes."
        )


def _pre_push_checks(repo_root: Path) -> None:
    script = repo_root / "scripts" / "verify_no_secrets.sh"
    if script.exists():
        result = run_command(["bash", str(script)], cwd=repo_root, check=False)
        if result.returncode != 0:
            raise GitHubSyncError(
                result.stderr.strip() or result.stdout.strip() or "secret scan failed"
            )
    fsck = run_command(["git", "fsck", "--no-dangling"], cwd=repo_root, check=False)
    if fsck.returncode != 0:
        raise GitHubSyncError(fsck.stderr.strip() or "git fsck failed")


def push_main_with_retry(repo_root: Path, config: GitHubConfig, refspec: str) -> None:
    expected_refspec = "refs/heads/main:refs/heads/main"
    if config.remote != "origin" or config.branch != "main" or refspec != expected_refspec:
        raise GitHubSyncError(
            "Factory pushes are restricted to origin refs/heads/main:refs/heads/main"
        )
    last_error = ""
    for attempt in range(1, config.retry_attempts + 1):
        result = run_command(
            ["git", "push", "--porcelain", "origin", expected_refspec],
            cwd=repo_root,
            check=False,
        )
        if result.returncode == 0:
            return
        last_error = result.stderr.strip() or result.stdout.strip()
        if attempt < config.retry_attempts:
            time.sleep(config.retry_backoff_seconds * attempt)
    raise GitHubSyncError(f"git push failed after {config.retry_attempts} attempts: {last_error}")


def _workflow_runs(repo_root: Path, sha: str) -> list[dict[str, Any]]:
    result = run_command(
        [
            "gh",
            "run",
            "list",
            "--commit",
            sha,
            "--limit",
            "30",
            "--json",
            "databaseId,status,conclusion,workflowName,headSha,headBranch,event,createdAt,url",
        ],
        cwd=repo_root,
        check=False,
    )
    if result.returncode != 0:
        raise GitHubSyncError(result.stderr.strip() or "gh run list failed")
    try:
        value = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise GitHubSyncError("gh run list returned invalid JSON") from exc
    return cast(list[dict[str, Any]], value) if isinstance(value, list) else []


def _run_created_at(run: dict[str, Any]) -> datetime | None:
    value = run.get("createdAt")
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def wait_for_remote_ci(
    repo_root: Path,
    config: GitHubConfig,
    sha: str,
    *,
    not_before: datetime | None = None,
) -> dict[str, Any]:
    ci = config.remote_ci
    deadline = time.monotonic() + ci.timeout_seconds
    last_runs: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        runs = [
            run
            for run in _workflow_runs(repo_root, sha)
            if run.get("workflowName") == ci.workflow_name
            and run.get("headSha") == sha
            and run.get("headBranch") == config.branch
            and run.get("event") == "push"
            and (
                not_before is None
                or (
                    (created_at := _run_created_at(run)) is not None
                    and created_at >= not_before
                )
            )
        ]
        runs.sort(
            key=lambda run: (
                _run_created_at(run) or datetime.min.replace(tzinfo=UTC),
                int(run.get("databaseId") or 0),
            ),
            reverse=True,
        )
        latest = runs[:1]
        last_runs = latest
        if not runs:
            time.sleep(ci.poll_seconds)
            continue
        if latest[0].get("status") != "completed":
            time.sleep(ci.poll_seconds)
            continue
        if latest[0].get("conclusion") != "success":
            raise RemoteCIFailure(
                f"Remote workflow {ci.workflow_name!r} failed for {sha[:12]}: {latest}"
            )
        return {"status": "pass", "runs": latest}
    message = (
        f"Timed out waiting for workflow {ci.workflow_name!r} on {sha[:12]}; "
        f"last observed runs: {last_runs}"
    )
    if ci.fail_closed:
        raise RemoteCIFailure(message)
    return {"status": "timeout-warning", "runs": last_runs}


def should_push(
    *,
    config: GitHubConfig,
    state: GitHubSyncState,
    task: TaskPacket | None,
    force: bool,
    now: datetime,
) -> bool:
    if force:
        return True
    task_risk = task.risk_tier if task is not None else state.last_task_risk
    if task_risk in config.immediate_risk_tiers:
        return state.tasks_since_push > 0
    if state.tasks_since_push >= config.push_after_verified_tasks:
        return True
    if state.tasks_since_push == 0:
        return False
    if state.last_push_at is None:
        return True
    elapsed = (now - state.last_push_at).total_seconds()
    return state.pending and elapsed >= config.push_interval_seconds


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

    metadata = validate_github_ready(repo_root, config)
    local_sha = current_sha(repo_root, config.branch)
    try:
        _pre_push_checks(repo_root)
        _ensure_no_divergence(repo_root, config, local_sha)
        pushed_at: datetime | None = None
        if _remote_sha(repo_root, config) != local_sha:
            pushed_at = datetime.now(UTC) - timedelta(seconds=30)
            push_main_with_retry(
                repo_root,
                config,
                "refs/heads/main:refs/heads/main",
            )
        if config.verify_remote_sha:
            observed = _remote_sha(repo_root, config)
            if observed != local_sha:
                raise GitHubSyncError(
                    f"Remote verification failed: local={local_sha}, remote={observed}"
                )
        main_ci: dict[str, Any] | None = None
        if config.remote_ci.enabled and config.wait_for_main_ci_after_push:
            main_ci = wait_for_remote_ci(
                repo_root,
                config,
                local_sha,
                not_before=pushed_at,
            )
        state.tasks_since_push = 0
        state.last_push_at = now
        state.last_pushed_sha = local_sha
        state.last_reason = reason
        state.last_error = None
        state.pending = False
        save_github_state(state_path, state)
        return {
            "status": "pushed",
            "sha": local_sha,
            "repository": metadata,
            "main_ci": main_ci,
        }
    except Exception as exc:
        state.last_error = f"{type(exc).__name__}: {exc}"
        state.pending = True
        save_github_state(state_path, state)
        raise


def run_remote_ci(
    *,
    repo_root: Path,
    factory: FactoryConfig,
    task: TaskPacket,
    candidate_sha: str,
    run_id: str,
    artifact_dir: Path,
) -> dict[str, object]:
    """Run GitHub Actions for a candidate already promoted locally to ``main``.

    TrainCapsule uses a single-branch remote policy.  Pre-promotion candidates are
    verified by local and private gates; remote CI starts only after the exact release
    commit becomes local ``main`` and is pushed to ``origin/main``.
    """

    config_path = factory.resolve(repo_root, factory.github_config_path)
    config = load_github_config(config_path)
    if not config.enabled:
        raise GitHubSyncError(
            "Task requires remote CI but GitHub synchronization is disabled. "
            "Complete scripts/configure_github.sh first."
        )
    _gh_ready(repo_root, config)
    _pre_push_checks(repo_root)
    local_main_sha = current_sha(repo_root, "main")
    if candidate_sha != local_main_sha:
        raise GitHubSyncError(
            "Remote CI may only push the current local main commit; "
            f"candidate={candidate_sha}, main={local_main_sha}"
        )
    _ensure_no_divergence(repo_root, config, candidate_sha)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    pushed_at: datetime | None = None
    if _remote_sha(repo_root, config) != candidate_sha:
        pushed_at = datetime.now(UTC) - timedelta(seconds=30)
        push_main_with_retry(
            repo_root,
            config,
            "refs/heads/main:refs/heads/main",
        )
    try:
        result = wait_for_remote_ci(
            repo_root,
            config,
            candidate_sha,
            not_before=pushed_at,
        )
        payload: dict[str, object] = {
            "required": True,
            "status": "pass",
            "candidate_sha": candidate_sha,
            "branch": "main",
            "workflow": config.remote_ci.workflow_name,
            "result": result,
        }
        write_json(artifact_dir / "remote-ci.json", payload)
        return payload
    except Exception as exc:
        payload = {
            "required": True,
            "status": "fail",
            "candidate_sha": candidate_sha,
            "branch": "main",
            "workflow": config.remote_ci.workflow_name,
            "error": f"{type(exc).__name__}: {exc}",
            "runs": _workflow_runs(repo_root, candidate_sha),
        }
        write_json(artifact_dir / "remote-ci.json", payload)
        raise GitHubSyncError(str(exc)) from exc
