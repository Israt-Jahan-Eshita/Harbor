"""Harbor FastAPI application entry point."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import (
    bazar,
    clinician,
    dashboard,
    engine as engine_api,
    eval as eval_api,
    events,
    households,
    internal,
    members,
    menu,
    prescriptions,
    push,
    reminders,
    stock,
)
from app.config import get_settings
from app.db import get_db
from app.errors import register_exception_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("harbor.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Validate runtime settings on startup."""
    settings = get_settings()
    logger.info("Harbor API starting in env=%s tz=%s", settings.env, settings.tz)
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    is_prod = settings.env == "prod"
    application = FastAPI(
        title="Harbor: Family Care Manager API",
        version="0.1.0",
        description="Deterministic food-safety & shared-pot family care engine with bounded AI extraction/explanation.",
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept-Language",
            "X-Tick-Secret",
            "X-Request-Id",
        ],
    )

    max_payload_bytes = 12 * 1024 * 1024  # 12 MB ceiling above 10 MB media limits

    @application.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id

        content_length_raw = request.headers.get("content-length")
        if content_length_raw:
            try:
                if int(content_length_raw) > max_payload_bytes:
                    resp = JSONResponse(
                        status_code=413,
                        content={
                            "code": "PAYLOAD_TOO_LARGE",
                            "message": "Request payload exceeds 12 MB limit.",
                            "details": {},
                        },
                    )
                    resp.headers["X-Request-Id"] = request_id
                    return resp
            except ValueError:
                pass

        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "microphone=(self), camera=(self)"
        return response

    register_exception_handlers(application)

    application.include_router(households.router)
    application.include_router(members.router)
    application.include_router(clinician.router)
    application.include_router(prescriptions.router)
    application.include_router(events.router)
    application.include_router(stock.router)
    application.include_router(menu.router)
    application.include_router(bazar.router)
    application.include_router(reminders.router)
    application.include_router(push.router)
    application.include_router(dashboard.router)
    application.include_router(internal.router)
    application.include_router(engine_api.router)
    application.include_router(eval_api.router)

    @application.api_route("/healthz", methods=["GET", "HEAD"], tags=["system"])
    def healthz(db: Session = Depends(get_db)):
        """Check API liveness and PostgreSQL database connectivity."""
        try:
            db.execute(text("SELECT 1"))
            return {"status": "ok", "db": "ok"}
        except Exception as exc:  # pragma: no cover - defensive runtime check
            logger.error("Health check DB failure: %s", exc)
            return JSONResponse(
                status_code=503,
                content={"code": "DB_UNAVAILABLE", "message": "Database check failed.", "details": {}},
            )

    return application


app = create_app()
