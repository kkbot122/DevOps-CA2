import concurrent.futures
import json
import os
import subprocess
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

BASE = "http://127.0.0.1:18081/api/v1/namespaces/urlshortener/services/shortly:80/proxy"
K = [
    "kubectl",
    "--kubeconfig",
    os.environ.get("KUBECONFIG", str(Path.home() / ".kube/config")),
    "--context",
    os.environ.get("KUBE_CONTEXT", "docker-desktop"),
    "-n",
    "urlshortener",
]
out = Path(__file__).resolve().parents[1] / "docs/evidence/windows"
samples = []


def sample(_):
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(BASE + "/version", timeout=8) as r:
            result = json.load(r)
        item = {
            "time": datetime.now(UTC).isoformat(),
            "ok": True,
            "version": result["version"],
            "hostname": result["hostname"],
        }
    except Exception as e:
        item = {"time": datetime.now(UTC).isoformat(), "ok": False, "error": str(e)}
    item["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
    return item


with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    future = pool.submit(
        subprocess.run,
        K + ["set", "env", "deployment/shortly", "APP_VERSION=v2"],
        capture_output=True,
        text=True,
    )
    for _ in range(220):
        samples.append(sample(0))
        time.sleep(0.15)
    rollout = subprocess.run(
        K + ["rollout", "status", "deployment/shortly", "--timeout=180s"],
        capture_output=True,
        text=True,
    )
    for _ in range(20):
        samples.append(sample(0))
        time.sleep(0.1)
    versions = sorted({s.get("version") for s in samples if s["ok"]})
    result = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "mode": "source-demo configuration rollout",
        "versions": versions,
        "requests": len(samples),
        "failed": sum(not s["ok"] for s in samples),
        "set_env": future.result().stdout,
        "rollout": rollout.stdout,
        "samples": samples,
    }
    result["pass"] = result["failed"] == 0 and versions == ["v1", "v2"] and rollout.returncode == 0
    (out / "rolling-update.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "samples"}, indent=2))
