#!/usr/bin/env python3
"""Build the inert, inventory-pinned Python distribution for deployment.

This runs only in the trusted build workspace.  The privileged installer never
invokes uv, pip, a project build hook, or any bytes from the candidate tree.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from deployment.repository_snapshot import materialize_exact_repository_tree
from deployment.runtime_distribution import (
    COMPLETE_RUNTIME_IMPORTS,
    PRODUCTION_RUNTIME_IMPORTS,
    PROJECT_RUNTIME_IMPORTS,
    PROJECT_SOURCE_MAPPINGS,
    RuntimeDistributionManifest,
    build_runtime_distribution,
    extract_runtime_distribution,
)


def _run(arguments: list[str], *, cwd: Path) -> None:
    result = subprocess.run(
        arguments,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=900,
        env={
            "HOME": os.environ.get("HOME", "/nonexistent"),
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
            "UV_NO_PROGRESS": "1",
        },
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout)[-4000:]
        raise RuntimeError(f"runtime dependency build failed: {detail}")


def project_runtime_source_files(source_root: Path) -> list[tuple[Path, Path]]:
    """Return production sources while excluding package-local test trees."""

    selected: list[tuple[Path, Path]] = []
    for source in sorted(source_root.rglob("*.py")):
        if source.is_symlink() or not source.is_file():
            raise RuntimeError("project runtime source contains a link")
        relative = source.relative_to(source_root)
        if relative.parts and relative.parts[0] == "tests":
            continue
        selected.append((source, relative))
    return selected


def build_production_runtime(
    *,
    repo_root: Path,
    python_root: Path,
    uv_executable: Path,
    output: Path,
) -> tuple[Path, Path]:
    repo = repo_root.resolve(strict=True)
    python = (python_root / "bin/python3.12").resolve(strict=True)
    uv = uv_executable.resolve(strict=True)
    if not (repo / "uv.lock").is_file() or not python.is_file() or not uv.is_file():
        raise RuntimeError("runtime build inputs are incomplete")
    with tempfile.TemporaryDirectory(prefix="traincapsule-runtime-build-") as temporary:
        stage = Path(temporary)
        exact_repo = stage / "repository"
        materialize_exact_repository_tree(repo, "HEAD", exact_repo)
        requirements = stage / "requirements.txt"
        dependencies = stage / "site-packages"
        dependencies.mkdir()
        _run(
            [
                str(uv),
                "export",
                "--frozen",
                "--no-dev",
                "--no-hashes",
                "--no-emit-project",
                "--no-emit-workspace",
                "--no-emit-local",
                "--format",
                "requirements-txt",
                "--output-file",
                str(requirements),
            ],
            cwd=exact_repo,
        )
        _run(
            [
                str(uv),
                "pip",
                "install",
                "--python",
                str(python),
                "--target",
                str(dependencies),
                "--only-binary",
                ":all:",
                "--link-mode",
                "copy",
                "--no-compile",
                "--requirements",
                str(requirements),
            ],
            cwd=exact_repo,
        )
        for cache in dependencies.rglob("__pycache__"):
            shutil.rmtree(cache)
        for compiled in dependencies.rglob("*.pyc"):
            compiled.unlink()
        for source_prefix, target_prefix in PROJECT_SOURCE_MAPPINGS:
            source_root = exact_repo / source_prefix.rstrip("/")
            if source_root.is_symlink() or not source_root.is_dir():
                raise RuntimeError("project runtime source root is unavailable")
            for source, relative in project_runtime_source_files(source_root):
                target = dependencies / target_prefix / relative
                if target.exists() or target.is_symlink():
                    raise RuntimeError("project runtime source collides with a dependency")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
                target.chmod(0o644)
        archive, manifest = build_runtime_distribution(
            output,
            python_root=python_root,
            dependency_root=dependencies,
            python_version="3.12.13",
            required_imports=COMPLETE_RUNTIME_IMPORTS,
            extra_executables={"uv": uv},
        )
        installed = stage / "installed"
        parsed_manifest = RuntimeDistributionManifest.model_validate_json(
            manifest.read_bytes(), strict=True
        )
        extract_runtime_distribution(archive, parsed_manifest, installed)
        project_paths = (
            exact_repo,
            exact_repo / "packages/traincapsule-core/src",
            exact_repo / "packages/traincapsule-ingest-pytorch/src",
            exact_repo / "packages/traincapsule-qualify/src",
            exact_repo / "packages/traincapsule-cli/src",
            exact_repo / "verifier/src",
            exact_repo / "canary_runner/src",
        )
        smoke = (
            "import importlib,sys;"
            "count=int(sys.argv[1]);"
            "sys.path[:0]=sys.argv[2:2+count];"
            "[importlib.import_module(name) for name in sys.argv[2+count:]]"
        )
        import_paths = [
            str(installed / "lib/python3.12/site-packages"),
            *(str(path) for path in project_paths),
        ]
        try:
            _run(
                [
                    str(installed / "bin/python3.12"),
                    "-S",
                    "-c",
                    smoke,
                    str(len(import_paths)),
                    *import_paths,
                *PRODUCTION_RUNTIME_IMPORTS,
                *PROJECT_RUNTIME_IMPORTS,
                ],
                cwd=exact_repo,
            )
            service_smoke = (
                "import importlib;"
                f"[importlib.import_module(name) for name in {COMPLETE_RUNTIME_IMPORTS!r}]"
            )
            _run(
                [str(installed / "bin/python3.12"), "-c", service_smoke],
                cwd=stage,
            )
            claude = (
                installed
                / "lib/python3.12/site-packages/claude_agent_sdk/_bundled/claude"
            )
            if not claude.is_file() or not claude.stat().st_mode & 0o111:
                raise RuntimeError("Claude SDK bundled executable is absent or non-executable")
            _run([str(claude), "--version"], cwd=exact_repo)
        finally:
            for directory in [
                installed,
                *(path for path in installed.rglob("*") if path.is_dir()),
            ]:
                directory.chmod(0o700)
        return archive, manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--python-root", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    archive, manifest = build_production_runtime(
        repo_root=arguments.repo,
        python_root=arguments.python_root,
        uv_executable=arguments.uv,
        output=arguments.output,
    )
    sys.stdout.write(f"archive={archive}\nmanifest={manifest}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
