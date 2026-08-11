#!/usr/bin/env bash
set -euo pipefail
required=(
  SOURCE_PRECEDENCE.md
  docs/source-of-truth/final-2026-08-09/FINAL_MANIFEST.json
  docs/source-of-truth/final-2026-08-09/TRAINCAPSULE_FINAL_MASTER_PLAN.md
  docs/source-of-truth/v3-2026-08-11/FINAL_MANIFEST_V3.json
  docs/source-of-truth/v3-2026-08-11/00_EXECUTIVE_BUILD_DECISION_V3.md
  docs/CONTEXT_INDEX.yaml
  config/human_approval.yaml
  config/risk_profiles.yaml
  config/context.yaml
  config/github.yaml
  factory/feature_ledger.yaml
  factory/task_catalog.yaml
  factory/product_definition_of_done.yaml
)
for path in "${required[@]}"; do
  test -s "$path" || { echo "Missing authority file: $path" >&2; exit 1; }
done
python3 scripts/gates/validate_source_manifest.py
python3 scripts/gates/source_of_truth_integrity.py
python3 - <<'PY'
from pathlib import Path
from tcfactory.yamlutil import load_yaml
ledger=load_yaml(Path('factory/feature_ledger.yaml'))
assert ledger['tasks'], 'feature ledger is empty'
for item in ledger['tasks']:
    assert item['risk_tier'] in {'mechanical','standard','integration','trust_core'}
    assert item.get('context_keys'), f"missing context_keys: {item['task_id']}"
PY
