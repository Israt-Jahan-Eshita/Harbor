"""Unit tests for shared-pot household aggregation (core/shared_pot.py)."""

from __future__ import annotations

from datetime import date

from app.core.shared_pot import find_shared_pot_dishes
from app.core.types import (
    DietPresetData,
    GuestEventData,
    IngredientData,
    MemberData,
    RecipeData,
    RecipeIngredientData,
    RuleContext,
)


def _ctx() -> RuleContext:
    return RuleContext(
        ingredients={
            "lau": IngredientData(
                key="lau", name_en="Lau", name_bn="লাউ",
                potassium_level="low", purine_level="low", sodium_level="low", gi_level="low",
            ),
            "salt": IngredientData(
                key="salt", name_en="Salt", name_bn="লবণ",
                potassium_level="low", purine_level="low", sodium_level="high", gi_level="low",
            ),
            "beef": IngredientData(
                key="beef", name_en="Beef", name_bn="গরুর মাংস",
                potassium_level="medium", purine_level="high", sodium_level="low", gi_level="low",
                tags=["red_meat"],
            ),
            "chingri": IngredientData(
                key="chingri", name_en="Prawn", name_bn="চিংড়ি",
                allergen_tags=["prawn_shellfish"],
                potassium_level="medium", purine_level="high", sodium_level="medium", gi_level="low",
            ),
        },
        diet_presets=[
            DietPresetData(preset="low_sodium", attr="sodium_level", max_level="medium", split_allowed=True),
            DietPresetData(preset="low_purine", attr="purine_level", max_level="medium", split_allowed=False),
        ],
    )


def test_two_members_split_at_same_step_allowed() -> None:
    ctx = _ctx()
    recipe = RecipeData(
        id="r1", key="lau_bhaji", name_bn="লাউ ভাজি",
        ingredients=[
            RecipeIngredientData(ingredient_key="lau", qty=300, unit="g"),
            RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
        ],
        split_step_bn="লবণ দেওয়ার আগে",
        split_removes=["salt"],
    )
    members = [
        MemberData(id="m1", name="মা", diet_presets=["low_sodium"]),
        MemberData(id="m2", name="বাবা", diet_presets=["low_sodium"]),
        MemberData(id="m3", name="কেয়ারগিভার"),
    ]
    res = find_shared_pot_dishes(members, [recipe], ctx, date(2026, 11, 22), "dinner")
    assert len(res.candidates) == 1
    cand = res.candidates[0]
    assert cand.status == "SAFE_WITH_SPLIT"
    assert cand.split_for == ["মা", "বাবা"]
    assert cand.split_step_bn == "লবণ দেওয়ার আগে"


def test_member_needing_unprovided_split_step_is_excluded() -> None:
    ctx = _ctx()
    recipe = RecipeData(
        id="r1", key="lau_nosplit", name_bn="লাউ",
        ingredients=[
            RecipeIngredientData(ingredient_key="lau", qty=300, unit="g"),
            RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
        ],
        split_step_bn=None,
        split_removes=[],
    )
    members = [MemberData(id="m1", name="মা", diet_presets=["low_sodium"])]
    res = find_shared_pot_dishes(members, [recipe], ctx, date(2026, 11, 22), "dinner")
    assert res.candidates == []
    assert len(res.excluded) == 1
    assert "LOW_SODIUM_SODIUM" in res.excluded[0].reasons


def test_guest_allergy_and_member_away() -> None:
    ctx = _ctx()
    prawn_recipe = RecipeData(
        id="r_prawn", key="lau_chingri", name_bn="লাউ চিংড়ি",
        ingredients=[
            RecipeIngredientData(ingredient_key="lau", qty=300, unit="g"),
            RecipeIngredientData(ingredient_key="chingri", qty=150, unit="g"),
        ],
        split_step_bn="লবণ দেওয়ার আগে",
        split_removes=[],
    )
    beef_recipe = RecipeData(
        id="r_beef", key="gorur_bhuna", name_bn="গরুর ভুনা",
        ingredients=[
            RecipeIngredientData(ingredient_key="beef", qty=400, unit="g"),
        ],
        split_step_bn="লবণ দেওয়ার আগে",
        split_removes=[],
    )
    child_prawn = MemberData(id="m_child", name="আরিফ", allergies=["prawn_shellfish"])
    adult = MemberData(id="m_adult", name="সুমাইয়া")

    # When child is away and no guest has prawn allergy, prawn_recipe is safe
    res_away = find_shared_pot_dishes(
        [child_prawn, adult],
        [prawn_recipe, beef_recipe],
        ctx,
        date(2026, 11, 22),
        away_member_ids={"m_child"},
        guests=[GuestEventData(guest_count=2, restrictions=["no_beef"])],
    )
    cand_keys = {c.recipe.key for c in res_away.candidates}
    excl_map = {e.recipe.key: e.reasons for e in res_away.excluded}
    assert res_away.people_count == 3  # 1 present member + 2 guests
    assert "lau_chingri" in cand_keys
    assert "gorur_bhuna" in excl_map
    assert "GUEST_EXCLUDES_BEEF" in excl_map["gorur_bhuna"]

    # When guest has prawn allergy, prawn_recipe is excluded even if child is away
    res_guest_allergy = find_shared_pot_dishes(
        [child_prawn, adult],
        [prawn_recipe],
        ctx,
        date(2026, 11, 22),
        away_member_ids={"m_child"},
        guests=[GuestEventData(guest_count=1, restrictions=["prawn_allergy"])],
    )
    assert res_guest_allergy.candidates == []
    assert "PRAWN_ALLERGY" in res_guest_allergy.excluded[0].reasons
