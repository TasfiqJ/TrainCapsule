#!/usr/bin/env bash
set -euo pipefail

# User-space Claude/Node installation used by the TrainCapsule factory.
export PATH="$HOME/.local/bin:$HOME/.local/share/node-v24/bin:$PATH"

for name in ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL \
  CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX CLAUDE_CODE_USE_FOUNDRY; do
  if [[ -n "${!name:-}" ]]; then
    echo "Refusing setup while $name is set." >&2
    exit 1
  fi
done

command -v claude >/dev/null || {
  echo "Claude Code is not installed inside this WSL distribution." >&2
  exit 1
}

ACK_FILE="$HOME/.config/traincapsule/usage-credits-disabled.ack"
if [[ ! -f "$ACK_FILE" ]]; then
  echo "Missing durable acknowledgement that Claude usage credits are disabled." >&2
  exit 1
fi

cat <<'TEXT'
This creates a long-lived OAuth token for your private Claude Max software factory.
It is not an Anthropic API key and it does not enable Console/API billing.

1. `claude setup-token` opens a browser authorization flow.
2. Authorize the Claude.ai account that owns Max.
3. Copy the token Claude prints.
4. Paste it once at the hidden prompt below.

Running this script again safely replaces the token file. A waiting autopilot reloads
that file on its next authentication retry and continues without losing task state.
TEXT

claude setup-token
read -r -s -p "Paste CLAUDE_CODE_OAUTH_TOKEN: " TOKEN
printf '\n'
if [[ -z "$TOKEN" ]]; then
  echo "No token entered." >&2
  exit 1
fi

CONFIG_DIR="$HOME/.config/traincapsule"
TOKEN_FILE="$CONFIG_DIR/claude-oauth-token"
ENV_FILE="$CONFIG_DIR/lights-out.env"
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
umask 077

TEMP_TOKEN="$(mktemp "$CONFIG_DIR/.claude-oauth-token.XXXXXX")"
printf '%s\n' "$TOKEN" > "$TEMP_TOKEN"
chmod 600 "$TEMP_TOKEN"
install -m 600 "$TEMP_TOKEN" "$TOKEN_FILE"
rm "$TEMP_TOKEN"
unset TOKEN

{
  printf 'export TCF_CLAUDE_OAUTH_TOKEN_FILE=%q\n' "$TOKEN_FILE"
  printf 'export TCF_MONTHLY_ESTIMATED_USD_CAP=100\n'
  printf 'export TCF_MAX_PARALLEL=1\n'
  printf 'export TCF_LIGHTS_OUT=1\n'
  printf 'export TCF_REQUIRE_LONG_LIVED_OAUTH=1\n'
  printf 'export TCF_USAGE_CREDITS_DISABLED_ACK=1\n'
  printf 'export TCF_PRIVATE_GATE_RUNNER=%q\n' \
    "$HOME/.local/share/traincapsule-factory/private-gates/run_private_gate.sh"
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"

printf 'Stored the subscription OAuth token in %s with mode 600.\n' "$TOKEN_FILE"
printf 'Stored non-secret factory configuration in %s with mode 600.\n' "$ENV_FILE"
printf 'Do not print, commit, or copy either file into the product repository.\n'
printf 'Keep Claude usage credits disabled; quota exhaustion must pause and resume.\n'
