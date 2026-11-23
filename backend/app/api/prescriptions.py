"""Prescription image upload -> draft extraction -> caregiver confirmation gate (B13)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.reminders import build_dose_schedule
from app.core.types import MedicineData
from app.db import get_db
from app.deps import (
    compute_payload_digest,
    enforce_rate_limit,
    get_current_household,
    sign_confirmation_token,
)
from app.errors import AppError
from app.llm.client import LLMClient
from app.llm.extract_prescription import extract_prescription_draft
from app.models import DoseSchedule, Household, Medicine, Member, Prescription
from app.schemas import PrescriptionConfirmRequest
from app.services.context_loader import load_drug_class_map

router = APIRouter(tags=["prescriptions"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB

DRUG_CLASS_CATALOG = [
    {
        "value": "ace_inhibitor",
        "label_bn": "ACE ইনহিবিটর (যেমন: Enalapril, Lisinopril, Ramipril)",
        "label_en": "ACE Inhibitor (e.g., Enalapril, Lisinopril, Ramipril)",
    },
    {
        "value": "arb",
        "label_bn": "ARB (যেমন: Losartan, Telmisartan, Valsartan)",
        "label_en": "ARB (e.g., Losartan, Telmisartan, Valsartan)",
    },
    {
        "value": "k_sparing_diuretic",
        "label_bn": "পটাশিয়াম-স্পেয়ারিং ডাইইউরেটিক (যেমন: Spironolactone)",
        "label_en": "Potassium-Sparing Diuretic (e.g., Spironolactone)",
    },
    {
        "value": "statin_cyp3a4",
        "label_bn": "CYP3A4 স্ট্যাটিন (যেমন: Atorvastatin, Simvastatin)",
        "label_en": "CYP3A4 Statin (e.g., Atorvastatin, Simvastatin)",
    },
    {
        "value": "none_modelled",
        "label_bn": "মডেল করা নেই (হারবারের নিয়ম-টেবিলে খাবারের সংঘাত নেই)",
        "label_en": "Not modelled (no food interaction in Harbor's rule table)",
    },
]


def get_llm_client() -> LLMClient:
    return LLMClient()


@router.get("/drug-classes")
def list_drug_classes():
    return {
        "drug_classes": DRUG_CLASS_CATALOG,
        "note_bn": "হারবার শুধুমাত্র তার নিয়ম-টেবিলে মডেল করা ওষুধ-খাবারের সংঘাত যাচাই করতে পারে।",
        "note_en": "Harbor can only check food interactions modelled in its rule table.",
    }


async def _read_upload_limited(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise AppError(
                "PAYLOAD_TOO_LARGE",
                "Prescription image exceeds 10 MB limit.",
                status_code=413,
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/members/{member_id}/prescription",
    dependencies=[Depends(enforce_rate_limit("prescription_extract", max_calls=15, window_seconds=60))],
)
async def upload_prescription_draft(
    member_id: uuid.UUID,
    file: UploadFile = File(...),
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
):
    if not hh.consent_given:
        raise AppError(
            "CONSENT_REQUIRED",
            "Caregiver consent is required before sending prescription images to third-party AI APIs.",
            status_code=403,
        )

    member = db.scalar(
        select(Member).where(Member.id == member_id, Member.household_id == hh.id)
    )
    if member is None:
        raise AppError("MEMBER_NOT_FOUND", "Member not found in household.", status_code=404)

    content_type = (file.content_type or "image/jpeg").lower()
    if not content_type.startswith("image/"):
        raise AppError("INVALID_FILE_TYPE", "Only image files are accepted.", status_code=400)

    image_bytes = await _read_upload_limited(file, MAX_IMAGE_BYTES)
    if not image_bytes:
        raise AppError(
            "INVALID_IMAGE_SIZE",
            "Prescription image must be non-empty and under 10 MB.",
            status_code=400,
        )

    drug_map = load_drug_class_map(db)
    try:
        draft = extract_prescription_draft(
            image_bytes=image_bytes,
            mime_type=content_type,
            llm_client=llm_client,
            drug_class_map=drug_map,
            db=db,
        )
    finally:
        # Guardrail #10: never persist prescription images
        del image_bytes

    rx = Prescription(
        member_id=member.id,
        raw_extraction=draft,
        status="draft",
    )
    db.add(rx)
    db.commit()
    db.refresh(rx)

    confirmation_token = sign_confirmation_token(
        str(hh.id),
        "prescription_confirm",
        compute_payload_digest({"prescription_id": str(rx.id)}),
    )

    return {
        "prescription_id": str(rx.id),
        "member_id": str(member.id),
        "status": rx.status,
        "image_stored": False,
        "confirmation_token": confirmation_token,
        "medicines": draft["medicines"],
        "diet_notes": draft["diet_notes"],
        "overall_confidence": draft["overall_confidence"],
        "extraction_failed": draft["extraction_failed"],
        "scope_note_bn": "নিশ্চিত করার আগে প্রতিটি ওষুধের নাম ও শ্রেণি পরীক্ষা করুন। কোনো ডোজ সংরক্ষণ করা হয় না।",
        "scope_note_en": "Review every medicine name and drug class before confirming. Doses are never saved.",
    }


@router.post("/prescriptions/{prescription_id}/confirm")
def confirm_prescription(
    prescription_id: uuid.UUID,
    payload: PrescriptionConfirmRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    rx = db.scalar(select(Prescription).where(Prescription.id == prescription_id))
    if rx is None:
        raise AppError("PRESCRIPTION_NOT_FOUND", "Prescription draft not found.", status_code=404)

    member = db.scalar(
        select(Member).where(Member.id == rx.member_id, Member.household_id == hh.id)
    )
    if member is None:
        raise AppError("FORBIDDEN", "Prescription does not belong to your household.", status_code=403)

    confirmed_rows = [r for r in payload.rows if r.confirmed]
    if not confirmed_rows:
        raise AppError(
            "NO_ROWS_CONFIRMED",
            "Tick at least one medicine row to confirm.",
            status_code=400,
        )

    settings = get_settings()
    today = datetime.now(ZoneInfo(settings.tz)).date()
    created_meds: list[dict] = []
    scheduled_count = 0

    for row in confirmed_rows:
        med = Medicine(
            member_id=member.id,
            prescription_id=rx.id,
            name_as_written=row.name_as_written.strip(),
            generic_name=row.generic_name.strip() if row.generic_name else None,
            drug_class=row.drug_class,
            timing=row.timing,
            meal_slots=row.meal_slots,
            verified_by_caregiver=True,
            active=True,
        )
        db.add(med)
        db.flush()

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
        doses = build_dose_schedule(
            medicine=med_data,
            member_id=str(member.id),
            member_name=member.name,
            meal_times=hh.meal_times,
            for_date=today,
            offsets_min=settings.reminder_offsets,
            grace_minutes=settings.reminder_grace_minutes,
            tz_name=settings.tz,
        )
        for rec in doses:
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
                scheduled_count += 1

        created_meds.append(
            {
                "id": str(med.id),
                "name_as_written": med.name_as_written,
                "drug_class": med.drug_class,
                "timing": med.timing,
                "meal_slots": med.meal_slots,
                "verified_by_caregiver": med.verified_by_caregiver,
            }
        )

    rx.status = "confirmed"
    rx.confirmed_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "prescription_id": str(rx.id),
        "status": rx.status,
        "confirmed_medicines": created_meds,
        "scheduled_doses_count": scheduled_count,
    }
