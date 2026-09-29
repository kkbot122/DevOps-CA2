from datetime import UTC, datetime, timedelta

import fakeredis.aioredis
import httpx
import pytest

from app.config import Settings
from app.main import create_app


class Clock:
    def __init__(self):
        self.value = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        admin_token="test-token",
        rate_limit_per_min=10,
        blocked_domains="evil.example,malware.test,phishing.test",
        app_version="test",
    )


@pytest.fixture
def app(redis, settings, clock):
    return create_app(settings=settings, redis_client=redis, clock=clock, hostname="pod-test")


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c
