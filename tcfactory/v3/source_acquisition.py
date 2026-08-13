"""Controlled, attributable source acquisition for V3.1 research lanes.

The controller, not an agent backend, owns this network boundary.  Plans must name every
HTTPS source up front, hosts are exact-allowlisted, redirects are peer-bound and revalidated,
IP literals are rejected, and every returned byte is persisted before it can support a finding.
"""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import stat
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from time import monotonic
from typing import ClassVar, Literal, Protocol, cast
from urllib.parse import SplitResult, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from pydantic import (
    AwareDatetime,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

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


class ParserLimits(ResearchModel):
    maximum_depth: int = Field(default=24, ge=1, le=64)
    maximum_nodes: int = Field(default=10_000, ge=1, le=100_000)
    maximum_string_bytes: int = Field(default=1_048_576, ge=1, le=4_194_304)
    maximum_claim_results: int = Field(default=128, ge=1, le=512)


class SourceAcquisitionPolicy(ResearchModel):
    policy_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    allowed_hostnames: list[str] = Field(min_length=1, max_length=128)
    timeout_seconds: float = Field(gt=0, le=60)
    max_response_bytes: int = Field(ge=1, le=16 * 1024 * 1024)
    max_sources_per_plan: int = Field(ge=1, le=64)
    allowed_content_types: list[str] = Field(min_length=1, max_length=32)
    user_agent: str = Field(min_length=1, max_length=160)
    allowed_methods: list[Literal["GET"]] = Field(
        default_factory=lambda: ["GET"], min_length=1, max_length=1
    )
    max_redirects: int = Field(default=3, ge=0, le=5)
    maximum_freshness_seconds: int = Field(default=86_400, ge=60, le=7_776_000)

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


class ResearchSourceRequest(ResearchModel):
    url: str = Field(min_length=1, max_length=2048)
    method: Literal["GET"] = "GET"
    query: str = Field(min_length=1, max_length=2000)
    control_query: str = Field(min_length=1, max_length=2000)
    parser_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    parser_version: str = Field(min_length=1, max_length=64)
    freshness_policy: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    freshness_seconds: int = Field(ge=60, le=7_776_000)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        _validated_https_url(value)
        return value


class ResearchSource(ResearchSourceRequest):
    source_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    source_class: SourceClass
    claim_ids: list[str] = Field(min_length=1, max_length=64)

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
    parser_limits: ParserLimits = Field(default_factory=lambda: ParserLimits(schema_version="3.1"))

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


class ReceiptAuthority(Protocol):
    issuer_id: str
    key_id: str
    signature_algorithm: str

    def sign(self, payload: bytes) -> str: ...

    def verify(
        self,
        payload: bytes,
        *,
        signature: str,
        issuer_id: str,
        key_id: str,
        signature_algorithm: str,
    ) -> bool: ...


class SourceHopReceipt(ResearchModel):
    url: str
    url_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    resolved_public_addresses: list[str] = Field(min_length=1, max_length=32)
    peer_address: str

    @model_validator(mode="after")
    def validate_hop(self) -> SourceHopReceipt:
        _validated_https_url(self.url)
        addresses = _validate_public_addresses(self.resolved_public_addresses)
        peer = _canonical_ip(self.peer_address)
        _validate_public_addresses([peer])
        if peer not in addresses:
            raise ValueError("source hop peer is not one of its resolved addresses")
        return self


class SourceRetrievalReceipt(ResearchModel):
    """Controller attestation binding one bounded retrieval to its raw CAS bytes."""

    receipt_id: str = Field(pattern=r"^SRCREC-[A-F0-9]{24}$")
    source_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    policy_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    plan_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    method: Literal["GET"]
    requested_url: str
    requested_url_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    final_url: str
    final_url_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    redirect_chain: list[str] = Field(default_factory=list, max_length=5)
    redirect_chain_digests: list[str] = Field(default_factory=list, max_length=5)
    hop_receipts: list[SourceHopReceipt] = Field(min_length=1, max_length=6)
    retrieved_at: AwareDatetime
    status_code: Literal[200]
    response_headers: dict[str, str] = Field(max_length=16)
    content_type: str
    content_length: int = Field(ge=0, le=16 * 1024 * 1024)
    source_class: SourceClass
    query: str
    control_query: str
    content_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    parser_id: str
    parser_version: str
    freshness_policy: str
    fresh_until: AwareDatetime
    authority_effect: Literal["ADVISORY_ONLY_NEVER_NORMATIVE"] = "ADVISORY_ONLY_NEVER_NORMATIVE"
    issuer_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    issuer_key_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    signature_algorithm: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    signature: str = Field(min_length=32, max_length=2048)

    @model_validator(mode="after")
    def validate_receipt_shape(self) -> SourceRetrievalReceipt:
        if self.fresh_until <= self.retrieved_at:
            raise ValueError("freshness receipt must expire after retrieval")
        for url in [self.requested_url, *self.redirect_chain, self.final_url]:
            _validated_https_url(url)
        if len(self.redirect_chain) != len(self.redirect_chain_digests):
            raise ValueError("redirect URL and digest counts differ")
        if len(self.hop_receipts) != len(self.redirect_chain) + 1:
            raise ValueError("source receipt requires one peer-bound receipt per hop")
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
    retrieval_receipt: SourceRetrievalReceipt


class ResearchControl(ResearchModel):
    kind: ControlKind
    artifact_digest: str = Field(
        default="sha256:" + "0" * 64, pattern=DIGEST_PATTERN.pattern
    )
    raw_artifact_roster_digest: str = Field(
        default="sha256:" + "0" * 64, pattern=DIGEST_PATTERN.pattern
    )
    oracle_executable_digest: str = Field(
        default="sha256:" + "0" * 64, pattern=DIGEST_PATTERN.pattern
    )
    oracle_result_digest: str = Field(
        default="sha256:" + "0" * 64, pattern=DIGEST_PATTERN.pattern
    )
    expected_verdict: ResearchVerdict
    observed_verdict: ResearchVerdict

    @model_validator(mode="after")
    def validate_control(self) -> ResearchControl:
        if self.expected_verdict is not self.observed_verdict:
            raise ValueError("research control did not produce its preregistered verdict")
        return self


class ResearchControlOracle(Protocol):
    def evaluate(
        self,
        *,
        plan: ResearchQueryPlan,
        artifact_root: Path,
        artifacts: list[SourceArtifact],
        expected_controls: list[ResearchControl],
        artifact_root_opener: Callable[[], int] | None,
    ) -> list[ResearchControl]: ...


class InProcessResearchControlOracle:
    """Test-only deterministic control evaluator over already bound raw artifacts."""

    def evaluate(
        self,
        *,
        plan: ResearchQueryPlan,
        artifact_root: Path,
        artifacts: list[SourceArtifact],
        expected_controls: list[ResearchControl],
        artifact_root_opener: Callable[[], int] | None,
    ) -> list[ResearchControl]:
        del plan
        root_fd = _open_bound_artifact_root(artifact_root, artifact_root_opener)
        try:
            digests = {
                "sha256:" + hashlib.sha256(
                    _read_raw(root_fd, artifact.artifact_path, self_limit=16 * 1024 * 1024)
                ).hexdigest()
                for artifact in artifacts
            }
        finally:
            os.close(root_fd)
        if not digests:
            raise SourceAcquisitionError("research control oracle received no raw evidence")
        roster_digest = research_artifact_roster_digest(artifacts)
        oracle_digest = f"sha256:{hashlib.sha256(b'IN_PROCESS_TEST_ORACLE_V1').hexdigest()}"
        draft = [
            ResearchControl(
                schema_version="3.1",
                kind=control.kind,
                artifact_digest=roster_digest,
                raw_artifact_roster_digest=roster_digest,
                oracle_executable_digest=oracle_digest,
                oracle_result_digest="sha256:" + "0" * 64,
                expected_verdict=control.expected_verdict,
                observed_verdict=control.expected_verdict,
            )
            for control in expected_controls
        ]
        result_digest = research_control_result_digest(draft)
        return [
            control.model_copy(update={"oracle_result_digest": result_digest})
            for control in draft
        ]


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


class SourceParsingError(RuntimeError):
    """Raised when trusted parsing cannot produce bounded typed claim evidence."""


class ParsedClaimResult(ResearchModel):
    claim_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    verdict: ResearchVerdict
    statement: str = Field(min_length=1, max_length=4000)


class ParsedSourceResult(ResearchModel):
    parser_id: str
    parser_version: str
    content_type: str
    claim_results: list[ParsedClaimResult] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_claim_results(self) -> ParsedSourceResult:
        claim_ids = [result.claim_id for result in self.claim_results]
        if len(set(claim_ids)) != len(claim_ids):
            raise ValueError("parsed claim result IDs must be unique")
        return self


class SourceParser(Protocol):
    parser_id: str
    parser_version: str
    allowed_content_types: frozenset[str]

    def parse(
        self,
        raw: bytes,
        *,
        expected_claim_ids: frozenset[str],
        limits: ParserLimits,
    ) -> ParsedSourceResult: ...


class SourceParserRegistry:
    """Controller-installed exact parser registry; no dynamic imports are permitted."""

    def __init__(self, parsers: Iterable[SourceParser] = ()) -> None:
        self._parsers: dict[tuple[str, str], SourceParser] = {}
        for parser in parsers:
            key = (parser.parser_id, parser.parser_version)
            if key in self._parsers:
                raise ValueError(f"duplicate installed source parser: {key}")
            self._parsers[key] = parser

    def get(self, parser_id: str, parser_version: str) -> SourceParser | None:
        return self._parsers.get((parser_id, parser_version))


class BoundedJsonClaimParser:
    """Strict JSON parser for controller-defined typed claim-result documents."""

    parser_id = "JSON.CLAIM_RESULTS"
    parser_version = "1.0.0"
    allowed_content_types = frozenset({"application/json"})

    def parse(
        self,
        raw: bytes,
        *,
        expected_claim_ids: frozenset[str],
        limits: ParserLimits,
    ) -> ParsedSourceResult:
        try:
            text = raw.decode("utf-8", errors="strict")
            document: object = json.loads(
                text,
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
            _validate_json_limits(document, limits)
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            RecursionError,
            SourceParsingError,
        ) as exc:
            raise SourceParsingError("source is not bounded canonical JSON") from exc
        if not isinstance(document, dict):
            raise SourceParsingError("JSON source must contain only claimResults")
        document_mapping = cast(dict[object, object], document)
        if set(document_mapping) != {"claimResults"}:
            raise SourceParsingError("JSON source must contain only claimResults")
        typed_document = cast(dict[str, object], document_mapping)
        values = typed_document["claimResults"]
        if not isinstance(values, list):
            raise SourceParsingError("JSON claimResults is missing or unbounded")
        typed_values = cast(list[object], values)
        if not typed_values or len(typed_values) > limits.maximum_claim_results:
            raise SourceParsingError("JSON claimResults is missing or unbounded")
        results: list[ParsedClaimResult] = []
        try:
            for raw_value in typed_values:
                if not isinstance(raw_value, dict):
                    raise SourceParsingError("claim result has an invalid shape")
                value_mapping = cast(dict[object, object], raw_value)
                if set(value_mapping) != {
                    "claimId",
                    "verdict",
                    "statement",
                }:
                    raise SourceParsingError("claim result has an invalid shape")
                value = cast(dict[str, object], value_mapping)
                claim_id = value["claimId"]
                raw_verdict = value["verdict"]
                statement = value["statement"]
                if not all(isinstance(item, str) for item in (claim_id, raw_verdict, statement)):
                    raise SourceParsingError("claim result values must be strings")
                results.append(
                    ParsedClaimResult(
                        schema_version="3.1",
                        claim_id=cast(str, claim_id),
                        verdict=ResearchVerdict(cast(str, raw_verdict)),
                        statement=cast(str, statement),
                    )
                )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise SourceParsingError("claim result is invalid") from exc
        if {result.claim_id for result in results} != set(expected_claim_ids):
            raise SourceParsingError("parsed claims do not exactly cover the source plan")
        return ParsedSourceResult(
            schema_version="3.1",
            parser_id=self.parser_id,
            parser_version=self.parser_version,
            content_type="application/json",
            claim_results=results,
        )


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
        roster_digest = research_artifact_roster_digest(self.artifacts)
        if any(
            control.artifact_digest != roster_digest
            or control.raw_artifact_roster_digest != roster_digest
            or control.oracle_executable_digest == "sha256:" + "0" * 64
            for control in self.controls
        ):
            raise ValueError("research controls are not bound to the raw artifact roster/oracle")
        result_digest = research_control_result_digest(self.controls)
        if any(control.oracle_result_digest != result_digest for control in self.controls):
            raise ValueError("research control oracle result digest mismatch")
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


class ResearchResolutionReason(StrEnum):
    VALIDATED = "VALIDATED"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    STALE_SOURCE = "STALE_SOURCE"
    TAMPERED_SOURCE = "TAMPERED_SOURCE"
    PARSER_MISMATCH = "PARSER_MISMATCH"
    PARSER_UNAVAILABLE = "PARSER_UNAVAILABLE"
    PARSER_FAILURE = "PARSER_FAILURE"
    INVALID_RECEIPT = "INVALID_RECEIPT"


class ResearchResolution(ResearchModel):
    """Fail-closed controller disposition for an advisory research report."""

    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    verdict: ResearchVerdict
    reason_codes: list[ResearchResolutionReason] = Field(min_length=1, max_length=16)
    report: ResearchReport | None = None
    authority_effect: Literal["ADVISORY_ONLY_NEVER_NORMATIVE"] = "ADVISORY_ONLY_NEVER_NORMATIVE"

    @model_validator(mode="after")
    def validate_resolution(self) -> ResearchResolution:
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("research resolution reason codes must be unique")
        if self.report is None and self.verdict is not ResearchVerdict.UNKNOWN:
            raise ValueError("only UNKNOWN resolutions may omit a report")
        if self.report is not None:
            if self.report.overall_verdict is not self.verdict:
                raise ValueError("resolution verdict must match its report")
            if (
                self.report.work_item_id != self.work_item_id
                or self.report.candidate_sha != self.candidate_sha
            ):
                raise ValueError("resolution report binding mismatch")
        return self


SOURCE_ACQUISITION_CONTRACTS: dict[str, type[ResearchModel]] = {
    "source-parser-limits": ParserLimits,
    "source-acquisition-policy": SourceAcquisitionPolicy,
    "research-source-request": ResearchSourceRequest,
    "research-source": ResearchSource,
    "research-claim": ResearchClaim,
    "research-query-plan": ResearchQueryPlan,
    "source-retrieval-receipt": SourceRetrievalReceipt,
    "source-hop-receipt": SourceHopReceipt,
    "source-artifact": SourceArtifact,
    "research-control": ResearchControl,
    "research-finding": ResearchFinding,
    "parsed-claim-result": ParsedClaimResult,
    "parsed-source-result": ParsedSourceResult,
    "research-report": ResearchReport,
    "research-resolution": ResearchResolution,
}


@dataclass(frozen=True)
class FetchedHopBinding:
    url: str
    resolved_addresses: tuple[str, ...]
    peer_address: str


@dataclass(frozen=True)
class FetchedResponse:
    final_url: str
    status_code: int
    content_type: str
    headers: tuple[tuple[str, str], ...]
    body: bytes
    hop_bindings: tuple[FetchedHopBinding, ...]
    redirect_chain: tuple[str, ...] = ()
    method: Literal["GET"] = "GET"


class SourceResolver(Protocol):
    def resolve(self, hostname: str) -> tuple[str, ...]: ...


class PublicDnsResolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        return _assert_public_resolution(hostname)


class SourceTransport(Protocol):
    def fetch(
        self,
        *,
        url: str,
        method: Literal["GET"],
        timeout_seconds: float,
        max_response_bytes: int,
        user_agent: str,
        allowed_hostnames: tuple[str, ...],
        allowed_content_types: tuple[str, ...],
        resolved_addresses: tuple[str, ...],
        resolver: SourceResolver,
        max_redirects: int,
    ) -> FetchedResponse: ...


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to one validated address while retaining hostname TLS verification."""

    def __init__(
        self,
        hostname: str,
        pinned_address: str,
        *,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        self._pinned_address = pinned_address
        super().__init__(hostname, port=443, timeout=timeout, context=context)
        self._create_connection = self._connect_pinned  # type: ignore[method-assign]

    def _connect_pinned(
        self,
        address: tuple[str, int],
        timeout: object = None,
        source_address: tuple[str, int] | None = None,
    ) -> socket.socket:
        del address
        timeout_seconds = float(timeout) if isinstance(timeout, (int, float)) else None
        return socket.create_connection(
            (self._pinned_address, 443), timeout_seconds, source_address
        )


class ControlledHttpsTransport:
    """HTTPS transport pinned to controller-validated public DNS answers."""

    def fetch(
        self,
        *,
        url: str,
        method: Literal["GET"],
        timeout_seconds: float,
        max_response_bytes: int,
        user_agent: str,
        allowed_hostnames: tuple[str, ...],
        allowed_content_types: tuple[str, ...],
        resolved_addresses: tuple[str, ...],
        resolver: SourceResolver,
        max_redirects: int,
    ) -> FetchedResponse:
        if method != "GET":
            raise SourceAcquisitionError("source method is not allowlisted")
        allowed = set(allowed_hostnames)
        allowed_types = set(allowed_content_types)
        current_url = url
        current_addresses = resolved_addresses
        redirects: list[str] = []
        hop_bindings: list[FetchedHopBinding] = []
        deadline = monotonic() + timeout_seconds
        context = ssl.create_default_context()
        while True:
            parts = _validated_https_url(current_url)
            hostname = _normalize_hostname(parts.hostname or "")
            if hostname not in allowed:
                raise SourceAcquisitionError(f"redirect hostname is not allowlisted: {hostname}")
            current_addresses = _validate_public_addresses(current_addresses)
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise SourceAcquisitionError("HTTPS acquisition exceeded the total time limit")
            response: http.client.HTTPResponse | None = None
            connection: _PinnedHTTPSConnection | None = None
            last_error: OSError | ssl.SSLError | None = None
            for address in current_addresses:
                try:
                    connection = _PinnedHTTPSConnection(
                        hostname, address, timeout=remaining, context=context
                    )
                    path = urlunsplit(("", "", parts.path or "/", parts.query, ""))
                    connection.request(
                        method,
                        path,
                        headers={
                            "Accept-Encoding": "identity",
                            "Connection": "close",
                            "User-Agent": user_agent,
                        },
                    )
                    response = connection.getresponse()
                    peer = connection.sock.getpeername()[0] if connection.sock is not None else ""
                    if _canonical_ip(peer) != _canonical_ip(address):
                        raise SourceAcquisitionError("HTTPS peer did not match the pinned address")
                    hop_bindings.append(
                        FetchedHopBinding(
                            url=current_url,
                            resolved_addresses=current_addresses,
                            peer_address=_canonical_ip(address),
                        )
                    )
                    break
                except SourceAcquisitionError:
                    if connection is not None:
                        connection.close()
                    raise
                except (OSError, ssl.SSLError) as exc:
                    last_error = exc
                    if connection is not None:
                        connection.close()
                    connection = None
            if response is None or connection is None:
                raise SourceAcquisitionError(
                    f"HTTPS acquisition failed: {type(last_error).__name__}"
                ) from last_error
            try:
                status = int(response.status)
                headers = _bounded_response_headers(response.getheaders())
                if status in {301, 302, 303, 307, 308}:
                    if len(redirects) >= max_redirects:
                        raise SourceAcquisitionError("source redirect limit exhausted")
                    location = headers.get("location")
                    if not location:
                        raise SourceAcquisitionError("redirect omitted the Location header")
                    redirected = urljoin(current_url, location)
                    redirected_parts = _validated_https_url(redirected)
                    redirected_host = _normalize_hostname(redirected_parts.hostname or "")
                    if redirected_host not in allowed:
                        raise SourceAcquisitionError(
                            f"redirect hostname is not allowlisted: {redirected_host}"
                        )
                    redirects.append(redirected)
                    current_url = redirected
                    current_addresses = resolver.resolve(redirected_host)
                    continue
                if status != 200:
                    raise SourceAcquisitionError(f"source returned HTTP {status}")
                content_type = headers.get("content-type", "").lower().split(";", 1)[0].strip()
                if content_type not in allowed_types:
                    raise SourceAcquisitionError(f"content type is not allowlisted: {content_type}")
                if headers.get("content-disposition", "").lower().startswith("attachment"):
                    raise SourceAcquisitionError("arbitrary attachment downloads are forbidden")
                if headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
                    raise SourceAcquisitionError("encoded responses are forbidden")
                declared = headers.get("content-length")
                if declared is not None:
                    try:
                        if int(declared) > max_response_bytes:
                            raise SourceAcquisitionError("declared response exceeds the byte limit")
                    except ValueError as exc:
                        raise SourceAcquisitionError("invalid Content-Length header") from exc
                body = response.read(max_response_bytes + 1)
                if len(body) > max_response_bytes:
                    raise SourceAcquisitionError("response exceeds the byte limit")
                return FetchedResponse(
                    final_url=current_url,
                    status_code=status,
                    content_type=content_type,
                    headers=tuple(sorted(headers.items())),
                    body=body,
                    hop_bindings=tuple(hop_bindings),
                    redirect_chain=tuple(redirects),
                    method=method,
                )
            finally:
                connection.close()


class ControlledSourceAcquirer:
    def __init__(
        self,
        *,
        policy: SourceAcquisitionPolicy,
        artifact_root: Path,
        transport: SourceTransport | None = None,
        resolver: SourceResolver | None = None,
        receipt_authority: ReceiptAuthority | None = None,
        artifact_root_opener: Callable[[], int] | None = None,
        _allow_test_transport: bool = False,
    ) -> None:
        if (
            transport is not None
            and type(transport) is not ControlledHttpsTransport
            and not _allow_test_transport
        ):
            raise SourceAcquisitionError("custom source transports are test-only")
        self.policy = policy
        self.artifact_root = artifact_root
        self.transport = transport or ControlledHttpsTransport()
        self.resolver = resolver or PublicDnsResolver()
        self.receipt_authority = receipt_authority
        self.artifact_root_opener = artifact_root_opener

    def _open_artifact_root(self) -> int:
        if self.artifact_root_opener is not None:
            try:
                return self.artifact_root_opener()
            except Exception as exc:
                raise SourceAcquisitionError("research CAS identity changed after install") from exc
        return _open_artifact_root(self.artifact_root)

    def read_artifact(self, name: str) -> bytes:
        root_fd = self._open_artifact_root()
        try:
            return _read_raw(root_fd, name, self_limit=16 * 1024 * 1024)
        finally:
            os.close(root_fd)

    def open_artifact_root(self) -> int:
        """Open the installed CAS through its captured identity guard."""

        return self._open_artifact_root()

    def acquire(self, plan: ResearchQueryPlan) -> list[SourceArtifact]:
        if self.receipt_authority is None:
            raise SourceAcquisitionError("controller source receipt authority is unavailable")
        if plan.policy_id != self.policy.policy_id:
            raise SourceAcquisitionError("query plan policy does not match active policy")
        if len(plan.sources) > self.policy.max_sources_per_plan:
            raise SourceAcquisitionError("query plan exceeds the source limit")
        root_fd = self._open_artifact_root()
        try:
            artifacts: list[SourceArtifact] = []
            for source in plan.sources:
                parts = _validated_https_url(source.url)
                hostname = _normalize_hostname(parts.hostname or "")
                if hostname not in set(self.policy.allowed_hostnames):
                    raise SourceAcquisitionError(f"source hostname is not allowlisted: {hostname}")
                if source.method not in set(self.policy.allowed_methods):
                    raise SourceAcquisitionError(
                        f"source method is not allowlisted: {source.method}"
                    )
                if source.freshness_seconds > self.policy.maximum_freshness_seconds:
                    raise SourceAcquisitionError("source freshness exceeds the active policy")
                resolved = _validate_public_addresses(self.resolver.resolve(hostname))
                response = self.transport.fetch(
                    url=source.url,
                    method=source.method,
                    timeout_seconds=self.policy.timeout_seconds,
                    max_response_bytes=self.policy.max_response_bytes,
                    user_agent=self.policy.user_agent,
                    allowed_hostnames=tuple(self.policy.allowed_hostnames),
                    allowed_content_types=tuple(self.policy.allowed_content_types),
                    resolved_addresses=resolved,
                    resolver=self.resolver,
                    max_redirects=self.policy.max_redirects,
                )
                if response.method != source.method:
                    raise SourceAcquisitionError("transport changed the preregistered method")
                chain = [source.url, *response.redirect_chain]
                if response.final_url != chain[-1]:
                    raise SourceAcquisitionError("response URL is not bound to its redirect chain")
                if len(response.redirect_chain) > self.policy.max_redirects:
                    raise SourceAcquisitionError("response exceeded the redirect limit")
                for observed_url in chain:
                    observed_parts = _validated_https_url(observed_url)
                    observed_host = _normalize_hostname(observed_parts.hostname or "")
                    if observed_host not in set(self.policy.allowed_hostnames):
                        raise SourceAcquisitionError(
                            f"redirect hostname is not allowlisted: {observed_host}"
                        )
                if len(response.hop_bindings) != len(chain):
                    raise SourceAcquisitionError("transport omitted per-hop peer bindings")
                hop_receipts: list[SourceHopReceipt] = []
                for index, (observed_url, hop) in enumerate(
                    zip(chain, response.hop_bindings, strict=True)
                ):
                    if hop.url != observed_url:
                        raise SourceAcquisitionError("transport hop URL binding mismatch")
                    hop_parts = _validated_https_url(observed_url)
                    hop_hostname = _normalize_hostname(hop_parts.hostname or "")
                    expected_addresses = _validate_public_addresses(
                        self.resolver.resolve(hop_hostname)
                    )
                    if index == 0 and set(expected_addresses) != set(resolved):
                        raise SourceAcquisitionError("source DNS rebound during fetch")
                    observed_addresses = _validate_public_addresses(hop.resolved_addresses)
                    peer_address = _canonical_ip(hop.peer_address)
                    _validate_public_addresses([peer_address])
                    if set(observed_addresses) != set(expected_addresses):
                        raise SourceAcquisitionError("source DNS changed during pinned fetch")
                    if peer_address not in observed_addresses:
                        raise SourceAcquisitionError(
                            "transport peer is outside its controller-pinned addresses"
                        )
                    hop_receipts.append(
                        SourceHopReceipt(
                            schema_version="3.1",
                            url=_receipt_url(observed_url),
                            url_digest=_text_digest(observed_url),
                            resolved_public_addresses=list(observed_addresses),
                            peer_address=peer_address,
                        )
                    )
                if response.status_code != 200:
                    raise SourceAcquisitionError(
                        f"source returned unexpected HTTP {response.status_code}"
                    )
                if len(response.body) > self.policy.max_response_bytes:
                    raise SourceAcquisitionError("response exceeds the byte limit")
                content_type = response.content_type.lower().split(";", 1)[0]
                if content_type not in set(self.policy.allowed_content_types):
                    raise SourceAcquisitionError(f"content type is not allowlisted: {content_type}")
                bounded_headers = _bounded_response_headers(response.headers)
                header_content_type = (
                    bounded_headers.get("content-type", "").lower().split(";", 1)[0].strip()
                )
                if header_content_type and header_content_type != content_type:
                    raise SourceAcquisitionError("transport content type metadata conflicts")
                disposition = bounded_headers.get("content-disposition", "").lower()
                if disposition.startswith("attachment") or "filename=" in disposition:
                    raise SourceAcquisitionError("arbitrary attachment downloads are forbidden")
                if bounded_headers.get("content-encoding", "identity").lower() not in {
                    "",
                    "identity",
                }:
                    raise SourceAcquisitionError("encoded responses are forbidden")
                declared_length = bounded_headers.get("content-length")
                if declared_length is not None:
                    try:
                        if int(declared_length) != len(response.body):
                            raise SourceAcquisitionError(
                                "transport Content-Length metadata conflicts"
                            )
                    except ValueError as exc:
                        raise SourceAcquisitionError("invalid Content-Length header") from exc
                content_digest = f"sha256:{hashlib.sha256(response.body).hexdigest()}"
                header_bytes = "\n".join(
                    f"{key}:{value}" for key, value in sorted(bounded_headers.items())
                ).encode()
                headers_digest = f"sha256:{hashlib.sha256(header_bytes).hexdigest()}"
                artifact_name = f"{content_digest.removeprefix('sha256:')}.raw"
                _publish_raw(root_fd, artifact_name, response.body)
                retrieved_at = datetime.now(UTC)
                plan_digest = _canonical_model_digest(plan)
                receipt_seed = (
                    hashlib.sha256(f"{plan_digest}:{source.source_id}:{content_digest}".encode())
                    .hexdigest()[:24]
                    .upper()
                )
                receipt_draft = SourceRetrievalReceipt.model_construct(
                    schema_version="3.1",
                    receipt_id=f"SRCREC-{receipt_seed}",
                    source_id=source.source_id,
                    work_item_id=plan.work_item_id,
                    candidate_sha=plan.candidate_sha,
                    policy_id=plan.policy_id,
                    plan_digest=plan_digest,
                    method=source.method,
                    requested_url=_receipt_url(source.url),
                    requested_url_digest=_text_digest(source.url),
                    final_url=_receipt_url(response.final_url),
                    final_url_digest=_text_digest(response.final_url),
                    redirect_chain=[_receipt_url(url) for url in response.redirect_chain],
                    redirect_chain_digests=[_text_digest(url) for url in response.redirect_chain],
                    hop_receipts=hop_receipts,
                    retrieved_at=retrieved_at,
                    status_code=200,
                    response_headers=bounded_headers,
                    content_type=content_type,
                    content_length=len(response.body),
                    source_class=source.source_class,
                    query=source.query,
                    control_query=source.control_query,
                    content_digest=content_digest,
                    parser_id=source.parser_id,
                    parser_version=source.parser_version,
                    freshness_policy=source.freshness_policy,
                    fresh_until=retrieved_at + timedelta(seconds=source.freshness_seconds),
                    authority_effect="ADVISORY_ONLY_NEVER_NORMATIVE",
                    issuer_id=self.receipt_authority.issuer_id,
                    issuer_key_id=self.receipt_authority.key_id,
                    signature_algorithm=self.receipt_authority.signature_algorithm,
                    signature="0" * 64,
                )
                signature = self.receipt_authority.sign(
                    _source_receipt_signature_payload(receipt_draft)
                )
                receipt = SourceRetrievalReceipt.model_validate(
                    receipt_draft.model_copy(update={"signature": signature}).model_dump(
                        by_alias=True
                    ),
                    strict=True,
                )
                if not self.receipt_authority.verify(
                    _source_receipt_signature_payload(receipt),
                    signature=receipt.signature,
                    issuer_id=receipt.issuer_id,
                    key_id=receipt.issuer_key_id,
                    signature_algorithm=receipt.signature_algorithm,
                ):
                    raise SourceAcquisitionError("source receipt authority rejected its signature")
                artifacts.append(
                    SourceArtifact(
                        schema_version="3.1",
                        source_id=source.source_id,
                        source_class=source.source_class,
                        requested_url=_receipt_url(source.url),
                        final_url=_receipt_url(response.final_url),
                        observed_at=datetime.now(UTC),
                        status_code=response.status_code,
                        content_type=content_type,
                        content_length=len(response.body),
                        content_digest=content_digest,
                        headers_digest=headers_digest,
                        artifact_path=artifact_name,
                        claim_ids=source.claim_ids,
                        retrieval_receipt=receipt,
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
    artifact_root_opener: Callable[[], int] | None = None,
) -> ResearchReport:
    """Bind a strict finding set to its preregistered plan and acquired raw bytes."""

    artifact_by_source = {artifact.source_id: artifact for artifact in artifacts}
    if set(artifact_by_source) != {source.source_id for source in plan.sources}:
        raise SourceAcquisitionError("artifacts do not exactly cover the query plan sources")
    root_fd = _open_bound_artifact_root(artifact_root, artifact_root_opener)
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
    plan_digest = _canonical_model_digest(plan)
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


def resolve_research_report(
    *,
    report_id: str,
    plan: ResearchQueryPlan,
    artifact_root: Path,
    artifacts: list[SourceArtifact],
    controls: list[ResearchControl],
    expected_parsers: dict[str, tuple[str, str]],
    parser_registry: SourceParserRegistry | None,
    receipt_authority: ReceiptAuthority | None,
    now: datetime,
    control_oracle: ResearchControlOracle | None = None,
    artifact_root_opener: Callable[[], int] | None = None,
) -> ResearchResolution:
    """Convert stale, tampered, or parser-incompatible evidence into typed UNKNOWN."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise SourceAcquisitionError("research resolution time must be timezone-aware")

    expected_source_ids = {source.source_id for source in plan.sources}
    if set(expected_parsers) != expected_source_ids:
        return _unknown_resolution(plan, ResearchResolutionReason.PARSER_MISMATCH)
    if parser_registry is None:
        return _unknown_resolution(plan, ResearchResolutionReason.PARSER_UNAVAILABLE)
    if receipt_authority is None:
        return _unknown_resolution(plan, ResearchResolutionReason.INVALID_RECEIPT)
    if control_oracle is None:
        return _unknown_resolution(plan, ResearchResolutionReason.PARSER_UNAVAILABLE)

    source_by_id = {source.source_id: source for source in plan.sources}
    plan_digest = _canonical_model_digest(plan)
    parsed_by_claim: dict[str, list[tuple[str, ParsedClaimResult]]] = {
        claim.claim_id: [] for claim in plan.claims
    }
    root_fd = _open_bound_artifact_root(artifact_root, artifact_root_opener)
    for artifact in artifacts:
        try:
            receipt = SourceRetrievalReceipt.model_validate(
                artifact.retrieval_receipt.model_dump(by_alias=True), strict=True
            )
        except ValidationError:
            os.close(root_fd)
            return _unknown_resolution(plan, ResearchResolutionReason.INVALID_RECEIPT)
        source = source_by_id.get(artifact.source_id)
        if (
            source is None
            or receipt.source_id != artifact.source_id
            or receipt.content_digest != artifact.content_digest
            or receipt.final_url != artifact.final_url
            or receipt.content_length != artifact.content_length
            or receipt.plan_digest != plan_digest
            or receipt.work_item_id != plan.work_item_id
            or receipt.candidate_sha != plan.candidate_sha
            or receipt.policy_id != plan.policy_id
            or receipt.requested_url_digest != _text_digest(source.url)
        ):
            os.close(root_fd)
            return _unknown_resolution(plan, ResearchResolutionReason.INVALID_RECEIPT)
        try:
            verified = receipt_authority.verify(
                _source_receipt_signature_payload(receipt),
                signature=receipt.signature,
                issuer_id=receipt.issuer_id,
                key_id=receipt.issuer_key_id,
                signature_algorithm=receipt.signature_algorithm,
            )
        except Exception:
            verified = False
        if not verified:
            os.close(root_fd)
            return _unknown_resolution(plan, ResearchResolutionReason.INVALID_RECEIPT)
        if receipt.fresh_until <= now:
            os.close(root_fd)
            return _unknown_resolution(plan, ResearchResolutionReason.STALE_SOURCE)
        if expected_parsers.get(artifact.source_id) != (
            receipt.parser_id,
            receipt.parser_version,
        ):
            os.close(root_fd)
            return _unknown_resolution(plan, ResearchResolutionReason.PARSER_MISMATCH)
        parser = parser_registry.get(receipt.parser_id, receipt.parser_version)
        if parser is None:
            os.close(root_fd)
            return _unknown_resolution(plan, ResearchResolutionReason.PARSER_UNAVAILABLE)
        if artifact.content_type not in parser.allowed_content_types:
            os.close(root_fd)
            return _unknown_resolution(plan, ResearchResolutionReason.PARSER_MISMATCH)
        try:
            raw = _read_raw(root_fd, artifact.artifact_path, self_limit=16 * 1024 * 1024)
            observed_digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
            if observed_digest != artifact.content_digest or len(raw) != artifact.content_length:
                raise SourceAcquisitionError("source artifact digest does not match raw bytes")
            parsed = parser.parse(
                raw,
                expected_claim_ids=frozenset(source.claim_ids),
                limits=plan.parser_limits,
            )
            parsed = ParsedSourceResult.model_validate(
                parsed.model_dump(by_alias=True), strict=True
            )
        except SourceAcquisitionError:
            os.close(root_fd)
            return _unknown_resolution(plan, ResearchResolutionReason.TAMPERED_SOURCE)
        except (SourceParsingError, ValidationError, ValueError, TypeError):
            os.close(root_fd)
            return _unknown_resolution(plan, ResearchResolutionReason.PARSER_FAILURE)
        if (
            parsed.parser_id != receipt.parser_id
            or parsed.parser_version != receipt.parser_version
            or parsed.content_type != artifact.content_type
            or {result.claim_id for result in parsed.claim_results} != set(source.claim_ids)
        ):
            os.close(root_fd)
            return _unknown_resolution(plan, ResearchResolutionReason.PARSER_MISMATCH)
        for parsed_claim in parsed.claim_results:
            parsed_by_claim[parsed_claim.claim_id].append((artifact.content_digest, parsed_claim))
    os.close(root_fd)

    findings: list[ResearchFinding] = []
    for claim in plan.claims:
        evidence = parsed_by_claim[claim.claim_id]
        verdicts = {result.verdict for _, result in evidence}
        if ResearchVerdict.CONFLICT in verdicts:
            verdict = ResearchVerdict.CONFLICT
        elif evidence and verdicts == {ResearchVerdict.CLEAR}:
            verdict = ResearchVerdict.CLEAR
        else:
            verdict = ResearchVerdict.UNKNOWN
        statement = " | ".join(result.statement for _, result in evidence)[:4000]
        findings.append(
            ResearchFinding(
                schema_version="3.1",
                claim_id=claim.claim_id,
                verdict=verdict,
                statement=statement or "Trusted parser produced no conclusive claim evidence.",
                source_artifact_digests=(
                    list(dict.fromkeys(digest for digest, _ in evidence))
                    if verdict is not ResearchVerdict.UNKNOWN
                    else []
                ),
            )
        )

    try:
        expected_control_roster = {
            (control.kind, control.expected_verdict) for control in controls
        }
        computed_controls = control_oracle.evaluate(
            plan=plan,
            artifact_root=artifact_root,
            artifacts=artifacts,
            expected_controls=controls,
            artifact_root_opener=artifact_root_opener,
        )
        controls = [
            ResearchControl.model_validate(
                control.model_dump(by_alias=True), strict=True
            )
            for control in computed_controls
        ]
        if {
            (control.kind, control.expected_verdict) for control in controls
        } != expected_control_roster:
            raise SourceAcquisitionError(
                "research control oracle changed preregistered controls"
            )
        roster_digest = research_artifact_roster_digest(artifacts)
        if any(
            control.artifact_digest != roster_digest
            or control.raw_artifact_roster_digest != roster_digest
            or control.oracle_executable_digest == "sha256:" + "0" * 64
            for control in controls
        ):
            raise SourceAcquisitionError(
                "research control oracle evidence binding mismatch"
            )
        result_digest = research_control_result_digest(controls)
        if any(
            control.oracle_result_digest != result_digest for control in controls
        ):
            raise SourceAcquisitionError(
                "research control oracle result digest mismatch"
            )
        report = compile_research_report(
            report_id=report_id,
            plan=plan,
            artifact_root=artifact_root,
            artifacts=artifacts,
            controls=controls,
            findings=findings,
            artifact_root_opener=artifact_root_opener,
        )
    except (SourceAcquisitionError, ValidationError, ValueError, TypeError) as exc:
        message = str(exc)
        reason = (
            ResearchResolutionReason.TAMPERED_SOURCE
            if "raw bytes" in message
            else ResearchResolutionReason.INVALID_RECEIPT
        )
        return _unknown_resolution(plan, reason)

    if report.overall_verdict is ResearchVerdict.CONFLICT:
        reason = ResearchResolutionReason.SOURCE_CONFLICT
    elif report.overall_verdict is ResearchVerdict.UNKNOWN:
        reason = ResearchResolutionReason.INSUFFICIENT_EVIDENCE
    else:
        reason = ResearchResolutionReason.VALIDATED
    return ResearchResolution(
        schema_version="3.1",
        work_item_id=plan.work_item_id,
        candidate_sha=plan.candidate_sha,
        verdict=report.overall_verdict,
        reason_codes=[reason],
        report=report,
    )


def _unknown_resolution(
    plan: ResearchQueryPlan, reason: ResearchResolutionReason
) -> ResearchResolution:
    return ResearchResolution(
        schema_version="3.1",
        work_item_id=plan.work_item_id,
        candidate_sha=plan.candidate_sha,
        verdict=ResearchVerdict.UNKNOWN,
        reason_codes=[reason],
        report=None,
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
    _validate_noncredential_query(parts.query)
    _normalize_hostname(parts.hostname)
    return parts


_CREDENTIAL_QUERY_NAME = re.compile(
    r"(?:^|[_-])(?:api[_-]?key|access[_-]?token|auth|authorization|credential|"
    r"password|passwd|secret|signature|sig|token|x[_-]?amz[_-]?credential|"
    r"x[_-]?amz[_-]?signature)(?:$|[_-])",
    re.IGNORECASE,
)
_CREDENTIAL_VALUE = re.compile(
    r"^(?:bearer\s+|basic\s+|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{16,}|"
    r"AKIA[A-Z0-9]{16}|[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\."
    r"[A-Za-z0-9_-]{16,})",
    re.IGNORECASE,
)


def _query_pairs(query: str) -> list[tuple[str, str]]:
    try:
        return parse_qsl(
            query,
            keep_blank_values=True,
            strict_parsing=False,
            max_num_fields=64,
        )
    except ValueError as exc:
        raise ValueError("source URL query is invalid or unbounded") from exc


def _validate_noncredential_query(query: str) -> None:
    for name, value in _query_pairs(query):
        if _CREDENTIAL_QUERY_NAME.search(name):
            raise ValueError("source URL cannot contain credential-like query names")
        if _CREDENTIAL_VALUE.search(value) or (len(value) >= 64 and " " not in value):
            raise ValueError("source URL cannot contain credential-like query values")


def _receipt_url(value: str) -> str:
    parts = _validated_https_url(value)
    pairs = _query_pairs(parts.query)
    redacted_query = urlencode([(name, "<redacted>") for name, _ in pairs])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, redacted_query, ""))


def _text_digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode()).hexdigest()}"


def _assert_public_resolution(hostname: str) -> tuple[str, ...]:
    try:
        addresses: set[str] = set()
        for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM):
            address = item[4][0]
            if not isinstance(address, str):
                raise SourceAcquisitionError("source resolution returned an invalid address")
            addresses.add(address)
    except OSError as exc:
        raise SourceAcquisitionError("source hostname could not be resolved") from exc
    if not addresses:
        raise SourceAcquisitionError("source hostname returned no addresses")
    return _validate_public_addresses(tuple(sorted(addresses)))


def _canonical_ip(value: str) -> str:
    try:
        return ipaddress.ip_address(value).compressed
    except ValueError as exc:
        raise SourceAcquisitionError("source resolution returned an invalid address") from exc


def _validate_public_addresses(addresses: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise SourceAcquisitionError("source resolution returned an invalid address") from exc
        if (
            not parsed.is_global
            or parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_reserved
            or parsed.is_multicast
            or parsed.is_unspecified
        ):
            raise SourceAcquisitionError("source hostname resolved to a non-public address")
        normalized.append(parsed.compressed)
    result = tuple(dict.fromkeys(normalized))
    if not result:
        raise SourceAcquisitionError("source hostname returned no addresses")
    return result


_RECEIPT_HEADER_NAMES = frozenset(
    {
        "cache-control",
        "content-disposition",
        "content-encoding",
        "content-length",
        "content-type",
        "date",
        "etag",
        "expires",
        "last-modified",
        "location",
    }
)


def _bounded_response_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    bounded: dict[str, str] = {}
    for raw_name, raw_value in headers:
        name = raw_name.strip().lower()
        value = raw_value.strip()
        if name not in _RECEIPT_HEADER_NAMES:
            continue
        if name in bounded:
            raise SourceAcquisitionError(f"duplicate security-relevant response header: {name}")
        if "\r" in value or "\n" in value or len(value) > 2048:
            raise SourceAcquisitionError("response header is unsafe or unbounded")
        bounded[name] = value
    return bounded


def _canonical_model_digest(model: ResearchModel, *, exclude: set[str] | None = None) -> str:
    payload = model.model_dump(mode="json", by_alias=True, exclude=exclude or set())
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _source_receipt_signature_payload(receipt: SourceRetrievalReceipt) -> bytes:
    payload = receipt.model_dump(mode="json", by_alias=True, exclude={"signature"})
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def source_receipt_signature_payload(receipt: SourceRetrievalReceipt) -> bytes:
    """Return the deterministic signed bytes for a source receipt."""

    return _source_receipt_signature_payload(receipt)


def research_artifact_roster_digest(artifacts: list[SourceArtifact]) -> str:
    roster = [
        {
            "sourceId": artifact.source_id,
            "artifactPath": artifact.artifact_path,
            "contentDigest": artifact.content_digest,
            "contentLength": artifact.content_length,
            "receiptId": artifact.retrieval_receipt.receipt_id,
        }
        for artifact in sorted(artifacts, key=lambda value: value.source_id)
    ]
    raw = json.dumps(roster, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def research_control_result_digest(controls: list[ResearchControl]) -> str:
    payload = [
        control.model_dump(
            mode="json",
            by_alias=True,
            exclude={"oracle_result_digest"},
        )
        for control in sorted(controls, key=lambda value: value.kind.value)
    ]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _open_bound_artifact_root(
    path: Path, opener: Callable[[], int] | None
) -> int:
    if opener is None:
        return _open_artifact_root(path)
    try:
        return opener()
    except Exception as exc:
        raise SourceAcquisitionError("research artifact root identity changed") from exc


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SourceParsingError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise SourceParsingError(f"invalid JSON constant: {value}")


def _validate_json_limits(value: object, limits: ParserLimits) -> None:
    nodes = 0
    string_bytes = 0
    stack: list[tuple[object, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > limits.maximum_nodes:
            raise SourceParsingError("JSON source exceeds the node limit")
        if depth > limits.maximum_depth:
            raise SourceParsingError("JSON source exceeds the depth limit")
        if isinstance(current, str):
            string_bytes += len(current.encode("utf-8"))
        elif isinstance(current, dict):
            mapping = cast(dict[object, object], current)
            for key, item in mapping.items():
                if not isinstance(key, str):
                    raise SourceParsingError("JSON object key is not a string")
                string_bytes += len(key.encode("utf-8"))
                stack.append((item, depth + 1))
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in cast(list[object], current))
        if string_bytes > limits.maximum_string_bytes:
            raise SourceParsingError("JSON source exceeds the string-byte limit")


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
        try:
            fd = os.open(
                name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=root_fd,
            )
        except OSError as exc:
            raise SourceAcquisitionError("existing source artifact is unsafe") from exc
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != len(body):
                raise SourceAcquisitionError(
                    "existing source artifact must be the exact bounded regular object"
                )
            chunks: list[bytes] = []
            remaining = len(body) + 1
            while remaining > 0:
                chunk = os.read(fd, min(1024 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            existing = b"".join(chunks)
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
