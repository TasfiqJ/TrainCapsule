#!/usr/bin/env python3
"""Generate the typed V3 work-item ledger from the authoritative roadmap tables."""

from __future__ import annotations

# ruff: noqa: E402
import argparse
import re
import sys
from pathlib import Path
from typing import Final

import yaml

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tcfactory.v3.enums import (
    CommercialMaturity,
    Disposition,
    EngineeringMaturity,
    Lane,
    OwnerType,
    RiskTier,
    WorkKind,
    WorkStatus,
)
from tcfactory.v3.maturity import MaturityTarget
from tcfactory.v3.retry_policy import RetryPolicy
from tcfactory.v3.work_items import WorkItem, WorkItemCollection

SOURCE: Final = ROOT / (
    "docs/source-of-truth/v3-2026-08-11/"
    "12_GATE_BASED_ROADMAP_AND_BACKLOG_V3.md"
)
OUTPUT: Final = ROOT / "factory/roadmap/work_items.yaml"
ROW = re.compile(
    r"^\|\s*`(?P<id>V3-[A-Z]+-[0-9]{3})`\s*"
    r"\|\s*(?P<lane>[A-Z]+)\s*"
    r"\|\s*(?P<outcome>.*?)\s*"
    r"\|\s*(?P<depends>.*?)\s*"
    r"\|\s*(?P<evidence>.*?)\s*\|\s*$"
)
MILESTONE = re.compile(r"^## 12\.[3-9] M(?P<number>[0-6])\s+—")
MILESTONE_IDS: Final = {
    0: "M0_FACTORY_MIGRATED",
    1: "M1_NATIVE_PREFLIGHT",
    2: "M2_CONTROLLED_QUALIFICATION",
    3: "M3_PAID_PREFLIGHT",
    4: "M4_PAID_PILOT",
    5: "M5_PAID_REPEAT",
    6: "M6_COMMERCIALLY_SUPPORTED_PACK",
}
M0_ENGINEERING_STATE: Final = {
    f"V3-MIG-{number:03d}": WorkStatus.COMPLETED for number in range(1, 21)
}
M0_ACCEPTANCE_EVIDENCE: Final = {
    f"V3-MIG-{number:03d}": f"docs/migrations/evidence/V3-MIG-{number:03d}.json"
    for number in range(16, 21)
}
IMPLEMENTED_M1_ITEMS: Final = {
    "V3-PROD-001",
    "V3-PROD-002",
    "V3-TRUST-001",
    "V3-PROD-003",
    "V3-PROD-004",
    "V3-PROD-005",
    "V3-PROD-006",
    "V3-PROD-007",
    "V3-PROD-008",
    "V3-PROD-009",
    "V3-PROD-010",
    "V3-TRUST-002",
    "V3-TRUST-003",
}
OUTSIDE_FACT_WORK_ITEMS: Final = {
    # These outcomes assert that an event, customer fact, or access grant exists
    # outside the repository.  The factory may prepare surrounding material, but
    # it cannot create or self-attest the fact itself.
    "V3-MKT-003",
    "V3-MKT-004",
    "V3-MKT-005",
    "V3-MKT-006",
    "V3-MKT-007",
}


def _zero_human_text(value: str) -> str:
    """Apply the owner-directed machine-policy override to generated roadmap text."""

    replacements = (
        (r"founder/human", "machine-policy"),
        (r"human-approval", "machine-policy"),
        (r"qualified human", "independent machine-policy"),
        (r"human review", "machine-policy verification"),
        (r"human approve", "machine policy authorizes"),
        (r"signed source-migration approval", "digest-bound source-migration policy receipt"),
        (r"signed approval", "digest-bound machine-policy receipt"),
        (
            r"change release path from direct main to draft PR",
            "enforce exact-SHA main-only release",
        ),
        (r"PR dry run", "main-only publication recovery rehearsal"),
    )
    transformed = value
    for pattern, replacement in replacements:
        transformed = re.sub(pattern, replacement, transformed, flags=re.IGNORECASE)
    return transformed


class SourceRow:
    def __init__(
        self,
        *,
        work_item_id: str,
        lane: Lane,
        outcome: str,
        depends: str,
        evidence: str,
        milestone_number: int,
        milestone_position: int,
    ) -> None:
        self.work_item_id = work_item_id
        self.lane = lane
        self.outcome = _zero_human_text(outcome.replace("`", "").strip())
        self.depends = depends.replace("`", "").strip()
        self.evidence = _zero_human_text(evidence.replace("`", "").strip())
        self.milestone_number = milestone_number
        self.milestone_position = milestone_position


def _source_rows() -> list[SourceRow]:
    rows: list[SourceRow] = []
    milestone_number: int | None = None
    positions: dict[int, int] = {}
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        heading = MILESTONE.match(line)
        if heading:
            milestone_number = int(heading.group("number"))
            positions[milestone_number] = 0
            continue
        match = ROW.match(line)
        if not match:
            continue
        if milestone_number is None:
            raise ValueError("V3 roadmap work item appears before a milestone heading")
        positions[milestone_number] += 1
        rows.append(
            SourceRow(
                work_item_id=match.group("id"),
                lane=Lane(match.group("lane")),
                outcome=match.group("outcome"),
                depends=match.group("depends"),
                evidence=match.group("evidence"),
                milestone_number=milestone_number,
                milestone_position=positions[milestone_number],
            )
        )
    if len(rows) != 109:
        raise ValueError(f"expected 109 authoritative roadmap rows; found {len(rows)}")
    return rows


def _range_dependencies(
    start: int,
    end: int,
    row: SourceRow,
    rows: list[SourceRow],
) -> list[str]:
    milestone_rows = [item for item in rows if item.milestone_number == row.milestone_number]
    prefix = row.work_item_id.rsplit("-", 1)[0]
    same_prefix = [
        item.work_item_id
        for item in milestone_rows
        if item.work_item_id.startswith(prefix + "-")
        and start <= int(item.work_item_id.rsplit("-", 1)[1]) <= end
    ]
    if same_prefix:
        return same_prefix
    positional = [
        item.work_item_id
        for item in milestone_rows
        if start <= item.milestone_position <= end
    ]
    return positional


def _dependencies(row: SourceRow, rows: list[SourceRow]) -> list[str]:
    expression = row.depends
    if expression in {"", "—", "-"} or re.fullmatch(r"M[0-6]", expression):
        return []
    milestone_rows = [item for item in rows if item.milestone_number == row.milestone_number]
    if expression.lower().startswith("all m"):
        return [
            item.work_item_id
            for item in milestone_rows
            if item.work_item_id != row.work_item_id
            and item.milestone_position < row.milestone_position
        ]
    dependencies: list[str] = []
    consumed: list[tuple[int, int]] = []
    for match in re.finditer(r"(?<![A-Z0-9-])(\d{3})\s*[–-]\s*(\d{3})(?![0-9])", expression):
        dependencies.extend(
            _range_dependencies(int(match.group(1)), int(match.group(2)), row, rows)
        )
        consumed.append(match.span())
    remaining = "".join(
        " " if any(start <= index < end for start, end in consumed) else character
        for index, character in enumerate(expression)
    )
    explicit = re.findall(r"(?:V3-)?([A-Z]+)-(\d{3})", remaining)
    for item_prefix, number in explicit:
        dependencies.append(f"V3-{item_prefix}-{number}")
    remaining = re.sub(r"(?:V3-)?[A-Z]+-\d{3}", " ", remaining)
    current_prefix = row.work_item_id.rsplit("-", 1)[0]
    all_ids = {item.work_item_id for item in rows}
    for number in re.findall(r"(?<!\d)\d{3}(?!\d)", remaining):
        candidate = f"{current_prefix}-{number}"
        if candidate in all_ids:
            dependencies.append(candidate)
            continue
        positional = next(
            (
                item.work_item_id
                for item in milestone_rows
                if item.milestone_position == int(number)
            ),
            None,
        )
        if positional:
            dependencies.append(positional)
    unique = list(dict.fromkeys(dependencies))
    return [dependency for dependency in unique if dependency != row.work_item_id]


def _kind(row: SourceRow) -> WorkKind:
    lowered = row.outcome.lower()
    if row.work_item_id in OUTSIDE_FACT_WORK_ITEMS:
        return WorkKind.EXTERNAL_EVIDENCE
    if row.work_item_id.startswith("V3-MIG-"):
        if "machine-policy" in lowered or "machine policy" in lowered:
            return WorkKind.MACHINE_POLICY_REVIEW
        return WorkKind.MIGRATION
    if "machine policy" in lowered or "machine-policy" in lowered:
        return WorkKind.MACHINE_POLICY_REVIEW
    if row.work_item_id.startswith("V3-DEC-"):
        return WorkKind.MACHINE_POLICY_REVIEW
    if row.lane is Lane.MARKET:
        external_terms = (
            "record",
            "obtain",
            "conversation",
            "customer",
            "paid",
            "schedule",
            "offer",
        )
        if any(term in lowered for term in external_terms):
            return WorkKind.EXTERNAL_EVIDENCE
        return WorkKind.RESEARCH
    if row.lane is Lane.COMPETITOR:
        return (
            WorkKind.CONTROLLED_EXPERIMENT
            if any(term in lowered for term in ("benchmark", "baseline", "run"))
            else WorkKind.RESEARCH
        )
    if row.lane is Lane.FACTORY:
        return WorkKind.MAINTENANCE
    if row.lane is Lane.TRUST:
        return WorkKind.SPECIFICATION
    return WorkKind.CODE


def _risk(row: SourceRow, kind: WorkKind) -> RiskTier:
    if kind is WorkKind.EXTERNAL_EVIDENCE:
        return RiskTier.EXTERNAL
    if kind is WorkKind.MACHINE_POLICY_REVIEW:
        return RiskTier.TRUST_CORE
    if row.lane is Lane.TRUST:
        return RiskTier.TRUST_CORE
    if row.lane is Lane.COMPETITOR or row.milestone_number >= 2:
        return RiskTier.INTEGRATION
    return RiskTier.STANDARD


def _maturity(row: SourceRow) -> MaturityTarget:
    if row.milestone_number == 0:
        return MaturityTarget(
            engineering=EngineeringMaturity.CONTROLLED_VALIDATED,
            commercial=CommercialMaturity.NOT_EVALUATED,
        )
    if row.milestone_number == 1:
        return MaturityTarget(
            engineering=EngineeringMaturity.CONTROLLED_VALIDATED,
            commercial=CommercialMaturity.NATIVE_ADVANTAGE_UNPROVEN,
        )
    if row.milestone_number == 2:
        return MaturityTarget(
            engineering=EngineeringMaturity.EXTERNAL_VALIDATED,
            commercial=CommercialMaturity.NATIVE_ADVANTAGE_DEMONSTRATED,
        )
    if row.milestone_number in {3, 4, 5}:
        return MaturityTarget(
            engineering=EngineeringMaturity.EXTERNAL_VALIDATED,
            commercial=CommercialMaturity.EXTERNAL_VALUE_DEMONSTRATED,
        )
    return MaturityTarget(
        engineering=EngineeringMaturity.EXTERNAL_VALIDATED,
        commercial=CommercialMaturity.COMMERCIALLY_SUPPORTED,
    )


def _status(row: SourceRow, kind: WorkKind) -> WorkStatus:
    if row.milestone_number == 0:
        return M0_ENGINEERING_STATE.get(row.work_item_id, WorkStatus.PROPOSED)
    if kind is WorkKind.EXTERNAL_EVIDENCE:
        return WorkStatus.WAITING_EXTERNAL
    if row.work_item_id in IMPLEMENTED_M1_ITEMS:
        return WorkStatus.PASSED_ENGINEERING
    return WorkStatus.PROPOSED


def build_collection() -> WorkItemCollection:
    rows = _source_rows()
    identifiers = {row.work_item_id for row in rows}
    items: list[WorkItem] = []
    for row in rows:
        kind = _kind(row)
        dependencies = _dependencies(row, rows)
        missing = set(dependencies) - identifiers
        if missing:
            raise ValueError(
                f"unresolved dependencies for {row.work_item_id}: {sorted(missing)} "
                f"from {row.depends!r}"
            )
        nonautomatable = kind is WorkKind.EXTERNAL_EVIDENCE
        items.append(
            WorkItem(
                work_item_id=row.work_item_id,
                title=row.outcome,
                lane=row.lane,
                kind=kind,
                milestone=MILESTONE_IDS[row.milestone_number],
                decision_contribution=row.outcome,
                customer_outcome=row.outcome,
                depends_on=dependencies,
                soft_depends_on=[],
                source_dependency_expression=row.depends,
                blocks_commercial_release=(
                    row.lane in {Lane.MARKET, Lane.TRUST}
                    or row.milestone_number >= 3
                ),
                priority=max(0, 100 - (row.milestone_number * 10) - row.milestone_position),
                risk_tier=_risk(row, kind),
                maturity_target=_maturity(row),
                disposition=(
                    Disposition.INTEGRATE_EXISTING_BACKEND
                    if row.lane is Lane.COMPETITOR
                    else Disposition.KEEP
                ),
                status=_status(row, kind),
                owner_type=(
                    OwnerType.EXTERNAL_PARTY
                    if kind is WorkKind.EXTERNAL_EVIDENCE
                    else OwnerType.AI
                ),
                automatable=not nonautomatable,
                packet_path=None,
                evidence_required=(
                    [M0_ACCEPTANCE_EVIDENCE[row.work_item_id]]
                    if row.work_item_id in M0_ACCEPTANCE_EVIDENCE
                    else [row.evidence]
                    if row.evidence not in {"", "—", "-"}
                    else []
                ),
                external_receipt_required=kind in {
                    WorkKind.EXTERNAL_EVIDENCE,
                    WorkKind.COMMERCIAL_EXPERIMENT,
                },
                retry_policy=RetryPolicy(
                    max_plan_attempts=0 if nonautomatable else 2,
                    max_candidate_repair_cycles=0 if nonautomatable else 3,
                ),
            )
        )
    return WorkItemCollection(
        active_milestone="M1_NATIVE_PREFLIGHT",
        work_items=items,
    )


def rendered() -> str:
    payload = build_collection().model_dump(mode="json", by_alias=True, exclude_none=False)
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = rendered()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != content:
            raise SystemExit("V3 roadmap work-item ledger is stale")
        print("PASS: 109 authoritative V3 roadmap work items match the source tables")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8", newline="\n")
    print("Wrote 109 authoritative V3 roadmap work items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
