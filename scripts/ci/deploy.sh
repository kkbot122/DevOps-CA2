#!/usr/bin/env bash
# Usage: scripts/ci/deploy.sh <image-ref> <expected-digest> [--no-auto-rollback]; LOCAL=1 skips registry pull/digest verification.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
source "$ROOT/scripts/ci/lib.sh"
[[ $# -ge 2 && $# -le 3 ]] || { echo 'Usage: deploy.sh <image-ref> <expected-digest> [--no-auto-rollback]' >&2; exit 2; }
IMAGE_REF=$1 EXPECTED_DIGEST=$2
[[ $# == 2 || $3 == --no-auto-rollback ]] || { echo 'Unknown option.' >&2; exit 2; }
NS=${NS:-urlshortener}
PROFILE=${PROFILE:-minikube}
AUTO_ROLLBACK=${AUTO_ROLLBACK:-true}
[[ ${3:-} == --no-auto-rollback ]] && AUTO_ROLLBACK=false
export NS AUTO_ROLLBACK
if [[ ${LOCAL:-0} != 1 ]]; then
    [[ -n ${GITHUB_TOKEN:-} ]] || { ci_error 'GITHUB_TOKEN is required for GHCR login.'; exit 1; }
    printf '%s' "$GITHUB_TOKEN" | docker login ghcr.io -u "${GITHUB_ACTOR:-github-actions[bot]}" --password-stdin
    docker pull "$IMAGE_REF"
    actual_digest=$(docker image inspect "$IMAGE_REF" --format '{{range .RepoDigests}}{{println .}}{{end}}' | awk -v image="${IMAGE_REF%%:*}" 'index($0,image"@sha256:"){sub(/^.*@/,"");print;exit}')
    [[ -n $actual_digest && $actual_digest == "$EXPECTED_DIGEST" ]] || { ci_error "Digest mismatch for $IMAGE_REF (expected $EXPECTED_DIGEST, got ${actual_digest:-none})."; exit 1; }
else
    ci_log 'LOCAL=1: skipping GHCR pull and registry digest verification.'
fi
minikube image load -p "$PROFILE" "$IMAGE_REF"
minikube image ls -p "$PROFILE" | grep -Fq "${IMAGE_REF%:*}" || { ci_error "Image $IMAGE_REF is not visible inside minikube after image load."; exit 1; }
PREVIOUS_REVISION=$(kubectl -n "$NS" get deployment shortly -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/revision}')
PREVIOUS_IMAGE=$(kubectl -n "$NS" get deployment shortly -o jsonpath='{.spec.template.spec.containers[?(@.name=="shortly")].image}')
export PREVIOUS_REVISION PREVIOUS_IMAGE
NEW_REVISION=unknown
START=$(date +%s)
probe_file=$(mktemp); versions_file=$(mktemp); body_file=$(mktemp)
printf '0 0\n' > "$probe_file"
probe_loop() {
    local http version total=0 failed=0
    while :; do
        total=$((total + 1))
        if [[ -n ${HOST_HEADER:-} ]]; then
            http=$(curl -H "Host: $HOST_HEADER" -sS --max-time 2 -o "$body_file" -w '%{http_code}' "${BASE:-http://short.local}/version" 2>/dev/null) || http=000
        else
            http=$(curl -sS --max-time 2 -o "$body_file" -w '%{http_code}' "${BASE:-http://short.local}/version" 2>/dev/null) || http=000
        fi
        if [[ $http == 2?? ]]; then
            version=$(python3 - "$body_file" <<'PY'
import json,sys
try: print(json.load(open(sys.argv[1], encoding='utf-8')).get('version',''))
except (OSError, ValueError): print('')
PY
)
            if [[ -n $version ]]; then printf '%s\n' "$version" >> "$versions_file"; else failed=$((failed + 1)); fi
        else failed=$((failed + 1)); fi
        printf '%s %s\n' "$total" "$failed" > "$probe_file"
        sleep 0.3
    done
}
PROBE_TOTAL=0 PROBE_FAILED=0
probe_loop & PROBE_PID=$!
stop_probe() { kill "$PROBE_PID" 2>/dev/null || true; wait "$PROBE_PID" 2>/dev/null || true; }
trap 'stop_probe; rm -f "$probe_file" "$versions_file" "$body_file"' EXIT
tmp=$(mktemp -d "$ROOT/.ci-overlay.XXXXXX")
cat >"$tmp/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../k8s
images:
  - name: shortly
    newName: ${IMAGE_REF%:*}
    newTag: ${IMAGE_REF##*:}
EOF
kubectl kustomize "$tmp" --load-restrictor=LoadRestrictionsNone | kubectl apply -f - || fail_with_rollback 'Applying the rendered CI overlay failed.'
sha7=${GITHUB_SHA:-$(git -C "$ROOT" rev-parse --short=7 HEAD)}; sha7=${sha7:0:7}
kubectl -n "$NS" annotate deployment/shortly "kubernetes.io/change-cause=ci $sha7 run ${GITHUB_RUN_ID:-local} by ${GITHUB_ACTOR:-$(id -un)} variant=${VARIANT:-good}" --overwrite
rollout_rc=0
kubectl -n "$NS" rollout status deployment/shortly --timeout=150s || rollout_rc=$?
stop_probe
read -r TOTAL FAILED < "$probe_file"
VERSIONS=$(sort -u "$versions_file" | paste -sd, -); DURATION=$(($(date +%s)-START))
export TOTAL FAILED VERSIONS DURATION
printf 'Rollout duration: %ss\nProbe requests: %s; failed: %s; versions seen: %s\n' "$DURATION" "$TOTAL" "$FAILED" "${VERSIONS:-none}"
[[ -n ${GITHUB_ENV:-} ]] && printf 'PROBE_TOTAL=%s\nPROBE_FAILED=%s\nPROBE_VERSIONS=%s\nROLLOUT_DURATION=%s\nPREVIOUS_REVISION=%s\nPREVIOUS_IMAGE=%s\nNEW_REVISION=%s\n' "$TOTAL" "$FAILED" "$VERSIONS" "$DURATION" "$PREVIOUS_REVISION" "$PREVIOUS_IMAGE" "$(kubectl -n "$NS" get deployment shortly -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/revision}')" >> "$GITHUB_ENV"
rm -rf "$tmp"
if (( rollout_rc != 0 )); then fail_with_rollback 'Deployment rollout failed or timed out.'; fi
NEW_REVISION=$(kubectl -n "$NS" get deployment shortly -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/revision}')
[[ -n ${GITHUB_ENV:-} ]] && printf 'NEW_REVISION=%s\n' "$NEW_REVISION" >> "$GITHUB_ENV"
printf 'Rollout complete at revision %s (previous revision %s, image %s).\n' "$NEW_REVISION" "$PREVIOUS_REVISION" "$PREVIOUS_IMAGE"
