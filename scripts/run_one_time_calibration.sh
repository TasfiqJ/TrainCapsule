#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${TCF_ENV_FILE:-$HOME/.config/traincapsule/lights-out.env}"
PRIVATE_ROOT="$HOME/.local/share/traincapsule-factory/private-gates"
EVIDENCE_DIR="$ROOT/factory/state/calibration"
CHECKPOINT="$ROOT/factory/state/pipelines/DEMO-001.json"
RESET_BUFFER_SECONDS=0
LIMIT_PROBE_SECONDS=3600

[[ -f "$ENV_FILE" ]] || {
  echo "Missing $ENV_FILE. Run scripts/configure_max5_token.sh." >&2
  exit 10
}
# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"
cd "$ROOT"

[[ -x "$PRIVATE_ROOT/run_private_gate.sh" ]] || {
  echo "Private gate is not installed at $PRIVATE_ROOT." >&2
  exit 11
}

rm -rf "$EVIDENCE_DIR"
mkdir -p "$EVIDENCE_DIR"

run_logged() {
  local name=$1
  shift
  echo "==> $name"
  "$@" > >(tee "$EVIDENCE_DIR/$name.stdout.log") \
        2> >(tee "$EVIDENCE_DIR/$name.stderr.log" >&2)
}

run_logged max_oauth_verify ./scripts/verify_max_subscription.sh
run_logged schema_generation uv run tcfactory schema --output schemas/task.generated.json
run_logged unit_tests uv run python -m pytest
run_logged ruff uv run ruff check .
run_logged pyright uv run pyright
run_logged deterministic_sabotage uv run python scripts/calibration_sabotage.py
run_logged private_gate_self_test "$PRIVATE_ROOT/self_test.sh"
run_logged private_gate_repository "$PRIVATE_ROOT/run_private_gate.sh" factory-negative-controls "$ROOT"

HEAD_SHA=$(git rev-parse HEAD)
find_valid_summary() {
  python3 - "$HEAD_SHA" <<'PY_FIND'
import json
import sys
from pathlib import Path

repo = Path.cwd().resolve()
head = sys.argv[1]
required_roles = {"specification", "builder", "adversary", "audit", "release"}


def resolve_artifact(raw: object) -> Path:
    path = Path(str(raw or ""))
    return path.resolve() if path.is_absolute() else (repo / path).resolve()


def nonempty(path: Path) -> bool:
    return path.is_file() and bool(path.read_text(encoding="utf-8").strip())


def native_feature_evidence(builder: dict, scout: dict) -> bool:
    builder_dir = resolve_artifact(builder.get("artifact_dir"))
    scout_dir = resolve_artifact(scout.get("artifact_dir"))
    builder_messages = builder_dir / "peer-messages.jsonl"
    scout_messages = scout_dir / "peer-messages.jsonl"
    if not (nonempty(builder_messages) and nonempty(scout_messages)):
        return False
    try:
        builder_plan = json.loads(
            (builder_dir / "claude-native-feature-plan.json").read_text(encoding="utf-8")
        )
        scout_plan = json.loads(
            (scout_dir / "claude-native-feature-plan.json").read_text(encoding="utf-8")
        )
    except Exception:
        return False
    return bool(
        builder.get("peer_messaging_enabled") is True
        and builder_plan.get("peer_messaging") is True
        and builder_plan.get("goal_condition")
        and builder_plan.get("advisor_model") == "opus"
        and "implement-task" in (builder_plan.get("skills") or [])
        and scout_plan.get("peer_messaging") is True
        and "integration-proof" in (scout_plan.get("skills") or [])
    )


for path in sorted(Path("factory/artifacts/DEMO-001").glob("*/pipeline-summary.json"), reverse=True):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    results = data.get("results") or []
    roles = {str(item.get("role")) for item in results if isinstance(item, dict)}
    builder = next(
        (item for item in results if isinstance(item, dict) and item.get("role") == "builder"),
        None,
    )
    if not builder:
        continue
    scout = next(
        (
            item
            for item in (builder.get("peer_sessions") or [])
            if isinstance(item, dict) and item.get("role") == "integration_scout"
        ),
        None,
    )
    if not scout or scout.get("verdict") != "pass" or not scout.get("session_id"):
        continue
    session_ids = [
        str(item.get("session_id"))
        for item in results
        if isinstance(item, dict) and item.get("session_id")
    ] + [str(scout.get("session_id"))]
    if (
        data.get("starting_sha") == head
        and data.get("merged") is False
        and data.get("final_sha")
        and results
        and required_roles.issubset(roles)
        and all(item.get("verdict") == "pass" for item in results if isinstance(item, dict))
        and len(session_ids) >= len(required_roles) + 1
        and len(session_ids) == len(set(session_ids))
        and native_feature_evidence(builder, scout)
    ):
        print(path)
        raise SystemExit(0)
raise SystemExit(1)
PY_FIND
}

quota_wait_seconds() {
  uv run python - "$CHECKPOINT" "$RESET_BUFFER_SECONDS" "$LIMIT_PROBE_SECONDS" <<'PY_QUOTA'
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

path = Path(sys.argv[1])
buffer_seconds = int(sys.argv[2])
probe_seconds = int(sys.argv[3])
if not path.is_file():
    raise SystemExit(2)
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(3)
if data.get("state") != "paused" or not isinstance(data.get("pause"), dict):
    raise SystemExit(4)
raw = str(data["pause"].get("resume_at") or "")
if not raw:
    raise SystemExit(5)
resume_at = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
now = datetime.now(UTC)
seconds = max(60, min(probe_seconds, int((resume_at - now).total_seconds()) + buffer_seconds))
print(seconds)
print(str(data["pause"].get("kind") or "unknown"), file=sys.stderr)
print(raw, file=sys.stderr)
PY_QUOTA
}

run_live_demo_with_quota_resume() {
  local stdout_log="$EVIDENCE_DIR/live_demo.stdout.log"
  local stderr_log="$EVIDENCE_DIR/live_demo.stderr.log"
  : > "$stdout_log"
  : > "$stderr_log"
  local attempt=0
  while true; do
    attempt=$((attempt + 1))
    printf '\n=== live demo attempt %d at %s ===\n' "$attempt" "$(date -Is)" | tee -a "$stdout_log"
    if uv run tcfactory run tasks/DEMO-001.yaml --no-merge \
      > >(tee -a "$stdout_log") 2> >(tee -a "$stderr_log" >&2); then
      return 0
    fi

    local wait_output wait_seconds
    if ! wait_output=$(quota_wait_seconds 2>>"$stderr_log"); then
      echo "Live demo failed for a non-quota reason. Calibration stopped." \
        | tee -a "$stderr_log" >&2
      return 1
    fi
    wait_seconds=$(printf '%s\n' "$wait_output" | tail -1)
    if [[ ! "$wait_seconds" =~ ^[0-9]+$ ]]; then
      echo "Could not calculate a safe quota-resume delay." | tee -a "$stderr_log" >&2
      return 1
    fi
    printf 'Claude rejected work for a usage limit. Probing again in %s seconds with a fresh session.\n' \
      "$wait_seconds" | tee -a "$stdout_log"
    sleep "$wait_seconds"
    # Reload a renewed token without restarting the setup when the operator replaced it.
    # shellcheck disable=SC1091
    source "$ROOT/scripts/load_factory_env.sh"
  done
}

SUMMARY=$(find_valid_summary || true)
if [[ -z "$SUMMARY" ]]; then
  echo "Running one live role-separated harmless pipeline. This consumes Claude Max capacity."
  run_live_demo_with_quota_resume
  SUMMARY=$(find_valid_summary)
else
  printf 'Reusing valid current-head live pipeline summary: %s\n' "$SUMMARY" \
    | tee "$EVIDENCE_DIR/live_demo.stdout.log"
  : > "$EVIDENCE_DIR/live_demo.stderr.log"
fi

python3 - "$SUMMARY" "$EVIDENCE_DIR" <<'PY_EVIDENCE'
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

summary = Path(sys.argv[1]).resolve()
evidence_dir = Path(sys.argv[2]).resolve()
repo = Path.cwd().resolve()
data = json.loads(summary.read_text(encoding="utf-8"))
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
required_roles = {"specification", "builder", "adversary", "audit", "release"}
results = data.get("results") or []
roles = {str(item.get("role")) for item in results if isinstance(item, dict)}
builder = next(item for item in results if item.get("role") == "builder")
scout = next(
    item
    for item in (builder.get("peer_sessions") or [])
    if item.get("role") == "integration_scout"
)
sessions = [str(item.get("session_id")) for item in results if item.get("session_id")]
sessions.append(str(scout.get("session_id")))
assert data["starting_sha"] == head, (data["starting_sha"], head)
assert data["merged"] is False
assert data["final_sha"]
assert required_roles.issubset(roles), (required_roles, roles)
assert all(item["verdict"] == "pass" for item in results)
assert scout["verdict"] == "pass"
assert len(sessions) >= len(required_roles) + 1, sessions
assert len(sessions) == len(set(sessions)), "calibration roles reused a Claude session"
assert builder.get("peer_messaging_enabled") is True


def resolve_artifact(raw: object) -> Path:
    path = Path(str(raw or ""))
    return path.resolve() if path.is_absolute() else (repo / path).resolve()


builder_dir = resolve_artifact(builder["artifact_dir"])
scout_dir = resolve_artifact(scout["artifact_dir"])
builder_messages = builder_dir / "peer-messages.jsonl"
scout_messages = scout_dir / "peer-messages.jsonl"
assert builder_messages.is_file() and builder_messages.read_text(encoding="utf-8").strip()
assert scout_messages.is_file() and scout_messages.read_text(encoding="utf-8").strip()
builder_plan_path = builder_dir / "claude-native-feature-plan.json"
scout_plan_path = scout_dir / "claude-native-feature-plan.json"
builder_plan = json.loads(builder_plan_path.read_text(encoding="utf-8"))
scout_plan = json.loads(scout_plan_path.read_text(encoding="utf-8"))
assert builder_plan["peer_messaging"] is True
assert scout_plan["peer_messaging"] is True
assert builder_plan["goal_condition"]
assert builder_plan["advisor_model"] == "opus"
assert "implement-task" in builder_plan["skills"]
assert "integration-proof" in scout_plan["skills"]

cross_payload = {
    "builder_session": builder.get("session_name"),
    "builder_session_id": builder.get("session_id"),
    "scout_session": scout.get("session_name"),
    "scout_session_id": scout.get("session_id"),
    "builder_message_audit": str(builder_messages.relative_to(repo)),
    "builder_message_sha256": hashlib.sha256(builder_messages.read_bytes()).hexdigest(),
    "scout_message_audit": str(scout_messages.relative_to(repo)),
    "scout_message_sha256": hashlib.sha256(scout_messages.read_bytes()).hexdigest(),
}
(evidence_dir / "cross_session_messaging.stdout.log").write_text(
    json.dumps(cross_payload, indent=2) + "\n", encoding="utf-8"
)
(evidence_dir / "cross_session_messaging.stderr.log").write_text("", encoding="utf-8")

feature_payload = {
    "builder_plan": str(builder_plan_path.relative_to(repo)),
    "builder_plan_sha256": hashlib.sha256(builder_plan_path.read_bytes()).hexdigest(),
    "scout_plan": str(scout_plan_path.relative_to(repo)),
    "scout_plan_sha256": hashlib.sha256(scout_plan_path.read_bytes()).hexdigest(),
    "builder": builder_plan,
    "scout": scout_plan,
}
(evidence_dir / "claude_native_features.stdout.log").write_text(
    json.dumps(feature_payload, indent=2) + "\n", encoding="utf-8"
)
(evidence_dir / "claude_native_features.stderr.log").write_text("", encoding="utf-8")

logs = []
for path in sorted(evidence_dir.glob("*.log")):
    logs.append(
        {
            "path": str(path.relative_to(repo)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
        }
    )
required_controls = [
    "max_oauth_verify",
    "schema_generation",
    "unit_tests",
    "ruff",
    "pyright",
    "deterministic_sabotage",
    "private_gate_self_test",
    "private_gate_repository",
    "live_demo",
    "claude_native_features",
    "cross_session_messaging",
]
payload = {
    "version": 3,
    "calibrated_at": datetime.now(UTC).isoformat(),
    "head_sha": head,
    "live_pipeline_summary": str(summary.relative_to(repo)),
    "summary_sha256": hashlib.sha256(summary.read_bytes()).hexdigest(),
    "required_controls": required_controls,
    "logs": logs,
}
Path("factory/state/CALIBRATION_EVIDENCE.json").write_text(
    json.dumps(payload, indent=2) + "\n", encoding="utf-8"
)
print(f"CALIBRATION EVIDENCE WRITTEN: {len(logs)} log files; live summary {summary}")
PY_EVIDENCE

uv run tcfactory mark-calibrated --acknowledge
printf '\nCALIBRATION COMPLETE. The installer will now enable lights-out mode.\n'
