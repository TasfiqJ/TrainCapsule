"""Exact, root-owned controller runtime identity used by LIVE activation."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ..util import sha256_file
from .base import DIGEST_PATTERN, V3Model, sha256_digest


class InstalledArtifact(V3Model):
    path: str = Field(pattern=r"^/[^\x00\r\n]{1,4095}$")
    digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    executable: bool = False


class InstalledControllerRuntimeManifest(V3Model):
    schema_version: Literal["3.1"] = "3.1"
    manifest_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    controller_principal: Literal["traincapsule-controller"]
    service_name: Literal["traincapsule-controller.service"]
    distribution_root: Literal["/opt/traincapsule-runtime"]
    repository_root: Literal["/var/lib/traincapsule-verifier/repository-boundary"]
    runtime_root: Literal["/var/lib/traincapsule-runtime"]
    python_runtime: InstalledArtifact
    package_manifest: InstalledArtifact
    dependency_lock: InstalledArtifact
    controller_unit: InstalledArtifact
    environment_file: InstalledArtifact
    effective_config: InstalledArtifact
    repository_snapshot_manifest: InstalledArtifact
    repository_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    repository_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    mutable_git_root: Literal["/var/lib/traincapsule-runtime/git"]
    mutable_worktree_root: Literal["/var/lib/traincapsule-runtime/worktrees"]
    artifact_root: Literal["/var/lib/traincapsule-runtime/artifacts/v3"]
    entry_arguments: tuple[
        Literal["-m"],
        Literal["tcfactory"],
        Literal["v3-controller"],
        Literal["--repo"],
        Literal["/var/lib/traincapsule-verifier/repository-boundary"],
    ]

    @model_validator(mode="after")
    def exact_paths(self) -> InstalledControllerRuntimeManifest:
        if self.python_runtime.path != "/opt/traincapsule-runtime/bin/python3.12":
            raise ValueError("controller Python runtime path is not the installed runtime")
        if not self.python_runtime.executable:
            raise ValueError("controller Python runtime must be executable")
        if self.controller_unit.path != "/etc/systemd/system/traincapsule-controller.service":
            raise ValueError("controller unit path is not canonical")
        if self.environment_file.path != "/etc/traincapsule-controller/controller-runtime.env":
            raise ValueError("controller environment path is not canonical")
        if self.effective_config.path != "/etc/traincapsule-controller/effective-config.yaml":
            raise ValueError("controller effective config path is not canonical")
        if (
            self.repository_snapshot_manifest.path
            != "/var/lib/traincapsule-verifier/repository-boundary/SNAPSHOT_MANIFEST.json"
        ):
            raise ValueError("repository snapshot manifest path is not canonical")
        for artifact in (self.package_manifest, self.dependency_lock):
            if not Path(artifact.path).is_relative_to(Path(self.distribution_root)):
                raise ValueError("controller distribution artifact escapes installed runtime")
        return self

    def computed_manifest_digest(self) -> str:
        payload = self.model_copy(update={"manifest_digest": "sha256:" + "0" * 64})
        return sha256_digest(payload.canonical_json_bytes())


def load_installed_controller_runtime(
    path: Path = Path("/etc/traincapsule-controller/runtime-manifest.json"),
    *,
    expected_owner_uid: int = 0,
) -> tuple[InstalledControllerRuntimeManifest, bytes]:
    """Reopen and attest the exact installed runtime and every bound byte."""

    resolved = path.resolve(strict=True)
    observed = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != expected_owner_uid
        or observed.st_nlink != 1
        or observed.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise RuntimeError("installed controller runtime manifest is not trusted")
    raw = resolved.read_bytes()
    manifest = InstalledControllerRuntimeManifest.model_validate_json(raw, strict=True)
    if raw != manifest.canonical_json_bytes():
        raise RuntimeError("installed controller runtime manifest is not canonical")
    if manifest.manifest_digest != manifest.computed_manifest_digest():
        raise RuntimeError("installed controller runtime manifest digest mismatch")
    for artifact in (
        manifest.python_runtime,
        manifest.package_manifest,
        manifest.dependency_lock,
        manifest.controller_unit,
        manifest.environment_file,
        manifest.effective_config,
        manifest.repository_snapshot_manifest,
    ):
        artifact_path = Path(artifact.path)
        artifact_observed = artifact_path.lstat()
        if (
            artifact_path.is_symlink()
            or not stat.S_ISREG(artifact_observed.st_mode)
            or artifact_observed.st_uid != expected_owner_uid
            or artifact_observed.st_nlink != 1
            or artifact_observed.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            or (artifact.executable and not artifact_observed.st_mode & stat.S_IXUSR)
        ):
            raise RuntimeError(f"installed controller artifact is not trusted: {artifact.path}")
        if f"sha256:{sha256_file(artifact_path)}" != artifact.digest:
            raise RuntimeError(f"installed controller artifact digest mismatch: {artifact.path}")
    snapshot_root = Path(manifest.repository_root)
    if snapshot_root.is_symlink() or not snapshot_root.is_dir():
        raise RuntimeError("installed repository snapshot root is not trusted")
    for forbidden in (
        snapshot_root / ".git/objects/info/alternates",
        snapshot_root / ".git/hooks",
    ):
        if forbidden.exists():
            raise RuntimeError("installed repository snapshot has mutable external Git behavior")
    remote = subprocess.run(
        ["/usr/bin/git", "-C", str(snapshot_root), "remote"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    sha = subprocess.run(
        ["/usr/bin/git", "-C", str(snapshot_root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    tree = subprocess.run(
        ["/usr/bin/git", "-C", str(snapshot_root), "rev-parse", "HEAD^{tree}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if (
        remote.returncode != 0
        or remote.stdout.strip()
        or sha.returncode != 0
        or sha.stdout.strip() != manifest.repository_main_sha
        or tree.returncode != 0
        or tree.stdout.strip() != manifest.repository_tree_sha
    ):
        raise RuntimeError("installed repository snapshot exact SHA/tree binding mismatch")
    if os.path.commonpath((str(resolved), manifest.repository_root)) == manifest.repository_root:
        raise RuntimeError("installed controller manifest cannot resolve inside repository")
    return manifest, raw
