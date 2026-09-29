#!/usr/bin/env bash
# Usage: BASE=http://short.local [HOST_HEADER=short.local] scripts/probe.sh
set -euo pipefail

BASE=${BASE:-http://short.local}
curl_args=()
if [[ -n ${HOST_HEADER:-} ]]; then
    curl_args+=(-H "Host: $HOST_HEADER")
fi
total=0
failures=0
last_pair=
body_file=$(mktemp)
versions_file=$(mktemp)

print_summary() {
    printf '\nProbe summary\nRequests: %s\nNon-2xx or failed: %s\n' "$total" "$failures"
    if [[ -s $versions_file ]]; then
        echo 'Requests per version:'
        sort "$versions_file" | uniq -c
    else
        echo 'Requests per version: none'
    fi
    rm -f "$body_file" "$versions_file"
}

on_signal() {
    trap - INT TERM EXIT
    print_summary
    exit 0
}

trap on_signal INT TERM

while true; do
    total=$((total + 1))
    http=$(curl "${curl_args[@]}" -sS --max-time 2 -o "$body_file" -w '%{http_code}' "$BASE/version" 2>/dev/null) || http=000
    if [[ $http == 2?? ]]; then
        pair=$(
            python3 - "$body_file" <<'PY'
import json
import sys

try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    print(f"{data['version']}\t{data['hostname']}")
except (OSError, KeyError, json.JSONDecodeError, TypeError):
    raise SystemExit(1)
PY
        ) || pair=
        if [[ -n $pair ]]; then
            version=${pair%%$'\t'*}
            hostname=${pair#*$'\t'}
            printf '%s\n' "$version" >> "$versions_file"
            if [[ $pair != "$last_pair" ]]; then
                printf '%s %s %s\n' "$(date +%H:%M:%S)" "$version" "$hostname"
                last_pair=$pair
            fi
        else
            failures=$((failures + 1))
            printf '%s FAIL http=%s\n' "$(date +%H:%M:%S)" "$http"
        fi
    else
        failures=$((failures + 1))
        printf '%s FAIL http=%s\n' "$(date +%H:%M:%S)" "$http"
    fi
    sleep 0.2
done
