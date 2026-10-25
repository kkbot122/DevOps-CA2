# Verification status - 25 October 2026

Fresh checks used Windows and Docker Desktop Kubernetes (context docker-desktop,
Kubernetes v1.36.1), namespaces urlshortener and monitoring. The source-demo
overlay ran the repository app in public Python containers. Its rolling update
and rollback changed **pod-template configuration**. The regular Dockerfile and
image-based Minikube/GitHub Actions release path remain available separately.
Historical load scenarios are not presented as fresh runs.

| Step | Verified evidence |
|---|---|
| 1 - deployment | GitHub run 37209744711: lint, test, build-scan-push and deploy succeeded; duration 5m 3s. Public metadata in pipeline-run.json and pipeline-jobs.json; screenshot 10. Existing screenshot 11 shows a failed release followed by automatic undo. |
| 2 - Ansible | Fresh Ubuntu 24.04 Job: first apply ok=63 changed=31 failed=0; check/diff and second apply ok=44 changed=0 failed=0; verify ok=23 changed=0 failed=0. Original logs and browser reports are in windows/. |
| 3 - containers/Kubernetes | Dockerfile and Deployment/Service YAMLs present. Fresh configuration rollout: 240 requests, v1 and v2 observed, zero failures. CrashLoopBackOff observed, rollback succeeded, 20 responses agreed on restored v2. See windows/rolling-update.json and rollback.json. |
| 4 - monitoring/logging | Helm chart 91.8.2 installed; Prometheus, Grafana, Alertmanager and kube-state-metrics healthy. Two app targets UP. Dashboard includes process uptime, availability, latency and 5xx rate. An 800ms delay caused ShortlyHighLatencyP95 to fire after 95.5s; chaos was reset. See screenshots 19/20 and windows/latency-alert.json, latency-traffic.json. App JSON logs are available through kubectl. |
| 5 - report | Four named members in submission/team.json, report and five-slide deck. Architecture, pipeline, challenges and lessons documented. Unconfirmed anecdote removed and stale memory settings corrected. |

## Screenshot provenance

- 10: original GitHub Actions UI for the successful public run.
- 19/20: original live Grafana/Prometheus UIs on this machine.
- 17/18/21/22/23/24: browser evidence reports of original JSON/stdout included
  under windows/. They are explicitly labeled as reports rather than terminal
  screenshots; no results were fabricated.
- Other pre-existing captures remain historical repository evidence.
- Browser screenshot bytes were re-encoded to PNG without changing the picture.
- All 12 MUST captures are present. Strict checks also validate PNG integrity,
  dimensions and duplicate content. Remaining optional fault/HPA captures are optional.

## Local Docker reproduction

The authorized elevated run of scripts/prepare-images.ps1 passed: the Compose
Dockerfile build completed, both services became healthy, and shortly:v1,
shortly:v2 and shortly:v2-bad-crash were built and imported into the Docker
Desktop Kubernetes node. The helper streams the archive through binary stdin
to avoid Windows Docker copy failures and PowerShell text transcoding. See
windows/docker-build.txt and windows/compose-smoke.json. Earlier sandbox pipe
restrictions were resolved for this run.

The source overlay installs dependencies at pod startup and is a demonstration
fallback, not the regular immutable release image. The full nine historical load
scenarios were not rerun; their original suite failure and focused rerun remain
reported honestly. No external challenge bonus is claimed. The changes are
prepared on codex/windows-demo-evidence for a pull request to the original repo.

## Final quality checks

31 tests passed with 96.97% app coverage. Ruff lint/format and report link checks passed. All 29 provisioned dashboard queries returned data. The five-slide PPTX passed structural, geometry, font and re-import checks; the five-page PDF was rendered for visual inspection. See windows/tests.txt and windows/dashboard-queries.txt.
