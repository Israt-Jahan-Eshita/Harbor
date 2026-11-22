"""Generic notification delivery (Web Push, SMTP email fallback, and DB Alert logs)."""

from __future__ import annotations

import json
import logging
import smtplib
import uuid
from email.message import EmailMessage
from typing import Any

from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Alert, PushSubscription

logger = logging.getLogger("harbor.notifications")

GENERIC_PATIENT_PUSH_TEXT = "ওষুধের সময় হয়েছে"


def record_and_dispatch_alert(
    db: Session,
    household_id: uuid.UUID,
    member_id: uuid.UUID | None,
    kind: str,
    payload: dict[str, Any],
    recipient_email: str | None = None,
) -> Alert:
    """Persist an in-app Alert and attempt Web Push / SMTP delivery when configured.

    Patient lock-screen push text is strictly generic ('ওষুধের সময় হয়েছে') with zero
    disease or medicine names.
    """
    settings = get_settings()
    channel = "in_app"

    # Web Push attempt
    if settings.vapid_private_key and settings.vapid_public_key:
        stmt = select(PushSubscription).where(PushSubscription.household_id == household_id)
        if member_id is not None and kind == "dose_due":
            stmt = stmt.where(
                (PushSubscription.member_id == member_id) | (PushSubscription.member_id.is_(None))
            )
        subs = db.scalars(stmt).all()
        push_text = (
            GENERIC_PATIENT_PUSH_TEXT
            if kind == "dose_due"
            else str(payload.get("text") or GENERIC_PATIENT_PUSH_TEXT)
        )
        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=json.dumps({"title": "Harbor", "body": push_text}, ensure_ascii=False),
                    vapid_private_key=settings.vapid_private_key,
                    vapid_claims={"sub": settings.vapid_subject},
                )
                channel = "web_push"
            except WebPushException as exc:
                logger.warning("WebPush failed for sub=%s: %s", sub.id, exc)
            except Exception as exc:  # pragma: no cover
                logger.warning("Unexpected push error: %s", exc)

    # SMTP fallback for caregiver escalations if configured
    if kind == "dose_missed_escalated" and recipient_email and settings.smtp_host:
        try:
            msg = EmailMessage()
            msg["Subject"] = "Harbor Alert — Dose Confirmation Pending"
            msg["From"] = settings.email_from or "harbor@example.com"
            msg["To"] = recipient_email
            msg.set_content(str(payload.get("text") or "A scheduled dose has not been confirmed."))
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                if settings.smtp_user and settings.smtp_password:
                    smtp.starttls()
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
            channel = "email" if channel == "in_app" else f"{channel}+email"
        except Exception as exc:
            logger.warning("SMTP alert delivery failed: %s", exc)

    alert = Alert(
        household_id=household_id,
        member_id=member_id,
        kind=kind,
        channel=channel,
        payload=payload,
    )
    db.add(alert)
    db.flush()
    return alert
