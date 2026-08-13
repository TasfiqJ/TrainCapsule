"""Root-only, evidence-gated immutable runtime refresh transaction.

Candidate bytes are treated only as data.  This module never invokes a project build
backend, setup.py, a candidate executable, or a network client.  It materializes a
fixed Python module allow-list directly from a verified Git bundle and records every
installed byte in a canonical generation manifest before switching any live path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import ClassVar, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator
from traincapsule_verifier.canonical import canonical_json_bytes, sha256_digest
from traincapsule_verifier.git_anchor_updater import (
    AnchorUpdatePolicy,
    AnchorUpdateRequest,
    advance_anchor,
)

from .privileged_installer import (
    RepositorySnapshotManifest,
    SnapshotEntry,
    SnapshotGitObject,
)

POLICY_PATH = Path("/etc/traincapsule-deployment/refresh-policy.json")
CONTROLLER_USER = "traincapsule-controller"
APPLY_CONFIRMATION = "APPLY_DEPLOYMENT_REFRESH"


class RefreshFailure(RuntimeError):
    """A fail-closed refresh validation or transaction failure."""


class _Strict(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        alias_generator=lambda name: "".join(
            [name.split("_")[0], *(part.title() for part in name.split("_")[1:])]
        ),
        populate_by_name=True,
        extra="forbid",
        strict=True,
    )


class RefreshPolicy(_Strict):
    schema_version: Literal["3.1"] = "3.1"
    handoff_root: Literal["/var/lib/traincapsule-runtime/deployment-update-handoffs"]
    evidence_root: Literal["/var/lib/traincapsule-verifier/anchor-updates"]
    anchor_root: Literal["/var/lib/traincapsule-runtime/git"]
    generation_root: Literal["/opt/traincapsule-runtime/generations"]
    repository_boundary: Literal["/var/lib/traincapsule-verifier/repository-boundary"]
    journal_root: Literal["/var/lib/traincapsule-verifier/deployment-refresh-journal"]
    runtime_manifest_path: Literal["/etc/traincapsule-controller/runtime-manifest.json"]
    generation_manifest_path: Literal[
        "/etc/traincapsule-controller/deployment-generation.json"
    ]
    current_pointer: Literal["/opt/traincapsule-runtime/current"]
    python_runtime: Literal["/opt/traincapsule-runtime/bin/python3.12"]
    python_runtime_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dependency_manifest_path: Literal["/etc/traincapsule-runtime/runtime.json"]
    dependency_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    allowed_source_prefixes: tuple[str, ...]
    required_imports: tuple[str, ...]
    controller_unit: Literal["traincapsule-controller.service"]

    @model_validator(mode="after")
    def exact_packager(self) -> RefreshPolicy:
        expected = (
            "tcfactory/",
            "deployment/",
            "verifier/src/traincapsule_verifier/",
            "canary_runner/src/traincapsule_canary_runner/",
        )
        if self.allowed_source_prefixes != expected:
            raise ValueError("refresh source allow-list is not exact")
        if self.required_imports != (
            "tcfactory",
            "deployment",
            "traincapsule_verifier",
            "traincapsule_canary_runner",
        ):
            raise ValueError("refresh import roster is not exact")
        return self


class DeploymentUpdateHandoff(_Strict):
    schema_version: Literal["3.1"] = "3.1"
    disposition: Literal["DEPLOYMENT_UPDATE_REQUIRED"]
    installed_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    installed_main_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    required_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    required_main_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_generation_id: str
    source_generation_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    controller_runtime_may_execute_required_main: Literal[False]
    installed_runtime_attested: bool
    installed_runtime_manifest_digest: str | None
    next_action: Literal["INSTALL_SIGNED_SNAPSHOT_RUNTIME_AT_REQUIRED_MAIN"]


class InstalledEntry(_Strict):
    path: str
    mode: Literal["0444", "0555"]
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_path: str

    @model_validator(mode="after")
    def safe_path(self) -> InstalledEntry:
        pure = PurePosixPath(self.path)
        source = PurePosixPath(self.source_path)
        if (
            pure.is_absolute()
            or source.is_absolute()
            or any(part in {"", ".", ".."} for part in (*pure.parts, *source.parts))
        ):
            raise ValueError("generation inventory path is unsafe")
        return self


class GenerationManifest(_Strict):
    schema_version: Literal["3.1"] = "3.1"
    manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    required_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    required_main_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_generation_id: str
    source_generation_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    python_runtime_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dependency_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    entries: tuple[InstalledEntry, ...]
    import_origins: dict[str, str]

    @model_validator(mode="after")
    def exact_inventory(self) -> GenerationManifest:
        if list(self.entries) != sorted(self.entries, key=lambda item: item.path):
            raise ValueError("generation inventory is not sorted")
        paths = [item.path for item in self.entries]
        if len(paths) != len(set(paths)):
            raise ValueError("generation inventory contains duplicates")
        return self

    def computed_digest(self) -> str:
        zeroed = self.model_copy(update={"manifest_digest": "sha256:" + "0" * 64})
        return sha256_digest(canonical_json_bytes(zeroed))


class RefreshJournal(_Strict):
    schema_version: Literal["3.1"] = "3.1"
    transaction_id: str
    handoff_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    required_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    phase: Literal[
        "PREPARED", "STAGED", "SWITCHING", "SWITCHED", "COMMITTED", "ROLLED_BACK"
    ]
    generation_path: str
    previous_pointer: str | None = None
    previous_repository: str | None = None
    previous_runtime_manifest: str | None = None
    previous_environment: str | None = None
    previous_effective_config: str | None = None


@dataclass(frozen=True)
class RefreshResult:
    state: Literal["DRY_RUN", "COMMITTED"]
    required_main_sha: str
    generation: str
    controller_started: Literal[False] = False


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return "sha256:" + value.hexdigest()


def _trusted(path: Path, *, uid: int, mode: int, maximum: int) -> bytes:
    observed = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != uid
        or observed.st_nlink != 1
        or stat.S_IMODE(observed.st_mode) != mode
        or observed.st_size <= 0
        or observed.st_size > maximum
    ):
        raise RefreshFailure("refresh input is not trusted")
    return path.read_bytes()


def _canonical_model(path: Path, model: type[_Strict], *, uid: int, mode: int) -> _Strict:
    raw = _trusted(path, uid=uid, mode=mode, maximum=2_000_000)
    try:
        value = model.model_validate_json(raw, strict=True)
    except ValueError as exc:
        raise RefreshFailure("refresh input schema is invalid") from exc
    if canonical_json_bytes(value) != raw:
        raise RefreshFailure("refresh input is not canonical")
    return value


def _run_git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(repo), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
        env={
            "PATH": "/usr/bin:/bin",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        },
    )
    if result.returncode != 0:
        raise RefreshFailure("offline Git evidence verification failed")
    return result.stdout.strip()


def _find_evidence(root: Path, handoff: DeploymentUpdateHandoff) -> tuple[Path, ...]:
    matches: list[tuple[Path, ...]] = []
    for request_path in sorted(root.glob("ANCHOR_*.request.json")):
        try:
            request = AnchorUpdateRequest.model_validate_json(
                request_path.read_bytes(), strict=True
            )
        except ValueError:
            continue
        if (
            request.merged_main_sha == handoff.required_main_sha
            and request.merged_main_tree_sha == handoff.required_main_tree_sha
            and request.base_sha == handoff.installed_main_sha
            and request.source_generation_id == handoff.source_generation_id
            and request.source_generation_digest == handoff.source_generation_digest
        ):
            stem = request_path.name.removesuffix(".request.json")
            matches.append(
                (
                    request_path,
                    root / f"{stem}.observed.json",
                    root / f"{stem}.ruleset.json",
                    root / f"{stem}.publication.json",
                    root / f"{stem}.bundle",
                )
            )
    if len(matches) != 1 or any(not item.is_file() for item in matches[0]):
        raise RefreshFailure("refresh evidence set is missing or ambiguous")
    return matches[0]


def _tree_files(
    bundle: Path, main_sha: str, tree_sha: str, stage: Path
) -> tuple[list[tuple[str, int, bytes]], Path]:
    bare = stage / "candidate.git"
    clone = subprocess.run(
        ["/usr/bin/git", "clone", "--bare", "--no-local", str(bundle), str(bare)],
        check=False,
        capture_output=True,
        timeout=120,
        env={
            "PATH": "/usr/bin:/bin",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        },
    )
    if clone.returncode != 0:
        raise RefreshFailure("verified Git bundle cannot be materialized")
    if _run_git(bare, "rev-parse", f"{main_sha}^{{tree}}") != tree_sha:
        raise RefreshFailure("Git bundle tree was substituted")
    if (bare / "objects/info/alternates").exists():
        raise RefreshFailure("Git bundle introduced object alternates")
    if (bare / "hooks").exists():
        shutil.rmtree(bare / "hooks")
    output = subprocess.run(
        ["/usr/bin/git", "-C", str(bare), "ls-tree", "-rz", "--full-tree", main_sha],
        check=True,
        capture_output=True,
        timeout=120,
    ).stdout
    rows: list[tuple[str, int, bytes]] = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        header, name_raw = raw.split(b"\t", 1)
        mode_raw, kind_raw, object_raw = header.split(b" ")
        if kind_raw != b"blob" or mode_raw not in {b"100644", b"100755"}:
            raise RefreshFailure("candidate tree contains symlink or special entry")
        name = name_raw.decode("utf-8", errors="strict")
        pure = PurePosixPath(name)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise RefreshFailure("candidate tree contains traversal")
        blob = subprocess.run(
            ["/usr/bin/git", "-C", str(bare), "cat-file", "blob", object_raw.decode()],
            check=True,
            capture_output=True,
            timeout=60,
        ).stdout
        rows.append((name, 0o555 if mode_raw == b"100755" else 0o444, blob))
    return rows, bare


def _module_target(source: str, policy: RefreshPolicy) -> str | None:
    if not source.endswith(".py"):
        return None
    mappings = (
        ("tcfactory/", "site-packages/tcfactory/"),
        ("deployment/", "site-packages/deployment/"),
        (
            "verifier/src/traincapsule_verifier/",
            "site-packages/traincapsule_verifier/",
        ),
        (
            "canary_runner/src/traincapsule_canary_runner/",
            "site-packages/traincapsule_canary_runner/",
        ),
    )
    if tuple(source for source, _target in mappings) != policy.allowed_source_prefixes:
        raise RefreshFailure("internal packager allow-list diverged from policy")
    for prefix, target in mappings:
        if source.startswith(prefix):
            return target + source.removeprefix(prefix)
    return None


def _write_exact(path: Path, raw: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    os.chmod(path, mode, follow_symlinks=False)


def _build_generation(
    *, policy: RefreshPolicy, handoff: DeploymentUpdateHandoff, bundle: Path, stage: Path
) -> tuple[Path, GenerationManifest, bytes]:
    rows, bare = _tree_files(
        bundle, handoff.required_main_sha, handoff.required_main_tree_sha, stage
    )
    generation = stage / handoff.required_main_sha
    repository = generation / "repository"
    imports = generation / "site-packages"
    repository.mkdir(parents=True, mode=0o755)
    imports.mkdir(parents=True, mode=0o755)
    entries: list[InstalledEntry] = []
    origins: dict[str, str] = {}
    for source, mode, raw in rows:
        repository_target = repository.joinpath(*PurePosixPath(source).parts)
        _write_exact(repository_target, raw, mode)
        relative = repository_target.relative_to(generation).as_posix()
        entries.append(
            InstalledEntry(
                path=relative,
                mode="0555" if mode == 0o555 else "0444",
                digest=sha256_digest(raw),
                source_path=source,
            )
        )
        module = _module_target(source, policy)
        if module is not None:
            module_target = generation.joinpath(*PurePosixPath(module).parts)
            _write_exact(module_target, raw, 0o444)
            entries.append(
                InstalledEntry(
                    path=module,
                    mode="0444",
                    digest=sha256_digest(raw),
                    source_path=source,
                )
            )
    os.replace(bare, repository / ".git")
    _run_git(repository, "config", "core.bare", "false")
    _run_git(repository, "config", "core.worktree", str(repository))
    _run_git(repository, "symbolic-ref", "HEAD", "refs/heads/main")
    _run_git(repository, "update-ref", "refs/heads/main", handoff.required_main_sha)
    info = repository / ".git/info"
    info.mkdir(parents=True, exist_ok=True)
    (info / "exclude").write_text("/SNAPSHOT_MANIFEST.json\n", encoding="utf-8")
    for package in policy.required_imports:
        root = imports / package
        initializer = root / "__init__.py"
        if not initializer.is_file():
            raise RefreshFailure("required import package is absent from verified main")
        origins[package] = initializer.relative_to(generation).as_posix()
    dependency_raw = _trusted(
        Path(policy.dependency_manifest_path), uid=0, mode=0o444, maximum=2_000_000
    )
    if sha256_digest(dependency_raw) != policy.dependency_manifest_digest:
        raise RefreshFailure("offline dependency manifest digest changed")
    python = Path(policy.python_runtime)
    if _digest(python) != policy.python_runtime_digest:
        raise RefreshFailure("pinned static Python runtime digest changed")
    manifest = GenerationManifest(
        manifest_digest="sha256:" + "0" * 64,
        required_main_sha=handoff.required_main_sha,
        required_main_tree_sha=handoff.required_main_tree_sha,
        source_generation_id=handoff.source_generation_id,
        source_generation_digest=handoff.source_generation_digest,
        python_runtime_digest=policy.python_runtime_digest,
        dependency_manifest_digest=policy.dependency_manifest_digest,
        entries=tuple(sorted(entries, key=lambda item: item.path)),
        import_origins=origins,
    )
    manifest = manifest.model_copy(update={"manifest_digest": manifest.computed_digest()})
    manifest_raw = canonical_json_bytes(manifest)
    _write_exact(generation / "GENERATION_MANIFEST.json", manifest_raw, 0o444)
    source_manifest_path = repository / "config/source-generation.json"
    if (
        not source_manifest_path.is_file()
        or _digest(source_manifest_path) != handoff.source_generation_digest
    ):
        raise RefreshFailure("required main source generation is not authoritative")
    effective_config = repository / "config/factory.yaml"
    if not effective_config.is_file():
        raise RefreshFailure("required main lacks the fixed effective configuration")
    snapshot_entries: list[SnapshotEntry] = []
    for path in sorted(repository.rglob("*")):
        relative = path.relative_to(repository).as_posix()
        if relative == "SNAPSHOT_MANIFEST.json":
            continue
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise RefreshFailure("materialized repository contains a special entry")
        snapshot_entries.append(
            SnapshotEntry(
                path=relative,
                kind="directory" if path.is_dir() else "file",
                mode="0555" if path.is_dir() or path.stat().st_mode & 0o111 else "0444",
                digest=None if path.is_dir() else _digest(path),
            )
        )
    object_rows = _run_git(repository, "cat-file", "--batch-all-objects", "--batch-check")
    objects: list[SnapshotGitObject] = []
    for row in object_rows.splitlines():
        object_id, kind, size_raw = row.split(" ")
        if kind not in {"blob", "tree", "commit", "tag"}:
            raise RefreshFailure("repository object kind is unsafe")
        objects.append(
            SnapshotGitObject(
                objectId=object_id,
                kind=cast(Literal["blob", "tree", "commit", "tag"], kind),
                size=int(size_raw),
            )
        )
    dependency_lock = Path("/opt/traincapsule-runtime/dependency.lock")
    snapshot = RepositorySnapshotManifest(
        manifestDigest="sha256:" + "0" * 64,
        mainSha=handoff.required_main_sha,
        treeSha=handoff.required_main_tree_sha,
        sourceManifestPath="config/source-generation.json",
        sourceGenerationDigest=handoff.source_generation_digest,
        effectiveConfigDigest=_digest(effective_config),
        pythonRuntimeManifestDigest=policy.dependency_manifest_digest,
        packageManifestDigest=sha256_digest(manifest_raw),
        dependencyLockDigest=_digest(dependency_lock),
        entries=snapshot_entries,
        gitObjects=sorted(objects, key=lambda item: item.object_id),
    )
    snapshot = snapshot.model_copy(update={"manifest_digest": snapshot.computed_digest()})
    _write_exact(
        repository / "SNAPSHOT_MANIFEST.json", canonical_json_bytes(snapshot), 0o444
    )
    # Syntax-only preactivation gate.  It parses candidate modules but executes none.
    for entry in manifest.entries:
        if entry.path.startswith("site-packages/"):
            result = subprocess.run(
                [
                    policy.python_runtime,
                    "-I",
                    "-S",
                    "-c",
                    "import ast,sys; ast.parse(open(sys.argv[1],'rb').read())",
                    str(generation / entry.path),
                ],
                check=False,
                capture_output=True,
                timeout=30,
                env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0"},
            )
            if result.returncode != 0:
                raise RefreshFailure("candidate module failed isolated syntax gate")
    for path in sorted(generation.rglob("*"), reverse=True):
        os.chmod(path, 0o555 if path.is_dir() else stat.S_IMODE(path.stat().st_mode))
    os.chmod(generation, 0o555)
    return generation, manifest, effective_config.read_bytes()


def _atomic_json(path: Path, raw: bytes, mode: int) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode, follow_symlinks=False)
    finally:
        os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _runtime_manifest(
    *,
    policy: RefreshPolicy,
    handoff: DeploymentUpdateHandoff,
    generation_path: Path,
    generation: GenerationManifest,
    snapshot_digest: str,
    environment_raw: bytes,
    effective_config_raw: bytes,
) -> bytes:
    path = Path(policy.runtime_manifest_path)
    raw = _trusted(path, uid=0, mode=0o444, maximum=2_000_000)
    try:
        value: object = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RefreshFailure("installed runtime manifest is invalid") from exc
    if not isinstance(value, dict):
        raise RefreshFailure("installed runtime manifest is invalid")
    manifest = cast(dict[str, object], value)
    package_path = generation_path / "GENERATION_MANIFEST.json"
    manifest["repositoryMainSha"] = handoff.required_main_sha
    manifest["repositoryTreeSha"] = handoff.required_main_tree_sha
    manifest["packageManifest"] = {
        "path": str(package_path),
        "digest": generation.manifest_digest,
        "executable": False,
    }
    manifest["repositorySnapshotManifest"] = {
        "path": "/var/lib/traincapsule-verifier/repository-boundary/SNAPSHOT_MANIFEST.json",
        "digest": snapshot_digest,
        "executable": False,
    }
    manifest["environmentFile"] = {
        "path": "/etc/traincapsule-controller/controller-runtime.env",
        "digest": sha256_digest(environment_raw),
        "executable": False,
    }
    manifest["effectiveConfig"] = {
        "path": "/etc/traincapsule-controller/effective-config.yaml",
        "digest": sha256_digest(effective_config_raw),
        "executable": False,
    }
    manifest["manifestDigest"] = "sha256:" + "0" * 64
    manifest["manifestDigest"] = sha256_digest(canonical_json_bytes(manifest))
    return canonical_json_bytes(manifest)


def _backup(path: Path, destination: Path) -> str | None:
    if not path.exists() and not path.is_symlink():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_dir() and not path.is_symlink():
        os.replace(path, destination)
    else:
        shutil.copy2(path, destination, follow_symlinks=False)
    return str(destination)


def _restore_file(target: Path, backup: str | None) -> None:
    if backup is None:
        target.unlink(missing_ok=True)
        return
    source = Path(backup)
    if source.exists() or source.is_symlink():
        os.replace(source, target)


def _rollback_switch(policy: RefreshPolicy, journal: RefreshJournal) -> None:
    pointer = Path(policy.current_pointer)
    pointer.unlink(missing_ok=True)
    if journal.previous_pointer is not None:
        os.symlink(journal.previous_pointer, pointer)
    boundary = Path(policy.repository_boundary)
    if boundary.exists():
        failed = Path(policy.journal_root) / "failed" / journal.transaction_id
        failed.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if failed.exists():
            shutil.rmtree(failed)
        os.replace(boundary, failed)
    if journal.previous_repository is not None and Path(journal.previous_repository).exists():
        os.replace(Path(journal.previous_repository), boundary)
    _restore_file(Path(policy.runtime_manifest_path), journal.previous_runtime_manifest)
    _restore_file(
        Path("/etc/traincapsule-controller/controller-runtime.env"),
        journal.previous_environment,
    )
    _restore_file(
        Path("/etc/traincapsule-controller/effective-config.yaml"),
        journal.previous_effective_config,
    )


def refresh(
    policy: RefreshPolicy,
    handoff_path: Path,
    *,
    apply: bool = False,
    fail_hook: Callable[[str], None] | None = None,
) -> RefreshResult:
    controller_uid = pwd.getpwnam(CONTROLLER_USER).pw_uid
    handoff = cast(
        DeploymentUpdateHandoff,
        _canonical_model(handoff_path, DeploymentUpdateHandoff, uid=controller_uid, mode=0o600),
    )
    raw_handoff = handoff_path.read_bytes()
    handoff_digest = sha256_digest(raw_handoff)
    expected_name = f"{handoff.required_main_sha}-{handoff_digest[7:23]}.json"
    if handoff_path.name != expected_name or handoff_path.parent != Path(policy.handoff_root):
        raise RefreshFailure("deployment handoff identity is invalid")
    request, observed, ruleset, publication, bundle = _find_evidence(
        Path(policy.evidence_root), handoff
    )
    anchor_policy_path = Path("/etc/traincapsule-verifier/git-anchor-policy.json")
    anchor_policy_raw = _trusted(anchor_policy_path, uid=0, mode=0o644, maximum=64_000)
    try:
        anchor_policy = AnchorUpdatePolicy.model_validate_json(anchor_policy_raw, strict=True)
    except ValueError as exc:
        raise RefreshFailure("anchor update policy schema is invalid") from exc
    if canonical_json_bytes(anchor_policy) != anchor_policy_raw:
        raise RefreshFailure("anchor update policy is not canonical")
    journal = advance_anchor(
        request_raw=_trusted(request, uid=0, mode=0o400, maximum=64_000),
        observed_main_raw=_trusted(observed, uid=0, mode=0o400, maximum=1_000_000),
        ruleset_raw=_trusted(ruleset, uid=0, mode=0o400, maximum=1_000_000),
        publication_transaction_raw=_trusted(
            publication, uid=0, mode=0o400, maximum=1_000_000
        ),
        bundle_path=bundle,
        policy=anchor_policy,
        selector_public_key_raw=_trusted(
            Path("/etc/traincapsule-verifier/selector-public-key.pem"),
            uid=0,
            mode=0o444,
            maximum=8_192,
        ),
        ruleset_public_key_raw=_trusted(
            Path("/etc/traincapsule-verifier/ruleset-public-key.pem"),
            uid=0,
            mode=0o444,
            maximum=8_192,
        ),
    )
    if journal.phase != "COMMITTED":
        raise RefreshFailure("anchor update is not independently committed")
    if (
        _run_git(Path(policy.anchor_root), "rev-parse", "refs/heads/main")
        != handoff.required_main_sha
    ):
        raise RefreshFailure("mutable anchor does not match the required main")
    generation_target = Path(policy.generation_root) / handoff.required_main_sha
    if not apply:
        return RefreshResult(
            state="DRY_RUN",
            required_main_sha=handoff.required_main_sha,
            generation=str(generation_target),
        )
    if os.geteuid() != 0:
        raise RefreshFailure("deployment refresh apply requires root")
    active = subprocess.run(
        ["/usr/bin/systemctl", "is-active", "--quiet", policy.controller_unit],
        check=False,
        timeout=20,
    )
    if active.returncode == 0:
        raise RefreshFailure("controller must already be stopped by the cycle boundary")
    journal_root = Path(policy.journal_root)
    journal_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    transaction_id = handoff.required_main_sha + "-" + handoff_digest[7:23]
    journal_path = journal_root / f"{transaction_id}.json"
    if journal_path.is_file():
        prior = cast(
            RefreshJournal,
            _canonical_model(journal_path, RefreshJournal, uid=0, mode=0o600),
        )
        if prior.handoff_digest != handoff_digest:
            raise RefreshFailure("refresh transaction identity conflict")
        if prior.phase == "COMMITTED":
            return RefreshResult(
                state="COMMITTED",
                required_main_sha=handoff.required_main_sha,
                generation=prior.generation_path,
            )
    prepared = RefreshJournal(
        transaction_id=transaction_id,
        handoff_digest=handoff_digest,
        required_main_sha=handoff.required_main_sha,
        phase="PREPARED",
        generation_path=str(generation_target),
    )
    _atomic_json(journal_path, canonical_json_bytes(prepared), 0o600)
    with tempfile.TemporaryDirectory(prefix="refresh-", dir=journal_root) as raw_stage:
        staged, manifest, _effective_config = _build_generation(
            policy=policy,
            handoff=handoff,
            bundle=bundle,
            stage=Path(raw_stage),
        )
        generation_target.parent.mkdir(parents=True, exist_ok=True, mode=0o555)
        if generation_target.exists():
            existing = GenerationManifest.model_validate_json(
                (generation_target / "GENERATION_MANIFEST.json").read_bytes(), strict=True
            )
            if existing != manifest:
                raise RefreshFailure("existing generation identity conflicts")
        else:
            os.replace(staged, generation_target)
        staged_journal = prepared.model_copy(update={"phase": "STAGED"})
        _atomic_json(journal_path, canonical_json_bytes(staged_journal), 0o600)
        if fail_hook is not None:
            fail_hook("STAGED")
        pointer = Path(policy.current_pointer)
        previous_pointer = os.readlink(pointer) if pointer.is_symlink() else None
        temporary_pointer = pointer.with_name(f".{pointer.name}.{os.getpid()}.tmp")
        os.symlink(str(generation_target), temporary_pointer)
        os.replace(temporary_pointer, pointer)
        _atomic_json(
            Path(policy.generation_manifest_path), canonical_json_bytes(manifest), 0o444
        )
        switched = staged_journal.model_copy(
            update={"phase": "SWITCHED", "previous_pointer": previous_pointer}
        )
        _atomic_json(journal_path, canonical_json_bytes(switched), 0o600)
        if fail_hook is not None:
            fail_hook("SWITCHED")
        committed = switched.model_copy(update={"phase": "COMMITTED"})
        _atomic_json(journal_path, canonical_json_bytes(committed), 0o600)
    # Deliberately do not start/restart the controller.  Existing gated start path is
    # notified by its own independently verified request/receipt transition.
    return RefreshResult(
        state="COMMITTED",
        required_main_sha=handoff.required_main_sha,
        generation=str(generation_target),
    )


def load_policy(path: Path = POLICY_PATH) -> RefreshPolicy:
    return cast(RefreshPolicy, _canonical_model(path, RefreshPolicy, uid=0, mode=0o444))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="traincapsule-deployment-refresh")
    parser.add_argument("handoff", type=Path)
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    try:
        if args.apply and args.confirm != APPLY_CONFIRMATION:
            raise RefreshFailure("apply confirmation token is missing")
        result = refresh(load_policy(args.policy), args.handoff, apply=args.apply)
    except (OSError, ValueError, RefreshFailure):
        print("deployment refresh failed closed", file=sys.stderr)
        return 1
    print(json.dumps(result.__dict__, sort_keys=True))
    return 0
