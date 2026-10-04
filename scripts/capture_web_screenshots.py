#!/usr/bin/env python3
"""Capture web pages only when the real local project UI is reachable."""

from __future__ import annotations

import base64
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIPPED: Playwright is not installed; all web UI captures remain manual.")
        print("Terminal screenshots are always manual.")
        return 0

    targets = [
        (
            "01-baseline-overview.png",
            "http://localhost:3000/d/shortly-overview/shortly-overview?var-datasource=prometheus&kiosk",
            "admin",
            "demo-grafana-pass",
        ),
        ("20-alert-firing.png", "http://localhost:9093", None, None),
        ("28-prometheus-targets.png", "http://localhost:9090/targets", None, None),
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        for filename, url, username, password in targets:
            try:
                with urllib.request.urlopen(url, timeout=3):
                    pass
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                print(f"SKIPPED {filename}: {url} is unreachable ({error}).")
                continue
            try:
                if username:
                    authorization = base64.b64encode(f"{username}:{password}".encode()).decode()
                    page.set_extra_http_headers({"Authorization": f"Basic {authorization}"})
                response = page.goto(url, wait_until="networkidle", timeout=15000)
                if response is None or response.status >= 400:
                    status = response.status if response else "no response"
                    print(f"SKIPPED {filename}: page returned HTTP {status}.")
                    continue
                page.screenshot(path=str(OUT / filename), full_page=True)
                print(f"CAPTURED {filename} from live {url}")
            except Exception as error:
                print(f"SKIPPED {filename}: could not render live page ({error}).")
        report = ROOT / "loadtest" / "reports" / "baseline" / "report.html"
        if report.is_file():
            filename = "29-locust-baseline.png"
            try:
                response = page.goto(report.resolve().as_uri(), wait_until="load", timeout=10000)
                if response is None:
                    print(f"SKIPPED {filename}: local report did not open.")
                else:
                    page.screenshot(path=str(OUT / filename), full_page=True)
                    print(f"CAPTURED {filename} from existing report {report.relative_to(ROOT)}")
            except Exception as error:
                print(f"SKIPPED {filename}: could not render existing report ({error}).")
        else:
            print(f"SKIPPED 29-locust-baseline.png: {report.relative_to(ROOT)} does not exist.")
        browser.close()
    print("Terminal screenshots are always manual.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
