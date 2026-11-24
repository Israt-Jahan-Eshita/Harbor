"""On-demand clinician care-plan escalation, fee payments, and token-gated approval portal."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_household
from app.errors import AppError
from app.models import (
    Alert,
    ClinicianReview,
    DietPreset,
    DoseSchedule,
    Household,
    Medicine,
    Member,
    MenuSuggestion,
)
from app.schemas import (
    ClinicianDecisionRequest,
    ClinicianPaymentRequest,
    ClinicianReviewCreateRequest,
)
from app.services.notifications import send_clinician_review_email

router = APIRouter(prefix="/clinician", tags=["clinician"])


def _serialize_review(review: ClinicianReview, member_name: str | None = None) -> dict:
    resolved_name = member_name
    if resolved_name is None and review.member is not None:
        resolved_name = review.member.name
    if resolved_name is None and isinstance(review.clinical_snapshot, dict):
        resolved_name = review.clinical_snapshot.get("member_name")

    return {
        "id": str(review.id),
        "household_id": str(review.household_id),
        "member_id": str(review.member_id),
        "member_name": resolved_name or "",
        "review_token": review.review_token,
        "review_url_path": f"/clinician/{review.review_token}",
        "doctor_name": review.doctor_name,
        "doctor_email": review.doctor_email,
        "contact_mode": review.contact_mode,
        "request_note": review.request_note,
        "clinical_snapshot": review.clinical_snapshot,
        "fee_bdt": review.fee_bdt,
        "payment_status": review.payment_status,
        "payment_method": review.payment_method,
        "payment_ref": review.payment_ref,
        "paid_at": review.paid_at.isoformat() if review.paid_at else None,
        "email_status": review.email_status,
        "status": review.status,
        "clinician_reg_no": review.clinician_reg_no,
        "clinician_note": review.clinician_note,
        "approved_diet_presets": list(review.approved_diet_presets or []),
        "apply_presets_on_approve": review.apply_presets_on_approve,
        "created_at": review.created_at.isoformat(),
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
    }


def _build_clinical_snapshot(db: Session, hh: Household, member: Member) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=30)
    doses = db.scalars(
        select(DoseSchedule)
        .join(Medicine)
        .where(Medicine.member_id == member.id, DoseSchedule.due_at >= since)
    ).all()

    counts = {"taken": 0, "taken_late": 0, "missed": 0, "escalated": 0, "pending": 0}
    for d in doses:
        if d.status in counts:
            counts[d.status] += 1
    completed_denom = counts["taken"] + counts["taken_late"] + counts["missed"] + counts["escalated"]
    adherence_pct = (
        round(((counts["taken"] + counts["taken_late"]) / completed_denom) * 100)
        if completed_denom > 0
        else None
    )

    recent_menus = db.scalars(
        select(MenuSuggestion)
        .where(MenuSuggestion.household_id == hh.id)
        .order_by(MenuSuggestion.for_date.desc(), MenuSuggestion.created_at.desc())
        .limit(5)
    ).all()
    recent_meals: list[dict] = []
    for ms in recent_menus:
        top3 = (ms.payload or {}).get("top_3") if isinstance(ms.payload, dict) else None
        if isinstance(top3, list) and top3:
            first_dish = top3[0]
            if isinstance(first_dish, dict):
                recent_meals.append(
                    {
                        "for_date": ms.for_date.isoformat(),
                        "meal": ms.meal,
                        "dish_bn": first_dish.get("name_bn") or first_dish.get("key") or "",
                        "dish_en": first_dish.get("name_en") or first_dish.get("key") or "",
                        "status": first_dish.get("status") or "",
                    }
                )

    return {
        "member_name": member.name,
        "role": member.role,
        "age_group": member.age_group,
        "conditions": list(member.conditions or []),
        "allergies": list(member.allergies or []),
        "diet_presets": list(member.diet_presets or []),
        "medicines": [
            {
                "name_as_written": med.name_as_written,
                "generic_name": med.generic_name,
                "drug_class": med.drug_class,
                "timing": med.timing,
                "meal_slots": list(med.meal_slots or []),
            }
            for med in member.medicines
            if med.active
        ],
        "adherence_30d": {
            **counts,
            "total": len(doses),
            "adherence_pct": adherence_pct,
        },
        "recent_meals": recent_meals,
    }


def _compute_payment_summary(reviews: list[ClinicianReview]) -> dict:
    total_paid_bdt = sum(r.fee_bdt for r in reviews if r.payment_status == "paid")
    total_unpaid_bdt = sum(r.fee_bdt for r in reviews if r.payment_status == "unpaid")
    return {
        "total_paid_bdt": total_paid_bdt,
        "total_unpaid_bdt": total_unpaid_bdt,
        "paid_count": sum(1 for r in reviews if r.payment_status == "paid"),
        "unpaid_count": sum(1 for r in reviews if r.payment_status == "unpaid"),
        "approved_count": sum(1 for r in reviews if r.status == "approved"),
        "pending_count": sum(1 for r in reviews if r.status == "pending"),
        "changes_requested_count": sum(1 for r in reviews if r.status == "changes_requested"),
    }


def _serialize_portal(db: Session, review: ClinicianReview, hh_name: str, member: Member) -> dict:
    presets = sorted({dp.preset for dp in db.scalars(select(DietPreset)).all()})
    data = _serialize_review(review, member_name=member.name)
    data["household_name"] = hh_name
    data["member_current_diet_presets"] = list(member.diet_presets or [])
    data["available_presets"] = presets
    return data


@router.get("/reviews")
def list_clinician_reviews(
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(ClinicianReview)
        .options(selectinload(ClinicianReview.member))
        .where(ClinicianReview.household_id == hh.id)
        .order_by(ClinicianReview.created_at.desc())
    ).all()
    return {
        "reviews": [_serialize_review(r) for r in rows],
        "payment_summary": _compute_payment_summary(rows),
    }


@router.post("/reviews", status_code=201)
def create_clinician_review(
    payload: ClinicianReviewCreateRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    try:
        member_uuid = uuid.UUID(payload.member_id)
    except ValueError as exc:
        raise AppError("MEMBER_NOT_FOUND", "Member not found in household.", status_code=404) from exc

    member = db.scalar(
        select(Member)
        .options(selectinload(Member.medicines))
        .where(Member.id == member_uuid, Member.household_id == hh.id)
    )
    if member is None:
        raise AppError("MEMBER_NOT_FOUND", "Member not found in household.", status_code=404)

    clean_email = (payload.doctor_email or "").strip() or None
    if payload.contact_mode == "email_invite":
        if not clean_email or "@" not in clean_email or "." not in clean_email.split("@", 1)[-1]:
            raise AppError(
                "INVALID_DOCTOR_EMAIL",
                "Please enter a valid doctor/dietitian email address for email invitations.",
                status_code=422,
            )

    settings = get_settings()
    review_token = f"cr-{secrets.token_urlsafe(24)}"
    origin = (payload.frontend_origin or "").strip().rstrip("/")
    if not (origin.startswith("http://") or origin.startswith("https://")):
        origin = (
            settings.cors_origins_list[0].rstrip("/")
            if settings.cors_origins_list
            else "http://localhost:3000"
        )
    review_url = f"{origin}/clinician/{review_token}"

    if payload.contact_mode == "email_invite" and clean_email:
        email_status = send_clinician_review_email(
            recipient_email=clean_email,
            doctor_name=payload.doctor_name.strip(),
            household_name=hh.name,
            member_name=member.name,
            review_url=review_url,
            fee_bdt=payload.fee_bdt,
        )
    else:
        email_status = "not_requested"

    snapshot = _build_clinical_snapshot(db, hh, member)
    now = datetime.now(timezone.utc)
    is_waived = payload.fee_bdt == 0

    review = ClinicianReview(
        household_id=hh.id,
        member_id=member.id,
        review_token=review_token,
        doctor_name=payload.doctor_name.strip(),
        doctor_email=clean_email,
        contact_mode=payload.contact_mode,
        request_note=(payload.request_note or "").strip() or None,
        clinical_snapshot=snapshot,
        fee_bdt=payload.fee_bdt,
        payment_status="waived" if is_waived else "unpaid",
        payment_method="waived" if is_waived else None,
        payment_ref="WAIVED" if is_waived else None,
        paid_at=now if is_waived else None,
        email_status=email_status,
        status="pending",
        approved_diet_presets=list(member.diet_presets or []),
        apply_presets_on_approve=True,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return _serialize_review(review, member_name=member.name)


@router.post("/reviews/{review_id}/pay")
def pay_clinician_review(
    review_id: uuid.UUID,
    payload: ClinicianPaymentRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    review = db.scalar(
        select(ClinicianReview)
        .options(selectinload(ClinicianReview.member))
        .where(ClinicianReview.id == review_id, ClinicianReview.household_id == hh.id)
    )
    if review is None:
        raise AppError("REVIEW_NOT_FOUND", "Clinician review record not found.", status_code=404)
    if review.payment_status in ("paid", "waived"):
        raise AppError("ALREADY_PAID", "Consultation fee is already settled.", status_code=400)

    now = datetime.now(timezone.utc)
    review.payment_status = "paid"
    review.payment_method = payload.payment_method
    review.payment_ref = (payload.payment_ref or "").strip() or f"HRB-PAY-{secrets.token_hex(4).upper()}"
    review.paid_at = now

    db.add(
        Alert(
            household_id=hh.id,
            member_id=review.member_id,
            kind="clinician_fee_paid",
            channel="in_app",
            payload={
                "review_id": str(review.id),
                "fee_bdt": review.fee_bdt,
                "payment_method": review.payment_method,
                "payment_ref": review.payment_ref,
                "text": f"Consultation fee BDT {review.fee_bdt} paid ({review.payment_method}).",
            },
        )
    )
    db.commit()
    db.refresh(review)
    return _serialize_review(review)


@router.get("/portal/{review_token}")
def get_clinician_portal(review_token: str, db: Session = Depends(get_db)):
    review = db.scalar(
        select(ClinicianReview)
        .options(selectinload(ClinicianReview.member).selectinload(Member.household))
        .where(ClinicianReview.review_token == review_token)
    )
    if review is None or review.member is None:
        raise AppError("REVIEW_NOT_FOUND", "Clinician review link is invalid or expired.", status_code=404)

    hh_name = review.member.household.name if review.member.household else ""
    return _serialize_portal(db, review, hh_name, review.member)


@router.post("/portal/{review_token}/decision")
def submit_clinician_decision(
    review_token: str,
    payload: ClinicianDecisionRequest,
    db: Session = Depends(get_db),
):
    review = db.scalar(
        select(ClinicianReview)
        .options(selectinload(ClinicianReview.member).selectinload(Member.household))
        .where(ClinicianReview.review_token == review_token)
    )
    if review is None or review.member is None:
        raise AppError("REVIEW_NOT_FOUND", "Clinician review link is invalid or expired.", status_code=404)

    valid_presets = {dp.preset for dp in db.scalars(select(DietPreset)).all()}
    clean_presets: list[str] = []
    for preset in payload.approved_diet_presets:
        if preset not in valid_presets:
            raise AppError("INVALID_PRESET", f"Unknown diet preset '{preset}'.", status_code=400)
        if preset not in clean_presets:
            clean_presets.append(preset)

    now = datetime.now(timezone.utc)
    review.status = payload.decision
    review.clinician_reg_no = (payload.clinician_reg_no or "").strip() or None
    review.clinician_note = payload.clinician_note.strip()
    review.approved_diet_presets = clean_presets
    review.apply_presets_on_approve = payload.apply_presets_to_member
    review.reviewed_at = now

    if payload.decision == "approved" and payload.apply_presets_to_member:
        review.member.diet_presets = clean_presets

    db.add(
        Alert(
            household_id=review.household_id,
            member_id=review.member_id,
            kind="clinician_review_completed",
            channel="in_app",
            payload={
                "review_id": str(review.id),
                "status": review.status,
                "doctor_name": review.doctor_name,
                "text": f"Care plan review updated by {review.doctor_name}: {review.status}.",
            },
        )
    )
    db.commit()
    db.refresh(review)
    db.refresh(review.member)

    hh_name = review.member.household.name if review.member.household else ""
    return _serialize_portal(db, review, hh_name, review.member)

