#!/usr/bin/env bash
# Usage: EVENT_NAME=... INPUT_VARIANT=... SHA=... scripts/ci/resolve-variant.sh; writes GitHub outputs.
set -euo pipefail
event=${EVENT_NAME:-push}
sha=${SHA:-$(git rev-parse HEAD)}
tag=${sha:0:7}
variant=good
bad_mode=none
if [[ $event == workflow_dispatch ]]; then
    variant=${INPUT_VARIANT:-good}
    case "$variant" in
        good) bad_mode=none ;;
        bad-errors) bad_mode=errors; tag+="-bad-errors" ;;
        bad-crash) bad_mode=crash; tag+="-bad-crash" ;;
        *) echo "Unsupported variant: $variant" >&2; exit 2 ;;
    esac
fi
if [[ -n ${GITHUB_OUTPUT:-} ]]; then
    printf 'tag=%s\nvariant=%s\nbad_mode=%s\n' "$tag" "$variant" "$bad_mode" >> "$GITHUB_OUTPUT"
else
    printf 'tag=%s\nvariant=%s\nbad_mode=%s\n' "$tag" "$variant" "$bad_mode"
fi
