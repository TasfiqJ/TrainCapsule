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
    evidence_refs: list[str] = Field(max_length=64)
    decided_by: OwnerType
    decided_at: datetime

    @model_validator(mode="after")
    def require_decision_evidence(self) -> DispositionRecord:
        if self.decided_at.utcoffset() is None:
            raise ValueError("disposition decision timestamp must include a timezone")
        if self.previous is self.decision:
            raise ValueError("disposition decision must change the previous state")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("disposition evidence references must be unique")
        if any(
            not reference.strip() or any(ord(char) < 32 for char in reference)
            for reference in self.evidence_refs
        ):
            raise ValueError(
                "disposition evidence references must be non-empty printable strings"
            )
        if self.decision in {Disposition.STOP, Disposition.REPLACE} and not self.evidence_refs:
            raise ValueError("stop and replace dispositions require evidence")
        return self


class DispositionLedger(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    records: list[DispositionRecord]

    @model_validator(mode="after")
    def validate_ledger_history(self) -> DispositionLedger:
        identifiers = [record.record_id for record in self.records]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("disposition record IDs must be unique")
        ordering = [(record.decided_at, record.record_id) for record in self.records]
        if ordering != sorted(ordering):
            raise ValueError("disposition records must be in chronological canonical order")
        last_decision: dict[str, Disposition] = {}
        for record in self.records:
            prior = last_decision.get(record.work_item_id)
            if prior is not None and record.previous is not prior:
                raise ValueError(
                    "disposition transition does not continue the prior decision for "
                    f"{record.work_item_id}"
                )
            last_decision[record.work_item_id] = record.decision
        return self
