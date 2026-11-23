"""Monthly bazar planning, confirmation, and purchase logging endpoints (B16)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.bazar import build_monthly_list
from app.db import get_db
from app.deps import get_current_household
from app.errors import AppError
from app.models import BazarList, Household, Ingredient, InventoryEvent, PriceObservation
from app.schemas import BazarBuildRequest, BazarConfirmRequest, BazarPurchasedRequest
from app.services.context_loader import (
    load_household_members,
    load_household_stock,
    load_rule_context_and_recipes,
    load_substitution_groups,
    load_user_price_observations,
)

router = APIRouter(prefix="/bazar", tags=["bazar"])


@router.post("/build")
def build_bazar_list_endpoint(
    payload: BazarBuildRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    ctx, recipes, _ = load_rule_context_and_recipes(db)
    members = load_household_members(db, hh.id)
    stock = load_household_stock(db, hh.id, ctx.ingredients)
    user_obs = load_user_price_observations(db, hh.id)
    current_month = int(payload.month.split("-")[1])
    if not 1 <= current_month <= 12:
        raise AppError("INVALID_MONTH", "Month must be YYYY-MM.", status_code=400)

    plan = build_monthly_list(
        members=members,
        recipes=recipes,
        context=ctx,
        stock_map=stock,
        month=payload.month,
        current_month=current_month,
        budget_bdt=payload.budget_bdt,
        substitution_groups=load_substitution_groups(),
        user_price_observations=user_obs,
    )

    bl = BazarList(
        household_id=hh.id,
        month=payload.month,
        budget_bdt=payload.budget_bdt,
        items=plan["items"],
        est_total_bdt=Decimal(str(plan["est_total_bdt"])),
        status="draft",
    )
    db.add(bl)
    db.commit()
    db.refresh(bl)

    return {
        "bazar_list_id": str(bl.id),
        "status": bl.status,
        "price_label_bn": "আনুমানিক",
        "price_label_en": "Estimated",
        **plan,
    }


@router.post("/confirm")
def confirm_bazar_list(
    payload: BazarConfirmRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    bl_uuid = uuid.UUID(payload.bazar_list_id)
    bl = db.scalar(
        select(BazarList).where(BazarList.id == bl_uuid, BazarList.household_id == hh.id)
    )
    if bl is None:
        raise AppError("BAZAR_NOT_FOUND", "Bazar list not found.", status_code=404)

    est_total = round(
        sum(float(it.get("est_price_bdt", 0.0)) for it in payload.items if not it.get("dropped")),
        2,
    )
    bl.items = payload.items
    bl.est_total_bdt = Decimal(str(est_total))
    bl.status = "confirmed"
    db.commit()
    db.refresh(bl)
    return {
        "bazar_list_id": str(bl.id),
        "status": bl.status,
        "est_total_bdt": float(bl.est_total_bdt),
        "items": bl.items,
        "price_label_bn": "আনুমানিক",
        "price_label_en": "Estimated",
    }


@router.post("/purchased")
def log_bazar_purchased(
    payload: BazarPurchasedRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    ing_by_key = {row.key: row for row in db.scalars(select(Ingredient)).all()}
    events_written = 0
    prices_recorded = 0

    for item in payload.items:
        ing = ing_by_key.get(item.ingredient_key)
        if ing is None:
            raise AppError("UNKNOWN_INGREDIENT", f"Unknown ingredient '{item.ingredient_key}'.", status_code=400)
        db.add(
            InventoryEvent(
                household_id=hh.id,
                event_type="PURCHASED",
                ingredient_id=ing.id,
                qty_base=Decimal(str(item.qty_base)),
                source="ui",
                raw_text="bazar_purchased",
            )
        )
        events_written += 1

        if item.price_bdt is not None and item.price_bdt > 0:
            db.add(
                PriceObservation(
                    household_id=hh.id,
                    ingredient_id=ing.id,
                    price_bdt=Decimal(str(item.price_bdt)),
                    per_qty=Decimal(str(item.per_qty)),
                    source="user_purchase",
                )
            )
            prices_recorded += 1

    db.commit()
    return {
        "events_written": events_written,
        "prices_recorded": prices_recorded,
    }


@router.get("/latest")
def get_latest_bazar(
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    bl = db.scalar(
        select(BazarList)
        .where(BazarList.household_id == hh.id)
        .order_by(BazarList.created_at.desc())
    )
    if bl is None:
        return {"bazar_list": None}
    return {
        "bazar_list": {
            "bazar_list_id": str(bl.id),
            "month": bl.month,
            "budget_bdt": bl.budget_bdt,
            "items": bl.items,
            "est_total_bdt": float(bl.est_total_bdt),
            "status": bl.status,
            "price_label_bn": "আনুমানিক",
            "price_label_en": "Estimated",
            "created_at": bl.created_at.isoformat(),
        }
    }
