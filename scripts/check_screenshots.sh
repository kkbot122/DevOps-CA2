#!/usr/bin/env bash
set -euo pipefail
strict=0
for arg in "$@"; do
  case "$arg" in
    --strict) strict=1 ;;
    *) echo "Usage: $0 [--strict]" >&2; exit 2 ;;
  esac
done
python3 - "$strict" <<'PY'
import hashlib
import re
import subprocess
import sys
from pathlib import Path

strict = sys.argv[1] == "1"
root = Path.cwd()
manifest = root / "docs/screenshots/MANIFEST.md"
table_row = re.compile(r"^\|\s*\d+\s*\|\s*`([^`]+\.png)`\s*\|.*\|\s*(MUST|SHOULD|NICE)\s*\|\s*$")
rows = []
for line in manifest.read_text(encoding="utf-8").splitlines():
    match = table_row.match(line)
    if match:
        rows.append((match.group(1), match.group(2)))

counts = {priority: [0, 0] for priority in ("MUST", "SHOULD", "NICE")}
hashes = {}
must_missing = 0
print(f"{'Filename':34} {'Priority':8} Status")
print("-" * 66)
for name, priority in rows:
    path = root / "docs/screenshots" / name
    status = "MISSING"
    if path.is_file():
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        hashes.setdefault(digest, []).append(name)
        width = 0
        try:
            result = subprocess.run(["sips", "-g", "pixelWidth", str(path)], capture_output=True, text=True, check=True)
            found = re.search(r"pixelWidth:\s*(\d+)", result.stdout)
            width = int(found.group(1)) if found else 0
        except (FileNotFoundError, subprocess.CalledProcessError):
            try:
                from PIL import Image

                with Image.open(path) as image:
                    width = image.width
            except Exception:
                width = 0
        status = "OK" if width >= 1000 else f"TOO SMALL ({width or 'unknown'} px wide)"
        counts[priority][1] += 1
    else:
        counts[priority][0] += 1
        if priority == "MUST":
            must_missing += 1
    print(f"{name:34} {priority:8} {status}")

for dupes in hashes.values():
    if len(dupes) > 1:
        print("WARNING duplicate image hash: " + ", ".join(dupes))
print(", ".join(f"{key} {counts[key][1]}/{counts[key][0] + counts[key][1]}" for key in counts))
if strict and must_missing:
    raise SystemExit(1)
PY
