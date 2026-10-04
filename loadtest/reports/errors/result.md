# Scenario: errors

Result: **PASS**
Run time: 520.6 s

## Assertions

| Assertion | Result | Detail |
|---|---|---|
| error alert fired | PASS | 126.51743204100057 |
| Locust fault failure ratio 15-45% | PASS | 24.77% |
| Prometheus and Locust error ratios within 10 points | PASS | Prometheus 23.86%, Locust 24.77% |
| zero failures after recovery | PASS | 0 failures |
| alert resolved after reset | PASS | 273.6496560420055 |
| load generator CPU below 90% warning threshold | PASS | warning absent |

## Load metrics

- Total requests: 8439
- Unexpected failures: 615
- Failure ratio: 7.29%
- Client p95: 12.0 ms

## Time to alert

- ShortlyHighErrorRate pending: 70.9 s
- ShortlyHighErrorRate firing: 126.5 s
- ShortlyHighErrorRate resolved: 273.6 s

## Events

See `timeline.json` for timestamped scenario events.
