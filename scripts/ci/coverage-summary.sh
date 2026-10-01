#!/usr/bin/env bash
# Usage: scripts/ci/coverage-summary.sh [coverage.xml]; writes coverage percentage to the job summary.
set -euo pipefail
file=${1:-coverage.xml}
python - "$file" "${GITHUB_STEP_SUMMARY:-}" <<'PY'
import sys
import xml.etree.ElementTree as ET
file, summary = sys.argv[1:]
try:
    root = ET.parse(file).getroot()
    pct = float(root.attrib.get("line-rate", "0")) * 100
    msg = f"Coverage: **{pct:.2f}%**"
except (OSError, ET.ParseError, ValueError) as exc:
    msg = f"Coverage report unavailable: {exc}"
print(msg)
if summary:
    with open(summary, "a", encoding="utf-8") as stream:
        stream.write(msg + "\n")
PY
