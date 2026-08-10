#!/usr/bin/env bash
set -euo pipefail
required=(
  docs/TrainCapsule_Matrix_Definitive_Master_Plan_v1.0.md
  docs/FINAL_AUTONOMOUS_FACTORY_PLAN.md
  docs/SOURCE_AUTHORITY.md
  docs/CONTEXT_INDEX.yaml
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
python3 - <<'PY'
from pathlib import Path
from tcfactory.yamlutil import load_yaml
ledger=load_yaml(Path('factory/feature_ledger.yaml'))
assert ledger['tasks'], 'feature ledger is empty'
for item in ledger['tasks']:
    assert item['risk_tier'] in {'mechanical','standard','integration','trust_core'}
    assert item.get('context_keys'), f"missing context_keys: {item['task_id']}"
PY
