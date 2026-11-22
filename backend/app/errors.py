"""Standardized JSON error responses for the Harbor API."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("harbor.errors")


class AppError(Exception):
    """Domain or application error serialized to {code, message, details}."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def _error_payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": details or {},
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Attach JSON error handlers without leaking internal stack traces."""

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(_request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            payload = _error_payload(
                str(detail["code"]),
                str(detail["message"]),
                detail.get("details") if isinstance(detail.get("details"), dict) else {},
            )
        else:
            payload = _error_payload(f"HTTP_{exc.status_code}", str(detail))
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                "VALIDATION_ERROR",
                "Request validation failed.",
                {"errors": exc.errors()},
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        logger.exception("Unhandled error request_id=%s", req_id, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                "INTERNAL_ERROR",
                "An unexpected internal error occurred.",
                {"request_id": req_id} if req_id else {},
            ),
        )
