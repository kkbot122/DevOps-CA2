#!/usr/bin/env bash
# Usage: BASE=http://short.local [HOST_HEADER=short.local] scripts/smoke.sh
set -euo pipefail

BASE=${BASE:-http://short.local}
BASE=${BASE%/}
curl_request() {
    if [[ -n ${HOST_HEADER:-} ]]; then
        curl -H "Host: $HOST_HEADER" "$@"
    else
        curl "$@"
    fi
}
body_file=$(mktemp)
header_file=$(mktemp)
failures=0
ip="198.51.$((RANDOM % 256)).$((RANDOM % 254 + 1))"
alias="smoke-${RANDOM}-$(date +%s)"
destination="https://example.com/smoke"

cleanup() {
    rm -f "$body_file" "$header_file"
}
trap cleanup EXIT

check_status() {
    local label=$1 expected=$2 actual=$3
    if [[ $actual == "$expected" ]]; then
        printf 'PASS %s (HTTP %s)\n' "$label" "$actual"
    else
        printf 'FAIL %s (expected HTTP %s, got %s)\n' "$label" "$expected" "$actual"
        failures=$((failures + 1))
    fi
}

request() {
    local status
    status=$(curl_request -sS --max-time 8 -o "$body_file" -w '%{http_code}' "$@") || status=000
    printf '%s' "$status"
}

status=$(request "$BASE/")
check_status 'home page' 200 "$status"
if [[ $status == 200 ]] && grep -qi shortly "$body_file"; then
    echo 'PASS home page contains shortly'
else
    echo 'FAIL home page content'
    failures=$((failures + 1))
fi

status=$(request "$BASE/healthz")
check_status 'liveness' 200 "$status"
status=$(request "$BASE/readyz")
check_status 'readiness' 200 "$status"

status=$(request -X POST "$BASE/api/shorten" \
    -H 'Content-Type: application/json' -H "X-Forwarded-For: $ip" \
    -d "{\"url\":\"$destination\",\"alias\":\"$alias\"}")
check_status 'shorten' 201 "$status"
if [[ $status == 201 ]]; then
    code=$(python3 - "$body_file" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["code"])
PY
    )
    status=$(curl_request -sS --max-time 8 -D "$header_file" -o "$body_file" -w '%{http_code}' "$BASE/$code") || status=000
    check_status 'redirect' 302 "$status"
    if [[ $status == 302 ]] && grep -Fqi "location: $destination" "$header_file"; then
        echo 'PASS redirect Location'
    else
        location=$(awk 'tolower($1)=="location:" { sub(/\r$/, "", $2); print $2 }' "$header_file")
        if [[ $location == "$destination" ]]; then
            echo 'PASS redirect Location'
        else
            printf 'FAIL redirect Location (got %s)\n' "${location:-missing}"
            failures=$((failures + 1))
        fi
    fi
else
    echo 'FAIL redirect skipped because link creation failed'
    failures=$((failures + 1))
fi

status=$(request "$BASE/no-such-smoke-code")
check_status 'unknown code' 404 "$status"

status=$(request -X POST "$BASE/api/shorten" \
    -H 'Content-Type: application/json' -H "X-Forwarded-For: $ip" \
    -d "{\"url\":\"https://example.org/duplicate\",\"alias\":\"$alias\"}")
check_status 'duplicate alias' 409 "$status"

status=$(request -X POST "$BASE/api/shorten" \
    -H 'Content-Type: application/json' -H "X-Forwarded-For: $ip" \
    -d '{"url":"ftp://example.com"}')
check_status 'invalid URL' 422 "$status"

status=$(request -X POST "$BASE/api/shorten" \
    -H 'Content-Type: application/json' -H "X-Forwarded-For: $ip" \
    -d '{"url":"https://evil.example/path"}')
check_status 'blocked domain' 403 "$status"

if (( failures > 0 )); then
    printf '%s smoke check(s) failed\n' "$failures"
    exit 1
fi
echo 'All smoke checks passed.'
