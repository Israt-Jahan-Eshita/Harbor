"""Idempotent database seed loader (`python -m app.seed.load`)."""

from __future__ import annotations

import os
import secrets
from decimal import Decimal

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, build_engine
from app.models import (
    DietPreset,
    DrugClassMap,
    DrugFoodRule,
    Household,
    Ingredient,
    IngredientAlias,
    InventoryEvent,
    Medicine,
    Member,
    PriceObservation,
    Recipe,
)
from app.seed.validate_seed import load_json, validate_all_seeds


def _hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def seed_reference_data(db: Session) -> dict[str, int]:
    """Idempotently upsert all reference tables (drug map, rules, presets, ingredients, aliases, recipes)."""
    validate_all_seeds()

    drug_map_data = load_json("drug_class_map.json")["classes"]
    rules_data = load_json("rules.json")["rules"]
    presets_data = load_json("diet_presets.json")["presets"]
    ingredients_data = load_json("ingredients.json")["ingredients"]
    aliases_data = load_json("aliases.json")["aliases"]
    recipes_data = load_json("recipes.json")["recipes"]

    # 1. Drug class map
    for drug_class, drug_names in drug_map_data.items():
        for drug_name in drug_names:
            norm_name = drug_name.strip().lower()
            existing = db.scalar(select(DrugClassMap).where(DrugClassMap.drug_name == norm_name))
            if existing:
                existing.drug_class = drug_class
            else:
                db.add(DrugClassMap(drug_name=norm_name, drug_class=drug_class))

    # 2. Drug-food rules
    for r in rules_data:
        existing = db.scalar(select(DrugFoodRule).where(DrugFoodRule.rule_id == r["rule_id"]))
        if existing:
            existing.drug_class = r["drug_class"]
            existing.ingredient_attr = r["ingredient_attr"]
            existing.attr_value = r["attr_value"]
            existing.severity = r["severity"]
            existing.message_bn = r["message_bn"]
            existing.message_en = r["message_en"]
            existing.source_note = r["source_note"]
        else:
            db.add(DrugFoodRule(**r))

    # 3. Diet presets
    for p in presets_data:
        existing = db.scalar(
            select(DietPreset).where(
                DietPreset.preset == p["preset"],
                DietPreset.attr == p["attr"],
            )
        )
        if existing:
            existing.max_level = p["max_level"]
            existing.split_allowed = p["split_allowed"]
        else:
            db.add(DietPreset(**p))

    # 4. Ingredients
    ing_key_to_obj: dict[str, Ingredient] = {}
    for ing in ingredients_data:
        existing = db.scalar(select(Ingredient).where(Ingredient.key == ing["key"]))
        if existing:
            for field in (
                "name_en",
                "name_bn",
                "category",
                "allergen_tags",
                "potassium_level",
                "purine_level",
                "sodium_level",
                "gi_level",
                "tags",
                "season_months",
                "perishable_days",
                "base_unit",
            ):
                setattr(existing, field, ing[field])
            existing.ref_price_bdt = Decimal(str(ing["ref_price_bdt"]))
            existing.ref_price_per = Decimal(str(ing["ref_price_per"]))
            ing_key_to_obj[ing["key"]] = existing
        else:
            obj = Ingredient(
                key=ing["key"],
                name_en=ing["name_en"],
                name_bn=ing["name_bn"],
                category=ing["category"],
                allergen_tags=ing["allergen_tags"],
                potassium_level=ing["potassium_level"],
                purine_level=ing["purine_level"],
                sodium_level=ing["sodium_level"],
                gi_level=ing["gi_level"],
                tags=ing["tags"],
                season_months=ing["season_months"],
                perishable_days=ing["perishable_days"],
                base_unit=ing["base_unit"],
                ref_price_bdt=Decimal(str(ing["ref_price_bdt"])),
                ref_price_per=Decimal(str(ing["ref_price_per"])),
            )
            db.add(obj)
            ing_key_to_obj[ing["key"]] = obj

    db.flush()

    # 5. Ingredient aliases
    for alias, ing_key in aliases_data.items():
        ing_obj = ing_key_to_obj[ing_key]
        existing = db.scalar(select(IngredientAlias).where(IngredientAlias.alias == alias))
        if existing:
            existing.ingredient_id = ing_obj.id
        else:
            db.add(IngredientAlias(alias=alias, ingredient_id=ing_obj.id))

    # 6. Reference price observations (global, household_id=None)
    for ing_key, ing_obj in ing_key_to_obj.items():
        if ing_obj.ref_price_bdt is None:
            continue
        existing_obs = db.scalar(
            select(PriceObservation).where(
                PriceObservation.household_id.is_(None),
                PriceObservation.ingredient_id == ing_obj.id,
                PriceObservation.source == "reference_table",
            )
        )
        if existing_obs:
            existing_obs.price_bdt = ing_obj.ref_price_bdt
            existing_obs.per_qty = ing_obj.ref_price_per
        else:
            db.add(
                PriceObservation(
                    household_id=None,
                    ingredient_id=ing_obj.id,
                    price_bdt=ing_obj.ref_price_bdt,
                    per_qty=ing_obj.ref_price_per,
                    source="reference_table",
                )
            )

    # 7. Recipes
    for r in recipes_data:
        existing = db.scalar(select(Recipe).where(Recipe.key == r["key"]))
        if existing:
            existing.name_bn = r["name_bn"]
            existing.name_en = r["name_en"]
            existing.servings_base = r["servings_base"]
            existing.ingredients = r["ingredients"]
            existing.steps_bn = r["steps_bn"]
            existing.split_step_bn = r["split_step_bn"]
            existing.split_removes = r["split_removes"]
            existing.taste_score = Decimal(str(r["taste_score"]))
            existing.category = r["category"]
            existing.est_cost_bdt = Decimal(str(r["est_cost_bdt"])) if r.get("est_cost_bdt") is not None else None
        else:
            db.add(
                Recipe(
                    key=r["key"],
                    name_bn=r["name_bn"],
                    name_en=r["name_en"],
                    servings_base=r["servings_base"],
                    ingredients=r["ingredients"],
                    steps_bn=r["steps_bn"],
                    split_step_bn=r["split_step_bn"],
                    split_removes=r["split_removes"],
                    taste_score=Decimal(str(r["taste_score"])),
                    category=r["category"],
                    est_cost_bdt=Decimal(str(r["est_cost_bdt"])) if r.get("est_cost_bdt") is not None else None,
                )
            )

    db.commit()
    return {
        "ingredients": len(ingredients_data),
        "aliases": len(aliases_data),
        "recipes": len(recipes_data),
        "rules": len(rules_data),
        "presets": len(presets_data),
    }


def seed_demo_household(db: Session, reset: bool = False) -> Household:
    """Create (or reset) the SPEC section 9.7 demo household."""
    demo = load_json("demo_household.json")
    hh_spec = demo["household"]
    existing = db.scalar(select(Household).where(Household.access_code == hh_spec["access_code"]))

    if existing and not reset:
        return existing

    if existing and reset:
        db.delete(existing)
        db.flush()

    hh = Household(
        name=hh_spec["name"],
        access_code=hh_spec["access_code"],
        caregiver_pin_hash=_hash_pin(hh_spec["pin"]),
        consent_given=hh_spec["consent_given"],
        meal_times=hh_spec["meal_times"],
        monthly_budget_bdt=hh_spec["monthly_budget_bdt"],
    )
    db.add(hh)
    db.flush()

    for m_spec in demo["members"]:
        member = Member(
            household_id=hh.id,
            name=m_spec["name"],
            role=m_spec["role"],
            age_group=m_spec["age_group"],
            conditions=m_spec["conditions"],
            allergies=m_spec["allergies"],
            diet_presets=m_spec["diet_presets"],
            patient_token=f"demo-{secrets.token_urlsafe(12)}",
        )
        db.add(member)
        db.flush()

        for med_spec in m_spec.get("medicines", []):
            db.add(
                Medicine(
                    member_id=member.id,
                    name_as_written=med_spec["name_as_written"],
                    generic_name=med_spec.get("generic_name"),
                    drug_class=med_spec.get("drug_class"),
                    timing=med_spec["timing"],
                    meal_slots=med_spec["meal_slots"],
                    verified_by_caregiver=med_spec["verified_by_caregiver"],
                    active=med_spec["active"],
                )
            )

    ing_map = {ing.key: ing for ing in db.scalars(select(Ingredient)).all()}
    for stock_item in demo.get("initial_stock", []):
        ing = ing_map.get(stock_item["ingredient_key"])
        if ing:
            db.add(
                InventoryEvent(
                    household_id=hh.id,
                    event_type="PURCHASED",
                    ingredient_id=ing.id,
                    qty_base=Decimal(str(stock_item["qty_base"])),
                    source="system",
                    raw_text="demo_seed_initial_stock",
                )
            )

    db.commit()
    db.refresh(hh)
    return hh


def main() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        eng = build_engine(db_url)
        from sqlalchemy.orm import sessionmaker

        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
        db = session_factory()
    else:
        db = SessionLocal()

    try:
        counts = seed_reference_data(db)
        hh = seed_demo_household(db, reset=False)
        print("Seed load complete:", counts, "demo_household_code=", hh.access_code)
    finally:
        db.close()


if __name__ == "__main__":
    main()
