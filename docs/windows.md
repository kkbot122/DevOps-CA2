# Windows setup and demonstration

Start Docker Desktop, then run from the repository root:

```powershell
docker compose up -d --build --wait
```

Open http://localhost:8001. The app uses the repository Dockerfile. Redis has
persistent storage and no host port; both services have health checks. If the
port is occupied, set `$env:APP_PORT = '8002'` and rerun.

```powershell
python scripts/verify_live.py --base http://127.0.0.1:8001 --output docs/evidence/windows/compose-smoke.json
docker compose ps
docker compose logs --tail=100 app redis
```

## Kubernetes, Ansible and monitoring

Enable Kubernetes in Docker Desktop. This guide explicitly uses its
`docker-desktop` context. Prerequisites: kubectl and Python 3.12 (or the
existing .venv). The helper downloads checksum-verified Helm into .runtime/
if it is not installed.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows-demo.ps1
```

The default All stage deploys the source demo, installs Prometheus/Grafana,
runs the original Ansible playbooks in a disposable Ubuntu 24.04 Job and prints
cluster status. The Ubuntu target installs packages, creates a deploy user,
manages files, then verifies a second apply with changed=0. It does not configure
Windows. Hosts management uses an isolated test file inside that target.

Individual stages: SourceDeploy, Monitoring, Ansible, Verify, Access
(for example, `-Stage Ansible`). Logs are saved under docs/evidence/windows/.
Rerunning Ansible replaces only the named disposable shortly-ansible-demo Job.

## Source demo versus built-image deployment

The regular k8s/ manifests use shortly:v1, built from Dockerfile. The explicit
source-demo overlay uses public Python containers; an init container installs
the pinned requirements into an ephemeral volume. It needs network access on
pod startup. It retains the same app, Redis, probes, Service, rolling strategy
and replica controls.

Fresh Windows rollout evidence changes APP_VERSION in the pod template. It
demonstrates a **configuration rollout**, not the building of two custom image
tags. The original image-based Actions pipeline has separate successful evidence.

To build and load Dockerfile images into Docker Desktop kind nodes:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare-images.ps1
```

This also rebuilds/checks the Compose app. The image archive and transcript stay
in .runtime/, excluded from the submission. When switching from the source demo,
remove its command/init-container overrides using a reviewed deployment plan.
Changing only its image does not remove those overrides.

## Live UI access

Run each command in a separate terminal and leave it running:

```powershell
kubectl --context docker-desktop -n urlshortener port-forward service/shortly 18080:80
kubectl --context docker-desktop -n monitoring port-forward service/kube-prometheus-stack-grafana 13000:80
kubectl --context docker-desktop -n monitoring port-forward service/kube-prometheus-stack-prometheus 19090:9090
```

App: http://localhost:18080; Grafana: http://localhost:13000
(admin / demo-grafana-pass, local demo only); Prometheus: http://localhost:19090.
Closing a forwarding terminal stops that connection, not the workload.

The release probes use a loopback Kubernetes API proxy so requests reach current
Service endpoints even when a pod is replaced:

```powershell
kubectl --context docker-desktop proxy --port=18081 --address=127.0.0.1
```

In another terminal, for the source demo:

```powershell
$env:KUBE_CONTEXT = 'docker-desktop'
kubectl --context docker-desktop -n urlshortener set env deployment/shortly APP_VERSION=v1 BAD_RELEASE_MODE=none
kubectl --context docker-desktop -n urlshortener rollout status deployment/shortly --timeout=180s
python scripts/rollout_demo.py
python scripts/rollback_demo.py
```

Original JSON results are stored in docs/evidence/windows/. Rollback observes a
CrashLoopBackOff, restores the previous revision and checks 20 version responses.

## Submission checks

```powershell
python -m pytest --cov=app --cov-fail-under=90
python -m ruff check .
python -m ruff format --check .
python scripts/check_screenshots.py --strict
python scripts/check_report_links.py
python scripts/build_submission.py --output dist/DevOps-CA2 --zip
```

The builder refuses an existing output directory. Use a new destination for
another snapshot. It excludes .runtime/, virtual environments, credentials, Git
internals and caches. Read [the current verification record](evidence/CURRENT-STATUS.md)
for evidence provenance and reproduction limitations.
