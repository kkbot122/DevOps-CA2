# Scenario: errors

Result: **PASS**
Run time: 494.7 s

## Assertions

| Assertion | Result | Detail |
|---|---|---|
| error alert fired | PASS | 131.47594766700058 |
| Locust fault failure ratio 15-45% | PASS | 25.04% |
| Prometheus and Locust error ratios within 10 points | PASS | Prometheus 25.07%, Locust 25.04% |
| zero failures after recovery | PASS | 0 failures |
| alert resolved after reset | PASS | 242.71468308300246 |
| load generator CPU below 90% warning threshold | PASS | warning absent |

## Load metrics

- Total requests: 7933
- Unexpected failures: 605
- Failure ratio: 7.63%
- Client p95: 8.0 ms

## Time to alert

- ShortlyHighErrorRate pending: 75.9 s
- ShortlyHighErrorRate firing: 131.5 s
- ShortlyHighErrorRate resolved: 242.7 s

## Events

See `timeline.json` for timestamped scenario events.
