import json
import os
import subprocess
from pathlib import Path

HOOK = Path(".claude/hooks/path_guard.py").resolve()


def run_hook(payload: dict[str, object], **env: str) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(
        ["python3", str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=merged,
        check=False,
    )


def test_write_outside_allowlist_is_denied(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    result = run_hook(
        {"tool_name": "Write", "tool_input": {"file_path": str(root / "blocked.txt")}},
        TCF_REPO_ROOT=str(root),
        TCF_ALLOWED_PATHS_JSON=json.dumps(["src/**"]),
        TCF_FORBIDDEN_PATHS_JSON="[]",
        TCF_READ_ONLY="0",
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_safe_write_is_silent(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    result = run_hook(
        {"tool_name": "Write", "tool_input": {"file_path": str(root / "src" / "ok.py")}},
        TCF_REPO_ROOT=str(root),
        TCF_ALLOWED_PATHS_JSON=json.dumps(["src/**"]),
        TCF_FORBIDDEN_PATHS_JSON="[]",
        TCF_READ_ONLY="0",
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_git_push_is_denied(tmp_path: Path) -> None:
    result = run_hook(
        {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
        TCF_REPO_ROOT=str(tmp_path),
        TCF_ALLOWED_PATHS_JSON="[]",
        TCF_FORBIDDEN_PATHS_JSON="[]",
        TCF_READ_ONLY="0",
    )
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_web_search_requires_allowed_site_filter(tmp_path: Path) -> None:
    result = run_hook(
        {"tool_name": "WebSearch", "tool_input": {"query": "Claude SDK docs"}},
        TCF_REPO_ROOT=str(tmp_path),
        TCF_ALLOWED_PATHS_JSON="[]",
        TCF_FORBIDDEN_PATHS_JSON="[]",
        TCF_ALLOWED_DOMAINS_JSON=json.dumps(["docs.anthropic.com"]),
        TCF_READ_ONLY="1",
    )
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_web_search_with_allowed_site_filter_is_silent(tmp_path: Path) -> None:
    result = run_hook(
        {
            "tool_name": "WebSearch",
            "tool_input": {"query": "Claude SDK site:docs.anthropic.com"},
        },
        TCF_REPO_ROOT=str(tmp_path),
        TCF_ALLOWED_PATHS_JSON="[]",
        TCF_FORBIDDEN_PATHS_JSON="[]",
        TCF_ALLOWED_DOMAINS_JSON=json.dumps(["docs.anthropic.com"]),
        TCF_READ_ONLY="1",
    )
    assert result.stdout == ""


def test_read_outside_worktree_is_denied(tmp_path: Path) -> None:
    root = (tmp_path / "repo").resolve()
    root.mkdir()
    result = run_hook(
        {"tool_name": "Read", "tool_input": {"file_path": str(tmp_path / "secret.txt")}},
        TCF_REPO_ROOT=str(root),
        TCF_ALLOWED_PATHS_JSON="[]",
        TCF_FORBIDDEN_PATHS_JSON="[]",
        TCF_READ_ONLY="0",
    )
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_read_inside_worktree_is_silent(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    result = run_hook(
        {"tool_name": "Read", "tool_input": {"file_path": str(root / "README.md")}},
        TCF_REPO_ROOT=str(root),
        TCF_ALLOWED_PATHS_JSON="[]",
        TCF_FORBIDDEN_PATHS_JSON="[]",
        TCF_READ_ONLY="1",
    )
    assert result.stdout == ""


def test_grep_outside_worktree_is_denied(tmp_path: Path) -> None:
    root = (tmp_path / "repo").resolve()
    root.mkdir()
    result = run_hook(
        {"tool_name": "Grep", "tool_input": {"pattern": "token", "path": str(tmp_path)}},
        TCF_REPO_ROOT=str(root),
        TCF_ALLOWED_PATHS_JSON="[]",
        TCF_FORBIDDEN_PATHS_JSON="[]",
        TCF_READ_ONLY="1",
    )
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_glob_inside_worktree_is_silent(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    result = run_hook(
        {"tool_name": "Glob", "tool_input": {"pattern": "**/*.py", "path": str(root)}},
        TCF_REPO_ROOT=str(root),
        TCF_ALLOWED_PATHS_JSON="[]",
        TCF_FORBIDDEN_PATHS_JSON="[]",
        TCF_READ_ONLY="1",
    )
    assert result.stdout == ""


def test_powershell_escape_is_denied(tmp_path: Path) -> None:
    result = run_hook(
        {"tool_name": "Bash", "tool_input": {"command": "powershell.exe Get-Content C:\\secret"}},
        TCF_REPO_ROOT=str(tmp_path),
        TCF_ALLOWED_PATHS_JSON="[]",
        TCF_FORBIDDEN_PATHS_JSON="[]",
        TCF_READ_ONLY="0",
    )
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
