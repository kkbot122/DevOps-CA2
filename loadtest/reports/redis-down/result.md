# Scenario: redis-down

Result: **PASS**
Run time: 226.8 s

## Assertions

| Assertion | Result | Detail |
|---|---|---|
| /readyz returned 503 during outage | PASS | 503 |
| Locust saw failures during Redis outage | PASS | 1024 failures in 1032 requests |
| Locust failures returned to zero after recovery | PASS | 0 failures in 501 requests |
| ShortlyRedisDown fired | PASS | 40.57208129198989 |
| ShortlyPodsNotReady fired | PASS | 86.05437425000127 |
| durability link still redirects after Redis outage | PASS | HTTP 302, Location=https://www.example.net/durability/07a8d53bf3ff477c8eecc5e5c031e167 |
| Redis outage did not restart app containers | PASS | before 0, after 0 |
| load generator CPU below 90% warning threshold | PASS | warning absent |

## Load metrics

- Total requests: 2779
- Unexpected failures: 1120
- Failure ratio: 40.30%
- Client p95: 8.0 ms

## Time to alert

- ShortlyRedisDown firing: 40.6 s
- ShortlyRedisDown pending: 10.2 s
- ShortlyPodsNotReady firing: 86.1 s
- ShortlyPodsNotReady pending: 25.4 s
- ShortlyRedisDown resolved: 25.3 s

## Events

See `timeline.json` for timestamped scenario events.
