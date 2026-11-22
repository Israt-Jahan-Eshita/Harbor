"""Patient reminder polling and one-tap confirmation endpoints (B17)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.reminders import GENERIC_REMINDER_TEXT_BN, mark_dose_taken
from app.core.types import DoseRecord
from app.db import get_db
from app.errors import AppError
from app.models import DoseSchedule, Medicine, Member

router = APIRouter(prefix="/reminders", tags=["reminders"])


def _require_patient_member(db: Session, token: str) -> Member:
    member = db.scalar(select(Member).where(Member.patient_token == token))
    if member is None:
        raise AppError("INVALID_PATIENT_TOKEN", "Invalid patient token.", status_code=401)
    return member


@router.get("/due")
def get_due_reminders(
    token: str = Query(..., min_length=4),
    now: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Patient polling endpoint (15s fallback). Strictly disease-free and scoped to one patient."""
    member = _require_patient_member(db, token)
    tz = ZoneInfo(get_settings().tz)
    current_now = now.astimezone(tz) if (now and now.tzinfo) else (now.replace(tzinfo=tz) if now else datetime.now(tz))
    day_start = current_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    rows = db.scalars(
        select(DoseSchedule)
        .join(Medicine)
        .where(
            Medicine.member_id == member.id,
            Medicine.verified_by_caregiver.is_(True),
            Medicine.active.is_(True),
            DoseSchedule.due_at >= day_start,
            DoseSchedule.due_at < day_end,
        )
        .order_by(DoseSchedule.due_at)
    ).all()

    due_doses = []
    upcoming_doses = []
    taken_count = 0

    for d in rows:
        if d.status in ("taken", "taken_late"):
            taken_count += 1
            continue
        item = {
            "dose_id": str(d.id),
            "due_at": d.due_at.astimezone(tz).isoformat(),
            "window_end": d.window_end.astimezone(tz).isoformat(),
            "status": d.status,
            "prompt_bn": GENERIC_REMINDER_TEXT_BN,
            "prompt_en": "Time for medicine",
        }
        if d.due_at <= current_now:
            due_doses.append(item)
        else:
            upcoming_doses.append(item)

    return {
        "member_name": member.name,
        "now": current_now.isoformat(),
        "has_due_dose": len(due_doses) > 0,
        "due_doses": due_doses,
        "upcoming_doses": upcoming_doses,
        "taken_today_count": taken_count,
    }


@router.post("/{dose_id}/taken")
def confirm_dose_taken(
    dose_id: uuid.UUID,
    token: str = Query(..., min_length=4),
    now: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Mark one dose taken/taken_late idempotently, strictly scoped to patient_token."""
    member = _require_patient_member(db, token)
    dose = db.scalar(
        select(DoseSchedule)
        .join(Medicine)
        .where(DoseSchedule.id == dose_id, Medicine.member_id == member.id)
    )
    if dose is None:
        raise AppError("DOSE_NOT_FOUND", "Dose not found for this patient.", status_code=404)

    tz = ZoneInfo(get_settings().tz)
    current_now = now.astimezone(tz) if (now and now.tzinfo) else (now.replace(tzinfo=tz) if now else datetime.now(tz))

    dose_rec = DoseRecord(
        id=str(dose.id),
        medicine_id=str(dose.medicine_id),
        member_id=str(member.id),
        member_name=member.name,
        due_at=dose.due_at,
        window_end=dose.window_end,
        status=dose.status,  # type: ignore[arg-type]
        confirmed_at=dose.confirmed_at,
    )
    updated = mark_dose_taken(dose_rec, current_now)
    dose.status = updated.status
    dose.confirmed_at = updated.confirmed_at
    db.commit()

    return {
        "dose_id": str(dose.id),
        "status": dose.status,
        "confirmed_at": dose.confirmed_at.isoformat() if dose.confirmed_at else None,
    }
