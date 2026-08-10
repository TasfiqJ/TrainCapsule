#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/bootstrap/private-gates"
TARGET="$HOME/.local/share/traincapsule-factory/private-gates"
ENV_FILE="$HOME/.config/traincapsule/lights-out.env"

mkdir -p "$HOME/.local/share" "$HOME/.config/traincapsule"
chmod 700 "$HOME/.config/traincapsule"

if [[ -d "$SOURCE" ]]; then
  rm -rf "$TARGET"
  cp -a "$SOURCE" "$TARGET"
  chmod 700 "$TARGET" "$TARGET/run_private_gate.sh" "$TARGET/self_test.sh"
  find "$TARGET" -type f -name '*.py' -exec chmod 600 {} +
  # Hidden gates must not remain in the repository that builder sessions can inspect.
  rm -rf "$SOURCE"
elif [[ ! -x "$TARGET/run_private_gate.sh" ]]; then
  echo "Private-gate bootstrap payload is missing and no installed runner exists." >&2
  exit 1
fi

PYTHON_BIN="${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
PYTHON_BIN="$PYTHON_BIN" bash "$TARGET/self_test.sh"

umask 077
TMP=$(mktemp "$HOME/.config/traincapsule/.lights-out.env.XXXXXX")
if [[ -f "$ENV_FILE" ]]; then
  grep -v '^export TCF_PRIVATE_GATE_RUNNER=' "$ENV_FILE" > "$TMP" || true
fi
printf 'export TCF_PRIVATE_GATE_RUNNER=%q\n' "$TARGET/run_private_gate.sh" >> "$TMP"
chmod 600 "$TMP"
mv -f "$TMP" "$ENV_FILE"

printf 'Installed and self-tested hidden private gates at %s.\n' "$TARGET"
printf 'Removed the hidden bootstrap payload from the product repository.\n'
