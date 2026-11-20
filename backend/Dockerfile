# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

# Non-root user with a fixed UID so Kubernetes runAsNonRoot can verify it.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin agentos
USER 10001

EXPOSE 8000

# Production defaults; override with environment variables.
ENV APP_ENV=production \
    AUTO_CREATE_TABLES=false \
    LOG_JSON=true \
    WEB_CONCURRENCY=2

# Scale out with more pods rather than more workers per pod.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY} --proxy-headers --forwarded-allow-ips='*' --no-access-log --timeout-graceful-shutdown 60"]
