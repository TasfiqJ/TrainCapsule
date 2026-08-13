"""Root-only exact-main import into the credential-free controller Git anchor."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from pydantic import Field, model_validator

from .canonical import canonical_json_bytes, model_digest, sha256_digest
from .models import (
    ObservedMainReceipt,
    RulesetObservationReceipt,
    SourceGenerationId,
    V31Model,
)
from .public_crypto import load_public_key, verify_model_signature

ROOT = Path("/var/lib/traincapsule-verifier/anchor-updates")
CONFIG = Path("/etc/traincapsule-verifier")


class AnchorUpdateRequest(V31Model):
    schema_version: Literal["3.1"] = "3.1"
    request_id: str = Field(pattern=r"^ANCHOR:[A-Z0-9:_-]{8,120}$")
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    base_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    merged_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    merged_main_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_generation_id: SourceGenerationId
    source_generation_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    observed_main_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    ruleset_observation_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    publication_transaction_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    bundle_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def bounded(self) -> AnchorUpdateRequest:
        if self.base_sha == self.merged_main_sha:
            raise ValueError("anchor advancement must change exact main")
        lifetime = self.expires_at.astimezone(UTC) - self.created_at.astimezone(UTC)
        if lifetime.total_seconds() <= 0 or lifetime.total_seconds() > 1800:
            raise ValueError("anchor request lifetime is invalid")
        return self


class AnchorUpdatePolicy(V31Model):
    schema_version: Literal["3.1"] = "3.1"
    repository: Literal["TasfiqJ/TrainCapsule"]
    source_generation_id: SourceGenerationId
    source_generation_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    anchor_root: Literal["/var/lib/traincapsule-runtime/git"]
    transaction_root: Literal["/var/lib/traincapsule-verifier/anchor-update-journal"]


class AnchorUpdateJournal(V31Model):
    schema_version: Literal["3.1"] = "3.1"
    request_id: str
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    base_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    merged_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    merged_main_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    phase: Literal["PREPARED", "OBJECTS_IMPORTED", "COMMITTED"]
    updated_at: datetime


def _run_git(path: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(path), *arguments],
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
        raise ValueError("anchor Git validation failed")
    return result.stdout.strip()


def _write_journal(path: Path, journal: AnchorUpdateJournal) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, canonical_json_bytes(journal))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _canonical_mapping(raw: bytes, label: str) -> dict[str, object]:
    try:
        value: object = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid") from exc
    if not isinstance(value, dict) or canonical_json_bytes(cast(dict[str, object], value)) != raw:
        raise ValueError(f"{label} is not canonical")
    return cast(dict[str, object], value)


def _validate_staging(stage: Path, request: AnchorUpdateRequest) -> None:
    if (stage / "hooks").exists() or (stage / "objects/info/alternates").exists():
        raise ValueError("anchor bundle contains external Git behavior")
    if _run_git(stage, "remote"):
        raise ValueError("anchor bundle contains a remote")
    refs = _run_git(stage, "for-each-ref", "--format=%(refname)").splitlines()
    if refs != ["refs/heads/main"]:
        raise ValueError("anchor bundle contains an unexpected ref")
    _run_git(stage, "fsck", "--strict")
    all_objects = set(
        _run_git(
            stage,
            "cat-file",
            "--batch-all-objects",
            "--batch-check=%(objectname)",
        ).splitlines()
    )
    reachable_objects = {
        line.split(maxsplit=1)[0]
        for line in _run_git(stage, "rev-list", "--objects", "refs/heads/main").splitlines()
        if line
    }
    if not all_objects or all_objects != reachable_objects:
        raise ValueError("anchor bundle contains substituted or unreachable objects")
    main = _run_git(stage, "rev-parse", "refs/heads/main")
    tree = _run_git(stage, "rev-parse", f"{main}^{{tree}}")
    parents = _run_git(stage, "show", "-s", "--format=%P", main).split()
    if (
        main != request.merged_main_sha
        or tree != request.merged_main_tree_sha
        or parents != [request.base_sha]
    ):
        raise ValueError("anchor bundle main/tree/parent binding is invalid")


def _freeze_bundle(bundle_path: Path, transaction_root: Path) -> tuple[Path, str]:
    """Freeze a bounded regular bundle before Git ever reopens it by pathname."""

    transaction_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(transaction_root, 0o700)
    before = bundle_path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size <= 0
        or before.st_size > 536_870_912
    ):
        raise ValueError("anchor bundle is not a bounded single-link regular file")
    source = os.open(bundle_path, os.O_RDONLY | os.O_NOFOLLOW)
    temporary = transaction_root / f".bundle-{os.getpid()}.tmp"
    target = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    digest = hashlib.sha256()
    copied = 0
    try:
        opened = os.fstat(source)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise ValueError("anchor bundle identity changed before freeze")
        while chunk := os.read(source, 1024 * 1024):
            copied += len(chunk)
            if copied > 536_870_912:
                raise ValueError("anchor bundle exceeds the bounded size")
            digest.update(chunk)
            os.write(target, chunk)
        if copied != before.st_size:
            raise ValueError("anchor bundle changed while frozen")
        os.fsync(target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        os.close(source)
        os.close(target)
    after = bundle_path.lstat()
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ):
        temporary.unlink(missing_ok=True)
        raise ValueError("anchor bundle identity changed during freeze")
    digest_text = "sha256:" + digest.hexdigest()
    frozen = transaction_root / f"{digest.hexdigest()}.bundle"
    if frozen.exists():
        if hashlib.sha256(frozen.read_bytes()).hexdigest() != digest.hexdigest():
            temporary.unlink(missing_ok=True)
            raise ValueError("frozen anchor bundle digest collision")
        temporary.unlink()
    else:
        os.replace(temporary, frozen)
        directory = os.open(transaction_root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    return frozen, digest_text


def advance_anchor(
    *,
    request_raw: bytes,
    observed_main_raw: bytes,
    ruleset_raw: bytes,
    publication_transaction_raw: bytes,
    bundle_path: Path,
    policy: AnchorUpdatePolicy,
    selector_public_key_raw: bytes,
    ruleset_public_key_raw: bytes,
    now: datetime | None = None,
    anchor_root: Path | None = None,
    transaction_root: Path | None = None,
    failpoint: Callable[[str], None] | None = None,
) -> AnchorUpdateJournal:
    """Verify one frozen import and atomically advance only ``refs/heads/main``."""

    observed_now = now or datetime.now(UTC)
    request = AnchorUpdateRequest.model_validate_json(request_raw, strict=True)
    observed = ObservedMainReceipt.model_validate_json(observed_main_raw, strict=True)
    ruleset = RulesetObservationReceipt.model_validate_json(ruleset_raw, strict=True)
    if canonical_json_bytes(request) != request_raw:
        raise ValueError("anchor request is not canonical")
    if (
        canonical_json_bytes(observed) != observed_main_raw
        or canonical_json_bytes(ruleset) != ruleset_raw
    ):
        raise ValueError("anchor authority receipt is not canonical")
    verify_model_signature(observed, load_public_key(selector_public_key_raw))
    verify_model_signature(ruleset, load_public_key(ruleset_public_key_raw))
    transaction = _canonical_mapping(publication_transaction_raw, "publication transaction")
    journals = (transaction_root or Path(policy.transaction_root)).resolve()
    frozen_bundle, bundle_raw_digest = _freeze_bundle(bundle_path, journals / "bundles")
    if (
        request.repository != policy.repository
        or request.source_generation_id != policy.source_generation_id
        or request.source_generation_digest != policy.source_generation_digest
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
        or request.bundle_digest != bundle_raw_digest
        or request.publication_transaction_digest != sha256_digest(publication_transaction_raw)
        or transaction.get("phase") != "MERGED"
        or transaction.get("baseSha") != request.base_sha
        or transaction.get("mergedMainSha") != request.merged_main_sha
    ):
        raise ValueError("anchor update evidence is stale or inconsistently bound")
    anchor = (anchor_root or Path(policy.anchor_root)).resolve(strict=True)
    request_digest = sha256_digest(request_raw)
    journal_path = journals / f"{request.request_id.replace(':', '_')}.json"
    if journal_path.is_file():
        journal = AnchorUpdateJournal.model_validate_json(journal_path.read_bytes(), strict=True)
        if journal.request_digest != request_digest:
            raise ValueError("anchor request identity conflicts with its journal")
        if journal.phase == "COMMITTED":
            if _run_git(anchor, "rev-parse", "refs/heads/main") != request.merged_main_sha:
                raise ValueError("committed anchor journal no longer matches main")
            return journal
    lock = os.open(anchor.parent / "git-anchor.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = _run_git(anchor, "rev-parse", "refs/heads/main")
        if current not in {request.base_sha, request.merged_main_sha}:
            raise ValueError("anchor main moved outside the signed transaction")
        prepared = AnchorUpdateJournal(
            request_id=request.request_id,
            request_digest=request_digest,
            base_sha=request.base_sha,
            merged_main_sha=request.merged_main_sha,
            merged_main_tree_sha=request.merged_main_tree_sha,
            phase="PREPARED",
            updated_at=observed_now,
        )
        _write_journal(journal_path, prepared)
        if failpoint is not None:
            failpoint("PREPARED")
        if current == request.base_sha:
            with tempfile.TemporaryDirectory(prefix="anchor-import-", dir=journals) as raw:
                stage = Path(raw) / "stage.git"
                clone = subprocess.run(
                    ["/usr/bin/git", "clone", "--bare", str(frozen_bundle), str(stage)],
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
                if clone.returncode != 0:
                    raise ValueError("anchor bundle cannot be materialized")
                _run_git(stage, "remote", "remove", "origin")
                shutil.rmtree(stage / "hooks")
                _validate_staging(stage, request)
                _run_git(anchor, "fetch", "--no-tags", str(stage), "refs/heads/main")
                imported = prepared.model_copy(update={"phase": "OBJECTS_IMPORTED"})
                _write_journal(journal_path, imported)
                if failpoint is not None:
                    failpoint("OBJECTS_IMPORTED")
                if (
                    _run_git(anchor, "rev-parse", f"{request.merged_main_sha}^{{tree}}")
                    != request.merged_main_tree_sha
                ):
                    raise ValueError("imported anchor object was substituted")
                _run_git(
                    anchor,
                    "update-ref",
                    "refs/heads/main",
                    request.merged_main_sha,
                    request.base_sha,
                )
                if failpoint is not None:
                    failpoint("REF_ADVANCED")
        if (
            _run_git(anchor, "rev-parse", "refs/heads/main") != request.merged_main_sha
            or _run_git(anchor, "rev-parse", f"{request.merged_main_sha}^{{tree}}")
            != request.merged_main_tree_sha
            or _run_git(anchor, "remote")
            or (anchor / "hooks").exists()
            or (anchor / "objects/info/alternates").exists()
        ):
            raise ValueError("advanced anchor failed final attestation")
        committed = prepared.model_copy(update={"phase": "COMMITTED", "updated_at": observed_now})
        _write_journal(journal_path, committed)
        return committed
    finally:
        os.close(lock)


def _trusted_file(path: Path, *, maximum_bytes: int) -> bytes:
    observed = path.lstat()
    if (
        path.is_symlink()
        or not path.is_file()
        or observed.st_uid != 0
        or observed.st_nlink != 1
        or observed.st_mode & 0o022
        or observed.st_size > maximum_bytes
    ):
        raise ValueError("anchor update input is not root-owned and bounded")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            observed.st_dev,
            observed.st_ino,
            observed.st_size,
        ):
            raise ValueError("anchor update input identity changed")
        raw = b""
        while chunk := os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - len(raw))):
            raw += chunk
            if len(raw) > maximum_bytes:
                raise ValueError("anchor update input exceeds its bound")
        return raw
    finally:
        os.close(descriptor)


def main() -> int:
    if sys.argv[1:] != ["process-inbox"]:
        print("usage: traincapsule-verifier-git-anchor-updater process-inbox", file=sys.stderr)
        return 2
    try:
        if os.geteuid() != 0:
            raise ValueError("anchor updater requires root")
        policy_raw = _trusted_file(CONFIG / "git-anchor-policy.json", maximum_bytes=32_768)
        policy = AnchorUpdatePolicy.model_validate_json(policy_raw, strict=True)
        if canonical_json_bytes(policy) != policy_raw:
            raise ValueError("anchor update policy is not canonical")
        selector_key = _trusted_file(
            CONFIG / "anchor-observer-public-key.pem", maximum_bytes=8_192
        )
        ruleset_key = _trusted_file(CONFIG / "ruleset-public-key.pem", maximum_bytes=8_192)
        root_observed = ROOT.lstat()
        if ROOT.is_symlink() or not ROOT.is_dir() or root_observed.st_uid != 0:
            raise ValueError("anchor update inbox is not trusted")
        for request_path in sorted(ROOT.glob("ANCHOR_*.request.json")):
            stem = request_path.name.removesuffix(".request.json")
            advance_anchor(
                request_raw=_trusted_file(request_path, maximum_bytes=64_000),
                observed_main_raw=_trusted_file(
                    ROOT / f"{stem}.observed.json", maximum_bytes=1_000_000
                ),
                ruleset_raw=_trusted_file(
                    ROOT / f"{stem}.ruleset.json", maximum_bytes=1_000_000
                ),
                publication_transaction_raw=_trusted_file(
                    ROOT / f"{stem}.publication.json", maximum_bytes=1_000_000
                ),
                bundle_path=ROOT / f"{stem}.bundle",
                policy=policy,
                selector_public_key_raw=selector_key,
                ruleset_public_key_raw=ruleset_key,
            )
        return 0
    except (OSError, ValueError):
        print("Git anchor updater rejected work", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
