from __future__ import annotations

from pathlib import Path

from tcfactory.context import build_context_manifest
from tcfactory.gitops import commit_all, current_sha
from tcfactory.models import FactoryConfig, RoleName, SecurityPolicy, Stage, TaskPacket
from tcfactory.util import run_command


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
    assert manifest["previous_findings"] == ["one", "two"]
    assert "transcript" not in manifest
    assert "transcript_path" not in manifest
    assert manifest["role_rules"]["do_not_read_prior_role_transcripts"] is True
