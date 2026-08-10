#!/usr/bin/env bash
set -euo pipefail
if ! git diff --exit-code main...HEAD -- \
  docs/source-of-truth/final-2026-08-09 \
  .factory/source-locks \
  .claude \
  config \
  prompts \
  schemas \
  tcfactory \
  scripts \
  bootstrap/private-gates \
  factory/task_catalog.yaml \
  factory/feature_ledger.yaml \
  factory/product_definition_of_done.yaml; then
  echo "Protected factory files changed during the harmless calibration task." >&2
  exit 1
fi
