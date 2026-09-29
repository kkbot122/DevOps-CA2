import json
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis


class LinkStore:
    def __init__(self, redis: Redis, clock=lambda: datetime.now(UTC)) -> None:
        self.redis = redis
        self.clock = clock

    @staticmethod
    def key(code: str) -> str:
        return f"link:{code}"

    async def claim(
        self, code: str, url: str, created_at: datetime, expires_at: datetime | None
    ) -> bool:
        key = self.key(code)
        claimed = await self.redis.hsetnx(key, "url", url)
        if not claimed:
            return False
        fields = {"created_at": created_at.isoformat(), "clicks": "0"}
        if expires_at is not None:
            fields["expires_at"] = expires_at.isoformat()
        await self.redis.hset(key, mapping=fields)
        if expires_at is not None:
            await self.redis.expire(
                key, max(1, int((expires_at - self.clock()).total_seconds()) + 86400)
            )
        await self.redis.lpush("recent", code)
        await self.redis.ltrim("recent", 0, 49)
        return True

    async def get(self, code: str) -> dict[str, str] | None:
        value = await self.redis.hgetall(self.key(code))
        return value or None

    async def increment_clicks(self, code: str) -> int:
        return int(await self.redis.hincrby(self.key(code), "clicks", 1))

    async def recent_codes(self) -> list[str]:
        return [
            item.decode() if isinstance(item, bytes) else item
            for item in await self.redis.lrange("recent", 0, 49)
        ]

    async def take_rate_limit(self, client_ip: str, limit: int) -> tuple[bool, int]:
        now = self.clock().timestamp()
        bucket = int(now // 60)
        key = f"rate:{client_ip}:{bucket}"
        count = int(await self.redis.incr(key))
        if count == 1:
            await self.redis.expire(key, 60)
        retry_after = max(1, int((bucket + 1) * 60 - now))
        return count <= limit, retry_after

    async def get_chaos(self) -> dict[str, int]:
        value = await self.redis.get("chaos:config")
        if not value:
            return {"latency_ms": 0, "error_pct": 0}
        return json.loads(value)

    async def set_chaos(self, config: dict[str, int]) -> None:
        await self.redis.set("chaos:config", json.dumps(config))

    async def reset_chaos(self) -> None:
        await self.redis.delete("chaos:config")

    def is_expired(self, record: dict[str, Any]) -> bool:
        expires_at = record.get("expires_at")
        if isinstance(expires_at, bytes):
            expires_at = expires_at.decode()
        return bool(expires_at and datetime.fromisoformat(expires_at) <= self.clock())
