# Scenario: latency

Result: **PASS**
Run time: 277.4 s

## Assertions

| Assertion | Result | Detail |
|---|---|---|
| latency alert fired | PASS | 86.01908624999487 |
| fault p95 at least 700 ms | PASS | 814.3 ms |
| no 5xx during latency fault | PASS | 0 unexpected failures |
| recovery p95 below 500 ms | PASS | 12.7 ms |
| alert resolved after reset | PASS | 70.92513083299855 |
| load generator CPU below 90% warning threshold | PASS | warning absent |

## Load metrics

- Total requests: 4065
- Unexpected failures: 0
- Failure ratio: 0.00%
- Client p95: 810.0 ms

## Time to alert

- ShortlyHighLatencyP95 pending: 10.2 s
- ShortlyHighLatencyP95 firing: 86.0 s
- ShortlyHighLatencyP95 resolved: 70.9 s

## Events

See `timeline.json` for timestamped scenario events.
