#!/usr/bin/env python3
"""Run one Shortly demo scenario; this coordinator uses only Python's stdlib."""

from __future__ import annotations

import csv
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "loadtest" / "reports"
LOCUST = ROOT / ".venv-load" / "bin" / "locust"
BASE = os.getenv("BASE", "http://short.local").rstrip("/")
HOST_HEADER = os.getenv("HOST_HEADER", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "demo-admin-token")
NS = os.getenv("NS", "urlshortener")
MON_NS = os.getenv("MON_NS", "monitoring")
PROM_SVC = os.getenv("PROM_SVC", "kube-prometheus-stack-prometheus")
WEIGHTS = "visitor=60,creator=25,power=10,abuser=5"
SCENARIOS = [
    "baseline",
    "abuse",
    "latency",
    "errors",
    "redis-down",
    "good-release",
    "bad-release-errors",
    "bad-release-crash",
    "surge",
]
DESCRIPTIONS = {
    "baseline": "3 min of normal mixed-persona behavior; no faults",
    "latency": "800 ms injected latency, alert and recovery",
    "errors": "30% injected 5xx, alert and recovery",
    "redis-down": "Redis outage, readiness, alerting, and PVC durability",
    "good-release": "zero-downtime v1 to v2 rolling release",
    "bad-release-crash": "crash-looping rollout, alert, then rollback",
    "bad-release-errors": "Ready but broken v2, error alert, then rollback",
    "surge": "0 to 200 users, HPA scale-up and scale-down",
    "abuse": "shared-IP bad-actor traffic and client-error alert hygiene",
}
DURATIONS = {
    "baseline": "4 min",
    "abuse": "4 min",
    "latency": "3–8 min",
    "errors": "5–9 min",
    "redis-down": "4–9 min",
    "good-release": "2–4 min",
    "bad-release-errors": "5–10 min",
    "bad-release-crash": "3–6 min",
    "surge": "8–12 min",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def log(message: str) -> None:
    print(f"[{now()}] {message}", flush=True)


def request(
    url: str,
    method: str = "GET",
    body: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 5,
) -> tuple[int, bytes, dict]:
    raw = json.dumps(body).encode() if body is not None else None
    request_headers = {"User-Agent": "shortly-scenario-runner/1.0", **(headers or {})}
    if HOST_HEADER:
        request_headers["Host"] = HOST_HEADER
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=raw, method=method, headers=request_headers)
    try:
        with OPENER.open(req, timeout=timeout) as response:
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return response.status, response.read(), response_headers
    except urllib.error.HTTPError as exc:
        response_headers = {key.lower(): value for key, value in exc.headers.items()}
        return exc.code, exc.read(), response_headers


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": ADMIN_TOKEN}


def run(
    command: list[str], timeout: int = 180, check: bool = True, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    log("$ " + " ".join(command))
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        env={**os.environ, **(env or {})},
    )
    if completed.stdout:
        print(completed.stdout.rstrip(), flush=True)
    if completed.stderr:
        print(completed.stderr.rstrip(), file=sys.stderr, flush=True)
    if check and completed.returncode:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}")
    return completed


def kubectl_json(*args: str) -> dict:
    completed = subprocess.run(
        ["kubectl", *args, "-o", "json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "kubectl JSON request failed")
    return json.loads(completed.stdout)


def alert_states() -> dict[str, str]:
    path = f"/api/v1/namespaces/{MON_NS}/services/{PROM_SVC}:9090/proxy/api/v1/alerts"
    result = subprocess.run(
        ["kubectl", "get", "--raw", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "could not read Prometheus alerts")
    payload = json.loads(result.stdout)
    return {
        item.get("labels", {}).get("alertname", "unknown"): item.get("state", "unknown")
        for item in payload.get("data", {}).get("alerts", [])
        if item.get("labels", {}).get("alertname", "").startswith("Shortly")
    }


def firing() -> list[str]:
    return [name for name, state in alert_states().items() if state == "firing"]


def wait_alert(name: str, target: str, seconds: int = 240) -> float | None:
    start = time.monotonic()
    deadline = start + seconds
    while time.monotonic() < deadline:
        state = alert_states().get(name)
        if state == target:
            return time.monotonic() - start
        time.sleep(5)
    return None


def wait_alert_stages(
    name: str,
    events: list[dict],
    seconds: int = 240,
    start_time: float | None = None,
) -> tuple[float | None, float | None]:
    start = time.monotonic() if start_time is None else start_time
    deadline = start + seconds
    pending_at = None
    while time.monotonic() < deadline:
        state = alert_states().get(name)
        elapsed = time.monotonic() - start
        if state == "pending" and pending_at is None:
            pending_at = elapsed
            event(events, "alert pending", alert=name, seconds=elapsed)
        if state == "firing":
            event(events, "alert firing", alert=name, seconds=elapsed)
            return pending_at, elapsed
        time.sleep(5)
    return pending_at, None


def wait_alert_group(
    names: list[str], events: list[dict], seconds: int = 240
) -> dict[str, tuple[float | None, float | None]]:
    start = time.monotonic()
    deadline = start + seconds
    result = {name: (None, None) for name in names}
    while time.monotonic() < deadline:
        states = alert_states()
        elapsed = time.monotonic() - start
        for name in names:
            pending, firing_at = result[name]
            state = states.get(name)
            if state == "pending" and pending is None:
                pending = elapsed
                event(events, "alert pending", alert=name, seconds=elapsed)
            if state == "firing" and firing_at is None:
                firing_at = elapsed
                event(events, "alert firing", alert=name, seconds=elapsed)
            result[name] = (pending, firing_at)
        if all(firing_at is not None for _pending, firing_at in result.values()):
            return result
        time.sleep(5)
    return result


def wait_resolved(name: str, seconds: int = 240) -> float | None:
    start = time.monotonic()
    deadline = start + seconds
    while time.monotonic() < deadline:
        if alert_states().get(name) not in {"pending", "firing"}:
            return time.monotonic() - start
        time.sleep(5)
    return None


def wait_ready(timeout: int = 180) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(
            [
                "kubectl",
                "-n",
                NS,
                "get",
                "pods",
                "-l",
                "app.kubernetes.io/name=shortly",
                "-o",
                "json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            try:
                pods = json.loads(result.stdout).get("items", [])
                app_pods = [
                    p
                    for p in pods
                    if "api"
                    in p.get("metadata", {})
                    .get("labels", {})
                    .get("app.kubernetes.io/component", "")
                ]
                if app_pods and all(
                    p.get("status", {}).get("phase") == "Running"
                    and all(
                        c.get("ready") for c in p.get("status", {}).get("containerStatuses", [])
                    )
                    for p in app_pods
                ):
                    return True
            except (json.JSONDecodeError, TypeError):
                pass
        time.sleep(3)
    return False


def current_image() -> str:
    data = kubectl_json("-n", NS, "get", "deployment", "shortly")
    return data["spec"]["template"]["spec"]["containers"][0]["image"]


def normalize() -> list[str]:
    fixed: list[str] = []
    status, _, _ = request(f"{BASE}/admin/chaos", "DELETE", headers=admin_headers())
    if status != 200:
        raise RuntimeError(f"chaos reset preflight returned HTTP {status}")
    fixed.append("chaos reset")
    run(["make", "redis-up"])
    run(["kubectl", "-n", NS, "rollout", "status", "deployment/redis", "--timeout=120s"])
    if current_image() != "shortly:v1":
        run(["make", "release", "TAG=v1"], timeout=180)
        fixed.append("deployment released to shortly:v1")
    else:
        fixed.append("deployment already on shortly:v1")
    if not wait_ready(180):
        raise RuntimeError("app pods did not become Ready during preflight")
    run(["kubectl", "-n", NS, "rollout", "status", "deployment/shortly", "--timeout=120s"])
    deadline = time.monotonic() + 180
    while firing() and time.monotonic() < deadline:
        time.sleep(5)
    current = firing()
    if current:
        raise RuntimeError(f"Shortly alerts still firing after 3 minutes: {', '.join(current)}")
    return fixed


def run_locust(
    name: str,
    users: int = 30,
    spawn: int = 5,
    duration: str | None = None,
    shape: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.Popen:
    folder = REPORTS / name
    folder.mkdir(parents=True, exist_ok=True)
    files = "loadtest/locustfile.py,loadtest/shapes/surge.py" if shape else "loadtest/locustfile.py"
    command = [
        str(LOCUST),
        "-f",
        files,
        "--headless",
        "--host",
        BASE,
        "-u",
        str(users),
        "-r",
        str(spawn),
        "--csv",
        str(folder / "locust"),
        "--csv-full-history",
        "--html",
        str(folder / "report.html"),
        "--logfile",
        str(folder / "locust.log"),
        "--exit-code-on-error",
        "1",
    ]
    if duration:
        command += ["-t", duration]
    merged_env = {
        **os.environ,
        "BASE": BASE,
        "HOST_HEADER": HOST_HEADER,
        "PERSONA_WEIGHTS": WEIGHTS,
        "LOCUST_TIMING_FILE": str(folder / "request-times.csv"),
        **(env or {}),
    }
    log("$ " + " ".join(command))
    output = open(folder / "locust-console.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        command, cwd=ROOT, env=merged_env, stdout=output, stderr=subprocess.STDOUT, text=True
    )
    proc._shortly_output = output
    return proc


def stop_locust(proc: subprocess.Popen | None) -> None:
    if not proc:
        return
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    output = getattr(proc, "_shortly_output", None)
    if output:
        output.close()


def aggregate(folder: Path) -> dict:
    path = folder / "locust_stats.csv"
    if not path.exists():
        return {"requests": 0, "failures": 0, "p95": 0, "rows": {}, "failure_ratio": 0.0}
    rows = {}
    aggregate_row = {}
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            name = row.get("Name", "")
            if name == "Aggregated":
                aggregate_row = row
            elif name:
                rows[name] = row
    requests = int(aggregate_row.get("Request Count", 0) or 0)
    failures = int(aggregate_row.get("Failure Count", 0) or 0)
    p95 = float(aggregate_row.get("95%", 0) or 0)
    return {
        "requests": requests,
        "failures": failures,
        "p95": p95,
        "rows": rows,
        "failure_ratio": failures / requests if requests else 0.0,
    }


def history(folder: Path) -> list[dict]:
    path = folder / "locust_stats_history.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        return [row for row in csv.DictReader(stream) if row.get("Name") == "Aggregated"]


def window_stats(folder: Path, start_epoch: float, end_epoch: float) -> dict:
    timing_path = folder / "request-times.csv"
    if timing_path.exists():
        observations = []
        with timing_path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                try:
                    stamp = float(row["timestamp"])
                    if start_epoch <= stamp <= end_epoch:
                        observations.append(row)
                except (KeyError, ValueError):
                    continue
        response_times = sorted(float(row["response_time_ms"]) for row in observations)
        failures = sum(row["failed"].lower() == "true" for row in observations)
        p95_index = max(0, int(0.95 * len(response_times) + 0.999999) - 1)
        return {
            "requests": len(observations),
            "failures": failures,
            "ratio": failures / len(observations) if observations else 0,
            "p95": response_times[p95_index] if response_times else 0,
        }
    selected = []
    for row in history(folder):
        try:
            timestamp = float(row.get("Timestamp", 0))
            if start_epoch <= timestamp <= end_epoch:
                selected.append(row)
        except ValueError:
            pass
    request_rate = sum(float(row.get("Requests/s", 0) or 0) for row in selected)
    failure_rate = sum(float(row.get("Failures/s", 0) or 0) for row in selected)
    requests = round(request_rate * 5)
    failures = round(failure_rate * 5)
    p95s = [float(row.get("95%", 0) or 0) for row in selected]
    return {
        "requests": requests,
        "failures": failures,
        "ratio": failures / requests if requests else 0,
        "p95": max(p95s, default=0),
    }


def metric(query: str) -> float:
    encoded = urllib.parse.quote(query, safe="")
    path = (
        f"/api/v1/namespaces/{MON_NS}/services/{PROM_SVC}:9090/proxy/api/v1/query?query={encoded}"
    )
    result = subprocess.run(
        ["kubectl", "get", "--raw", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Prometheus query failed")
    series = json.loads(result.stdout).get("data", {}).get("result", [])
    return float(series[0]["value"][1]) if series else 0.0


def write_result(
    name: str,
    assertions: list[tuple[str, bool, str]],
    events: list[dict],
    metrics: dict,
    alert_delays: dict,
    elapsed: float,
) -> bool:
    folder = REPORTS / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "timeline.json").write_text(json.dumps(events, indent=2) + "\n", encoding="utf-8")
    passed = all(item[1] for item in assertions)
    lines = [
        f"# Scenario: {name}",
        "",
        f"Result: **{'PASS' if passed else 'FAIL'}**",
        f"Run time: {elapsed:.1f} s",
        "",
        "## Assertions",
        "",
        "| Assertion | Result | Detail |",
        "|---|---|---|",
    ]
    lines += [
        f"| {label} | {'PASS' if ok else 'FAIL'} | {detail.replace('|', '/')} |"
        for label, ok, detail in assertions
    ]
    lines += [
        "",
        "## Load metrics",
        "",
        f"- Total requests: {metrics.get('requests', 0)}",
        f"- Unexpected failures: {metrics.get('failures', 0)}",
        f"- Failure ratio: {metrics.get('failure_ratio', 0):.2%}",
        f"- Client p95: {metrics.get('p95', 0):.1f} ms",
        "",
        "## Time to alert",
        "",
    ]
    if alert_delays:
        lines += [
            f"- {key}: {value:.1f} s" if value is not None else f"- {key}: not observed"
            for key, value in alert_delays.items()
        ]
    else:
        lines.append("- No alert wait was required.")
    lines += ["", "## Events", "", "See `timeline.json` for timestamped scenario events.", ""]
    (folder / "result.md").write_text("\n".join(lines), encoding="utf-8")
    return passed


def event(events: list[dict], name: str, **detail) -> None:
    item = {"timestamp": now(), "event": name, **detail}
    events.append(item)
    log(name + (": " + json.dumps(detail, sort_keys=True) if detail else ""))


def app_link() -> tuple[str, str]:
    body = {"url": f"https://www.example.net/durability/{uuid.uuid4().hex}"}
    status, raw, _ = request(
        f"{BASE}/api/shorten",
        "POST",
        body,
        {"X-Forwarded-For": "192.0.2.240", "X-Request-ID": str(uuid.uuid4())},
    )
    if status != 201:
        raise RuntimeError(f"could not create durability link: HTTP {status}: {raw[:200]!r}")
    data = json.loads(raw)
    return data["code"], body["url"]


def version() -> str:
    status, body, _ = request(f"{BASE}/version", timeout=2)
    return str(json.loads(body).get("version", "")) if status == 200 else ""


def restart_count() -> int:
    data = kubectl_json("-n", NS, "get", "pods", "-l", "app.kubernetes.io/component=api")
    return sum(
        int(c.get("restartCount", 0))
        for pod in data.get("items", [])
        for c in pod.get("status", {}).get("containerStatuses", [])
    )


def crash_looping_pods() -> set[str]:
    data = kubectl_json("-n", NS, "get", "pods", "-l", "app.kubernetes.io/component=api")
    return {
        pod.get("metadata", {}).get("name", "unknown")
        for pod in data.get("items", [])
        for container in pod.get("status", {}).get("containerStatuses", [])
        if container.get("state", {}).get("waiting", {}).get("reason") == "CrashLoopBackOff"
    }


def replicas() -> tuple[int, int]:
    data = kubectl_json("-n", NS, "get", "hpa", "shortly")
    return (
        int(data.get("status", {}).get("currentReplicas", 0)),
        int(data.get("status", {}).get("desiredReplicas", 0)),
    )


def rate_limit_evidence(since: float) -> tuple[int, set[str]]:
    since_iso = (
        datetime.fromtimestamp(since, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    command = [
        "kubectl",
        "-n",
        NS,
        "logs",
        "-l",
        "app.kubernetes.io/component=api",
        f"--since-time={since_iso}",
        "--tail=-1",
        "--prefix",
        "--max-log-requests",
        "10",
    ]
    # These logs can contain thousands of lines during a baseline run; keep
    # them in memory for parsing instead of echoing every request to the user.
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"could not collect app access logs: {exc}") from exc
    ips = set()
    limited = set()
    for line in result.stdout.splitlines():
        start = line.find("{")
        if start < 0:
            continue
        try:
            entry = json.loads(line[start:])
        except json.JSONDecodeError:
            continue
        client_ip = entry.get("client_ip")
        if client_ip:
            ips.add(str(client_ip))
            if entry.get("status") == 429:
                limited.add(str(client_ip))
    report = REPORTS / "baseline" / "rate-limit-realism.md"
    report.write_text(
        "# Baseline rate-limit realism check\n\n"
        "Command used:\n\n"
        "```sh\n"
        f"kubectl -n {NS} logs -l app.kubernetes.io/component=api --since-time={since_iso} "
        "--tail=-1 --prefix --max-log-requests 10\n"
        "```\n\n"
        f"Distinct client_ip values: **{len(ips)}**\n\n"
        f"IP addresses with 429 responses: **{', '.join(sorted(limited)) or 'none'}**\n\n"
        "The scenario asserts that more than ten source IPs reach the app and that the only "
        "rate-limited source is the shared Abuser address `198.51.100.250`.\n",
        encoding="utf-8",
    )
    return len(ips), limited


def scenario(name: str) -> bool:
    folder = REPORTS / name
    folder.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    started_wall = time.time()
    events: list[dict] = []
    assertions: list[tuple[str, bool, str]] = []
    alerts: dict[str, float | None] = {}
    proc = None
    load_metrics = {"requests": 0, "failures": 0, "failure_ratio": 0.0, "p95": 0}
    fault_start = 0.0
    post_recovery_start = 0.0
    prom_error_ratio: float | None = None
    try:
        fixed = normalize()
        event(events, "preflight complete", changes=fixed)
        if name == "baseline":
            proc = run_locust(name, duration="4m")
            event(events, "load started", users=30)
            time.sleep(45)
            event(events, "warmup complete")
            time.sleep(180)
            stop_locust(proc)
            proc = None
        elif name in {"latency", "errors"}:
            proc = run_locust(name)
            event(events, "load started", users=30)
            time.sleep(45)
            event(events, "warmup complete")
            fault_start = time.time()
            fault = (
                {"latency_ms": 800, "error_pct": 0}
                if name == "latency"
                else {"latency_ms": 0, "error_pct": 30}
            )
            status, _, _ = request(f"{BASE}/admin/chaos", "POST", fault, admin_headers())
            event(events, "fault injected", fault=fault, status=status)
            target = "ShortlyHighLatencyP95" if name == "latency" else "ShortlyHighErrorRate"
            pending, delay = wait_alert_stages(target, events, 240)
            if pending is not None:
                alerts[f"{target} pending"] = pending
            alerts[f"{target} firing"] = delay
            if delay is None:
                event(events, "alert not observed", alert=target)
            if name == "errors":
                # Capture the same 1-minute 5xx ratio while the fault is still
                # active; after recovery, the rolling Prometheus window decays.
                prom_error_ratio = metric(
                    'sum(rate(http_requests_total{job="shortly",namespace="urlshortener",'
                    'handler!~"/healthz|/readyz",status=~"5.."}[1m])) / clamp_min('
                    'sum(rate(http_requests_total{job="shortly",namespace="urlshortener",'
                    'handler!~"/healthz|/readyz"}[1m])), 1e-9)'
                )
            fault_end = time.time()
            time.sleep(30)
            status, _, _ = request(f"{BASE}/admin/chaos", "DELETE", headers=admin_headers())
            event(events, "fault reset", status=status)
            # The error alert evaluates a five-minute rolling window, so its
            # recovery can take just over five minutes after chaos is reset.
            resolution_timeout = 360 if name == "errors" else 240
            alerts[f"{target} resolved"] = wait_resolved(target, resolution_timeout)
            post_recovery_start = time.time()
            time.sleep(45)
            stop_locust(proc)
            proc = None
            event(events, "recovered")
            fault_window = window_stats(folder, fault_start, fault_end)
            load_metrics["fault_window"] = fault_window
            load_metrics["recovery_window"] = window_stats(folder, post_recovery_start, time.time())
            if name == "latency":
                assertions.append(
                    (
                        "latency alert fired",
                        alerts[f"{target} firing"] is not None,
                        str(alerts[f"{target} firing"]),
                    )
                )
                assertions.append(
                    (
                        "fault p95 at least 700 ms",
                        fault_window["p95"] >= 700,
                        f"{fault_window['p95']:.1f} ms",
                    )
                )
                assertions.append(
                    (
                        "no 5xx during latency fault",
                        fault_window["failures"] == 0,
                        f"{fault_window['failures']} unexpected failures",
                    )
                )
                recovery_p95 = load_metrics["recovery_window"]["p95"]
                assertions.append(
                    ("recovery p95 below 500 ms", 0 < recovery_p95 < 500, f"{recovery_p95:.1f} ms")
                )
            else:
                ratio = fault_window["ratio"]
                prom = prom_error_ratio or 0.0
                assertions.append(
                    (
                        "error alert fired",
                        alerts[f"{target} firing"] is not None,
                        str(alerts[f"{target} firing"]),
                    )
                )
                assertions.append(
                    ("Locust fault failure ratio 15-45%", 0.15 <= ratio <= 0.45, f"{ratio:.2%}")
                )
                assertions.append(
                    (
                        "Prometheus and Locust error ratios within 10 points",
                        abs(prom - ratio) <= 0.10,
                        f"Prometheus {prom:.2%}, Locust {ratio:.2%}",
                    )
                )
                assertions.append(
                    (
                        "zero failures after recovery",
                        load_metrics["recovery_window"]["failures"] == 0,
                        f"{load_metrics['recovery_window']['failures']} failures",
                    )
                )
            assertions.append(
                (
                    "alert resolved after reset",
                    alerts.get(f"{target} resolved") is not None,
                    str(alerts.get(f"{target} resolved")),
                )
            )
        elif name == "redis-down":
            code, target_url = app_link()
            before_restarts = restart_count()
            proc = run_locust(name)
            event(events, "load started", users=30, durability_code=code)
            time.sleep(45)
            event(events, "warmup complete")
            fault_start = time.time()
            run(["make", "redis-down"])
            event(events, "fault injected", fault="Redis scaled to zero")
            ready_status = None
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                ready_status, _, _ = request(f"{BASE}/readyz")
                if ready_status == 503:
                    break
                time.sleep(1)
            group = wait_alert_group(["ShortlyRedisDown", "ShortlyPodsNotReady"], events, 240)
            pending_redis, delay_redis = group["ShortlyRedisDown"]
            alerts["ShortlyRedisDown firing"] = delay_redis
            if pending_redis is not None:
                alerts["ShortlyRedisDown pending"] = pending_redis
            pending_notready, delay_notready = group["ShortlyPodsNotReady"]
            alerts["ShortlyPodsNotReady firing"] = delay_notready
            if pending_notready is not None:
                alerts["ShortlyPodsNotReady pending"] = pending_notready
            if delay_redis is None:
                event(events, "alert not observed", alert="ShortlyRedisDown")
            if delay_notready is None:
                event(events, "alert not observed", alert="ShortlyPodsNotReady")
            time.sleep(30)
            fault_end = time.time()
            run(["make", "redis-up"])
            run(["kubectl", "-n", NS, "rollout", "status", "deployment/redis", "--timeout=120s"])
            event(events, "reset", fault="Redis restored")
            if not wait_ready(180):
                raise RuntimeError("app pods did not recover after Redis was restored")
            alerts["ShortlyRedisDown resolved"] = wait_resolved("ShortlyRedisDown", 240)
            recovery_start = time.time()
            time.sleep(30)
            status, _, headers = request(f"{BASE}/{code}")
            load_metrics["durability_status"] = status
            load_metrics["durability_location"] = headers.get("location", "")
            load_metrics["readyz_outage_status"] = ready_status
            load_metrics["app_restarts_before"] = before_restarts
            load_metrics["app_restarts_after"] = restart_count()
            stop_locust(proc)
            proc = None
            outage_window = window_stats(folder, fault_start, fault_end)
            recovery_window = window_stats(folder, recovery_start, time.time())
            load_metrics["outage_window"] = outage_window
            load_metrics["recovery_window"] = recovery_window
            event(events, "recovered", ready_status=ready_status, durable_redirect=status)
            assertions += [
                ("/readyz returned 503 during outage", ready_status == 503, str(ready_status)),
                (
                    "Locust saw failures during Redis outage",
                    outage_window["failures"] > 0,
                    f"{outage_window['failures']} failures in {outage_window['requests']} requests",
                ),
                (
                    "Locust failures returned to zero after recovery",
                    recovery_window["failures"] == 0,
                    f"{recovery_window['failures']} failures in "
                    f"{recovery_window['requests']} requests",
                ),
                (
                    "ShortlyRedisDown fired",
                    alerts["ShortlyRedisDown firing"] is not None,
                    str(alerts["ShortlyRedisDown firing"]),
                ),
                (
                    "ShortlyPodsNotReady fired",
                    alerts["ShortlyPodsNotReady firing"] is not None,
                    str(alerts["ShortlyPodsNotReady firing"]),
                ),
                (
                    "durability link still redirects after Redis outage",
                    status == 302 and headers.get("location") == target_url,
                    f"HTTP {status}, Location={headers.get('location', '')}",
                ),
                (
                    "Redis outage did not restart app containers",
                    load_metrics["app_restarts_after"] == before_restarts,
                    f"before {before_restarts}, after {load_metrics['app_restarts_after']}",
                ),
            ]
        elif name == "good-release":
            proc = run_locust(name)
            event(events, "load started", users=30)
            time.sleep(45)
            event(events, "warmup complete")
            release_started = time.time()
            event(events, "release started", image="shortly:v2")
            versions = []
            release = subprocess.Popen(
                ["make", "good-release"],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            while release.poll() is None:
                seen = version()
                if seen:
                    versions.append(seen)
                time.sleep(0.5)
            output = release.stdout.read() if release.stdout else ""
            release_duration = time.time() - release_started
            load_metrics["release_duration"] = release_duration
            if release.returncode:
                raise RuntimeError("good-release failed: " + output[-1000:])
            event(events, "rollout complete", duration_seconds=release_duration)
            versions.extend([version(), version()])
            time.sleep(15)
            stop_locust(proc)
            proc = None
            load_metrics.update(versions=versions, version_end=version())
            assertions += [
                (
                    "both v1 and v2 observed during rollout",
                    "v1" in versions and "v2" in versions,
                    ", ".join(dict.fromkeys(versions)),
                ),
                ("only v2 at end", version() == "v2", version()),
                ("rollout completed", True, f"{release_duration:.1f} s"),
                (
                    "zero unexpected failures during rollout",
                    aggregate(folder)["failures"] == 0,
                    str(aggregate(folder)["failures"]),
                ),
                ("no Shortly alerts firing", not firing(), str(firing())),
            ]
        elif name in {"bad-release-errors", "bad-release-crash"}:
            proc = run_locust(name)
            event(events, "load started", users=30)
            time.sleep(45)
            event(events, "warmup complete")
            target = (
                "ShortlyHighErrorRate" if name == "bad-release-errors" else "ShortlyPodCrashLooping"
            )
            tag = "v2-bad-errors" if name == "bad-release-errors" else "v2-bad-crash"
            event(events, "release started", image=f"shortly:{tag}")
            release_start = time.time()
            release_start_monotonic = time.monotonic()
            crash_pods: set[str] = set()
            if name == "bad-release-crash":
                release_process = subprocess.Popen(
                    ["make", name],
                    cwd=ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                while release_process.poll() is None:
                    crash_pods.update(crash_looping_pods())
                    states = alert_states()
                    elapsed = time.monotonic() - release_start_monotonic
                    if states.get(target) == "pending" and f"{target} pending" not in alerts:
                        alerts[f"{target} pending"] = elapsed
                        event(events, "alert pending", alert=target, seconds=elapsed)
                    if states.get(target) == "firing" and f"{target} firing" not in alerts:
                        alerts[f"{target} firing"] = elapsed
                        event(events, "alert firing", alert=target, seconds=elapsed)
                    time.sleep(2)
                crash_pods.update(crash_looping_pods())
                release_output = release_process.communicate()[0]
                if release_output:
                    print(release_output.rstrip(), flush=True)
                release_exit_code = release_process.returncode
            else:
                release = run(["make", name], timeout=180, check=False)
                release_exit_code = release.returncode
            event(events, "release command returned", exit_code=release_exit_code)
            if f"{target} firing" not in alerts:
                pending, alerts[f"{target} firing"] = wait_alert_stages(
                    target, events, 240, start_time=release_start_monotonic
                )
                if pending is not None and f"{target} pending" not in alerts:
                    alerts[f"{target} pending"] = pending
            pending = alerts.get(f"{target} pending")
            if alerts[f"{target} firing"] is None:
                event(events, "alert not observed", alert=target)
            if name == "bad-release-crash":
                rollout = run(
                    [
                        "kubectl",
                        "-n",
                        NS,
                        "rollout",
                        "status",
                        "deployment/shortly",
                        "--timeout=5s",
                    ],
                    timeout=10,
                    check=False,
                )
                run(["make", "rollback"], timeout=180)
                event(events, "reset", action="rollback to v1")
                recovered = wait_ready(180)
                alerts["ShortlyPodCrashLooping resolved"] = wait_resolved(
                    "ShortlyPodCrashLooping", 360
                )
                assertions += [
                    (
                        "CrashLoopBackOff pods observed",
                        bool(crash_pods),
                        ", ".join(sorted(crash_pods)) or "no pod entered CrashLoopBackOff",
                    ),
                    (
                        "bad rollout stopped progressing",
                        rollout.returncode != 0,
                        str(rollout.returncode),
                    ),
                    (
                        "crash-loop alert fired",
                        alerts[f"{target} firing"] is not None,
                        str(alerts[f"{target} firing"]),
                    ),
                    (
                        "zero unexpected failures during rollout",
                        aggregate(folder)["failures"] == 0,
                        str(aggregate(folder)["failures"]),
                    ),
                    (
                        "rollback restored v1 and readiness",
                        recovered and version() == "v1",
                        f"version={version()}, ready={recovered}",
                    ),
                    (
                        "alerts resolved after rollback",
                        alerts["ShortlyPodCrashLooping resolved"] is not None and not firing(),
                        str(firing()),
                    ),
                ]
            else:
                image = current_image()
                all_ready = wait_ready(30)
                no_crash_no_notready = (
                    "ShortlyPodCrashLooping" not in firing()
                    and "ShortlyPodsNotReady" not in firing()
                )
                fault_start = release_start
                time.sleep(45)
                fault_end = time.time()
                run(["make", "rollback"], timeout=180)
                event(events, "reset", action="rollback to v1")
                # Let in-flight requests to the terminating bad pod drain
                # before defining the post-rollback zero-failure window.
                time.sleep(5)
                recovery_start = time.time()
                time.sleep(45)
                stop_locust(proc)
                proc = None
                fault_metrics = window_stats(folder, fault_start, fault_end)
                recovery_metrics = window_stats(folder, recovery_start, time.time())
                load_metrics["fault_window"] = fault_metrics
                load_metrics["recovery_window"] = recovery_metrics
                alerts["ShortlyHighErrorRate resolved"] = wait_resolved("ShortlyHighErrorRate", 360)
                assertions += [
                    (
                        "bad error release completed and pods stayed Ready",
                        image == "shortly:v2-bad-errors" and all_ready,
                        f"image={image}, ready={all_ready}",
                    ),
                    (
                        "error alert fired",
                        alerts[f"{target} firing"] is not None,
                        str(alerts[f"{target} firing"]),
                    ),
                    ("no crash loop or not-ready alert", no_crash_no_notready, str(firing())),
                    (
                        "fault failure ratio between 10% and 50%",
                        0.10 <= fault_metrics["ratio"] <= 0.50,
                        f"{fault_metrics['ratio']:.2%}",
                    ),
                    ("rollback restores v1", version() == "v1", version()),
                    (
                        "zero failures after rollback",
                        recovery_metrics["failures"] == 0,
                        str(recovery_metrics["failures"]),
                    ),
                    (
                        "error alert resolved after rollback",
                        alerts["ShortlyHighErrorRate resolved"] is not None,
                        str(alerts["ShortlyHighErrorRate resolved"]),
                    ),
                ]
        elif name == "abuse":
            # Counter series are labeled per pod; aggregate all replicas so
            # traffic distribution cannot hide blocked requests on one pod.
            query_limited = (
                'sum(shortly_rate_limited_total{job="shortly",namespace="urlshortener"})'
            )
            query_blocked = 'sum(shortly_blocked_total{job="shortly",namespace="urlshortener"})'
            before = (metric(query_limited), metric(query_blocked))
            proc = run_locust(
                name, env={"PERSONA_WEIGHTS": "visitor=30,creator=10,power=10,abuser=50"}
            )
            event(
                events, "load started", users=30, weights="visitor=30,creator=10,power=10,abuser=50"
            )
            time.sleep(45)
            event(events, "warmup complete")
            time.sleep(180)
            stop_locust(proc)
            proc = None
            after = (metric(query_limited), metric(query_blocked))
            load_metrics["counter_increases"] = {
                "rate_limited": after[0] - before[0],
                "blocked": after[1] - before[1],
            }
            assertions += [
                ("rate-limited counter increased", after[0] > before[0], str(after[0] - before[0])),
                ("blocked counter increased", after[1] > before[1], str(after[1] - before[1])),
                (
                    "ShortlyHighErrorRate did not fire",
                    "ShortlyHighErrorRate" not in firing(),
                    str(firing()),
                ),
                (
                    "zero 5xx failures",
                    aggregate(folder)["failures"] == 0,
                    str(aggregate(folder)["failures"]),
                ),
            ]
        elif name == "surge":
            attempt = 0
            max_replicas = 0
            scale_time = None
            settings = [
                {"SURGE_USERS": "200", "THINK_TIME_SCALE": "1.0"},
                {"SURGE_USERS": "300", "THINK_TIME_SCALE": "0.25"},
            ]
            while attempt < 2:
                attempt += 1
                proc = run_locust(
                    name,
                    users=200,
                    spawn=10,
                    shape=True,
                    env={**settings[attempt - 1], "SURGE_HOLD": "180"},
                )
                event(events, "load started", shape=True, settings=settings[attempt - 1])
                ended = time.monotonic() + 300
                while time.monotonic() < ended and proc.poll() is None:
                    current, desired = replicas()
                    max_replicas = max(max_replicas, current, desired)
                    if current > 2 and scale_time is None:
                        scale_time = time.time()
                        event(events, "hpa scaled above two", replicas=current)
                    time.sleep(10)
                stop_locust(proc)
                proc = None
                if max_replicas > 2:
                    break
            load_metrics["max_replicas"] = max_replicas
            load_metrics["surge_settings"] = settings[min(attempt - 1, len(settings) - 1)]
            deadline = time.monotonic() + 360
            scaledown = False
            while time.monotonic() < deadline:
                current, desired = replicas()
                if current == 2 and desired == 2:
                    scaledown = True
                    break
                time.sleep(10)
            load_metrics.update(
                scaledown_verified=scaledown,
                scale_up_seconds=(scale_time - started if scale_time else None),
            )
            assertions += [
                ("HPA rose above two replicas", max_replicas > 2, f"max {max_replicas}"),
                (
                    "unexpected failure ratio below 1%",
                    aggregate(folder)["failure_ratio"] < 0.01,
                    f"{aggregate(folder)['failure_ratio']:.2%}",
                ),
                (
                    "ShortlyHighErrorRate did not fire",
                    "ShortlyHighErrorRate" not in firing(),
                    str(firing()),
                ),
                ("HPA returned to two replicas", scaledown, str(replicas())),
            ]
        else:
            raise ValueError(f"unknown scenario: {name}")

        load_metrics.update(aggregate(folder))
        console = folder / "locust-console.log"
        if console.exists():
            text = console.read_text(encoding="utf-8", errors="replace")
            no_cpu_warning = "CPU usage above 90%" not in text
            assertions.append(
                (
                    "load generator CPU below 90% warning threshold",
                    no_cpu_warning,
                    "warning absent" if no_cpu_warning else "Locust CPU warning found",
                )
            )
            if not no_cpu_warning:
                event(events, "invalid load generator CPU warning")
        if name == "baseline":
            names = [
                "GET /{code} [known]",
                "GET / [home]",
                "GET /api/links/recent [poll]",
                "GET /{code} [expired]",
                "POST /api/shorten [create]",
                "GET /api/links/{code}/stats [own link]",
                "POST /api/shorten [duplicate alias]",
                "Abuser POST /api/shorten [invalid URL]",
                "Abuser POST /api/shorten [blocked domain]",
                "Abuser GET /{code} [unknown]",
                "Abuser GET /{path} [path scan]",
                "Abuser GET /admin/chaos [unauthorized]",
                "Abuser POST /api/shorten [burst]",
            ]
            found = set(load_metrics["rows"])
            missing = [item for item in names if item not in found]
            assertions.append(
                (
                    "all persona request rows present",
                    not missing,
                    "all present" if not missing else "missing: " + ", ".join(missing),
                )
            )
            unexpected_429 = [
                row for row in found if "[rate limited]" in row and "abuser" not in row.lower()
            ]
            assertions.append(
                (
                    "429 rows are confined to Abuser request intents",
                    not unexpected_429,
                    ", ".join(unexpected_429) or "only rate-limited named rows",
                )
            )
            assertions.append(
                (
                    "zero unexpected failures",
                    load_metrics["failures"] == 0,
                    str(load_metrics["failures"]),
                )
            )
            assertions.append(
                (
                    "client p95 below 500 ms",
                    0 < load_metrics["p95"] < 500,
                    f"{load_metrics['p95']:.1f} ms",
                )
            )
            assertions.append(("no Shortly alerts firing", not firing(), str(firing())))
            distinct_ips, limited_ips = rate_limit_evidence(started_wall)
            assertions.append(
                (
                    "spoofed per-user IPs reach app logs",
                    distinct_ips > 10,
                    f"{distinct_ips} distinct client_ip values",
                )
            )
            expected_abuser = "198.51.100.250"
            assertions.append(
                (
                    "only the shared Abuser IP receives 429",
                    limited_ips <= {expected_abuser} and bool(limited_ips),
                    ", ".join(sorted(limited_ips)) or "no 429 source observed",
                )
            )
        passed = write_result(
            name, assertions, events, load_metrics, alerts, time.monotonic() - started
        )
        return passed
    except KeyboardInterrupt:
        event(events, "interrupted")
        assertions.append(("scenario completed", False, "interrupted by user"))
        write_result(name, assertions, events, load_metrics, alerts, time.monotonic() - started)
        raise
    except Exception as exc:  # Persist evidence even when orchestration fails.
        event(events, "runner error", error=str(exc))
        assertions.append(("scenario runner completed", False, str(exc)))
        load_metrics.update(aggregate(folder))
        write_result(name, assertions, events, load_metrics, alerts, time.monotonic() - started)
        return False
    finally:
        stop_locust(proc)
        try:
            request(f"{BASE}/admin/chaos", "DELETE", headers=admin_headers())
            run(["make", "redis-up"], timeout=60, check=False)
            if current_image() != "shortly:v1":
                run(["make", "rollback"], timeout=180, check=False)
            wait_ready(180)
            deadline = time.monotonic() + 240
            remaining = firing()
            while remaining and time.monotonic() < deadline:
                time.sleep(5)
                remaining = firing()
            event(events, "cleanup complete", firing_alerts=remaining)
        except Exception as exc:
            event(events, "cleanup warning", error=str(exc))
        # Rewrite timeline after cleanup so interrupted and failed cleanup is also retained.
        (folder / "timeline.json").write_text(json.dumps(events, indent=2) + "\n", encoding="utf-8")


def summary(names: list[str], total_seconds: float) -> None:
    rows = [
        "# Phase 4 scenario summary",
        "",
        f"Date: {datetime.now(UTC).date().isoformat()}",
        f"Chart version: {os.getenv('CHART_VERSION', '91.8.2')}",
        "Image tags: shortly:v1, shortly:v2, shortly:v2-bad-crash, shortly:v2-bad-errors",
        f"Total scenario-all time: {total_seconds / 60:.1f} minutes",
        "",
        "| Scenario | Result | Key metric(s) | Alert time (s) | Requests | Failures | p95 (ms) |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for name in names:
        path = REPORTS / name / "result.md"
        result = path.read_text(encoding="utf-8") if path.exists() else ""
        data = aggregate(REPORTS / name)
        status = "PASS" if "Result: **PASS**" in result else "FAIL"
        try:
            event_data = json.loads((REPORTS / name / "timeline.json").read_text(encoding="utf-8"))
            metric_summary = ", ".join(
                f"{e['event']} {e.get('alert', '')}"
                for e in event_data
                if e["event"] in {"hpa scaled above two", "rollout complete", "fault injected"}
            )
        except (OSError, json.JSONDecodeError):
            metric_summary = ""
        alert_seconds = ""
        for line in result.splitlines():
            if line.startswith("- ") and ("firing:" in line or "firing: " in line):
                alert_seconds = line.split(":", 1)[-1].strip().replace("s", "")
                break
        rows.append(
            f"| {name} | {status} | {metric_summary or DESCRIPTIONS[name]} | {alert_seconds} | "
            f"{data['requests']} | {data['failures']} | {data['p95']:.1f} |"
        )
    rows += [
        "",
        "How to read this: unexpected responses and failed content assertions count as failures. "
        "Expected client errors such as 404, 409, 410, 422, 403, and 429 have named rows in Locust "
        "and do not count as failures. Scenario details, assertions, and timestamped events are in "
        "each scenario directory.",
        "",
    ]
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "SUMMARY.md").write_text("\n".join(rows), encoding="utf-8")


def main(args: list[str]) -> int:
    if not LOCUST.exists():
        print("Missing .venv-load; run make load-install first", file=sys.stderr)
        return 2
    if args == ["list"]:
        for item in SCENARIOS:
            print(f"{item:20} {DURATIONS[item]:8} {DESCRIPTIONS[item]}")
        print("all                  40–50 minutes including 60 s settle periods")
        return 0
    name = args[0] if args else ""
    if name == "all":
        start = time.monotonic()
        results = []
        for index, item in enumerate(SCENARIOS):
            results.append(scenario(item))
            if index < len(SCENARIOS) - 1:
                log("settle period: 60 seconds")
                time.sleep(60)
        summary(SCENARIOS, time.monotonic() - start)
        print((REPORTS / "SUMMARY.md").read_text(encoding="utf-8"))
        return 0 if all(results) else 1
    if name not in SCENARIOS:
        print("Usage: scenario_runner.py {" + ",".join(SCENARIOS) + "|all|list}", file=sys.stderr)
        return 2
    passed = scenario(name)
    result_path = REPORTS / name / "result.md"
    if result_path.exists():
        print(result_path.read_text(encoding="utf-8"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
