#!/usr/bin/env bash
# Usage: scripts/ci/summary.sh; writes markdown to GITHUB_STEP_SUMMARY or stdout.
set -euo pipefail
out=${GITHUB_STEP_SUMMARY:-/dev/stdout}
commit=${GITHUB_SHA:-unknown}; variant=${VARIANT:-good}; image=${IMAGE_REF:-unknown}; digest=${IMAGE_DIGEST:-unknown}
{
    echo '## Shortly CI/CD deployment summary'
    echo
    echo '| Field | Result |'
    echo '|---|---|'
    printf '| Commit | `%s` |\n| Variant | `%s` |\n| Image | `%s` |\n| Digest | `%s` |\n' "$commit" "$variant" "$image" "$digest"
    printf '| Revision | %s → %s |\n| Rollout duration | %ss |\n| Probe requests | %s total / %s failed; versions `%s` |\n' "${PREVIOUS_REVISION:-unknown}" "${NEW_REVISION:-unknown}" "${ROLLOUT_DURATION:-unknown}" "${PROBE_TOTAL:-unknown}" "${PROBE_FAILED:-unknown}" "${PROBE_VERSIONS:-unknown}"
    printf '| Smoke | %s |\n| Load-smoke | %s |\n| Final status | **%s** |\n' "${SMOKE_RESULT:-not run}" "${LOAD_SMOKE_RESULT:-not run}" "${FINAL_STATUS:-failed or incomplete}"
} >> "$out"
