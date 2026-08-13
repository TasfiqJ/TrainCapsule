#!/usr/bin/env python3
"""Preserve the V2 ledger and generate its explicit V3 disposition map."""

from __future__ import annotations

# ruff: noqa: E402
import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Final, cast

import yaml

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tcfactory.feature_ledger import FeatureItem, load_feature_ledger
from tcfactory.util import atomic_write_text
from tcfactory.v3.base import sha256_digest
from tcfactory.v3.migrations import (
    LegacyDisposition,
    LegacyEvidenceFile,
    LegacyMapRecord,
    LegacyMigrationMap,
    LegacyStatus,
)
from tcfactory.v3.work_items import WorkItemCollection
from tcfactory.yamlutil import load_yaml

LEGACY_SOURCE: Final = ROOT / "factory/feature_ledger.yaml"
LEGACY_ARCHIVE: Final = ROOT / "factory/roadmap/legacy_feature_ledger.yaml"
MAPPING_OUTPUT: Final = ROOT / "factory/roadmap/migrations/v2_to_v3.yaml"
OPTIONAL_EVIDENCE_MANIFEST: Final = (
    ROOT / "factory/roadmap/migrations/v2_runtime_evidence_manifest.json"
)
ROADMAP_SOURCE: Final = ROOT / "factory/roadmap/work_items.yaml"
SNAPSHOT_SOURCE: Final = ROOT / "docs/migrations/V3_RUNTIME_SNAPSHOT_METADATA.json"
OPTIONAL_RUNTIME_EVIDENCE_ROOTS: Final = (
    "factory/artifacts/T001",
    "factory/artifacts/T002",
)

# Only explicit V3 equivalents are mapped. Broad or merely similar V2 designs stay
# deferred, which prevents semantic title matching from silently expanding V3.
EXPLICIT_V3_EQUIVALENTS: Final[dict[str, tuple[str, ...]]] = {
    "T001": ("V3-MIG-003", "V3-MIG-004"),
    "T003": ("V3-MIG-004",),
    "T004": ("V3-MIG-004", "V3-MIG-013"),
    "T005": ("V3-MIG-005", "V3-MIG-006"),
    "T006": ("V3-MIG-007", "V3-MIG-014"),
    "T007": ("V3-MIG-013",),
    "T009": ("V3-COMP-002",),
    "T010": ("V3-DEC-001",),
    "T011": ("V3-DEC-001",),
    "T012": ("V3-PROD-002",),
    "T013": ("V3-PROD-002", "V3-PROD-004"),
    "T014": ("V3-TRUST-001",),
    "T015": ("V3-PROD-004", "V3-PROD-005"),
    "T016": ("V3-PROD-005",),
    "T017": ("V3-PROD-002", "V3-PROD-003"),
    "T018": ("V3-PROD-003",),
    "T020": ("V3-TRUST-003",),
    "T021": ("V3-TRUST-002", "V3-TRUST-003"),
    "T022": ("V3-PROD-010",),
    "T023": ("V3-TRUST-001",),
    "T025": ("V3-PROD-006",),
    "T026": ("V3-PROD-012",),
    "T030": ("V3-PROD-008",),
    "T031": ("V3-TRUST-002",),
    "T033": ("V3-COMP-001", "V3-COMP-003"),
    "T034": ("V3-COMP-002", "V3-COMP-004"),
    "T037": ("V3-PROD-012",),
    "T038": ("V3-TRUST-004",),
    "T039": ("V3-PROD-008",),
    "T040": ("V3-PROD-011", "V3-PROD-021"),
    "T041": ("V3-PROD-024",),
    "T042": ("V3-PROD-024",),
    "T043": ("V3-PROD-024",),
    "T044": ("V3-TRUST-004",),
    "T045": ("V3-PROD-013",),
    "T046": ("V3-PROD-008", "V3-TRUST-004"),
    "T047": ("V3-PROD-024", "V3-TRUST-004"),
    "T056": ("V3-PROD-013", "V3-PROD-015"),
    "T057": ("V3-PROD-013",),
    "T058": ("V3-PROD-009", "V3-PROD-015"),
    "T059": ("V3-DEC-002", "V3-PROD-009"),
    "T060": ("V3-PROD-016", "V3-TRUST-005"),
    "T061": ("V3-PROD-014",),
    "T062": ("V3-PROD-014",),
    "T063": ("V3-PROD-014", "V3-TRUST-005"),
    "T064": ("V3-PROD-014", "V3-TRUST-005"),
    "T066": ("V3-PROD-005", "V3-PROD-014"),
    "T067": ("V3-PROD-009", "V3-PROD-014"),
    "T068": ("V3-PROD-024", "V3-TRUST-005"),
    "T069": ("V3-PROD-025", "V3-TRUST-005"),
    "T070": ("V3-PROD-017", "V3-PROD-018"),
    "T071": ("V3-PROD-017",),
    "T072": ("V3-PROD-005", "V3-PROD-017"),
    "T073": ("V3-PROD-025",),
    "T075": ("V3-PROD-005", "V3-PROD-009"),
    "T076": ("V3-PROD-017", "V3-TRUST-006"),
    "T077": ("V3-TRUST-002", "V3-TRUST-006"),
    "T078": ("V3-PROD-027", "V3-TRUST-006"),
    "T079": ("V3-PROD-016", "V3-PROD-022"),
    "T080": ("V3-PROD-002", "V3-PROD-027"),
    "T081": ("V3-PROD-022", "V3-PROD-027"),
    "T082": ("V3-PROD-025", "V3-PROD-027"),
    "T083": ("V3-PROD-019",),
    "T084": ("V3-PROD-019", "V3-TRUST-007"),
    "T085": ("V3-PROD-019", "V3-TRUST-007"),
    "T086": ("V3-PROD-019", "V3-TRUST-007"),
    "T087": ("V3-PROD-019", "V3-PROD-020"),
    "T088": ("V3-PROD-019", "V3-PROD-021"),
    "T089": ("V3-PROD-024", "V3-TRUST-007"),
    "T090": ("V3-PROD-021",),
    "T091": ("V3-PROD-021",),
    "T092": ("V3-PROD-020", "V3-PROD-021"),
    "T093": ("V3-PROD-021", "V3-TRUST-008"),
    "T094": ("V3-PROD-025", "V3-TRUST-008"),
    "T097": ("V3-PROD-015", "V3-PROD-019"),
    "T098": ("V3-TRUST-007", "V3-TRUST-008"),
    "T104": ("V3-COMP-004", "V3-DEC-002"),
    "T106": ("V3-PROD-023",),
    "T107": ("V3-PROD-027",),
    "T108": ("V3-PROD-027", "V3-TRUST-009"),
    "T109": ("V3-TRUST-009",),
    "T110": ("V3-COMP-005",),
    "T111": ("V3-PROD-024", "V3-PROD-025"),
    "T112": ("V3-COMP-005", "V3-DEC-002"),
    "T114": ("V3-TRUST-010",),
    "T115": ("V3-MKT-001",),
    "T116": ("V3-MKT-008", "V3-MKT-009"),
    "T117": ("V3-TRUST-011",),
    "T118": ("V3-MKT-003",),
    "T119": ("V3-COMP-006", "V3-PROD-028"),
    "T120": ("V3-PROD-009", "V3-REPEAT-006"),
    "T121": ("V3-REPEAT-001",),
    "T122": ("V3-REPEAT-005", "V3-REPEAT-006"),
    "T123": ("V3-DEC-005",),
}
FACTORY_HISTORY_IDS: Final = {f"T{index:03d}" for index in range(1, 8)}


def _source_digest(source: Path) -> str:
    return f"sha256:{hashlib.sha256(source.read_bytes()).hexdigest()}"


def _snapshot(source: Path) -> dict[str, object]:
    raw: object = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("runtime snapshot must be an object")
    return cast(dict[str, object], raw)


def _snapshot_ledger_digest(snapshot: dict[str, object]) -> str:
    inputs = snapshot.get("trackedInputs")
    if not isinstance(inputs, list):
        raise ValueError("runtime snapshot trackedInputs must be a list")
    for raw_item in cast(list[object], inputs):
        if isinstance(raw_item, dict):
            item = cast(dict[str, object], raw_item)
            if item.get("path") != "factory/feature_ledger.yaml":
                continue
            digest = item.get("sha256")
            if isinstance(digest, str):
                return f"sha256:{digest}"
    raise ValueError("runtime snapshot does not bind the V2 feature ledger")


def _inventory_digest(inventory: list[LegacyEvidenceFile]) -> str:
    payload = b"".join(
        f"{item.mode}\0{item.path}\0{item.sha256}\n".encode() for item in inventory
    )
    return sha256_digest(payload)


def _load_optional_evidence_manifest(root: Path) -> list[LegacyEvidenceFile]:
    manifest_path = root / "factory/roadmap/migrations/v2_runtime_evidence_manifest.json"
    raw: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("legacy runtime evidence manifest must be an object")
    payload = cast(dict[str, object], raw)
    if set(payload) != {
        "schemaVersion",
        "sourceMigrationBaseSha",
        "inventory",
        "inventoryDigest",
    }:
        raise ValueError("legacy runtime evidence manifest fields are not exact")
    if payload["schemaVersion"] != "1":
        raise ValueError("legacy runtime evidence manifest version is unsupported")
    snapshot = _snapshot(root / "docs/migrations/V3_RUNTIME_SNAPSHOT_METADATA.json")
    if payload["sourceMigrationBaseSha"] != snapshot.get("head"):
        raise ValueError("legacy runtime evidence manifest base SHA mismatch")
    raw_inventory = payload["inventory"]
    if not isinstance(raw_inventory, list):
        raise ValueError("legacy runtime evidence inventory must be a list")
    inventory = [
        LegacyEvidenceFile.model_validate(item)
        for item in cast(list[object], raw_inventory)
    ]
    paths = [item.path for item in inventory]
    if paths != sorted(set(paths)):
        raise ValueError("legacy runtime evidence paths must be unique and sorted")
    if not inventory or any(
        not any(
            item.path == evidence_root
            or item.path.startswith(f"{evidence_root}/")
            for evidence_root in OPTIONAL_RUNTIME_EVIDENCE_ROOTS
        )
        for item in inventory
    ):
        raise ValueError("legacy runtime evidence escaped its exact optional roots")
    if payload["inventoryDigest"] != _inventory_digest(inventory):
        raise ValueError("legacy runtime evidence manifest digest mismatch")
    return inventory


def _evidence_file(root: Path, path: Path) -> LegacyEvidenceFile:
    return LegacyEvidenceFile(
        path=path.relative_to(root).as_posix(),
        mode=format(path.stat().st_mode & 0o7777, "04o"),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def _preserved_evidence(item: FeatureItem, root: Path) -> list[str]:
    references = {"factory/feature_ledger.yaml"}
    if item.packet_path:
        references.add(item.packet_path)
    references.update(item.evidence)
    task_id = item.task_id
    candidates = [
        root / f"docs/evidence/{task_id}",
        root / f"factory/proposals/{task_id}.yaml",
        root / f"specs/tasks/{task_id}.md",
    ]
    if task_id in {"T001", "T002"}:
        # These ignored runtime trees were present in the signed migration snapshot.
        # Keep their preservation references deterministic in clean checkouts.
        references.add(f"factory/artifacts/{task_id}")
    for candidate in candidates:
        if candidate.exists():
            references.add(candidate.relative_to(root).as_posix())
    recovery = root / "factory/recovery/task-packets"
    if recovery.is_dir():
        references.update(
            path.relative_to(root).as_posix()
            for path in recovery.glob(f"{task_id}-*")
            if path.is_file()
        )
    if task_id in {"T001", "T002"}:
        references.add("docs/migrations/V3_RUNTIME_SNAPSHOT_METADATA.json")
    return sorted(references)


def _evidence_inventory(
    root: Path, records: list[LegacyMapRecord]
) -> tuple[list[LegacyEvidenceFile], str]:
    optional_inventory = _load_optional_evidence_manifest(root)
    optional_by_path = {item.path: item for item in optional_inventory}
    optional_roots = {
        evidence_root: {
            path: item
            for path, item in optional_by_path.items()
            if path == evidence_root or path.startswith(f"{evidence_root}/")
        }
        for evidence_root in OPTIONAL_RUNTIME_EVIDENCE_ROOTS
    }
    files: set[Path] = set()
    for record in records:
        for relative in record.evidence_preserved:
            candidate = root / relative
            if candidate.is_symlink():
                raise ValueError(f"legacy evidence cannot be a symlink: {relative}")
            if candidate.is_dir():
                files.update(path for path in candidate.rglob("*") if path.is_file())
            elif candidate.is_file():
                files.add(candidate)
            elif any(
                relative == evidence_root
                or relative.startswith(f"{evidence_root}/")
                for evidence_root in OPTIONAL_RUNTIME_EVIDENCE_ROOTS
            ):
                # T001/T002 execution artifacts are deliberately ignored runtime bytes.
                # Their complete immutable per-file roster is checked in separately so a
                # clean checkout can reproduce the migration map without pretending the
                # runtime trees are repository source.
                continue
            else:
                raise ValueError(f"legacy evidence is missing: {relative}")
    observed_items = [_evidence_file(root, path) for path in sorted(files)]
    observed = {item.path: item for item in observed_items}
    for evidence_root, expected in optional_roots.items():
        candidate_root = root / evidence_root
        if candidate_root.exists():
            actual = {
                item.path: item
                for item in (
                    _evidence_file(root, path)
                    for path in sorted(candidate_root.rglob("*"))
                    if path.is_file()
                )
            }
            if actual != expected:
                raise ValueError(
                    f"legacy runtime evidence differs from its immutable manifest: {evidence_root}"
                )
        observed.update(expected)
    inventory = [observed[path] for path in sorted(observed)]
    return inventory, _inventory_digest(inventory)


def build_mapping(root: Path = ROOT) -> LegacyMigrationMap:
    legacy_source = root / "factory/feature_ledger.yaml"
    roadmap_source = root / "factory/roadmap/work_items.yaml"
    snapshot_source = root / "docs/migrations/V3_RUNTIME_SNAPSHOT_METADATA.json"
    ledger = load_feature_ledger(legacy_source)
    if ledger.version != 2:
        raise ValueError(f"expected V2 feature ledger, observed version {ledger.version}")
    snapshot = _snapshot(snapshot_source)
    digest = _source_digest(legacy_source)
    if digest != _snapshot_ledger_digest(snapshot):
        raise ValueError("V2 feature ledger no longer matches the stopped-runtime snapshot")
    base_sha = snapshot.get("head")
    if not isinstance(base_sha, str):
        raise ValueError("runtime snapshot head must be a SHA")

    records: list[LegacyMapRecord] = []
    for item in ledger.tasks:
        mapped = sorted(EXPLICIT_V3_EQUIVALENTS.get(item.task_id, ()))
        if item.task_id == "T002":
            disposition = LegacyDisposition.DEFERRED_NON_BLOCKING
            reason = (
                "Naming/trademark clearance is deferred and non-blocking for private product "
                "implementation. It may reopen only at public launch, package publication, paid "
                "contract, or legal-counsel request; it never auto-resumes."
            )
        elif item.task_id in FACTORY_HISTORY_IDS:
            disposition = LegacyDisposition.FACTORY
            reason = (
                "Historical V2 factory/source-control work; any replacement is only "
                "the listed bounded V3 work and the legacy status does not transfer."
            )
        elif mapped:
            disposition = LegacyDisposition.MAPPED_TO_V3
            reason = (
                "This concept is explicitly represented by the listed bounded V3 work; "
                "the legacy status and dependency chain do not transfer."
            )
        else:
            disposition = LegacyDisposition.DEFERRED_DESIGN
            reason = (
                "Broad or unselected V2 design is preserved as historical input and is "
                "not scheduled unless an authorized V3 work item is promoted later."
            )
        records.append(
            LegacyMapRecord(
                legacy_task_id=item.task_id,
                legacy_status=LegacyStatus(item.status),
                legacy_outcome=item.outcome,
                legacy_packet=item.packet_path,
                v3_disposition=disposition,
                mapped_work_items=mapped,
                reason=reason,
                evidence_preserved=_preserved_evidence(item, root),
            )
        )

    inventory, inventory_digest = _evidence_inventory(root, records)
    migration = LegacyMigrationMap(
        migration_base_sha=base_sha,
        source_ledger_digest=digest,
        source_policy_ref=ledger.source_of_truth,
        records=records,
        preserved_evidence_inventory=inventory,
        preserved_evidence_inventory_digest=inventory_digest,
    )
    roadmap = WorkItemCollection.model_validate(load_yaml(roadmap_source))
    migration.validate_v3_targets({item.work_item_id for item in roadmap.work_items})
    return migration


def rendered_mapping(root: Path = ROOT) -> str:
    payload = build_mapping(root).model_dump(
        mode="json", by_alias=True, exclude_none=False
    )
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def install(root: Path = ROOT, *, keep_previous: bool = True) -> None:
    """Atomically install the exact legacy archive and its deterministic mapping."""

    legacy_source = root / "factory/feature_ledger.yaml"
    legacy_archive = root / "factory/roadmap/legacy_feature_ledger.yaml"
    mapping_output = root / "factory/roadmap/migrations/v2_to_v3.yaml"
    mapping = rendered_mapping(root)
    legacy = legacy_source.read_text(encoding="utf-8")
    if not mapping_output.is_file() or mapping_output.read_text(encoding="utf-8") != mapping:
        atomic_write_text(mapping_output, mapping, keep_previous=keep_previous)
    if not legacy_archive.is_file() or (
        legacy_archive.read_text(encoding="utf-8") != legacy
    ):
        atomic_write_text(legacy_archive, legacy, keep_previous=keep_previous)


def verify_installed(root: Path = ROOT) -> None:
    """Fail if the installed legacy artifacts differ from their deterministic source."""

    legacy_source = root / "factory/feature_ledger.yaml"
    legacy_archive = root / "factory/roadmap/legacy_feature_ledger.yaml"
    mapping_output = root / "factory/roadmap/migrations/v2_to_v3.yaml"
    if not mapping_output.is_file() or (
        mapping_output.read_text(encoding="utf-8") != rendered_mapping(root)
    ):
        raise ValueError("V3 legacy migration map is stale")
    if not legacy_archive.is_file() or (
        legacy_archive.read_text(encoding="utf-8")
        != legacy_source.read_text(encoding="utf-8")
    ):
        raise ValueError("V2 legacy feature ledger archive is stale")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        try:
            verify_installed()
        except ValueError as error:
            raise SystemExit(str(error)) from error
        print("PASS: 124 V2 entries and statuses have an exact V3 migration record")
        return 0
    install()
    print("Wrote exact V2 ledger archive and 124-record V3 migration map")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
