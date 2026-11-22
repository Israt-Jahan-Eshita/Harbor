"""Unit tests for bazar shortfall, safe substitutes, and monthly list (core/bazar.py)."""

from __future__ import annotations

from app.core.bazar import build_monthly_list, calculate_bazar_shortfall, find_safe_substitute
from app.core.types import (
    DietPresetData,
    IngredientData,
    MemberData,
    RecipeData,
    RecipeIngredientData,
    RuleContext,
    StockItemState,
)


def _bazar_ctx():
    ingredients = {
        "rui_fish": IngredientData(
            key="rui_fish", name_en="Rui Fish", name_bn="রুই মাছ", category="protein",
            allergen_tags=["fish"], potassium_level="medium", purine_level="medium",
            sodium_level="low", gi_level="low", season_months=[1, 11, 12], ref_price_bdt=380.0, ref_price_per=1000.0,
        ),
        "pangas_fish": IngredientData(
            key="pangas_fish", name_en="Pangas Fish", name_bn="পাঙাশ মাছ", category="protein",
            allergen_tags=["fish"], potassium_level="medium", purine_level="medium",
            sodium_level="low", gi_level="low", season_months=[1, 11, 12], ref_price_bdt=200.0, ref_price_per=1000.0,
        ),
        "hilsha_fish": IngredientData(
            key="hilsha_fish", name_en="Hilsa", name_bn="ইলিশ মাছ", category="protein",
            allergen_tags=["fish"], potassium_level="medium", purine_level="high",
            sodium_level="low", gi_level="low", season_months=[6, 7, 8], ref_price_bdt=1400.0, ref_price_per=1000.0,
        ),
        "lau": IngredientData(
            key="lau", name_en="Bottle Gourd", name_bn="লাউ", category="vegetable",
            potassium_level="low", purine_level="low", sodium_level="low", gi_level="low",
            season_months=[11, 12, 1], ref_price_bdt=60.0, ref_price_per=1000.0,
        ),
        "potol": IngredientData(
            key="potol", name_en="Pointed Gourd", name_bn="পটল", category="vegetable",
            potassium_level="low", purine_level="low", sodium_level="low", gi_level="low",
            season_months=[5, 6, 7], ref_price_bdt=70.0, ref_price_per=1000.0,
        ),
        "salt": IngredientData(
            key="salt", name_en="Salt", name_bn="লবণ", category="spice",
            potassium_level="low", purine_level="low", sodium_level="high", gi_level="low",
            season_months=list(range(1, 13)), ref_price_bdt=42.0, ref_price_per=1000.0,
        ),
    }
    presets = [
        DietPresetData(preset="low_purine", attr="purine_level", max_level="medium", split_allowed=False),
        DietPresetData(preset="low_sodium", attr="sodium_level", max_level="medium", split_allowed=True),
    ]
    ctx = RuleContext(ingredients=ingredients, diet_presets=presets)
    sub_groups = {
        "fish_protein": ["pangas_fish", "rui_fish", "hilsha_fish"],
        "vegetable_gourd": ["lau", "potol"],
    }
    return ctx, sub_groups


def test_shortfall_with_reserved_stock() -> None:
    plan = [{"ingredient_key": "lau", "qty": 1000.0}, {"ingredient_key": "salt", "qty": 50.0}]
    stock = {
        "lau": StockItemState(ingredient_key="lau", raw_qty=600.0, qty_base=600.0),
        "salt": StockItemState(ingredient_key="salt", raw_qty=100.0, qty_base=100.0),
    }
    reserved = {"lau": 200.0}  # Net available lau = 400 -> shortfall = 600
    shortfall = calculate_bazar_shortfall(plan, stock, reserved)
    assert shortfall == {"lau": 600.0}


def test_substitute_must_stay_safe_for_all_members() -> None:
    ctx, sub_groups = _bazar_ctx()
    fish_curry = RecipeData(
        id="r1", key="rui_lau", name_bn="রুই লাউ",
        ingredients=[
            RecipeIngredientData(ingredient_key="rui_fish", qty=400, unit="g"),
            RecipeIngredientData(ingredient_key="lau", qty=300, unit="g"),
            RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
        ],
        split_step_bn="লবণ দেওয়ার আগে",
        split_removes=["salt"],
    )
    members = [MemberData(id="m1", name="Member", diet_presets=["low_purine", "low_sodium"])]
    subs = find_safe_substitute("rui_fish", members, [fish_curry], ctx, sub_groups, current_month=11)
    sub_keys = [s["ingredient_key"] for s in subs]
    assert "pangas_fish" in sub_keys
    assert "hilsha_fish" not in sub_keys  # High purine violates low_purine -> must NOT be offered!


def test_monthly_list_budget_substitution_and_labels() -> None:
    ctx, sub_groups = _bazar_ctx()
    recipes = [
        RecipeData(
            id="r1", key="rui_potol", name_bn="রুই পটল", category="fish", servings_base=4,
            ingredients=[
                RecipeIngredientData(ingredient_key="rui_fish", qty=400, unit="g"),
                RecipeIngredientData(ingredient_key="potol", qty=400, unit="g"),
                RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
            ],
            split_step_bn="লবণ দেওয়ার আগে",
            split_removes=["salt"],
            taste_score=0.9,
        ),
    ]
    members = [MemberData(id="m1", name="Member", diet_presets=["low_sodium"])]
    res = build_monthly_list(
        members=members,
        recipes=recipes,
        context=ctx,
        stock_map={},
        month="2026-11",
        current_month=11,
        budget_bdt=800,
        substitution_groups=sub_groups,
    )
    assert res["price_label_bn"] == "আনুমানিক"
    assert len(res["items"]) > 0
    assert all(it["label_bn"] == "আনুমানিক" for it in res["items"])
    # Tight budget triggers safe substitution (rui_fish -> pangas_fish, potol -> lau) and/or drop flags
    assert any(it["substitute_used"] or it["dropped"] for it in res["items"])
