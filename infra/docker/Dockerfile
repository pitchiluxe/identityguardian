# IdentityGuardian AI — one image for the API, worker and operator commands (Phase 20).
# Pin base images by digest when promoting to a registry; tags are used for local builds.

FROM node:22.21-alpine AS web
WORKDIR /build
COPY package.json package-lock.json tsconfig.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY apps/web apps/web
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    LOG_FORMAT=json IG_SECRETS_DIR=/run/secrets
# PostgreSQL client tools for migrations and the backup drill.
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 guardian \
 && useradd --system --uid 10001 --gid guardian --no-create-home --shell /usr/sbin/nologin guardian
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-deps -r requirements.lock
COPY apps apps
COPY packages packages
COPY migrations migrations
COPY scripts scripts
COPY --from=web /build/apps/web/dist apps/web/dist
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).status != 200)"
# Proxy headers are trusted only from the reverse proxy network (FORWARDED_ALLOW_IPS).
CMD ["sh", "-c", "exec uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:?set to the proxy address}\""]
