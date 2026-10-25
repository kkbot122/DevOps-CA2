#!/usr/bin/env python3
"""Smoke-test a real running service; never substitute fixture data for evidence."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8001")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    base = args.base.rstrip("/")
    checks = []

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect)

    def request(path, expected, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            base + path,
            data=data,
            headers={"Content-Type": "application/json", "X-Forwarded-For": "198.51.100.201"},
        )
        started = time.perf_counter()
        try:
            response = opener.open(req, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        content = response.read().decode()
        status = response.code
        checks.append(
            {
                "path": path,
                "status": status,
                "expected": expected,
                "pass": status == expected,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )
        if status != expected:
            raise RuntimeError(f"{path}: expected {expected}, received {status}: {content[:120]}")
        return content, response.headers

    failure = None
    try:
        request("/", 200)
        request("/healthz", 200)
        request("/readyz", 200)
        request("/version", 200)
        code = "check-" + uuid.uuid4().hex[:10]
        created, _ = request("/api/shorten", 201, {"url": "https://example.com/", "alias": code})
        if json.loads(created)["code"] != code:
            raise RuntimeError("Created code differs from requested alias")
        _, headers = request("/" + code, 302)
        if headers.get("Location") != "https://example.com/":
            raise RuntimeError("Redirect destination differs from the original URL")
        stats, _ = request("/api/links/" + code + "/stats", 200)
        if json.loads(stats)["clicks"] != 1:
            raise RuntimeError("Click count was not incremented")
        request("/api/shorten", 409, {"url": "https://example.com/", "alias": code})
        request("/api/shorten", 422, {"url": "ftp://example.com/"})
        request("/api/shorten", 403, {"url": "https://evil.example/"})
        metrics, _ = request("/metrics", 200)
        if "http_request_duration_seconds_bucket" not in metrics:
            raise RuntimeError("Latency histogram is missing from /metrics")
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        failure = str(error)
    result = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "base": base,
        "checks": checks,
        "pass": failure is None,
        "error": failure,
    }
    for check in checks:
        print(f"{'PASS' if check['pass'] else 'FAIL'} {check['path']} HTTP {check['status']}")
    if failure:
        print("FAIL " + failure)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return int(failure is not None)


if __name__ == "__main__":
    raise SystemExit(main())
