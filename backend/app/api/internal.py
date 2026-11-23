"""Idempotent scheduler tick endpoint (`POST /internal/tick`) with demo `now` override (B17)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.reminders import build_dose_schedule, evaluate_tick
from app.core.types import DoseRecord, MedicineData
from app.db import get_db
from app.deps import verify_tick_secret
from app.errors import AppError
from app.models import Alert, DoseSchedule, Household, LLMCall, Medicine, Member
from app.services.notifications import record_and_dispatch_alert

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/tick", dependencies=[Depends(verify_tick_secret)])
def run_internal_tick(
    now: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Run idempotent scheduled jobs across all households.

    Supports `?now=YYYY-MM-DDTHH:MM:SS+06:00` override when non-prod or explicitly permitted.
    """
    settings = get_settings()
    if now is not None and settings.env == "prod" and not settings.allow_demo_tick_override:
        raise AppError(
            "TICK_OVERRIDE_FORBIDDEN",
            "Time override is disabled in production.",
            status_code=403,
        )
    tz = ZoneInfo(settings.tz)
    current_now = (
        now.astimezone(tz)
        if (now and now.tzinfo)
        else (now.replace(tzinfo=tz) if now else datetime.now(tz))
    )
    target_date = current_now.date()
    schedule_dates = [target_date, target_date + timedelta(days=1)]

    # 1. Idempotently ensure DoseSchedule rows exist for today + tomorrow (handles midnight crossovers)
    med_rows = db.execute(
        select(Medicine, Member, Household)
        .join(Member, Medicine.member_id == Member.id)
        .join(Household, Member.household_id == Household.id)
        .where(Medicine.verified_by_caregiver.is_(True), Medicine.active.is_(True))
    ).all()

    created_schedules = 0
    for med, member, hh in med_rows:
        med_data = MedicineData(
            id=str(med.id),
            name_as_written=med.name_as_written,
            generic_name=med.generic_name,
            drug_class=med.drug_class,
            timing=med.timing,
            meal_slots=list(med.meal_slots or []),
            verified_by_caregiver=True,
            active=True,
        )
        for sched_date in schedule_dates:
            recs = build_dose_schedule(
                medicine=med_data,
                member_id=str(member.id),
                member_name=member.name,
                meal_times=hh.meal_times,
                for_date=sched_date,
                offsets_min=settings.reminder_offsets,
                grace_minutes=settings.reminder_grace_minutes,
                tz_name=settings.tz,
            )
            for rec in recs:
                exists = db.scalar(
                    select(DoseSchedule).where(
                        DoseSchedule.medicine_id == med.id,
                        DoseSchedule.due_at == rec.due_at,
                    )
                )
                if exists is None:
                    db.add(
                        DoseSchedule(
                            medicine_id=med.id,
                            due_at=rec.due_at,
                            window_end=rec.window_end,
                            status="pending",
                        )
                    )
                    created_schedules += 1
    db.flush()

    # 2. Load pending/missed doses and bounded recent alert keys for idempotency
    alert_cutoff = current_now - timedelta(days=35)
    existing_alerts = db.scalars(select(Alert).where(Alert.sent_at >= alert_cutoff)).all()
    existing_keys = {
        str(a.payload.get("alert_key"))
        for a in existing_alerts
        if isinstance(a.payload, dict) and a.payload.get("alert_key")
    }

    dose_tuples = db.execute(
        select(DoseSchedule, Medicine, Member)
        .join(Medicine, DoseSchedule.medicine_id == Medicine.id)
        .join(Member, Medicine.member_id == Member.id)
        .where(DoseSchedule.status.in_(["pending", "missed"]))
    ).all()

    dose_records: list[DoseRecord] = []
    dose_meta: dict[str, tuple[DoseSchedule, Member]] = {}
    for dose, _med, member in dose_tuples:
        did = str(dose.id)
        dose_records.append(
            DoseRecord(
                id=did,
                medicine_id=str(dose.medicine_id),
                member_id=str(member.id),
                member_name=member.name,
                due_at=dose.due_at,
                window_end=dose.window_end,
                status=dose.status,  # type: ignore[arg-type]
                confirmed_at=dose.confirmed_at,
            )
        )
        dose_meta[did] = (dose, member)

    tick_out = evaluate_tick(dose_records, now=current_now, existing_alert_keys=existing_keys)

    for updated_rec in tick_out["doses"]:
        orm_dose, _ = dose_meta[updated_rec.id]
        if orm_dose.status != updated_rec.status:
            orm_dose.status = updated_rec.status

    due_sent = 0
    for notif in tick_out["patient_notifications"]:
        _, member = dose_meta[notif["dose_id"]]
        record_and_dispatch_alert(
            db=db,
            household_id=member.household_id,
            member_id=member.id,
            kind="dose_due",
            payload=notif,
        )
        due_sent += 1

    esc_sent = 0
    for esc in tick_out["caregiver_escalations"]:
        _, member = dose_meta[esc["dose_id"]]
        caregiver = db.scalar(
            select(Member).where(
                Member.household_id == member.household_id,
                Member.role == "caregiver",
            )
        )
        email = caregiver.notify_email if caregiver else None
        record_and_dispatch_alert(
            db=db,
            household_id=member.household_id,
            member_id=member.id,
            kind="dose_missed_escalated",
            payload=esc,
            recipient_email=email,
        )
        esc_sent += 1

    # 3. Day-1 monthly bazar reminder prompt (idempotent per household/month)
    bazar_prompts = 0
    if current_now.day == 1:
        month_str = current_now.strftime("%Y-%m")
        for hh in db.scalars(select(Household)).all():
            bkey = f"bazar_prompt:{hh.id}:{month_str}"
            if bkey not in existing_keys:
                record_and_dispatch_alert(
                    db=db,
                    household_id=hh.id,
                    member_id=None,
                    kind="monthly_bazar_prompt",
                    payload={
                        "alert_key": bkey,
                        "month": month_str,
                        "text_bn": "মাসের শুরু হয়েছে—আপনার ভান্ডার যাচাই করে মাসিক বাজারের বাজেট দিন।",
                        "text_en": "New month started — review your pantry and enter your monthly bazar budget.",
                    },
                )
                bazar_prompts += 1

    # 4. Prune aged LLM audit logs (>30 days)
    db.execute(delete(LLMCall).where(LLMCall.created_at < current_now - timedelta(days=30)))

    db.commit()
    return {
        "now": current_now.isoformat(),
        "created_schedules": created_schedules,
        "patient_notifications_sent": due_sent,
        "caregiver_escalations_sent": esc_sent,
        "bazar_prompts_sent": bazar_prompts,
    }
