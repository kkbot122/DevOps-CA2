#!/usr/bin/env python3
"""Run every provisioned dashboard PromQL target through the Prometheus API proxy."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote


PROM_NS = os.environ.get("MON_NS", "monitoring")
PROM_SVC = os.environ.get("PROM_SVC", "kube-prometheus-stack-prometheus")
DASHBOARD = Path(__file__).resolve().parents[1] / "monitoring/dashboards/shortly-overview.json"
MACROS = {
    "$__rate_interval": "1m",
    "$__interval": "1m",
    "$__range_s": "900",
    "$__range": "15m",
}


def panels(items: list[dict]):
    for panel in items:
        yield panel
        yield from panels(panel.get("panels", []))


def prom_query(expression: str) -> dict:
    for macro, value in MACROS.items():
        expression = expression.replace(macro, value)
    path = (
        f"/api/v1/namespaces/{PROM_NS}/services/{PROM_SVC}:9090/proxy/"
        f"api/v1/query?query={quote(expression, safe='')}"
    )
    result = subprocess.run(
        ["kubectl", "get", "--raw", path],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return json.loads(result.stdout)


def main() -> int:
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    failures = 0
    empty_ok: list[str] = []
    checked = 0
    for panel in panels(dashboard.get("panels", [])):
        title = panel.get("title", "untitled panel")
        for target in panel.get("targets", []):
            expression = target.get("expr", "").strip()
            if not expression:
                continue
            checked += 1
            try:
                response = prom_query(expression)
                if response.get("status") != "success":
                    failures += 1
                    error = response.get("error", "invalid query")
                    print(f"FAIL {title}: {error}")
                    continue
                results = response.get("data", {}).get("result", [])
                if results:
                    print(f"PASS {title}: data ({len(results)} series)")
                else:
                    allowed = bool(re.search(r"5xx|429|restart", title, re.IGNORECASE))
                    if allowed:
                        empty_ok.append(title)
                        print(f"PASS {title}: EMPTY(ok?)")
                    else:
                        failures += 1
                        print(f"FAIL {title}: EMPTY(unexpected)")
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
                failures += 1
                print(f"FAIL {title}: {exc}")
    print(f"Checked {checked} dashboard queries; invalid/empty-unexpected: {failures}")
    if empty_ok:
        print("EMPTY(ok?) panels: " + ", ".join(sorted(set(empty_ok))))
    else:
        print("EMPTY(ok?) panels: none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
