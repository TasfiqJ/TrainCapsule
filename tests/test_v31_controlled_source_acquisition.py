from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

import pytest
from pydantic import ValidationError

from tcfactory.util import read_json, sha256_file, write_json
from tcfactory.v3.enums import Lane
from tcfactory.v3.market_artifacts import DiscoveryInterviewGuide, InterviewQuestion
from tcfactory.v3.phase6_runtime import (
    Phase6ControllerRuntime,
    Phase6RuntimeError,
    ResearchOutputDeclaration,
    ResearchOutputKind,
)
from tcfactory.v3.service_storage import TrustedServiceDirectory
from tcfactory.v3.source_acquisition import (
    BoundedJsonClaimParser,
    ControlKind,
    ControlledSourceAcquirer,
    FetchedHopBinding,
    FetchedResponse,
    InProcessResearchControlOracle,
    ResearchClaim,
    ResearchControl,
    ResearchFinding,
    ResearchQueryPlan,
    ResearchResolutionReason,
    ResearchSource,
    ResearchVerdict,
    SourceAcquisitionError,
    SourceAcquisitionPolicy,
    SourceArtifact,
    SourceClass,
    SourceParserRegistry,
    compile_research_report,
    research_artifact_roster_digest,
    resolve_research_report,
)
from tcfactory.v3.work_items import WorkItem

SHA = "a" * 40


class FakeTransport:
    def __init__(
        self,
        *,
        final_url: str = "https://docs.example.test/fact.json",
        content_type: str = "application/json",
        body: bytes = (
            b'{"claimResults":[{"claimId":"CLAIM-001","verdict":"CLEAR",'
            b'"statement":"bounded parser evidence"}]}\n'
        ),
        status_code: int = 200,
        redirect_chain: tuple[str, ...] = (),
        resolved_addresses: tuple[str, ...] = ("93.184.216.34",),
    ) -> None:
        self.final_url = final_url
        self.content_type = content_type
        self.body = body
        self.status_code = status_code
        self.redirect_chain = redirect_chain
        self.resolved_addresses = resolved_addresses
        self.calls: list[str] = []

    def fetch(
        self,
        *,
        url: str,
        method: str,
        timeout_seconds: float,
        max_response_bytes: int,
        user_agent: str,
        allowed_hostnames: tuple[str, ...],
        allowed_content_types: tuple[str, ...],
        resolved_addresses: tuple[str, ...],
        resolver: object,
        max_redirects: int,
    ) -> FetchedResponse:
        del resolver
        self.calls.append(url)
        assert method == "GET"
        assert timeout_seconds == 5
        assert max_response_bytes == 4096
        assert user_agent == "TrainCapsule controlled research/3.1"
        assert allowed_hostnames == ("docs.example.test",)
        assert allowed_content_types == ("application/json",)
        assert resolved_addresses == ("93.184.216.34",)
        assert max_redirects == 3
        return FetchedResponse(
            final_url=self.final_url,
            status_code=self.status_code,
            content_type=self.content_type,
            headers=(("content-type", self.content_type),),
            body=self.body,
            hop_bindings=tuple(
                FetchedHopBinding(
                    url=hop_url,
                    resolved_addresses=self.resolved_addresses,
                    peer_address=self.resolved_addresses[0],
                )
                for hop_url in (url, *self.redirect_chain)
            ),
            redirect_chain=self.redirect_chain,
        )


class FakeResolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        assert hostname == "docs.example.test"
        return ("93.184.216.34",)


class FixtureReceiptAuthority:
    issuer_id = "CONTROLLER:TEST:001"
    key_id = "KEY:TEST:HMAC:001"
    signature_algorithm = "hmac-sha256"
    _key = b"independent-test-key-outside-repository"

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()

    def verify(
        self,
        payload: bytes,
        *,
        signature: str,
        issuer_id: str,
        key_id: str,
        signature_algorithm: str,
    ) -> bool:
        if (
            issuer_id != self.issuer_id
            or key_id != self.key_id
            or signature_algorithm != self.signature_algorithm
        ):
            return False
        return hmac.compare_digest(self.sign(payload), signature)


AUTHORITY = FixtureReceiptAuthority()
PARSERS = SourceParserRegistry([BoundedJsonClaimParser()])
CONTROL_ORACLE = InProcessResearchControlOracle()
_acquirer = partial(
    ControlledSourceAcquirer,
    receipt_authority=AUTHORITY,
    _allow_test_transport=True,
)


def policy() -> SourceAcquisitionPolicy:
    return SourceAcquisitionPolicy(
        schema_version="3.1",
        policy_id="RESEARCH-POLICY-001",
        allowed_hostnames=["docs.example.test"],
        timeout_seconds=5,
        max_response_bytes=4096,
        max_sources_per_plan=4,
        allowed_content_types=["application/json"],
        user_agent="TrainCapsule controlled research/3.1",
    )


def plan(
    *,
    lane: Lane = Lane.MARKET,
    url: str = "https://docs.example.test/fact.json",
) -> ResearchQueryPlan:
    return ResearchQueryPlan(
        schema_version="3.1",
        plan_id="QUERY-PLAN-001",
        work_item_id="V3-MKT-001",
        lane=lane,
        candidate_sha=SHA,
        policy_id="RESEARCH-POLICY-001",
        claims=[
            ResearchClaim(
                schema_version="3.1", claim_id="CLAIM-001", question="Is the fact current?"
            )
        ],
        sources=[
            ResearchSource(
                schema_version="3.1",
                source_id="SOURCE-001",
                url=url,
                query="current fact",
                control_query="known-negative current fact",
                parser_id="JSON.CLAIM_RESULTS",
                parser_version="1.0.0",
                freshness_policy="DAILY",
                freshness_seconds=3600,
                source_class=SourceClass.OFFICIAL_DOCUMENTATION,
                claim_ids=["CLAIM-001"],
            )
        ],
    )


def controls() -> list[ResearchControl]:
    outcomes = {
        ControlKind.POSITIVE: ResearchVerdict.CLEAR,
        ControlKind.NEGATIVE: ResearchVerdict.CONFLICT,
        ControlKind.ERROR: ResearchVerdict.UNKNOWN,
    }
    return [
        ResearchControl(
            schema_version="3.1",
            kind=kind,
            artifact_digest=f"sha256:{str(index) * 64}",
            raw_artifact_roster_digest=f"sha256:{str(index) * 64}",
            oracle_executable_digest="sha256:" + "a" * 64,
            oracle_result_digest="sha256:" + "b" * 64,
            expected_verdict=verdict,
            observed_verdict=verdict,
        )
        for index, (kind, verdict) in enumerate(outcomes.items(), start=1)
    ]


def bound_controls(
    artifact_root: Path, artifacts: list[SourceArtifact]
) -> list[ResearchControl]:
    return CONTROL_ORACLE.evaluate(
        plan=plan(),
        artifact_root=artifact_root,
        artifacts=artifacts,
        expected_controls=controls(),
        artifact_root_opener=None,
    )


def research_item() -> WorkItem:
    return WorkItem.model_validate(
        {
            "version": 3,
            "workItemId": "V3-MKT-001",
            "title": "Controlled market research",
            "lane": "MARKET",
            "kind": "RESEARCH",
            "milestone": "M3_MARKET_EVIDENCE",
            "decisionContribution": "Advisory current-fact evidence.",
            "customerOutcome": "No normative claim.",
            "dependsOn": [],
            "softDependsOn": [],
            "blocksCommercialRelease": False,
            "priority": 80,
            "riskTier": "STANDARD",
            "maturityTarget": {
                "engineering": "CONTROLLED_VALIDATED",
                "commercial": "NOT_EVALUATED",
            },
            "disposition": "KEEP",
            "status": "PROPOSED",
            "ownerType": "AI",
            "automatable": True,
            "evidenceRequired": ["signed advisory source receipts"],
            "externalReceiptRequired": False,
            "retryPolicy": {
                "maxPlanAttempts": 2,
                "maxCandidateRepairCycles": 2,
                "maxSameFindingRepeats": 2,
                "maxCandidateRestarts": 1,
            },
        }
    )


def test_phase6_runtime_exposes_only_signed_offline_advisory_evidence(
    tmp_path: Path,
) -> None:
    plan_root = tmp_path / "plans"
    plan_root.mkdir()
    write_json(plan_root / "V3-MKT-001.json", plan().model_dump(mode="json", by_alias=True))
    write_json(
        plan_root / "V3-MKT-001.controls.json",
        [
            control.model_dump(mode="json", by_alias=True, exclude={"observed_verdict"})
            for control in controls()
        ],
    )
    cas = tmp_path / "cas"
    cas.mkdir()
    acquirer = _acquirer(
        policy=policy(),
        artifact_root=cas,
        transport=FakeTransport(),
        resolver=FakeResolver(),
    )
    cas.chmod(0o700)
    cas_guard = TrustedServiceDirectory.capture(cas, owner_uid=os.getuid())
    acquirer.artifact_root_opener = cas_guard.open_fd
    runtime = Phase6ControllerRuntime(
        research_plan_root=plan_root,
        research_acquirer=acquirer,
        parser_registry=PARSERS,
        research_control_oracle=CONTROL_ORACLE,
        source_receipt_authority=AUTHORITY,
        external_request_root=tmp_path / "actions",
        external_action_adapter=None,
        external_outcome_root=tmp_path / "outcomes",
    )

    bundle = runtime.prepare_research_advisory(
        item=research_item(),
        candidate_sha=SHA,
        artifact_root=tmp_path / "advisory",
        now=datetime.now(UTC),
    )

    assert bundle.network_policy == "DENY"
    assert bundle.authority_effect == "ADVISORY_ONLY_NEVER_NORMATIVE"
    assert len(bundle.artifacts) == 1
    assert Path(bundle.artifacts[0].raw_cas_path).is_file()
    receipt = Path(bundle.artifacts[0].receipt_path).read_text(encoding="utf-8")
    assert "ADVISORY_ONLY_NEVER_NORMATIVE" in receipt
    assert "signature" in receipt

    immutable = runtime.materialize_research_advisory(
        bundle, evidence_root=tmp_path / "candidate-evidence"
    )
    runtime.verify_research_advisory(immutable)
    raw_copy = Path(immutable.artifacts[0].raw_cas_path)
    raw_copy.chmod(0o600)
    raw_copy.write_bytes(b"substituted")
    with pytest.raises(Phase6RuntimeError, match="digest mismatch"):
        runtime.verify_research_advisory(immutable)

    moved_cas = cas.with_name("cas-original")
    cas.rename(moved_cas)
    cas.mkdir(mode=0o700)
    cas.chmod(0o700)
    for source_artifact in bundle.artifacts:
        raw_name = Path(source_artifact.raw_cas_path).name
        (cas / raw_name).write_bytes((moved_cas / raw_name).read_bytes())
    with pytest.raises(Phase6RuntimeError, match="CAS identity changed"):
        runtime.materialize_research_advisory(
            bundle, evidence_root=tmp_path / "swapped-cas-evidence"
        )

    write_json(
        plan_root / "V3-MKT-001.controls.json",
        [control.model_dump(mode="json", by_alias=True) for control in controls()],
    )
    with pytest.raises(Phase6RuntimeError, match="may not assert observed verdicts"):
        runtime.prepare_research_advisory(
            item=research_item(),
            candidate_sha=SHA,
            artifact_root=tmp_path / "forged-control-advisory",
            now=datetime.now(UTC),
        )


def test_phase6_runtime_parser_authority_and_plan_substitution_wait_fail_closed(
    tmp_path: Path,
) -> None:
    plan_root = tmp_path / "plans"
    plan_root.mkdir()
    write_json(plan_root / "V3-MKT-001.json", plan().model_dump(mode="json", by_alias=True))
    write_json(
        plan_root / "V3-MKT-001.controls.json",
        [
            control.model_dump(mode="json", by_alias=True, exclude={"observed_verdict"})
            for control in controls()
        ],
    )
    cas = tmp_path / "cas"
    cas.mkdir()
    runtime = Phase6ControllerRuntime(
        research_plan_root=plan_root,
        research_acquirer=_acquirer(
            policy=policy(),
            artifact_root=cas,
            transport=FakeTransport(),
            resolver=FakeResolver(),
        ),
        parser_registry=None,
        source_receipt_authority=AUTHORITY,
        external_request_root=tmp_path / "actions",
        external_action_adapter=None,
        external_outcome_root=tmp_path / "outcomes",
    )
    with pytest.raises(Phase6RuntimeError, match="parser or receipt authority"):
        runtime.prepare_research_advisory(
            item=research_item(),
            candidate_sha=SHA,
            artifact_root=tmp_path / "advisory",
            now=datetime.now(UTC),
        )

    unknown_cas = tmp_path / "unknown-cas"
    unknown_cas.mkdir()
    unknown_runtime = Phase6ControllerRuntime(
        research_plan_root=plan_root,
        research_acquirer=_acquirer(
            policy=policy(),
            artifact_root=unknown_cas,
            transport=FakeTransport(body=b"not-json-at-all"),
            resolver=FakeResolver(),
        ),
        parser_registry=PARSERS,
        research_control_oracle=CONTROL_ORACLE,
        source_receipt_authority=AUTHORITY,
        external_request_root=tmp_path / "actions",
        external_action_adapter=None,
        external_outcome_root=tmp_path / "outcomes",
    )
    with pytest.raises(Phase6RuntimeError, match="evidence is unavailable"):
        unknown_runtime.prepare_research_advisory(
            item=research_item(),
            candidate_sha=SHA,
            artifact_root=tmp_path / "unknown-advisory",
            now=datetime.now(UTC),
        )


def test_phase8_typed_market_artifact_is_reachable_only_from_bound_research(
    tmp_path: Path,
) -> None:
    plan_root = tmp_path / "plans"
    plan_root.mkdir()
    write_json(plan_root / "V3-MKT-001.json", plan().model_dump(mode="json", by_alias=True))
    write_json(
        plan_root / "V3-MKT-001.controls.json",
        [
            control.model_dump(mode="json", by_alias=True, exclude={"observed_verdict"})
            for control in controls()
        ],
    )
    guide = DiscoveryInterviewGuide(
        schema_version="3.1",
        guide_id="GUIDE:DISCOVERY:001",
        source_generation_digest="sha256:" + "9" * 64,
        questions=[
            InterviewQuestion(
                schema_version="3.1",
                question_id=f"Q-{index:03d}",
                prompt=f"Evidence question {index}?",
                evidence_target="Attributable external fact",
                disallowed_inference="Never synthesize an answer",
            )
            for index in range(1, 9)
        ],
    )
    write_json(
        plan_root / "V3-MKT-001.discovery-interview-guide.json",
        guide.model_dump(mode="json", by_alias=True),
    )
    cas = tmp_path / "cas"
    cas.mkdir()
    runtime = Phase6ControllerRuntime(
        research_plan_root=plan_root,
        research_acquirer=_acquirer(
            policy=policy(),
            artifact_root=cas,
            transport=FakeTransport(),
            resolver=FakeResolver(),
        ),
        parser_registry=PARSERS,
        research_control_oracle=CONTROL_ORACLE,
        source_receipt_authority=AUTHORITY,
        external_request_root=tmp_path / "actions",
        external_action_adapter=None,
        external_outcome_root=tmp_path / "outcomes",
    )
    runtime.research_output_declarations = {
        "V3-MKT-001": (
            ResearchOutputDeclaration(
                kind=ResearchOutputKind.DISCOVERY_INTERVIEW_GUIDE,
                record_suffix=".discovery-interview-guide.json",
                record_digest=(
                    "sha256:" + sha256_file(plan_root / "V3-MKT-001.discovery-interview-guide.json")
                ),
            ),
        )
    }
    item = research_item().model_copy(update={"evidence_required": ["discovery-interview-guide"]})

    bundle = runtime.prepare_research_advisory(
        item=item,
        candidate_sha=SHA,
        artifact_root=tmp_path / "advisory",
        now=datetime.now(UTC),
    )

    assert set(bundle.typed_market_artifacts) == {"discovery-interview-guide"}
    typed = tmp_path / "advisory/discovery-interview-guide.json"
    assert typed.is_file()
    assert read_json(typed, {})["allowsSyntheticAnswers"] is False

    (plan_root / "V3-MKT-001.discovery-interview-guide.json").unlink()
    with pytest.raises(Phase6RuntimeError, match="record is unavailable"):
        runtime.prepare_research_advisory(
            item=item,
            candidate_sha=SHA,
            artifact_root=tmp_path / "second-advisory",
            now=datetime.now(UTC),
        )

    substituted = plan().model_copy(update={"candidate_sha": "b" * 40})
    write_json(
        plan_root / "V3-MKT-001.json",
        substituted.model_dump(mode="json", by_alias=True),
    )
    runtime.parser_registry = PARSERS
    with pytest.raises(Phase6RuntimeError, match="identity mismatch"):
        runtime.prepare_research_advisory(
            item=research_item(),
            candidate_sha=SHA,
            artifact_root=tmp_path / "advisory",
            now=datetime.now(UTC),
        )


def test_acquires_only_preregistered_bytes_and_compiles_bound_report(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    transport = FakeTransport()
    query_plan = plan()
    artifacts = _acquirer(
        policy=policy(),
        artifact_root=artifact_root,
        transport=transport,
        resolver=FakeResolver(),
    ).acquire(query_plan)

    expected_digest = f"sha256:{hashlib.sha256(transport.body).hexdigest()}"
    assert transport.calls == [query_plan.sources[0].url]
    assert artifacts[0].content_digest == expected_digest
    assert (artifact_root / artifacts[0].artifact_path).read_bytes() == transport.body
    report = compile_research_report(
        report_id="RESEARCH-REPORT-001",
        plan=query_plan,
        artifact_root=artifact_root,
        artifacts=artifacts,
        controls=bound_controls(artifact_root, artifacts),
        findings=[
            ResearchFinding(
                schema_version="3.1",
                claim_id="CLAIM-001",
                verdict=ResearchVerdict.CLEAR,
                statement="The preregistered primary source supports the bounded claim.",
                source_artifact_digests=[expected_digest],
            )
        ],
    )
    assert report.overall_verdict is ResearchVerdict.CLEAR
    assert report.candidate_sha == SHA


@pytest.mark.parametrize("lane", [Lane.PRODUCT, Lane.TRUST, Lane.FACTORY])
def test_non_research_lanes_cannot_request_network(lane: Lane) -> None:
    with pytest.raises(ValidationError, match="limited to research lanes"):
        plan(lane=lane)


@pytest.mark.parametrize(
    "url",
    [
        "http://docs.example.test/fact.json",
        "https://user:secret@docs.example.test/fact.json",
        "https://docs.example.test/fact.json?api_key=TOPSECRET",
        "https://docs.example.test/fact.json?id=abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "https://127.0.0.1/fact.json",
        "https://docs.example.test:444/fact.json",
        "https://docs.example.test/fact.json#fragment",
    ],
)
def test_url_policy_rejects_broad_or_ambiguous_network_targets(url: str) -> None:
    with pytest.raises(ValidationError):
        plan(url=url)


def test_non_allowlisted_host_fails_before_transport(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    transport = FakeTransport(final_url="https://other.example.test/fact.json")
    query_plan = plan(url="https://other.example.test/fact.json")
    with pytest.raises(SourceAcquisitionError, match="not allowlisted"):
        _acquirer(
            policy=policy(),
            artifact_root=artifact_root,
            transport=transport,
            resolver=FakeResolver(),
        ).acquire(query_plan)
    assert transport.calls == []


def test_redirect_or_wrong_content_type_fails_closed(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    with pytest.raises(SourceAcquisitionError, match="not bound"):
        _acquirer(
            policy=policy(),
            artifact_root=artifact_root,
            transport=FakeTransport(final_url="https://docs.example.test/redirected.json"),
            resolver=FakeResolver(),
        ).acquire(plan())


def test_transport_cannot_bypass_status_or_byte_limits(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    with pytest.raises(SourceAcquisitionError, match="unexpected HTTP 500"):
        _acquirer(
            policy=policy(),
            artifact_root=artifact_root,
            transport=FakeTransport(status_code=500),
            resolver=FakeResolver(),
        ).acquire(plan())
    with pytest.raises(SourceAcquisitionError, match="byte limit"):
        _acquirer(
            policy=policy(),
            artifact_root=artifact_root,
            transport=FakeTransport(body=b"x" * 4097),
            resolver=FakeResolver(),
        ).acquire(plan())
    with pytest.raises(SourceAcquisitionError, match="content type"):
        _acquirer(
            policy=policy(),
            artifact_root=artifact_root,
            transport=FakeTransport(content_type="text/html"),
            resolver=FakeResolver(),
        ).acquire(plan())


def test_report_cannot_cite_unplanned_evidence_or_skip_controls(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    query_plan = plan()
    artifacts = _acquirer(
        policy=policy(),
        artifact_root=artifact_root,
        transport=FakeTransport(),
        resolver=FakeResolver(),
    ).acquire(query_plan)
    forged = "sha256:" + "f" * 64
    finding = ResearchFinding(
        schema_version="3.1",
        claim_id="CLAIM-001",
        verdict=ResearchVerdict.CLEAR,
        statement="forged",
        source_artifact_digests=[forged],
    )
    with pytest.raises(SourceAcquisitionError, match="not preregistered"):
        compile_research_report(
            report_id="RESEARCH-REPORT-001",
            plan=query_plan,
            artifact_root=artifact_root,
            artifacts=artifacts,
            controls=bound_controls(artifact_root, artifacts),
            findings=[finding],
        )
    with pytest.raises(ValidationError, match="at least 3 items"):
        compile_research_report(
            report_id="RESEARCH-REPORT-001",
            plan=query_plan,
            artifact_root=artifact_root,
            artifacts=artifacts,
            controls=bound_controls(artifact_root, artifacts)[:2],
            findings=[
                ResearchFinding(
                    schema_version="3.1",
                    claim_id="CLAIM-001",
                    verdict=ResearchVerdict.UNKNOWN,
                    statement="No attributable conclusion is available.",
                )
            ],
        )


def test_unknown_and_conflict_precedence_is_deterministic(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    query_plan = plan()
    artifacts = _acquirer(
        policy=policy(),
        artifact_root=artifact_root,
        transport=FakeTransport(),
        resolver=FakeResolver(),
    ).acquire(query_plan)
    digest = artifacts[0].content_digest
    report = compile_research_report(
        report_id="RESEARCH-REPORT-001",
        plan=query_plan,
        artifact_root=artifact_root,
        artifacts=artifacts,
        controls=bound_controls(artifact_root, artifacts),
        findings=[
            ResearchFinding(
                schema_version="3.1",
                claim_id="CLAIM-001",
                verdict=ResearchVerdict.CONFLICT,
                statement="Attributable sources conflict.",
                source_artifact_digests=[digest],
            )
        ],
    )
    assert report.overall_verdict is ResearchVerdict.CONFLICT


def test_report_reopens_raw_evidence_and_rejects_substitution(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    query_plan = plan()
    artifacts = _acquirer(
        policy=policy(),
        artifact_root=artifact_root,
        transport=FakeTransport(),
        resolver=FakeResolver(),
    ).acquire(query_plan)
    raw_path = artifact_root / artifacts[0].artifact_path
    raw_path.write_bytes(b"substituted")
    with pytest.raises(SourceAcquisitionError, match="digest does not match"):
        compile_research_report(
            report_id="RESEARCH-REPORT-001",
            plan=query_plan,
            artifact_root=artifact_root,
            artifacts=artifacts,
            controls=bound_controls(artifact_root, artifacts),
            findings=[
                ResearchFinding(
                    schema_version="3.1",
                    claim_id="CLAIM-001",
                    verdict=ResearchVerdict.CLEAR,
                    statement="Would otherwise have approved.",
                    source_artifact_digests=[artifacts[0].content_digest],
                )
            ],
        )


def test_symlink_artifact_root_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(SourceAcquisitionError, match="real pre-created directory"):
        _acquirer(
            policy=policy(),
            artifact_root=link,
            transport=FakeTransport(),
            resolver=FakeResolver(),
        ).acquire(plan())


def test_acquisition_receipt_is_complete_advisory_and_redirect_bound(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    redirected = "https://docs.example.test/final.json"
    artifacts = _acquirer(
        policy=policy(),
        artifact_root=artifact_root,
        transport=FakeTransport(final_url=redirected, redirect_chain=(redirected,)),
        resolver=FakeResolver(),
    ).acquire(plan())

    receipt = artifacts[0].retrieval_receipt
    assert receipt.requested_url == "https://docs.example.test/fact.json"
    assert receipt.final_url == redirected
    assert receipt.redirect_chain == [redirected]
    assert receipt.hop_receipts[-1].resolved_public_addresses == ["93.184.216.34"]
    assert receipt.query == "current fact"
    assert receipt.control_query == "known-negative current fact"
    assert receipt.parser_id == "JSON.CLAIM_RESULTS"
    assert receipt.issuer_id == AUTHORITY.issuer_id
    assert len(receipt.signature) == 64
    assert receipt.authority_effect == "ADVISORY_ONLY_NEVER_NORMATIVE"


def test_private_dns_and_rebinding_are_rejected_before_storage(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()

    class PrivateResolver:
        def resolve(self, hostname: str) -> tuple[str, ...]:
            del hostname
            return ("127.0.0.1",)

    with pytest.raises(SourceAcquisitionError, match="non-public address"):
        _acquirer(
            policy=policy(),
            artifact_root=artifact_root,
            transport=FakeTransport(),
            resolver=PrivateResolver(),
        ).acquire(plan())
    assert list(artifact_root.iterdir()) == []

    with pytest.raises(SourceAcquisitionError, match="DNS changed"):
        _acquirer(
            policy=policy(),
            artifact_root=artifact_root,
            transport=FakeTransport(resolved_addresses=("1.1.1.1",)),
            resolver=FakeResolver(),
        ).acquire(plan())
    with pytest.raises(SourceAcquisitionError, match="DNS changed"):
        _acquirer(
            policy=policy(),
            artifact_root=artifact_root,
            transport=FakeTransport(resolved_addresses=("93.184.216.34", "1.1.1.1")),
            resolver=FakeResolver(),
        ).acquire(plan())
    assert list(artifact_root.iterdir()) == []


@pytest.mark.parametrize(
    "url",
    [
        "http://docs.example.test/fact.json",
        "https://user:secret@docs.example.test/fact.json",
        "file:///etc/passwd",
    ],
)
def test_non_https_and_credential_sources_are_not_representable(url: str) -> None:
    with pytest.raises(ValidationError):
        plan(url=url)


def test_stale_tampered_and_parser_mismatch_resolve_to_typed_unknown(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    query_plan = plan()
    artifacts = _acquirer(
        policy=policy(),
        artifact_root=artifact_root,
        transport=FakeTransport(),
        resolver=FakeResolver(),
    ).acquire(query_plan)
    parser = {"SOURCE-001": ("JSON.CLAIM_RESULTS", "1.0.0")}

    stale = resolve_research_report(
        report_id="RESEARCH-REPORT-STALE",
        plan=query_plan,
        artifact_root=artifact_root,
        artifacts=artifacts,
        controls=controls(),
        expected_parsers=parser,
        parser_registry=PARSERS,
        control_oracle=CONTROL_ORACLE,
        receipt_authority=AUTHORITY,
        now=datetime.now(UTC) + timedelta(hours=2),
    )
    assert stale.verdict is ResearchVerdict.UNKNOWN
    assert stale.reason_codes == [ResearchResolutionReason.STALE_SOURCE]
    assert stale.report is None

    parser_mismatch = resolve_research_report(
        report_id="RESEARCH-REPORT-PARSER",
        plan=query_plan,
        artifact_root=artifact_root,
        artifacts=artifacts,
        controls=controls(),
        expected_parsers={"SOURCE-001": ("JSON.CLAIM_RESULTS", "2.0.0")},
        parser_registry=PARSERS,
        control_oracle=CONTROL_ORACLE,
        receipt_authority=AUTHORITY,
        now=datetime.now(UTC),
    )
    assert parser_mismatch.reason_codes == [ResearchResolutionReason.PARSER_MISMATCH]

    (artifact_root / artifacts[0].artifact_path).write_bytes(b"substituted")
    tampered = resolve_research_report(
        report_id="RESEARCH-REPORT-TAMPERED",
        plan=query_plan,
        artifact_root=artifact_root,
        artifacts=artifacts,
        controls=controls(),
        expected_parsers=parser,
        parser_registry=PARSERS,
        control_oracle=CONTROL_ORACLE,
        receipt_authority=AUTHORITY,
        now=datetime.now(UTC),
    )
    assert tampered.verdict is ResearchVerdict.UNKNOWN
    assert tampered.reason_codes == [ResearchResolutionReason.TAMPERED_SOURCE]


def test_conflicting_sources_resolve_to_typed_conflict(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    query_plan = plan()
    artifacts = _acquirer(
        policy=policy(),
        artifact_root=artifact_root,
        transport=FakeTransport(
            body=(
                b'{"claimResults":[{"claimId":"CLAIM-001",'
                b'"verdict":"CONFLICT","statement":"sources conflict"}]}'
            )
        ),
        resolver=FakeResolver(),
    ).acquire(query_plan)
    result = resolve_research_report(
        report_id="RESEARCH-REPORT-CONFLICT",
        plan=query_plan,
        artifact_root=artifact_root,
        artifacts=artifacts,
        controls=controls(),
        expected_parsers={"SOURCE-001": ("JSON.CLAIM_RESULTS", "1.0.0")},
        parser_registry=PARSERS,
        control_oracle=CONTROL_ORACLE,
        receipt_authority=AUTHORITY,
        now=datetime.now(UTC),
    )
    assert result.verdict is ResearchVerdict.CONFLICT
    assert result.reason_codes == [ResearchResolutionReason.SOURCE_CONFLICT]
    assert result.report is not None
    roster_digest = research_artifact_roster_digest(artifacts)
    assert {control.artifact_digest for control in result.report.controls} == {
        roster_digest
    }
    assert {control.raw_artifact_roster_digest for control in result.report.controls} == {
        roster_digest
    }
    assert not {
        "sha256:" + str(index) * 64 for index in range(1, 4)
    }.intersection(control.artifact_digest for control in result.report.controls)


def test_guarded_cas_swap_after_oracle_cannot_reach_validated_report(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir(mode=0o700)
    artifact_root.chmod(0o700)
    guard = TrustedServiceDirectory.capture(artifact_root, owner_uid=os.getuid())
    query_plan = plan()
    acquirer = _acquirer(
        policy=policy(),
        artifact_root=artifact_root,
        transport=FakeTransport(),
        resolver=FakeResolver(),
    )
    acquirer.artifact_root_opener = guard.open_fd
    artifacts = acquirer.acquire(query_plan)

    class SwapAfterOracle(InProcessResearchControlOracle):
        def evaluate(
            self,
            *,
            plan: ResearchQueryPlan,
            artifact_root: Path,
            artifacts: list[SourceArtifact],
            expected_controls: list[ResearchControl],
            artifact_root_opener: Callable[[], int] | None,
        ) -> list[ResearchControl]:
            computed = super().evaluate(
                plan=plan,
                artifact_root=artifact_root,
                artifacts=artifacts,
                expected_controls=expected_controls,
                artifact_root_opener=artifact_root_opener,
            )
            moved = artifact_root.with_name("raw-original")
            artifact_root.rename(moved)
            artifact_root.mkdir(mode=0o700)
            artifact_root.chmod(0o700)
            for artifact in artifacts:
                (artifact_root / artifact.artifact_path).write_bytes(
                    (moved / artifact.artifact_path).read_bytes()
                )
            return computed

    result = resolve_research_report(
        report_id="RESEARCH-REPORT-SWAPPED-CAS",
        plan=query_plan,
        artifact_root=artifact_root,
        artifacts=artifacts,
        controls=controls(),
        expected_parsers={"SOURCE-001": ("JSON.CLAIM_RESULTS", "1.0.0")},
        parser_registry=PARSERS,
        receipt_authority=AUTHORITY,
        control_oracle=SwapAfterOracle(),
        artifact_root_opener=guard.open_fd,
        now=datetime.now(UTC),
    )
    assert result.verdict is ResearchVerdict.UNKNOWN
    assert result.report is None


def test_control_oracle_cannot_change_preregistered_control_roster(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    query_plan = plan()
    artifacts = _acquirer(
        policy=policy(),
        artifact_root=artifact_root,
        transport=FakeTransport(),
        resolver=FakeResolver(),
    ).acquire(query_plan)

    class ForgedOracle(InProcessResearchControlOracle):
        def evaluate(
            self,
            *,
            plan: ResearchQueryPlan,
            artifact_root: Path,
            artifacts: list[SourceArtifact],
            expected_controls: list[ResearchControl],
            artifact_root_opener: Callable[[], int] | None,
        ) -> list[ResearchControl]:
            computed = super().evaluate(
                plan=plan,
                artifact_root=artifact_root,
                artifacts=artifacts,
                expected_controls=expected_controls,
                artifact_root_opener=artifact_root_opener,
            )
            return [
                computed[0].model_copy(update={"artifact_digest": "sha256:" + "f" * 64}),
                *computed[1:],
            ]

    result = resolve_research_report(
        report_id="RESEARCH-REPORT-FORGED-CONTROL",
        plan=query_plan,
        artifact_root=artifact_root,
        artifacts=artifacts,
        controls=controls(),
        expected_parsers={"SOURCE-001": ("JSON.CLAIM_RESULTS", "1.0.0")},
        parser_registry=PARSERS,
        control_oracle=ForgedOracle(),
        receipt_authority=AUTHORITY,
        now=datetime.now(UTC),
    )
    assert result.verdict is ResearchVerdict.UNKNOWN
    assert result.reason_codes == [ResearchResolutionReason.INVALID_RECEIPT]


def test_malformed_source_cannot_be_promoted_by_caller_authored_findings(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    query_plan = plan()
    artifacts = _acquirer(
        policy=policy(),
        artifact_root=artifact_root,
        transport=FakeTransport(body=b"not-json-at-all"),
        resolver=FakeResolver(),
    ).acquire(query_plan)
    result = resolve_research_report(
        report_id="RESEARCH-REPORT-MALFORMED",
        plan=query_plan,
        artifact_root=artifact_root,
        artifacts=artifacts,
        controls=controls(),
        expected_parsers={"SOURCE-001": ("JSON.CLAIM_RESULTS", "1.0.0")},
        parser_registry=PARSERS,
        control_oracle=CONTROL_ORACLE,
        receipt_authority=AUTHORITY,
        now=datetime.now(UTC),
    )
    assert result.verdict is ResearchVerdict.UNKNOWN
    assert result.reason_codes == [ResearchResolutionReason.PARSER_FAILURE]
    assert result.report is None


def test_parser_depth_limit_fails_to_typed_unknown(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    query_plan = plan()
    nested = b"[" * 30 + b"0" + b"]" * 30
    body = b'{"claimResults":' + nested + b"}"
    artifacts = _acquirer(
        policy=policy(),
        artifact_root=artifact_root,
        transport=FakeTransport(body=body),
        resolver=FakeResolver(),
    ).acquire(query_plan)
    result = resolve_research_report(
        report_id="RESEARCH-REPORT-DEPTH",
        plan=query_plan,
        artifact_root=artifact_root,
        artifacts=artifacts,
        controls=controls(),
        expected_parsers={"SOURCE-001": ("JSON.CLAIM_RESULTS", "1.0.0")},
        parser_registry=PARSERS,
        control_oracle=CONTROL_ORACLE,
        receipt_authority=AUTHORITY,
        now=datetime.now(UTC),
    )
    assert result.verdict is ResearchVerdict.UNKNOWN
    assert result.reason_codes == [ResearchResolutionReason.PARSER_FAILURE]


def test_receipt_signature_tamper_and_missing_authority_fail_closed(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    query_plan = plan()
    artifacts = _acquirer(
        policy=policy(),
        artifact_root=artifact_root,
        transport=FakeTransport(),
        resolver=FakeResolver(),
    ).acquire(query_plan)
    forged_receipt = artifacts[0].retrieval_receipt.model_copy(
        update={"fresh_until": artifacts[0].retrieval_receipt.fresh_until + timedelta(days=30)}
    )
    forged_artifact = artifacts[0].model_copy(update={"retrieval_receipt": forged_receipt})
    tampered = resolve_research_report(
        report_id="RESEARCH-REPORT-SIGNATURE",
        plan=query_plan,
        artifact_root=artifact_root,
        artifacts=[forged_artifact],
        controls=controls(),
        expected_parsers={"SOURCE-001": ("JSON.CLAIM_RESULTS", "1.0.0")},
        parser_registry=PARSERS,
        control_oracle=CONTROL_ORACLE,
        receipt_authority=AUTHORITY,
        now=datetime.now(UTC),
    )
    unavailable = resolve_research_report(
        report_id="RESEARCH-REPORT-SIGNATURE",
        plan=query_plan,
        artifact_root=artifact_root,
        artifacts=[forged_artifact],
        controls=controls(),
        expected_parsers={"SOURCE-001": ("JSON.CLAIM_RESULTS", "1.0.0")},
        parser_registry=PARSERS,
        control_oracle=CONTROL_ORACLE,
        receipt_authority=None,
        now=datetime.now(UTC),
    )
    assert tampered.reason_codes == [ResearchResolutionReason.INVALID_RECEIPT]
    assert unavailable.reason_codes == [ResearchResolutionReason.INVALID_RECEIPT]


def test_receipt_redacts_safe_query_values_but_binds_original_url(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    url = "https://docs.example.test/fact.json?page=2"
    artifact = _acquirer(
        policy=policy(),
        artifact_root=artifact_root,
        transport=FakeTransport(final_url=url),
        resolver=FakeResolver(),
    ).acquire(plan(url=url))[0]
    assert artifact.requested_url.endswith("?page=%3Credacted%3E")
    assert "=2" not in artifact.retrieval_receipt.requested_url
    assert artifact.retrieval_receipt.requested_url_digest == (
        f"sha256:{hashlib.sha256(url.encode()).hexdigest()}"
    )


def test_existing_fifo_cas_object_and_production_transport_injection_fail_closed(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    transport = FakeTransport()
    artifact_name = f"{hashlib.sha256(transport.body).hexdigest()}.raw"
    os.mkfifo(artifact_root / artifact_name)
    with pytest.raises(SourceAcquisitionError, match="bounded regular object"):
        _acquirer(
            policy=policy(),
            artifact_root=artifact_root,
            transport=transport,
            resolver=FakeResolver(),
        ).acquire(plan())
    with pytest.raises(SourceAcquisitionError, match="test-only"):
        ControlledSourceAcquirer(
            policy=policy(),
            artifact_root=artifact_root,
            transport=FakeTransport(),
            resolver=FakeResolver(),
            receipt_authority=AUTHORITY,
        )
