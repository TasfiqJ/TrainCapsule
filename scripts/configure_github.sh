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
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Tracked repository changes must be committed before GitHub setup." >&2
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
  - push only exact verified candidates to release branches and never force-push;
  - stop when remote main diverges instead of overwriting outside work;
  - open draft pull requests for required GitHub-hosted validation;
  - leave every merge to an authorized human decision.
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
data["releaseMode"] = "pull_request"
data["directMainPush"] = False
path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
PY

# Verify the protected base without updating it. The configured change is left for
# the normal reviewed candidate flow; setup never performs a direct main push.
if ! git ls-remote --exit-code --heads origin main >/dev/null 2>&1; then
  echo "origin/main is missing. Establish it through an authorized bootstrap process." >&2
  exit 1
fi
git fetch --no-tags origin refs/heads/main:refs/remotes/origin/main
if ! git merge-base --is-ancestor origin/main main; then
  echo "Remote main contains work absent from local main. Resolve divergence first." >&2
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

printf '\nGitHub pull-request release configuration is ready: %s\n' "$name_with_owner"
printf 'Commit config/github.yaml through the verified candidate workflow.\n'
printf 'Verified commits will use: %s <%s>\n' \
  "$(git config user.name)" "$(git config user.email)"
