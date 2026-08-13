"""Build an exact deterministic immutable repository snapshot from Git objects."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import zipfile
import zlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Literal, cast

import yaml
from traincapsule_verifier.canonical import canonical_json_bytes, sha256_digest

from .privileged_installer import (
    RepositorySnapshotManifest,
    SnapshotEntry,
    SnapshotGitObject,
    validate_repository_snapshot_archive,
)

MAX_OBJECTS = 1_000_000
MAX_ENTRIES = 1_000_000
MAX_TOTAL_BYTES = 4_000_000_000
_GIT_ENV = {
    "PATH": "/usr/bin:/bin",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_NO_REPLACE_OBJECTS": "1",
}


class RepositorySnapshotError(RuntimeError):
    """The selected Git commit or snapshot output is unsafe or inconsistent."""


@dataclass(frozen=True)
class _TrackedFile:
    path: str
    object_id: str
    mode: int


def _git(
    repository: Path,
    arguments: Sequence[str],
    *,
    input_bytes: bytes | None = None,
    timeout: int = 120,
) -> bytes:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), *arguments],
        input=input_bytes,
        check=False,
        capture_output=True,
        timeout=timeout,
        env=_GIT_ENV,
    )
    if result.returncode != 0:
        raise RepositorySnapshotError("trusted Git object operation failed")
    return result.stdout


def _exact_commit(repository: Path, candidate: str) -> tuple[str, str]:
    try:
        main = _git(
            repository, ["rev-parse", "--verify", f"{candidate}^{{commit}}"]
        ).decode("ascii").strip()
        tree = _git(
            repository, ["rev-parse", "--verify", f"{candidate}^{{tree}}"]
        ).decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise RepositorySnapshotError("Git candidate identity is not ASCII") from exc
    if (
        len(main) != 40
        or len(tree) != 40
        or any(character not in "0123456789abcdef" for character in main + tree)
    ):
        raise RepositorySnapshotError("Git candidate identity is not exact SHA-1")
    return main, tree


def _tracked_files(repository: Path, candidate_sha: str) -> list[_TrackedFile]:
    raw = _git(repository, ["ls-tree", "-rz", "--full-tree", "-r", candidate_sha])
    files: list[_TrackedFile] = []
    seen: set[str] = set()
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, path_raw = record.split(b"\t", 1)
            mode_raw, kind_raw, object_raw = metadata.split(b" ", 2)
            path = path_raw.decode("utf-8")
            mode_text = mode_raw.decode("ascii")
            kind = kind_raw.decode("ascii")
            object_id = object_raw.decode("ascii")
        except (UnicodeDecodeError, ValueError) as exc:
            raise RepositorySnapshotError("Git tree entry is malformed") from exc
        pure = PurePosixPath(path)
        if (
            kind != "blob"
            or mode_text not in {"100644", "100755"}
            or pure.is_absolute()
            or ".." in pure.parts
            or str(pure) != path
            or path in seen
            or path == "SNAPSHOT_MANIFEST.json"
            or len(object_id) != 40
            or any(character not in "0123456789abcdef" for character in object_id)
        ):
            raise RepositorySnapshotError(
                "Git tree contains a link, submodule, unsafe path, or unsupported entry"
            )
        seen.add(path)
        files.append(
            _TrackedFile(
                path=path,
                object_id=object_id,
                mode=0o555 if mode_text == "100755" else 0o444,
            )
        )
    if not files or len(files) > MAX_ENTRIES:
        raise RepositorySnapshotError("Git tree file inventory is empty or excessive")
    return sorted(files, key=lambda item: item.path)


def _reachable_objects(repository: Path, candidate_sha: str) -> list[str]:
    raw = _git(repository, ["rev-list", "--objects", candidate_sha], timeout=300)
    objects: set[str] = set()
    for line in raw.splitlines():
        object_raw = line.split(b" ", 1)[0]
        try:
            object_id = object_raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise RepositorySnapshotError("Git object identity is not ASCII") from exc
        if len(object_id) != 40 or any(
            character not in "0123456789abcdef" for character in object_id
        ):
            raise RepositorySnapshotError("Git reachable-object inventory is malformed")
        objects.add(object_id)
    if not objects or len(objects) > MAX_OBJECTS:
        raise RepositorySnapshotError("Git reachable-object inventory is empty or excessive")
    return sorted(objects)


def _directories_for(paths: Iterable[str]) -> set[str]:
    directories: set[str] = set()
    for path in paths:
        parent = PurePosixPath(path).parent
        while str(parent) != ".":
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _write_file(root: Path, relative: str, raw: bytes, mode: int) -> None:
    target = root.joinpath(*PurePosixPath(relative).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise RepositorySnapshotError("snapshot staging path collided")
    target.write_bytes(raw)
    target.chmod(mode)


def _copy_exact(stream: BinaryIO, destination: Path, size: int) -> None:
    remaining = size
    with destination.open("xb") as output:
        while remaining:
            chunk = stream.read(min(1_048_576, remaining))
            if not chunk:
                raise RepositorySnapshotError("Git object batch ended unexpectedly")
            output.write(chunk)
            remaining -= len(chunk)
    destination.chmod(0o600)


def _materialize_objects_and_files(
    repository: Path,
    stage: Path,
    object_ids: Sequence[str],
    tracked: Sequence[_TrackedFile],
) -> list[SnapshotGitObject]:
    paths_by_blob: dict[str, list[_TrackedFile]] = {}
    for item in tracked:
        paths_by_blob.setdefault(item.object_id, []).append(item)
    git_objects: list[SnapshotGitObject] = []
    total_bytes = 0
    process: subprocess.Popen[bytes] = subprocess.Popen(
        ["/usr/bin/git", "-C", str(repository), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_GIT_ENV,
    )
    if process.stdin is None or process.stdout is None or process.stderr is None:
        process.kill()
        raise RepositorySnapshotError("Git object batch streams are unavailable")
    stdin = cast(BinaryIO, process.stdin)
    stdout = cast(BinaryIO, process.stdout)
    stderr = cast(BinaryIO, process.stderr)
    operation_failed = False
    try:
        for object_id in object_ids:
            stdin.write((object_id + "\n").encode("ascii"))
            stdin.flush()
            header = stdout.readline()
            try:
                actual_raw, kind_raw, size_raw = header.rstrip(b"\n").split(b" ", 2)
                actual = actual_raw.decode("ascii")
                kind = kind_raw.decode("ascii")
                size = int(size_raw)
            except (UnicodeDecodeError, ValueError) as exc:
                raise RepositorySnapshotError("Git object batch header is malformed") from exc
            if (
                actual != object_id
                or kind not in {"blob", "tree", "commit", "tag"}
                or size < 0
                or size > 2_000_000_000
            ):
                raise RepositorySnapshotError("Git object batch identity is inconsistent")
            total_bytes += size
            if total_bytes > MAX_TOTAL_BYTES:
                raise RepositorySnapshotError("Git object inventory exceeds the safety limit")
            temporary = stage / ".object-content"
            _copy_exact(stdout, temporary, size)
            if stdout.read(1) != b"\n":
                raise RepositorySnapshotError("Git object batch framing is malformed")
            header_raw = f"{kind} {size}\0".encode("ascii")
            identity = hashlib.sha1(header_raw, usedforsecurity=False)
            with temporary.open("rb") as source:
                while chunk := source.read(1_048_576):
                    identity.update(chunk)
            if identity.hexdigest() != object_id:
                raise RepositorySnapshotError("Git object content identity mismatch")
            object_target = stage / ".git/objects" / object_id[:2] / object_id[2:]
            object_target.parent.mkdir(parents=True, exist_ok=True)
            compressor = zlib.compressobj(level=9)
            with object_target.open("xb") as output, temporary.open("rb") as source:
                output.write(compressor.compress(header_raw))
                while chunk := source.read(1_048_576):
                    output.write(compressor.compress(chunk))
                output.write(compressor.flush())
            object_target.chmod(0o444)
            if kind == "blob":
                for tracked_file in paths_by_blob.get(object_id, []):
                    target = stage.joinpath(*PurePosixPath(tracked_file.path).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists() or target.is_symlink():
                        raise RepositorySnapshotError("tracked file staging path collided")
                    shutil.copyfile(temporary, target)
                    target.chmod(tracked_file.mode)
            temporary.unlink()
            git_objects.append(
                SnapshotGitObject(
                    object_id=object_id,
                    kind=cast(Literal["blob", "tree", "commit", "tag"], kind),
                    size=size,
                )
            )
    except BaseException:
        operation_failed = True
        process.kill()
        process.wait(timeout=60)
        raise
    finally:
        if not operation_failed:
            stdin.close()
            return_code = process.wait(timeout=60)
            error = stderr.read()
            if return_code != 0 or error:
                raise RepositorySnapshotError("Git object batch operation failed")
    if set(paths_by_blob) - {item.object_id for item in git_objects if item.kind == "blob"}:
        raise RepositorySnapshotError("tracked Git blob is not reachable from the candidate")
    return git_objects


def _initialize_git_controls(stage: Path, main_sha: str) -> None:
    _write_file(
        stage,
        ".git/config",
        (
            b"[core]\n"
            b"\trepositoryformatversion = 0\n"
            b"\tfilemode = true\n"
            b"\tbare = false\n"
            b"\tlogallrefupdates = false\n"
        ),
        0o444,
    )
    _write_file(stage, ".git/HEAD", b"ref: refs/heads/main\n", 0o444)
    _write_file(stage, ".git/refs/heads/main", (main_sha + "\n").encode("ascii"), 0o444)
    _write_file(stage, ".git/info/exclude", b"/SNAPSHOT_MANIFEST.json\n", 0o444)
    index = stage / ".git/index"
    result = subprocess.run(
        ["/usr/bin/git", "read-tree", main_sha],
        check=False,
        capture_output=True,
        timeout=120,
        env={
            **_GIT_ENV,
            "GIT_DIR": str(stage / ".git"),
            "GIT_WORK_TREE": str(stage),
            "GIT_INDEX_FILE": str(index),
            "GIT_INDEX_VERSION": "2",
        },
    )
    if result.returncode != 0 or not index.is_file() or index.is_symlink():
        raise RepositorySnapshotError("deterministic Git index creation failed")
    index.chmod(0o444)


def materialize_exact_repository_tree(
    repository: Path, candidate: str, destination: Path
) -> tuple[str, str]:
    """Materialize tracked regular files from one exact commit, never the worktree."""

    repo = repository.resolve(strict=True)
    if destination.exists() or destination.is_symlink():
        raise RepositorySnapshotError("exact repository destination must be absent")
    main_sha, tree_sha = _exact_commit(repo, candidate)
    tracked = _tracked_files(repo, main_sha)
    destination.mkdir(parents=True)
    object_ids = sorted({item.object_id for item in tracked})
    _materialize_objects_and_files(repo, destination, object_ids, tracked)
    shutil.rmtree(destination / ".git")
    for directory in sorted(_directories_for(item.path for item in tracked)):
        destination.joinpath(*PurePosixPath(directory).parts).chmod(0o755)
    return main_sha, tree_sha


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1_048_576):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _binding_digest(path: Path, *, label: str) -> str:
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_file() or resolved.stat().st_size > 128_000_000:
        raise RepositorySnapshotError(f"{label} binding is not a bounded regular file")
    return _sha256_file(resolved)


def _source_authority(stage: Path, requested_path: str | None) -> tuple[str, str]:
    active_path = stage / "config/active_generation.yaml"
    try:
        active_value: object = yaml.safe_load(active_path.read_bytes())
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise RepositorySnapshotError("active source-generation pointer is invalid") from exc
    if not isinstance(active_value, dict):
        raise RepositorySnapshotError("active source-generation pointer is not a mapping")
    active = cast(dict[str, object], active_value)
    generation_id = active.get("generationId")
    manifest_value = active.get("manifestPath")
    if not isinstance(generation_id, str) or not isinstance(manifest_value, str):
        raise RepositorySnapshotError("active source-generation identity is incomplete")
    source_path = requested_path or manifest_value
    if requested_path is not None and requested_path != manifest_value:
        raise RepositorySnapshotError("requested source manifest is not the active authority")
    pure = PurePosixPath(source_path)
    if pure.is_absolute() or ".." in pure.parts or str(pure) != source_path:
        raise RepositorySnapshotError("source manifest path is not normalized")
    target = stage.joinpath(*pure.parts)
    try:
        raw = target.read_bytes()
        value: object = json.loads(raw)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise RepositorySnapshotError("source-generation manifest is invalid") from exc
    if not isinstance(value, dict):
        raise RepositorySnapshotError("source-generation manifest identity is inconsistent")
    source_manifest = cast(dict[str, object], value)
    if source_manifest.get("generationId") != generation_id:
        raise RepositorySnapshotError("source-generation manifest identity is inconsistent")
    return source_path, _sha256_file(target)


def _zip_info(relative: str, *, directory: bool, mode: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(relative + ("/" if directory else ""))
    info.date_time = (1980, 1, 1, 0, 0, 0)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = ((stat.S_IFDIR if directory else stat.S_IFREG) | mode) << 16
    return info


def _inventory(stage: Path) -> list[SnapshotEntry]:
    entries: list[SnapshotEntry] = []
    paths = sorted(stage.rglob("*"), key=lambda item: item.relative_to(stage).as_posix())
    for path in paths:
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise RepositorySnapshotError("snapshot staging tree contains an unsafe entry")
        relative = path.relative_to(stage).as_posix()
        mode = 0o555 if path.is_dir() or os.access(path, os.X_OK) else 0o444
        entries.append(
            SnapshotEntry(
                path=relative,
                kind="directory" if path.is_dir() else "file",
                mode=f"0{mode:03o}",
                digest=None if path.is_dir() else _sha256_file(path),
            )
        )
    if not entries or len(entries) > MAX_ENTRIES:
        raise RepositorySnapshotError("snapshot complete inventory is empty or excessive")
    return entries


def _write_archive(archive_path: Path, stage: Path, entries: Sequence[SnapshotEntry]) -> None:
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_STORED) as archive:
        for entry in entries:
            source = stage.joinpath(*PurePosixPath(entry.path).parts)
            mode = int(entry.mode, 8)
            info = _zip_info(entry.path, directory=entry.kind == "directory", mode=mode)
            if entry.kind == "directory":
                archive.writestr(info, b"")
            else:
                with archive.open(info, "w") as output, source.open("rb") as input_file:
                    shutil.copyfileobj(input_file, output, length=1_048_576)
    archive_path.chmod(0o444)


def build_repository_snapshot(
    *,
    repository: Path,
    candidate: str,
    output: Path,
    effective_config: Path,
    python_runtime_manifest: Path,
    package_manifest: Path,
    dependency_lock: Path,
    source_manifest_path: str | None = None,
) -> tuple[Path, Path]:
    """Build and self-validate one complete exact-commit repository snapshot."""

    repo = repository.resolve(strict=True)
    archive_path = output.absolute()
    manifest_path = archive_path.with_suffix(archive_path.suffix + ".manifest.json")
    if (
        archive_path.exists()
        or archive_path.is_symlink()
        or manifest_path.exists()
        or manifest_path.is_symlink()
        or archive_path.is_relative_to(repo)
    ):
        raise RepositorySnapshotError("snapshot outputs must be absent and outside the repository")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="traincapsule-repository-snapshot-", dir=archive_path.parent
    ) as temporary:
        stage = Path(temporary) / "tree"
        main_sha, tree_sha = _exact_commit(repo, candidate)
        tracked = _tracked_files(repo, main_sha)
        stage.mkdir()
        git_objects = _materialize_objects_and_files(
            repo, stage, _reachable_objects(repo, main_sha), tracked
        )
        _initialize_git_controls(stage, main_sha)
        source_path, source_digest = _source_authority(stage, source_manifest_path)
        for directory in sorted(stage.rglob("*"), reverse=True):
            if directory.is_dir():
                directory.chmod(0o555)
        entries = _inventory(stage)
        _write_archive(archive_path, stage, entries)
        provisional = RepositorySnapshotManifest.model_construct(
            schema_version="3.1",
            manifest_digest="sha256:" + "0" * 64,
            main_sha=main_sha,
            tree_sha=tree_sha,
            source_manifest_path=source_path,
            source_generation_digest=source_digest,
            effective_config_digest=_binding_digest(
                effective_config, label="effective configuration"
            ),
            python_runtime_manifest_digest=_binding_digest(
                python_runtime_manifest, label="Python runtime manifest"
            ),
            package_manifest_digest=_binding_digest(
                package_manifest, label="controller package manifest"
            ),
            dependency_lock_digest=_binding_digest(
                dependency_lock, label="dependency lock"
            ),
            entries=entries,
            git_objects=sorted(git_objects, key=lambda item: item.object_id),
        )
        payload = provisional.model_dump(mode="json", by_alias=True)
        payload["manifestDigest"] = sha256_digest(canonical_json_bytes(payload))
        manifest = RepositorySnapshotManifest.model_validate(payload, strict=True)
        manifest_path.write_bytes(canonical_json_bytes(manifest))
        manifest_path.chmod(0o444)
    validate_repository_snapshot_archive(archive_path, manifest)
    return archive_path, manifest_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an exact deterministic TrainCapsule repository snapshot"
    )
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--candidate", default="HEAD")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--effective-config", type=Path, required=True)
    parser.add_argument("--python-runtime-manifest", type=Path, required=True)
    parser.add_argument("--package-manifest", type=Path, required=True)
    parser.add_argument("--dependency-lock", type=Path, required=True)
    parser.add_argument("--source-manifest-path")
    arguments = parser.parse_args(argv)
    try:
        archive, manifest = build_repository_snapshot(
            repository=arguments.repository,
            candidate=arguments.candidate,
            output=arguments.output,
            effective_config=arguments.effective_config,
            python_runtime_manifest=arguments.python_runtime_manifest,
            package_manifest=arguments.package_manifest,
            dependency_lock=arguments.dependency_lock,
            source_manifest_path=arguments.source_manifest_path,
        )
    except RepositorySnapshotError as exc:
        parser.exit(2, f"BLOCKED: {exc}\n")
    print(f"repository snapshot: {archive}")
    print(f"repository snapshot manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
