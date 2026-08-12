"""Strict, generation-scoped V3.1 source authority validation."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import Field, model_validator

from tcfactory.util import read_json, resolve_within, sha256_file, write_json
from tcfactory.v3.base import V3Model, sha256_digest
from tcfactory.yamlutil import load_yaml

ACTIVE_GENERATION_CONFIG = Path("config/active_generation.yaml")


class ActiveGenerationConfig(V3Model):
    schema_version: Literal["3.1"]
    schema_id: Literal["traincapsule.active-generation/v3.1-zh"]
    generation_id: Literal["traincapsule-v3.1-zh-2026-08-12"]
    source_root: Literal["docs/source-of-truth/v3.1-zh-2026-08-12"]
    manifest_path: Literal[
        "docs/source-of-truth/v3.1-zh-2026-08-12/FINAL_MANIFEST_V3_1_ZH.json"
    ]
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generator_path: Literal["scripts/generate_v3_1_zh_source.py"]
    generator_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    deterministic_derivation_check_required: Literal[True]
    supersedes_generation_id: Literal["traincapsule-v3-2026-08-11"]
    mixed_normative_generation_policy: Literal["REJECT"]


class SourceManifestSection(V3Model):
    heading: str = Field(min_length=1)
    level: int = Field(ge=1, le=6)
    section_id: str = Field(min_length=1)


class SourceManifestDocument(V3Model):
    logical_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_class: str = Field(min_length=1)
    sections: list[SourceManifestSection] = Field(min_length=1)
    generation_id: str = Field(min_length=1)
    derived_from: str = Field(min_length=1)
    required: Literal[True]


class SourceManifestIntegrity(V3Model):
    algorithm: Literal["sha256"]
    document_count: int = Field(ge=1, le=64)
    generator_path: Literal["scripts/generate_v3_1_zh_source.py"]
    manifest_self_included: Literal[False]


class SourceCoverageEvidence(V3Model):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_heading_count: int = Field(ge=1)
    mapped_heading_count: int = Field(ge=1)

    @model_validator(mode="after")
    def require_complete_mapping(self) -> SourceCoverageEvidence:
        if self.mapped_heading_count != self.source_heading_count:
            raise ValueError("source-generation heading coverage is incomplete")
        return self


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _headings(path: Path) -> list[tuple[str, int]]:
    return [
        (match.group(2), line_number)
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if (match := _HEADING.match(line)) is not None
    ]


def _validate_coverage(repo_root: Path, path: Path, generation_id: str) -> tuple[int, int]:
    try:
        payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceAuthorityError("source coverage evidence is unreadable") from exc
    if payload.get("schemaVersion") != 1 or payload.get("generationId") != generation_id:
        raise SourceAuthorityError("source coverage evidence generation mismatch")
    records = payload.get("documents")
    if not isinstance(records, list) or not records:
        raise SourceAuthorityError("source coverage evidence has no documents")
    observed_source = 0
    observed_mapped = 0
    for raw in cast(list[object], records):
        if not isinstance(raw, dict):
            raise SourceAuthorityError("source coverage document is invalid")
        record = cast(dict[str, Any], raw)
        source = resolve_within(repo_root, str(record.get("sourcePath", "")), require_exists=True)
        target = resolve_within(repo_root, str(record.get("targetPath", "")), require_exists=True)
        if sha256_file(source) != record.get("sourceSha256") or (
            sha256_file(target) != record.get("targetSha256")
        ):
            raise SourceAuthorityError("source coverage document digest mismatch")
        source_headings = _headings(source)
        target_headings = _headings(target)
        mappings = record.get("mappings")
        if not isinstance(mappings, list):
            raise SourceAuthorityError("source coverage mappings are invalid")
        mapped = cast(list[object], mappings)
        if len(source_headings) != len(mapped):
            raise SourceAuthorityError("source coverage mapping count is incomplete")
        expected_source = [(heading, line) for heading, line in source_headings]
        actual_source: list[tuple[str, int]] = []
        target_cursor = 0
        for raw_mapping in mapped:
            if not isinstance(raw_mapping, dict):
                raise SourceAuthorityError("source coverage mapping is invalid")
            mapping = cast(dict[str, Any], raw_mapping)
            if mapping.get("disposition") not in {"PRESERVED", "SUPERSEDED_POLICY"}:
                raise SourceAuthorityError("source coverage disposition is invalid")
            actual_source.append(
                (str(mapping.get("sourceHeading", "")), int(mapping.get("sourceLine", 0)))
            )
            target_pair = (
                str(mapping.get("targetHeading", "")),
                int(mapping.get("targetLine", 0)),
            )
            try:
                target_index = target_headings.index(target_pair, target_cursor)
            except ValueError as exc:
                raise SourceAuthorityError(
                    "source coverage target heading is missing or out of order"
                ) from exc
            target_cursor = target_index + 1
        if actual_source != expected_source:
            raise SourceAuthorityError("source coverage source headings are not exact")
        if record.get("sourceHeadingCount") != len(source_headings) or (
            record.get("mappedHeadingCount") != len(mapped)
        ):
            raise SourceAuthorityError("source coverage document counts are self-inconsistent")
        observed_source += len(source_headings)
        observed_mapped += len(mapped)
    totals = payload.get("totals")
    if not isinstance(totals, dict) or totals != {
        "sourceHeadingCount": observed_source,
        "mappedHeadingCount": observed_mapped,
    }:
        raise SourceAuthorityError("source coverage totals are self-inconsistent")
    return observed_source, observed_mapped


class SourceGenerationManifest(V3Model):
    schema_version: Literal[1]
    generation_id: str = Field(min_length=1)
    generated_at: datetime
    authority_model: dict[str, Any]
    supersession: dict[str, Any]
    documents: list[SourceManifestDocument] = Field(min_length=1, max_length=64)
    coverage_evidence: SourceCoverageEvidence
    integrity: SourceManifestIntegrity

    @model_validator(mode="after")
    def validate_document_identity(self) -> SourceGenerationManifest:
        paths = [document.path for document in self.documents]
        logical_ids = [document.logical_id for document in self.documents]
        if len(set(paths)) != len(paths) or len(set(logical_ids)) != len(logical_ids):
            raise ValueError("source manifest document paths and logical IDs must be unique")
        if self.integrity.document_count != len(self.documents):
            raise ValueError("source manifest document count is stale")
        return self


class ActiveSourceGeneration(V3Model):
    schema_version: Literal["3.1"] = "3.1"
    generation_id: str
    config_path: str
    config_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_root: str
    manifest_path: str
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    normative_documents: list[str] = Field(min_length=1)


class StaleSourceProposal(V3Model):
    version: Literal[3] = 3
    schema_id: Literal["traincapsule.source-wedge-proposal/v3.1-zh"] = (
        "traincapsule.source-wedge-proposal/v3.1-zh"
    )
    proposal_id: str = Field(pattern=r"^SOURCE-WEDGE-[0-9a-f]{16}$")
    work_item_id: str = Field(min_length=1, max_length=128)
    group: str = Field(min_length=1, max_length=128)
    freshness_status: Literal["STALE", "RECHECK_REQUIRED"]
    disposition: Literal["WAITING_EXTERNAL"] = "WAITING_EXTERNAL"
    proposed_actions: tuple[
        Literal["REFRESH_CURRENT_FACT_RECEIPT"],
        Literal["OPEN_ADR_WEDGE_REVIEW_IF_NORMATIVE_DECISION_CHANGES"],
    ] = (
        "REFRESH_CURRENT_FACT_RECEIPT",
        "OPEN_ADR_WEDGE_REVIEW_IF_NORMATIVE_DECISION_CHANGES",
    )
    max_review_rounds: Literal[2] = 2
    normative_source_mutated: Literal[False] = False
    created_at: datetime


class SourceAuthorityError(RuntimeError):
    """Raised when active source authority is missing, mixed, or tampered."""


def _context_source_paths(
    repo_root: Path,
    *,
    expected_root: str,
    document_headings: dict[str, set[str]],
) -> set[str]:
    index = load_yaml(repo_root / "docs/CONTEXT_INDEX.yaml")
    if index.get("activeBundle") != expected_root:
        raise SourceAuthorityError("context index active bundle differs from active generation")
    groups = index.get("groups")
    if not isinstance(groups, dict):
        raise SourceAuthorityError("context index has no typed groups")
    paths: set[str] = set()
    for raw_group in cast(dict[str, object], groups).values():
        if not isinstance(raw_group, dict):
            raise SourceAuthorityError("context index contains an invalid group")
        group = cast(dict[str, object], raw_group)
        entries = group.get("entries", [])
        if not isinstance(entries, list):
            raise SourceAuthorityError("context index contains invalid entries")
        for raw_entry in cast(list[object], entries):
            if not isinstance(raw_entry, dict):
                raise SourceAuthorityError("context index contains an invalid entry")
            entry = cast(dict[str, object], raw_entry)
            path = str(entry.get("path", ""))
            if path.startswith("docs/source-of-truth/"):
                paths.add(path)
                raw_sections = entry.get("authoritySections")
                if not isinstance(raw_sections, list) or not raw_sections:
                    raise SourceAuthorityError(
                        f"context entry has no exact authority sections: {path}"
                    )
                available = document_headings.get(path)
                if available is None:
                    raise SourceAuthorityError(
                        f"context entry is not an active source document: {path}"
                    )
                for raw_section in cast(list[object], raw_sections):
                    if not isinstance(raw_section, str) or not raw_section.startswith("§"):
                        raise SourceAuthorityError(
                            f"context authority section is malformed for {path}"
                        )
                    heading = raw_section.removeprefix("§").strip()
                    if not heading or heading not in available:
                        raise SourceAuthorityError(
                            f"context authority section is not an exact heading in {path}: "
                            f"{raw_section}"
                        )
    return paths


def validate_active_source_generation(repo_root: Path) -> ActiveSourceGeneration:
    """Validate the one active generation pointer, manifest, documents, and context."""

    root = repo_root.resolve()
    declared_config_path = root / ACTIVE_GENERATION_CONFIG
    if declared_config_path.is_symlink():
        raise SourceAuthorityError("active generation pointer must not be a symlink")
    config_path = resolve_within(root, ACTIVE_GENERATION_CONFIG, require_exists=True)
    config = ActiveGenerationConfig.model_validate(load_yaml(config_path))
    declared_generator_path = root / config.generator_path
    if declared_generator_path.is_symlink():
        raise SourceAuthorityError("active source generator must not be a symlink")
    generator_path = resolve_within(root, config.generator_path, require_exists=True)
    if not generator_path.is_file() or sha256_file(generator_path) != config.generator_sha256:
        raise SourceAuthorityError("active source generator digest mismatch")
    completed = subprocess.run(
        [sys.executable, str(generator_path), "--check"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        suffix = detail[0] if detail else "unknown derivation failure"
        raise SourceAuthorityError(
            f"active source differs from deterministic historical derivation: {suffix}"
        )
    declared_source_root = root / config.source_root
    if declared_source_root.is_symlink():
        raise SourceAuthorityError("active source root must not be a symlink")
    source_root = resolve_within(root, config.source_root, require_exists=True)
    if not source_root.is_dir():
        raise SourceAuthorityError("active source root is not a directory")
    declared_manifest_path = root / config.manifest_path
    if declared_manifest_path.is_symlink():
        raise SourceAuthorityError("active source manifest must not be a symlink")
    manifest_path = resolve_within(root, config.manifest_path, require_exists=True)
    if manifest_path.parent != source_root:
        raise SourceAuthorityError("active manifest must be directly inside its source root")
    manifest_digest = sha256_file(manifest_path)
    if manifest_digest != config.manifest_sha256:
        raise SourceAuthorityError("active source manifest digest mismatch")
    manifest = SourceGenerationManifest.model_validate(read_json(manifest_path, {}))
    if manifest.generation_id != config.generation_id:
        raise SourceAuthorityError("active source manifest generation mismatch")

    document_paths: list[str] = []
    document_headings: dict[str, set[str]] = {}
    digest_payload: list[bytes] = []
    prefix = config.source_root.rstrip("/") + "/"
    for document in manifest.documents:
        if document.path == config.manifest_path:
            raise SourceAuthorityError("active manifest self-hash is forbidden")
        if document.generation_id != config.generation_id:
            raise SourceAuthorityError(f"mixed source generation in {document.path}")
        if not document.path.startswith(prefix):
            raise SourceAuthorityError(
                f"source document escaped active generation: {document.path}"
            )
        declared_path = root / document.path
        if declared_path.is_symlink():
            raise SourceAuthorityError(f"source document is a symlink: {document.path}")
        path = resolve_within(root, document.path, require_exists=True)
        if not path.is_file():
            raise SourceAuthorityError(f"source document is not a regular file: {document.path}")
        actual = sha256_file(path)
        if actual != document.sha256:
            raise SourceAuthorityError(f"source document digest mismatch: {document.path}")
        document_paths.append(document.path)
        document_headings[document.path] = {
            heading for heading, _line in _headings(path)
        }
        digest_payload.append(f"{document.path}\0{actual}\n".encode())

    declared = set(document_paths)
    coverage = manifest.coverage_evidence
    if not coverage.path.startswith(prefix):
        raise SourceAuthorityError("source coverage evidence escaped active generation")
    declared_coverage_path = root / coverage.path
    if declared_coverage_path.is_symlink():
        raise SourceAuthorityError("source coverage evidence must not be a symlink")
    coverage_path = resolve_within(root, coverage.path, require_exists=True)
    if not coverage_path.is_file() or sha256_file(coverage_path) != coverage.sha256:
        raise SourceAuthorityError("source coverage evidence digest mismatch")
    observed_source, observed_mapped = _validate_coverage(
        root, coverage_path, config.generation_id
    )
    if (observed_source, observed_mapped) != (
        coverage.source_heading_count,
        coverage.mapped_heading_count,
    ):
        raise SourceAuthorityError("manifest coverage counts do not match verified mappings")
    digest_payload.append(f"{coverage.path}\0{coverage.sha256}\n".encode())
    source_root_relative = Path(config.source_root)
    expected_members = {
        *(
            Path(relative).relative_to(source_root_relative).as_posix()
            for relative in declared
        ),
        Path(config.manifest_path).relative_to(source_root_relative).as_posix(),
        Path(coverage.path).relative_to(source_root_relative).as_posix(),
    }
    actual_members: set[str] = set()
    for descendant in source_root.rglob("*"):
        relative = descendant.relative_to(source_root).as_posix()
        if descendant.is_symlink():
            raise SourceAuthorityError(f"active source contains a symlink: {relative}")
        if descendant.is_dir():
            raise SourceAuthorityError(
                f"active source contains an undeclared directory: {relative}"
            )
        if not descendant.is_file():
            raise SourceAuthorityError(
                f"active source contains a non-regular descendant: {relative}"
            )
        actual_members.add(relative)
    if actual_members != expected_members:
        raise SourceAuthorityError(
            "active source membership mismatch: "
            f"missing={sorted(expected_members - actual_members)}, "
            f"undeclared={sorted(actual_members - expected_members)}"
        )

    for context_path in _context_source_paths(
        root,
        expected_root=config.source_root,
        document_headings=document_headings,
    ):
        if context_path not in declared:
            raise SourceAuthorityError(
                f"mixed or undeclared source generation in context: {context_path}"
            )

    return ActiveSourceGeneration(
        generation_id=config.generation_id,
        config_path=ACTIVE_GENERATION_CONFIG.as_posix(),
        config_digest=sha256_file(config_path),
        source_root=config.source_root,
        manifest_path=config.manifest_path,
        manifest_digest=manifest_digest,
        source_digest=sha256_digest(b"".join(sorted(digest_payload))),
        normative_documents=sorted(document_paths),
    )


def emit_stale_source_proposal(
    *,
    proposal_root: Path,
    work_item_id: str,
    group: str,
    freshness_status: Literal["STALE", "RECHECK_REQUIRED"],
    now: datetime | None = None,
) -> tuple[StaleSourceProposal, Path]:
    """Write one idempotent bounded proposal without touching normative source."""

    fingerprint = sha256_digest(f"{work_item_id}\0{group}\0{freshness_status}\n".encode())
    proposal = StaleSourceProposal(
        proposal_id=f"SOURCE-WEDGE-{fingerprint.removeprefix('sha256:')[:16]}",
        work_item_id=work_item_id,
        group=group,
        freshness_status=freshness_status,
        created_at=(now or datetime.now(UTC)).astimezone(UTC),
    )
    path = proposal_root / f"{proposal.proposal_id}.json"
    write_json(path, proposal.model_dump(mode="json", by_alias=True))
    return proposal, path
