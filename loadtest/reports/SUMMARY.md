# Phase 4 scenario summary

Date: 2026-09-30
Chart version: 91.8.2
Image tags: shortly:v1, shortly:v2, shortly:v2-bad-crash, shortly:v2-bad-errors
Total scenario-all time: 55.7 minutes

| Scenario | Result | Key metric(s) | Alert time (s) | Requests | Failures | p95 (ms) |
|---|---|---|---:|---:|---:|---:|
| baseline | PASS | 3 min of normal mixed-persona behavior; no faults |  | 3753 | 0 | 8.0 |
| abuse | FAIL | shared-IP bad-actor traffic and client-error alert hygiene |  | 6187 | 0 | 7.0 |
| latency | PASS | fault injected  | 76.0  | 3865 | 0 | 810.0 |
| errors | PASS | fault injected  | 131.5  | 7933 | 605 | 8.0 |
| redis-down | PASS | fault injected  | 40.6  | 2779 | 1120 | 8.0 |
| good-release | PASS | rollout complete  |  | 1264 | 0 | 9.0 |
| bad-release-errors | PASS | Ready but broken v2, error alert, then rollback | 130.8  | 4272 | 639 | 8.0 |
| bad-release-crash | PASS | crash-looping rollout, alert, then rollback | 90.2  | 7354 | 0 | 8.0 |
| surge | PASS | hpa scaled above two  |  | 24874 | 0 | 7.0 |

How to read this: unexpected responses and failed content assertions count as failures. Expected client errors such as 404, 409, 410, 422, 403, and 429 have named rows in Locust and do not count as failures. Scenario details, assertions, and timestamped events are in each scenario directory.

## Follow-up verification

After this `scenario-all` run, the abuse counter check was corrected to aggregate Prometheus series across all Shortly pods. The focused `scenario-abuse` rerun on 2026-09-30 passed in 225.6 seconds: 6,309 requests, zero unexpected failures, rate-limited counter increase of 3,796, and blocked counter increase of 4. No error alert fired. The full `scenario-all` suite was not rerun, so the table above remains the result of the earlier run and still records its original abuse failure.

The final `make smoke BASE=http://127.0.0.1:8080 HOST_HEADER=short.local` verification passed all 11 checks.
