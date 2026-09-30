# Scenario: abuse

Result: **PASS**
Run time: 225.6 s

## Assertions

| Assertion | Result | Detail |
|---|---|---|
| rate-limited counter increased | PASS | 3796.0 |
| blocked counter increased | PASS | 4.0 |
| ShortlyHighErrorRate did not fire | PASS | [] |
| zero 5xx failures | PASS | 0 |
| load generator CPU below 90% warning threshold | PASS | warning absent |

## Load metrics

- Total requests: 6309
- Unexpected failures: 0
- Failure ratio: 0.00%
- Client p95: 7.0 ms

## Time to alert

- No alert wait was required.

## Events

See `timeline.json` for timestamped scenario events.
