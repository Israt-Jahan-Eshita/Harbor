"""Web Push subscription registration endpoint (B17)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_household
from app.models import Household, PushSubscription
from app.schemas import PushSubscribeRequest

router = APIRouter(prefix="/push", tags=["push"])


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
