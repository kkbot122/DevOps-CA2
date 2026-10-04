# Scenario: good-release

Result: **PASS**
Run time: 91.0 s

## Assertions

| Assertion | Result | Detail |
|---|---|---|
| both v1 and v2 observed during rollout | PASS | v1, v2 |
| only v2 at end | PASS | v2 |
| rollout completed | PASS | 15.9 s |
| zero unexpected failures during rollout | PASS | 0 |
| no Shortly alerts firing | PASS | [] |
| load generator CPU below 90% warning threshold | PASS | warning absent |

## Load metrics

- Total requests: 1173
- Unexpected failures: 0
- Failure ratio: 0.00%
- Client p95: 9.0 ms

## Time to alert

- No alert wait was required.

## Events

See `timeline.json` for timestamped scenario events.
