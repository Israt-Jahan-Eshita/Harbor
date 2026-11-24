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
from app.core.reminders import GENERIC_REMINDER_TEXT_BN
from app.models import Alert, PushSubscription

logger = logging.getLogger("harbor.notifications")

GENERIC_PATIENT_PUSH_TEXT = GENERIC_REMINDER_TEXT_BN


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


def build_clinician_review_email_body(
    doctor_name: str,
    household_name: str,
    member_name: str,
    review_url: str,
    request_note: str | None = None,
    custom_email_body: str | None = None,
) -> str:
    """Build either the family's manual email body (with portal URL ensured) or an auto-generated email."""
    custom = (custom_email_body or "").strip()
    if custom:
        if review_url in custom:
            return custom
        return f"{custom}\n\nSecure Review Portal Link:\n{review_url}"

    note_block = f"Family Question / Note:\n{request_note.strip()}\n\n" if (request_note or "").strip() else ""
    return (
        f"Dear {doctor_name},\n\n"
        f"The family '{household_name}' is requesting a care-plan and dietary safety review for "
        f"{member_name} on Harbor.\n\n"
        f"{note_block}"
        "On the portal link below, you can:\n"
        "1. Review the patient's 30-day medical conditions, active drug classes, dose adherence, and recent meals.\n"
        "2. Set your consultation fee (or waive it to 0 BDT), which will immediately appear on the family's portal for payment.\n"
        "3. Submit your formal dietary preset verification and clinical recommendation once ready.\n\n"
        f"Secure Review Portal Link:\n{review_url}\n\n"
        "Warm regards,\n"
        f"{household_name} via Harbor Family Care"
    )


def send_clinician_review_email(
    recipient_email: str,
    household_name: str,
    member_name: str,
    email_body: str,
) -> str:
    """Attempt SMTP delivery for a clinician care-plan review link; report honest delivery status."""
    settings = get_settings()
    if not settings.smtp_host or not recipient_email.strip():
        return "link_ready"
    try:
        msg = EmailMessage()
        msg["Subject"] = f"Harbor Care Plan Review Request — {member_name} ({household_name})"
        msg["From"] = settings.email_from or "harbor@example.com"
        msg["To"] = recipient_email.strip()
        msg.set_content(email_body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_user and settings.smtp_password:
                smtp.starttls()
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        return "sent"
    except Exception as exc:
        logger.warning("Clinician review SMTP delivery failed: %s", exc)
        return "failed"
