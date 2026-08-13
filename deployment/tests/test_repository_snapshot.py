from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import zipfile
from pathlib import Path

import pytest

from deployment.bundle_assembler import validate_repository_git_graph
from deployment.privileged_installer import (
    load_repository_snapshot_manifest,
    validate_repository_snapshot_archive,
)
from deployment.repository_snapshot import (
    RepositorySnapshotError,
    build_repository_snapshot,
    materialize_exact_repository_tree,
)


def _run(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["/usr/bin/git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        },
    ).stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _run(repository, "init", "-b", "main")
    (repository / "config").mkdir()
    source_root = repository / "docs/source-of-truth/generation"
    source_root.mkdir(parents=True)
    source_path = "docs/source-of-truth/generation/FINAL_MANIFEST.json"
    (source_root / "FINAL_MANIFEST.json").write_text(
        '{\n  "generationId": "test-generation",\n  "schemaVersion": "3.1"\n}\n',
        encoding="utf-8",
    )
    (repository / "config/active_generation.yaml").write_text(
        "schemaVersion: '3.1'\n"
        "generationId: test-generation\n"
        "sourceRoot: docs/source-of-truth/generation\n"
        f"manifestPath: {source_path}\n",
        encoding="utf-8",
    )
    (repository / "controller.py").write_text("VALUE = 'committed'\n", encoding="utf-8")
    executable = repository / "scripts/runner.sh"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    _run(repository, "add", ".")
    _run(
        repository,
        "-c",
        "user.name=Snapshot Test",
        "-c",
        "user.email=snapshot@example.invalid",
        "commit",
        "-m",
        "snapshot candidate",
    )
    return repository, _run(repository, "rev-parse", "HEAD"), source_path


def _bindings(tmp_path: Path) -> dict[str, Path]:
    bindings: dict[str, Path] = {}
    for name in ("effective", "runtime", "package", "lock"):
        path = tmp_path / f"{name}.json"
        path.write_text(f'{{"binding":"{name}"}}\n', encoding="utf-8")
        bindings[name] = path
    return bindings


def _build(
    repository: Path, output: Path, bindings: dict[str, Path], *, source: str | None = None
) -> tuple[Path, Path]:
    return build_repository_snapshot(
        repository=repository,
        candidate="HEAD",
        output=output,
        effective_config=bindings["effective"],
        python_runtime_manifest=bindings["runtime"],
        package_manifest=bindings["package"],
        dependency_lock=bindings["lock"],
        source_manifest_path=source,
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_snapshot_is_deterministic_complete_and_git_clean(tmp_path: Path) -> None:
    repository, main_sha, source_path = _repository(tmp_path)
    bindings = _bindings(tmp_path)
    first, first_manifest = _build(repository, tmp_path / "first.snapshot", bindings)
    second, second_manifest = _build(repository, tmp_path / "second.snapshot", bindings)

    assert _digest(first) == _digest(second)
    assert _digest(first_manifest) == _digest(second_manifest)
    manifest = load_repository_snapshot_manifest(first_manifest)
    assert manifest.main_sha == main_sha
    assert manifest.tree_sha == _run(repository, "rev-parse", "HEAD^{tree}")
    assert manifest.source_manifest_path == source_path
    assert manifest.entries == sorted(manifest.entries, key=lambda item: item.path)
    assert manifest.git_objects == sorted(
        manifest.git_objects, key=lambda item: item.object_id
    )
    validate_repository_snapshot_archive(first, manifest)
    validate_repository_git_graph(first, first_manifest)
    with zipfile.ZipFile(first) as archive:
        executable = archive.getinfo("scripts/runner.sh")
        assert stat.S_IMODE(executable.external_attr >> 16) == 0o555
        assert archive.comment == b""


def test_dirty_and_untracked_worktree_bytes_never_enter_snapshot(tmp_path: Path) -> None:
    repository, _, _ = _repository(tmp_path)
    bindings = _bindings(tmp_path)
    (repository / "controller.py").write_text("VALUE = 'dirty'\n", encoding="utf-8")
    (repository / "untracked-secret.txt").write_text("must-not-enter\n", encoding="utf-8")

    archive, _ = _build(repository, tmp_path / "snapshot", bindings)
    with zipfile.ZipFile(archive) as observed:
        assert observed.read("controller.py") == b"VALUE = 'committed'\n"
        assert "untracked-secret.txt" not in observed.namelist()

    exact = tmp_path / "exact-tree"
    materialize_exact_repository_tree(repository, "HEAD", exact)
    assert not (exact / ".git").exists()
    assert (exact / "controller.py").read_bytes() == b"VALUE = 'committed'\n"
    assert not (exact / "untracked-secret.txt").exists()


def test_link_and_source_authority_substitution_fail_closed(tmp_path: Path) -> None:
    repository, _, source_path = _repository(tmp_path)
    bindings = _bindings(tmp_path)
    link = repository / "linked-controller"
    os.symlink("controller.py", link)
    _run(repository, "add", "linked-controller")
    _run(
        repository,
        "-c",
        "user.name=Snapshot Test",
        "-c",
        "user.email=snapshot@example.invalid",
        "commit",
        "-m",
        "unsafe link",
    )
    with pytest.raises(RepositorySnapshotError, match="link, submodule"):
        _build(repository, tmp_path / "linked.snapshot", bindings)

    _run(repository, "reset", "--hard", "HEAD^")
    with pytest.raises(RepositorySnapshotError, match="not the active authority"):
        _build(
            repository,
            tmp_path / "substituted.snapshot",
            bindings,
            source="controller.py",
        )
    assert source_path != "controller.py"
