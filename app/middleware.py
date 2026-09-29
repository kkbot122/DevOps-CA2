import asyncio
import logging
import random
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("shortly.access")


class RequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        duration = round((time.perf_counter() - started) * 1000, 3)
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault(
            "Cache-Control", "no-store"
        ) if request.url.path != "/" else None
        client_ip = request.client.host if request.client else "unknown"
        config = request.app.state.settings
        if config.trust_xff and request.headers.get("x-forwarded-for"):
            client_ip = request.headers["x-forwarded-for"].split(",", 1)[0].strip()
        status = response.status_code
        logger.log(
            logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO,
            "request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "duration_ms": duration,
                "client_ip": client_ip,
                "request_id": request_id,
                "version": config.app_version,
                "hostname": request.app.state.hostname,
            },
        )
        return response


class ChaosMiddleware(BaseHTTPMiddleware):
    EXCLUDED = ("/healthz", "/readyz", "/metrics", "/admin", "/static")

    async def dispatch(self, request, call_next):
        path = request.url.path
        if any(path == prefix or path.startswith(prefix + "/") for prefix in self.EXCLUDED):
            return await call_next(request)
        now = time.monotonic()
        cache = request.app.state.chaos_cache
        config = {"latency_ms": cache["latency_ms"], "error_pct": cache["error_pct"]}
        if now - cache["loaded_at"] >= 1:
            try:
                config = await request.app.state.store.get_chaos()
                cache.update(config, loaded_at=now)
            except Exception:
                config = {"latency_ms": 0, "error_pct": 0}
        if config["latency_ms"]:
            await asyncio.sleep(config["latency_ms"] / 1000)
        if config["error_pct"] and random.randrange(100) < config["error_pct"]:
            return JSONResponse({"detail": "chaos injected failure"}, status_code=500)
        return await call_next(request)


class BadReleaseMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        settings = request.app.state.settings
        applies = request.method == "POST" and request.url.path == "/api/shorten"
        applies |= (
            request.method == "GET"
            and request.url.path not in {"/", "/healthz", "/readyz", "/version", "/metrics"}
            and not request.url.path.startswith("/")
        )
        # Redirect paths are single-segment paths. API routes and health endpoints are excluded.
        segments = request.url.path.strip("/").split("/")
        applies = applies or (
            request.method == "GET"
            and len(segments) == 1
            and bool(segments[0])
            and segments[0] not in {"healthz", "readyz", "version", "metrics", "docs", "redoc"}
        )
        if (
            settings.bad_release_mode == "errors"
            and applies
            and random.randrange(100) < settings.bad_release_error_pct
        ):
            return JSONResponse({"detail": "bad release injected failure"}, status_code=500)
        return await call_next(request)
