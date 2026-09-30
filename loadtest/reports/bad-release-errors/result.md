# Scenario: bad-release-errors

Result: **PASS**
Run time: 519.0 s

## Assertions

| Assertion | Result | Detail |
|---|---|---|
| bad error release completed and pods stayed Ready | PASS | image=shortly:v2-bad-errors, ready=True |
| error alert fired | PASS | 130.83497933400213 |
| no crash loop or not-ready alert | PASS | [] |
| fault failure ratio between 10% and 50% | PASS | 24.38% |
| rollback restores v1 | PASS | v1 |
| zero failures after rollback | PASS | 0 |
| error alert resolved after rollback | PASS | 232.9534621250059 |
| load generator CPU below 90% warning threshold | PASS | warning absent |

## Load metrics

- Total requests: 4272
- Unexpected failures: 639
- Failure ratio: 14.96%
- Client p95: 8.0 ms

## Time to alert

- ShortlyHighErrorRate firing: 130.8 s
- ShortlyHighErrorRate pending: 70.3 s
- ShortlyHighErrorRate resolved: 233.0 s

## Events

See `timeline.json` for timestamped scenario events.
