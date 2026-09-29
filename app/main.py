import logging
import socket
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator import metrics as instrumentator_metrics
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware

from app import metrics
from app.config import Settings, get_settings
from app.logging_config import configure_logging
from app.middleware import BadReleaseMiddleware, ChaosMiddleware, RequestMiddleware
from app.routes import admin, health, links, redirect, ui
from app.storage import LinkStore

HTTP_INSTRUMENTATION = instrumentator_metrics.default(
    latency_highr_buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
    latency_lowr_buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)


def create_app(
    settings: Settings | None = None, redis_client=None, clock=None, hostname: str | None = None
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    if settings.bad_release_mode == "crash":
        raise RuntimeError("BAD_RELEASE_MODE=crash: intentional startup failure (demo only)")
    clock = clock or (lambda: datetime.now(UTC))
    client = redis_client or Redis.from_url(settings.redis_url, decode_responses=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if redis_client is None:
            await client.aclose()

    app = FastAPI(title="shortly", version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings
    app.state.redis = client
    app.state.store = LinkStore(client, clock)
    app.state.clock = clock
    app.state.hostname = hostname or socket.gethostname()
    app.state.chaos_cache = {"latency_ms": 0, "error_pct": 0, "loaded_at": 0.0}
    metrics.build_info.labels(version=settings.app_version).set(1)

    async def rate_limit(request: Request, call_next):
        if request.method == "POST" and request.url.path == "/api/shorten":
            client_ip = request.client.host if request.client else "unknown"
            if settings.trust_xff and request.headers.get("x-forwarded-for"):
                client_ip = request.headers["x-forwarded-for"].split(",", 1)[0].strip()
            try:
                allowed, retry_after = await app.state.store.take_rate_limit(
                    client_ip, settings.rate_limit_per_min
                )
            except Exception:
                metrics.redis_up.set(0)
                logger = logging.getLogger("shortly")
                logger.exception("rate limit storage unavailable")
                return JSONResponse({"detail": "service temporarily unavailable"}, status_code=503)
            if not allowed:
                metrics.rate_limited.inc()
                return JSONResponse(
                    {"detail": "rate limit exceeded"},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
        return await call_next(request)

    app.add_middleware(BadReleaseMiddleware)
    app.add_middleware(ChaosMiddleware)
    app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limit)
    app.add_middleware(RequestMiddleware)
    app.include_router(ui.router)
    app.include_router(links.router)
    app.include_router(admin.router)
    app.include_router(health.router)
    # A bespoke histogram is exported with route-template labels by instrumentator.
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/metrics"],
    ).add(HTTP_INSTRUMENTATION)
    instrumentator.instrument(app).expose(app, include_in_schema=False)
    app.include_router(redirect.router)

    @app.exception_handler(RedisError)
    async def redis_error_handler(request: Request, exc: RedisError):
        metrics.redis_up.set(0)
        logging.getLogger("shortly").exception("Redis operation failed", exc_info=exc)
        return JSONResponse({"detail": "service temporarily unavailable"}, status_code=503)

    return app


app = create_app()
