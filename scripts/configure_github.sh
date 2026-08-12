#!/usr/bin/env bash
set -euo pipefail

echo "No GitHub setup mutation is allowed; configure_github.sh is disabled by V3." >&2
echo "GitHub configuration is immutable runtime authority; verify it with: tcfactory verify" >&2
exit 64
