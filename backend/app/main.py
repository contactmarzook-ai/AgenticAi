import logging
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import models  # noqa: F401  (register tables)
from .bootstrap import seed
from .config import settings
from .database import Base, SessionLocal, engine
from .logging_config import configure_logging
from .routers import (
    admin,
    agents,
    auth,
    chat,
    credentials,
    llm_models,
    nodes,
    runs,
    tools,
    triggers,
    users,
    workflows,
)
from .routers import (
    settings as settings_router,
)

logger = logging.getLogger("agentos.http")
_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def create_app() -> FastAPI:
    settings.validate()
    configure_logging(settings.log_level, settings.log_json)
    if settings.is_production and not settings.cookie_secure:
        logger.warning("COOKIE_SECURE is false: session cookies can travel over plain HTTP. Use only for trials.")

    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()

    if settings.run_worker_enabled:
        # Pick up queued runs and resume runs interrupted by a restart (no-op when polling is off).
        from .services.runs import worker

        worker.start_polling()

    app = FastAPI(
        title="Star Dust",
        version="1.0.0",
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Webhook-Token", "X-Form-Token", "X-Request-ID"],
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        supplied = request.headers.get("x-request-id", "")
        # Only accept short, plain ids from clients (they end up in logs and audit rows).
        request_id = supplied if _REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        started = time.monotonic()
        length = request.headers.get("content-length")
        try:
            if length is not None and (not length.isdigit() or int(length) > settings.max_request_bytes):
                response = JSONResponse({"detail": "Request body too large"}, status_code=413)
            else:
                response = await call_next(request)
        except Exception:
            logger.exception("Unhandled error", extra={"request_id": request_id, "path": request.url.path})
            response = JSONResponse({"detail": "Internal server error", "request_id": request_id}, status_code=500)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        if not request.url.path.startswith("/api/docs"):
            # The API only returns JSON: nothing in a response may load or run anything.
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path not in ("/healthz", "/readyz"):
            logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "user_id": getattr(request.state, "user_id", None),
                },
            )
        return response

    for module in (
        auth,
        users,
        llm_models,
        tools,
        agents,
        workflows,
        runs,
        triggers,
        chat,
        admin,
        nodes,
        credentials,
        settings_router,
    ):
        app.include_router(module.router)
    app.include_router(triggers.hooks)
    app.include_router(triggers.public)
    app.include_router(workflows.templates_router)
    app.include_router(users.orgs_router)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    def readyz():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ok"}

    return app


app = create_app()
