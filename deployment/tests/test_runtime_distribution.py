from __future__ import annotations

import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest
from traincapsule_verifier.canonical import canonical_json_bytes

from deployment.runtime_distribution import (
    RuntimeDistributionError,
    RuntimeDistributionManifest,
    build_runtime_distribution,
    extract_runtime_distribution,
    validate_extracted_runtime_distribution,
    validate_runtime_distribution,
)


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    python_root = tmp_path / "python"
    executable = python_root / "bin/python3.12"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"\x7fELF\x02\x01fixture-runtime")
    executable.chmod(0o755)
    stdlib = python_root / "lib/python3.12"
    stdlib.mkdir(parents=True)
    (stdlib / "os.py").write_text("name = 'fixture'\n")
    dependencies = tmp_path / "site-packages"
    (dependencies / "pydantic").mkdir(parents=True)
    (dependencies / "pydantic/__init__.py").write_text("VERSION = 'fixture'\n")
    sentinel = tmp_path / "build-hook-ran"
    (dependencies / "setup.py").write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('unsafe')\n"
    )
    return python_root, dependencies, sentinel


def _build(tmp_path: Path) -> tuple[Path, RuntimeDistributionManifest, Path]:
    python_root, dependencies, sentinel = _inputs(tmp_path)
    archive, manifest_path = build_runtime_distribution(
        tmp_path / "runtime.zip",
        python_root=python_root,
        dependency_root=dependencies,
        python_version="3.12.13",
        required_imports=("pydantic",),
    )
    manifest = RuntimeDistributionManifest.model_validate_json(
        manifest_path.read_bytes(), strict=True
    )
    return archive, manifest, sentinel


def test_exact_distribution_extracts_without_running_build_hooks(tmp_path: Path) -> None:
    archive, manifest, sentinel = _build(tmp_path)
    validate_runtime_distribution(archive, manifest)
    destination = tmp_path / "installed"
    extract_runtime_distribution(archive, manifest, destination)
    validate_extracted_runtime_distribution(destination, manifest)

    assert not sentinel.exists()
    assert (destination / "lib/python3.12/os.py").is_file()
    assert (destination / "lib/python3.12/site-packages/pydantic/__init__.py").is_file()
    assert stat.S_IMODE((destination / "bin/python3.12").stat().st_mode) == 0o555


def test_archive_tamper_extra_member_and_manifest_substitution_fail_closed(
    tmp_path: Path,
) -> None:
    archive, manifest, _ = _build(tmp_path)
    archive.chmod(0o600)
    with zipfile.ZipFile(archive, "a") as bundle:
        info = zipfile.ZipInfo("unexpected.py")
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o444) << 16
        bundle.writestr(info, b"unexpected")
    with pytest.raises(RuntimeDistributionError, match="archive digest differs"):
        validate_runtime_distribution(archive, manifest)

    raw = json.loads(canonical_json_bytes(manifest))
    entry = next(item for item in raw["entries"] if item["path"] != "bin/python3.12")
    entry["digest"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="manifest digest is invalid"):
        RuntimeDistributionManifest.model_validate(raw, strict=True)


def test_archive_links_and_input_hardlinks_are_rejected(tmp_path: Path) -> None:
    archive, manifest, _ = _build(tmp_path)
    archive.chmod(0o600)
    with zipfile.ZipFile(archive, "a") as bundle:
        info = zipfile.ZipInfo("lib/python3.12/site-packages/escape")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        bundle.writestr(info, b"../../escape")
    raw = archive.read_bytes()
    substituted = manifest.model_copy(
        update={"archive_digest": "sha256:" + hashlib.sha256(raw).hexdigest()}
    )
    zeroed = substituted.model_copy(update={"manifest_digest": "sha256:" + "0" * 64})
    substituted = substituted.model_copy(
        update={
            "manifest_digest": "sha256:"
            + hashlib.sha256(canonical_json_bytes(zeroed)).hexdigest()
        }
    )
    with pytest.raises(RuntimeDistributionError, match="unsafe member"):
        validate_runtime_distribution(archive, substituted)

    python_root, dependencies, _ = _inputs(tmp_path / "hardlink")
    original = dependencies / "pydantic/__init__.py"
    os.link(original, dependencies / "pydantic/alias.py")
    with pytest.raises(RuntimeDistributionError, match="hard link"):
        build_runtime_distribution(
            tmp_path / "hardlink.zip",
            python_root=python_root,
            dependency_root=dependencies,
            python_version="3.12.13",
            required_imports=("pydantic",),
        )


def test_extracted_tree_tamper_extra_file_and_symlink_are_rejected(tmp_path: Path) -> None:
    archive, manifest, _ = _build(tmp_path)
    destination = tmp_path / "installed"
    extract_runtime_distribution(archive, manifest, destination)
    target = destination / "lib/python3.12/os.py"
    target.chmod(0o644)
    target.write_text("tampered\n")
    with pytest.raises(RuntimeDistributionError, match="extracted member differs"):
        validate_extracted_runtime_distribution(destination, manifest)

    target.write_text("name = 'fixture'\n")
    target.chmod(0o444)
    extra = destination / "extra.py"
    destination.chmod(0o755)
    extra.write_text("extra\n")
    extra.chmod(0o444)
    destination.chmod(0o555)
    with pytest.raises(RuntimeDistributionError, match="inventory differs"):
        validate_extracted_runtime_distribution(destination, manifest)

    destination.chmod(0o755)
    extra.unlink()
    link = destination / "escape"
    link.symlink_to("/tmp")
    destination.chmod(0o555)
    with pytest.raises(RuntimeDistributionError, match="contains a link"):
        validate_extracted_runtime_distribution(destination, manifest)
    destination.chmod(0o700)
    link.unlink()
    for directory in (path for path in destination.rglob("*") if path.is_dir()):
        directory.chmod(0o700)
