# Scenario: baseline

Result: **PASS**
Run time: 225.6 s

## Assertions

| Assertion | Result | Detail |
|---|---|---|
| load generator CPU below 90% warning threshold | PASS | warning absent |
| all persona request rows present | PASS | all present |
| 429 rows are confined to Abuser request intents | PASS | only rate-limited named rows |
| zero unexpected failures | PASS | 0 |
| client p95 below 500 ms | PASS | 13.0 ms |
| no Shortly alerts firing | PASS | [] |
| spoofed per-user IPs reach app logs | PASS | 62 distinct client_ip values |
| only the shared Abuser IP receives 429 | PASS | 198.51.100.250 |

## Load metrics

- Total requests: 3628
- Unexpected failures: 0
- Failure ratio: 0.00%
- Client p95: 13.0 ms

## Time to alert

- No alert wait was required.

## Events

See `timeline.json` for timestamped scenario events.
