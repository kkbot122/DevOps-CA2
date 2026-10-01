#!/usr/bin/env bash
# Usage: scripts/ci/scan-summary.sh [trivy-config.txt]; appends report-only findings to job summary.
set -euo pipefail
file=${1:-trivy-config.txt}
summary=${SUMMARY_FILE:-${GITHUB_STEP_SUMMARY:-/dev/stdout}}
{
    echo '### Trivy configuration scan (report only)'
    echo
    if [[ -s $file ]]; then echo '```text'; cat "$file"; echo '```'; else echo 'No configuration report was produced.'; fi
} >> "$summary"
