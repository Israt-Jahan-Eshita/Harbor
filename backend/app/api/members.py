"""Member and confirmed-medicine CRUD endpoints (B12)."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.core.reminders import build_dose_schedule
from app.core.types import MedicineData
from app.db import get_db
from app.deps import get_current_household
from app.errors import AppError
from app.models import DoseSchedule, Household, Medicine, Member
from app.schemas import (
    MedicineCreateRequest,
    MedicineUpdateRequest,
    MemberCreateRequest,
    MemberUpdateRequest,
)

router = APIRouter(prefix="/members", tags=["members"])


def _serialize_member(m: Member) -> dict:
    return {
        "id": str(m.id),
        "household_id": str(m.household_id),
        "name": m.name,
        "role": m.role,
        "age_group": m.age_group,
        "conditions": list(m.conditions or []),
        "allergies": list(m.allergies or []),
        "diet_presets": list(m.diet_presets or []),
        "patient_token": m.patient_token,
        "notify_email": m.notify_email,
        "created_at": m.created_at.isoformat(),
        "medicines": [
            {
                "id": str(med.id),
                "name_as_written": med.name_as_written,
                "generic_name": med.generic_name,
                "drug_class": med.drug_class,
                "timing": med.timing,
                "meal_slots": list(med.meal_slots or []),
                "verified_by_caregiver": med.verified_by_caregiver,
                "active": med.active,
            }
            for med in m.medicines
        ],
    }


def _get_member_checked(db: Session, hh: Household, member_id: uuid.UUID) -> Member:
    member = db.scalar(
        select(Member)
        .options(selectinload(Member.medicines))
        .where(Member.id == member_id, Member.household_id == hh.id)
    )
    if member is None:
        raise AppError("MEMBER_NOT_FOUND", "Member not found in household.", status_code=404)
    return member


def _schedule_today_doses_for_medicine(db: Session, hh: Household, member: Member, med: Medicine) -> int:
    if not med.verified_by_caregiver or not med.active:
        return 0
    settings = get_settings()
    today = datetime.now(ZoneInfo(settings.tz)).date()
    med_data = MedicineData(
        id=str(med.id),
        name_as_written=med.name_as_written,
        generic_name=med.generic_name,
        drug_class=med.drug_class,
        timing=med.timing,
        meal_slots=list(med.meal_slots or []),
        verified_by_caregiver=med.verified_by_caregiver,
        active=med.active,
    )
    records = build_dose_schedule(
        medicine=med_data,
        member_id=str(member.id),
        member_name=member.name,
        meal_times=hh.meal_times,
        for_date=today,
        offsets_min=settings.reminder_offsets,
        grace_minutes=settings.reminder_grace_minutes,
        tz_name=settings.tz,
    )
    created = 0
    for rec in records:
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
            created += 1
    return created


@router.get("")
def list_members(hh: Household = Depends(get_current_household), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Member)
        .options(selectinload(Member.medicines))
        .where(Member.household_id == hh.id)
        .order_by(Member.created_at)
    ).all()
    return {"members": [_serialize_member(m) for m in rows]}


@router.post("", status_code=201)
def create_member(
    payload: MemberCreateRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    existing_count = len(
        db.scalars(select(Member.id).where(Member.household_id == hh.id)).all()
    )
    if existing_count >= 12:
        raise AppError("HOUSEHOLD_LIMIT", "Maximum 12 household members allowed.", status_code=400)

    member = Member(
        household_id=hh.id,
        name=payload.name.strip(),
        role=payload.role,
        age_group=payload.age_group,
        conditions=payload.conditions,
        allergies=payload.allergies,
        diet_presets=payload.diet_presets,
        patient_token=f"pt-{secrets.token_urlsafe(18)}",
        notify_email=payload.notify_email,
    )
    db.add(member)
    db.commit()
    member = _get_member_checked(db, hh, member.id)
    return _serialize_member(member)


@router.get("/{member_id}")
def get_member(
    member_id: uuid.UUID,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    member = _get_member_checked(db, hh, member_id)
    doses = db.scalars(
        select(DoseSchedule)
        .join(Medicine)
        .where(Medicine.member_id == member.id)
        .order_by(DoseSchedule.due_at.desc())
        .limit(25)
    ).all()
    data = _serialize_member(member)
    data["dose_history"] = [
        {
            "id": str(d.id),
            "medicine_id": str(d.medicine_id),
            "due_at": d.due_at.isoformat(),
            "window_end": d.window_end.isoformat(),
            "status": d.status,
            "confirmed_at": d.confirmed_at.isoformat() if d.confirmed_at else None,
        }
        for d in doses
    ]
    return data


@router.patch("/{member_id}")
def update_member(
    member_id: uuid.UUID,
    payload: MemberUpdateRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    member = _get_member_checked(db, hh, member_id)
    for field in ("name", "role", "age_group", "conditions", "allergies", "diet_presets", "notify_email"):
        val = getattr(payload, field)
        if val is not None:
            setattr(member, field, val.strip() if isinstance(val, str) else val)
    db.commit()
    member = _get_member_checked(db, hh, member.id)
    return _serialize_member(member)


@router.delete("/{member_id}")
def delete_member(
    member_id: uuid.UUID,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    member = _get_member_checked(db, hh, member_id)
    db.delete(member)
    db.commit()
    return {"deleted": True, "member_id": str(member_id)}


@router.post("/{member_id}/medicines", status_code=201)
def add_member_medicine(
    member_id: uuid.UUID,
    payload: MedicineCreateRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    member = _get_member_checked(db, hh, member_id)
    med = Medicine(
        member_id=member.id,
        name_as_written=payload.name_as_written.strip(),
        generic_name=payload.generic_name.strip() if payload.generic_name else None,
        drug_class=payload.drug_class,
        timing=payload.timing,
        meal_slots=payload.meal_slots,
        verified_by_caregiver=payload.verified_by_caregiver,
        active=True,
    )
    db.add(med)
    db.flush()
    scheduled = _schedule_today_doses_for_medicine(db, hh, member, med)
    db.commit()
    db.refresh(med)
    return {
        "id": str(med.id),
        "name_as_written": med.name_as_written,
        "drug_class": med.drug_class,
        "timing": med.timing,
        "meal_slots": med.meal_slots,
        "verified_by_caregiver": med.verified_by_caregiver,
        "active": med.active,
        "scheduled_doses": scheduled,
    }


@router.patch("/{member_id}/medicines/{medicine_id}")
def update_member_medicine(
    member_id: uuid.UUID,
    medicine_id: uuid.UUID,
    payload: MedicineUpdateRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    member = _get_member_checked(db, hh, member_id)
    med = db.scalar(
        select(Medicine).where(Medicine.id == medicine_id, Medicine.member_id == member.id)
    )
    if med is None:
        raise AppError("MEDICINE_NOT_FOUND", "Medicine not found.", status_code=404)
    for field in ("drug_class", "timing", "meal_slots", "verified_by_caregiver", "active"):
        val = getattr(payload, field)
        if val is not None:
            setattr(med, field, val)
    db.flush()
    _schedule_today_doses_for_medicine(db, hh, member, med)
    db.commit()
    db.refresh(med)
    return {
        "id": str(med.id),
        "name_as_written": med.name_as_written,
        "drug_class": med.drug_class,
        "timing": med.timing,
        "meal_slots": med.meal_slots,
        "verified_by_caregiver": med.verified_by_caregiver,
        "active": med.active,
    }


@router.delete("/{member_id}/medicines/{medicine_id}")
def delete_member_medicine(
    member_id: uuid.UUID,
    medicine_id: uuid.UUID,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    member = _get_member_checked(db, hh, member_id)
    med = db.scalar(
        select(Medicine).where(Medicine.id == medicine_id, Medicine.member_id == member.id)
    )
    if med is None:
        raise AppError("MEDICINE_NOT_FOUND", "Medicine not found.", status_code=404)
    db.delete(med)
    db.commit()
    return {"deleted": True, "medicine_id": str(medicine_id)}
