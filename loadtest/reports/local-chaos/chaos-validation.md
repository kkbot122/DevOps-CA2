# Local 100% error chaos validation

Command: `curl -X POST http://localhost:8000/admin/chaos -H 'X-Admin-Token: change-me' -H 'Content-Type: application/json' -d '{"latency_ms":0,"error_pct":100}'`, followed by `make load-local`.

Locust recorded 199 requests and 182 failures (91.46%), demonstrating that unexpected 500 responses appear in failure statistics. The unauthorized admin row recorded 1 request and 0 failures. Rate-limited rows recorded 14 requests and 0 failures. The 100% global chaos middleware intentionally converts ordinary-route 4xx outcomes such as 404, 422, and 403 into 500 before their route handlers can return; the app excludes `/admin/*`, and rate limiting runs before chaos, so 401 and 429 remain expected successes. This behavior is described in `docs/scenarios.md`.

Chaos was reset with `curl -X DELETE http://localhost:8000/admin/chaos -H 'X-Admin-Token: change-me'`. The CSV and HTML output from the run are stored in this directory.
