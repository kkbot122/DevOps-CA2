# Scenario: bad-release-crash

Result: **PASS**
Run time: 439.0 s

## Assertions

| Assertion | Result | Detail |
|---|---|---|
| CrashLoopBackOff pods observed | PASS | shortly-86bb799dd7-xfdpc |
| bad rollout stopped progressing | PASS | 1 |
| crash-loop alert fired | PASS | 90.16114520799601 |
| zero unexpected failures during rollout | PASS | 0 |
| rollback restored v1 and readiness | PASS | version=v1, ready=True |
| alerts resolved after rollback | PASS | [] |
| load generator CPU below 90% warning threshold | PASS | warning absent |

## Load metrics

- Total requests: 7354
- Unexpected failures: 0
- Failure ratio: 0.00%
- Client p95: 8.0 ms

## Time to alert

- ShortlyPodCrashLooping pending: 29.4 s
- ShortlyPodCrashLooping firing: 90.2 s
- ShortlyPodCrashLooping resolved: 298.2 s

## Events

See `timeline.json` for timestamped scenario events.
