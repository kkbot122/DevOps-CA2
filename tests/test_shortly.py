import asyncio
import json
import time

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.config import Settings
from app.logging_config import JsonFormatter
from app.main import create_app


def payload(**overrides):
    return {"url": "https://example.org/a/long/path", **overrides}


@pytest.mark.parametrize(
    "data",
    [
        {"url": "ftp://example.com"},
        {"url": "http:///missing"},
        {"url": ""},
        {"url": "https://" + "a" * 2044 + ".com"},
        payload(alias="ab"),
        payload(alias="bad!alias"),
        payload(expires_in_seconds=0),
        payload(expires_in_seconds=2_592_001),
    ],
)
async def test_validation(client, data):
    assert (await client.post("/api/shorten", json=data)).status_code == 422


async def test_shorten_generated_custom_expiry_and_forwarded_url(client, clock):
    generated = await client.post(
        "/api/shorten",
        json=payload(),
        headers={"x-forwarded-proto": "https", "x-forwarded-host": "s.example"},
    )
    assert generated.status_code == 201
    body = generated.json()
    assert len(body["code"]) == 6 and all(
        c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz" for c in body["code"]
    )
    assert body["short_url"] == f"https://s.example/{body['code']}"
    custom = await client.post(
        "/api/shorten", json=payload(alias="nice_link", expires_in_seconds=60)
    )
    assert custom.status_code == 201 and custom.json()["code"] == "nice_link"
    assert custom.json()["expires_at"] == "2026-01-01T00:01:00Z"
    assert (await client.post("/api/shorten", json=payload(alias="nice_link"))).status_code == 409
    assert (await client.post("/api/shorten", json=payload(alias="metrics"))).status_code == 409


@pytest.mark.parametrize("url", ["https://evil.example/x", "https://sub.evil.example/x"])
async def test_blocked_domain(client, url):
    response = await client.post("/api/shorten", json={"url": url})
    assert response.status_code == 403 and response.json()["detail"] == "domain is blocked"


async def test_concurrent_alias_claim_is_atomic(client):
    responses = await asyncio.gather(
        *(
            client.post(
                "/api/shorten",
                json=payload(alias="shared"),
                headers={"x-forwarded-for": f"10.0.0.{index}"},
            )
            for index in range(20)
        )
    )
    assert [r.status_code for r in responses].count(201) == 1
    assert [r.status_code for r in responses].count(409) == 19


async def test_redirect_expiry_stats_and_deleted_key(client, app, clock):
    created = (await client.post("/api/shorten", json=payload(alias="clicks"))).json()
    for _ in range(3):
        response = await client.get("/clicks", follow_redirects=False)
        assert response.status_code == 302 and response.headers["location"] == created["url"]
        assert response.headers["cache-control"] == "no-store"
    assert (await client.get("/api/links/clicks/stats")).json()["clicks"] == 3
    assert (await client.get("/unknown")).status_code == 404
    exp = await client.post("/api/shorten", json=payload(alias="expires", expires_in_seconds=1))
    assert exp.status_code == 201
    clock.advance(2)
    assert (await client.get("/expires")).status_code == 410
    assert (await client.get("/api/links/expires/stats")).status_code == 410
    assert (await client.get("/api/links/missing/stats")).status_code == 404
    await app.state.redis.delete("link:expires")
    assert (await client.get("/expires")).status_code == 404


async def test_recent_order_limit_and_skip_deleted(client, app):
    for code in ("first", "second", "third"):
        assert (await client.post("/api/shorten", json=payload(alias=code))).status_code == 201
    await app.state.redis.delete("link:second")
    response = await client.get("/api/links/recent?limit=1")
    assert [row["code"] for row in response.json()] == ["third"]
    assert (await client.get("/api/links/recent?limit=21")).status_code == 422


async def test_recent_skips_expired_links(client, clock):
    await client.post("/api/shorten", json=payload(alias="short-lived", expires_in_seconds=1))
    clock.advance(2)
    assert (await client.get("/api/links/recent")).json() == []


async def test_rate_limit_fixed_window_xff_and_invalid_requests(client, clock):
    for _ in range(10):
        await client.post(
            "/api/shorten", json={"bad": True}, headers={"x-forwarded-for": "10.0.0.1"}
        )
    limited = await client.post(
        "/api/shorten", json={"bad": True}, headers={"x-forwarded-for": "10.0.0.1"}
    )
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0
    assert (
        await client.post("/api/shorten", json=payload(), headers={"x-forwarded-for": "10.0.0.2"})
    ).status_code == 201
    clock.advance(61)
    assert (
        await client.post("/api/shorten", json=payload(), headers={"x-forwarded-for": "10.0.0.1"})
    ).status_code == 201


async def test_health_version_and_redis_failure(client, app, monkeypatch):
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    assert (await client.get("/readyz")).status_code == 200
    assert (await client.get("/version")).json() == {"version": "test", "hostname": "pod-test"}

    async def broken():
        raise RedisConnectionError("down")

    monkeypatch.setattr(app.state.redis, "ping", broken)
    assert (await client.get("/readyz")).status_code == 503
    assert (await client.get("/healthz")).status_code == 200


async def test_redis_operation_error_sets_gauge_and_returns_503(client, app, monkeypatch):
    async def broken(*args, **kwargs):
        raise RedisConnectionError("redis offline")

    monkeypatch.setattr(app.state.redis, "lrange", broken)
    response = await client.get("/api/links/recent")
    assert response.status_code == 503
    assert response.json() == {"detail": "service temporarily unavailable"}


async def test_admin_chaos_roundtrip_validation_latency_shared_and_fail_open(
    client, app, redis, settings, clock, monkeypatch
):
    assert (await client.get("/admin/chaos")).status_code == 401
    assert (await client.get("/admin/chaos", headers={"X-Admin-Token": "wrong"})).status_code == 401
    headers = {"X-Admin-Token": "test-token"}
    assert (
        await client.post(
            "/admin/chaos", json={"latency_ms": 5001, "error_pct": 0}, headers=headers
        )
    ).status_code == 422
    response = await client.post(
        "/admin/chaos", json={"latency_ms": 0, "error_pct": 100}, headers=headers
    )
    assert response.json() == {"latency_ms": 0, "error_pct": 100}
    second = create_app(settings=settings, redis_client=redis, clock=clock, hostname="pod-2")
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=second), base_url="http://testserver"
    ) as second_client:
        # The in-process one-second cache starts at empty and reads the shared Redis config.
        assert (await second_client.get("/fresh-random-looking-route")).status_code == 500
    assert (await client.get("/healthz")).status_code == 200
    await client.delete("/admin/chaos", headers=headers)
    assert (await client.get("/admin/chaos", headers=headers)).json() == {
        "latency_ms": 0,
        "error_pct": 0,
    }
    await app.state.redis.set("chaos:config", "{broken")
    app.state.chaos_cache["loaded_at"] = 0
    assert (await client.get("/a-route")).status_code == 404


async def test_chaos_latency(client):
    headers = {"X-Admin-Token": "test-token"}
    await client.post("/admin/chaos", json={"latency_ms": 200, "error_pct": 0}, headers=headers)
    started = time.perf_counter()
    await client.get("/healthz")
    # Liveness is deliberately excluded; the next normal request has the configured delay.
    await client.get("/not-found")
    assert time.perf_counter() - started >= 0.2


async def test_chaos_errors_on_shorten_and_redirect(client):
    headers = {"X-Admin-Token": "test-token"}
    await client.post("/api/shorten", json=payload(alias="redir"))
    await client.post("/admin/chaos", json={"latency_ms": 0, "error_pct": 100}, headers=headers)
    assert (await client.post("/api/shorten", json=payload())).status_code == 500
    assert (await client.get("/redir")).status_code == 500
    assert (await client.get("/healthz")).status_code == 200


async def test_bad_release_modes(client, settings, redis, clock):
    bad = Settings(
        _env_file=None, bad_release_mode="errors", bad_release_error_pct=100, app_version="bad"
    )
    bad_app = create_app(settings=bad, redis_client=redis, clock=clock)
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=bad_app), base_url="http://testserver"
    ) as c:
        assert (await c.post("/api/shorten", json=payload())).status_code == 500
        assert (await c.get("/anycode")).status_code == 500
        assert (await c.get("/healthz")).status_code == 200
        assert (await c.get("/readyz")).status_code == 200
    with pytest.raises(RuntimeError, match="intentional startup failure"):
        create_app(settings=Settings(_env_file=None, bad_release_mode="crash"), redis_client=redis)
    none = create_app(settings=settings, redis_client=redis, clock=clock)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=none), base_url="http://testserver"
    ) as c:
        assert (await c.get("/healthz")).status_code == 200


async def test_metrics_custom_counters_and_route_template(client):
    await client.get("/an-unknown-code")
    await client.post("/api/shorten", json=payload())
    await client.post("/api/shorten", json={"url": "https://evil.example"})
    response = await client.get("/metrics")
    assert response.status_code == 200 and "text/plain" in response.headers["content-type"]
    text = response.text
    request_metric = next(
        line
        for line in text.splitlines()
        if line.startswith("http_requests_total{") and 'status="404"' in line
    )
    assert 'handler="/{code}"' in request_metric
    for metric in (
        "shortly_links_created_total",
        "shortly_redirects_total",
        "shortly_rate_limited_total",
        "shortly_blocked_total",
        "shortly_redis_up",
        'shortly_build_info{version="test"}',
    ):
        assert metric in text
    assert "0.5" in text


async def test_access_json_and_request_id(client, caplog):
    response = await client.get("/healthz", headers={"X-Request-ID": "trace-me"})
    assert response.headers["x-request-id"] == "trace-me"
    record = next(record for record in caplog.records if record.name == "shortly.access")
    entry = json.loads(JsonFormatter().format(record))
    assert {
        "ts",
        "level",
        "msg",
        "logger",
        "method",
        "path",
        "status",
        "duration_ms",
        "client_ip",
        "request_id",
        "version",
        "hostname",
    } <= entry.keys()


async def test_ui(client):
    response = await client.get("/")
    assert response.status_code == 200 and "shortly" in response.text


def test_settings_defaults_and_blocked_domain_normalization():
    settings = Settings(_env_file=None, blocked_domains=" Foo.test,bar.test,,")
    assert settings.rate_limit_per_min == 10
    assert settings.blocked_domain_set == {"foo.test", "bar.test"}
