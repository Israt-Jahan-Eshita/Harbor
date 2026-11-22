"""Household creation, login, demo loader, and state endpoints (B12)."""

from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_household, hash_pin, sign_session_token, verify_pin
from app.errors import AppError
from app.models import Alert, Household
from app.schemas import (
    HouseholdAuthResponse,
    HouseholdCreateRequest,
    HouseholdLoginRequest,
    HouseholdSettingsUpdateRequest,
)
from app.seed.load import seed_demo_household, seed_reference_data
from app.services.context_loader import (
    load_day_events,
    load_household_members,
    load_household_stock,
    load_rule_context_and_recipes,
)

router = APIRouter(prefix="/households", tags=["households"])


def _generate_access_code(db: Session) -> str:
    for _ in range(10):
        code = "HBR" + secrets.token_hex(2).upper()
        if db.scalar(select(Household).where(Household.access_code == code)) is None:
            return code
    return "HBR" + secrets.token_hex(4).upper()


def _auth_payload(hh: Household) -> HouseholdAuthResponse:
    return HouseholdAuthResponse(
        household_id=str(hh.id),
        name=hh.name,
        access_code=hh.access_code,
        token=sign_session_token(hh.id),
        consent_given=hh.consent_given,
        meal_times=hh.meal_times,
        monthly_budget_bdt=hh.monthly_budget_bdt,
    )


@router.post("", response_model=HouseholdAuthResponse, status_code=201)
def create_household(payload: HouseholdCreateRequest, db: Session = Depends(get_db)):
    hh = Household(
        name=payload.name.strip(),
        access_code=_generate_access_code(db),
        caregiver_pin_hash=hash_pin(payload.pin.strip()),
        consent_given=payload.consent_given,
        meal_times=payload.meal_times.model_dump(),
        monthly_budget_bdt=payload.monthly_budget_bdt,
    )
    db.add(hh)
    db.commit()
    db.refresh(hh)
    return _auth_payload(hh)


@router.post("/login", response_model=HouseholdAuthResponse)
def login_household(payload: HouseholdLoginRequest, db: Session = Depends(get_db)):
    code = payload.access_code.strip().upper()
    hh = db.scalar(select(Household).where(Household.access_code == code))
    if hh is None or not verify_pin(payload.pin.strip(), hh.caregiver_pin_hash):
        raise AppError("INVALID_CREDENTIALS", "Invalid access code or PIN.", status_code=401)
    return _auth_payload(hh)


@router.post("/demo", response_model=HouseholdAuthResponse)
def load_demo_household(reset: bool = False, db: Session = Depends(get_db)):
    """Load/reset the SPEC §9.7 demo household (DEMO26 / PIN 1234) and issue a session token."""
    seed_reference_data(db)
    hh = seed_demo_household(db, reset=reset)
    return _auth_payload(hh)


@router.get("/{household_id}/state")
def get_household_state(
    household_id: uuid.UUID,
    for_date: date | None = None,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    if hh.id != household_id:
        raise AppError("FORBIDDEN", "Access denied to another household.", status_code=403)

    settings = get_settings()
    target_date = for_date or datetime.now(ZoneInfo(settings.tz)).date()
    ctx, _, _ = load_rule_context_and_recipes(db)
    members = load_household_members(db, hh.id)
    stock = load_household_stock(db, hh.id, ctx.ingredients)
    guests, away_ids, today_events = load_day_events(db, hh.id, target_date)

    near_expiry_items = [
        {"ingredient_key": k, "name_bn": ctx.ingredients[k].name_bn, "expiry_ratio": s.expiry_ratio}
        for k, s in stock.items()
        if s.near_expiry and k in ctx.ingredients
    ]
    recent_alerts = db.scalars(
        select(Alert)
        .where(Alert.household_id == hh.id)
        .order_by(Alert.sent_at.desc())
        .limit(10)
    ).all()

    return {
        "household_id": str(hh.id),
        "name": hh.name,
        "access_code": hh.access_code,
        "consent_given": hh.consent_given,
        "meal_times": hh.meal_times,
        "monthly_budget_bdt": hh.monthly_budget_bdt,
        "for_date": target_date.isoformat(),
        "members": [m.model_dump() for m in members],
        "present_member_count": len([m for m in members if m.id not in away_ids]),
        "guest_count": sum(g.guest_count for g in guests),
        "today_events": today_events,
        "stock_item_count": sum(1 for s in stock.values() if s.qty_base > 0),
        "near_expiry_items": near_expiry_items,
        "recent_alerts": [
            {
                "id": str(a.id),
                "kind": a.kind,
                "channel": a.channel,
                "sent_at": a.sent_at.isoformat(),
                "payload": a.payload,
            }
            for a in recent_alerts
        ],
    }


@router.patch("/{household_id}/settings")
def update_household_settings(
    household_id: uuid.UUID,
    payload: HouseholdSettingsUpdateRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    if hh.id != household_id:
        raise AppError("FORBIDDEN", "Access denied to another household.", status_code=403)
    if payload.name is not None:
        hh.name = payload.name.strip()
    if payload.consent_given is not None:
        hh.consent_given = payload.consent_given
    if payload.meal_times is not None:
        hh.meal_times = payload.meal_times.model_dump()
    if payload.monthly_budget_bdt is not None:
        hh.monthly_budget_bdt = payload.monthly_budget_bdt
    db.commit()
    db.refresh(hh)
    return {
        "household_id": str(hh.id),
        "name": hh.name,
        "consent_given": hh.consent_given,
        "meal_times": hh.meal_times,
        "monthly_budget_bdt": hh.monthly_budget_bdt,
    }
