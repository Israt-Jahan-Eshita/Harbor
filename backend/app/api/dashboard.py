"""Caregiver dose dashboard overview endpoint (B17)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_household
from app.models import Alert, DoseSchedule, Household, Medicine, Member

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/doses")
def get_caregiver_doses_dashboard(
    for_date: date | None = Query(default=None),
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    tz = ZoneInfo(get_settings().tz)
    target_date = for_date or datetime.now(tz).date()
    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=tz)
    day_end = day_start + timedelta(days=1)

    members = db.scalars(
        select(Member).where(Member.household_id == hh.id).order_by(Member.created_at)
    ).all()

    dose_rows = db.execute(
        select(DoseSchedule, Medicine, Member)
        .join(Medicine, DoseSchedule.medicine_id == Medicine.id)
        .join(Member, Medicine.member_id == Member.id)
        .where(
            Member.household_id == hh.id,
            DoseSchedule.due_at >= day_start,
            DoseSchedule.due_at < day_end,
        )
        .order_by(DoseSchedule.due_at)
    ).all()

    doses_by_member: dict[str, list[dict]] = {str(m.id): [] for m in members}
    summary = {"taken": 0, "taken_late": 0, "pending": 0, "missed": 0, "escalated": 0}

    for dose, med, member in dose_rows:
        summary[dose.status] = summary.get(dose.status, 0) + 1
        doses_by_member[str(member.id)].append(
            {
                "dose_id": str(dose.id),
                "medicine_id": str(med.id),
                "medicine_name": med.name_as_written,
                "timing": med.timing,
                "due_at": dose.due_at.astimezone(tz).isoformat(),
                "window_end": dose.window_end.astimezone(tz).isoformat(),
                "status": dose.status,
                "confirmed_at": dose.confirmed_at.astimezone(tz).isoformat() if dose.confirmed_at else None,
            }
        )

    alerts = db.scalars(
        select(Alert)
        .where(Alert.household_id == hh.id)
        .order_by(Alert.sent_at.desc())
        .limit(15)
    ).all()

    return {
        "for_date": target_date.isoformat(),
        "summary": summary,
        "patients": [
            {
                "member_id": str(m.id),
                "name": m.name,
                "role": m.role,
                "patient_token": m.patient_token,
                "doses": doses_by_member[str(m.id)],
            }
            for m in members
            if doses_by_member[str(m.id)] or m.role in ("patient", "elder")
        ],
        "alerts": [
            {
                "id": str(a.id),
                "kind": a.kind,
                "channel": a.channel,
                "sent_at": a.sent_at.astimezone(tz).isoformat(),
                "payload": a.payload,
            }
            for a in alerts
        ],
    }
