"""Typed, deterministic V2-to-V3 migration mapping records."""

from __future__ import annotations

from pydantic import Field, model_validator

from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import Disposition, Lane, WorkStatus


class LegacyMapRecord(V3Model):
    legacy_task_id: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,63}$")
    work_item_id: str | None = Field(default=None, pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    lane: Lane
    status: WorkStatus
    disposition: Disposition
    rationale: str = Field(min_length=1)
    preserved_evidence_refs: list[str]


class LegacyMigrationMap(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    source_version: int = Field(default=2, ge=2, le=2)
    records: list[LegacyMapRecord]

    @model_validator(mode="after")
    def unique_mapping(self) -> LegacyMigrationMap:
        legacy_ids = [record.legacy_task_id for record in self.records]
        if len(legacy_ids) != len(set(legacy_ids)):
            raise ValueError("legacy task IDs must be unique")
        v3_ids = [record.work_item_id for record in self.records if record.work_item_id]
        if len(v3_ids) != len(set(v3_ids)):
            raise ValueError("mapped V3 work item IDs must be unique")
        return self
