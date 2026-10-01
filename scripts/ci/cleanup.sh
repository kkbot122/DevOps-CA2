#!/usr/bin/env bash
# Usage: scripts/ci/cleanup.sh; stops only the port-forward started by preflight.sh.
set -euo pipefail
if [[ ${CI_PORT_FORWARD_PID:-} =~ ^[0-9]+$ ]]; then kill "$CI_PORT_FORWARD_PID" 2>/dev/null || true; fi
