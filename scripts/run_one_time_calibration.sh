#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'TEXT'
The legacy live/model calibration workflow is permanently disabled.
V3 startup uses deterministic configuration, source, private-gate, migration, credential,
checkpoint, and publication-recovery preflight checks. No evidence or state was changed.
TEXT
exit 64
