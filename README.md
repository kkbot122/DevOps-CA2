# shortly

**shortly** is a small, production-style URL shortener built with FastAPI and Redis. It stores links, click counts, recent-link data, rate limits, and demo chaos settings in Redis so multiple app replicas can share state.

## Features

- Generated or custom short codes, expiry, and blocked destination domains.
- Atomic alias claims, click statistics, recent links, and fixed-window rate limiting.
- JSON access logs, Prometheus metrics, readiness/liveness endpoints, and request IDs.
- Redis-backed chaos controls and a bad-release simulation for deployment demos.
- Responsive, accessible single-page UI rendered by Jinja2.

## Quickstart

```sh
make redis
make install
make dev
```

Open <http://localhost:8000>. Or run `docker compose up` to start the app and Redis together. `make test`, `make lint`, and `make fmt` run the test, lint, and formatting workflows.

`make install` creates `.venv` with Python 3.12 and installs the pinned runtime and development dependencies. Set `PYTHON` when your Python 3.12 executable has a different name or path.

## Endpoints

| Method | Path | Success | Errors |
|---|---|---:|---|
| GET | `/` | 200 | — |
| POST | `/api/shorten` | 201 | 403, 409, 422, 429, 503, 500 |
| GET | `/{code}` | 302 | 404, 410, 500 |
| GET | `/api/links/{code}/stats` | 200 | 404, 410 |
| GET | `/api/links/recent` | 200 | 422 |
| GET | `/healthz` | 200 | — |
| GET | `/readyz` | 200 | 503 |
| GET | `/version` | 200 | — |
| GET/POST/DELETE | `/admin/chaos` | 200 | 401, 422 |
| GET | `/metrics` | 200 | — |

## Curl examples

Set `BASE=http://localhost:8000` in one terminal. Start an app with `make dev` and Redis running.

```sh
# 201 Created
curl -i -X POST "$BASE/api/shorten" -H 'Content-Type: application/json' -d '{"url":"https://example.com"}'

# 302 Found (use the code returned above)
curl -i "$BASE/<code>"

# 404 Not Found
curl -i "$BASE/not-a-real-code"

# 409 Conflict
curl -i -X POST "$BASE/api/shorten" -H 'Content-Type: application/json' -d '{"url":"https://example.com","alias":"taken"}'
curl -i -X POST "$BASE/api/shorten" -H 'Content-Type: application/json' -d '{"url":"https://example.org","alias":"taken"}'

# 410 Gone
curl -i -X POST "$BASE/api/shorten" -H 'Content-Type: application/json' -d '{"url":"https://example.com","alias":"one-min","expires_in_seconds":1}'
sleep 2
curl -i "$BASE/one-min"

# 422 Unprocessable Entity
curl -i -X POST "$BASE/api/shorten" -H 'Content-Type: application/json' -d '{"url":"ftp://example.com"}'

# 403 Forbidden
curl -i -X POST "$BASE/api/shorten" -H 'Content-Type: application/json' -d '{"url":"https://evil.example/path"}'

# 429 Too Many Requests (repeat until the 11th request from this IP)
for n in $(seq 1 11); do curl -s -o /dev/null -w '%{http_code}\n' -X POST "$BASE/api/shorten" -H 'Content-Type: application/json' -d '{"url":"https://example.com"}'; done

# 503 Service Unavailable (stop Redis temporarily, then request readiness)
curl -i "$BASE/readyz"
```

The first `taken` request returns 201 and the second returns 409. The 410 example uses a one-second expiry; allow two seconds before requesting it. Restart Redis after the 503 example.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `APP_VERSION` | `dev` | Version in API, UI, and logs |
| `BASE_URL` | empty | Override short-link origin; otherwise use request/forwarded host |
| `ADMIN_TOKEN` | `change-me` | `X-Admin-Token` for `/admin/*` |
| `RATE_LIMIT_PER_MIN` | `10` | Max shorten requests per fixed minute window per IP |
| `TRUST_XFF` | `true` | Use the first forwarded IP; only enable behind a trusted proxy |
| `BLOCKED_DOMAINS` | `evil.example,malware.test,phishing.test` | Comma-separated host suffix blocklist |
| `BAD_RELEASE_MODE` | `none` | `none`, `crash`, or `errors` demo mode |
| `BAD_RELEASE_ERROR_PCT` | `40` | Failure percentage in errors mode |
| `LOG_LEVEL` | `INFO` | Python logging threshold |

## Design decisions

- **Redis key schema:** `link:{code}` hashes hold `url`, `created_at`, `clicks`, and optional `expires_at`; `recent` is a newest-first list capped at 50 codes; `rate:{ip}:{minute}` is a fixed-window counter; `chaos:config` stores shared JSON settings.
- **External state:** app processes remain stateless so a load balancer can send consecutive requests to different replicas. Redis owns all link state and shared controls.
- **Expiry and 410:** links keep their Redis hash until 24 hours after `expires_at`; reads check that timestamp and return 410 during the retention window. Once Redis deletes the key, reads return 404.
- **Rate limits:** a Redis `INCR` counter is keyed by client IP and the current UTC minute bucket, with a 60-second TTL. The check runs in middleware before request validation, so invalid requests consume quota too.
- **Chaos configuration:** the admin API writes to Redis so every replica observes the same controls; each replica caches the value for at most one second to avoid a Redis read on every request.
- **Forwarded addresses:** `TRUST_XFF=true` trusts the first `X-Forwarded-For` value. Set it only when a trusted reverse proxy replaces or sanitizes that header; direct clients could otherwise spoof their rate-limit identity.

## Demo-only features

`/admin/chaos` is intended only for demos. It requires `X-Admin-Token`; `GET` reads the current `latency_ms` and `error_pct`, `POST` sets them, and `DELETE` resets both to zero. The chaos middleware skips liveness, readiness, metrics, admin, and static paths, and fails open if Redis cannot supply its settings.

`BAD_RELEASE_MODE=crash` raises during startup to simulate a crash loop. `BAD_RELEASE_MODE=errors` injects failures for a configured percentage of shorten and redirect requests while health probes continue to pass, demonstrating why health checks alone do not detect application failures. These modes are for demo only.
