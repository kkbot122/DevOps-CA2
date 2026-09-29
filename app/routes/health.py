import asyncio
import socket

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import metrics

router = APIRouter()


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request):
    try:
        await asyncio.wait_for(request.app.state.redis.ping(), timeout=1)
    except Exception:
        metrics.redis_up.set(0)
        return JSONResponse({"status": "not ready", "reason": "redis unavailable"}, status_code=503)
    metrics.redis_up.set(1)
    return {"status": "ready"}


@router.get("/version")
async def version(request: Request):
    return {
        "version": request.app.state.settings.app_version,
        "hostname": request.app.state.hostname or socket.gethostname(),
    }
