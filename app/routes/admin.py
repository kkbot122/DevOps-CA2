from fastapi import APIRouter, Header, HTTPException, Request

from app.schemas import ChaosConfig

router = APIRouter(prefix="/admin")


def authorize(request: Request, token: str | None) -> None:
    if token != request.app.state.settings.admin_token:
        raise HTTPException(status_code=401, detail="unauthorized")


@router.get("/chaos")
async def get_chaos(request: Request, x_admin_token: str | None = Header(default=None)):
    authorize(request, x_admin_token)
    return await request.app.state.store.get_chaos()


@router.post("/chaos")
async def set_chaos(
    body: ChaosConfig, request: Request, x_admin_token: str | None = Header(default=None)
):
    authorize(request, x_admin_token)
    value = body.model_dump()
    await request.app.state.store.set_chaos(value)
    request.app.state.chaos_cache.update(value, loaded_at=0)
    return value


@router.delete("/chaos")
async def delete_chaos(request: Request, x_admin_token: str | None = Header(default=None)):
    authorize(request, x_admin_token)
    await request.app.state.store.reset_chaos()
    request.app.state.chaos_cache.update(latency_ms=0, error_pct=0, loaded_at=0)
    return {"latency_ms": 0, "error_pct": 0}
