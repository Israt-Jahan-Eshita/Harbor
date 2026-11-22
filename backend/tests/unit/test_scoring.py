"""Unit tests for price estimates and dish scoring (core/prices.py, core/scoring.py)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.prices import get_price_estimate
from app.core.scoring import score_dishes
from app.core.types import (
    HouseholdCandidate,
    IngredientData,
    RecipeData,
    RecipeIngredientData,
    RuleContext,
    StockItemState,
)


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
