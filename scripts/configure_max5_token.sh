#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'TEXT'
The legacy interactive token configurator is permanently disabled.
V3 credentials must be provisioned externally and are only validated by startup preflight.
No credential, repository, or runtime file was changed.
TEXT
exit 64
