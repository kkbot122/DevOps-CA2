#!/usr/bin/env python3
"""Fail when an Ansible recap does not show the expected changed/failed counts."""

import argparse
import re
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("recap", type=Path)
parser.add_argument("--changed", type=int)
parser.add_argument("--min-changed", type=int)
parser.add_argument("--failed", type=int, default=0)
parser.add_argument("--host", default="localhost")
args = parser.parse_args()
contents = args.recap.read_text(encoding="utf-8")
host = re.escape(args.host)
recap_pattern = (
    rf"{host}\s+:\s+ok=(\d+)\s+changed=(\d+)\s+"
    r"unreachable=(\d+)\s+failed=(\d+)"
)
matches = re.findall(recap_pattern, contents)
if not matches:
    raise SystemExit(f"No localhost PLAY RECAP found in {args.recap}")
if args.changed is None and args.min_changed is None:
    raise SystemExit("Specify --changed or --min-changed")
ok, changed, unreachable, failed = map(int, matches[-1])
print(f"recap: ok={ok} changed={changed} unreachable={unreachable} failed={failed}")
changed_matches = (
    changed == args.changed if args.min_changed is None else changed >= args.min_changed
)
if not changed_matches or failed != args.failed or unreachable:
    raise SystemExit("Ansible recap did not match the required counts")
