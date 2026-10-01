#!/usr/bin/env bash
# Usage: BASE=http://short.local EXPECTED_VERSION=<tag> scripts/ci/verify.sh [--no-auto-rollback|--version-only].
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
source "$ROOT/scripts/ci/lib.sh"
BASE=${BASE:-http://short.local}
AUTO_ROLLBACK=${AUTO_ROLLBACK:-true}
MODE=all
for arg in "$@"; do case "$arg" in --no-auto-rollback) AUTO_ROLLBACK=false;; --version-only) MODE=version-only;; *) echo "Unknown option: $arg" >&2; exit 2;; esac; done
export AUTO_ROLLBACK
verify_versions() {
    local expected=${EXPECTED_VERSION:-} body status actual
    local versions=()
    if [[ -n $expected && $MODE != version-only ]]; then
        local consecutive=0
        ci_log "Waiting for ingress endpoints to return $expected consistently."
        for _ in $(seq 1 30); do
            body=$(mktemp)
            if [[ -n ${HOST_HEADER:-} ]]; then status=$(curl -H "Host: $HOST_HEADER" -sS --max-time 3 -o "$body" -w '%{http_code}' "$BASE/version") || status=000
            else status=$(curl -sS --max-time 3 -o "$body" -w '%{http_code}' "$BASE/version") || status=000; fi
            actual=$(python3 - "$body" <<'PY'
import json,sys
try: print(json.load(open(sys.argv[1], encoding='utf-8')).get('version',''))
except (OSError, ValueError): print('')
PY
)
            rm -f "$body"
            if [[ $status == 2?? && $actual == "$expected" ]]; then consecutive=$((consecutive + 1)); else consecutive=0; fi
            [[ $consecutive -ge 5 ]] && break
            sleep 0.3
        done
        [[ $consecutive -ge 5 ]] || { ci_error "Ingress did not converge to version $expected."; return 1; }
    elif [[ $MODE == version-only ]]; then
        local stable_version='' consecutive=0
        ci_log 'Waiting for ingress endpoints to return one consistent version.'
        for _ in $(seq 1 30); do
            body=$(mktemp)
            if [[ -n ${HOST_HEADER:-} ]]; then status=$(curl -H "Host: $HOST_HEADER" -sS --max-time 3 -o "$body" -w '%{http_code}' "$BASE/version") || status=000
            else status=$(curl -sS --max-time 3 -o "$body" -w '%{http_code}' "$BASE/version") || status=000; fi
            actual=$(python3 - "$body" <<'PY'
import json,sys
try: print(json.load(open(sys.argv[1], encoding='utf-8')).get('version',''))
except (OSError, ValueError): print('')
PY
)
            rm -f "$body"
            if [[ $status == 2?? && -n $actual && ( -z $stable_version || $actual == "$stable_version" ) ]]; then
                stable_version=$actual; consecutive=$((consecutive + 1))
            elif [[ $status == 2?? && -n $actual ]]; then
                stable_version=$actual; consecutive=1
            else consecutive=0; stable_version=''; fi
            [[ $consecutive -ge 5 ]] && break
            sleep 0.3
        done
        [[ $consecutive -ge 5 ]] || { ci_error 'Ingress did not converge to one consistent version.'; return 1; }
    fi
    for _ in $(seq 1 20); do
        body=$(mktemp)
        if [[ -n ${HOST_HEADER:-} ]]; then status=$(curl -H "Host: $HOST_HEADER" -sS --max-time 5 -o "$body" -w '%{http_code}' "$BASE/version") || status=000
        else status=$(curl -sS --max-time 5 -o "$body" -w '%{http_code}' "$BASE/version") || status=000; fi
        [[ $status == 2?? ]] || { rm -f "$body"; return 1; }
        actual=$(python3 - "$body" <<'PY'
import json,sys
try: print(json.load(open(sys.argv[1], encoding='utf-8')).get('version',''))
except (OSError, ValueError): raise SystemExit(1)
PY
) || { rm -f "$body"; return 1; }
        rm -f "$body"
        [[ -n $actual ]] || return 1
        [[ -z $expected || $actual == "$expected" ]] || { ci_error "Expected version $expected but observed $actual."; return 1; }
        versions+=("$actual")
    done
    if [[ $MODE == version-only ]]; then
        [[ $(printf '%s\n' "${versions[@]}" | sort -u | wc -l | tr -d ' ') == 1 ]] || { ci_error 'Pods did not return a consistent version.'; return 1; }
    fi
    printf 'PASS /version: %s responses, version(s) %s\n' "${#versions[@]}" "$(printf '%s\n' "${versions[@]}" | sort -u | paste -sd, -)"
}
verify_versions || fail_with_rollback '/version verification failed.'
[[ $MODE == version-only ]] && exit 0
if BASE="$BASE" HOST_HEADER="${HOST_HEADER:-}" bash "$ROOT/scripts/smoke.sh"; then [[ -n ${GITHUB_ENV:-} ]] && echo 'SMOKE_RESULT=passed' >> "$GITHUB_ENV"; else [[ -n ${GITHUB_ENV:-} ]] && echo 'SMOKE_RESULT=failed' >> "$GITHUB_ENV"; fail_with_rollback 'Smoke checks failed.'; fi
if [[ ! -x "$ROOT/.venv-load/bin/locust" ]]; then make -C "$ROOT" load-install; fi
if make -C "$ROOT" load-smoke BASE="$BASE" HOST_HEADER="${HOST_HEADER:-}"; then [[ -n ${GITHUB_ENV:-} ]] && echo 'LOAD_SMOKE_RESULT=passed' >> "$GITHUB_ENV"; else [[ -n ${GITHUB_ENV:-} ]] && echo 'LOAD_SMOKE_RESULT=failed' >> "$GITHUB_ENV"; fail_with_rollback 'Load-smoke failed.'; fi
if [[ ${VARIANT:-good} == good && ${PROBE_FAILED:-0} != 0 ]]; then fail_with_rollback "Zero-downtime probe recorded ${PROBE_FAILED} failed request(s)."; fi
[[ -n ${GITHUB_ENV:-} ]] && echo 'FINAL_STATUS=deployed' >> "$GITHUB_ENV"
echo 'All post-deploy checks passed.'
