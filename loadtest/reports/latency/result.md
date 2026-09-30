# Scenario: latency

Result: **PASS**
Run time: 257.1 s

## Assertions

| Assertion | Result | Detail |
|---|---|---|
| latency alert fired | PASS | 75.96830433301511 |
| fault p95 at least 700 ms | PASS | 811.1 ms |
| no 5xx during latency fault | PASS | 0 unexpected failures |
| recovery p95 below 500 ms | PASS | 8.0 ms |
| alert resolved after reset | PASS | 60.661961457983125 |
| load generator CPU below 90% warning threshold | PASS | warning absent |

## Load metrics

- Total requests: 3865
- Unexpected failures: 0
- Failure ratio: 0.00%
- Client p95: 810.0 ms

## Time to alert

- ShortlyHighLatencyP95 pending: 15.2 s
- ShortlyHighLatencyP95 firing: 76.0 s
- ShortlyHighLatencyP95 resolved: 60.7 s

## Events

See `timeline.json` for timestamped scenario events.
