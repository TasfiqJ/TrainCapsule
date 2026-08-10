#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

case "$ROOT" in
  /mnt/*)
    echo "The product repository must be in the WSL Linux filesystem under /home/<user>/projects." >&2
    exit 1
    ;;
esac

if [[ "$(uname -s)" != Linux ]] || ! grep -qi microsoft /proc/version; then
  echo "Run this setup inside Ubuntu on WSL2." >&2
  exit 1
fi

cat <<'TEXT'
TrainCapsule Claude Autonomous Product Factory v8.0 — one-time setup

This setup will:
  1. install WSL/Linux dependencies;
  2. create a long-lived Claude Max subscription OAuth token;
  3. install hidden gates outside the repository and delete their bootstrap source;
  4. verify Claude-native features, including a real cross-session builder/scout handshake;
  5. run deterministic, adversarial, value, and live multi-role calibration;
  6. connect a private GitHub repository and verify Actions;
  7. enable automatic planning, coding, review, repair, merge, push, quota resume, and reboot recovery.

Keep Claude usage credits disabled. No Anthropic API key is used.
TEXT

# Installs Git, uv, Python, Claude Code, bubblewrap/socat, dependencies, and public tests.
bash "$ROOT/scripts/windows_wsl_prepare.sh"

for name in ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL \
  CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX CLAUDE_CODE_USE_FOUNDRY; do
  if [[ -n "${!name:-}" ]]; then
    echo "Refusing Max-only setup while $name is set. Remove it and rerun." >&2
    exit 1
  fi
done

if [[ -z "$(git config user.name || true)" ]]; then
  read -r -p "Git display name: " GIT_NAME
  [[ -n "$GIT_NAME" ]] || { echo "Git name cannot be empty." >&2; exit 1; }
  git config user.name "$GIT_NAME"
fi
if [[ -z "$(git config user.email || true)" ]]; then
  read -r -p "Git email: " GIT_EMAIL
  [[ -n "$GIT_EMAIL" ]] || { echo "Git email cannot be empty." >&2; exit 1; }
  git config user.email "$GIT_EMAIL"
fi

# One-time browser authorization. Token lives outside the repository with mode 600.
bash "$ROOT/scripts/configure_max5_token.sh"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"

# Move hidden gates outside the builder-visible repository and self-test them.
bash "$ROOT/scripts/install_private_gate.sh"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"

bash "$ROOT/scripts/validate_factory.sh"

git add -A
if ! git diff --cached --quiet; then
  git commit -m "set up autonomous builder"
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Repository is not clean after bootstrap; refusing autonomy." >&2
  git status --short >&2
  exit 1
fi

# This live calibration is itself quota-aware. It waits and resumes the same demo stage
# with a fresh Claude session if Max is exhausted during setup.
bash "$ROOT/scripts/run_one_time_calibration.sh"

# Authenticate GitHub, create or attach a private repository, push the verified baseline,
# and prove that remote CI can observe the same commit.
bash "$ROOT/scripts/configure_github.sh"

# Enable automatic merge and register/start the Windows recovery task.
bash "$ROOT/scripts/enable_lights_out.sh"

printf '\nONE-TIME SETUP COMPLETE.\n'
printf 'The autonomous builder is now running. It plans, codes, tests, attacks, repairs,\n'
printf 'merges exact passing commits, waits through Claude Max limits, and resumes with fresh\n'
printf 'sessions until the automatable TrainCapsule definition of done passes or a genuine\n'
printf 'external blocker is reached.\n\n'
printf 'Status: cd %q && source scripts/load_factory_env.sh && uv run tcfactory autonomy-status\n' "$ROOT"
printf 'Log:    tail -f %q\n' "$ROOT/factory/logs/autopilot.log"
printf 'Controls from WSL: bash scripts/factory_control.sh overview|pause|resume|verify\n'
