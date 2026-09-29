#!/usr/bin/env bash
# Throwaway dashboard-verification traffic only; Phase 4 Locust covers real user behavior.
# Usage: BASE=http://short.local DURATION=120 bash scripts/traffic.sh [seconds]
set -euo pipefail

BASE=${BASE:-http://short.local}; BASE=${BASE%/}
HOST_HEADER=${HOST_HEADER:-}
DURATION=${DURATION:-${1:-120}}
body=$(mktemp)
status_file=$(mktemp)
print_counts() {
    echo 'Traffic status counts:'
    if [[ -s $status_file ]]; then sort "$status_file" | uniq -c | awk '{ printf "  HTTP %s: %s\n", $2, $1 }'; fi
}
trap 'rm -f "$body" "$status_file"' EXIT
trap 'print_counts; exit 130' INT
codes=()
alias="traffic-$RANDOM-$SECONDS"
headers=(); [[ -n $HOST_HEADER ]] && headers=(-H "Host: $HOST_HEADER")

request() {
    local method=$1 path=$2 ip=$3 data=${4:-} status
    if [[ $method == POST ]]; then
        status=$(curl -sS --max-time 5 -o "$body" -w '%{http_code}' -X POST "${headers[@]}" "$BASE$path" -H 'Content-Type: application/json' -H "X-Forwarded-For: $ip" -d "$data") || status=000
    else
        status=$(curl -sS --max-time 5 -o "$body" -w '%{http_code}' "${headers[@]}" "$BASE$path" -H "X-Forwarded-For: $ip") || status=000
    fi
    printf '%s\n' "$status" >> "$status_file"; last_status=$status
}

request POST /api/shorten "198.51.100.$((RANDOM % 254 + 1))" "{\"url\":\"https://example.com/traffic\",\"alias\":\"$alias\"}"
if [[ $last_status == 201 ]]; then codes+=($(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["code"])' "$body")); fi
burst_ip=203.0.113.254
for _ in $(seq 1 12); do request POST /api/shorten "$burst_ip" '{"url":"https://example.com/burst"}' >/dev/null; done

end=$((SECONDS + DURATION))
while (( SECONDS < end )); do
    ip="198.51.100.$((RANDOM % 254 + 1))"
    case $((RANDOM % 10)) in
        0) alias="traffic-$RANDOM-$SECONDS"; request POST /api/shorten "$ip" "{\"url\":\"https://example.com/$SECONDS\",\"alias\":\"$alias\"}"; [[ $last_status == 201 ]] && codes+=($(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["code"])' "$body")) ;;
        1) request GET "/missing-$RANDOM" "$ip" >/dev/null ;;
        2) request POST /api/shorten "$ip" "{\"url\":\"https://example.org/duplicate\",\"alias\":\"$alias\"}" >/dev/null ;;
        3) request POST /api/shorten "$ip" '{"url":"ftp://example.com"}' >/dev/null ;;
        4) request POST /api/shorten "$ip" '{"url":"https://evil.example/path"}' >/dev/null ;;
        *) if ((${#codes[@]})); then request GET "/${codes[RANDOM % ${#codes[@]}]}" "$ip" >/dev/null; else request GET /healthz "$ip" >/dev/null; fi ;;
    esac
    sleep 0.1
done

print_counts
