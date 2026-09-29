from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import metrics

router = APIRouter()


@router.get("/{code}")
async def redirect(code: str, request: Request):
    store = request.app.state.store
    record = await store.get(code)
    if record is None:
        raise HTTPException(status_code=404, detail="short link not found")
    if store.is_expired(record):
        raise HTTPException(status_code=410, detail="short link expired")
    await store.increment_clicks(code)
    metrics.redirects.inc()
    response = RedirectResponse(record["url"], status_code=302)
    response.headers["Cache-Control"] = "no-store"
    return response
