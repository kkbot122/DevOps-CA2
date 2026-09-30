# Phase 4: behavior-driven load and failure scenarios

Locust runs on the host and sends traffic to the deployed app (`BASE=http://short.local` by default). It uses `FastHttpUser` to keep generator overhead low. Load-test dependencies are isolated from the app image and app requirements.

## Personas

| Persona | Default share | Pace | Why it exists |
|---|---:|---:|---|
| CasualVisitor | 60% | 1–4 s | Follows live links, loads the home page, polls recent links, and revisits expiring links. |
| Creator | 25% | 3–8 s | Creates links, visits them, and checks click statistics. A 429 honors `Retry-After`. |
| PowerUser | 10% | 2–6 s | Uses custom aliases and expiries, tries duplicate/reserved aliases, and checks ephemeral links after expiry. |
| Abuser | 5% | 0.5–3 s | Sends malformed and blocked URLs, scans paths, probes admin authorization, and bursts shorten requests from one shared IP. |

Each user receives a stable Faker public IPv4, a realistic User-Agent, and a fresh UUID request ID per request. Abusers share `198.51.100.250` so their rate-limit behavior is reproducible. Link pools are shared within the single Locust process and randomly evict entries above 500. The test-start hook seeds 30 links using rotating IPs so users can browse immediately. Seed errors are warnings; load continues.

## Expected client errors

Expected 4xx responses are successful outcomes for the simulation, not Locust failures. The request is recorded under a fixed intent name such as `Abuser POST /api/shorten [invalid URL]` or `GET /{code} [expired]`; a 429 gets a `[rate limited]` suffix. A response outside the allowed set, a 5xx, timeout, connection error, wrong redirect target, malformed response body, or incorrect stats count is a failure. No request follows a redirect: generated destinations are fake external URLs and must never receive test traffic.

## Install and run

```sh
make load-install
.venv-load/bin/locust --version
make load-ui                         # http://localhost:8089
make load BASE=http://short.local USERS=30 SPAWN=5 DURATION=3m
make load-local                      # localhost:8000, 20 users, 30 s
make load-smoke                      # 10 users, 20 s; nonzero on unexpected failures
make scenario-baseline
make scenario-latency
make scenario-errors
make scenario-redis-down
make scenario-good-release
make scenario-bad-release-errors
make scenario-bad-release-crash
make scenario-surge
make scenario-abuse
make scenario-all
```

Set `PERSONA_WEIGHTS=visitor=60,creator=25,power=10,abuser=5` and `THINK_TIME_SCALE=1.0` to tune personas globally. The surge scenario can set `SURGE_USERS`, `SURGE_HOLD`, and `THINK_TIME_SCALE` independently. Scenario commands normalize Redis, chaos, image version, readiness, and firing Shortly alerts before they start. They stop Locust, reset chaos, restore Redis and v1, and save evidence even if an assertion fails. Each scenario writes CSV history, per-request timing samples, an HTML report, a Locust log, `timeline.json`, and `result.md` under `loadtest/reports/<scenario>/`.

`make scenario-all` runs baseline, abuse, latency, errors, Redis down, good release, bad error release, crash release, and surge in that order, with 60 seconds between runs. Budget roughly 40–50 minutes, including alert windows, rollouts, and HPA scale-down. `make scenarios-list` lists the scenarios and approximate durations.

## Scenario guide

| Scenario | Simulation | Grafana panels and expected alert | Main assertions | Approx. time |
|---|---|---|---|---:|
| baseline | 30 users, all personas, no fault | Health at a glance, request rate/status, latency, business rates; no Shortly alert | 0 unexpected failures, p95 <500 ms, intent rows present, Abuser-only 429s | 4 min |
| latency | 800 ms chaos, then reset | p95 panels rise; `ShortlyHighLatencyP95` fires and resolves | Fault p95 ≥700 ms, no 5xx, recovery p95 <500 ms | 3–8 min |
| errors | 30% chaos errors, then reset | 5xx and error percentage rise; `ShortlyHighErrorRate` fires and resolves | Locust 15–45% in fault window, Prometheus agrees within 10 points, no recovery failures | 5–9 min |
| redis-down | Redis scaled to zero, then restored | Redis up and pod readiness; `ShortlyRedisDown` and `ShortlyPodsNotReady` | `/readyz`=503, load sees errors, app restart counts stay level, saved link still redirects | 4–9 min |
| good-release | v1 to v2 rolling update | Running versions briefly show v1 and v2; no alert | Runner observes both versions during rollout, only v2 at end, no failures | 2–4 min |
| bad-release-errors | Ready v2 with 40% injected request errors, then rollback | Error-rate panels rise; `ShortlyHighErrorRate`, while readiness/crash alerts stay quiet | Release is Ready, mixed-version failure ratio is 10–50%, rollback restores v1 | 5–10 min |
| bad-release-crash | Crash-looping v2, then rollback | Pod restarts; `ShortlyPodCrashLooping` | Old replicas keep serving, bad rollout stalls, rollback restores v1 | 3–6 min |
| surge | 0→200 users, hold, ramp down | HPA desired/current replicas and CPU; no error alert | HPA exceeds 2, failures <1%, HPA returns to 2 within 6 min | 8–12 min |
| abuse | 50% Abuser traffic from a shared IP | Rate-limited/blocked business rates; no error alert | 429/blocked counters rise, no 5xx, `ShortlyHighErrorRate` stays quiet | 4 min |

The runner polls alert transitions every five seconds. It waits up to 240 seconds for alerts to fire, and up to 360 seconds for `ShortlyHighErrorRate` to resolve after chaos reset because the rule uses a five-minute rolling window. It records pending and firing timestamps when visible. Tolerances account for scrape intervals, alert `for:` windows, request scheduling, ingress latency, and mixed-version rollout traffic; expected 4xx are excluded from the failure ratio.

## Live demo script

Keep the `Shortly / Overview` dashboard open in Grafana. Expand **Health at a glance**, **Traffic and errors**, **Where and how**, and **Kubernetes and business**. Keep Locust's Statistics tab beside it, and use a 15-minute Grafana range.

1. **Baseline** — Run `make scenario-baseline`. Point to both app pods, 100% availability, normal request rate, and the Locust intent rows. Say: “The fake users behave like visitors, creators, power users, and one shared-IP abuser; expected client errors are measured, not treated as outages.”
2. **Latency** — Run `make scenario-latency`. Point to p95, latency percentiles, and `ShortlyHighLatencyP95`. Say: “The request path slows while remaining successful; resetting chaos returns p95 to baseline.”
3. **Errors** — Run `make scenario-errors`. Point to 5xx rate, error percentage, and `ShortlyHighErrorRate`. Say: “A 30% injected server-error rate agrees between the client and Prometheus, then clears after reset.”
4. **Good release** — Run `make scenario-good-release`. Point to Running versions during rollout. Say: “v1 and v2 overlap while the zero-unavailable rollout keeps requests successful.”
5. **Bad release: errors** — Run `make scenario-bad-release-errors`. Point to app versions, error panels, and readiness. Say: “The new pods are Ready, but the metrics detect a silent application failure.”
6. **Bad release: crash** — Run `make scenario-bad-release-crash`. Point to Pod restarts and `ShortlyPodCrashLooping`. Say: “The crash-looping release stalls while the old replicas serve traffic; the runner rolls back.”
7. **Redis outage** — Run `make scenario-redis-down`. Point to Redis up, pod readiness, and both outage alerts. Say: “Readiness drops while Redis is down, the API pods survive, and the Redis PVC preserves the link.”
8. **Surge** — Run `make scenario-surge`. Point to HPA current/desired replicas and CPU. Say: “The load ramps up and Kubernetes scales the API, then returns to two replicas after traffic falls.”

## Screenshot checklist

Save screenshots in `docs/screenshots/` when preparing the report:

- `01-baseline-overview.png` — Health at a glance and request rate during baseline.
- `02-baseline-personas.png` — Locust Statistics with named persona request rows.
- `03-latency-p95-alert.png` — p95 panels with `ShortlyHighLatencyP95` firing.
- `04-errors-5xx-alert.png` — 5xx/error percentage with `ShortlyHighErrorRate` firing.
- `05-good-release-versions.png` — Running versions showing v1 and v2 during rollout.
- `06-bad-release-errors.png` — Error-rate alert while deployment replicas remain Ready.
- `07-bad-release-crash.png` — Pod restart panel and crash-loop alert.
- `08-redis-outage.png` — Redis up/readiness panels and outage alerts.
- `09-surge-hpa.png` — HPA current/desired replicas at surge peak.

## Reading Locust results

The UI's Statistics tab groups by fixed request intent; the Failures tab should contain only unexpected status codes, transport failures, or failed content assertions. CSV files include per-request and aggregate rows; the `_stats_history.csv` file supports time-window comparisons. The HTML report is a compact run summary. `result.md` lists each PASS/FAIL assertion, aggregate requests, unexpected failures, p95, and alert timing; `timeline.json` records fault, rollout, alert, reset, and recovery events.

## Troubleshooting

- **Generator CPU above 90%** — The run is invalid. Reduce users or increase `THINK_TIME_SCALE`, then repeat it. Locust's CPU warning is retained in `locust-console.log` and treated as a failed assertion.
- **Spoofed IPs do not reach the app** — Confirm the ingress `use-forwarded-headers` setting with `make k8s-up`, inspect JSON access logs for `client_ip`, and follow the log verification commands in the baseline report. `TRUST_XFF` must be enabled only behind the trusted local ingress.
- **HPA shows `<unknown>`** — Wait for metrics-server readiness, then check `kubectl top nodes` and `kubectl top pods -n urlshortener`. If needed, rerun `make k8s-up` to enable metrics-server.
- **Alerts are slow to fire** — The runner polls every 5 seconds, but Prometheus scrapes at 10 seconds and rules have a 30–60 second `for:`. Keep traffic running through the full alert window and check `make alerts` / `make promq`.
- **macOS/Windows Ingress throughput is poor** — Keep `minikube tunnel` running. Port forwarding is a useful connectivity fallback but can limit a high-concurrency surge; compare with ingress before changing the load shape.
- **Windows** — Run Make and Bash from WSL. Keep Docker Desktop, Minikube, and the WSL network route available.
- **`short.local` does not resolve on the host** — Keep an ingress-controller forward open with `kubectl -n ingress-nginx port-forward service/ingress-nginx-controller 8080:80`, then run a target with `BASE=http://localhost:8080 HOST_HEADER=short.local`.
- **Local chaos probe** — `make load-local` needs the app and Redis at `localhost:8000`/`6379`; `docker compose up -d` starts them. The local compose app uses `change-me` as its admin token unless overridden. Reset it with `DELETE /admin/chaos` after checking errors.

## Design decisions

- **Per-user source IPs:** Faker public IPv4 values persist for each simulated user so the app's IP-keyed limiter treats normal visitors as independent clients. Seeding rotates IPs to stay below the 10-per-minute threshold.
- **Shared Abuser IP:** all Abuser users use the documentation-only TEST-NET address `198.51.100.250`, intentionally concentrating their shorten attempts and producing rate-limit events.
- **Redirects are disabled:** `allow_redirects=False` is passed to every FastHttpUser request, and seed/runner urllib clients install a no-redirect handler. Link targets remain external and are never contacted.
- **FastHttpUser redirect compatibility:** Locust 2.46.6 accepts the `allow_redirects` parameter but toggles a misspelled redirect-code property internally. The `NoRedirectSession` adapter temporarily clears geventhttpclient's actual `redirect_response_codes`; each request also passes `allow_redirects=False`.
- **Single-process pools:** Locust runs in one process for these targets; module-level lists and sets need no lock. Each pool is capped at 500 and randomly evicts one entry when full.
- **Assertions and tolerances:** the latency floor (700 ms) allows network/jitter around the configured 800 ms; recovery is below the existing 500 ms alert threshold. Chaos error ratios use 15–45% around the configured 30%, and Prometheus must be within 10 percentage points. The bad-release range reflects old and new replicas receiving traffic during rollout. Surge must produce less than 1% unexpected failures.
- **Error alert measurement:** the runner samples the Prometheus 1-minute 5xx ratio before resetting chaos, while Locust measures the same fault window. After reset, it allows up to six minutes for `ShortlyHighErrorRate` to clear because its rule uses a five-minute rolling window.
- **Expected expiry window:** the visitor accepts either 302 or 410 only within two seconds of the recorded expiry time. Outside that window, the status is deterministic.
- **Shortly response expiry field:** the current API model serializes `expires_at: null` for links without expiry; the load test treats non-null `expires_at` as the requested expiry and verifies the URL/code/short URL on 201.
- **Local chaos and 4xx:** the app's global chaos middleware runs before ordinary app routes. At `error_pct=100`, it turns normal 4xx paths into 500 responses; `/admin/*` is excluded, so an unauthorized admin request remains 401. The local error-detection check therefore verifies that the 401 row remains expected while normal traffic turns into failures. This records the app's actual middleware behavior without changing app code.
- **Grafana annotations:** the optional annotation stretch is not implemented. Timeline JSON provides the same event timestamps without requiring persistent Grafana API writes or another port-forward.
