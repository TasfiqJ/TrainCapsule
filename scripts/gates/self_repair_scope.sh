#!/usr/bin/env bash
set -euo pipefail

# Controller repair is allowed, but billing, authority, truth, and the gates
# validating this repair remain immutable.
if ! git diff --exit-code main...HEAD -- \
  tcfactory/auth.py \
  config/factory.yaml \
  config/github.yaml \
  config/context.yaml \
  config/value_policy.yaml \
  .claude \
  .factory/source-locks \
  bootstrap/private-gates \
  docs/source-of-truth \
  factory/task_catalog.yaml \
  factory/feature_ledger.yaml \
  factory/product_definition_of_done.yaml \
  scripts/gates/no_paid_usage.sh \
  scripts/gates/secret_scan.sh \
  scripts/gates/self_repair_scope.sh \
  scripts/configure_max5_token.sh \
  scripts/load_factory_env.sh; then
  echo "Self-repair changed a billing, authority, truth, or gate control." >&2
  exit 1
fi

echo "PASS: self-repair stayed inside mutable controller scope"
