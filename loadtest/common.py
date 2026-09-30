"""Shared host-side Locust configuration and state for Shortly personas."""

from __future__ import annotations

import json
import os
import random
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from urllib.parse import urlsplit

from faker import Faker

fake = Faker()
BASE = os.getenv("BASE", "http://short.local").rstrip("/")
HOST_HEADER = os.getenv("HOST_HEADER", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "demo-admin-token")
THINK_TIME_SCALE = max(0.0, float(os.getenv("THINK_TIME_SCALE", "1.0")))
ABUSER_IP = "198.51.100.250"
PERSONA_WEIGHTS = {"visitor": 60, "creator": 25, "power": 10, "abuser": 5}
for _item in os.getenv("PERSONA_WEIGHTS", "").split(","):
    if "=" in _item:
        _key, _value = _item.split("=", 1)
        if _key.strip() in PERSONA_WEIGHTS:
            PERSONA_WEIGHTS[_key.strip()] = max(0, int(_value))

live_links: list[dict[str, str]] = []
expiring_links: list[dict[str, str]] = []
aliases: set[str] = set()


def metadata_headers(ip: str, user_agent: str) -> dict[str, str]:
    """Build request metadata consistently for seeded and simulated users."""
    headers = {
        "X-Forwarded-For": ip,
        "User-Agent": user_agent,
        "X-Request-ID": str(uuid.uuid4()),
    }
    if HOST_HEADER:
        headers["Host"] = HOST_HEADER
    return headers


def fake_headers(user) -> dict[str, str]:
    """Build per-request metadata while preserving each user's stable source IP."""
    return metadata_headers(user.fake_ip, user.user_agent)


def expect(resp_ctx, allowed: set[int], name: str) -> bool:
    """Mark expected statuses as successes and all others as real Locust failures."""
    status = getattr(resp_ctx, "status_code", 0)
    if status == 429 and 429 in allowed and "[rate limited]" not in name:
        name = f"{name} [rate limited]"
    metadata = getattr(resp_ctx, "request_meta", None)
    if isinstance(metadata, dict):
        metadata["name"] = name
    if status not in allowed:
        resp_ctx.failure(f"{name}: expected {sorted(allowed)}, got {status}")
        return False
    # FastHttpUser also marks 4xx as transport-level status errors; explicitly
    # clear that default for the outcomes this scenario intentionally expects.
    resp_ctx.success()
    return True


def add_pool(pool: list[dict[str, str]], item: dict[str, str], limit: int = 500) -> None:
    if len(pool) >= limit:
        del pool[random.randrange(len(pool))]
    pool.append(item)


def add_alias(alias: str, limit: int = 500) -> None:
    if len(aliases) >= limit:
        aliases.discard(random.choice(tuple(aliases)))
    aliases.add(alias)


def choose_safe_url() -> str:
    """Generate a realistic external target while excluding the configured blocklist."""
    blocked = {
        item.strip().lower().rstrip(".")
        for item in os.getenv("BLOCKED_DOMAINS", "evil.example,malware.test,phishing.test").split(
            ","
        )
        if item.strip()
    }
    for _ in range(20):
        domain = fake.domain_name().lower().rstrip(".")
        host = f"www.{domain}"
        if not any(host == item or host.endswith("." + item) for item in blocked):
            return f"https://{host}/{fake.slug()}?ref={fake.word()}"
    return f"https://www.example.net/{fake.slug()}?ref={fake.word()}"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Seed requests must never follow a short-link redirect off-cluster."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def seed_links(count: int = 30) -> None:
    """Seed reusable links with distinct source IPs so initial traffic is useful."""
    opener = urllib.request.build_opener(NoRedirect)
    seed_alias = f"seed-{uuid.uuid4().hex[:8]}"
    for index in range(count):
        payload = {"url": choose_safe_url()}
        if index == 0:
            payload["alias"] = seed_alias
        body = json.dumps(payload).encode()
        seed_headers = {
            "Content-Type": "application/json",
            **metadata_headers(fake.ipv4_public(), fake.user_agent()),
        }
        request = urllib.request.Request(
            f"{BASE}/api/shorten",
            data=body,
            method="POST",
            headers=seed_headers,
        )
        try:
            with opener.open(request, timeout=5) as response:
                if response.status != 201:
                    continue
                payload = json.loads(response.read())
                entry = {
                    "code": str(payload["code"]),
                    "url": str(payload["url"]),
                    "created_at": str(payload.get("created_at", "")),
                }
                add_pool(live_links, entry)
                if index == 0:
                    add_alias(seed_alias)
        except (
            OSError,
            urllib.error.URLError,
            urllib.error.HTTPError,
            KeyError,
            ValueError,
        ) as exc:
            if index == 0:
                print(f"WARNING: Locust seed request failed; continuing without seeds: {exc}")
            break


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC)


def response_json(resp_ctx) -> dict:
    try:
        data = resp_ctx.json()
        if not isinstance(data, dict):
            raise ValueError("JSON response is not an object")
        return data
    except (ValueError, json.JSONDecodeError) as exc:
        resp_ctx.failure(f"invalid JSON response: {exc}")
        return {}


def verify_created(resp_ctx, url: str, expiry_requested: bool) -> dict:
    data = response_json(resp_ctx)
    if not data:
        return {}
    missing = {"code", "short_url", "url"} - data.keys()
    if missing:
        resp_ctx.failure(f"created link response missing fields: {sorted(missing)}")
    if data.get("url") != url:
        resp_ctx.failure("created link response URL differs from submitted URL")
    if not isinstance(data.get("code"), str) or not data["code"]:
        resp_ctx.failure("created link response has no code")
    if not isinstance(data.get("short_url"), str) or not urlsplit(data["short_url"]).scheme:
        resp_ctx.failure("created link response has no absolute short_url")
    if expiry_requested != (data.get("expires_at") is not None):
        resp_ctx.failure("created link expiry does not match the request")
    if "created_at" not in data:
        resp_ctx.failure("created link response has no created_at")
    return data


def assert_redirect(resp_ctx, url: str) -> bool:
    location = (getattr(resp_ctx, "headers", {}) or {}).get("Location")
    if location != url:
        resp_ctx.failure(f"redirect Location mismatch: expected {url!r}, got {location!r}")
        return False
    return True
