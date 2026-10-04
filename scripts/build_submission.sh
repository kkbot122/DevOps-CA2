#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
dest="$root/dist/DevOps-CA2"
python3 - "$root" "$dest" <<'PY'
import shutil
import sys
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
if destination.exists():
    shutil.rmtree(destination)

def ignore(directory: str, names: list[str]) -> set[str]:
    excluded = set()
    for name in names:
        if name in {".git", "dist", "__pycache__", ".pytest_cache", ".ruff_cache", ".coverage", "htmlcov", ".DS_Store", ".ansible", ".cache"}:
            excluded.add(name)
        elif name.startswith(".venv") or name.endswith((".pyc", ".pyo")):
            excluded.add(name)
        elif name in {".env", "kubeconfig"}:
            excluded.add(name)
        elif name.startswith(".env.") and name not in {".env.example", ".env.sample"}:
            excluded.add(name)
        elif name in {"locust.log", "request-times.csv", "report.html"}:
            excluded.add(name)
        elif name.endswith("_stats.csv") or name.endswith("_stats_history.csv"):
            excluded.add(name)
    return excluded

shutil.copytree(source, destination, ignore=ignore, dirs_exist_ok=True)
PY
python3 "$root/scripts/check_submission_secrets.py" "$dest"
printf '\nAssembled tree (two levels):\n'
find "$dest" -mindepth 1 -maxdepth 2 -print | sed "s#^$root/##" | sort
printf '\nFolder size:\n'
du -sh "$dest"
cat <<'EOF'

When ready, run these commands yourself; this target does not push:
cd dist/DevOps-CA2
git init
git branch -M main
git add .
git commit -m "Submit DevOps CA2 project"
git remote add origin https://github.com/aditisharmas11/DevOps-CA2_2023_27.git
git push -u origin main
EOF
