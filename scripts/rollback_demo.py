import json
import os
import subprocess
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

k = [
    "kubectl",
    "--kubeconfig",
    os.environ.get("KUBECONFIG", str(Path.home() / ".kube/config")),
    "--context",
    os.environ.get("KUBE_CONTEXT", "docker-desktop"),
    "-n",
    "urlshortener",
]
commands = []


def run(args):
    p = subprocess.run(k + args, capture_output=True, text=True)
    commands.append(
        {
            "command": "kubectl --context docker-desktop -n urlshortener " + " ".join(args),
            "stdout": p.stdout,
            "stderr": p.stderr,
            "returncode": p.returncode,
        }
    )
    return p


before = json.loads(run(["get", "deployment", "shortly", "-o", "json"]).stdout)
revision = before["metadata"]["annotations"]["deployment.kubernetes.io/revision"]
run(["set", "env", "deployment/shortly", "APP_VERSION=v2-bad-crash", "BAD_RELEASE_MODE=crash"])
crash = False
for _ in range(60):
    p = subprocess.run(
        k + ["get", "pods", "-l", "app.kubernetes.io/component=api", "-o", "json"],
        capture_output=True,
        text=True,
    )
    for pod in json.loads(p.stdout)["items"]:
        for status in pod.get("status", {}).get("containerStatuses", []):
            crash |= status.get("state", {}).get("waiting", {}).get("reason") == "CrashLoopBackOff"
    if crash:
        break
    time.sleep(2)
run(["get", "pods", "-o", "wide"])
undo = run(["rollout", "undo", "deployment/shortly", "--to-revision=" + revision])
healthy = run(["rollout", "status", "deployment/shortly", "--timeout=180s"])
run(["rollout", "history", "deployment/shortly"])
url = "http://127.0.0.1:18081/api/v1/namespaces/urlshortener/services/shortly:80/proxy/version"
versions = []
for _ in range(20):
    with urllib.request.urlopen(url, timeout=5) as response:
        versions.append(json.load(response)["version"])
result = {
    "recorded_at": datetime.now(UTC).isoformat(),
    "mode": "source-demo configuration rollback",
    "crash_loop_observed": crash,
    "restored_version": "v2",
    "versions": sorted(set(versions)),
    "pass": crash and undo.returncode == 0 and healthy.returncode == 0 and set(versions) == {"v2"},
    "commands": commands,
}
(Path(__file__).resolve().parents[1] / "docs/evidence/windows/rollback.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps({k: v for k, v in result.items() if k != "commands"}, indent=2))
