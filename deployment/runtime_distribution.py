"""Exact archive contract for the installed Python runtime distribution.

The production controller needs more than a Python ELF: it needs the matching
standard library and an importable, no-build-hook dependency layer.  This module
defines the complete byte inventory which the unprivileged assembler validates
and the privileged installer replays without executing package installers.
"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, model_validator
from traincapsule_verifier.canonical import canonical_json_bytes, sha256_digest
from traincapsule_verifier.models import StrictModel

PRODUCTION_RUNTIME_IMPORTS = (
    "annotated_doc",
    "annotated_types",
    "anyio",
    "attrs",
    "certifi",
    "cffi",
    "claude_agent_sdk",
    "click",
    "cryptography",
    "dateutil",
    "dotenv",
    "h11",
    "httpcore",
    "httpx",
    "httpx_sse",
    "idna",
    "jsonschema",
    "jsonschema_specifications",
    "jwt",
    "markdown_it",
    "mcp",
    "mdurl",
    "multipart",
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "pygments",
    "referencing",
    "rich",
    "rpds",
    "shellingham",
    "six",
    "sniffio",
    "sse_starlette",
    "starlette",
    "typer",
    "typing_extensions",
    "typing_inspection",
    "uvicorn",
    "yaml",
)
PROJECT_SOURCE_MAPPINGS = (
    ("tcfactory/", "tcfactory/"),
    ("deployment/", "deployment/"),
    ("verifier/src/traincapsule_verifier/", "traincapsule_verifier/"),
    ("canary_runner/src/traincapsule_canary_runner/", "traincapsule_canary_runner/"),
    ("packages/traincapsule-core/src/traincapsule_core/", "traincapsule_core/"),
    (
        "packages/traincapsule-ingest-pytorch/src/traincapsule_ingest_pytorch/",
        "traincapsule_ingest_pytorch/",
    ),
    ("packages/traincapsule-qualify/src/traincapsule_qualify/", "traincapsule_qualify/"),
    ("packages/traincapsule-cli/src/traincapsule_cli/", "traincapsule_cli/"),
)
PROJECT_RUNTIME_IMPORTS = tuple(target.rstrip("/") for _source, target in PROJECT_SOURCE_MAPPINGS)
COMPLETE_RUNTIME_IMPORTS = tuple(sorted((*PRODUCTION_RUNTIME_IMPORTS, *PROJECT_RUNTIME_IMPORTS)))


class RuntimeDistributionError(RuntimeError):
    """A runtime archive or its complete inventory is unsafe or inconsistent."""


class RuntimeDistributionEntry(StrictModel):
    path: str = Field(min_length=1, max_length=512)
    mode: Literal["0444", "0555"]
    size: int = Field(ge=0, le=512_000_000)
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def safe_relative_path(self) -> RuntimeDistributionEntry:
        parsed = PurePosixPath(self.path)
        if (
            parsed.is_absolute()
            or ".." in parsed.parts
            or "." in parsed.parts
            or not parsed.parts
            or self.path != parsed.as_posix()
        ):
            raise ValueError("runtime distribution path is unsafe")
        return self


class RuntimeDistributionManifest(StrictModel):
    schema_version: Literal["3.1"] = "3.1"
    manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    archive_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    python_version: str = Field(pattern=r"^3\.12\.\d+$")
    executable_path: Literal["bin/python3.12"] = "bin/python3.12"
    dependency_path: Literal["lib/python3.12/site-packages"] = (
        "lib/python3.12/site-packages"
    )
    executable_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    required_imports: list[str] = Field(min_length=1, max_length=256)
    entries: list[RuntimeDistributionEntry] = Field(min_length=2, max_length=100_000)

    @model_validator(mode="after")
    def exact_inventory(self) -> RuntimeDistributionManifest:
        paths = [entry.path for entry in self.entries]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError("runtime distribution inventory is not sorted and unique")
        by_path = {entry.path: entry for entry in self.entries}
        executable = by_path.get(self.executable_path)
        if executable is None or executable.mode != "0555":
            raise ValueError("runtime distribution executable is absent or non-executable")
        if executable.digest != self.executable_digest:
            raise ValueError("runtime distribution executable digest differs from inventory")
        if (
            self.required_imports != sorted(self.required_imports)
            or len(self.required_imports) != len(set(self.required_imports))
            or any(
                not name.replace("_", "a").isalnum() or name[0].isdigit()
                for name in self.required_imports
            )
        ):
            raise ValueError("runtime distribution required imports are invalid")
        if not any(path.startswith("lib/python3.12/") for path in paths):
            raise ValueError("runtime distribution has no Python 3.12 standard library")
        if not any(path.startswith(self.dependency_path + "/") for path in paths):
            raise ValueError("runtime distribution has no dependency site-packages")
        dependency_prefix = self.dependency_path + "/"
        dependency_files = {
            path.removeprefix(dependency_prefix)
            for path in paths
            if path.startswith(dependency_prefix)
        }
        for name in self.required_imports:
            if not (
                f"{name}.py" in dependency_files
                or any(path.startswith(name + "/") for path in dependency_files)
                or any(
                    path.startswith(name + ".") and path.endswith(".so")
                    for path in dependency_files
                )
            ):
                raise ValueError("runtime distribution required import is absent")
        zeroed = self.model_copy(update={"manifest_digest": "sha256:" + "0" * 64})
        if self.manifest_digest != sha256_digest(canonical_json_bytes(zeroed)):
            raise ValueError("runtime distribution manifest digest is invalid")
        return self


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _archive_members(archive_path: Path) -> dict[str, zipfile.ZipInfo]:
    if archive_path.is_symlink() or not archive_path.is_file():
        raise RuntimeDistributionError("runtime distribution archive is unavailable")
    members: dict[str, zipfile.ZipInfo] = {}
    total_size = 0
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                name = info.filename
                parsed = PurePosixPath(name)
                mode = (info.external_attr >> 16) & 0o177777
                if (
                    info.is_dir()
                    or parsed.is_absolute()
                    or ".." in parsed.parts
                    or "." in parsed.parts
                    or not parsed.parts
                    or name != parsed.as_posix()
                    or name in members
                    or stat.S_ISLNK(mode)
                    or not stat.S_ISREG(mode)
                ):
                    raise RuntimeDistributionError(
                        "runtime distribution archive contains an unsafe member"
                    )
                if info.file_size > 512_000_000:
                    raise RuntimeDistributionError(
                        "runtime distribution archive member size is invalid"
                    )
                total_size += info.file_size
                if total_size > 4_000_000_000:
                    raise RuntimeDistributionError(
                        "runtime distribution archive expanded size is invalid"
                    )
                members[name] = info
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, RuntimeDistributionError):
            raise
        raise RuntimeDistributionError("runtime distribution archive is invalid") from exc
    return members


def validate_runtime_distribution(
    archive_path: Path, manifest: RuntimeDistributionManifest
) -> None:
    """Verify every archive member against the self-digested complete inventory."""

    if _sha256_file(archive_path) != manifest.archive_digest:
        raise RuntimeDistributionError("runtime distribution archive digest differs")
    members = _archive_members(archive_path)
    if set(members) != {entry.path for entry in manifest.entries}:
        raise RuntimeDistributionError("runtime distribution archive inventory differs")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for entry in manifest.entries:
                info = members[entry.path]
                observed_mode = (info.external_attr >> 16) & 0o777
                digest = hashlib.sha256()
                size = 0
                with archive.open(info) as source:
                    while chunk := source.read(1024 * 1024):
                        size += len(chunk)
                        if size > entry.size:
                            raise RuntimeDistributionError(
                                "runtime distribution archive member differs"
                            )
                        digest.update(chunk)
                if (
                    observed_mode != int(entry.mode, 8)
                    or size != entry.size
                    or "sha256:" + digest.hexdigest() != entry.digest
                ):
                    raise RuntimeDistributionError(
                        "runtime distribution archive member differs"
                    )
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, RuntimeDistributionError):
            raise
        raise RuntimeDistributionError("runtime distribution archive is invalid") from exc


def extract_runtime_distribution(
    archive_path: Path,
    manifest: RuntimeDistributionManifest,
    destination: Path,
) -> None:
    """Atomically extract one verified distribution without links or build hooks."""

    validate_runtime_distribution(archive_path, manifest)
    if destination.exists() or destination.is_symlink():
        raise RuntimeDistributionError("runtime distribution destination must be absent")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".runtime-distribution-", dir=destination.parent))
    try:
        members = _archive_members(archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            for entry in manifest.entries:
                target = stage / entry.path
                target.parent.mkdir(parents=True, exist_ok=True)
                size = 0
                with archive.open(members[entry.path]) as source, target.open("xb") as sink:
                    while chunk := source.read(1024 * 1024):
                        size += len(chunk)
                        if size > entry.size:
                            raise RuntimeDistributionError(
                                "runtime distribution archive member differs during extraction"
                            )
                        sink.write(chunk)
                if size != entry.size:
                    raise RuntimeDistributionError(
                        "runtime distribution archive member differs during extraction"
                    )
                target.chmod(int(entry.mode, 8))
        for directory in sorted(
            (path for path in stage.rglob("*") if path.is_dir()), reverse=True
        ):
            directory.chmod(0o555)
        stage.chmod(0o555)
        os.rename(stage, destination)
    except BaseException:
        if stage.exists():
            for path in sorted(stage.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            stage.rmdir()
        raise


def validate_extracted_runtime_distribution(
    destination: Path,
    manifest: RuntimeDistributionManifest,
) -> None:
    """Reopen and verify the complete extracted tree without following links."""

    if destination.is_symlink() or not destination.is_dir():
        raise RuntimeDistributionError("runtime distribution destination is unavailable")
    observed_files: dict[str, Path] = {}
    for path in destination.rglob("*"):
        if path.is_symlink():
            raise RuntimeDistributionError("runtime distribution tree contains a link")
        relative = path.relative_to(destination).as_posix()
        if path.is_dir():
            if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != 0o555:
                raise RuntimeDistributionError("runtime distribution directory mode differs")
            continue
        if not path.is_file():
            raise RuntimeDistributionError("runtime distribution tree contains a special file")
        observed_files[relative] = path
    expected = {entry.path: entry for entry in manifest.entries}
    if set(observed_files) != set(expected):
        raise RuntimeDistributionError("runtime distribution extracted inventory differs")
    for relative, entry in expected.items():
        path = observed_files[relative]
        info = path.stat(follow_symlinks=False)
        if (
            stat.S_IMODE(info.st_mode) != int(entry.mode, 8)
            or info.st_size != entry.size
            or sha256_digest(path.read_bytes()) != entry.digest
        ):
            raise RuntimeDistributionError("runtime distribution extracted member differs")


def build_runtime_distribution(
    destination: Path,
    *,
    python_root: Path,
    dependency_root: Path,
    python_version: str,
    required_imports: Iterable[str],
) -> tuple[Path, Path]:
    """Build a deterministic archive from pre-provisioned runtime/dependency trees."""

    if destination.exists() or destination.is_symlink():
        raise RuntimeDistributionError("runtime distribution output must be absent")
    executable = python_root / "bin/python3.12"
    stdlib = python_root / "lib/python3.12"
    if executable.is_symlink() or not executable.is_file() or not stdlib.is_dir():
        raise RuntimeDistributionError("Python distribution root is incomplete")
    if dependency_root.is_symlink() or not dependency_root.is_dir():
        raise RuntimeDistributionError("dependency site-packages root is incomplete")
    roots = (
        (stdlib, PurePosixPath("lib/python3.12")),
        (dependency_root, PurePosixPath("lib/python3.12/site-packages")),
    )
    files: list[tuple[str, Path, int]] = [("bin/python3.12", executable, 0o555)]
    identities: set[tuple[int, int]] = set()
    executable_identity = (executable.stat().st_dev, executable.stat().st_ino)
    if executable.stat().st_nlink != 1:
        raise RuntimeDistributionError("runtime executable contains a hard link")
    identities.add(executable_identity)
    for root, prefix in roots:
        for source in sorted(path for path in root.rglob("*") if path.is_file()):
            if root == stdlib and source.relative_to(root).parts[0] == "site-packages":
                continue
            if source.is_symlink():
                raise RuntimeDistributionError("runtime input contains a symlink")
            identity = (source.stat().st_dev, source.stat().st_ino)
            if identity in identities or source.stat().st_nlink != 1:
                raise RuntimeDistributionError("runtime input contains a hard link")
            identities.add(identity)
            relative = prefix / source.relative_to(root).as_posix()
            mode = 0o555 if source.stat().st_mode & 0o111 else 0o444
            files.append((relative.as_posix(), source, mode))
    if not files:
        raise RuntimeDistributionError("runtime distribution input is empty")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination,
        "x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for relative, source, mode in sorted(files):
            info = zipfile.ZipInfo(relative)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, source.read_bytes())
    destination.chmod(0o444)
    entries = [
        RuntimeDistributionEntry(
            path=relative,
            mode="0555" if mode == 0o555 else "0444",
            size=source.stat().st_size,
            digest=sha256_digest(source.read_bytes()),
        )
        for relative, source, mode in sorted(files)
    ]
    provisional = RuntimeDistributionManifest.model_construct(
        schema_version="3.1",
        manifest_digest="sha256:" + "0" * 64,
        archive_digest=_sha256_file(destination),
        python_version=python_version,
        executable_path="bin/python3.12",
        dependency_path="lib/python3.12/site-packages",
        executable_digest=_sha256_file(executable),
        required_imports=sorted(required_imports),
        entries=entries,
    )
    manifest = RuntimeDistributionManifest.model_validate(
        provisional.model_copy(
            update={"manifest_digest": sha256_digest(canonical_json_bytes(provisional))}
        )
    )
    manifest_path = destination.with_suffix(".manifest.json")
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    manifest_path.chmod(0o444)
    return destination, manifest_path


def inventory_digest(paths: Iterable[Path]) -> str:
    """Return a stable digest helper for diagnostics and tests."""

    digest = hashlib.sha256()
    for path in sorted(paths):
        raw = path.read_bytes()
        encoded = path.as_posix().encode()
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return "sha256:" + digest.hexdigest()
