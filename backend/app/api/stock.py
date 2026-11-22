"""Pantry stock read and manual adjustment endpoints (B14)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.inventory import compute_adjust_delta
from app.db import get_db
from app.deps import get_current_household
from app.errors import AppError
from app.models import Household, Ingredient, InventoryEvent
from app.schemas import StockAdjustRequest
from app.services.context_loader import load_household_stock, load_rule_context_and_recipes

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("")
def get_stock(hh: Household = Depends(get_current_household), db: Session = Depends(get_db)):
    ctx, _, _ = load_rule_context_and_recipes(db)
    stock_map = load_household_stock(db, hh.id, ctx.ingredients)
    items = []
    for key, ing in sorted(ctx.ingredients.items()):
        st = stock_map.get(key)
        items.append(
            {
                "ingredient_key": key,
                "name_bn": ing.name_bn,
                "name_en": ing.name_en,
                "category": ing.category,
                "base_unit": ing.base_unit,
                "qty_base": st.qty_base if st else 0.0,
                "raw_qty": st.raw_qty if st else 0.0,
                "clamped_negative": st.clamped_negative if st else False,
                "last_purchased_at": st.last_purchased_at.isoformat() if (st and st.last_purchased_at) else None,
                "expiry_ratio": st.expiry_ratio if st else None,
                "near_expiry": st.near_expiry if st else False,
                "perishable_days": ing.perishable_days,
            }
        )
    return {"items": items}


@router.post("/adjust")
def adjust_stock(
    payload: StockAdjustRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    ing_row = db.scalar(select(Ingredient).where(Ingredient.key == payload.ingredient_key))
    if ing_row is None:
        raise AppError("UNKNOWN_INGREDIENT", f"Unknown ingredient '{payload.ingredient_key}'.", status_code=404)

    ctx, _, _ = load_rule_context_and_recipes(db)
    stock_map = load_household_stock(db, hh.id, ctx.ingredients)
    current = stock_map[payload.ingredient_key].qty_base if payload.ingredient_key in stock_map else 0.0
    delta = compute_adjust_delta(current, payload.target_qty_base)

    ev = InventoryEvent(
        household_id=hh.id,
        event_type="ADJUST",
        ingredient_id=ing_row.id,
        qty_base=Decimal(str(delta)),
        source="ui",
        raw_text=payload.note or f"manual_adjust_to_{payload.target_qty_base}",
    )
    db.add(ev)
    db.commit()
    return {
        "ingredient_key": payload.ingredient_key,
        "previous_qty": current,
        "new_qty": payload.target_qty_base,
        "delta": delta,
        "unit": ing_row.base_unit,
    }
