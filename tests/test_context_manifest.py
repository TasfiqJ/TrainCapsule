from __future__ import annotations

from pathlib import Path

import pytest

from tcfactory.config import load_factory_config, load_task
from tcfactory.context import ContextPolicyError, build_context_manifest
from tcfactory.feature_ledger import load_feature_ledger
from tcfactory.gitops import commit_all, current_sha
from tcfactory.models import FactoryConfig, RoleName, SecurityPolicy, Stage, TaskPacket
from tcfactory.planner import planning_task_for
from tcfactory.risk import load_risk_profiles
from tcfactory.util import run_command
from tcfactory.yamlutil import load_yaml

ROOT = Path(__file__).resolve().parents[1]


def test_context_manifest_uses_paths_not_transcripts(tmp_path: Path) -> None:
    run_command(["git", "init", "-b", "main"], cwd=tmp_path)
    run_command(["git", "config", "user.name", "Test User"], cwd=tmp_path)
    run_command(["git", "config", "user.email", "test@example.com"], cwd=tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "config/context.yaml").write_text("max_previous_findings: 2\n")
    (tmp_path / "docs/CONTEXT_INDEX.yaml").write_text(
        "version: 1\nkeys:\n  web_product:\n    paths: [docs/plan.md]\n    sections: [web]\n"
    )
    (tmp_path / "docs/plan.md").write_text("plan\n")
    (tmp_path / "SOURCE_PRECEDENCE.md").write_text("authority and loading precedence\n")
    (tmp_path / "app.py").write_text("x = 1\n")
    commit_all(tmp_path, "start")
    base = current_sha(tmp_path)
    task = TaskPacket(
        task_id="T900",
        title="test",
        phase="test",
        goal="test",
        source_of_truth=["docs/plan.md"],
        acceptance_criteria=["works"],
        outputs=["app.py"],
        stop_conditions=["blocked"],
        security=SecurityPolicy(),
        pipeline=[Stage(role=RoleName.BUILDER, allowed_paths=["app.py"])],
        context_keys=["web_product"],
    )
    manifest = build_context_manifest(
        repo_root=tmp_path,
        worktree=tmp_path,
        config=FactoryConfig(),
        task=task,
        stage=task.pipeline[0],
        base_sha=base,
        previous_findings=["one", "two", "three"],
    )
    assert manifest["policy"] == "just_in_time_paths_not_transcripts"
    assert manifest["context_keys"][0]["paths"] == ["docs/plan.md"]
    assert manifest["previous_findings"] == ["three", "two"]
    assert "transcript" not in manifest
    assert "transcript_path" not in manifest
    assert manifest["role_rules"]["do_not_read_prior_role_transcripts"] is True


def test_context_manifest_rejects_unknown_required_key(tmp_path: Path) -> None:
    run_command(["git", "init", "-b", "main"], cwd=tmp_path)
    run_command(["git", "config", "user.name", "Test User"], cwd=tmp_path)
    run_command(["git", "config", "user.email", "test@example.com"], cwd=tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "config/context.yaml").write_text("max_previous_findings: 2\n")
    (tmp_path / "docs/CONTEXT_INDEX.yaml").write_text("version: 1\nkeys: {}\n")
    (tmp_path / "docs/plan.md").write_text("authority\n")
    (tmp_path / "SOURCE_PRECEDENCE.md").write_text("authority and loading precedence\n")
    commit_all(tmp_path, "start")
    task = TaskPacket(
        task_id="T901",
        title="test",
        phase="test",
        goal="test",
        source_of_truth=["docs/plan.md"],
        acceptance_criteria=["works"],
        outputs=["app.py"],
        stop_conditions=["blocked"],
        security=SecurityPolicy(),
        pipeline=[Stage(role=RoleName.BUILDER, allowed_paths=["app.py"])],
        context_keys=["missing-key"],
    )
    with pytest.raises(ContextPolicyError, match="Unknown required context keys"):
        build_context_manifest(
            repo_root=tmp_path,
            worktree=tmp_path,
            config=FactoryConfig(),
            task=task,
            stage=task.pipeline[0],
            base_sha=current_sha(tmp_path),
            previous_findings=[],
        )


def test_context_manifest_never_falls_back_to_live_repo_source(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    worktree = tmp_path / "candidate"
    repo.mkdir()
    worktree.mkdir()
    run_command(["git", "init", "-b", "main"], cwd=worktree)
    run_command(["git", "config", "user.name", "Test User"], cwd=worktree)
    run_command(["git", "config", "user.email", "test@example.com"], cwd=worktree)
    (worktree / "config").mkdir()
    (worktree / "docs").mkdir()
    (worktree / "config/context.yaml").write_text("max_previous_findings: 2\n")
    (worktree / "docs/CONTEXT_INDEX.yaml").write_text("version: 1\nkeys: {}\n")
    (worktree / "SOURCE_PRECEDENCE.md").write_text(
        "authority and loading precedence\n"
    )
    (repo / "config").mkdir()
    (repo / "docs").mkdir()
    (repo / "config/context.yaml").write_text("max_previous_findings: 2\n")
    (repo / "docs/CONTEXT_INDEX.yaml").write_text("version: 1\nkeys: {}\n")
    (repo / "docs/only-live.md").write_text("stale live source\n")
    commit_all(worktree, "start")
    task = TaskPacket(
        task_id="T902",
        title="test",
        phase="test",
        goal="test",
        source_of_truth=["docs/only-live.md"],
        acceptance_criteria=["works"],
        outputs=["app.py"],
        stop_conditions=["blocked"],
        security=SecurityPolicy(),
        pipeline=[Stage(role=RoleName.BUILDER, allowed_paths=["app.py"])],
    )
    with pytest.raises(ContextPolicyError, match="candidate worktree"):
        build_context_manifest(
            repo_root=repo,
            worktree=worktree,
            config=FactoryConfig(),
            task=task,
            stage=task.pipeline[0],
            base_sha=current_sha(worktree),
            previous_findings=[],
        )


def test_repository_role_default_contexts_resolve_to_existing_sources() -> None:
    context_config = load_yaml(ROOT / "config/context.yaml")
    context_index = load_yaml(ROOT / "docs/CONTEXT_INDEX.yaml")
    contexts = context_index["contexts"]
    for role, keys in context_config["role_defaults"].items():
        for key in keys:
            assert key in contexts, f"{role} references unknown context key {key}"
            for source in contexts[key]:
                assert (ROOT / source).is_file(), (
                    f"{role} context {key} references missing source {source}"
                )


def test_live_t002_and_planning_packets_build_candidate_bound_context() -> None:
    config = load_factory_config(ROOT / "config/factory.yaml")
    base_sha = current_sha(ROOT)
    t002 = load_task(ROOT / "tasks/T002.yaml")
    research = next(stage for stage in t002.pipeline if stage.role == RoleName.RESEARCH)
    research_manifest = build_context_manifest(
        repo_root=ROOT,
        worktree=ROOT,
        config=config,
        task=t002,
        stage=research,
        base_sha=base_sha,
        previous_findings=[],
    )
    assert research_manifest["files"]

    ledger = load_feature_ledger(ROOT / "factory/feature_ledger.yaml")
    profiles = load_risk_profiles(ROOT / "config/risk_profiles.yaml")
    planning = planning_task_for(ledger.item("T002"), profiles=profiles)
    planning_manifest = build_context_manifest(
        repo_root=ROOT,
        worktree=ROOT,
        config=config,
        task=planning,
        stage=planning.pipeline[0],
        base_sha=base_sha,
        previous_findings=[],
    )
    assert planning_manifest["files"]
