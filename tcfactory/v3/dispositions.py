"""Auditable stop/narrow/replace/upstream disposition records."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import Disposition, OwnerType


class DispositionRecord(V3Model):
    record_id: str = Field(pattern=r"^DISP-[A-Z0-9_-]+$")
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    previous: Disposition
    decision: Disposition
    rationale: str = Field(min_length=1)
    evidence_refs: list[str]
    decided_by: OwnerType
    decided_at: datetime
    @model_validator(mode="after")
    def require_decision_evidence(self) -> DispositionRecord:
        if self.previous is self.decision:
            raise ValueError("disposition decision must change the previous state")
        if self.decision in {Disposition.STOP, Disposition.REPLACE} and not self.evidence_refs:
            raise ValueError("stop and replace dispositions require evidence")
        return self


class DispositionLedger(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    records: list[DispositionRecord]

    @model_validator(mode="after")
    def unique_records(self) -> DispositionLedger:
        identifiers = [record.record_id for record in self.records]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("disposition record IDs must be unique")
        return self
