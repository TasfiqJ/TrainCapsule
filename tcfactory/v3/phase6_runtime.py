"""Controller-only Phase 6 research and consequential-action adapters."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import suppress
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, cast

from pydantic import Field, ValidationError

from tcfactory.util import sha256_file, write_json
from tcfactory.v3.base import DIGEST_PATTERN, V3Model
from tcfactory.v3.enums import Lane, WorkKind
from tcfactory.v3.external_actions import (
    ExternalActionAdapter,
    ExternalActionOutcome,
    ExternalActionPolicyError,
    ExternalActionRequest,
    ExternalResponseConsumption,
)
from tcfactory.v3.external_evidence import ExternalEvidenceReceipt
from tcfactory.v3.market_artifacts import (
    DiscoveryInterviewGuide,
    MarketArtifactError,
    PilotQualificationRubric,
    ReachableAccountMap,
    bind_reachable_account_map,
)
from tcfactory.v3.service_storage import TrustedServiceDirectory
from tcfactory.v3.source_acquisition import (
    ControlledSourceAcquirer,
    ReceiptAuthority,
    ResearchControl,
    ResearchControlOracle,
    ResearchQueryPlan,
    ResearchReport,
    ResearchVerdict,
    SourceAcquisitionError,
    SourceParserRegistry,
    SourceRetrievalReceipt,
    resolve_research_report,
    source_receipt_signature_payload,
)
from tcfactory.v3.work_items import WorkItem

_MAX_RESEARCH_EVIDENCE_BYTES = 16 * 1024 * 1024


def _read_bound_file(path: Path, expected_digest: str) -> bytes:
    if not path.is_absolute() or path.is_symlink():
        raise Phase6RuntimeError("research evidence path is not an absolute regular file")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise Phase6RuntimeError("research evidence file is unavailable") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_RESEARCH_EVIDENCE_BYTES:
            raise Phase6RuntimeError("research evidence file is unsafe or unbounded")
        chunks: list[bytes] = []
        remaining = _MAX_RESEARCH_EVIDENCE_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    if len(raw) > _MAX_RESEARCH_EVIDENCE_BYTES or _digest_bytes(raw) != expected_digest:
        raise Phase6RuntimeError("research evidence content digest mismatch")
    return raw


def _write_exclusive(path: Path, raw: bytes) -> None:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    except OSError as exc:
        raise Phase6RuntimeError("immutable research evidence publication failed") from exc
    try:
        offset = 0
        while offset < len(raw):
            offset += os.write(fd, raw[offset:])
        os.fsync(fd)
    finally:
        os.close(fd)


def _digest_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class Phase6RuntimeError(RuntimeError):
    """A Phase 6 controller-owned prerequisite is absent, stale, or invalid."""


def _write_guarded_json(
    guard: TrustedServiceDirectory, name: str, payload: object
) -> None:
    if "/" in name or "\\" in name or name in {".", ".."}:
        raise Phase6RuntimeError("guarded output name is invalid")
    raw = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        + b"\n"
    )
    root_fd = guard.open_fd()
    temporary = f".{name}.{os.getpid()}.tmp"
    try:
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=root_fd,
        )
        try:
            offset = 0
            while offset < len(raw):
                offset += os.write(fd, raw[offset:])
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
        os.fsync(root_fd)
    except OSError as exc:
        raise Phase6RuntimeError("guarded external outcome publication failed") from exc
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=root_fd)
        os.close(root_fd)


class ResearchOutputKind(StrEnum):
    REACHABLE_ACCOUNT_MAP = "REACHABLE_ACCOUNT_MAP"
    DISCOVERY_INTERVIEW_GUIDE = "DISCOVERY_INTERVIEW_GUIDE"
    PILOT_QUALIFICATION_RUBRIC = "PILOT_QUALIFICATION_RUBRIC"


class ResearchOutputDeclaration(V3Model):
    kind: ResearchOutputKind
    record_suffix: str = Field(pattern=r"^\.[a-z0-9-]+\.json$")
    record_digest: str = Field(pattern=DIGEST_PATTERN.pattern)


class AdvisoryArtifact(V3Model):
    source_id: str
    raw_cas_path: str
    raw_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    receipt_path: str
    receipt_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    authority_effect: Literal["ADVISORY_ONLY_NEVER_NORMATIVE"] = (
        "ADVISORY_ONLY_NEVER_NORMATIVE"
    )


class ResearchAdvisoryBundle(V3Model):
    work_item_id: str
    candidate_sha: str
    lane: Lane
    plan_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    report_path: str
    report_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    bundle_path: str
    artifacts: list[AdvisoryArtifact] = Field(min_length=1, max_length=64)
    typed_market_artifacts: dict[str, str] = Field(default_factory=dict, max_length=3)
    typed_market_artifact_paths: dict[str, str] = Field(default_factory=dict, max_length=3)
    network_policy: Literal["DENY"] = "DENY"
    authority_effect: Literal["ADVISORY_ONLY_NEVER_NORMATIVE"] = (
        "ADVISORY_ONLY_NEVER_NORMATIVE"
    )

    def agent_context(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True)


def _trusted_controller_json(
    root: Path,
    work_item_id: str,
    suffix: str,
    *,
    expected_owner_uid: int,
) -> tuple[Path, object]:
    name = f"{work_item_id}{suffix}"
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise Phase6RuntimeError("controller-owned Phase 6 root is unavailable") from exc
    try:
        root_metadata = os.fstat(root_fd)
        if root_metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise Phase6RuntimeError("controller-owned Phase 6 root is writable by others")
        if root_metadata.st_uid != expected_owner_uid:
            raise Phase6RuntimeError("controller-owned Phase 6 root has the wrong owner")
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
        except OSError as exc:
            raise Phase6RuntimeError("controller-owned Phase 6 record is unavailable") from exc
        try:
            metadata = os.fstat(fd)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
                or metadata.st_size > 2_000_000
            ):
                raise Phase6RuntimeError("controller-owned Phase 6 record is unsafe")
            if metadata.st_uid != expected_owner_uid:
                raise Phase6RuntimeError("controller-owned Phase 6 record has the wrong owner")
            chunks: list[bytes] = []
            remaining = metadata.st_size
            while remaining > 0:
                chunk = os.read(fd, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) != metadata.st_size:
                raise Phase6RuntimeError("controller-owned Phase 6 record changed while reading")
            if len(raw) > 2_000_000:
                raise Phase6RuntimeError("controller-owned Phase 6 record is unbounded")
        finally:
            os.close(fd)
    finally:
        os.close(root_fd)
    try:
        return root / name, json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Phase6RuntimeError("controller-owned Phase 6 record is invalid JSON") from exc


class Phase6ControllerRuntime:
    """Narrow live-controller bridge; agents never receive transport or send authority."""

    def __init__(
        self,
        *,
        research_plan_root: Path,
        research_acquirer: ControlledSourceAcquirer | None,
        parser_registry: SourceParserRegistry | None,
        source_receipt_authority: ReceiptAuthority | None,
        research_control_oracle: ResearchControlOracle | None = None,
        external_request_root: Path,
        external_action_adapter: ExternalActionAdapter | None,
        external_outcome_root: Path,
        external_outcome_guard: TrustedServiceDirectory | None = None,
        research_output_declarations: dict[
            str, tuple[ResearchOutputDeclaration, ...]
        ] | None = None,
        external_action_item_ids: frozenset[str] = frozenset(),
        trusted_input_owner_uid: int | None = None,
    ) -> None:
        self.research_plan_root = research_plan_root.absolute()
        self.research_acquirer = research_acquirer
        self.parser_registry = parser_registry
        self.source_receipt_authority = source_receipt_authority
        self.research_control_oracle = research_control_oracle
        self.external_request_root = external_request_root.absolute()
        self.external_action_adapter = external_action_adapter
        self.external_outcome_root = external_outcome_root.resolve()
        self.external_outcome_guard = external_outcome_guard
        self.research_output_declarations = research_output_declarations or {}
        self.external_action_item_ids = external_action_item_ids
        self.trusted_input_owner_uid = (
            os.geteuid()
            if trusted_input_owner_uid is None and hasattr(os, "geteuid")
            else 0
            if trusted_input_owner_uid is None
            else trusted_input_owner_uid
        )

    @classmethod
    def unavailable(cls) -> Phase6ControllerRuntime:
        """Return an inert item-scoped runtime when the external install is absent."""

        unavailable = Path("/nonexistent/traincapsule-phase6")
        return cls(
            research_plan_root=unavailable,
            research_acquirer=None,
            parser_registry=None,
            source_receipt_authority=None,
            research_control_oracle=None,
            external_request_root=unavailable,
            external_action_adapter=None,
            external_outcome_root=unavailable,
        )

    def handles_external_action(self, item: WorkItem) -> bool:
        return item.work_item_id in self.external_action_item_ids

    def prepare_research_advisory(
        self,
        *,
        item: WorkItem,
        candidate_sha: str,
        artifact_root: Path,
        now: datetime,
    ) -> ResearchAdvisoryBundle:
        if item.kind is not WorkKind.RESEARCH or item.lane not in {
            Lane.MARKET,
            Lane.COMPETITOR,
        }:
            raise Phase6RuntimeError(
                "controlled source acquisition is not authorized for this item"
            )
        if self.research_acquirer is None:
            raise Phase6RuntimeError("controlled source acquirer is unavailable")
        if self.parser_registry is None or self.source_receipt_authority is None:
            raise Phase6RuntimeError("trusted research parser or receipt authority is unavailable")
        plan_path, raw_plan = _trusted_controller_json(
            self.research_plan_root,
            item.work_item_id,
            ".json",
            expected_owner_uid=self.trusted_input_owner_uid,
        )
        controls_path, raw_controls = _trusted_controller_json(
            self.research_plan_root,
            item.work_item_id,
            ".controls.json",
            expected_owner_uid=self.trusted_input_owner_uid,
        )
        del plan_path, controls_path
        try:
            plan = ResearchQueryPlan.model_validate(raw_plan, strict=False)
            if not isinstance(raw_controls, list):
                raise Phase6RuntimeError("research controls are not a list")
            controls: list[ResearchControl] = []
            for raw_value in cast(list[object], raw_controls):
                if not isinstance(raw_value, dict):
                    raise Phase6RuntimeError("research control expectation is invalid")
                value = cast(dict[str, object], raw_value)
                if "observedVerdict" in value or "observed_verdict" in value:
                    raise Phase6RuntimeError(
                        "installed research controls may not assert observed verdicts"
                    )
                expected = value.get("expectedVerdict", value.get("expected_verdict"))
                controls.append(
                    ResearchControl.model_validate(
                        {**value, "observedVerdict": expected}, strict=False
                    )
                )
        except (ValidationError, ValueError, TypeError) as exc:
            raise Phase6RuntimeError("preregistered research plan or controls are invalid") from exc
        if (
            plan.work_item_id != item.work_item_id
            or plan.lane is not item.lane
            or plan.candidate_sha != candidate_sha
        ):
            raise Phase6RuntimeError("preregistered research plan identity mismatch")
        try:
            artifacts = self.research_acquirer.acquire(plan)
            resolution = resolve_research_report(
                report_id=f"RESEARCH-{item.work_item_id}-{candidate_sha[:12].upper()}",
                plan=plan,
                artifact_root=self.research_acquirer.artifact_root,
                artifacts=artifacts,
                controls=controls,
                expected_parsers={
                    source.source_id: (source.parser_id, source.parser_version)
                    for source in plan.sources
                },
                parser_registry=self.parser_registry,
                receipt_authority=self.source_receipt_authority,
                now=now,
                control_oracle=self.research_control_oracle,
                artifact_root_opener=self.research_acquirer.open_artifact_root,
            )
        except (OSError, SourceAcquisitionError) as exc:
            raise Phase6RuntimeError("controlled research retrieval failed") from exc
        if resolution.report is None or resolution.verdict is ResearchVerdict.UNKNOWN:
            raise Phase6RuntimeError(
                "controlled research evidence is unavailable: "
                + ",".join(reason.value for reason in resolution.reason_codes)
            )
        artifact_root.mkdir(parents=True, exist_ok=True)
        report_path = artifact_root / "research-report.json"
        write_json(report_path, resolution.report.model_dump(mode="json", by_alias=True))
        advisory_artifacts: list[AdvisoryArtifact] = []
        for index, artifact in enumerate(resolution.report.artifacts, start=1):
            receipt_path = artifact_root / f"source-receipt-{index:02d}.json"
            write_json(
                receipt_path,
                artifact.retrieval_receipt.model_dump(mode="json", by_alias=True),
            )
            raw_path = self.research_acquirer.artifact_root / artifact.artifact_path
            try:
                raw_bytes = self.research_acquirer.read_artifact(artifact.artifact_path)
            except SourceAcquisitionError as exc:
                raise Phase6RuntimeError("offline research CAS identity changed") from exc
            if _digest_bytes(raw_bytes) != artifact.content_digest:
                raise Phase6RuntimeError("offline research CAS digest mismatch")
            advisory_artifacts.append(
                AdvisoryArtifact(
                    source_id=artifact.source_id,
                    raw_cas_path=str(raw_path.resolve()),
                    raw_digest=artifact.content_digest,
                    receipt_path=str(receipt_path.resolve()),
                    receipt_digest=f"sha256:{sha256_file(receipt_path)}",
                )
            )
        bundle_path = artifact_root / "research-advisory-bundle.json"
        typed_market_artifacts: dict[str, str] = {}
        typed_market_artifact_paths: dict[str, str] = {}
        requested_market_artifacts = {
            ResearchOutputKind.REACHABLE_ACCOUNT_MAP: (
                "reachable-account-map",
                ReachableAccountMap,
            ),
            ResearchOutputKind.DISCOVERY_INTERVIEW_GUIDE: (
                "discovery-interview-guide",
                DiscoveryInterviewGuide,
            ),
            ResearchOutputKind.PILOT_QUALIFICATION_RUBRIC: (
                "pilot-qualification-rubric",
                PilotQualificationRubric,
            ),
        }
        declarations = self.research_output_declarations.get(item.work_item_id, ())
        for declaration in declarations:
            name, model = requested_market_artifacts[declaration.kind]
            path, raw_typed = _trusted_controller_json(
                self.research_plan_root,
                item.work_item_id,
                declaration.record_suffix,
                expected_owner_uid=self.trusted_input_owner_uid,
            )
            if f"sha256:{sha256_file(path)}" != declaration.record_digest:
                raise Phase6RuntimeError(f"typed market artifact {name} digest mismatch")
            try:
                typed = model.model_validate(raw_typed, strict=False)
            except ValidationError as exc:
                raise Phase6RuntimeError(f"typed market artifact {name} is invalid") from exc
            if isinstance(typed, ReachableAccountMap):
                try:
                    typed = bind_reachable_account_map(
                        map_id=typed.map_id,
                        report=resolution.report,
                        accounts=typed.accounts,
                    )
                except MarketArtifactError as exc:
                    raise Phase6RuntimeError(
                        "reachable account map evidence binding mismatch"
                    ) from exc
            typed_path = artifact_root / f"{name}.json"
            write_json(typed_path, typed.model_dump(mode="json", by_alias=True))
            typed_market_artifacts[name] = f"sha256:{sha256_file(typed_path)}"
            typed_market_artifact_paths[name] = str(typed_path.resolve())
        bundle = ResearchAdvisoryBundle(
            work_item_id=item.work_item_id,
            candidate_sha=candidate_sha,
            lane=item.lane,
            plan_digest=resolution.report.plan_digest,
            report_path=str(report_path.resolve()),
            report_digest=f"sha256:{sha256_file(report_path)}",
            bundle_path=str(bundle_path.resolve()),
            artifacts=advisory_artifacts,
            typed_market_artifacts=typed_market_artifacts,
            typed_market_artifact_paths=typed_market_artifact_paths,
        )
        write_json(bundle_path, bundle.model_dump(mode="json", by_alias=True))
        return bundle

    def materialize_research_advisory(
        self,
        bundle: ResearchAdvisoryBundle,
        *,
        evidence_root: Path,
    ) -> ResearchAdvisoryBundle:
        """Copy every verified advisory byte into one immutable candidate evidence root."""

        evidence_root.mkdir(parents=True, exist_ok=False)
        payloads = self.verify_research_advisory(bundle)
        report_path = evidence_root / "research-report.json"
        _write_exclusive(report_path, payloads["report"])
        artifacts: list[AdvisoryArtifact] = []
        for index, artifact in enumerate(bundle.artifacts, start=1):
            raw_path = evidence_root / f"source-{index:02d}.raw"
            receipt_path = evidence_root / f"source-receipt-{index:02d}.json"
            _write_exclusive(raw_path, payloads[f"raw:{artifact.source_id}"])
            _write_exclusive(receipt_path, payloads[f"receipt:{artifact.source_id}"])
            artifacts.append(
                AdvisoryArtifact(
                    source_id=artifact.source_id,
                    raw_cas_path=str(raw_path.resolve()),
                    raw_digest=artifact.raw_digest,
                    receipt_path=str(receipt_path.resolve()),
                    receipt_digest=artifact.receipt_digest,
                )
            )
        typed_paths: dict[str, str] = {}
        for name in sorted(bundle.typed_market_artifacts):
            path = evidence_root / f"{name}.json"
            _write_exclusive(path, payloads[f"typed:{name}"])
            typed_paths[name] = str(path.resolve())
        bundle_path = evidence_root / "research-advisory-bundle.json"
        materialized = bundle.model_copy(
            update={
                "report_path": str(report_path.resolve()),
                "bundle_path": str(bundle_path.resolve()),
                "artifacts": artifacts,
                "typed_market_artifact_paths": typed_paths,
            }
        )
        _write_exclusive(bundle_path, materialized.canonical_json_bytes() + b"\n")
        self.verify_research_advisory(materialized)
        return materialized

    def verify_research_advisory(
        self, bundle: ResearchAdvisoryBundle
    ) -> dict[str, bytes]:
        """Re-open and fully verify every advisory payload and signed source receipt."""

        if self.source_receipt_authority is None:
            raise Phase6RuntimeError("source receipt authority is unavailable")
        if set(bundle.typed_market_artifacts) != set(bundle.typed_market_artifact_paths):
            raise Phase6RuntimeError("typed market artifact paths and digests differ")
        report_bytes = _read_bound_file(Path(bundle.report_path), bundle.report_digest)
        try:
            report = ResearchReport.model_validate_json(report_bytes, strict=True)
        except ValidationError as exc:
            raise Phase6RuntimeError("materialized research report is invalid") from exc
        if (
            report.work_item_id != bundle.work_item_id
            or report.candidate_sha != bundle.candidate_sha
            or report.plan_digest != bundle.plan_digest
            or report.overall_verdict is ResearchVerdict.UNKNOWN
        ):
            raise Phase6RuntimeError("materialized research report identity mismatch")
        report_artifacts = {artifact.source_id: artifact for artifact in report.artifacts}
        if set(report_artifacts) != {artifact.source_id for artifact in bundle.artifacts}:
            raise Phase6RuntimeError("materialized research source roster mismatch")
        payloads = {"report": report_bytes}
        for artifact in bundle.artifacts:
            report_artifact = report_artifacts[artifact.source_id]
            raw_path = Path(artifact.raw_cas_path)
            if (
                self.research_acquirer is not None
                and raw_path.parent.resolve() == self.research_acquirer.artifact_root.resolve()
            ):
                try:
                    raw = self.research_acquirer.read_artifact(raw_path.name)
                except SourceAcquisitionError as exc:
                    raise Phase6RuntimeError("research CAS identity changed") from exc
                if _digest_bytes(raw) != artifact.raw_digest:
                    raise Phase6RuntimeError("research CAS content digest mismatch")
            else:
                raw = _read_bound_file(raw_path, artifact.raw_digest)
            receipt_bytes = _read_bound_file(Path(artifact.receipt_path), artifact.receipt_digest)
            try:
                receipt = SourceRetrievalReceipt.model_validate_json(receipt_bytes, strict=True)
            except ValidationError as exc:
                raise Phase6RuntimeError("materialized source receipt is invalid") from exc
            if (
                report_artifact.content_digest != artifact.raw_digest
                or report_artifact.retrieval_receipt != receipt
                or receipt.source_id != artifact.source_id
                or receipt.work_item_id != bundle.work_item_id
                or receipt.candidate_sha != bundle.candidate_sha
                or receipt.plan_digest != bundle.plan_digest
                or receipt.content_digest != artifact.raw_digest
                or not self.source_receipt_authority.verify(
                    source_receipt_signature_payload(receipt),
                    signature=receipt.signature,
                    issuer_id=receipt.issuer_id,
                    key_id=receipt.issuer_key_id,
                    signature_algorithm=receipt.signature_algorithm,
                )
            ):
                raise Phase6RuntimeError("materialized source receipt binding is invalid")
            payloads[f"raw:{artifact.source_id}"] = raw
            payloads[f"receipt:{artifact.source_id}"] = receipt_bytes
        typed_models = {
            "reachable-account-map": ReachableAccountMap,
            "discovery-interview-guide": DiscoveryInterviewGuide,
            "pilot-qualification-rubric": PilotQualificationRubric,
        }
        for name, digest in sorted(bundle.typed_market_artifacts.items()):
            if name not in typed_models:
                raise Phase6RuntimeError("unknown typed market artifact")
            raw = _read_bound_file(Path(bundle.typed_market_artifact_paths[name]), digest)
            try:
                typed_models[name].model_validate_json(raw, strict=True)
            except ValidationError as exc:
                raise Phase6RuntimeError(f"materialized typed artifact {name} is invalid") from exc
            payloads[f"typed:{name}"] = raw
        return payloads

    def execute_commercial_action(
        self, *, item: WorkItem, candidate_sha: str, now: datetime
    ) -> ExternalActionOutcome:
        if not self.handles_external_action(item):
            raise Phase6RuntimeError("external action is not authorized for this item")
        if self.external_action_adapter is None:
            raise Phase6RuntimeError("external action adapter is unavailable")
        request_path, raw_request = _trusted_controller_json(
            self.external_request_root,
            item.work_item_id,
            ".json",
            expected_owner_uid=self.trusted_input_owner_uid,
        )
        del request_path
        try:
            request = ExternalActionRequest.model_validate(raw_request, strict=False)
        except ValidationError as exc:
            raise Phase6RuntimeError("preregistered external action request is invalid") from exc
        if request.work_item_id != item.work_item_id or request.candidate_sha != candidate_sha:
            raise Phase6RuntimeError("preregistered external action request identity mismatch")
        try:
            outcome = self.external_action_adapter.execute(request, now=now)
        except ExternalActionPolicyError as exc:
            raise Phase6RuntimeError("external action policy rejected the exact request") from exc
        if self.external_outcome_guard is None:
            self.external_outcome_root.mkdir(parents=True, exist_ok=True)
            write_json(
                self.external_outcome_root / f"{item.work_item_id}.json",
                outcome.model_dump(mode="json", by_alias=True),
            )
        else:
            _write_guarded_json(
                self.external_outcome_guard,
                f"{item.work_item_id}.json",
                outcome.model_dump(mode="json", by_alias=True),
            )
        return outcome

    def reserve_external_response_consumption(
        self,
        *,
        outcome: ExternalActionOutcome,
        receipt: ExternalEvidenceReceipt,
    ) -> ExternalResponseConsumption:
        """Durably reserve the exact signed response before terminal advancement."""

        if self.external_action_adapter is None or self.external_action_adapter.journal is None:
            raise Phase6RuntimeError("external response journal is unavailable")
        binding = receipt.action_response_binding
        if binding is None:
            raise Phase6RuntimeError("external response binding is unavailable")
        try:
            return self.external_action_adapter.journal.reserve_response_consumption(
                outcome,
                response_receipt_id=receipt.receipt_id,
                response_nonce=binding.response_nonce,
                response_digest=_digest_bytes(receipt.canonical_json_bytes()),
            )
        except ExternalActionPolicyError as exc:
            raise Phase6RuntimeError("external response consumption was rejected") from exc

    def commit_external_response_consumption(
        self,
        *,
        outcome: ExternalActionOutcome,
        consumption: ExternalResponseConsumption,
    ) -> None:
        """Commit the journal after the controller's terminal queue transition."""

        if self.external_action_adapter is None or self.external_action_adapter.journal is None:
            raise Phase6RuntimeError("external response journal is unavailable")
        try:
            self.external_action_adapter.journal.commit_response_consumption(
                outcome, consumption
            )
        except ExternalActionPolicyError as exc:
            raise Phase6RuntimeError("external response consumption commit failed") from exc
