from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
import time
from pathlib import Path

from .models import Gate, GateResult, RoleName
from .util import path_matches


class PathPolicyError(RuntimeError):
    pass


class PrivateGateError(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    """Return an inspectable identity for an external gate executable."""

    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise PrivateGateError(f"Private gate runner is not a file: {resolved}")
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_ALLOWED_DIRECT = {"pytest", "ruff", "pyright"}
_ALLOWED_UV_RUN = {"python", "pytest", "ruff", "pyright", "tcfactory"}
_SHELL_META = (";", "&&", "||", "|", "`", "$(", ">", "<", "\n", "\r")


def _safe_repo_script(cwd: Path, raw: str, prefix: str) -> bool:
    path = (cwd / raw).resolve()
    root = cwd.resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return False
    return relative.startswith(prefix) and path.is_file()


def gate_argv(command: str, *, cwd: Path) -> list[str]:
    """Convert an approved deterministic gate command to argv.

    Model-authored task packets are never allowed to smuggle arbitrary shell programs into the
    controller. Shell composition, redirection, substitutions, environment assignments, network
    clients, Git mutation, and inline Python are rejected. Complex checks must be implemented as
    reviewed scripts under ``scripts/gates/`` and invoked directly.
    """

    stripped = command.strip()
    if not stripped or any(marker in stripped for marker in _SHELL_META):
        raise PathPolicyError(f"Unsafe gate command syntax: {command!r}")
    try:
        argv = shlex.split(stripped, posix=True)
    except ValueError as exc:
        raise PathPolicyError(f"Invalid gate command quoting: {command!r}") from exc
    if not argv:
        raise PathPolicyError("Gate command is empty")
    if any("=" in token and index == 0 for index, token in enumerate(argv)):
        raise PathPolicyError("Gate commands may not set controller environment variables")

    executable = argv[0]
    if executable in _ALLOWED_DIRECT:
        return argv
    if executable in {"python", "python3"}:
        if len(argv) >= 3 and argv[1] == "-m" and argv[2] == "pytest":
            return argv
        if len(argv) >= 2 and _safe_repo_script(cwd, argv[1], "scripts/gates/"):
            return argv
        raise PathPolicyError("Python gates must run pytest or a reviewed scripts/gates file")
    if executable == "bash":
        if len(argv) >= 2 and _safe_repo_script(cwd, argv[1], "scripts/gates/"):
            return argv
        raise PathPolicyError("Bash gates must invoke a reviewed scripts/gates file")
    if executable == "uv" and len(argv) >= 3 and argv[1] == "run":
        nested = argv[2]
        if nested not in _ALLOWED_UV_RUN:
            raise PathPolicyError(f"uv run target is not allowed: {nested}")
        if nested == "python":
            if len(argv) >= 5 and argv[3] == "-m" and argv[4] == "pytest":
                return argv
            if len(argv) >= 4 and _safe_repo_script(cwd, argv[3], "scripts/gates/"):
                return argv
            raise PathPolicyError(
                "uv run python gates must run pytest or a reviewed scripts/gates file"
            )
        return argv
    raise PathPolicyError(f"Gate executable is not allowlisted: {executable}")


def validate_changed_paths(
    changed: list[str], *, allowed: list[str], forbidden: list[str], read_only: bool
) -> None:
    if read_only and changed:
        raise PathPolicyError(f"Read-only stage changed files: {changed}")
    violations: list[str] = []
    for path in changed:
        if forbidden and path_matches(path, forbidden):
            violations.append(f"forbidden:{path}")
            continue
        if allowed and not path_matches(path, allowed):
            violations.append(f"outside-allowlist:{path}")
    if violations:
        raise PathPolicyError("Changed-file policy violations: " + ", ".join(violations))


def select_gates(gates: list[Gate], role: RoleName, names: list[str]) -> list[Gate]:
    selected: list[Gate] = []
    requested = set(names)
    for gate in gates:
        if requested and gate.name not in requested:
            continue
        if gate.stages and role not in gate.stages:
            continue
        selected.append(gate)
    return selected


def _execute_gate_command(
    *,
    args: list[str],
    display_command: str,
    name: str,
    cwd: Path,
    artifact_dir: Path,
    timeout_seconds: int,
    env: dict[str, str] | None = None,
) -> GateResult:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = artifact_dir / f"gate-{name}.stdout.txt"
    stderr_path = artifact_dir / f"gate-{name}.stderr.txt"
    started = time.monotonic()
    timed_out = False
    return_code = 1
    stdout = ""
    stderr = ""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            env=merged_env,
        )
        return_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        return_code = 124
        raw_stdout = exc.stdout or ""
        raw_stderr = exc.stderr or ""
        stdout = (
            raw_stdout.decode("utf-8", errors="replace")
            if isinstance(raw_stdout, bytes)
            else raw_stdout
        )
        stderr_text = (
            raw_stderr.decode("utf-8", errors="replace")
            if isinstance(raw_stderr, bytes)
            else raw_stderr
        )
        stderr = stderr_text + f"\nTimed out after {timeout_seconds}s\n"
    duration = time.monotonic() - started
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    return GateResult(
        name=name,
        command=display_command,
        return_code=return_code,
        duration_seconds=duration,
        passed=return_code == 0,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        timed_out=timed_out,
    )


def run_gate(gate: Gate, *, cwd: Path, artifact_dir: Path) -> GateResult:
    argv = gate_argv(gate.command, cwd=cwd)
    return _execute_gate_command(
        args=argv,
        display_command=gate.command,
        name=gate.name,
        cwd=cwd,
        artifact_dir=artifact_dir,
        timeout_seconds=gate.timeout_seconds,
    )


def run_private_gate(
    *,
    runner: Path,
    suite: str,
    cwd: Path,
    repo_root: Path,
    artifact_dir: Path,
    timeout_seconds: int,
    task_id: str,
    run_id: str,
    candidate_sha: str,
) -> GateResult:
    resolved_runner = runner.expanduser().resolve()
    if not resolved_runner.exists():
        raise PrivateGateError(f"Private gate runner does not exist: {resolved_runner}")
    try:
        resolved_runner.relative_to(repo_root.resolve())
    except ValueError:
        pass
    else:
        raise PrivateGateError(
            "Private gate runner must live outside the agent-visible repository."
        )
    if not resolved_runner.is_file():
        raise PrivateGateError(f"Private gate runner is not a file: {resolved_runner}")

    safe_name = (
        "private-"
        + "".join(char if char.isalnum() or char in "-_." else "-" for char in suite)[:80]
    )
    return _execute_gate_command(
        args=[str(resolved_runner), suite, str(cwd)],
        display_command=f"<external-private-gate> {suite} <candidate-worktree>",
        name=safe_name,
        cwd=cwd,
        artifact_dir=artifact_dir,
        timeout_seconds=timeout_seconds,
        env={
            "TCF_TASK_ID": task_id,
            "TCF_RUN_ID": run_id,
            "TCF_CANDIDATE_SHA": candidate_sha,
            "TCF_CANDIDATE_WORKTREE": str(cwd),
        },
    )
