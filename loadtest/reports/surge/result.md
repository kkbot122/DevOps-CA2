# Scenario: surge

Result: **PASS**
Run time: 382.8 s

## Assertions

| Assertion | Result | Detail |
|---|---|---|
| HPA rose above two replicas | PASS | max 3 |
| unexpected failure ratio below 1% | PASS | 0.00% |
| ShortlyHighErrorRate did not fire | PASS | [] |
| HPA returned to two replicas | PASS | (2, 2) |
| load generator CPU below 90% warning threshold | PASS | warning absent |

## Load metrics

- Total requests: 24874
- Unexpected failures: 0
- Failure ratio: 0.00%
- Client p95: 7.0 ms

## Time to alert

- No alert wait was required.

## Events

See `timeline.json` for timestamped scenario events.
