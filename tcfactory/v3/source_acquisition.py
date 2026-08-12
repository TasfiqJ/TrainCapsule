"""Controlled, attributable source acquisition for V3.1 research lanes.

The controller, not an agent backend, owns this network boundary.  Plans must name every
HTTPS source up front, hosts are exact-allowlisted, redirects and IP literals are rejected,
and every returned byte is persisted before it can support a research finding.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import socket
import ssl
import stat
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Protocol
from urllib.parse import SplitResult, urlsplit

from pydantic import AwareDatetime, ConfigDict, Field, field_validator, model_validator

from tcfactory.v3.base import DIGEST_PATTERN, SHA_PATTERN, to_camel
from tcfactory.v3.contracts_v31 import V31Model
from tcfactory.v3.enums import Lane


class SourceAcquisitionError(RuntimeError):
    """Raised when controlled acquisition cannot preserve its security contract."""


class ResearchVerdict(StrEnum):
    CLEAR = "CLEAR"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class SourceClass(StrEnum):
    OFFICIAL_REGISTRY = "OFFICIAL_REGISTRY"
    OFFICIAL_DOCUMENTATION = "OFFICIAL_DOCUMENTATION"
    STANDARDS_BODY = "STANDARDS_BODY"
    COMPANY_PRIMARY = "COMPANY_PRIMARY"
    PUBLIC_REPOSITORY = "PUBLIC_REPOSITORY"


class ControlKind(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    ERROR = "ERROR"


class ResearchModel(V31Model):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        strict=True,
    )


class SourceAcquisitionPolicy(ResearchModel):
    policy_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    allowed_hostnames: list[str] = Field(min_length=1, max_length=128)
    timeout_seconds: float = Field(gt=0, le=60)
    max_response_bytes: int = Field(ge=1, le=16 * 1024 * 1024)
    max_sources_per_plan: int = Field(ge=1, le=64)
    allowed_content_types: list[str] = Field(min_length=1, max_length=32)
    user_agent: str = Field(min_length=1, max_length=160)

    @field_validator("allowed_hostnames")
    @classmethod
    def validate_hosts(cls, values: list[str]) -> list[str]:
        normalized = [_normalize_hostname(value) for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError("allowed hostnames must be unique")
        return normalized

    @field_validator("allowed_content_types")
    @classmethod
    def validate_content_types(cls, values: list[str]) -> list[str]:
        normalized = [value.lower().split(";", 1)[0].strip() for value in values]
        if any("/" not in value or "*" in value for value in normalized):
            raise ValueError("content types must be exact media types")
        if len(set(normalized)) != len(normalized):
            raise ValueError("allowed content types must be unique")
        return normalized


class ResearchSource(ResearchModel):
    source_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    url: str = Field(min_length=1, max_length=2048)
    source_class: SourceClass
    claim_ids: list[str] = Field(min_length=1, max_length=64)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        _validated_https_url(value)
        return value

    @field_validator("claim_ids")
    @classmethod
    def validate_claim_ids(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("source claim IDs must be unique")
        return values


class ResearchClaim(ResearchModel):
    claim_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    question: str = Field(min_length=1, max_length=2000)


class ResearchQueryPlan(ResearchModel):
    plan_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    lane: Lane
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    policy_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    claims: list[ResearchClaim] = Field(min_length=1, max_length=128)
    sources: list[ResearchSource] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_plan(self) -> ResearchQueryPlan:
        if self.lane not in {Lane.MARKET, Lane.COMPETITOR}:
            raise ValueError("controlled source acquisition is limited to research lanes")
        claim_ids = [claim.claim_id for claim in self.claims]
        source_ids = [source.source_id for source in self.sources]
        if len(set(claim_ids)) != len(claim_ids):
            raise ValueError("claim IDs must be unique")
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("source IDs must be unique")
        unknown = {
            claim_id
            for source in self.sources
            for claim_id in source.claim_ids
            if claim_id not in set(claim_ids)
        }
        if unknown:
            raise ValueError(f"sources reference unknown claims: {sorted(unknown)}")
        return self


class SourceArtifact(ResearchModel):
    source_id: str
    source_class: SourceClass
    requested_url: str
    final_url: str
    observed_at: AwareDatetime
    status_code: int = Field(ge=100, le=599)
    content_type: str
    content_length: int = Field(ge=0)
    content_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    headers_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    artifact_path: str = Field(pattern=r"^[^/\\]+$")
    claim_ids: list[str] = Field(min_length=1, max_length=64)


class ResearchControl(ResearchModel):
    kind: ControlKind
    artifact_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    expected_verdict: ResearchVerdict
    observed_verdict: ResearchVerdict

    @model_validator(mode="after")
    def validate_control(self) -> ResearchControl:
        if self.expected_verdict is not self.observed_verdict:
            raise ValueError("research control did not produce its preregistered verdict")
        return self


class ResearchFinding(ResearchModel):
    claim_id: str
    verdict: ResearchVerdict
    statement: str = Field(min_length=1, max_length=4000)
    source_artifact_digests: list[str] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def validate_finding(self) -> ResearchFinding:
        if len(set(self.source_artifact_digests)) != len(self.source_artifact_digests):
            raise ValueError("finding source digests must be unique")
        if self.verdict is not ResearchVerdict.UNKNOWN and not self.source_artifact_digests:
            raise ValueError("CLEAR and CONFLICT findings require raw source evidence")
        return self


class ResearchReport(ResearchModel):
    report_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    plan_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    overall_verdict: ResearchVerdict
    artifacts: list[SourceArtifact] = Field(min_length=1, max_length=64)
    controls: list[ResearchControl] = Field(min_length=3, max_length=16)
    findings: list[ResearchFinding] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_report(self) -> ResearchReport:
        control_kinds = [control.kind for control in self.controls]
        if set(control_kinds) != set(ControlKind) or len(control_kinds) != 3:
            raise ValueError("exactly one positive, negative, and error control is required")
        artifact_digests = {artifact.content_digest for artifact in self.artifacts}
        if any(
            digest not in artifact_digests
            for finding in self.findings
            for digest in finding.source_artifact_digests
        ):
            raise ValueError("finding references an unknown source artifact")
        expected = _overall_verdict(self.findings)
        if self.overall_verdict is not expected:
            raise ValueError("overall research verdict does not match finding verdicts")
        return self


SOURCE_ACQUISITION_CONTRACTS: dict[str, type[ResearchModel]] = {
    "source-acquisition-policy": SourceAcquisitionPolicy,
    "research-source": ResearchSource,
    "research-claim": ResearchClaim,
    "research-query-plan": ResearchQueryPlan,
    "source-artifact": SourceArtifact,
    "research-control": ResearchControl,
    "research-finding": ResearchFinding,
    "research-report": ResearchReport,
}


@dataclass(frozen=True)
class FetchedResponse:
    final_url: str
    status_code: int
    content_type: str
    headers: tuple[tuple[str, str], ...]
    body: bytes


class SourceTransport(Protocol):
    def fetch(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_response_bytes: int,
        user_agent: str,
    ) -> FetchedResponse: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        raise SourceAcquisitionError(f"redirects are forbidden ({code})")


class ControlledHttpsTransport:
    """Small HTTPS-only transport with no redirects or decompression."""

    def fetch(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_response_bytes: int,
        user_agent: str,
    ) -> FetchedResponse:
        parts = _validated_https_url(url)
        _assert_public_resolution(parts.hostname or "")
        context = ssl.create_default_context()
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context), _NoRedirect()
        )
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"Accept-Encoding": "identity", "User-Agent": user_agent},
        )
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                final_url = response.geturl()
                if final_url != url:
                    raise SourceAcquisitionError("transport changed the preregistered URL")
                status = int(response.status)
                if status != 200:
                    raise SourceAcquisitionError(f"source returned HTTP {status}")
                declared = response.headers.get("Content-Length")
                if declared is not None and int(declared) > max_response_bytes:
                    raise SourceAcquisitionError("declared response exceeds the byte limit")
                body = response.read(max_response_bytes + 1)
                if len(body) > max_response_bytes:
                    raise SourceAcquisitionError("response exceeds the byte limit")
                return FetchedResponse(
                    final_url=final_url,
                    status_code=status,
                    content_type=response.headers.get_content_type().lower(),
                    headers=tuple(
                        sorted((key.lower(), value) for key, value in response.headers.items())
                    ),
                    body=body,
                )
        except SourceAcquisitionError:
            raise
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise SourceAcquisitionError(f"HTTPS acquisition failed: {type(exc).__name__}") from exc


class ControlledSourceAcquirer:
    def __init__(
        self,
        *,
        policy: SourceAcquisitionPolicy,
        artifact_root: Path,
        transport: SourceTransport | None = None,
    ) -> None:
        self.policy = policy
        self.artifact_root = artifact_root
        self.transport = transport or ControlledHttpsTransport()

    def acquire(self, plan: ResearchQueryPlan) -> list[SourceArtifact]:
        if plan.policy_id != self.policy.policy_id:
            raise SourceAcquisitionError("query plan policy does not match active policy")
        if len(plan.sources) > self.policy.max_sources_per_plan:
            raise SourceAcquisitionError("query plan exceeds the source limit")
        root_fd = _open_artifact_root(self.artifact_root)
        try:
            artifacts: list[SourceArtifact] = []
            for source in plan.sources:
                parts = _validated_https_url(source.url)
                hostname = _normalize_hostname(parts.hostname or "")
                if hostname not in set(self.policy.allowed_hostnames):
                    raise SourceAcquisitionError(f"source hostname is not allowlisted: {hostname}")
                response = self.transport.fetch(
                    url=source.url,
                    timeout_seconds=self.policy.timeout_seconds,
                    max_response_bytes=self.policy.max_response_bytes,
                    user_agent=self.policy.user_agent,
                )
                if response.final_url != source.url:
                    raise SourceAcquisitionError("response URL does not match the query plan")
                if response.status_code != 200:
                    raise SourceAcquisitionError(
                        f"source returned unexpected HTTP {response.status_code}"
                    )
                if len(response.body) > self.policy.max_response_bytes:
                    raise SourceAcquisitionError("response exceeds the byte limit")
                content_type = response.content_type.lower().split(";", 1)[0]
                if content_type not in set(self.policy.allowed_content_types):
                    raise SourceAcquisitionError(f"content type is not allowlisted: {content_type}")
                content_digest = f"sha256:{hashlib.sha256(response.body).hexdigest()}"
                header_bytes = "\n".join(
                    f"{key}:{value}" for key, value in response.headers
                ).encode()
                headers_digest = f"sha256:{hashlib.sha256(header_bytes).hexdigest()}"
                artifact_name = f"{content_digest.removeprefix('sha256:')}.raw"
                _publish_raw(root_fd, artifact_name, response.body)
                artifacts.append(
                    SourceArtifact(
                        schema_version="3.1",
                        source_id=source.source_id,
                        source_class=source.source_class,
                        requested_url=source.url,
                        final_url=response.final_url,
                        observed_at=datetime.now(UTC),
                        status_code=response.status_code,
                        content_type=content_type,
                        content_length=len(response.body),
                        content_digest=content_digest,
                        headers_digest=headers_digest,
                        artifact_path=artifact_name,
                        claim_ids=source.claim_ids,
                    )
                )
            return artifacts
        finally:
            os.close(root_fd)


def compile_research_report(
    *,
    report_id: str,
    plan: ResearchQueryPlan,
    artifact_root: Path,
    artifacts: list[SourceArtifact],
    controls: list[ResearchControl],
    findings: list[ResearchFinding],
) -> ResearchReport:
    """Bind a strict finding set to its preregistered plan and acquired raw bytes."""

    artifact_by_source = {artifact.source_id: artifact for artifact in artifacts}
    if set(artifact_by_source) != {source.source_id for source in plan.sources}:
        raise SourceAcquisitionError("artifacts do not exactly cover the query plan sources")
    root_fd = _open_artifact_root(artifact_root)
    try:
        for artifact in artifacts:
            raw = _read_raw(root_fd, artifact.artifact_path, self_limit=16 * 1024 * 1024)
            observed_digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
            if observed_digest != artifact.content_digest:
                raise SourceAcquisitionError("source artifact digest does not match raw bytes")
            if len(raw) != artifact.content_length:
                raise SourceAcquisitionError("source artifact length does not match raw bytes")
    finally:
        os.close(root_fd)
    claim_ids = {claim.claim_id for claim in plan.claims}
    findings_by_claim = {finding.claim_id: finding for finding in findings}
    if set(findings_by_claim) != claim_ids or len(findings_by_claim) != len(findings):
        raise SourceAcquisitionError("findings must cover each preregistered claim exactly once")
    allowed_by_claim: dict[str, set[str]] = {claim_id: set() for claim_id in claim_ids}
    for artifact in artifacts:
        for claim_id in artifact.claim_ids:
            allowed_by_claim[claim_id].add(artifact.content_digest)
    for finding in findings:
        if not set(finding.source_artifact_digests).issubset(allowed_by_claim[finding.claim_id]):
            raise SourceAcquisitionError("finding cites evidence not preregistered for its claim")
    serialized_plan = plan.model_dump_json(by_alias=True).encode()
    plan_digest = f"sha256:{hashlib.sha256(serialized_plan).hexdigest()}"
    return ResearchReport(
        schema_version="3.1",
        report_id=report_id,
        plan_digest=plan_digest,
        work_item_id=plan.work_item_id,
        candidate_sha=plan.candidate_sha,
        overall_verdict=_overall_verdict(findings),
        artifacts=artifacts,
        controls=controls,
        findings=findings,
    )


def _overall_verdict(findings: list[ResearchFinding]) -> ResearchVerdict:
    if any(finding.verdict is ResearchVerdict.CONFLICT for finding in findings):
        return ResearchVerdict.CONFLICT
    if any(finding.verdict is ResearchVerdict.UNKNOWN for finding in findings):
        return ResearchVerdict.UNKNOWN
    return ResearchVerdict.CLEAR


def _normalize_hostname(value: str) -> str:
    raw = value.strip().rstrip(".").lower()
    if not raw or raw == "localhost":
        raise ValueError("hostname is not permitted")
    try:
        ipaddress.ip_address(raw)
    except ValueError:
        try:
            normalized = raw.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("hostname is not valid IDNA") from exc
        if not normalized or any(not label for label in normalized.split(".")):
            raise ValueError("hostname is invalid") from None
        return normalized
    raise ValueError("IP-literal sources are forbidden")


def _validated_https_url(value: str) -> SplitResult:
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise ValueError("source URL is invalid") from exc
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("source URL must use HTTPS")
    if parts.username or parts.password or parts.fragment:
        raise ValueError("source URL cannot contain credentials or a fragment")
    if port not in {None, 443}:
        raise ValueError("source URL must use the default HTTPS port")
    _normalize_hostname(parts.hostname)
    return parts


def _assert_public_resolution(hostname: str) -> None:
    try:
        addresses = {
            item[4][0] for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise SourceAcquisitionError("source hostname could not be resolved") from exc
    if not addresses:
        raise SourceAcquisitionError("source hostname returned no addresses")
    if any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise SourceAcquisitionError("source hostname resolved to a non-public address")


def _open_artifact_root(path: Path) -> int:
    if not path.is_absolute():
        raise SourceAcquisitionError("artifact root must be absolute")
    try:
        return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise SourceAcquisitionError("artifact root must be a real pre-created directory") from exc


def _publish_raw(root_fd: int, name: str, body: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    try:
        fd = os.open(name, flags, 0o600, dir_fd=root_fd)
    except FileExistsError:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            existing = b""
            while chunk := os.read(fd, 1024 * 1024):
                existing += chunk
        finally:
            os.close(fd)
        if existing != body:
            raise SourceAcquisitionError("content-addressed source artifact collision") from None
        return
    except OSError as exc:
        raise SourceAcquisitionError("could not publish source artifact") from exc
    try:
        view = memoryview(body)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(root_fd)


def _read_raw(root_fd: int, name: str, *, self_limit: int) -> bytes:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
    except OSError as exc:
        raise SourceAcquisitionError("source artifact is missing or unsafe") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > self_limit:
            raise SourceAcquisitionError("source artifact must be a bounded regular file")
        chunks: list[bytes] = []
        remaining = self_limit + 1
        while remaining > 0:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > self_limit:
            raise SourceAcquisitionError("source artifact exceeds the read limit")
        return raw
    finally:
        os.close(fd)
