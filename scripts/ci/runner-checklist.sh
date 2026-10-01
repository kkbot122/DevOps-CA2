#!/usr/bin/env bash
# Usage: scripts/ci/runner-checklist.sh; reports runner prerequisites and available service status.
set -euo pipefail
expected=${ALLOW_CONTEXT:-minikube}
context=$(kubectl config current-context 2>/dev/null || true)
printf 'Runner checklist\n'
for tool in docker kubectl minikube; do
    if command -v "$tool" >/dev/null 2>&1; then printf 'PASS tool: %s (%s)\n' "$tool" "$(command -v "$tool")"; else printf 'MISSING tool: %s\n' "$tool"; fi
done
if [[ $context == "$expected" ]]; then printf 'PASS kubectl context: %s\n' "$context"; else printf 'Context: %s (preflight expects %s)\n' "${context:-unset}" "$expected"; fi
if python3 -c 'import socket; socket.gethostbyname("short.local")' >/dev/null 2>&1; then
    echo 'PASS hosts mapping: short.local resolves'
else
    echo 'Fallback: short.local is not mapped; preflight uses the ingress port-forward'
fi
runner_root=${RUNNER_ROOT:-}
if [[ -n $runner_root && -x $runner_root/svc.sh ]]; then
    "$runner_root/svc.sh" status || echo 'Runner service is not active.'
elif [[ $(uname -s) == Linux ]] && command -v systemctl >/dev/null 2>&1; then
    services=$(systemctl list-units --type=service --all --no-legend 'actions.runner*' 2>/dev/null || true)
    if [[ -n $services ]]; then printf '%s\n' "$services"; else echo 'Runner service not detected; start ./run.sh interactively if needed.'; fi
else
    echo 'Runner service status not detected; use ./run.sh interactively if needed.'
fi
