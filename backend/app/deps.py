"""Authentication, confirmation-gate tokens, tick secret verification, and rate limiting."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from collections import defaultdict, deque
from typing import Any

import bcrypt
from fastapi import Depends, Header, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import AppError
from app.models import Household

_RATE_WINDOWS: dict[str, deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    """Clear in-memory rate-limit counters (used by tests)."""
    _RATE_WINDOWS.clear()


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_pin(pin: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _session_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt="harbor-session")


def _confirm_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt="harbor-confirm")


def sign_session_token(household_id: uuid.UUID | str) -> str:
    return _session_serializer().dumps({"household_id": str(household_id)})


def verify_session_token(token: str, max_age_seconds: int = 86400 * 7) -> uuid.UUID:
    try:
        data = _session_serializer().loads(token, max_age=max_age_seconds)
        return uuid.UUID(str(data["household_id"]))
    except (BadSignature, SignatureExpired, KeyError, ValueError) as exc:
        raise AppError("UNAUTHORIZED", "Invalid or expired session token.", status_code=401) from exc


def compute_payload_digest(payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:24]


def sign_confirmation_token(household_id: uuid.UUID | str, kind: str, digest: str) -> str:
    return _confirm_serializer().dumps(
        {"household_id": str(household_id), "kind": kind, "digest": digest}
    )


def verify_confirmation_token(
    token: str,
    household_id: uuid.UUID | str,
    kind: str,
    max_age_seconds: int = 3600,
) -> dict[str, str]:
    if not token or not token.strip():
        raise AppError(
            "CONFIRMATION_REQUIRED",
            "Caregiver confirmation token is required.",
            status_code=400,
        )
    try:
        data = _confirm_serializer().loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired) as exc:
        raise AppError(
            "INVALID_CONFIRMATION_TOKEN",
            "Caregiver confirmation token is invalid or expired.",
            status_code=400,
        ) from exc
    if data.get("household_id") != str(household_id) or data.get("kind") != kind:
        raise AppError(
            "INVALID_CONFIRMATION_TOKEN",
            "Confirmation token does not match household or action.",
            status_code=403,
        )
    return data


def get_current_household(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Household:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError("UNAUTHORIZED", "Missing Bearer session token.", status_code=401)
    token = authorization.split(" ", 1)[1].strip()
    hh_id = verify_session_token(token)
    hh = db.scalar(select(Household).where(Household.id == hh_id))
    if hh is None:
        raise AppError("UNAUTHORIZED", "Household session not found.", status_code=401)
    return hh


def verify_tick_secret(x_tick_secret: str | None = Header(default=None, alias="X-Tick-Secret")) -> None:
    expected = get_settings().tick_secret
    if not x_tick_secret or not hmac.compare_digest(x_tick_secret, expected):
        raise AppError("INVALID_TICK_SECRET", "Invalid X-Tick-Secret header.", status_code=401)


def enforce_rate_limit(bucket: str, max_calls: int = 30, window_seconds: int = 60):
    """FastAPI dependency enforcing sliding-window rate limits with stale-key pruning."""

    def _dependency(request: Request) -> None:
        client_host = request.client.host if request.client else "unknown"
        auth = request.headers.get("authorization", "")[-16:]
        key = f"{bucket}:{client_host}:{auth}"
        now = time.monotonic()

        if len(_RATE_WINDOWS) > 5000:
            stale_keys = [k for k, v in _RATE_WINDOWS.items() if not v or now - v[-1] > 3600]
            for sk in stale_keys:
                _RATE_WINDOWS.pop(sk, None)

        dq = _RATE_WINDOWS[key]
        while dq and now - dq[0] > window_seconds:
            dq.popleft()
        if not dq:
            _RATE_WINDOWS.pop(key, None)
            dq = _RATE_WINDOWS[key]
        if len(dq) >= max_calls:
            raise AppError(
                "RATE_LIMITED",
                "Too many requests; please wait a moment and try again.",
                status_code=429,
            )
        dq.append(now)

    return _dependency
