#!/usr/bin/env bash
# This file is intentionally safe to source into an interactive shell.
export PATH="$HOME/.local/bin:$HOME/.local/share/node-v24/bin:$PATH"
ENV_FILE="${TCF_ENV_FILE:-$HOME/.config/traincapsule/lights-out.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing factory environment file: $ENV_FILE" >&2
  return 1 2>/dev/null || exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
TOKEN_FILE="${TCF_CLAUDE_OAUTH_TOKEN_FILE:-$HOME/.config/traincapsule/claude-oauth-token}"
if [[ "${TCF_REQUIRE_MODEL_CREDENTIALS:-1}" == "1" && ! -s "$TOKEN_FILE" ]]; then
  echo "Missing or empty Claude subscription OAuth token file: $TOKEN_FILE" >&2
  return 1 2>/dev/null || exit 1
fi
if [[ "${TCF_REQUIRE_MODEL_CREDENTIALS:-1}" == "1" ]]; then
  export CLAUDE_CODE_OAUTH_TOKEN="$(<"$TOKEN_FILE")"
fi
unset TOKEN_FILE ENV_FILE
