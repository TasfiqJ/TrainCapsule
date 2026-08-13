from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tcfactory.context import ContextPolicyError, build_context_manifest, build_v3_context_manifest
from tcfactory.gitops import commit_all, current_sha
from tcfactory.models import FactoryConfig, RoleName, SecurityPolicy, Stage, TaskPacket
from tcfactory.util import run_command
from tcfactory.v3.work_items import WorkItemCollection
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
    assert context_config["version"] == 3
    assert context_index["version"] == 4
    groups = context_index["groups"]
    for role, names in context_config["roleDefaultGroups"].items():
        for name in names:
            assert name in groups, f"{role} references unknown context group {name}"
            assert role in groups[name]["includeRoles"]
            assert role not in groups[name]["excludeRoles"]
            for entry in groups[name]["entries"]:
                assert (ROOT / entry["path"]).is_file()
                assert len(entry["sha256"]) == 64
                assert entry["authoritySections"]


def test_v3_research_context_is_bound_and_t002_stays_historical() -> None:
    roadmap = WorkItemCollection.model_validate(
        load_yaml(ROOT / "factory/roadmap/work_items.yaml")
    )
    item = next(
        item
        for item in roadmap.work_items
        if item.kind.value == "RESEARCH" and item.automatable
    )
    policy = load_yaml(ROOT / "config/context.yaml")
    manifest = build_v3_context_manifest(
        repo_root=ROOT,
        work_item=item,
        role="research",
        requested_groups=policy["roleDefaultGroups"]["research"],
        max_context_chars=policy["defaultMaxContextCharacters"],
        freshness_receipts={
            name: datetime.now(UTC) for name in policy["roleDefaultGroups"]["research"]
        },
    )
    assert manifest.entries
    assert manifest.work_item_id == item.work_item_id
    migration = load_yaml(ROOT / "factory/roadmap/migrations/v2_to_v3.yaml")
    t002 = next(
        record for record in migration["records"] if record["legacyTaskId"] == "T002"
    )
    assert t002["v3Disposition"] == "DEFERRED_NON_BLOCKING"
    assert t002["mappedWorkItems"] == []
    assert "never auto-resumes" in t002["reason"]
