#!/usr/bin/env bash
set -euo pipefail

# This file is an example only. The real runner and hidden fixtures MUST live outside
# the agent-visible TrainCapsule repository. Configure its absolute path through:
#   export TCF_PRIVATE_GATE_RUNNER=/opt/traincapsule-factory/private-gates/run_private_gate.sh
# Invocation contract:
#   run_private_gate.sh <suite-name> <candidate-worktree>

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <suite-name> <candidate-worktree>" >&2
  exit 2
fi

suite=$1
candidate=$2
hidden_root=${TCF_HIDDEN_TEST_ROOT:-/opt/traincapsule-factory/private-gates}

case "$suite" in
  factory-negative-controls)
    python3 "$hidden_root/suites/factory_negative_controls.py" --repo "$candidate"
    ;;
  trust-core-mutations)
    python3 -m pytest -q "$hidden_root/tests/trust_core" --candidate "$candidate"
    ;;
  *)
    echo "unknown private gate suite: $suite" >&2
    exit 3
    ;;
esac
