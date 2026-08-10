#!/usr/bin/env bash
set -euo pipefail

# Scan tracked files only. The OAuth token and private gates must never be tracked.
tracked="$(git ls-files)"
for forbidden in \
  '.claude/.credentials.json' \
  '.config/traincapsule' \
  'claude-oauth-token' \
  'traincapsule-factory/private-gates'; do
  if grep -Fq "$forbidden" <<<"$tracked"; then
    echo "Forbidden credential/private path is tracked: $forbidden" >&2
    exit 1
  fi
done

if git grep -nE '(ANTHROPIC_API_KEY|CLAUDE_CODE_OAUTH_TOKEN)[[:space:]]*=[[:space:]]*[A-Za-z0-9_-]{20,}' -- ':!scripts/verify_no_secrets.sh' >/tmp/rpf-secret-scan.txt 2>/dev/null; then
  cat /tmp/rpf-secret-scan.txt >&2
  echo "Potential live credential found in tracked content." >&2
  exit 1
fi
rm -f /tmp/rpf-secret-scan.txt
