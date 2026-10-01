#!/usr/bin/env bash
# Usage: source scripts/ci/lib.sh; provides log_group, error, rollback_deployment.
set -euo pipefail

ci_group() { printf '::group::%s\n' "$*"; }
ci_endgroup() { printf '::endgroup::\n'; }
ci_error() { printf '::error::%s\n' "$*" >&2; }
ci_log() { printf '[ci] %s\n' "$*"; }

rollback_deployment() {
    local namespace=${NS:-urlshortener}
    local previous_revision=${PREVIOUS_REVISION:-}
    local previous_image=${PREVIOUS_IMAGE:-unknown}
    if [[ ${AUTO_ROLLBACK:-true} != true ]]; then
        ci_log 'Automatic rollback is disabled; leaving the current Deployment unchanged.'
        [[ -n ${GITHUB_ENV:-} ]] && printf 'FINAL_STATUS=failed (left in place)\n' >> "$GITHUB_ENV"
        return 0
    fi
    ci_group "Rolling back deployment in $namespace"
    if [[ -n $previous_revision && $previous_revision =~ ^[0-9]+$ ]]; then
        kubectl -n "$namespace" rollout undo deployment/shortly --to-revision="$previous_revision"
    else
        kubectl -n "$namespace" rollout undo deployment/shortly
    fi
    kubectl -n "$namespace" rollout status deployment/shortly --timeout=150s
    ci_log "rolled back to revision ${previous_revision:-previous} (image $previous_image)"
    if [[ -n ${GITHUB_ENV:-} ]]; then
        printf 'FINAL_STATUS=rolled back\n' >> "$GITHUB_ENV"
    fi
    ci_endgroup
}

fail_with_rollback() {
    local message=$1
    ci_error "$message"
    if [[ ${AUTO_ROLLBACK:-true} == true ]]; then
        if ! rollback_deployment; then ci_error 'Automatic rollback failed; inspect the Deployment immediately.'; fi
    fi
    exit 1
}
