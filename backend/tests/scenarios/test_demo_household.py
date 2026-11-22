"""End-to-end pure-core scenario test matching SPEC section 9.7 Demo Household."""

from __future__ import annotations

from datetime import date

from app.core.shared_pot import find_shared_pot_dishes
from app.core.types import (
    DietPresetData,
    DrugFoodRuleData,
    IngredientData,
    MedicineData,
    MemberData,
    RecipeData,
    RecipeIngredientData,
    RuleContext,
)
from app.seed.validate_seed import load_json


def _load_seed_context_and_recipes() -> tuple[RuleContext, list[RecipeData]]:
    ingredients_raw = load_json("ingredients.json")["ingredients"]
    rules_raw = load_json("rules.json")["rules"]
    presets_raw = load_json("diet_presets.json")["presets"]
    recipes_raw = load_json("recipes.json")["recipes"]

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
    return ctx, recipes


def _demo_members() -> list[MemberData]:
    demo = load_json("demo_household.json")["members"]
    members: list[MemberData] = []
    for idx, m in enumerate(demo):
        meds = [MedicineData(id=f"med-{idx}-{j}", **med) for j, med in enumerate(m.get("medicines", []))]
        members.append(
            MemberData(
                id=f"member-{idx}",
                name=m["name"],
                role=m["role"],
                age_group=m["age_group"],
                conditions=m["conditions"],
                allergies=m["allergies"],
                diet_presets=m["diet_presets"],
                medicines=meds,
            )
        )
    return members


def test_spec_9_7_demo_household_dinner() -> None:
    ctx, recipes = _load_seed_context_and_recipes()
    members = _demo_members()

    result = find_shared_pot_dishes(members, recipes, ctx, date(2026, 11, 22), meal="dinner")

    candidates_by_key = {c.recipe.key: c for c in result.candidates}
    excluded_by_key = {e.recipe.key: e for e in result.excluded}

    # Expected exclusions from SPEC §9.7
    assert "lau_chingri" in excluded_by_key
    assert "PRAWN_ALLERGY" in excluded_by_key["lau_chingri"].reasons

    assert "palong_shak_bhaji" in excluded_by_key
    assert "ACE_INHIBITOR_HIGH_POTASSIUM" in excluded_by_key["palong_shak_bhaji"].reasons
    assert "LOW_POTASSIUM_POTASSIUM" in excluded_by_key["palong_shak_bhaji"].reasons

    # Expected shared-pot split dishes from SPEC §9.7
    for key in ("lau_masoor_dal", "rui_macher_jhol", "mishti_shobji"):
        assert key in candidates_by_key
        cand = candidates_by_key[key]
        assert cand.status == "SAFE_WITH_SPLIT"
        assert cand.split_for == ["মা"]
        assert cand.split_step_bn == "লবণ ও কাঁচামরিচ দেওয়ার আগে"
