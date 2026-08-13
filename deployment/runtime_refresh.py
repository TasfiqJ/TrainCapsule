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
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import ClassVar, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator
from traincapsule_verifier.canonical import (
    canonical_json_bytes,
    model_digest,
    sha256_digest,
)
from traincapsule_verifier.git_anchor_updater import (
    AnchorUpdatePolicy,
    AnchorUpdateRequest,
)
from traincapsule_verifier.models import ObservedMainReceipt, RulesetObservationReceipt
from traincapsule_verifier.public_crypto import load_public_key, verify_model_signature

from tcfactory.v3.installed_runtime import InstalledControllerRuntimeManifest

from .privileged_installer import (
    RepositorySnapshotManifest,
    SnapshotEntry,
    SnapshotGitObject,
)
from .runtime_distribution import PROJECT_RUNTIME_IMPORTS, PROJECT_SOURCE_MAPPINGS

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
    proposal_root: Literal["/var/lib/traincapsule-runtime/deployment-update-handoffs"]
    handoff_root: Literal["/var/lib/traincapsule-verifier/deployment-refresh-claims"]
    evidence_root: Literal["/var/lib/traincapsule-verifier/anchor-updates"]
    anchor_root: Literal["/var/lib/traincapsule-runtime/git"]
    generation_root: Literal["/opt/traincapsule-runtime/generations"]
    repository_boundary: Literal["/var/lib/traincapsule-verifier/repository-boundary"]
    journal_root: Literal["/var/lib/traincapsule-verifier/deployment-refresh-journal"]
    runtime_manifest_path: Literal["/etc/traincapsule-controller/runtime-manifest.json"]
    environment_path: Literal["/etc/traincapsule-controller/controller-runtime.env"]
    effective_config_path: Literal["/etc/traincapsule-controller/effective-config.yaml"]
    generation_manifest_path: Literal[
        "/etc/traincapsule-controller/deployment-generation.json"
    ]
    current_pointer: Literal["/opt/traincapsule-runtime/current"]
    python_runtime: Literal["/opt/traincapsule-runtime/python/bin/python3.12"]
    python_runtime_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dependency_manifest_path: Literal["/etc/traincapsule-runtime/runtime.json"]
    dependency_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    allowed_source_prefixes: tuple[str, ...]
    required_imports: tuple[str, ...]
    controller_unit: Literal["traincapsule-controller.service"]

    @model_validator(mode="after")
    def exact_packager(self) -> RefreshPolicy:
        expected = tuple(source for source, _target in PROJECT_SOURCE_MAPPINGS)
        if self.allowed_source_prefixes != expected:
            raise ValueError("refresh source allow-list is not exact")
        if self.required_imports != PROJECT_RUNTIME_IMPORTS:
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
    installed_runtime_manifest_digest: str | None = Field(
        pattern=r"^sha256:[0-9a-f]{64}$"
    )
    next_action: Literal["INSTALL_SIGNED_SNAPSHOT_RUNTIME_AT_REQUIRED_MAIN"]

    @model_validator(mode="after")
    def attested_installed_runtime(self) -> DeploymentUpdateHandoff:
        if (
            not self.installed_runtime_attested
            or self.installed_runtime_manifest_digest is None
            or not self.installed_runtime_manifest_digest.startswith("sha256:")
        ):
            raise ValueError("deployment refresh requires an attested installed runtime")
        return self


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
    generation_created: bool = False
    repository_was_present: bool = False
    previous_pointer: str | None = None
    previous_repository: str | None = None
    previous_runtime_manifest: str | None = None
    previous_environment: str | None = None
    previous_effective_config: str | None = None
    previous_generation_manifest: str | None = None
    generation_manifest_digest: str | None = None
    snapshot_manifest_digest: str | None = None
    runtime_manifest_digest: str | None = None
    environment_digest: str | None = None
    effective_config_digest: str | None = None


@dataclass(frozen=True)
class RefreshResult:
    state: Literal["DRY_RUN", "COMMITTED"]
    required_main_sha: str
    generation: str
    controller_started: Literal[False] = False


class RefreshCompletion(_Strict):
    schema_version: Literal["3.1"] = "3.1"
    transaction_id: str
    handoff_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    previous_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    required_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    required_main_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_generation_id: str
    source_generation_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    generation_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    runtime_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    environment_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    effective_config_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    snapshot_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    committed_at: datetime


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return "sha256:" + value.hexdigest()


def _at(root: Path, absolute: str) -> Path:
    path = Path(absolute)
    if not path.is_absolute():
        raise RefreshFailure("refresh policy path is not absolute")
    return root / path.relative_to("/")


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


def _canonical_model(
    path: Path, model: type[BaseModel], *, uid: int, mode: int
) -> BaseModel:
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
            request = cast(
                AnchorUpdateRequest,
                _canonical_model(
                    request_path,
                    AnchorUpdateRequest,
                    uid=request_path.stat().st_uid,
                    mode=0o400,
                ),
            )
        except (OSError, ValueError, RefreshFailure):
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
    if len(matches) != 1:
        raise RefreshFailure("refresh evidence set is missing or ambiguous")
    for item in matches[0]:
        observed = item.lstat()
        if item.is_symlink() or not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
            raise RefreshFailure("refresh evidence set contains an unsafe entry")
    return matches[0]


def _verify_evidence(
    *,
    handoff: DeploymentUpdateHandoff,
    request_raw: bytes,
    observed_raw: bytes,
    ruleset_raw: bytes,
    publication_raw: bytes,
    bundle: Path,
    policy: AnchorUpdatePolicy,
    selector_public_key: bytes,
    ruleset_public_key: bytes,
    now: datetime | None = None,
) -> AnchorUpdateRequest:
    try:
        request = AnchorUpdateRequest.model_validate_json(request_raw, strict=True)
        observed = ObservedMainReceipt.model_validate_json(observed_raw, strict=True)
        ruleset = RulesetObservationReceipt.model_validate_json(ruleset_raw, strict=True)
        publication_value: object = json.loads(publication_raw)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RefreshFailure("refresh authority evidence schema is invalid") from exc
    if not isinstance(publication_value, dict):
        raise RefreshFailure("refresh authority evidence is not canonical")
    publication = cast(dict[str, object], publication_value)
    if (
        canonical_json_bytes(request) != request_raw
        or canonical_json_bytes(observed) != observed_raw
        or canonical_json_bytes(ruleset) != ruleset_raw
        or canonical_json_bytes(publication) != publication_raw
    ):
        raise RefreshFailure("refresh authority evidence is not canonical")
    try:
        verify_model_signature(observed, load_public_key(selector_public_key))
        verify_model_signature(ruleset, load_public_key(ruleset_public_key))
    except ValueError as exc:
        raise RefreshFailure("refresh authority signature is invalid") from exc
    observed_now = now or datetime.now(UTC)
    if (
        request.repository != policy.repository
        or request.source_generation_id != policy.source_generation_id
        or request.source_generation_digest != policy.source_generation_digest
        or request.base_sha != handoff.installed_main_sha
        or request.merged_main_sha != handoff.required_main_sha
        or request.merged_main_tree_sha != handoff.required_main_tree_sha
        or request.source_generation_id != handoff.source_generation_id
        or request.source_generation_digest != handoff.source_generation_digest
        or request.created_at > observed_now
        or request.expires_at <= observed_now
        or observed.observed_at > observed_now
        or observed.expires_at <= observed_now
        or ruleset.observed_at > observed_now
        or ruleset.expires_at <= observed_now
        or observed.repository != request.repository
        or ruleset.repository != request.repository
        or observed.verified_main_sha != request.merged_main_sha
        or observed.verified_main_tree_sha != request.merged_main_tree_sha
        or observed.source_generation_id != request.source_generation_id
        or observed.source_generation_digest != request.source_generation_digest
        or request.observed_main_digest != model_digest(observed)
        or request.ruleset_observation_digest != model_digest(ruleset)
        or observed.ruleset_observation_digest != model_digest(ruleset)
        or request.bundle_digest != _digest(bundle)
        or request.publication_transaction_digest != sha256_digest(publication_raw)
        or publication.get("phase") != "MERGED"
        or publication.get("baseSha") != request.base_sha
        or publication.get("mergedMainSha") != request.merged_main_sha
    ):
        raise RefreshFailure("refresh authority evidence is stale or inconsistently bound")
    return request


def _tree_files(
    bundle: Path, main_sha: str, tree_sha: str, stage: Path
) -> tuple[list[tuple[str, int, bytes]], Path]:
    bundle_stat = bundle.lstat()
    if (
        bundle.is_symlink()
        or not stat.S_ISREG(bundle_stat.st_mode)
        or bundle_stat.st_nlink != 1
        or bundle_stat.st_size <= 0
        or bundle_stat.st_size > 2_000_000_000
    ):
        raise RefreshFailure("verified Git bundle file identity is unsafe")
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
    mappings = tuple(
        (source_prefix, "site-packages/" + target_prefix)
        for source_prefix, target_prefix in PROJECT_SOURCE_MAPPINGS
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
    *,
    policy: RefreshPolicy,
    handoff: DeploymentUpdateHandoff,
    bundle: Path,
    stage: Path,
    root: Path = Path("/"),
    authority_uid: int = 0,
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
    _run_git(repository, "symbolic-ref", "HEAD", "refs/heads/main")
    _run_git(repository, "update-ref", "refs/heads/main", handoff.required_main_sha)
    if _run_git(repository, "remote"):
        _run_git(repository, "remote", "remove", "origin")
    _run_git(repository, "reset", "--mixed", "HEAD")
    info = repository / ".git/info"
    info.mkdir(parents=True, exist_ok=True)
    (info / "exclude").write_text("/SNAPSHOT_MANIFEST.json\n", encoding="utf-8")
    for package in policy.required_imports:
        package_root = imports / package
        initializer = package_root / "__init__.py"
        if not initializer.is_file():
            raise RefreshFailure("required import package is absent from verified main")
        origins[package] = initializer.relative_to(generation).as_posix()
    dependency_raw = _trusted(
        _at(root, policy.dependency_manifest_path),
        uid=authority_uid,
        mode=0o444,
        maximum=2_000_000,
    )
    if sha256_digest(dependency_raw) != policy.dependency_manifest_digest:
        raise RefreshFailure("offline dependency manifest digest changed")
    python = _at(root, policy.python_runtime)
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
    try:
        source_value: object = json.loads(source_manifest_path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RefreshFailure("required main source authority is invalid") from exc
    if not isinstance(source_value, dict):
        raise RefreshFailure("required main source authority identity changed")
    source_authority = cast(dict[str, object], source_value)
    if (
        canonical_json_bytes(source_authority) != source_manifest_path.read_bytes()
        or source_authority.get("generationId") != handoff.source_generation_id
    ):
        raise RefreshFailure("required main source authority identity changed")
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
                object_id=object_id,
                kind=cast(Literal["blob", "tree", "commit", "tag"], kind),
                size=int(size_raw),
            )
        )
    dependency_lock = _at(root, "/opt/traincapsule-runtime/dependency.lock")
    candidate_lock = repository / "uv.lock"
    if (
        not candidate_lock.is_file()
        or candidate_lock.is_symlink()
        or _digest(candidate_lock) != _digest(dependency_lock)
    ):
        raise RefreshFailure("candidate dependency lock differs from pinned offline lock")
    snapshot_payload: dict[str, object] = {
        "schemaVersion": "3.1",
        "manifestDigest": "sha256:" + "0" * 64,
        "mainSha": handoff.required_main_sha,
        "treeSha": handoff.required_main_tree_sha,
        "sourceManifestPath": "config/source-generation.json",
        "sourceGenerationDigest": handoff.source_generation_digest,
        "effectiveConfigDigest": _digest(effective_config),
        "pythonRuntimeManifestDigest": policy.dependency_manifest_digest,
        "packageManifestDigest": sha256_digest(manifest_raw),
        "dependencyLockDigest": _digest(dependency_lock),
        "entries": [entry.model_dump(mode="json", by_alias=True) for entry in snapshot_entries],
        "gitObjects": [
            item.model_dump(mode="json", by_alias=True)
            for item in sorted(objects, key=lambda item: item.object_id)
        ],
    }
    snapshot_payload["manifestDigest"] = sha256_digest(
        canonical_json_bytes(snapshot_payload)
    )
    snapshot = RepositorySnapshotManifest.model_validate(snapshot_payload, strict=True)
    _write_exact(
        repository / "SNAPSHOT_MANIFEST.json", canonical_json_bytes(snapshot), 0o444
    )
    # Syntax-only preactivation gate.  It parses candidate modules but executes none.
    for entry in manifest.entries:
        if entry.path.startswith("site-packages/"):
            result = subprocess.run(
                [
                    str(python),
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
        mode = 0o555 if path.is_dir() or path.stat().st_mode & 0o111 else 0o444
        os.chmod(path, mode)
    os.chmod(generation, 0o555)
    return generation, manifest, effective_config.read_bytes()


def _atomic_json(path: Path, raw: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def claim_pending(
    policy: RefreshPolicy,
    *,
    root: Path = Path("/"),
    authority_uid: int = 0,
    controller_uid: int | None = None,
) -> list[Path]:
    observed_controller_uid = (
        pwd.getpwnam(CONTROLLER_USER).pw_uid
        if controller_uid is None
        else controller_uid
    )
    proposal_root = _at(root, policy.proposal_root)
    claim_root = _at(root, policy.handoff_root)
    claimed: list[Path] = []
    for proposal in sorted(proposal_root.glob("*.json")):
        handoff = cast(
            DeploymentUpdateHandoff,
            _canonical_model(
                proposal,
                DeploymentUpdateHandoff,
                uid=observed_controller_uid,
                mode=0o600,
            ),
        )
        raw = proposal.read_bytes()
        digest = sha256_digest(raw)
        expected_name = f"{handoff.required_main_sha}-{digest[7:23]}.json"
        if proposal.name != expected_name:
            raise RefreshFailure("deployment proposal identity is invalid")
        target = claim_root / proposal.name
        if target.is_file():
            if _trusted(target, uid=authority_uid, mode=0o400, maximum=2_000_000) != raw:
                raise RefreshFailure("deployment claim identity conflicts")
        else:
            _atomic_json(target, raw, 0o400)
        claimed.append(target)
    return claimed


def publish_activation_completions(
    policy: RefreshPolicy,
    *,
    root: Path = Path("/"),
    authority_uid: int = 0,
    controller_uid: int | None = None,
) -> list[Path]:
    observed_controller_uid = (
        pwd.getpwnam(CONTROLLER_USER).pw_uid
        if controller_uid is None
        else controller_uid
    )
    source_root = _at(root, policy.journal_root) / "completions"
    target_root = _at(
        root, "/var/lib/traincapsule-verifier/activation-refresh-inbox"
    )
    retired_root = _at(
        root, "/var/lib/traincapsule-verifier/activation-refresh-retirement"
    ) / "retired"
    published: list[Path] = []
    for source in sorted(source_root.glob("*.json")):
        raw = _trusted(source, uid=authority_uid, mode=0o400, maximum=2_000_000)
        try:
            completion = RefreshCompletion.model_validate_json(raw, strict=True)
        except ValueError as exc:
            raise RefreshFailure("refresh completion schema is invalid") from exc
        if canonical_json_bytes(completion) != raw:
            raise RefreshFailure("refresh completion is not canonical")
        expected = f"{completion.required_main_sha}-{completion.transaction_id}.json"
        if source.name != expected:
            raise RefreshFailure("refresh completion path is not canonical")
        retired = retired_root / source.name
        if retired.is_file():
            if _trusted(
                retired,
                uid=authority_uid,
                mode=0o440,
                maximum=2_000_000,
            ) != raw:
                raise RefreshFailure("retired activation completion identity conflicts")
            continue
        target = target_root / source.name
        if target.is_file():
            if _trusted(
                target,
                uid=authority_uid,
                mode=0o440,
                maximum=2_000_000,
            ) != raw:
                raise RefreshFailure("activation completion claim identity conflicts")
        else:
            _atomic_json(target, raw, 0o440)
            if root == Path("/"):
                os.chown(target, authority_uid, observed_controller_uid)
        published.append(target)
    return published


def _runtime_manifest(
    *,
    policy: RefreshPolicy,
    handoff: DeploymentUpdateHandoff,
    generation_path: Path,
    generation: GenerationManifest,
    snapshot_digest: str,
    environment_raw: bytes,
    effective_config_raw: bytes,
    root: Path = Path("/"),
    authority_uid: int = 0,
) -> bytes:
    path = _at(root, policy.runtime_manifest_path)
    raw = _trusted(path, uid=authority_uid, mode=0o444, maximum=2_000_000)
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
        "digest": sha256_digest(canonical_json_bytes(generation)),
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
    rendered = canonical_json_bytes(manifest)
    try:
        validated = InstalledControllerRuntimeManifest.model_validate_json(
            rendered, strict=True
        )
    except ValueError as exc:
        raise RefreshFailure("refreshed runtime manifest is invalid") from exc
    if validated.computed_manifest_digest() != validated.manifest_digest:
        raise RefreshFailure("refreshed runtime manifest self-digest is invalid")
    return rendered


def _attest_generation(path: Path, expected: GenerationManifest) -> None:
    manifest_path = path / "GENERATION_MANIFEST.json"
    try:
        observed = GenerationManifest.model_validate_json(
            manifest_path.read_bytes(), strict=True
        )
    except ValueError as exc:
        raise RefreshFailure("installed generation manifest is invalid") from exc
    if observed != expected or observed.computed_digest() != observed.manifest_digest:
        raise RefreshFailure("installed generation manifest identity changed")
    expected_paths = {entry.path: entry for entry in expected.entries}
    observed_files = {
        item.relative_to(path).as_posix()
        for item in path.rglob("*")
        if item.is_file()
        and not item.is_symlink()
        and "/.git/" not in f"/{item.relative_to(path).as_posix()}"
        and item.relative_to(path).as_posix()
        not in {"GENERATION_MANIFEST.json", "repository/SNAPSHOT_MANIFEST.json"}
    }
    if observed_files != set(expected_paths):
        raise RefreshFailure("installed generation file inventory changed")
    for relative, entry in expected_paths.items():
        target = path.joinpath(*PurePosixPath(relative).parts)
        observed_stat = target.lstat()
        if (
            target.is_symlink()
            or not stat.S_ISREG(observed_stat.st_mode)
            or observed_stat.st_nlink != 1
            or stat.S_IMODE(observed_stat.st_mode) != int(entry.mode, 8)
            or _digest(target) != entry.digest
        ):
            raise RefreshFailure("installed generation entry changed")
    for package, relative in expected.import_origins.items():
        expected_origin = f"site-packages/{package}/__init__.py"
        if relative != expected_origin or relative not in expected_paths:
            raise RefreshFailure("installed import origin escapes the generation")


def _attest_repository_boundary(path: Path, expected: RepositorySnapshotManifest) -> None:
    try:
        observed = RepositorySnapshotManifest.model_validate_json(
            (path / "SNAPSHOT_MANIFEST.json").read_bytes(), strict=True
        )
    except ValueError as exc:
        raise RefreshFailure("installed snapshot manifest is invalid") from exc
    if observed != expected:
        raise RefreshFailure("installed snapshot manifest changed")
    expected_paths = {entry.path: entry for entry in expected.entries}
    observed_paths = {
        item.relative_to(path).as_posix()
        for item in path.rglob("*")
        if item.relative_to(path).as_posix() != "SNAPSHOT_MANIFEST.json"
    }
    if observed_paths != set(expected_paths):
        raise RefreshFailure("installed snapshot inventory changed")
    for relative, entry in expected_paths.items():
        target = path.joinpath(*PurePosixPath(relative).parts)
        target_stat = target.lstat()
        if target.is_symlink() or stat.S_IMODE(target_stat.st_mode) != int(entry.mode, 8):
            raise RefreshFailure("installed snapshot metadata changed")
        if entry.digest is not None and _digest(target) != entry.digest:
            raise RefreshFailure("installed snapshot content changed")
    git = path / ".git"
    if (git / "objects/info/alternates").exists() or (git / "hooks").exists():
        raise RefreshFailure("installed snapshot has external Git behavior")
    checks = (
        (("fsck", "--strict", "--no-dangling"), None),
        (("remote",), ""),
        (("rev-parse", "HEAD"), expected.main_sha),
        (("rev-parse", "HEAD^{tree}"), expected.tree_sha),
        (("status", "--porcelain=v1", "--untracked-files=all"), ""),
    )
    for arguments, expected_output in checks:
        output = _run_git(path, *arguments)
        if expected_output is not None and output != expected_output:
            raise RefreshFailure("installed snapshot Git identity changed")


def _backup(path: Path, destination: Path) -> str | None:
    if not path.exists() and not path.is_symlink():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_dir() and not path.is_symlink():
        raise RefreshFailure("file backup target is unexpectedly a directory")
    shutil.copy2(path, destination, follow_symlinks=False)
    return str(destination)


def _restore_file(target: Path, backup: str | None) -> None:
    if backup is None:
        target.unlink(missing_ok=True)
        return
    source = Path(backup)
    if source.exists() or source.is_symlink():
        os.replace(source, target)


def _rollback_switch(
    policy: RefreshPolicy, journal: RefreshJournal, *, root: Path = Path("/")
) -> None:
    pointer = _at(root, policy.current_pointer)
    pointer.unlink(missing_ok=True)
    if journal.previous_pointer is not None:
        os.symlink(journal.previous_pointer, pointer)
    boundary = _at(root, policy.repository_boundary)
    previous_repository = (
        Path(journal.previous_repository)
        if journal.previous_repository is not None
        else None
    )
    should_remove_boundary = not journal.repository_was_present or (
        previous_repository is not None and previous_repository.exists()
    )
    if should_remove_boundary and boundary.exists():
        failed = _at(root, policy.journal_root) / "failed" / journal.transaction_id
        failed.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if failed.exists():
            shutil.rmtree(failed)
        os.replace(boundary, failed)
    if previous_repository is not None and previous_repository.exists():
        os.replace(previous_repository, boundary)
    _restore_file(
        _at(root, policy.runtime_manifest_path), journal.previous_runtime_manifest
    )
    _restore_file(
        _at(root, policy.environment_path),
        journal.previous_environment,
    )
    _restore_file(
        _at(root, policy.effective_config_path),
        journal.previous_effective_config,
    )
    _restore_file(
        _at(root, policy.generation_manifest_path),
        journal.previous_generation_manifest,
    )
    if journal.generation_created:
        generation = Path(journal.generation_path)
        if generation.exists() and generation.is_dir() and not generation.is_symlink():
            shutil.rmtree(generation)


def _attest_committed(
    policy: RefreshPolicy,
    handoff: DeploymentUpdateHandoff,
    journal: RefreshJournal,
    *,
    root: Path,
) -> tuple[GenerationManifest, RepositorySnapshotManifest]:
    required_digests = (
        journal.generation_manifest_digest,
        journal.snapshot_manifest_digest,
        journal.runtime_manifest_digest,
        journal.environment_digest,
        journal.effective_config_digest,
    )
    if any(value is None for value in required_digests):
        raise RefreshFailure("committed refresh journal lacks artifact bindings")
    generation = Path(journal.generation_path)
    generation_manifest_path = generation / "GENERATION_MANIFEST.json"
    if _digest(generation_manifest_path) != journal.generation_manifest_digest:
        raise RefreshFailure("committed generation manifest was substituted")
    generation_manifest = GenerationManifest.model_validate_json(
        generation_manifest_path.read_bytes(), strict=True
    )
    if (
        generation_manifest.required_main_sha != handoff.required_main_sha
        or generation_manifest.required_main_tree_sha != handoff.required_main_tree_sha
        or generation_manifest.source_generation_id != handoff.source_generation_id
        or generation_manifest.source_generation_digest != handoff.source_generation_digest
    ):
        raise RefreshFailure("committed generation identity no longer matches handoff")
    _attest_generation(generation, generation_manifest)
    pointer = _at(root, policy.current_pointer)
    logical_generation = str(Path(policy.generation_root) / handoff.required_main_sha)
    if not pointer.is_symlink() or os.readlink(pointer) != logical_generation:
        raise RefreshFailure("committed generation pointer was substituted")
    boundary = _at(root, policy.repository_boundary)
    snapshot_path = boundary / "SNAPSHOT_MANIFEST.json"
    if _digest(snapshot_path) != journal.snapshot_manifest_digest:
        raise RefreshFailure("committed snapshot manifest was substituted")
    snapshot = RepositorySnapshotManifest.model_validate_json(
        snapshot_path.read_bytes(), strict=True
    )
    if (
        snapshot.main_sha != handoff.required_main_sha
        or snapshot.tree_sha != handoff.required_main_tree_sha
        or snapshot.source_generation_digest != handoff.source_generation_digest
    ):
        raise RefreshFailure("committed snapshot identity no longer matches handoff")
    _attest_repository_boundary(boundary, snapshot)
    artifacts = (
        (_at(root, policy.runtime_manifest_path), journal.runtime_manifest_digest),
        (_at(root, policy.environment_path), journal.environment_digest),
        (_at(root, policy.effective_config_path), journal.effective_config_digest),
        (
            _at(root, policy.generation_manifest_path),
            journal.generation_manifest_digest,
        ),
    )
    for artifact, expected_digest in artifacts:
        if _digest(artifact) != expected_digest:
            raise RefreshFailure("committed runtime artifact was substituted")
    runtime_raw = _trusted(
        _at(root, policy.runtime_manifest_path),
        uid=_at(root, policy.runtime_manifest_path).stat().st_uid,
        mode=0o444,
        maximum=2_000_000,
    )
    runtime = InstalledControllerRuntimeManifest.model_validate_json(runtime_raw, strict=True)
    if (
        runtime.computed_manifest_digest() != runtime.manifest_digest
        or runtime.repository_main_sha != handoff.required_main_sha
        or runtime.repository_tree_sha != handoff.required_main_tree_sha
        or runtime.package_manifest.digest != journal.generation_manifest_digest
        or runtime.repository_snapshot_manifest.digest != journal.snapshot_manifest_digest
        or runtime.environment_file.digest != journal.environment_digest
        or runtime.effective_config.digest != journal.effective_config_digest
    ):
        raise RefreshFailure("committed runtime manifest binding changed")
    return generation_manifest, snapshot


def _attest_pre_refresh(
    policy: RefreshPolicy,
    handoff: DeploymentUpdateHandoff,
    *,
    root: Path,
    authority_uid: int,
) -> InstalledControllerRuntimeManifest:
    manifest_path = _at(root, policy.runtime_manifest_path)
    raw = _trusted(
        manifest_path, uid=authority_uid, mode=0o444, maximum=2_000_000
    )
    if sha256_digest(raw) != handoff.installed_runtime_manifest_digest:
        raise RefreshFailure("installed runtime manifest differs from the handoff")
    try:
        runtime = InstalledControllerRuntimeManifest.model_validate_json(raw, strict=True)
    except ValueError as exc:
        raise RefreshFailure("installed runtime manifest is invalid") from exc
    if (
        runtime.computed_manifest_digest() != runtime.manifest_digest
        or runtime.repository_main_sha != handoff.installed_main_sha
        or runtime.repository_tree_sha != handoff.installed_main_tree_sha
    ):
        raise RefreshFailure("installed runtime identity differs from the handoff")
    for artifact in (
        runtime.python_runtime,
        runtime.package_manifest,
        runtime.dependency_lock,
        runtime.controller_unit,
        runtime.environment_file,
        runtime.effective_config,
        runtime.repository_snapshot_manifest,
    ):
        target = _at(root, artifact.path)
        target_stat = target.lstat()
        if (
            target.is_symlink()
            or not stat.S_ISREG(target_stat.st_mode)
            or target_stat.st_uid != authority_uid
            or target_stat.st_nlink != 1
            or _digest(target) != artifact.digest
            or artifact.executable != bool(target_stat.st_mode & 0o111)
        ):
            raise RefreshFailure("installed runtime artifact differs from its manifest")
    snapshot_path = _at(root, runtime.repository_snapshot_manifest.path)
    snapshot = RepositorySnapshotManifest.model_validate_json(
        snapshot_path.read_bytes(), strict=True
    )
    if (
        snapshot.main_sha != handoff.installed_main_sha
        or snapshot.tree_sha != handoff.installed_main_tree_sha
    ):
        raise RefreshFailure("installed snapshot differs from the handoff")
    _attest_repository_boundary(_at(root, policy.repository_boundary), snapshot)
    return runtime


def _write_completion(
    *,
    handoff: DeploymentUpdateHandoff,
    journal: RefreshJournal,
    journal_root: Path,
) -> Path:
    if any(
        value is None
        for value in (
            journal.generation_manifest_digest,
            journal.runtime_manifest_digest,
            journal.environment_digest,
            journal.effective_config_digest,
            journal.snapshot_manifest_digest,
        )
    ):
        raise RefreshFailure("committed refresh cannot produce an unbound completion")
    completion = RefreshCompletion(
        transaction_id=journal.transaction_id,
        handoff_digest=journal.handoff_digest,
        previous_main_sha=handoff.installed_main_sha,
        required_main_sha=handoff.required_main_sha,
        required_main_tree_sha=handoff.required_main_tree_sha,
        source_generation_id=handoff.source_generation_id,
        source_generation_digest=handoff.source_generation_digest,
        generation_manifest_digest=cast(str, journal.generation_manifest_digest),
        runtime_manifest_digest=cast(str, journal.runtime_manifest_digest),
        environment_digest=cast(str, journal.environment_digest),
        effective_config_digest=cast(str, journal.effective_config_digest),
        snapshot_manifest_digest=cast(str, journal.snapshot_manifest_digest),
        committed_at=datetime.now(UTC),
    )
    path = (
        journal_root
        / "completions"
        / f"{handoff.required_main_sha}-{journal.transaction_id}.json"
    )
    raw = canonical_json_bytes(completion)
    if path.is_file():
        existing = RefreshCompletion.model_validate_json(path.read_bytes(), strict=True)
        # committedAt is immutable after first publication; every authority binding must match.
        if existing.model_copy(update={"committed_at": completion.committed_at}) != completion:
            raise RefreshFailure("refresh completion identity conflicts")
        return path
    _atomic_json(path, raw, 0o400)
    return path


def refresh(
    policy: RefreshPolicy,
    handoff_path: Path,
    *,
    apply: bool = False,
    fail_hook: Callable[[str], None] | None = None,
    root: Path = Path("/"),
    authority_uid: int = 0,
    controller_active: Callable[[], bool] | None = None,
) -> RefreshResult:
    handoff = cast(
        DeploymentUpdateHandoff,
        _canonical_model(
            handoff_path,
            DeploymentUpdateHandoff,
            uid=authority_uid,
            mode=0o400,
        ),
    )
    raw_handoff = handoff_path.read_bytes()
    handoff_digest = sha256_digest(raw_handoff)
    expected_name = f"{handoff.required_main_sha}-{handoff_digest[7:23]}.json"
    if (
        handoff_path.name != expected_name
        or handoff_path.parent != _at(root, policy.handoff_root)
    ):
        raise RefreshFailure("deployment handoff identity is invalid")
    _attest_pre_refresh(
        policy, handoff, root=root, authority_uid=authority_uid
    )
    request, observed, ruleset, publication, bundle = _find_evidence(
        _at(root, policy.evidence_root), handoff
    )
    anchor_policy_path = _at(
        root, "/etc/traincapsule-verifier/git-anchor-policy.json"
    )
    anchor_policy_raw = _trusted(
        anchor_policy_path, uid=authority_uid, mode=0o644, maximum=64_000
    )
    try:
        anchor_policy = AnchorUpdatePolicy.model_validate_json(anchor_policy_raw, strict=True)
    except ValueError as exc:
        raise RefreshFailure("anchor update policy schema is invalid") from exc
    if canonical_json_bytes(anchor_policy) != anchor_policy_raw:
        raise RefreshFailure("anchor update policy is not canonical")
    request_raw = _trusted(
        request, uid=authority_uid, mode=0o400, maximum=64_000
    )
    observed_raw = _trusted(
        observed, uid=authority_uid, mode=0o400, maximum=1_000_000
    )
    ruleset_raw = _trusted(
        ruleset, uid=authority_uid, mode=0o400, maximum=1_000_000
    )
    publication_raw = _trusted(
        publication, uid=authority_uid, mode=0o400, maximum=1_000_000
    )
    _verify_evidence(
        handoff=handoff,
        request_raw=request_raw,
        observed_raw=observed_raw,
        ruleset_raw=ruleset_raw,
        publication_raw=publication_raw,
        bundle=bundle,
        policy=anchor_policy,
        selector_public_key=_trusted(
            _at(root, "/etc/traincapsule-verifier/selector-public-key.pem"),
            uid=authority_uid,
            mode=0o444,
            maximum=8_192,
        ),
        ruleset_public_key=_trusted(
            _at(root, "/etc/traincapsule-verifier/ruleset-public-key.pem"),
            uid=authority_uid,
            mode=0o444,
            maximum=8_192,
        ),
    )
    anchor = _at(root, policy.anchor_root)
    if (
        _run_git(anchor, "rev-parse", "refs/heads/main")
        != handoff.required_main_sha
        or _run_git(anchor, "rev-parse", f"{handoff.required_main_sha}^{{tree}}")
        != handoff.required_main_tree_sha
        or _run_git(anchor, "remote")
        or (anchor / "hooks").exists()
        or (anchor / "objects/info/alternates").exists()
    ):
        raise RefreshFailure("credential-free anchor does not match the required main")
    logical_generation = Path(policy.generation_root) / handoff.required_main_sha
    generation_target = _at(root, str(logical_generation))
    if not apply:
        with tempfile.TemporaryDirectory(prefix="traincapsule-refresh-preflight-") as raw:
            _build_generation(
                policy=policy,
                handoff=handoff,
                bundle=bundle,
                stage=Path(raw),
                root=root,
                authority_uid=authority_uid,
            )
        return RefreshResult(
            state="DRY_RUN",
            required_main_sha=handoff.required_main_sha,
            generation=str(logical_generation),
        )
    if root == Path("/") and os.geteuid() != 0:
        raise RefreshFailure("deployment refresh apply requires root")
    if controller_active is None:
        active = subprocess.run(
            ["/usr/bin/systemctl", "is-active", "--quiet", policy.controller_unit],
            check=False,
            timeout=20,
        ).returncode == 0
    else:
        active = controller_active()
    if active:
        raise RefreshFailure("controller must already be stopped by the cycle boundary")
    journal_root = _at(root, policy.journal_root)
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
            _attest_committed(policy, handoff, prior, root=root)
            _write_completion(handoff=handoff, journal=prior, journal_root=journal_root)
            return RefreshResult(
                state="COMMITTED",
                required_main_sha=handoff.required_main_sha,
                generation=str(logical_generation),
            )
        if prior.phase in {"SWITCHING", "SWITCHED"}:
            _rollback_switch(policy, prior, root=root)
            rolled_back = prior.model_copy(update={"phase": "ROLLED_BACK"})
            _atomic_json(journal_path, canonical_json_bytes(rolled_back), 0o600)
    prepared = RefreshJournal(
        transaction_id=transaction_id,
        handoff_digest=handoff_digest,
        required_main_sha=handoff.required_main_sha,
        phase="PREPARED",
        generation_path=str(generation_target),
    )
    _atomic_json(journal_path, canonical_json_bytes(prepared), 0o600)
    generation_root = _at(root, policy.generation_root)
    generation_root.mkdir(parents=True, exist_ok=True, mode=0o755)
    raw_stage = tempfile.mkdtemp(prefix=".refresh-stage-", dir=generation_root)
    boundary_stage = _at(root, policy.repository_boundary).with_name(
        f".repository-boundary.{transaction_id}.stage"
    )
    switching: RefreshJournal | None = None
    try:
        staged, manifest, effective_config = _build_generation(
            policy=policy,
            handoff=handoff,
            bundle=bundle,
            stage=Path(raw_stage),
            root=root,
            authority_uid=authority_uid,
        )
        generation_created = False
        if generation_target.exists():
            existing = GenerationManifest.model_validate_json(
                (generation_target / "GENERATION_MANIFEST.json").read_bytes(), strict=True
            )
            if existing != manifest:
                raise RefreshFailure("existing generation identity conflicts")
            _attest_generation(generation_target, existing)
            shutil.rmtree(staged)
        else:
            os.replace(staged, generation_target)
            generation_created = True
        staged_journal = prepared.model_copy(
            update={"phase": "STAGED", "generation_created": generation_created}
        )
        _atomic_json(journal_path, canonical_json_bytes(staged_journal), 0o600)
        if fail_hook is not None:
            fail_hook("STAGED")
        if boundary_stage.exists():
            shutil.rmtree(boundary_stage)
        shutil.copytree(
            generation_target / "repository",
            boundary_stage,
            symlinks=False,
            copy_function=shutil.copy2,
        )
        snapshot = RepositorySnapshotManifest.model_validate_json(
            (boundary_stage / "SNAPSHOT_MANIFEST.json").read_bytes(), strict=True
        )
        _attest_repository_boundary(boundary_stage, snapshot)
        environment = (
            "TCF_RUNTIME_ROOT=/var/lib/traincapsule-runtime\n"
            "PYTHONSAFEPATH=1\n"
            "PYTHONNOUSERSITE=1\n"
            f"PYTHONPATH={logical_generation}/site-packages\n"
        ).encode()
        runtime_manifest = _runtime_manifest(
            policy=policy,
            handoff=handoff,
            generation_path=logical_generation,
            generation=manifest,
            snapshot_digest=_digest(boundary_stage / "SNAPSHOT_MANIFEST.json"),
            environment_raw=environment,
            effective_config_raw=effective_config,
            root=root,
            authority_uid=authority_uid,
        )
        backup_root = journal_root / "backups" / transaction_id
        runtime_backup = _backup(
            _at(root, policy.runtime_manifest_path), backup_root / "runtime-manifest.json"
        )
        environment_backup = _backup(
            _at(root, policy.environment_path), backup_root / "controller-runtime.env"
        )
        config_backup = _backup(
            _at(root, policy.effective_config_path), backup_root / "effective-config.yaml"
        )
        generation_manifest_backup = _backup(
            _at(root, policy.generation_manifest_path),
            backup_root / "deployment-generation.json",
        )
        pointer = _at(root, policy.current_pointer)
        if pointer.exists() and not pointer.is_symlink():
            raise RefreshFailure("current generation pointer is not a symlink")
        previous_pointer = os.readlink(pointer) if pointer.is_symlink() else None
        if previous_pointer is not None and not Path(previous_pointer).is_relative_to(
            Path(policy.generation_root)
        ):
            raise RefreshFailure("current generation pointer escapes its root")
        boundary = _at(root, policy.repository_boundary)
        previous_repository = backup_root / "repository-boundary"
        switching = staged_journal.model_copy(
            update={
                "phase": "SWITCHING",
                "repository_was_present": boundary.exists(),
                "previous_pointer": previous_pointer,
                "previous_repository": str(previous_repository),
                "previous_runtime_manifest": runtime_backup,
                "previous_environment": environment_backup,
                "previous_effective_config": config_backup,
                "previous_generation_manifest": generation_manifest_backup,
            }
        )
        _atomic_json(journal_path, canonical_json_bytes(switching), 0o600)
        if fail_hook is not None:
            fail_hook("SWITCHING")
        if boundary.exists():
            os.replace(boundary, previous_repository)
        os.replace(boundary_stage, boundary)
        _atomic_json(
            _at(root, policy.runtime_manifest_path), runtime_manifest, 0o444
        )
        _atomic_json(_at(root, policy.environment_path), environment, 0o444)
        _atomic_json(
            _at(root, policy.effective_config_path), effective_config, 0o444
        )
        _atomic_json(
            _at(root, policy.generation_manifest_path),
            canonical_json_bytes(manifest),
            0o444,
        )
        temporary_pointer = pointer.with_name(f".{pointer.name}.{os.getpid()}.tmp")
        os.symlink(str(logical_generation), temporary_pointer)
        os.replace(temporary_pointer, pointer)
        _attest_generation(generation_target, manifest)
        _attest_repository_boundary(boundary, snapshot)
        if (
            _digest(_at(root, policy.runtime_manifest_path))
            != sha256_digest(runtime_manifest)
            or _digest(_at(root, policy.environment_path)) != sha256_digest(environment)
            or _digest(_at(root, policy.effective_config_path))
            != sha256_digest(effective_config)
        ):
            raise RefreshFailure("refreshed controller configuration changed")
        switched = switching.model_copy(update={"phase": "SWITCHED"})
        generation_digest = _digest(generation_target / "GENERATION_MANIFEST.json")
        snapshot_digest = _digest(boundary / "SNAPSHOT_MANIFEST.json")
        switched = switched.model_copy(
            update={
                "generation_manifest_digest": generation_digest,
                "snapshot_manifest_digest": snapshot_digest,
                "runtime_manifest_digest": sha256_digest(runtime_manifest),
                "environment_digest": sha256_digest(environment),
                "effective_config_digest": sha256_digest(effective_config),
            }
        )
        _atomic_json(journal_path, canonical_json_bytes(switched), 0o600)
        if fail_hook is not None:
            fail_hook("SWITCHED")
        committed = switched.model_copy(update={"phase": "COMMITTED"})
        _atomic_json(journal_path, canonical_json_bytes(committed), 0o600)
        _attest_committed(policy, handoff, committed, root=root)
        _write_completion(
            handoff=handoff, journal=committed, journal_root=journal_root
        )
    except Exception:
        if switching is not None:
            _rollback_switch(policy, switching, root=root)
            rolled_back = switching.model_copy(update={"phase": "ROLLED_BACK"})
            _atomic_json(journal_path, canonical_json_bytes(rolled_back), 0o600)
        raise
    finally:
        if Path(raw_stage).exists():
            shutil.rmtree(raw_stage)
        if boundary_stage.exists():
            shutil.rmtree(boundary_stage)
    # Deliberately do not start/restart the controller.  Existing gated start path is
    # notified by its own independently verified request/receipt transition.
    return RefreshResult(
        state="COMMITTED",
        required_main_sha=handoff.required_main_sha,
        generation=str(logical_generation),
    )


def load_policy(path: Path = POLICY_PATH) -> RefreshPolicy:
    return cast(RefreshPolicy, _canonical_model(path, RefreshPolicy, uid=0, mode=0o444))


def process_pending(policy: RefreshPolicy, *, apply: bool) -> list[RefreshResult]:
    handoffs = sorted(Path(policy.handoff_root).glob("*.json"))
    if len(handoffs) > 1:
        raise RefreshFailure("deployment handoff inbox is ambiguous")
    results: list[RefreshResult] = []
    for handoff in handoffs:
        result = refresh(policy, handoff, apply=apply)
        results.append(result)
        if apply and result.state == "COMMITTED":
            consumed = Path(policy.journal_root) / "consumed" / handoff.name
            consumed.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if consumed.is_file():
                if consumed.read_bytes() != handoff.read_bytes():
                    raise RefreshFailure("consumed handoff identity conflicts")
                handoff.unlink()
            else:
                os.replace(handoff, consumed)
                os.chmod(consumed, 0o600)
    return results


# Public, testable no-hook transaction primitives.  The service entry point composes
# the same functions; exposing them avoids test-only privileged execution.
build_generation = _build_generation
attest_generation = _attest_generation
attest_repository_boundary = _attest_repository_boundary
rollback_switch = _rollback_switch
extract_tree_files = _tree_files


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="traincapsule-deployment-refresh")
    parser.add_argument("handoff", type=Path, nargs="?")
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--claim-only", action="store_true")
    parser.add_argument("--publish-activation-completion", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    try:
        if args.apply and args.confirm != APPLY_CONFIRMATION:
            raise RefreshFailure("apply confirmation token is missing")
        policy = load_policy(args.policy)
        if args.claim_only:
            if not args.apply:
                raise RefreshFailure("claim broker requires explicit apply")
            claimed = claim_pending(policy)
            print(json.dumps({"claimed": len(claimed)}, sort_keys=True))
            return 0
        if args.publish_activation_completion:
            if not args.apply:
                raise RefreshFailure("activation completion broker requires explicit apply")
            published = publish_activation_completions(policy)
            print(json.dumps({"published": len(published)}, sort_keys=True))
            return 0
        results = (
            process_pending(policy, apply=args.apply)
            if args.handoff is None
            else [refresh(policy, args.handoff, apply=args.apply)]
        )
    except (OSError, ValueError, RefreshFailure):
        print("deployment refresh failed closed", file=sys.stderr)
        return 1
    print(json.dumps([result.__dict__ for result in results], sort_keys=True))
    return 0
