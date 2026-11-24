"""Unit tests for whole-week (7 x 3 = 21 slot) meal planner (core/weekly_plan.py)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.core.types import (
    DietPresetData,
    GuestEventData,
    IngredientData,
    MedicineData,
    MemberData,
    RecipeData,
    RecipeIngredientData,
    RuleContext,
    StockItemState,
)
from app.core.weekly_plan import build_weekly_meal_plan, recalculate_weekly_plan_totals


def _weekly_fixture():
    ingredients = {
        "lau": IngredientData(
            key="lau", name_en="Bottle Gourd", name_bn="লাউ", category="vegetable",
            potassium_level="low", purine_level="low", sodium_level="low", gi_level="low",
            season_months=list(range(1, 13)), ref_price_bdt=50.0, ref_price_per=1000.0,
        ),
        "masoor_dal": IngredientData(
            key="masoor_dal", name_en="Masoor Dal", name_bn="মসুর ডাল", category="dal",
            potassium_level="medium", purine_level="medium", sodium_level="low", gi_level="low",
            season_months=list(range(1, 13)), ref_price_bdt=140.0, ref_price_per=1000.0,
        ),
        "rui_fish": IngredientData(
            key="rui_fish", name_en="Rui Fish", name_bn="রুই মাছ", category="fish",
            allergen_tags=["fish"],
            potassium_level="medium", purine_level="medium", sodium_level="low", gi_level="low",
            season_months=list(range(1, 13)), ref_price_bdt=360.0, ref_price_per=1000.0,
        ),
        "chingri": IngredientData(
            key="chingri", name_en="Prawn", name_bn="চিংড়ি", category="fish",
            allergen_tags=["prawn_shellfish"],
            potassium_level="medium", purine_level="high", sodium_level="medium", gi_level="low",
            season_months=list(range(1, 13)), ref_price_bdt=750.0, ref_price_per=1000.0,
        ),
        "salt": IngredientData(
            key="salt", name_en="Salt", name_bn="লবণ", category="spice",
            potassium_level="low", purine_level="low", sodium_level="high", gi_level="low",
            season_months=list(range(1, 13)), ref_price_bdt=40.0, ref_price_per=1000.0,
        ),
        "egg": IngredientData(
            key="egg", name_en="Egg", name_bn="ডিম", category="egg", base_unit="piece",
            allergen_tags=["egg"],
            potassium_level="low", purine_level="low", sodium_level="low", gi_level="low",
            season_months=list(range(1, 13)), ref_price_bdt=140.0, ref_price_per=12.0,
        ),
        "kancha_pepe": IngredientData(
            key="kancha_pepe", name_en="Raw Papaya", name_bn="কাঁচা পেঁপে", category="vegetable",
            potassium_level="low", purine_level="low", sodium_level="low", gi_level="low",
            season_months=list(range(1, 13)), ref_price_bdt=40.0, ref_price_per=1000.0,
        ),
        "chicken": IngredientData(
            key="chicken", name_en="Chicken", name_bn="মুরগি", category="meat",
            potassium_level="medium", purine_level="medium", sodium_level="low", gi_level="low",
            season_months=list(range(1, 13)), ref_price_bdt=220.0, ref_price_per=1000.0,
        ),
    }
    presets = [
        DietPresetData(preset="low_sodium", attr="sodium_level", max_level="medium", split_allowed=True),
        DietPresetData(preset="low_potassium", attr="potassium_level", max_level="medium", split_allowed=False),
    ]
    ctx = RuleContext(ingredients=ingredients, presets=presets, diet_presets=presets)

    recipes = [
        RecipeData(
            id="r1", key="lau_masoor_dal", name_bn="লাউ ডাল", name_en="Lau Dal", category="dal",
            servings_base=4, taste_score=0.85, split_step_bn="লবণ দেওয়ার আগে", split_removes=["salt"],
            ingredients=[
                RecipeIngredientData(ingredient_key="lau", qty=300, unit="g"),
                RecipeIngredientData(ingredient_key="masoor_dal", qty=120, unit="g"),
                RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
            ],
        ),
        RecipeData(
            id="r2", key="dim_bhuna", name_bn="ডিম ভুনা", name_en="Egg Curry", category="egg",
            servings_base=4, taste_score=0.82, split_step_bn="লবণ দেওয়ার আগে", split_removes=["salt"],
            ingredients=[
                RecipeIngredientData(ingredient_key="egg", qty=4, unit="piece"),
                RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
            ],
        ),
        RecipeData(
            id="r3", key="rui_lau_jhol", name_bn="রুই লাউ ঝোল", name_en="Rui Lau", category="fish",
            servings_base=4, taste_score=0.88, split_step_bn="লবণ দেওয়ার আগে", split_removes=["salt"],
            ingredients=[
                RecipeIngredientData(ingredient_key="rui_fish", qty=400, unit="g"),
                RecipeIngredientData(ingredient_key="lau", qty=250, unit="g"),
                RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
            ],
        ),
        RecipeData(
            id="r4", key="pepe_bhaji", name_bn="পেঁপে ভাজি", name_en="Papaya Stir Fry", category="vegetable",
            servings_base=4, taste_score=0.78, split_step_bn="লবণ দেওয়ার আগে", split_removes=["salt"],
            ingredients=[
                RecipeIngredientData(ingredient_key="kancha_pepe", qty=350, unit="g"),
                RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
            ],
        ),
        RecipeData(
            id="r5", key="murgir_jhol", name_bn="মুরগির ঝোল", name_en="Chicken Curry", category="chicken",
            servings_base=4, taste_score=0.86, split_step_bn="লবণ দেওয়ার আগে", split_removes=["salt"],
            ingredients=[
                RecipeIngredientData(ingredient_key="chicken", qty=500, unit="g"),
                RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
            ],
        ),
        RecipeData(
            id="r6", key="lau_chingri", name_bn="লাউ চিংড়ি", name_en="Prawn Curry", category="fish",
            servings_base=4, taste_score=0.90, split_step_bn="লবণ দেওয়ার আগে", split_removes=["salt"],
            ingredients=[
                RecipeIngredientData(ingredient_key="lau", qty=300, unit="g"),
                RecipeIngredientData(ingredient_key="chingri", qty=200, unit="g"),
                RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
            ],
        ),
    ]

    members = [
        MemberData(
            id="m1", name="মা", diet_presets=["low_sodium"],
            medicines=[
                MedicineData(
                    id="med1", name_as_written="Metformin", drug_class="none_modelled",
                    timing="after_food", meal_slots=["breakfast", "dinner"], verified_by_caregiver=True, active=True,
                )
            ],
        ),
        MemberData(id="m2", name="আরিফ", allergies=["prawn_shellfish"]),
        MemberData(id="m3", name="বাবা", diet_presets=["low_potassium"]),
    ]

    stock = {
        "lau": StockItemState(ingredient_key="lau", raw_qty=600, qty_base=600, last_purchased_at=datetime.now(timezone.utc)),
        "salt": StockItemState(ingredient_key="salt", raw_qty=500, qty_base=500),
    }
    return ctx, recipes, members, stock


def test_weekly_plan_builds_21_safe_slots_with_linked_meds_and_shortfall() -> None:
    ctx, recipes, members, stock = _weekly_fixture()
    plan = build_weekly_meal_plan(
        members=members,
        recipes=recipes,
        context=ctx,
        stock_map=stock,
        start_date=date(2026, 11, 24),
        days=7,
        household_budget_bdt=14000,
    )
    assert plan["days_count"] == 7
    assert plan["total_slots"] == 21
    assert plan["safe_slots_count"] == 21
    assert plan["deadlock_slots_count"] == 0
    assert plan["unique_dishes_count"] == 5  # all 5 non-prawn dishes rotated across 21 slots

    # Prawn recipe excluded on every single slot
    for day in plan["days"]:
        for slot in day["slots"]:
            assert slot["recipe_key"] != "lau_chingri"
            assert slot["status"] == "SAFE_WITH_SPLIT"
            med_names = [m["medicine_name"] for m in slot["linked_medicines"]]
            if slot["meal"] in ("breakfast", "dinner"):
                assert "Metformin" in med_names
            else:
                assert med_names == []

    # Consolidated shortfall detects missing items minus initial 600g lau stock
    assert plan["est_weekly_shortfall_bdt"] > 0
    assert len(plan["shortfall_items"]) > 0
    assert len(plan["conflict_matrix"]) >= 1  # chingri conflict captured


def test_weekly_plan_per_day_guest_override_and_unsafe_lock_override() -> None:
    ctx, recipes, members, stock = _weekly_fixture()
    # Day 2 has guest with fish_allergy -> rui_lau_jhol locked for Day 2 lunch must be overridden safely!
    day2 = date(2026, 11, 25)
    plan = build_weekly_meal_plan(
        members=members,
        recipes=recipes,
        context=ctx,
        stock_map=stock,
        start_date=date(2026, 11, 24),
        days=3,
        day_events_by_date={day2: ([GuestEventData(guest_count=2, restrictions=["fish"])], set())},
        locked_slots={
            "2026-11-24:lunch": "murgir_jhol",
            "2026-11-25:lunch": "rui_lau_jhol",
        },
    )
    d1_lunch = next(s for s in plan["days"][0]["slots"] if s["meal"] == "lunch")
    assert d1_lunch["recipe_key"] == "murgir_jhol"
    assert d1_lunch["locked"] is True
    assert d1_lunch["lock_overridden"] is False

    d2_lunch = next(s for s in plan["days"][1]["slots"] if s["meal"] == "lunch")
    assert plan["days"][1]["guest_count"] == 2
    assert plan["days"][1]["people_count"] == 5
    assert d2_lunch["recipe_key"] != "rui_lau_jhol"
    assert d2_lunch["lock_overridden"] is True

    # Recalculation keeps totals consistent
    recalc = recalculate_weekly_plan_totals(
        plan_payload=plan,
        recipes_by_key={r.key: r for r in recipes},
        context=ctx,
        stock_map=stock,
        household_budget_bdt=14000,
    )
    assert recalc["est_weekly_shortfall_bdt"] == plan["est_weekly_shortfall_bdt"]

