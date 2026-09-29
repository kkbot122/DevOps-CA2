from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    redis_url: str = "redis://localhost:6379/0"
    app_version: str = "dev"
    base_url: str = ""
    admin_token: str = "change-me"
    rate_limit_per_min: int = 10
    trust_xff: bool = True
    blocked_domains: str = "evil.example,malware.test,phishing.test"
    bad_release_mode: str = "none"
    bad_release_error_pct: int = 40
    log_level: str = "INFO"

    @property
    def blocked_domain_set(self) -> set[str]:
        return {
            item.strip().lower().rstrip(".")
            for item in self.blocked_domains.split(",")
            if item.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
