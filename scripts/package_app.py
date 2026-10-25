#!/usr/bin/env python3
"""Package source for the explicit source-demo overlay; no generated credentials."""

import argparse
import io
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.parent.mkdir(parents=True, exist_ok=True)
with tarfile.open(args.output, "w:gz") as archive:
    paths = [p for p in (root / "app").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    paths.append(root / "requirements.txt")
    for path in sorted(paths):
        data = path.read_bytes().replace(b"\r\n", b"\n")
        info = tarfile.TarInfo(path.relative_to(root).as_posix())
        info.size = len(data)
        info.mode = 0o644
        archive.addfile(info, io.BytesIO(data))
print(args.output)
