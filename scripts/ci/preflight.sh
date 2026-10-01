#!/usr/bin/env bash
# Usage: BASE=http://short.local scripts/ci/preflight.sh; optionally ALLOW_CONTEXT=<name>.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
source "$ROOT/scripts/ci/lib.sh"
NS=${NS:-urlshortener}
PROFILE=${PROFILE:-minikube}
BASE=${BASE:-http://short.local}
for tool in docker kubectl minikube; do
    command -v "$tool" >/dev/null 2>&1 || { ci_error "Required tool '$tool' is not on PATH."; exit 1; }
done
docker info >/dev/null 2>&1 || { ci_error 'Docker is not reachable by the runner user; check the Docker service/socket permissions.'; exit 1; }
expected_context=${ALLOW_CONTEXT:-minikube}
context=$(kubectl config current-context 2>/dev/null || true)
[[ $context == "$expected_context" ]] || { ci_error "Refusing deployment: kubectl context is '$context', expected '$expected_context'. Set ALLOW_CONTEXT explicitly only for an intentional override."; exit 1; }
minikube status -p "$PROFILE" 2>/dev/null | grep -q 'host: Running' || { ci_error "minikube profile '$PROFILE' is not Running; start it before deployment."; exit 1; }
kubectl get --raw=/readyz >/dev/null 2>&1 || { ci_error 'Kubernetes API server is not answering.'; exit 1; }
kubectl get namespace "$NS" >/dev/null 2>&1 && kubectl -n "$NS" get deployment shortly >/dev/null 2>&1 && kubectl -n "$NS" get secret shortly-secrets >/dev/null 2>&1 || {
    ci_error "Namespace, Deployment, or Secret missing. Run 'make k8s-up deploy' first. CI never creates or modifies secrets."; exit 1;
}
curl_args=(-fsS --max-time 3)
if ! curl "${curl_args[@]}" "$BASE/healthz" >/dev/null 2>&1; then
    host=${BASE#*://}; host=${host%%/*}; host=${host%%:*}
    if [[ $host == short.local ]] && ! python3 -c 'import socket; socket.gethostbyname("short.local")' >/dev/null 2>&1; then
        pf_log=$(mktemp)
        nohup kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 18000:80 >"$pf_log" 2>&1 </dev/null &
        PF_PID=$!
        export PF_PID
        for _ in $(seq 1 30); do
            if curl -fsS --max-time 1 -H 'Host: short.local' http://localhost:18000/healthz >/dev/null 2>&1; then break; fi
            sleep 0.3
        done
        curl -fsS --max-time 2 -H 'Host: short.local' http://localhost:18000/healthz >/dev/null || { ci_error 'short.local is unavailable and the ingress port-forward failed.'; cat "$pf_log" >&2; exit 1; }
        BASE=http://localhost:18000
        HOST_HEADER=short.local
        export BASE
        export HOST_HEADER
        ci_log 'short.local did not resolve; using ingress port-forward at http://localhost:18000 with Host: short.local.'
        [[ -n ${GITHUB_ENV:-} ]] && printf 'BASE=%s\nHOST_HEADER=%s\n' "$BASE" "$HOST_HEADER" >> "$GITHUB_ENV"
        [[ -n ${GITHUB_ENV:-} ]] && printf 'CI_PORT_FORWARD_PID=%s\n' "$PF_PID" >> "$GITHUB_ENV"
    else
        ci_error "Health check failed at $BASE/healthz."; exit 1
    fi
fi
printf 'Docker: '; docker --version
printf 'kubectl: '; kubectl version --client --output=yaml | awk '/gitVersion:/{print $2; exit}'
printf 'minikube: '; minikube version --short
printf 'Context: %s\nNamespace: %s\nBASE: %s\n' "$context" "$NS" "$BASE"
printf 'Before image: '
kubectl -n "$NS" get deployment shortly -o jsonpath='{.spec.template.spec.containers[?(@.name=="shortly")].image}{"\n"}'
