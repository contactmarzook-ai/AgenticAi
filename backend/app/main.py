import logging
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
    llm_models,
    runs,
    tools,
    triggers,
    users,
    workflows,
)

logger = logging.getLogger("agentos.http")


def create_app() -> FastAPI:
    settings.validate()
    configure_logging(settings.log_level, settings.log_json)

    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()

    app = FastAPI(
        title="AgentOS",
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
            allow_headers=["Authorization", "Content-Type", "X-Webhook-Token", "X-Request-ID"],
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled error", extra={"request_id": request_id, "path": request.url.path})
            response = JSONResponse({"detail": "Internal server error", "request_id": request_id}, status_code=500)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
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

    for module in (auth, users, llm_models, tools, agents, workflows, runs, triggers, chat, admin):
        app.include_router(module.router)
    app.include_router(triggers.hooks)

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
