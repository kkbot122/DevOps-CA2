import re
from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
RESERVED_CODES = {
    "api",
    "admin",
    "healthz",
    "readyz",
    "metrics",
    "version",
    "static",
    "docs",
    "redoc",
    "openapi.json",
}


class ShortenRequest(BaseModel):
    url: str
    alias: str | None = None
    expires_in_seconds: int | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value or len(value) > 2048 or any(char.isspace() for char in value):
            raise ValueError(
                "URL must be non-empty, at most 2048 characters, and contain no whitespace"
            )
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("URL scheme must be http or https")
        if not parsed.hostname:
            raise ValueError("URL host is required")
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError("URL has an invalid port") from exc
        return value

    @field_validator("alias")
    @classmethod
    def validate_alias(cls, value: str | None) -> str | None:
        if value is not None and not ALIAS_PATTERN.fullmatch(value):
            raise ValueError("Alias must be 3-32 characters using letters, numbers, _ or -")
        return value

    @field_validator("expires_in_seconds")
    @classmethod
    def validate_expiry(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 2_592_000:
            raise ValueError("Expiry must be between 1 and 2592000 seconds")
        return value


class ShortenResponse(BaseModel):
    code: str
    short_url: str
    url: str
    created_at: datetime
    expires_at: datetime | None


class ChaosConfig(BaseModel):
    latency_ms: int = Field(ge=0, le=5000)
    error_pct: int = Field(ge=0, le=100)


class LinkStats(BaseModel):
    code: str
    url: str
    short_url: str
    clicks: int
    created_at: datetime
    expires_at: datetime | None
    expired: bool


class RecentLink(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    short_url: str
    url: str
    clicks: int
    created_at: datetime
    expires_at: datetime | None
