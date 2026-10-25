#!/usr/bin/env python3
"""Archive original Ansible sources with Linux line endings for the demo Job."""

import argparse
import io
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.parent.mkdir(parents=True, exist_ok=True)
paths = [
    p
    for p in (root / "ansible").rglob("*")
    if p.is_file() and not any(x in p.parts for x in (".ansible", "evidence", ".cache"))
]
paths += [
    root / name
    for name in (
        "requirements-ansible.txt",
        "scripts/ansible-assert-recap.py",
        "scripts/ansible-k8s-demo.sh",
    )
]
with tarfile.open(args.output, "w:gz") as archive:
    for path in sorted(paths):
        data = path.read_bytes().replace(b"\r\n", b"\n")
        info = tarfile.TarInfo(path.relative_to(root).as_posix())
        info.size, info.mode = len(data), 0o644
        archive.addfile(info, io.BytesIO(data))
print(args.output)
