from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from tcfactory.v3.enums import Lane
from tcfactory.v3.source_acquisition import (
    ControlKind,
    ControlledSourceAcquirer,
    FetchedResponse,
    ResearchClaim,
    ResearchControl,
    ResearchFinding,
    ResearchQueryPlan,
    ResearchSource,
    ResearchVerdict,
    SourceAcquisitionError,
    SourceAcquisitionPolicy,
    SourceClass,
    compile_research_report,
)

SHA = "a" * 40


class FakeTransport:
    def __init__(
        self,
        *,
        final_url: str = "https://docs.example.test/fact.json",
        content_type: str = "application/json",
        body: bytes = b'{"fact":"bounded"}\n',
        status_code: int = 200,
    ) -> None:
        self.final_url = final_url
        self.content_type = content_type
        self.body = body
        self.status_code = status_code
        self.calls: list[str] = []

    def fetch(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_response_bytes: int,
        user_agent: str,
    ) -> FetchedResponse:
        self.calls.append(url)
        assert timeout_seconds == 5
        assert max_response_bytes == 4096
        assert user_agent == "TrainCapsule controlled research/3.1"
        return FetchedResponse(
            final_url=self.final_url,
            status_code=self.status_code,
            content_type=self.content_type,
            headers=(("content-type", self.content_type),),
            body=self.body,
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
            expected_verdict=verdict,
            observed_verdict=verdict,
        )
        for index, (kind, verdict) in enumerate(outcomes.items(), start=1)
    ]


def test_acquires_only_preregistered_bytes_and_compiles_bound_report(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    transport = FakeTransport()
    query_plan = plan()
    artifacts = ControlledSourceAcquirer(
        policy=policy(), artifact_root=artifact_root, transport=transport
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
        controls=controls(),
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
        ControlledSourceAcquirer(
            policy=policy(), artifact_root=artifact_root, transport=transport
        ).acquire(query_plan)
    assert transport.calls == []


def test_redirect_or_wrong_content_type_fails_closed(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    with pytest.raises(SourceAcquisitionError, match="does not match"):
        ControlledSourceAcquirer(
            policy=policy(),
            artifact_root=artifact_root,
            transport=FakeTransport(final_url="https://docs.example.test/redirected.json"),
        ).acquire(plan())


def test_transport_cannot_bypass_status_or_byte_limits(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    with pytest.raises(SourceAcquisitionError, match="unexpected HTTP 500"):
        ControlledSourceAcquirer(
            policy=policy(),
            artifact_root=artifact_root,
            transport=FakeTransport(status_code=500),
        ).acquire(plan())
    with pytest.raises(SourceAcquisitionError, match="byte limit"):
        ControlledSourceAcquirer(
            policy=policy(),
            artifact_root=artifact_root,
            transport=FakeTransport(body=b"x" * 4097),
        ).acquire(plan())
    with pytest.raises(SourceAcquisitionError, match="content type"):
        ControlledSourceAcquirer(
            policy=policy(),
            artifact_root=artifact_root,
            transport=FakeTransport(content_type="text/html"),
        ).acquire(plan())


def test_report_cannot_cite_unplanned_evidence_or_skip_controls(tmp_path: Path) -> None:
    artifact_root = tmp_path / "raw"
    artifact_root.mkdir()
    query_plan = plan()
    artifacts = ControlledSourceAcquirer(
        policy=policy(), artifact_root=artifact_root, transport=FakeTransport()
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
            controls=controls(),
            findings=[finding],
        )
    with pytest.raises(ValidationError, match="at least 3 items"):
        compile_research_report(
            report_id="RESEARCH-REPORT-001",
            plan=query_plan,
            artifact_root=artifact_root,
            artifacts=artifacts,
            controls=controls()[:2],
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
    artifacts = ControlledSourceAcquirer(
        policy=policy(), artifact_root=artifact_root, transport=FakeTransport()
    ).acquire(query_plan)
    digest = artifacts[0].content_digest
    report = compile_research_report(
        report_id="RESEARCH-REPORT-001",
        plan=query_plan,
        artifact_root=artifact_root,
        artifacts=artifacts,
        controls=controls(),
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
    artifacts = ControlledSourceAcquirer(
        policy=policy(), artifact_root=artifact_root, transport=FakeTransport()
    ).acquire(query_plan)
    raw_path = artifact_root / artifacts[0].artifact_path
    raw_path.write_bytes(b"substituted")
    with pytest.raises(SourceAcquisitionError, match="digest does not match"):
        compile_research_report(
            report_id="RESEARCH-REPORT-001",
            plan=query_plan,
            artifact_root=artifact_root,
            artifacts=artifacts,
            controls=controls(),
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
        ControlledSourceAcquirer(
            policy=policy(), artifact_root=link, transport=FakeTransport()
        ).acquire(plan())
