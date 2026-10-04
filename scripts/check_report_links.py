#!/usr/bin/env python3
"""Check relative Markdown links in the report entry points."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "docs/REPORT.md",
    ROOT / "README.md",
    ROOT / "submission/README.md",
    ROOT / "docs/screenshots/MANIFEST.md",
]
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
failures: list[str] = []
checked = 0

for source in FILES:
    text = source.read_text(encoding="utf-8")
    for raw_target in LINK.findall(text):
        target = raw_target.strip().split()[0].strip("<>")
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        relative_path = target.split("#", 1)[0]
        if not relative_path:
            continue
        checked += 1
        resolved = (source.parent / relative_path).resolve()
        if not resolved.exists():
            failures.append(f"{source.relative_to(ROOT)}: {target}")

print(f"LINK CHECK: checked {checked} relative links across {len(FILES)} files")
if failures:
    print("FAIL: unresolved relative links")
    print("\n".join(failures))
    sys.exit(1)
print("PASS: all links resolve")
