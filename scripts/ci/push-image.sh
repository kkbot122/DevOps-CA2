#!/usr/bin/env bash
# Usage: IMAGE=<single image tag> GH_TOKEN=<GITHUB_TOKEN> scripts/ci/push-image.sh; writes digest output.
set -euo pipefail
image=${IMAGE:?IMAGE is required}
token=${GH_TOKEN:?GH_TOKEN is required}
printf '%s' "$token" | docker login ghcr.io -u "${GITHUB_ACTOR:-github-actions[bot]}" --password-stdin
push_output=$(docker push "$image" 2>&1) || { printf '%s\n' "$push_output" >&2; exit 1; }
printf '%s\n' "$push_output"
digest=$(printf '%s\n' "$push_output" | grep -oE 'sha256:[0-9a-f]{64}' | tail -n 1 || true)
[[ $digest =~ ^sha256:[0-9a-f]{64}$ ]] || { echo 'Could not extract a valid pushed image digest.' >&2; exit 1; }
printf 'digest=%s\n' "$digest" >> "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
