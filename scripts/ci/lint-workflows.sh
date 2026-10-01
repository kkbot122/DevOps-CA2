#!/usr/bin/env bash
# Usage: scripts/ci/lint-workflows.sh; downloads pinned kubeconform/actionlint releases, then validates manifests and workflows.
set -euo pipefail
tmp=${RUNNER_TEMP:-/tmp}/shortly-ci-lint
mkdir -p "$tmp"
curl -fsSL https://github.com/yannh/kubeconform/releases/download/v0.7.0/kubeconform-linux-amd64.tar.gz -o "$tmp/kubeconform.tar.gz"
tar -xzf "$tmp/kubeconform.tar.gz" -C "$tmp" kubeconform
curl -fsSL https://github.com/rhysd/actionlint/releases/download/v1.7.7/actionlint_1.7.7_linux_amd64.tar.gz -o "$tmp/actionlint.tar.gz"
tar -xzf "$tmp/actionlint.tar.gz" -C "$tmp" actionlint
"$tmp/kubeconform" -strict -ignore-missing-schemas k8s/
"$tmp/actionlint" .github/workflows/*.yml
