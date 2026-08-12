#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'TEXT'
The legacy automatic-enable workflow is permanently disabled.
The V3 Windows launcher is managed only through scripts/factory_control.sh and it always
honors the configured RuntimePaths plus durable STOP, PAUSE, and HARD_STUCK controls.
No runtime control was changed.
TEXT
exit 64
