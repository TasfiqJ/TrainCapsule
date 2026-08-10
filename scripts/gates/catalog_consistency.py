from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tcfactory.catalog import load_task_catalog  # noqa: E402
from tcfactory.feature_ledger import load_feature_ledger  # noqa: E402

EXTERNAL_OR_DEMAND_DRIVEN = {"T119", "T121"}


def main() -> int:
    ledger = load_feature_ledger(ROOT / "factory/feature_ledger.yaml")
    catalog = load_task_catalog(ROOT / "factory/task_catalog.yaml")
    errors: list[str] = []

    automatable = {item.task_id for item in ledger.tasks if item.automatable}
    expected_catalog = automatable - EXTERNAL_OR_DEMAND_DRIVEN
    actual_catalog = set(catalog.tasks)

    missing = sorted(expected_catalog - actual_catalog)
    extra = sorted(actual_catalog - automatable)
    if missing:
        errors.append(f"missing catalog entries: {missing}")
    if extra:
        errors.append(f"catalog contains non-automatable/unknown entries: {extra}")

    for task_id in sorted(expected_catalog & actual_catalog):
        item = ledger.item(task_id)
        entry = catalog.tasks[task_id]
        if entry.depends_on != item.depends_on:
            errors.append(
                f"{task_id} dependencies differ: catalog={entry.depends_on!r}, "
                f"ledger={item.depends_on!r}"
            )
        if not entry.allowed_paths:
            errors.append(f"{task_id} has no allowed_paths")
        if not entry.expected_outputs:
            errors.append(f"{task_id} has no expected_outputs")
        if not entry.acceptance_criteria:
            errors.append(f"{task_id} has no acceptance_criteria")
        if len(entry.acceptance_criteria) > 25:
            errors.append(f"{task_id} exceeds 25 acceptance criteria")
        if entry.risk_tier and entry.risk_tier != item.risk_tier.value:
            errors.append(
                f"{task_id} risk label differs: catalog={entry.risk_tier}, "
                f"ledger={item.risk_tier.value}"
            )

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(
        f"PASS: {len(actual_catalog)} deterministic task catalog entries match the "
        "automatable roadmap."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
