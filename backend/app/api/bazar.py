"""Monthly bazar planning, confirmation, and purchase logging endpoints (B16)."""

from __future__ import annotations

import re
import secrets
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.bazar import build_monthly_list
from app.core.prices import get_price_estimate
from app.core.rules import check_dish_safe
from app.core.types import IngredientData, RecipeData, RecipeIngredientData
from app.db import get_db
from app.deps import get_current_household
from app.errors import AppError
from app.llm.client import LLMClient
from app.models import (
    BazarList,
    Household,
    Ingredient,
    IngredientAlias,
    InventoryEvent,
    PriceObservation,
)
from app.schemas import (
    BazarBuildRequest,
    BazarConfirmRequest,
    BazarPredictItemRequest,
    BazarPurchasedRequest,
    dhaka_today,
)
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


class _AIPriceEstimateOutput(BaseModel):
    est_price_bdt: float = Field(..., ge=0, le=500000)
    market_note_bn: str = Field(..., min_length=2, max_length=240)
    market_note_en: str = Field(..., min_length=2, max_length=240)


def _resolve_bazar_ingredient(
    db: Session,
    ctx_ingredients: dict[str, IngredientData],
    ingredient_key: str | None,
    custom_name: str | None,
) -> IngredientData | None:
    clean_key = (ingredient_key or "").strip()
    if clean_key and clean_key in ctx_ingredients:
        return ctx_ingredients[clean_key]

    clean_name = (custom_name or "").strip()
    if not clean_name:
        return None

    lowered = clean_name.lower()
    for ing in ctx_ingredients.values():
        if (
            ing.key.lower() == lowered
            or ing.name_en.strip().lower() == lowered
            or ing.name_bn.strip().lower() == lowered
        ):
            return ing

    alias_row = db.scalar(
        select(IngredientAlias).where(func.lower(IngredientAlias.alias) == lowered)
    )
    if alias_row is not None and alias_row.ingredient is not None:
        return ctx_ingredients.get(alias_row.ingredient.key)
    return None


@router.post("/predict-item")
def predict_bazar_item_endpoint(
    payload: BazarPredictItemRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    clean_key = (payload.ingredient_key or "").strip()
    clean_name = (payload.custom_name or "").strip()
    if not clean_key and not clean_name:
        raise AppError(
            "INVALID_ITEM",
            "Select an ingredient or enter an item name.",
            status_code=422,
        )

    current_month = int(payload.month.split("-")[1]) if payload.month else dhaka_today().month
    if not 1 <= current_month <= 12:
        raise AppError("INVALID_MONTH", "Month must be YYYY-MM.", status_code=400)

    ctx, _, _ = load_rule_context_and_recipes(db)
    members = load_household_members(db, hh.id)
    user_obs = load_user_price_observations(db, hh.id)

    ing = _resolve_bazar_ingredient(db, ctx.ingredients, clean_key, clean_name)

    used_ai = False
    market_note_bn: str | None = None
    market_note_en: str | None = None
    safety_warnings: list[dict] = []

    if ing is not None:
        est = get_price_estimate(ing, user_obs)
        prediction_source = est.source
        missing_price = est.missing_price
        est_cost = (
            round((payload.qty / est.per_qty) * est.price_bdt, 2)
            if (est.price_bdt is not None and est.per_qty > 0)
            else 0.0
        )

        synthetic_recipe = RecipeData(
            id=f"preview-{ing.key}",
            key=f"preview_{ing.key}",
            name_bn=ing.name_bn,
            name_en=ing.name_en,
            servings_base=4,
            ingredients=[
                RecipeIngredientData(
                    ingredient_key=ing.key,
                    qty=payload.qty,
                    unit=ing.base_unit,
                )
            ],
            category=ing.category,
        )
        for member in members:
            res = check_dish_safe(member, synthetic_recipe, ctx)
            if res.status in ("BLOCKED", "UNVERIFIED", "SAFE_WITH_SPLIT"):
                safety_warnings.append(
                    {
                        "member_name": member.name,
                        "status": res.status,
                        "reasons": list(res.reasons),
                    }
                )

        if payload.use_ai_estimate:
            llm = LLMClient()
            ai_out = llm.call_groq_json(
                task="bazar_price_predict",
                system_prompt=(
                    "You estimate retail Bangladesh grocery prices in BDT. "
                    "Return JSON with est_price_bdt (total BDT for requested quantity), "
                    "market_note_bn (concise Bangla price note <= 200 chars), "
                    "and market_note_en (concise English price note <= 200 chars)."
                ),
                user_prompt=(
                    f"Item: {ing.name_en} ({ing.name_bn})\n"
                    f"Quantity: {payload.qty} {ing.base_unit}\n"
                    f"Month number: {current_month}\n"
                    f"Reference estimate: {est_cost} BDT (missing={missing_price})"
                ),
                schema_cls=_AIPriceEstimateOutput,
                db=db,
                model_override=llm.llm_fast_model,
                max_completion_tokens=180,
                input_summary=f"bazar_predict:{ing.key}:{payload.qty}{ing.base_unit}",
            )
            if ai_out is not None:
                used_ai = True
                market_note_bn = ai_out.market_note_bn
                market_note_en = ai_out.market_note_en
                if missing_price:
                    est_cost = round(float(ai_out.est_price_bdt), 2)
                    missing_price = False
                    prediction_source = "ai_market_estimate"

        item = {
            "ingredient_key": ing.key,
            "name_bn": ing.name_bn,
            "qty": round(payload.qty, 2),
            "unit": ing.base_unit,
            "est_price_bdt": est_cost,
            "price_source": prediction_source,
            "missing_price": missing_price,
            "is_estimated": True,
            "label_bn": "আনুমানিক",
            "in_season": current_month in ing.season_months,
            "substitute_used": False,
            "substituted_from": None,
            "dropped": False,
            "flag": "ইউজার যোগ করেছেন",
            "category": ing.category,
        }
    else:
        display_name = clean_name or clean_key
        slug = re.sub(r"[^a-z0-9]+", "_", display_name.lower()).strip("_") or secrets.token_hex(3)
        custom_key = f"custom_{slug}"
        safety_warnings = [
            {
                "member_name": "Family",
                "status": "UNVERIFIED",
                "reasons": ["UNVERIFIED_CUSTOM_ITEM"],
            }
        ]
        est_cost = 0.0
        prediction_source = "missing"
        missing_price = True

        if payload.use_ai_estimate:
            llm = LLMClient()
            ai_out = llm.call_groq_json(
                task="bazar_price_predict",
                system_prompt=(
                    "You estimate retail Bangladesh grocery prices in BDT. "
                    "Return JSON with est_price_bdt (total BDT for requested quantity), "
                    "market_note_bn (concise Bangla price note <= 200 chars), "
                    "and market_note_en (concise English price note <= 200 chars)."
                ),
                user_prompt=(
                    f"Custom grocery item: {display_name}\n"
                    f"Quantity: {payload.qty} {payload.unit}\n"
                    f"Month number: {current_month}\n"
                    "Estimate typical Dhaka retail cost in BDT."
                ),
                schema_cls=_AIPriceEstimateOutput,
                db=db,
                model_override=llm.llm_fast_model,
                max_completion_tokens=180,
                input_summary=f"bazar_predict_custom:{display_name}:{payload.qty}{payload.unit}",
            )
            if ai_out is not None:
                used_ai = True
                est_cost = round(float(ai_out.est_price_bdt), 2)
                prediction_source = "ai_market_estimate"
                missing_price = False
                market_note_bn = ai_out.market_note_bn
                market_note_en = ai_out.market_note_en

        item = {
            "ingredient_key": custom_key,
            "name_bn": display_name,
            "qty": round(payload.qty, 2),
            "unit": payload.unit,
            "est_price_bdt": est_cost,
            "price_source": prediction_source,
            "missing_price": missing_price,
            "is_estimated": True,
            "label_bn": "আনুমানিক",
            "in_season": False,
            "substitute_used": False,
            "substituted_from": None,
            "dropped": False,
            "flag": "কাস্টম আইটেম (যাচাইকৃত ক্যাটালগের বাইরে)",
            "category": "custom",
        }

    projected_total = round(payload.current_total_bdt + float(item["est_price_bdt"]), 2)
    over_budget = (projected_total > payload.budget_bdt) if payload.budget_bdt else False
    budget_delta = round(projected_total - payload.budget_bdt, 2) if payload.budget_bdt else 0.0

    return {
        "item": item,
        "prediction_source": prediction_source,
        "used_ai": used_ai,
        "market_note_bn": market_note_bn,
        "market_note_en": market_note_en,
        "projected_total_bdt": projected_total,
        "over_budget": over_budget,
        "budget_delta_bdt": budget_delta,
        "safety_warnings": safety_warnings,
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
    skipped_custom_count = 0

    for item in payload.items:
        ing = ing_by_key.get(item.ingredient_key)
        if ing is None:
            if item.ingredient_key.startswith("custom_"):
                skipped_custom_count += 1
                continue
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
        "skipped_custom_count": skipped_custom_count,
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
