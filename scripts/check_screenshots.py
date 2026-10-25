#!/usr/bin/env python3
"""Validate screenshot presence, PNG integrity, size and duplicate evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROW = re.compile(r"^\|\s*\d+\s*\|\s*`([^`]+\.png)`\s*\|.*\|\s*(MUST|SHOULD|NICE)\s*\|\s*$")


def png_width(data: bytes) -> int:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("invalid PNG signature")
    offset, width, image_data = 8, 0, False
    while offset + 12 <= len(data):
        size = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + size]
        if offset + 12 + size > len(data):
            raise ValueError("truncated PNG chunk")
        crc = struct.unpack(">I", data[offset + 8 + size : offset + 12 + size])[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != crc:
            raise ValueError("PNG checksum mismatch")
        if kind == b"IHDR":
            width, height = struct.unpack(">II", payload[:8])
            if not width or not height:
                raise ValueError("empty PNG dimensions")
        image_data |= kind == b"IDAT"
        if kind == b"IEND" and width and image_data:
            return width
        offset += size + 12
    raise ValueError("incomplete PNG")


def inspect(root: Path) -> list[dict]:
    rows, hashes = [], {}
    for line in (root / "docs/screenshots/MANIFEST.md").read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if not match:
            continue
        name, priority = match.groups()
        path = root / "docs/screenshots" / name
        row = {"filename": name, "priority": priority, "status": "MISSING"}
        if path.is_file():
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            row["sha256"] = digest
            hashes.setdefault(digest, []).append(row)
            try:
                width = png_width(data)
                row["width"] = width
                row["status"] = "OK" if width >= 1000 else "TOO SMALL"
            except (ValueError, struct.error) as error:
                row["status"] = f"INVALID: {error}"
        rows.append(row)
    for matches in hashes.values():
        if len(matches) > 1:
            for row in matches:
                row["status"] = "DUPLICATE"
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    rows = inspect(args.root)
    if not rows:
        raise SystemExit("No screenshot requirements found; refusing an empty check.")
    for row in rows:
        print(f"{row['filename']:36} {row['priority']:7} {row['status']}")
    failed = [x for x in rows if x["priority"] == "MUST" and x["status"] != "OK"]
    print(
        f"Required evidence: {sum(x['priority'] == 'MUST' for x in rows) - len(failed)} "
        f"passed, {len(failed)} incomplete/invalid"
    )
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return int(args.strict and bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
