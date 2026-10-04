# VIVA preparation

Answers are phrased for speaking aloud. The citation after each answer points to the implementation or saved evidence.

## Application and design

1. **Why Redis?** App pods can be replaced or receive different requests, so local memory would split link state and click counts. Redis holds shared links, counters, recent links, rate limits and chaos settings. (`README.md`, `app/storage.py`)
2. **Why keep the API stateless?** Any ready API replica can serve a request because shared state is externalized. This makes rolling updates and horizontal scaling practical. (`README.md`, `docs/k8s.md`)
3. **What is the difference between 410 and 404?** An expired link is retained for a 24-hour window and returns 410 Gone; after Redis removes it, lookup returns 404 Not Found. (`README.md`, `app/routes/redirect.py`)
4. **How does rate limiting work?** Middleware increments a Redis fixed-window counter keyed by client IP and current UTC minute, with a 60-second TTL and a default limit of ten shorten requests. Invalid requests also use quota because counting happens before validation. (`README.md`, `app/middleware.py`)
5. **Can users spoof their source IP?** The app trusts the first X-Forwarded-For address only behind the configured local trusted ingress. That setting must not be copied behind an untrusted proxy. (`docs/k8s.md`, `docs/scenarios.md`)

## Docker and Kubernetes

6. **Why separate liveness from readiness?** `/healthz` checks that the API process is alive; `/readyz` also requires Redis. When Redis was scaled down, readiness returned 503 while app restart counts stayed at zero. (`app/routes/health.py`, `loadtest/reports/redis-down/result.md`)
7. **What does `maxUnavailable: 0` do?** It prevents a rolling update from intentionally removing an old available replica before a replacement is ready. The good-release evidence observed both versions during rollout and zero unexpected failures. (`k8s/app-deployment.yaml`, `loadtest/reports/good-release/result.md`)
8. **How is rollback different from a rollout?** A rollout changes the Deployment image and waits for new pods; rollback asks Kubernetes to restore a prior revision. The CI helper also verifies the restored version and keeps the failed release job red. (`scripts/ci/deploy.sh`, `scripts/ci/rollback.sh`)
9. **What does the HPA use?** It targets 60% CPU utilization using pod CPU requests and scales from two to five replicas. In the saved surge scenario it reached three and returned to two. (`k8s/hpa.yaml`, `loadtest/reports/surge/result.md`)
10. **Why add a PDB?** A PodDisruptionBudget asks voluntary disruptions to preserve at least one available app pod. It complements rolling strategy settings rather than replacing them. (`k8s/pdb.yaml`)
11. **What does `IfNotPresent` mean with `minikube image load`?** Kubernetes can use the image already loaded into the Minikube node instead of trying to pull it from a registry. The Make targets explicitly load local variants before deploying. (`k8s/app-deployment.yaml`, `Makefile`)
12. **Why is Redis a single replica?** This is a small local demonstration and the PVC is ReadWriteOnce; the docs explicitly call it unsuitable as a highly available production topology. (`k8s/redis.yaml`, `docs/k8s.md`)

## CI/CD

13. **Why use a self-hosted runner?** It can reach the local Minikube Docker daemon and kubeconfig. That access is powerful, so only trusted main-branch deployment events reach it and the repository should remain private. (`docs/cicd.md`, `.github/workflows/ci-cd.yml`)
14. **Why verify an image digest?** A mutable tag alone does not prove the deployed bytes are the same as the scanned build. The deploy path compares the expected registry digest before loading and applying the image. (`scripts/ci/deploy.sh`)
15. **Why do pull requests not deploy?** PR code is untrusted relative to the local runner. The workflow condition separates hosted checks from deployment and prevents PR workflows from executing there. (`.github/workflows/ci-cd.yml`, `docs/cicd.md`)
16. **What does automatic rollback do?** On a failed rollout or post-deploy verification, the CI helper undoes the Deployment revision and checks the restored version/readiness. The workflow still returns failure so the release remains visible as failed. (`scripts/ci/verify.sh`, `scripts/ci/rollback.sh`)
17. **Why does the context guard fail closed?** A self-hosted runner may hold several Kubernetes contexts; deployment should stop unless it targets the expected cluster. The configured `shortly` profile needs explicit runner context allowlisting in the documented setup. (`scripts/ci/preflight.sh`, `docs/cicd.md`)
18. **What do the hosted jobs scan?** The pipeline runs Trivy image, secret and configuration scans and emits a CycloneDX SBOM. Fixed CRITICAL vulnerabilities block; HIGH and configuration findings are reported. (`.github/workflows/ci-cd.yml`, `docs/cicd.md`)

## Ansible

19. **What does idempotence mean here?** Running the same playbook again should leave managed state unchanged. The Ubuntu 24.04 second apply recorded `changed=0`, and verify was a separate read-only run with `changed=0`. (`ansible/evidence/container-idempotence.txt`, `ansible/evidence/container-verify.txt`)
20. **Why skip existing Docker, kubectl, Helm and Minikube tools?** The default prioritizes preserving a working host over enforcing versions; replacing tools requires an explicit variable. This reduces risk on the existing runner machine. (`ansible/roles/`, `docs/ansible.md`)
21. **Why use `no_log` for the token?** The `.env` template may contain an admin token, so Ansible suppresses task output and diff for that task. Real secrets should be supplied through Vault/private vars, not committed defaults. (`ansible/roles/shortly_config/tasks/main.yml`, `docs/ansible.md`)
22. **What was the drift demo?** It deliberately changes two Ansible-managed items, reruns the play, verifies repair and checks a final unchanged recap. Use the disposable supported target for this demonstration. (`scripts/ansible-drift-demo.sh`, `docs/ansible.md`)
23. **Why a narrow sudoers rule?** The deploy account is limited to read-only status queries for Docker and runner services, which support diagnosis without granting unrestricted service control. `visudo -cf` validates the file before replacement. (`ansible/roles/deploy_user/templates/sudoers.j2`, `docs/ansible.md`)

## Monitoring and testing

24. **Why exclude probe traffic from user metrics?** Kubernetes continuously calls health endpoints; including those requests would distort user request rates, latency and error ratios. The dashboard query filters `/healthz` and `/readyz`. (`docs/monitoring.md`)
25. **Why do alert rules have traffic guards?** Error and latency ratios are noisy or meaningless when there is almost no real traffic. Rules require sustained request volume and a `for` period before firing. (`monitoring/prometheusrule.yaml`, `docs/monitoring.md`)
26. **Why are exact statuses and request intents important?** Expected 4xx results such as 404, 409, 410, 422, 403 and 429 are normal tested behaviors, not outages. Locust treats unexpected statuses, transport failures and failed content assertions as failures. (`docs/scenarios.md`, `loadtest/common.py`)
27. **What does the silent bad release show?** Its pods stayed Ready because probes passed, but 24.38% of the fault-window requests failed and the error alert fired after 130.8 seconds. Metrics and application-level verification caught a fault that readiness alone missed. (`loadtest/reports/bad-release-errors/result.md`)
28. **Why use four personas?** Visitors, creators, power users and a shared-IP abuser exercise browsing, creation, alias/expiry behavior and abuse/rate limiting at different pacing. The shared abuser address makes rate-limit behavior reproducible. (`docs/scenarios.md`, `loadtest/personas.py`)
29. **How do you avoid high-cardinality metrics?** App metrics use normalized handler templates such as `/{code}`, not each unique short code. This preserves useful route grouping without a time series per link. (`docs/monitoring.md`, `app/metrics.py`)

## Things I must be honest about

- **Chaos endpoints:** They are demonstration controls behind an admin token, not a production fault-management feature. Explain that rules and recovery are exercised locally. (`README.md`)
- **Grafana credential:** `demo-grafana-pass` is a documented local demo credential, not suitable for production. (`docs/monitoring.md`)
- **Cluster and Redis:** The cluster is single-node and Redis has one replica. Do not claim high availability. (`docs/k8s.md`)
- **Image loading:** `minikube image load` is for the local demo; a production cluster would normally use a private registry pull with workload identity/credentials. (`Makefile`, `docs/cicd.md`)
- **Self-hosted runner:** It is local and has access to Docker and the cluster; keep it restricted to trusted events and keep the source repository private. (`docs/cicd.md`)
- **Step 6:** No proof is saved yet. Call it pending until the chosen external challenge and original evidence are attached. (`docs/bonus/README.md`)
- **Scenario suite:** The full saved run had an abuse FAIL; the focused rerun passed, but the full suite was not rerun. State both facts. (`loadtest/reports/SUMMARY.md`)
