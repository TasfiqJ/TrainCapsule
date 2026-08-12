#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'TEXT'
The legacy interactive one-time setup is permanently disabled.
Use scripts/factory_control.sh verify after external V3 credentials and the root-owned
private gate have been provisioned. No files, commits, or runtime controls were changed.
TEXT
exit 64
