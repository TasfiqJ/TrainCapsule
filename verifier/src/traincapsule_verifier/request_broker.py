"""Root-owned, copy-only bridge from controller requests to the issuer inbox."""

from __future__ import annotations

import os
import re
import stat
from typing import Literal

from pydantic import Field

from .canonical import canonical_json_bytes, sha256_digest
from .evaluator import verification_request_digest
from .filesystem import (
    TrustedPathError,
    TrustedRoot,
    atomic_write_new,
    open_trusted_root,
    read_bounded_file,
    sha256_file,
    strict_json_loads,
)
from .models import StrictModel, TrustedEvidenceManifest, VerificationRequest

_REQUEST_NAME = re.compile(r"^[A-Z0-9][A-Z0-9._:-]{2,127}\.request\.json$")
MAX_BUNDLE_FILES = 129
MAX_BUNDLE_BYTES = 100_000_000


class RequestSubmissionError(RuntimeError):
    """The request package is not safe to cross the authority boundary."""


class RequestSubmissionResult(StrictModel):
    state: Literal["SUBMITTED", "ALREADY_SUBMITTED"]
    request_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evidence_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    issuer_request_name: str
    issuer_evidence_name: str


def _bundle_paths(root: TrustedRoot) -> tuple[str, ...]:
    paths: list[str] = []
    total = 0
    for directory, directories, files, descriptor in os.fwalk(
        ".", topdown=True, follow_symlinks=False, dir_fd=root.descriptor
    ):
        if any(name in {"", ".", ".."} for name in [*directories, *files]):
            raise RequestSubmissionError("evidence bundle contains an invalid path")
        prefix = "" if directory == "." else f"{directory.removeprefix('./')}/"
        for name in files:
            relative = f"{prefix}{name}"
            metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISREG(metadata.st_mode):
                raise RequestSubmissionError("evidence bundle contains a non-regular file")
            if metadata.st_uid != root.expected_uid or metadata.st_nlink != 1:
                raise RequestSubmissionError("evidence bundle file ownership/link count is invalid")
            if metadata.st_mode & 0o022:
                raise RequestSubmissionError("evidence bundle file is group/world writable")
            total += metadata.st_size
            paths.append(relative)
        if len(paths) > MAX_BUNDLE_FILES or total > MAX_BUNDLE_BYTES:
            raise RequestSubmissionError("evidence bundle exceeds its file or byte bound")
    return tuple(sorted(paths))


def _open_evidence_root(outbox: TrustedRoot, name: str) -> TrustedRoot:
    candidate = outbox.path / name
    resolved = candidate.resolve(strict=True)
    if resolved.parent != outbox.path:
        raise RequestSubmissionError("evidence directory escaped the controller outbox")
    return open_trusted_root(resolved, expected_uid=outbox.expected_uid)


def _load_request(outbox: TrustedRoot, request_name: str) -> tuple[VerificationRequest, bytes]:
    if not _REQUEST_NAME.fullmatch(request_name):
        raise RequestSubmissionError("request filename is invalid")
    raw = read_bounded_file(outbox, request_name, maximum_bytes=5_000_000)
    strict_json_loads(raw)
    try:
        request = VerificationRequest.model_validate_json(raw, strict=True)
    except ValueError as exc:
        raise RequestSubmissionError("verification request contract is invalid") from exc
    if request_name != f"{request.request_id}.request.json":
        raise RequestSubmissionError("request filename does not match request identity")
    if raw != canonical_json_bytes(request):
        raise RequestSubmissionError("verification request bytes are not canonical")
    if request.request_digest != verification_request_digest(request):
        raise RequestSubmissionError("verification request digest is invalid")
    return request, raw


def _load_evidence(
    outbox: TrustedRoot, request: VerificationRequest
) -> tuple[TrustedEvidenceManifest, TrustedRoot, dict[str, bytes]]:
    evidence_name = f"{request.request_id}.evidence"
    root = _open_evidence_root(outbox, evidence_name)
    try:
        raw_manifest = read_bounded_file(root, "evidence.json", maximum_bytes=5_000_000)
        strict_json_loads(raw_manifest)
        evidence = TrustedEvidenceManifest.model_validate_json(raw_manifest, strict=True)
        if raw_manifest != canonical_json_bytes(evidence):
            raise RequestSubmissionError("trusted evidence manifest is not canonical")
        exact_fields = (
            "work_item_id",
            "milestone_id",
            "lane",
            "candidate_sha",
            "candidate_tree_sha",
            "base_sha",
            "source_generation_id",
            "source_generation_digest",
            "context_manifest_digest",
            "task_packet_digest",
            "candidate_manifest_digest",
            "checkpoint_digest",
        )
        if any(getattr(request, field) != getattr(evidence, field) for field in exact_fields):
            raise RequestSubmissionError("request and evidence exact identities differ")
        expected = {"evidence.json", *(binding.path for binding in evidence.raw_artifacts.values())}
        observed = set(_bundle_paths(root))
        if observed != expected:
            raise RequestSubmissionError("evidence bundle contains missing or undeclared files")
        payloads = {relative: read_bounded_file(root, relative) for relative in sorted(expected)}
        for binding in evidence.raw_artifacts.values():
            if sha256_file(root, binding.path) != binding.digest:
                raise RequestSubmissionError("raw evidence digest mismatch")
        return evidence, root, payloads
    except Exception:
        root.close()
        raise


def _ensure_service_directory(
    inbox: TrustedRoot, name: str, *, service_uid: int, service_gid: int
) -> tuple[TrustedRoot, bool]:
    created = False
    try:
        os.mkdir(name, mode=0o700, dir_fd=inbox.descriptor)
        os.chown(name, service_uid, service_gid, dir_fd=inbox.descriptor, follow_symlinks=False)
        os.fsync(inbox.descriptor)
        created = True
    except FileExistsError:
        pass
    target = (inbox.path / name).resolve(strict=True)
    if target.parent != inbox.path:
        raise RequestSubmissionError("issuer evidence directory escaped its inbox")
    return open_trusted_root(target, expected_uid=service_uid), created


class RootRequestBroker:
    """Validate and copy requests without access to keys, private oracles, or receipts."""

    def __init__(
        self,
        *,
        controller_outbox: TrustedRoot,
        service_inbox: TrustedRoot,
        journal_root: TrustedRoot,
        service_uid: int,
        service_gid: int,
    ) -> None:
        identities = {
            (controller_outbox.device, controller_outbox.inode),
            (service_inbox.device, service_inbox.inode),
            (journal_root.device, journal_root.inode),
        }
        if len(identities) != 3:
            raise RequestSubmissionError("request bridge roots must be distinct")
        self.controller_outbox = controller_outbox
        self.service_inbox = service_inbox
        self.journal_root = journal_root
        self.service_uid = service_uid
        self.service_gid = service_gid

    def submit(self, request_name: str) -> RequestSubmissionResult:
        try:
            request, request_bytes = _load_request(self.controller_outbox, request_name)
            evidence, source_root, payloads = _load_evidence(self.controller_outbox, request)
            try:
                del evidence
                evidence_name = f"{request.request_id}.evidence"
                destination, _ = _ensure_service_directory(
                    self.service_inbox,
                    evidence_name,
                    service_uid=self.service_uid,
                    service_gid=self.service_gid,
                )
                try:
                    for relative, payload in payloads.items():
                        target = destination.path / relative
                        if target.exists():
                            if read_bounded_file(destination, relative) != payload:
                                raise RequestSubmissionError(
                                    "issuer evidence identity has conflicting bytes"
                                )
                            continue
                        atomic_write_new(
                            destination,
                            relative,
                            payload,
                            owner_uid=self.service_uid,
                            owner_gid=self.service_gid,
                        )
                finally:
                    destination.close()
            finally:
                source_root.close()
            request_target = self.service_inbox.path / request_name
            if request_target.exists():
                if read_bounded_file(self.service_inbox, request_name) != request_bytes:
                    raise RequestSubmissionError("issuer request identity has conflicting bytes")
                state: Literal["SUBMITTED", "ALREADY_SUBMITTED"] = "ALREADY_SUBMITTED"
            else:
                atomic_write_new(
                    self.service_inbox,
                    request_name,
                    request_bytes,
                    owner_uid=self.service_uid,
                    owner_gid=self.service_gid,
                )
                state = "SUBMITTED"
            result = RequestSubmissionResult(
                state=state,
                request_id=request.request_id,
                request_digest=request.request_digest,
                evidence_digest=sha256_digest(payloads["evidence.json"]),
                issuer_request_name=request_name,
                issuer_evidence_name=evidence_name,
            )
            journal_name = f"{request.request_id}.submission.json"
            journal = canonical_json_bytes(result)
            if (self.journal_root.path / journal_name).exists():
                if read_bounded_file(self.journal_root, journal_name) != journal:
                    previous = RequestSubmissionResult.model_validate_json(
                        read_bounded_file(self.journal_root, journal_name), strict=True
                    )
                    if previous.model_copy(update={"state": state}) != result:
                        raise RequestSubmissionError("request submission journal conflicts")
            else:
                atomic_write_new(self.journal_root, journal_name, journal)
            return result
        except RequestSubmissionError:
            raise
        except (OSError, TrustedPathError, ValueError) as exc:
            raise RequestSubmissionError("root request broker rejected submission") from exc
