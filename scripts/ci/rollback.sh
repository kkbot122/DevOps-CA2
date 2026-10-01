#!/usr/bin/env bash
# Usage: TO_REVISION=<optional-number> scripts/ci/rollback.sh; applies the previous or requested revision.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
source "$ROOT/scripts/ci/lib.sh"
NS=${NS:-urlshortener}
TO_REVISION=${TO_REVISION:-}
PREVIOUS_REVISION=$(kubectl -n "$NS" get deployment shortly -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/revision}')
PREVIOUS_IMAGE=$(kubectl -n "$NS" get deployment shortly -o jsonpath='{.spec.template.spec.containers[?(@.name=="shortly")].image}')
export PREVIOUS_REVISION PREVIOUS_IMAGE AUTO_ROLLBACK=true
if [[ -n $TO_REVISION ]]; then
    [[ $TO_REVISION =~ ^[0-9]+$ ]] || { ci_error 'to_revision must be a positive integer.'; exit 2; }
    kubectl -n "$NS" rollout undo deployment/shortly --to-revision="$TO_REVISION"
else
    kubectl -n "$NS" rollout undo deployment/shortly
fi
kubectl -n "$NS" rollout status deployment/shortly --timeout=150s
AUTO_ROLLBACK=false MODE=version-only EXPECTED_VERSION='' bash "$ROOT/scripts/ci/verify.sh" --version-only
[[ -n ${GITHUB_ENV:-} ]] && printf 'FINAL_STATUS=manual rollback\nPREVIOUS_REVISION=%s\nPREVIOUS_IMAGE=%s\n' "$PREVIOUS_REVISION" "$PREVIOUS_IMAGE" >> "$GITHUB_ENV"
echo 'Manual rollback completed and version consistency verified.'
