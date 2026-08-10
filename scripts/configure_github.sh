#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI is missing. Re-run scripts/windows_wsl_prepare.sh." >&2
  exit 1
fi
if [[ -z "$(git config user.name || true)" || -z "$(git config user.email || true)" ]]; then
  echo "Git user.name and user.email must be configured before GitHub setup." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Repository must be clean before GitHub setup." >&2
  git status --short >&2
  exit 1
fi

cat <<'TEXT'
GitHub one-time setup

The factory will:
  - authenticate through the official GitHub CLI browser flow;
  - create or attach a private repository;
  - author verified task commits with your configured Git name and email;
  - keep AI-factory provenance in local structured records;
  - push only fast-forward history and never force-push;
  - stop when remote main diverges instead of overwriting outside work;
  - run GitHub Actions for integration and trust-core candidates;
  - push normal verified work in small periodic batches.
TEXT

if ! gh auth status --hostname github.com >/dev/null 2>&1; then
  gh auth login --hostname github.com --web --git-protocol https
fi
gh auth setup-git --hostname github.com

if ! git remote get-url origin >/dev/null 2>&1; then
  default_name="traincapsule"
  read -r -p "Private GitHub repository name [$default_name]: " repo_name
  repo_name="${repo_name:-$default_name}"
  gh repo create "$repo_name" \
    --private \
    --source=. \
    --remote=origin \
    --description "Verified compatibility and upgrade control plane for agent infrastructure"
fi

remote_url="$(git remote get-url origin)"
case "$remote_url" in
  https://github.com/*|git@github.com:*|ssh://git@github.com/*) ;;
  *)
    echo "Origin is not a GitHub remote: $remote_url" >&2
    exit 1
    ;;
esac

metadata="$(gh repo view --json nameWithOwner,visibility,url)"
name_with_owner="$(printf '%s' "$metadata" | jq -r '.nameWithOwner')"
visibility="$(printf '%s' "$metadata" | jq -r '.visibility | ascii_downcase')"
if [[ -z "$name_with_owner" || "$name_with_owner" == "null" ]]; then
  echo "Could not resolve the GitHub repository identity." >&2
  exit 1
fi
if [[ "$visibility" != "private" ]]; then
  echo "Refusing GitHub sync because the repository is not private: $name_with_owner ($visibility)" >&2
  exit 1
fi

python3 - "$name_with_owner" <<'PY'
from pathlib import Path
import sys
import yaml

from tcfactory.yamlutil import load_yaml

path = Path("config/github.yaml")
data = load_yaml(path)
if not isinstance(data, dict):
    raise SystemExit("config/github.yaml must be a mapping")
data["enabled"] = True
data["repository"] = sys.argv[1]
data["visibility"] = "private"
path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
PY

git add config/github.yaml
if ! git diff --cached --quiet; then
  git commit -m "set up github sync"
fi

# Establish or update origin/main without rewriting history.
if git ls-remote --exit-code --heads origin main >/dev/null 2>&1; then
  git fetch --prune origin main
  if ! git merge-base --is-ancestor origin/main main; then
    echo "Remote main contains work that local main does not contain. Refusing to overwrite it." >&2
    exit 1
  fi
fi
git push -u origin main

local_sha="$(git rev-parse main)"
remote_sha="$(git ls-remote origin refs/heads/main | awk '{print $1}')"
if [[ "$local_sha" != "$remote_sha" ]]; then
  echo "Initial GitHub verification failed: local=$local_sha remote=$remote_sha" >&2
  exit 1
fi

# Secret scanning for private repositories can depend on account/repository eligibility.
# Enable it when GitHub permits it, but keep the local secret scan mandatory regardless.
if ! gh api --method PATCH "repos/$name_with_owner" \
  -f 'security_and_analysis[secret_scanning][status]=enabled' \
  -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled' \
  >/dev/null 2>&1; then
  echo "Note: GitHub secret-scanning push protection was unavailable for this private repository."
  echo "The factory's mandatory local secret scan remains enabled."
fi

uv run tcfactory github-sync --force
printf '\nGitHub synchronization is ready: %s\n' "$name_with_owner"
printf 'Verified commits will use: %s <%s>\n' \
  "$(git config user.name)" "$(git config user.email)"
