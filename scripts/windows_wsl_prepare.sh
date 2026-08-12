#!/usr/bin/env bash
set -euo pipefail

if ! grep -qi microsoft /proc/version; then
  echo "Warning: this script is designed for Ubuntu under WSL2." >&2
fi

sudo apt update
sudo apt install -y \
  git curl wget jq unzip ca-certificates build-essential \
  bubblewrap socat tmux apparmor apparmor-utils

# Install GitHub CLI from GitHub's maintained Debian repository. The Ubuntu community
# package can lag or break against newer GitHub APIs.
if ! command -v gh >/dev/null 2>&1; then
  sudo mkdir -p -m 755 /etc/apt/keyrings /etc/apt/sources.list.d
  key_tmp="$(mktemp)"
  wget -nv -O "$key_tmp" https://cli.github.com/packages/githubcli-archive-keyring.gpg
  printf '%s  %s\n' \
    '6084d5d7bd8e288441e0e94fc6275570895da18e6751f70f057485dc2d1a811b' \
    "$key_tmp" | sha256sum --check --status
  sudo install -m 0644 "$key_tmp" /etc/apt/keyrings/githubcli-archive-keyring.gpg
  rm -f "$key_tmp"
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\n' \
    "$(dpkg --print-architecture)" | \
    sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
  sudo apt update
  sudo apt install -y gh
fi

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

export PATH="$HOME/.local/bin:$PATH"
grep -qxF 'export PATH="$HOME/.local/bin:$PATH"' ~/.bashrc || \
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

uv python install 3.12

# The Claude-native loop requires cross-session messaging and /goal. Re-running the
# official installer is idempotent and updates an older Claude Code installation.
curl -fsSL https://claude.ai/install.sh | bash
export PATH="$HOME/.local/bin:$PATH"

if [[ ! -d .git ]]; then
  git init -b main
fi

uv sync --extra dev
test -f uv.lock || { echo "uv sync did not create uv.lock" >&2; exit 1; }
uv run python scripts/verify_yaml_unique.py .
uv run tcfactory schema --output schemas/task.generated.json
uv run python scripts/gates/catalog_consistency.py
uv run python -m pytest
uv run ruff check .
uv run pyright
claude doctor
bash scripts/verify_claude_features.sh

printf '\n%s\n' "WSL host and repository dependencies are ready."
printf '%s\n' "Legacy interactive credential/setup scripts are disabled under V3."
printf '%s\n' "Use scripts/factory_control.sh verify for the read-only readiness check."
