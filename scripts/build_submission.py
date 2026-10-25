#!/usr/bin/env python3
"""Assemble a fresh submission without overwriting existing files."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {
    ".git",
    "dist",
    ".runtime",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".coverage",
    "htmlcov",
    ".DS_Store",
    ".ansible",
    ".cache",
    "coverage.xml",
}


def ignore(directory, names):
    return {
        name
        for name in names
        if name in EXCLUDED
        or name.startswith(".venv")
        or name.endswith((".pyc", ".pyo"))
        or name in {".env", "kubeconfig", "locust.log"}
        or (name.startswith(".env.") and name not in {".env.example", ".env.sample"})
        or name.endswith(("_stats.csv", "_stats_history.csv", "request-times.csv"))
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/DevOps-CA2")
    parser.add_argument("--zip", action="store_true")
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination.exists():
        raise SystemExit("Destination already exists; choose a new output directory.")
    if destination == ROOT or destination in ROOT.parents:
        raise SystemExit("Refusing to overwrite the source tree or an ancestor.")
    if destination.is_relative_to(ROOT) and not destination.is_relative_to(ROOT / "dist"):
        raise SystemExit("Use dist/ for a destination inside the source repository.")
    archive = Path(str(destination) + ".zip")
    if args.zip and archive.exists():
        raise SystemExit("ZIP already exists; choose a new output destination.")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_screenshots.py"), "--strict"], check=False
    )
    if result.returncode:
        return result.returncode
    shutil.copytree(ROOT, destination, ignore=ignore)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_submission_secrets.py"), str(destination)],
        check=False,
    )
    if result.returncode:
        print("Credential scan failed; folder retained for review. No ZIP created.")
        return result.returncode
    print("Assembled:", destination)
    if args.zip:
        shutil.make_archive(str(destination), "zip", destination.parent, destination.name)
        print("ZIP:", archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
