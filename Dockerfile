FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime

ARG APP_VERSION=dev
ARG BAD_RELEASE_MODE=none

RUN case "$BAD_RELEASE_MODE" in none|crash|errors) ;; *) echo "BAD_RELEASE_MODE must be none, crash, or errors" >&2; exit 1 ;; esac \
    && groupadd --gid 10001 shortly \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin shortly

WORKDIR /srv
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_VERSION=${APP_VERSION} \
    BAD_RELEASE_MODE=${BAD_RELEASE_MODE}

LABEL org.opencontainers.image.version=${APP_VERSION} \
      org.opencontainers.image.source="https://github.com/kkbot122/DevOps-CA2"

COPY --from=builder /install /usr/local
COPY app/ /srv/app/

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]

CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--proxy-headers","--forwarded-allow-ips","*","--no-server-header"]
