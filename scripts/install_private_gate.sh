#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'TEXT'
This legacy user-writable private-gate installer is permanently disabled.
TrainCapsule V3 requires the externally provisioned, root-owned gate under /var/lib.
No files or runtime controls were changed.
TEXT
exit 64
