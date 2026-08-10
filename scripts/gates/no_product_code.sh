#!/usr/bin/env bash
set -euo pipefail
if git diff --name-only main...HEAD -- src apps packages web | grep -q .; then
  echo "Product code changed during a source-freeze task." >&2
  git diff --name-only main...HEAD -- src apps packages web >&2
  exit 1
fi
