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
    application = FastAPI(
        title="Harbor: Family Care Manager API",
        version="0.1.0",
        description="Deterministic food-safety & shared-pot family care engine with bounded AI extraction/explanation.",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    register_exception_handlers(application)

    @application.get("/healthz", tags=["system"])
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
