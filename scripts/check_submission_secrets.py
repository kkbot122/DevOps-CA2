#!/usr/bin/env python3
"""Reject apparent non-demo credentials from the assembled submission tree."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/DevOps-CA2")
ALLOWED = {
    "change-me",
    "demo-admin-token",
    "demo-grafana-pass",
    "test-token",
    "choose-a-local-demo-token",
    "your-token",
}
ASSIGNMENT = re.compile(
    r"(?i)\b([\w.-]*(?:TOKEN|PASSWORD|SECRET))\s*(?::\s*(?:str\s*=\s*)?|=\s*)"
    r"(?:['\"]([^'\"]+)['\"]|([A-Za-z0-9._-]+))"
)
TOKEN_PATTERNS = [
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]
issues: list[str] = []

for path in ROOT.rglob("*"):
    if not path.is_file() or path.suffix.lower() in {
        ".png",
        ".jpg",
        ".jpeg",
        ".pdf",
        ".pptx",
        ".zip",
        ".pyc",
    }:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    for line_number, line in enumerate(text.splitlines(), 1):
        for match in ASSIGNMENT.finditer(line):
            value = (match.group(2) or match.group(3) or "").strip().strip(")}")
            if value in ALLOWED or value in {"str", "string", "-"}:
                continue
            if value.startswith("${") or value.startswith("{{") or value.startswith(":"):
                continue
            if value.startswith("$"):
                continue
            if value.startswith("os.getenv"):
                continue
            issues.append(
                f"{path.relative_to(ROOT)}:{line_number}: unexpected {match.group(1)} value"
            )
        for pattern in TOKEN_PATTERNS:
            if pattern.search(line):
                issues.append(f"{path.relative_to(ROOT)}:{line_number}: token-shaped value")

if issues:
    print("FAIL submission credential scan:")
    print("\n".join(issues))
    raise SystemExit(1)
print("PASS submission credential scan: demo defaults, test fixture and placeholders only")
