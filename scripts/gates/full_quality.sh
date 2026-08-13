#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

EVIDENCE_MODE="validate"
if [[ ${1:-} == "--pre-evidence" ]]; then
  EVIDENCE_MODE="pre-evidence"
  shift
fi
if [[ $# -ne 0 ]]; then
  echo "usage: full_quality.sh [--pre-evidence]" >&2
  exit 2
fi

bash scripts/gates/secret_scan.sh
COMMON_GIT_DIR="$(git rev-parse --path-format=absolute --git-common-dir)"
SHARED_VENV="$(dirname "$COMMON_GIT_DIR")/.venv"
for executable in ruff pyright python; do
  if [[ ! -x "$SHARED_VENV/bin/$executable" ]]; then
    echo "INFRASTRUCTURE_ERROR: missing pinned $SHARED_VENV/bin/$executable" >&2
    exit 3
  fi
done

"$SHARED_VENV/bin/python" scripts/gates/active_policy_integrity.py
"$SHARED_VENV/bin/python" scripts/gates/validate_source_manifest.py
"$SHARED_VENV/bin/python" scripts/gates/v3_bundle_integrity.py --check-report
"$SHARED_VENV/bin/python" scripts/gates/v3_1_zh_package_integrity.py
"$SHARED_VENV/bin/python" scripts/generate_v3_1_zh_source.py --check
"$SHARED_VENV/bin/python" scripts/gates/source_of_truth_integrity.py
"$SHARED_VENV/bin/python" scripts/gates/output_and_integration_gate.py --repository-v31
if [[ $EVIDENCE_MODE == "validate" ]]; then
  "$SHARED_VENV/bin/python" scripts/gates/v3_migration_evidence.py
fi

UV_BIN="$(command -v uv || true)"
if [[ -z "$UV_BIN" && -x "$HOME/.local/bin/uv" ]]; then
  UV_BIN="$HOME/.local/bin/uv"
fi
if [[ -z "$UV_BIN" ]]; then
  echo "INFRASTRUCTURE_ERROR: uv executable is unavailable" >&2
  exit 3
fi

export VIRTUAL_ENV="$SHARED_VENV"
export UV_OFFLINE=1
"$UV_BIN" run --active --no-sync ruff check .
"$UV_BIN" run --active --no-sync pyright
"$UV_BIN" run --active --no-sync python -m pytest -q
"$UV_BIN" run --active --no-sync python scripts/generate_v3_schemas.py --check
"$UV_BIN" run --active --no-sync python scripts/generate_v31_contract_schemas.py --check
PYTHONPATH="$ROOT/verifier/src${PYTHONPATH:+:$PYTHONPATH}" \
  "$UV_BIN" run --active --no-sync python verifier/scripts/generate_schemas.py --check
"$UV_BIN" run --active --no-sync python scripts/generate_v3_roadmap.py --check
"$UV_BIN" run --active --no-sync python scripts/generate_v3_legacy_migration.py --check
"$UV_BIN" run --active --no-sync python scripts/generate_product_schemas.py --check
"$UV_BIN" run --active --no-sync python scripts/update_v3_migration_inventory.py --check
"$UV_BIN" run --active --no-sync python scripts/gates/no_paid_usage.py
"$UV_BIN" run --active --no-sync tcfactory config validate
"$UV_BIN" run --active --no-sync tcfactory migrate-roadmap --from-v2 --dry-run
"$UV_BIN" build --offline --wheel
"$UV_BIN" build --offline --wheel --project verifier --out-dir dist/verifier

root_script_present() {
  "$SHARED_VENV/bin/python" - "$1" <<'PY'
import json
import sys

try:
    payload = json.loads(open("package.json", encoding="utf-8").read())
except (OSError, json.JSONDecodeError):
    raise SystemExit(1) from None
raise SystemExit(0 if sys.argv[1] in payload.get("scripts", {}) else 1)
PY
}

run_root_script_if_present() {
  local script=$1
  if [[ -f package.json ]] && command -v pnpm >/dev/null 2>&1 \
    && root_script_present "$script"; then
    pnpm run "$script"
  fi
}

run_root_script_if_present lint
run_root_script_if_present test
run_root_script_if_present build
