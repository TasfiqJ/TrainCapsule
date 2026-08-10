#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"

bad=0
for name in ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL \
  CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX CLAUDE_CODE_USE_FOUNDRY; do
  if [[ -n "${!name:-}" ]]; then
    printf 'FAIL: %s is set; Max-only mode refuses non-subscription routing.\n' "$name" >&2
    bad=1
  fi
done
[[ "$bad" -eq 0 ]] || exit 1

command -v claude >/dev/null || {
  echo 'FAIL: claude is not installed inside this WSL2 distribution.' >&2
  exit 1
}

if [[ "${TCF_REQUIRE_LONG_LIVED_OAUTH:-1}" == "1" && -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]]; then
  cat >&2 <<'TEXT'
FAIL: the long-lived Claude subscription OAuth token is not loaded.
Run scripts/configure_max5_token.sh. The setup-token credential is a one-year
Claude subscription OAuth token, not an API key.
TEXT
  exit 1
fi

claude --version
status_json="$(claude auth status)"
printf '%s\n' "$status_json" | jq .

logged_in="$(printf '%s\n' "$status_json" | jq -r '.loggedIn // false')"
auth_method="$(printf '%s\n' "$status_json" | jq -r '.authMethod // ""')"
api_provider="$(printf '%s\n' "$status_json" | jq -r '.apiProvider // ""')"

[[ "$logged_in" == "true" ]] || {
  echo 'FAIL: Claude Code is not authenticated.' >&2
  exit 1
}
case "$auth_method" in
  claude.ai|oauth_token) ;;
  *)
    echo "FAIL: authMethod=$auth_method is not Claude.ai subscription OAuth." >&2
    exit 1
    ;;
esac
if [[ -n "$api_provider" && "$api_provider" != "firstParty" && \
      "$api_provider" != "first_party" && "$api_provider" != "anthropic" ]]; then
  echo "FAIL: apiProvider=$api_provider is not first-party Claude authentication." >&2
  exit 1
fi

echo 'PASS: long-lived Claude subscription OAuth is active and no API-billing route is configured.'
echo 'Verify Max 5x separately in Claude Settings > Usage and keep usage credits disabled.'
