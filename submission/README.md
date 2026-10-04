# Marker’s guide

The files below map the course steps to the implementation and planned evidence. Screenshots are not included until real captures are saved under `docs/screenshots/`.

| Step | Requirement | Files to inspect | Screenshot filenames | How to verify |
|---|---|---|---|---|
| 1 | Workflow file and pipeline diagram | `.github/workflows/ci-cd.yml`, `.github/workflows/rollback.yml`, `docs/diagrams/pipeline.mmd`, `scripts/ci/` | `10-pipeline-green.png`, `11-pipeline-autorollback.png`, `27-pipeline-diagram.png` | Inspect hosted gates, main-only deploy condition, digest guard, context guard and rollback path. |
| 2 | Playbook/manifest and inventory | `ansible/site.yml`, `ansible/verify.yml`, `ansible/inventory/`, `ansible/roles/`, `ansible/evidence/` | `21-ansible-check-diff.png`–`24-ansible-verify-pass.png` | Compare Ubuntu first and second recaps; second apply and verify must show `changed=0`. |
| 3 | Dockerfile and Kubernetes YAMLs, rolling update and rollback | `Dockerfile`, `k8s/`, `scripts/probe.sh`, `scripts/ci/rollback.sh` | `16-kubectl-pods.png`, `17-rolling-update-probe.png`, `18-rollback-history.png` | Inspect probes, HPA, PDB and `maxUnavailable: 0`; compare release and rollback version output. |
| 4 | Prometheus/Grafana screenshots (uptime, latency, error rate) | `monitoring/`, `docs/monitoring.md`, `docs/scenarios.md`, `loadtest/reports/` | `19-grafana-dashboard.png`, `20-alert-firing.png`, `01-baseline-overview.png`–`09-surge-hpa.png` | Compare dashboard panels and alert state with committed scenario result files. |
| 5 | Reflection, report, slides and documentation | `docs/REPORT.md`, `docs/CHALLENGES.md`, `docs/VIVA.md`, `report/` | Screenshot references are in `docs/screenshots/MANIFEST.md` | Rebuild with `make slides`; check the five-slide deck and report source references. |
| 6 | External DevOps challenge proof | `docs/bonus/README.md`, `docs/bonus/proof-*.png` | Add original proof as `docs/bonus/proof-*.png` | **PENDING:** verify the chosen challenge, date, link, activity and original proof before claiming the bonus. |

## Build the hand-in folder

From the source repository, run:

```sh
make submission
```

This assembles `dist/DevOps-CA2/`, excludes Git internals, virtual environments, cache directories and prior `dist/`, and checks committed credential values against documented demo defaults. Review the assembled folder before copying it.

The source repository containing the self-hosted runner workflow must remain private. The class copy includes `.github/workflows/` as files because Step 1 requires the workflow; check whether the course repository expects a copy or a link before pushing.

When ready, run these commands yourself from the assembled folder; they are printed for convenience and are intentionally not executed by the build target:

```sh
cd dist/DevOps-CA2
git init
git branch -M main
git add .
git commit -m "Submit DevOps CA2 project"
git remote add origin https://github.com/aditisharmas11/DevOps-CA2_2023_27.git
git push -u origin main
```

Deadline in the supplied assignment: **5 October 2026**.
