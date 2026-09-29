import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app import metrics
from app.schemas import RESERVED_CODES, LinkStats, RecentLink, ShortenRequest, ShortenResponse

router = APIRouter(prefix="/api")
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def make_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(6))


def short_url(request: Request, code: str) -> str:
    settings = request.app.state.settings
    if settings.base_url:
        base = settings.base_url.rstrip("/")
    else:
        proto = (
            request.headers.get("x-forwarded-proto", request.url.scheme).split(",", 1)[0].strip()
        )
        host = (
            request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
            .split(",", 1)[0]
            .strip()
        )
        base = f"{proto}://{host}" if host else str(request.base_url).rstrip("/")
    return f"{base}/{code}"


def is_blocked(request: Request, host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(
        host == domain or host.endswith("." + domain)
        for domain in request.app.state.settings.blocked_domain_set
    )


@router.post("/shorten", response_model=ShortenResponse, status_code=201)
async def shorten(body: ShortenRequest, request: Request):
    host = urlsplit(body.url).hostname or ""
    if is_blocked(request, host):
        metrics.blocked.inc()
        return JSONResponse({"detail": "domain is blocked"}, status_code=403)
    store = request.app.state.store
    now = request.app.state.clock()
    expires_at = (
        now + timedelta(seconds=body.expires_in_seconds)
        if body.expires_in_seconds is not None
        else None
    )
    if body.alias:
        if body.alias.lower() in RESERVED_CODES:
            raise HTTPException(status_code=409, detail="alias is reserved")
        if not await store.claim(body.alias, body.url, now, expires_at):
            raise HTTPException(status_code=409, detail="alias already taken")
        code = body.alias
    else:
        code = ""
        for _ in range(5):
            candidate = make_code()
            if await store.claim(candidate, body.url, now, expires_at):
                code = candidate
                break
        if not code:
            raise HTTPException(status_code=500, detail="could not allocate a short code")
    metrics.links_created.inc()
    return ShortenResponse(
        code=code,
        short_url=short_url(request, code),
        url=body.url,
        created_at=now,
        expires_at=expires_at,
    )


async def read_link(request: Request, code: str):
    record = await request.app.state.store.get(code)
    if record is None:
        raise HTTPException(status_code=404, detail="short link not found")
    if request.app.state.store.is_expired(record):
        raise HTTPException(status_code=410, detail="short link expired")
    return record


@router.get("/links/{code}/stats", response_model=LinkStats)
async def stats(code: str, request: Request):
    record = await read_link(request, code)
    return LinkStats(
        code=code,
        url=record["url"],
        short_url=short_url(request, code),
        clicks=int(record.get("clicks", 0)),
        created_at=record["created_at"],
        expires_at=record.get("expires_at"),
        expired=False,
    )


@router.get("/links/recent", response_model=list[RecentLink])
async def recent(request: Request, limit: int = Query(10, ge=1, le=20)):
    result = []
    for code in await request.app.state.store.recent_codes():
        record = await request.app.state.store.get(code)
        if not record or request.app.state.store.is_expired(record):
            continue
        result.append(
            RecentLink(
                code=code,
                short_url=short_url(request, code),
                url=record["url"],
                clicks=int(record.get("clicks", 0)),
                created_at=record["created_at"],
                expires_at=record.get("expires_at"),
            )
        )
        if len(result) >= limit:
            break
    return result
