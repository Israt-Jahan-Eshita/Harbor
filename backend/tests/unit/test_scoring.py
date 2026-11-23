"""Unit tests for price estimates and dish scoring (core/prices.py, core/scoring.py)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.core.prices import get_price_estimate
from app.core.scoring import score_dishes
from app.core.shared_pot import find_shared_pot_dishes
from app.core.types import (
    DietPresetData,
    DrugFoodRuleData,
    HouseholdCandidate,
    IngredientData,
    MedicineData,
    MemberData,
    RecipeData,
    RecipeIngredientData,
    RuleContext,
    StockItemState,
)
from app.seed.validate_seed import load_json


def test_price_estimate_priority_and_agripricebd() -> None:
    garlic = IngredientData(
        key="garlic", name_en="Garlic", name_bn="রসুন",
        base_unit="g", ref_price_bdt=220.0, ref_price_per=1000.0,
    )
    # 1. Reference fallback when no user purchase
    est_ref = get_price_estimate(garlic)
    assert est_ref.source == "reference_table"
    assert est_ref.price_bdt == 220.0
    assert est_ref.is_estimated is True
    assert est_ref.label_bn == "আনুমানিক"
    assert est_ref.cross_check_skipped is True

    # 2. AgriPriceBD cross-check flags >30% disagreement
    est_cross = get_price_estimate(
        garlic,
        agripricebd_data={"garlic": {"price_bdt": 120.0, "per_qty": 1000.0}},
    )
    assert est_cross.cross_check_note is not None
    assert "AgriPriceBD" in est_cross.cross_check_note

    # 3. User purchase overrides reference table
    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    est_user = get_price_estimate(
        garlic,
        user_observations=[
            {"ingredient_key": "garlic", "source": "user_purchase", "price_bdt": 190.0, "per_qty": 1000.0, "observed_at": now - timedelta(days=5)},
            {"ingredient_key": "garlic", "source": "user_purchase", "price_bdt": 250.0, "per_qty": 1000.0, "observed_at": now},
        ],
    )
    assert est_user.source == "user_purchase"
    assert est_user.price_bdt == 250.0

    # 4. Missing price everywhere never invents a price
    unpriced = IngredientData(key="rare", name_en="Rare", name_bn="দুর্লভ", ref_price_bdt=None)
    est_miss = get_price_estimate(unpriced)
    assert est_miss.missing_price is True
    assert est_miss.price_bdt is None


def test_scoring_repeat_penalty_expiry_season_and_weights() -> None:
    ctx = RuleContext(
        ingredients={
            "lau": IngredientData(
                key="lau", name_en="Lau", name_bn="লাউ",
                season_months=[11, 12], perishable_days=7, ref_price_bdt=60.0, ref_price_per=1000.0,
            ),
            "jhinge": IngredientData(
                key="jhinge", name_en="Jhinge", name_bn="ঝিঙে",
                season_months=[5, 6], perishable_days=5, ref_price_bdt=70.0, ref_price_per=1000.0,
            ),
        }
    )
    r1 = RecipeData(
        id="r1", key="lau_dish", name_bn="লাউ",
        ingredients=[RecipeIngredientData(ingredient_key="lau", qty=300, unit="g")],
        taste_score=0.8,
    )
    r2 = RecipeData(
        id="r2", key="jhinge_dish", name_bn="ঝিঙে",
        ingredients=[RecipeIngredientData(ingredient_key="jhinge", qty=300, unit="g")],
        taste_score=0.8,
    )
    cands = [
        HouseholdCandidate(recipe=r1, status="SAFE_DIRECT"),
        HouseholdCandidate(recipe=r2, status="SAFE_DIRECT"),
    ]
    stock = {
        "lau": StockItemState(ingredient_key="lau", raw_qty=500, qty_base=500, near_expiry=True),
        "jhinge": StockItemState(ingredient_key="jhinge", raw_qty=500, qty_base=500, near_expiry=False),
    }
    ranked = score_dishes(cands, stock, ctx, current_month=11, recent_cooked_recipe_keys={"jhinge_dish"})
    assert ranked[0].recipe.key == "lau_dish"
    assert ranked[0].components["expiry_bonus"] == 1.0
    assert ranked[0].components["season_bonus"] == 1.0
    assert ranked[1].components["repeat_penalty"] == 1.0
    assert ranked[0].score > ranked[1].score

    # Weight override changes ranking when repeat_penalty=0 and taste=1.0 dominates
    r2_tastier = RecipeData(
        id="r2", key="jhinge_dish", name_bn="ঝিঙে",
        ingredients=[RecipeIngredientData(ingredient_key="jhinge", qty=300, unit="g")],
        taste_score=1.0,
    )
    cands2 = [
        HouseholdCandidate(recipe=r1, status="SAFE_DIRECT"),
        HouseholdCandidate(recipe=r2_tastier, status="SAFE_DIRECT"),
    ]
    ranked_custom = score_dishes(
        cands2,
        stock,
        ctx,
        current_month=11,
        recent_cooked_recipe_keys={"jhinge_dish"},
        weights={"stock_fit": 0.0, "expiry_bonus": 0.0, "season_bonus": 0.0, "health_fit": 0.0, "taste": 1.0, "price_fit": 0.0, "repeat_penalty": 0.0},
    )
    assert ranked_custom[0].recipe.key == "jhinge_dish"


def test_meal_slot_differentiation_and_daily_date_rotation() -> None:
    """Breakfast, lunch, and dinner return distinct dish types, and changing dates rotates Top 3."""
    ingredients_raw = load_json("ingredients.json")["ingredients"]
    rules_raw = load_json("rules.json")["rules"]
    presets_raw = load_json("diet_presets.json")["presets"]
    recipes_raw = load_json("recipes.json")["recipes"]
    demo_raw = load_json("demo_household.json")

    ctx = RuleContext(
        ingredients={ing["key"]: IngredientData(**ing) for ing in ingredients_raw},
        drug_food_rules=[DrugFoodRuleData(**r) for r in rules_raw],
        diet_presets=[DietPresetData(**p) for p in presets_raw],
    )
    recipes = [
        RecipeData(
            id=r["key"],
            key=r["key"],
            name_bn=r["name_bn"],
            name_en=r["name_en"],
            servings_base=r["servings_base"],
            ingredients=[RecipeIngredientData(**ri) for ri in r["ingredients"]],
            steps_bn=r["steps_bn"],
            split_step_bn=r.get("split_step_bn"),
            split_removes=r.get("split_removes", []),
            taste_score=r["taste_score"],
            category=r["category"],
            est_cost_bdt=r.get("est_cost_bdt"),
        )
        for r in recipes_raw
    ]
    members = [
        MemberData(
            id=f"m-{i}",
            name=m["name"],
            role=m["role"],
            age_group=m["age_group"],
            conditions=m["conditions"],
            allergies=m["allergies"],
            diet_presets=m["diet_presets"],
            medicines=[MedicineData(id=f"med-{i}-{j}", **med) for j, med in enumerate(m.get("medicines", []))],
        )
        for i, m in enumerate(demo_raw["members"])
    ]
    stock = {
        item["ingredient_key"]: StockItemState(
            ingredient_key=item["ingredient_key"],
            raw_qty=float(item["qty_base"]),
            qty_base=float(item["qty_base"]),
            near_expiry=False,
        )
        for item in demo_raw["initial_stock"]
    }

    shared = find_shared_pot_dishes(members, recipes, ctx, date(2026, 11, 24), meal="dinner")

    bf_24 = [s.recipe.key for s in score_dishes(shared.candidates, stock, ctx, 11, meal="breakfast", for_date=date(2026, 11, 24))[:3]]
    ln_24 = [s.recipe.key for s in score_dishes(shared.candidates, stock, ctx, 11, meal="lunch", for_date=date(2026, 11, 24))[:3]]
    dn_24 = [s.recipe.key for s in score_dishes(shared.candidates, stock, ctx, 11, meal="dinner", for_date=date(2026, 11, 24))[:3]]

    # Breakfast, lunch, and dinner on the same date must not be identical
    assert bf_24 != ln_24
    assert ln_24 != dn_24
    assert bf_24 != dn_24

    # Breakfast top 3 must never include heavy fish or meat curries
    recipes_by_key = {r.key: r for r in recipes}
    assert all(recipes_by_key[k].category not in ("fish", "meat") for k in bf_24)

    # Changing the date (Nov 24 vs Nov 25 vs Dec 1) rotates the Top 3 menu
    dn_25 = [s.recipe.key for s in score_dishes(shared.candidates, stock, ctx, 11, meal="dinner", for_date=date(2026, 11, 25))[:3]]
    dn_dec1 = [s.recipe.key for s in score_dishes(shared.candidates, stock, ctx, 12, meal="dinner", for_date=date(2026, 12, 1))[:3]]
    assert dn_24 != dn_25
    assert dn_24 != dn_dec1
    assert dn_25 != dn_dec1
