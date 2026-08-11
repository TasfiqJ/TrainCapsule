"""Bounded V3 task packets, compiler templates, and digest-bound packet reuse."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path, PurePosixPath

import yaml
from pydantic import Field, model_validator

from tcfactory.util import atomic_write_text
from tcfactory.v3.base import DIGEST_PATTERN, SHA_PATTERN, V3Model, sha256_digest
from tcfactory.v3.enums import Lane, RiskTier, WorkKind
from tcfactory.v3.work_items import WorkItem
from tcfactory.yamlutil import load_yaml

MAX_ACCEPTANCE_CRITERIA = 12
MAX_OUTPUTS = 8
MAX_SOURCE_DOCUMENTS = 8
MAX_PACKET_TEXT_CHARS = 24_000

_UNIVERSAL_CRITERION = re.compile(
    r"\b(?:all|every)\s+(?:company|product|roadmap|customer|commercial)\s+"
    r"(?:criterion|criteria|requirement|task|work|need)s?\b",
    re.IGNORECASE,
)
_GENERIC_CLAIM = re.compile(
    r"\b(?:production[- ]ready|enterprise[- ]ready|commercially (?:proven|validated)|"
    r"customer[- ]validated)\b",
    re.IGNORECASE,
)
_FACTORY_ROOTS = ("tcfactory/", "factory/", "config/", "prompts/", "scripts/")
_PRODUCT_ROOTS = ("packages/traincapsule-", "src/traincapsule", "tests/product/")


class PacketPolicyError(ValueError):
    """A proposed task packet violates a deterministic V3 boundary."""


class V3TaskPacket(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    title: str = Field(min_length=1)
    lane: Lane
    milestone: str = Field(pattern=r"^M[0-9]+_[A-Z0-9_]+$")
    kind: WorkKind
    risk_tier: RiskTier
    template: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    decision_contribution: str = Field(min_length=1)
    non_goals: list[str] = Field(min_length=1, max_length=8)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=MAX_ACCEPTANCE_CRITERIA)
    outputs: list[str] = Field(max_length=MAX_OUTPUTS)
    source_documents: list[str] = Field(min_length=1, max_length=MAX_SOURCE_DOCUMENTS)
    allowed_paths: list[str] = Field(min_length=1, max_length=16)
    forbidden_paths: list[str] = Field(default_factory=list[str], max_length=24)
    oracle: str = Field(min_length=1)
    rollback: str = Field(min_length=1)
    stop_conditions: list[str] = Field(min_length=1, max_length=8)
    stop_disposition: str = Field(min_length=1)
    work_item_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    source_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    context_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    compiler_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    base_sha: str = Field(pattern=SHA_PATTERN.pattern)
    approved_split_ref: str | None = None

    @model_validator(mode="after")
    def validate_packet_policy(self) -> V3TaskPacket:
        if len(self.acceptance_criteria) != len(set(self.acceptance_criteria)):
            raise PacketPolicyError("acceptance criteria must be unique")
        if len(self.outputs) != len(set(self.outputs)):
            raise PacketPolicyError("outputs must be unique")
        if len(self.source_documents) != len(set(self.source_documents)):
            raise PacketPolicyError("source documents must be unique")
        if any(_UNIVERSAL_CRITERION.search(value) for value in self.acceptance_criteria):
            raise PacketPolicyError("universal company/product criteria are forbidden")
        if any(_GENERIC_CLAIM.search(value) for value in self.acceptance_criteria):
            raise PacketPolicyError("generic production or commercial claims are forbidden")
        if self._contains_mixed_product_factory_scope():
            raise PacketPolicyError("one packet cannot mix product and factory mutations")
        invalid_outputs = [path for path in self.outputs if not self._is_allowed_output(path)]
        if invalid_outputs:
            raise PacketPolicyError(
                f"outputs are not writable by the owner stage: {sorted(invalid_outputs)}"
            )
        packet_text = "\n".join(
            [
                self.goal,
                self.decision_contribution,
                *self.non_goals,
                *self.acceptance_criteria,
                *self.stop_conditions,
            ]
        )
        if len(packet_text) > MAX_PACKET_TEXT_CHARS and not self.approved_split_ref:
            raise PacketPolicyError("oversized packet requires an approved split reference")
        return self

    def _contains_mixed_product_factory_scope(self) -> bool:
        paths = [*self.allowed_paths, *self.outputs]
        product = any(path.startswith(_PRODUCT_ROOTS) for path in paths)
        factory = any(path.startswith(_FACTORY_ROOTS) for path in paths)
        return product and factory

    def _is_allowed_output(self, raw: str) -> bool:
        normalized = PurePosixPath(raw).as_posix().lstrip("./")
        if normalized.startswith("../") or normalized.startswith("/"):
            return False
        for raw_pattern in self.allowed_paths:
            pattern = raw_pattern.lstrip("./")
            if fnmatch.fnmatch(normalized, pattern):
                return True
            if pattern.endswith("/**") and (
                normalized == pattern[:-3] or normalized.startswith(pattern[:-2])
            ):
                return True
        return False

    def cache_key(self) -> str:
        return sha256_digest(
            "\0".join(
                [
                    self.work_item_id,
                    self.work_item_digest,
                    self.source_digest,
                    self.context_digest,
                    self.compiler_digest,
                    self.base_sha,
                ]
            ).encode()
        )


TASK_TYPE_TEMPLATES: dict[WorkKind, str] = {
    WorkKind.CODE: "code-implementation-v3",
    WorkKind.SPECIFICATION: "bounded-specification-v3",
    WorkKind.RESEARCH: "attributable-research-v3",
    WorkKind.CONTROLLED_EXPERIMENT: "controlled-experiment-v3",
    WorkKind.EXTERNAL_EVIDENCE: "external-evidence-wait-v3",
    WorkKind.HUMAN_REVIEW: "human-review-wait-v3",
    WorkKind.COMMERCIAL_EXPERIMENT: "commercial-experiment-v3",
    WorkKind.MAINTENANCE: "factory-maintenance-v3",
    WorkKind.MIGRATION: "migration-v3",
}


def compile_work_item_packet(
    item: WorkItem,
    *,
    source_documents: list[str],
    allowed_paths: list[str],
    outputs: list[str],
    acceptance_criteria: list[str],
    non_goals: list[str],
    oracle: str,
    rollback: str,
    stop_conditions: list[str],
    stop_disposition: str,
    source_digest: str,
    context_digest: str,
    compiler_digest: str,
    base_sha: str,
) -> V3TaskPacket:
    """Compile one typed V3 work item without task-ID special cases."""

    if not item.automatable or item.kind in {
        WorkKind.EXTERNAL_EVIDENCE,
        WorkKind.HUMAN_REVIEW,
        WorkKind.COMMERCIAL_EXPERIMENT,
    }:
        raise PacketPolicyError(
            f"{item.work_item_id} requires external or human action; AI packet refused"
        )

    return V3TaskPacket(
        work_item_id=item.work_item_id,
        title=item.title,
        lane=item.lane,
        milestone=item.milestone,
        kind=item.kind,
        risk_tier=item.risk_tier,
        template=TASK_TYPE_TEMPLATES[item.kind],
        goal=f"Produce only the bounded outcome for {item.work_item_id}: {item.title}",
        decision_contribution=item.decision_contribution,
        non_goals=non_goals,
        acceptance_criteria=acceptance_criteria,
        outputs=outputs,
        source_documents=source_documents,
        allowed_paths=allowed_paths,
        oracle=oracle,
        rollback=rollback,
        stop_conditions=stop_conditions,
        stop_disposition=stop_disposition,
        work_item_digest=item.canonical_digest(),
        source_digest=source_digest,
        context_digest=context_digest,
        compiler_digest=compiler_digest,
        base_sha=base_sha,
    )


def load_cached_packet(path: Path, expected: V3TaskPacket) -> V3TaskPacket | None:
    """Reuse a valid packet only when every cache-binding digest still matches."""

    if not path.is_file():
        return None
    cached = V3TaskPacket.model_validate(load_yaml(path))
    if cached.cache_key() != expected.cache_key():
        return None
    return cached


def write_packet(path: Path, packet: V3TaskPacket) -> None:
    payload = packet.model_dump(mode="json", by_alias=True, exclude_none=True)
    atomic_write_text(path, yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
