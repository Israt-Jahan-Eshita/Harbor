"""Load PostgreSQL entities into pure-Python core domain structures."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.inventory import compute_stock
from app.core.types import (
    DietPresetData,
    DrugFoodRuleData,
    GuestEventData,
    IngredientData,
    InventoryEventData,
    MedicineData,
    MemberData,
    RecipeData,
    RecipeIngredientData,
    RuleContext,
    StockItemState,
)
from app.models import (
    DietPreset,
    DrugClassMap,
    DrugFoodRule,
    Household,
    HouseholdEvent,
    Ingredient,
    IngredientAlias,
    InventoryEvent,
    Member,
    MenuSuggestion,
    PriceObservation,
    Recipe,
)
from app.seed.validate_seed import load_json


def load_rule_context_and_recipes(db: Session) -> tuple[RuleContext, list[RecipeData], dict[str, RecipeData]]:
    """Load ingredients, drug-food rules, diet presets, and recipes from PostgreSQL."""
    ing_rows = db.scalars(select(Ingredient)).all()
    ingredients: dict[str, IngredientData] = {}
    for row in ing_rows:
        ingredients[row.key] = IngredientData(
            key=row.key,
            name_en=row.name_en,
            name_bn=row.name_bn,
            category=row.category,
            allergen_tags=list(row.allergen_tags or []),
            potassium_level=row.potassium_level,
            purine_level=row.purine_level,
            sodium_level=row.sodium_level,
            gi_level=row.gi_level,
            tags=list(row.tags or []),
            season_months=list(row.season_months or []),
            perishable_days=row.perishable_days,
            base_unit=row.base_unit,
            ref_price_bdt=float(row.ref_price_bdt) if row.ref_price_bdt is not None else None,
            ref_price_per=float(row.ref_price_per),
        )

    rule_rows = db.scalars(select(DrugFoodRule)).all()
    rules = [
        DrugFoodRuleData(
            rule_id=r.rule_id,
            drug_class=r.drug_class,
            ingredient_attr=r.ingredient_attr,
            attr_value=r.attr_value,
            severity=r.severity,
            message_bn=r.message_bn,
            message_en=r.message_en,
            source_note=r.source_note,
        )
        for r in rule_rows
    ]

    preset_rows = db.scalars(select(DietPreset)).all()
    presets = [
        DietPresetData(
            preset=p.preset,
            attr=p.attr,
            max_level=p.max_level,  # type: ignore[arg-type]
            split_allowed=p.split_allowed,
        )
        for p in preset_rows
    ]

    context = RuleContext(
        ingredients=ingredients,
        drug_food_rules=rules,
        diet_presets=presets,
    )

    rec_rows = db.scalars(select(Recipe).order_by(Recipe.key)).all()
    recipes: list[RecipeData] = []
    recipes_by_id: dict[str, RecipeData] = {}
    for rec in rec_rows:
        rdata = RecipeData(
            id=str(rec.id),
            key=rec.key,
            name_bn=rec.name_bn,
            name_en=rec.name_en,
            servings_base=rec.servings_base,
            ingredients=[RecipeIngredientData(**item) for item in (rec.ingredients or [])],
            steps_bn=list(rec.steps_bn or []),
            split_step_bn=rec.split_step_bn,
            split_removes=list(rec.split_removes or []),
            taste_score=float(rec.taste_score),
            category=rec.category,
            est_cost_bdt=float(rec.est_cost_bdt) if rec.est_cost_bdt is not None else None,
        )
        recipes.append(rdata)
        recipes_by_id[rdata.id] = rdata

    return context, recipes, recipes_by_id


def load_household_members(db: Session, household_id: uuid.UUID) -> list[MemberData]:
    """Load household members with their medicines into MemberData models."""
    rows = db.scalars(
        select(Member)
        .options(selectinload(Member.medicines))
        .where(Member.household_id == household_id)
        .order_by(Member.created_at)
    ).all()
    members: list[MemberData] = []
    for m in rows:
        meds = [
            MedicineData(
                id=str(med.id),
                name_as_written=med.name_as_written,
                generic_name=med.generic_name,
                drug_class=med.drug_class,
                timing=med.timing,
                meal_slots=list(med.meal_slots or []),
                verified_by_caregiver=med.verified_by_caregiver,
                active=med.active,
            )
            for med in m.medicines
        ]
        members.append(
            MemberData(
                id=str(m.id),
                name=m.name,
                role=m.role,
                age_group=m.age_group,
                conditions=list(m.conditions or []),
                allergies=list(m.allergies or []),
                diet_presets=list(m.diet_presets or []),
                medicines=meds,
            )
        )
    return members


def load_aliases_map(db: Session, ingredients: dict[str, IngredientData]) -> dict[str, IngredientData]:
    """Build alias -> IngredientData map from DB aliases + ingredient Bangla/English names."""
    out: dict[str, IngredientData] = {}
    id_to_key = {row.id: row.key for row in db.scalars(select(Ingredient)).all()}
    for ing_key, ing_data in ingredients.items():
        out[ing_key.lower()] = ing_data
        out[ing_data.name_en.lower()] = ing_data
        out[ing_data.name_bn.lower()] = ing_data

    for alias_row in db.scalars(select(IngredientAlias)).all():
        key = id_to_key.get(alias_row.ingredient_id)
        if key and key in ingredients:
            out[alias_row.alias.strip().lower()] = ingredients[key]
    return out


def load_drug_class_map(db: Session) -> dict[str, str]:
    rows = db.scalars(select(DrugClassMap)).all()
    return {r.drug_name.strip().lower(): r.drug_class for r in rows}


def load_household_stock(
    db: Session,
    household_id: uuid.UUID,
    ingredients: dict[str, IngredientData],
    now: datetime | None = None,
) -> dict[str, StockItemState]:
    """Compute event-sourced stock map for a household."""
    now_dt = now or datetime.now(timezone.utc)
    id_to_key = {row.id: row.key for row in db.scalars(select(Ingredient)).all()}
    ev_rows = db.scalars(
        select(InventoryEvent)
        .where(InventoryEvent.household_id == household_id)
        .order_by(InventoryEvent.created_at)
    ).all()
    ev_data = [
        InventoryEventData(
            event_type=ev.event_type,  # type: ignore[arg-type]
            ingredient_key=id_to_key[ev.ingredient_id],
            qty_base=float(ev.qty_base),
            created_at=ev.created_at,
        )
        for ev in ev_rows
        if ev.ingredient_id in id_to_key
    ]
    return compute_stock(ev_data, ingredients, now_dt)


def load_day_events(
    db: Session,
    household_id: uuid.UUID,
    for_date: date,
) -> tuple[list[GuestEventData], set[str], list[dict[str, Any]]]:
    """Return active guest events (respecting cancellations), away member IDs, and raw event list."""
    rows = db.scalars(
        select(HouseholdEvent)
        .where(
            HouseholdEvent.household_id == household_id,
            HouseholdEvent.for_date == for_date,
        )
        .order_by(HouseholdEvent.created_at)
    ).all()

    guests: list[GuestEventData] = []
    away_ids: set[str] = set()
    raw_list: list[dict[str, Any]] = []

    for row in rows:
        payload = row.payload or {}
        raw_list.append(
            {
                "id": str(row.id),
                "kind": row.kind,
                "for_date": row.for_date.isoformat(),
                "payload": payload,
                "created_at": row.created_at.isoformat(),
            }
        )
        if row.kind == "GUESTS":
            guests.append(
                GuestEventData(
                    guest_count=int(payload.get("guest_count", 0)),
                    restrictions=list(payload.get("restrictions", [])),
                )
            )
        elif row.kind == "GUESTS_CANCELLED":
            guests.clear()
        elif row.kind == "MEMBER_AWAY":
            mid = payload.get("member_id")
            if mid:
                away_ids.add(str(mid))

    return guests, away_ids, raw_list


def load_recent_cooked_keys(
    db: Session,
    household_id: uuid.UUID,
    for_date: date,
    lookback_days: int = 7,
) -> set[str]:
    """Return recipe keys cooked in the last 7 days (from COOKED inventory/menu records)."""
    cutoff_date = for_date - timedelta(days=lookback_days)
    recent_keys: set[str] = set()

    # Check explicit COOKED inventory events with raw_text recipe:<key>
    cutoff_dt = datetime.combine(cutoff_date, datetime.min.time(), tzinfo=timezone.utc)
    cooked_events = db.scalars(
        select(InventoryEvent).where(
            InventoryEvent.household_id == household_id,
            InventoryEvent.event_type == "COOKED",
            InventoryEvent.created_at >= cutoff_dt,
        )
    ).all()
    for ev in cooked_events:
        if ev.raw_text and ev.raw_text.startswith("cooked_recipe:"):
            recent_keys.add(ev.raw_text.split("cooked_recipe:", 1)[1].strip())

    # Also check cooked menu_suggestions
    sugg_rows = db.scalars(
        select(MenuSuggestion).where(
            MenuSuggestion.household_id == household_id,
            MenuSuggestion.for_date >= cutoff_date,
            MenuSuggestion.for_date <= for_date,
        )
    ).all()
    for s in sugg_rows:
        p = s.payload or {}
        if p.get("cooked_recipe_key"):
            recent_keys.add(str(p["cooked_recipe_key"]))

    return recent_keys


def load_user_price_observations(db: Session, household_id: uuid.UUID) -> list[dict[str, Any]]:
    id_to_key = {row.id: row.key for row in db.scalars(select(Ingredient)).all()}
    rows = db.scalars(
        select(PriceObservation).where(
            PriceObservation.household_id == household_id,
            PriceObservation.source == "user_purchase",
        )
    ).all()
    return [
        {
            "ingredient_key": id_to_key[r.ingredient_id],
            "price_bdt": float(r.price_bdt),
            "per_qty": float(r.per_qty),
            "source": r.source,
            "observed_at": r.observed_at,
        }
        for r in rows
        if r.ingredient_id in id_to_key
    ]


def load_substitution_groups() -> dict[str, list[str]]:
    return load_json("substitution_groups.json")["groups"]


def get_household_or_none(db: Session, household_id: uuid.UUID) -> Household | None:
    return db.scalar(select(Household).where(Household.id == household_id))
