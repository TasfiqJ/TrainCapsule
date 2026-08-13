#!/bin/sh
set -eu
readonly TCF_RUNTIME_PYTHON=/opt/traincapsule-runtime/bin/python3.12
readonly TCF_REPOSITORY_BOUNDARY=/var/lib/traincapsule-verifier/repository-boundary
readonly TCF_EFFECTIVE_ENV=/etc/traincapsule-controller/controller-runtime.env
if [ ! -x "$TCF_RUNTIME_PYTHON" ] || [ ! -r "$TCF_EFFECTIVE_ENV" ]; then
    echo "activation supervisor installed runtime is unavailable" >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
. "$TCF_EFFECTIVE_ENV"
set +a
export TCF_REPO_PATH="$TCF_REPOSITORY_BOUNDARY"
exec "$TCF_RUNTIME_PYTHON" -m tcfactory.v3.activation_supervisor
