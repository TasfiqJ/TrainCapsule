"""Customer-local, case-isolated content-addressed evidence storage."""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .base import sha256_digest
from .models import (
    EvidenceArtifact,
    EvidenceIntegrity,
    PrivacyClass,
    safe_identifier,
)


class EvidenceStoreError(ValueError):
    pass


class LocalEvidenceStore:
    def __init__(
        self,
        root: Path,
        *,
        max_artifact_bytes: int = 16 * 1024 * 1024,
        max_case_artifacts: int = 256,
    ) -> None:
        if max_artifact_bytes < 1 or max_case_artifacts < 1:
            raise ValueError("evidence limits must be positive")
        if root.is_symlink():
            raise EvidenceStoreError("evidence root cannot be a symlink")
        self.root = root.resolve()
        self.max_artifact_bytes = max_artifact_bytes
        self.max_case_artifacts = max_case_artifacts
        if self.root.exists() and self.root.is_symlink():
            raise EvidenceStoreError("evidence root cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True)

    def _case_root(self, case_id: str) -> Path:
        safe_identifier(case_id)
        path = (self.root / "cases" / case_id).resolve()
        if not path.is_relative_to(self.root):
            raise EvidenceStoreError("case path escapes evidence root")
        return path

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise EvidenceStoreError("evidence destination contains a symlink")
        temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(temporary, flags, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError as error:
                raise EvidenceStoreError(
                    "evidence destination changed during atomic write"
                ) from error
            temporary.unlink()
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _read_regular(path: Path, *, limit: int) -> bytes:
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError as error:
            raise EvidenceStoreError("stored evidence is unavailable or unsafe") from error
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or details.st_size > limit:
                raise EvidenceStoreError("stored evidence violates type or size policy")
            payload = bytearray()
            while True:
                chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - len(payload)))
                if not chunk:
                    break
                payload.extend(chunk)
                if len(payload) > limit:
                    raise EvidenceStoreError("stored evidence exceeds configured policy")
            return bytes(payload)
        finally:
            os.close(descriptor)

    def put_bytes(
        self,
        *,
        case_id: str,
        payload: bytes,
        kind: str,
        source_adapter: str,
        source_version: str,
        captured_at: datetime,
        privacy_class: PrivacyClass = PrivacyClass.CONFIDENTIAL,
        provenance: dict[str, str] | None = None,
    ) -> EvidenceArtifact:
        if len(payload) > self.max_artifact_bytes:
            raise EvidenceStoreError("artifact exceeds configured size policy")
        case_root = self._case_root(case_id)
        metadata_root = case_root / "metadata"
        existing = list(metadata_root.glob("*.json")) if metadata_root.is_dir() else []
        digest = sha256_digest(payload)
        digest_hex = digest.removeprefix("sha256:")
        metadata_path = metadata_root / f"{digest_hex}.json"
        object_path = case_root / "objects/sha256" / digest_hex
        if not metadata_path.exists() and len(existing) >= self.max_case_artifacts:
            raise EvidenceStoreError("case artifact count exceeds configured policy")
        if object_path.exists():
            if (
                sha256_digest(self._read_regular(object_path, limit=self.max_artifact_bytes))
                != digest
            ):
                raise EvidenceStoreError("content-address collision or substitution detected")
        else:
            self._atomic_write(object_path, payload)
        artifact = EvidenceArtifact(
            artifact_id=digest,
            case_id=case_id,
            kind=kind,
            source_adapter=source_adapter,
            source_version=source_version,
            captured_at=captured_at,
            content_digest=digest,
            size_bytes=len(payload),
            privacy_class=privacy_class,
            customer_local_uri=f"cas://{case_id}/sha256/{digest_hex}",
            export_policy="LOCAL_ONLY",
            provenance=provenance or {},
            integrity_status=EvidenceIntegrity.VALID,
        )
        rendered = (
            json.dumps(
                artifact.model_dump(mode="json", by_alias=True),
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
        if (
            metadata_path.exists()
            and self._read_regular(metadata_path, limit=self.max_artifact_bytes) != rendered
        ):
            raise EvidenceStoreError("duplicate digest has conflicting metadata")
        if not metadata_path.exists():
            self._atomic_write(metadata_path, rendered)
        return artifact

    def put_file(
        self,
        *,
        source: Path,
        case_id: str,
        kind: str,
        source_adapter: str,
        source_version: str,
        captured_at: datetime,
        privacy_class: PrivacyClass = PrivacyClass.CONFIDENTIAL,
        provenance: dict[str, str] | None = None,
    ) -> EvidenceArtifact:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(source, flags)
        except OSError as error:
            raise EvidenceStoreError(
                "source evidence must be a non-symlink regular file"
            ) from error
        try:
            source_stat = os.fstat(descriptor)
            if not stat.S_ISREG(source_stat.st_mode):
                raise EvidenceStoreError("source evidence must be a regular file")
            if source_stat.st_size > self.max_artifact_bytes:
                raise EvidenceStoreError("artifact exceeds configured size policy")
            payload = bytearray()
            while True:
                chunk = os.read(
                    descriptor,
                    min(1024 * 1024, self.max_artifact_bytes + 1 - len(payload)),
                )
                if not chunk:
                    break
                payload.extend(chunk)
                if len(payload) > self.max_artifact_bytes:
                    raise EvidenceStoreError("artifact exceeds configured size policy")
        finally:
            os.close(descriptor)
        return self.put_bytes(
            case_id=case_id,
            payload=bytes(payload),
            kind=kind,
            source_adapter=source_adapter,
            source_version=source_version,
            captured_at=captured_at,
            privacy_class=privacy_class,
            provenance=provenance,
        )

    def get_bytes(self, *, case_id: str, artifact: EvidenceArtifact) -> bytes:
        if artifact.case_id != case_id:
            raise EvidenceStoreError("cross-case evidence access is forbidden")
        case_root = self._case_root(case_id)
        digest_hex = artifact.content_digest.removeprefix("sha256:")
        path = (case_root / "objects/sha256" / digest_hex).resolve()
        if not path.is_relative_to(case_root) or path.is_symlink():
            raise EvidenceStoreError("stored evidence path is unsafe")
        rendered = self._read_regular(path, limit=self.max_artifact_bytes)
        if sha256_digest(rendered) != artifact.content_digest:
            raise EvidenceStoreError("stored evidence digest mismatch")
        return rendered
