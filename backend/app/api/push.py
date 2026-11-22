"""Web Push subscription registration endpoint (B17)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_household
from app.errors import AppError
from app.models import Household, Member, PushSubscription
from app.schemas import PushSubscribeRequest

router = APIRouter(prefix="/push", tags=["push"])


class PatientPushSubscribeRequest(BaseModel):
    endpoint: str = Field(..., min_length=1)
    p256dh: str = Field(..., min_length=1)
    auth: str = Field(..., min_length=1)


@router.get("/vapid-public-key")
def get_vapid_public_key():
    """Return configured VAPID public key for browser PushManager subscription."""
    settings = get_settings()
    return {
        "public_key": settings.vapid_public_key,
        "configured": bool(settings.vapid_public_key and settings.vapid_private_key),
    }


@router.post("/subscribe")
def subscribe_push(
    payload: PushSubscribeRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    member_uuid = uuid.UUID(payload.member_id) if payload.member_id else None
    existing = db.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    )
    if existing:
        existing.household_id = hh.id
        existing.member_id = member_uuid
        existing.p256dh = payload.p256dh
        existing.auth = payload.auth
    else:
        db.add(
            PushSubscription(
                household_id=hh.id,
                member_id=member_uuid,
                endpoint=payload.endpoint,
                p256dh=payload.p256dh,
                auth=payload.auth,
            )
        )
    db.commit()
    return {"subscribed": True}


@router.post("/subscribe-patient")
def subscribe_patient_push(
    payload: PatientPushSubscribeRequest,
    token: str = Query(..., min_length=4),
    db: Session = Depends(get_db),
):
    """Register browser Web Push subscription scoped strictly to a valid patient_token."""
    member = db.scalar(select(Member).where(Member.patient_token == token))
    if member is None:
        raise AppError("INVALID_PATIENT_TOKEN", "Invalid patient token.", status_code=401)

    existing = db.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    )
    if existing:
        existing.household_id = member.household_id
        existing.member_id = member.id
        existing.p256dh = payload.p256dh
        existing.auth = payload.auth
    else:
        db.add(
            PushSubscription(
                household_id=member.household_id,
                member_id=member.id,
                endpoint=payload.endpoint,
                p256dh=payload.p256dh,
                auth=payload.auth,
            )
        )
    db.commit()
    return {"subscribed": True}
