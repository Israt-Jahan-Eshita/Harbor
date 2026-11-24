"""Unit tests for same-ingredient multi-member conflict resolution (core/shared_pot.py & rules.py)."""

from __future__ import annotations

from datetime import date
from itertools import permutations

from app.core.rules import check_dish_safe
from app.core.shared_pot import evaluate_multi_member_conflict, find_shared_pot_dishes
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


def _conflict_ctx() -> RuleContext:
    ingredients = {
        "lau": IngredientData(
            key="lau", name_en="Bottle Gourd", name_bn="লাউ", category="vegetable",
            potassium_level="low", purine_level="low", sodium_level="low", gi_level="low",
            season_months=[10, 11, 12, 1], ref_price_bdt=45.0, ref_price_per=1000.0,
        ),
        "kancha_pepe": IngredientData(
            key="kancha_pepe", name_en="Raw Papaya", name_bn="কাঁচা পেঁপে", category="vegetable",
            potassium_level="low", purine_level="low", sodium_level="low", gi_level="low",
            season_months=[10, 11, 12], ref_price_bdt=40.0, ref_price_per=1000.0,
        ),
        "potato": IngredientData(
            key="potato", name_en="Potato", name_bn="আলু", category="vegetable",
            potassium_level="high", purine_level="low", sodium_level="low", gi_level="high",
            season_months=[1, 2, 11, 12], ref_price_bdt=55.0, ref_price_per=1000.0,
        ),
        "fulkopi": IngredientData(
            key="fulkopi", name_en="Cauliflower", name_bn="ফুলকপি", category="vegetable",
            potassium_level="medium", purine_level="medium", sodium_level="low", gi_level="low",
            season_months=[11, 12, 1, 2], ref_price_bdt=60.0, ref_price_per=1000.0,
        ),
        "salt": IngredientData(
            key="salt", name_en="Salt", name_bn="লবণ", category="spice",
            potassium_level="low", purine_level="low", sodium_level="high", gi_level="low",
            tags=["splittable"], season_months=list(range(1, 13)),
        ),
        "chingri": IngredientData(
            key="chingri", name_en="Prawn", name_bn="চিংড়ি", category="fish",
            allergen_tags=["prawn_shellfish"],
            potassium_level="medium", purine_level="high", sodium_level="medium", gi_level="low",
            season_months=list(range(1, 13)), ref_price_bdt=750.0, ref_price_per=1000.0,
        ),
        "rui_fish": IngredientData(
            key="rui_fish", name_en="Rui Fish", name_bn="রুই মাছ", category="fish",
            allergen_tags=["fish"],
            potassium_level="medium", purine_level="medium", sodium_level="low", gi_level="low",
            season_months=list(range(1, 13)), ref_price_bdt=360.0, ref_price_per=1000.0,
        ),
    }
    rules = [
        DrugFoodRuleData(
            rule_id="ACE_INHIBITOR_HIGH_POTASSIUM",
            drug_class="ace_inhibitor",
            ingredient_attr="potassium_level",
            attr_value="high",
        ),
    ]
    presets = [
        DietPresetData(preset="low_gi", attr="gi_level", max_level="medium", split_allowed=False),
        DietPresetData(preset="low_sodium", attr="sodium_level", max_level="medium", split_allowed=True),
        DietPresetData(preset="low_purine", attr="purine_level", max_level="medium", split_allowed=False),
        DietPresetData(preset="low_potassium", attr="potassium_level", max_level="medium", split_allowed=False),
    ]
    return RuleContext(ingredients=ingredients, drug_food_rules=rules, diet_presets=presets)


def test_severity_escalation_split_vs_block_on_same_ingredient() -> None:
    """Member A allows salt via split; Member B excludes salt strictly -> BLOCKED wins."""
    ctx = _conflict_ctx()
    recipe = RecipeData(
        id="r1",
        key="lau_bhaji",
        name_bn="লাউ ভাজি",
        name_en="Bottle Gourd Stir Fry",
        ingredients=[
            RecipeIngredientData(ingredient_key="lau", qty=300, unit="g"),
            RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
        ],
        split_step_bn="লবণ দেওয়ার আগে",
        split_removes=["salt"],
    )
    m_split = MemberData(id="m1", name="মা", diet_presets=["low_sodium"])
    m_block = MemberData(id="m2", name="রোগী-বি", excluded_ingredient_keys=["salt"])

    res = find_shared_pot_dishes([m_split, m_block], [recipe], ctx, date(2026, 11, 24))
    assert res.candidates == []
    assert len(res.excluded) == 1
    excl = res.excluded[0]
    assert set(excl.reasons) == {"GUEST_EXCLUDES_SALT"}

    salt_conflicts = [c for c in excl.ingredient_conflicts if c.ingredient_key == "salt"]
    assert len(salt_conflicts) == 1
    assert salt_conflicts[0].conflict_type == "MULTI_RULE_COLLISION"
    assert salt_conflicts[0].resolution == "BLOCKED_MOST_RESTRICTIVE_WINS"
    assert salt_conflicts[0].winning_status == "BLOCKED"
    assert set(salt_conflicts[0].winning_reasons) == {"GUEST_EXCLUDES_SALT", "LOW_SODIUM_SODIUM"}


def test_unverified_fail_closed_beats_blocked_and_split() -> None:
    """Any unmapped medicine forces UNVERIFIED_FAIL_CLOSED regardless of other members."""
    ctx = _conflict_ctx()
    recipe = RecipeData(
        id="r_pot",
        key="alu_torkari",
        name_bn="আলুর তরকারি",
        name_en="Potato Curry",
        ingredients=[
            RecipeIngredientData(ingredient_key="potato", qty=250, unit="g"),
            RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
        ],
        split_step_bn="লবণ দেওয়ার আগে",
        split_removes=["salt"],
    )
    m_unmapped = MemberData(
        id="m1",
        name="দাদা",
        medicines=[
            MedicineData(name_as_written="MysteryHerb", drug_class=None, verified_by_caregiver=True, active=True)
        ],
    )
    m_blocked = MemberData(id="m2", name="বাবা", diet_presets=["low_potassium"])
    m_split = MemberData(id="m3", name="মা", diet_presets=["low_sodium"])

    res = evaluate_multi_member_conflict([m_split, m_blocked, m_unmapped], recipe, ctx)
    assert res["household_status"] == "EXCLUDED"
    assert res["order_invariant"] is True
    assert "UNMAPPED_MEDICINE" in res["reasons"]
    potato_conf = next(c for c in res["ingredient_conflicts"] if c["ingredient_key"] == "potato")
    assert potato_conf["conflict_type"] == "UNVERIFIED_FAIL_CLOSED"
    assert potato_conf["winning_status"] == "UNVERIFIED"


def test_multi_rule_collision_and_all_permutations_commutative() -> None:
    """Two members trigger different rules on potato; permutation order never changes outcome."""
    ctx = _conflict_ctx()
    recipe = RecipeData(
        id="r_alu",
        key="alu_fulkopi_jhol",
        name_bn="আলু ফুলকপির ঝোল",
        name_en="Potato Cauliflower Curry",
        ingredients=[
            RecipeIngredientData(ingredient_key="potato", qty=200, unit="g"),
            RecipeIngredientData(ingredient_key="fulkopi", qty=250, unit="g"),
            RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
        ],
        split_step_bn="লবণ দেওয়ার আগে",
        split_removes=["salt"],
    )
    baba = MemberData(id="m1", name="বাবা", diet_presets=["low_potassium"])
    ma = MemberData(
        id="m2",
        name="মা",
        diet_presets=["low_gi", "low_sodium"],
        medicines=[
            MedicineData(
                name_as_written="Enalapril",
                drug_class="ace_inhibitor",
                verified_by_caregiver=True,
                active=True,
            )
        ],
    )
    arif = MemberData(id="m3", name="আরিফ", allergies=["prawn_shellfish"])

    sub_groups = {"vegetable_gourd": ["lau", "kancha_pepe", "potato"]}
    baseline_sig = None
    for perm in permutations([baba, ma, arif]):
        out = evaluate_multi_member_conflict(list(perm), recipe, ctx, substitution_groups=sub_groups)
        assert out["household_status"] == "EXCLUDED"
        assert out["order_invariant"] is True
        sig = (
            out["household_status"],
            tuple(out["reasons"]),
            tuple(
                (
                    c["ingredient_key"],
                    c["conflict_type"],
                    c["winning_status"],
                    tuple(c["winning_reasons"]),
                    tuple((p["member_id"], p["status"]) for p in c["positions"]),
                )
                for c in out["ingredient_conflicts"]
            ),
        )
        if baseline_sig is None:
            baseline_sig = sig
        else:
            assert sig == baseline_sig

    assert baseline_sig is not None
    out0 = evaluate_multi_member_conflict([baba, ma, arif], recipe, ctx, substitution_groups=sub_groups)
    potato_conf = next(c for c in out0["ingredient_conflicts"] if c["ingredient_key"] == "potato")
    assert potato_conf["conflict_type"] == "MULTI_RULE_COLLISION"
    assert set(potato_conf["winning_reasons"]) >= {
        "LOW_POTASSIUM_POTASSIUM",
        "LOW_GI_GI",
        "ACE_INHIBITOR_HIGH_POTASSIUM",
    }
    sub_keys = [s["ingredient_key"] for s in potato_conf["safe_substitutes"]]
    assert "lau" in sub_keys


def test_convergent_split_and_incompatible_split() -> None:
    """Convergent salt split keeps dish safe; unprovided split step excludes safely."""
    ctx = _conflict_ctx()
    dal = RecipeData(
        id="r_dal",
        key="lau_bhaji",
        name_bn="লাউ ভাজি",
        ingredients=[
            RecipeIngredientData(ingredient_key="lau", qty=300, unit="g"),
            RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
        ],
        split_step_bn="লবণ দেওয়ার আগে",
        split_removes=["salt"],
    )
    m1 = MemberData(id="m1", name="মা", diet_presets=["low_sodium"])
    m2 = MemberData(id="m2", name="চাচি", diet_presets=["low_sodium"])

    out = evaluate_multi_member_conflict([m1, m2], dal, ctx)
    assert out["household_status"] == "SAFE_WITH_SPLIT"
    assert set(out["split_for"]) == {"মা", "চাচি"}
    salt_conf = next(c for c in out["ingredient_conflicts"] if c["ingredient_key"] == "salt")
    assert salt_conf["conflict_type"] == "CONVERGENT_SPLIT"
    assert salt_conf["resolution"] == "SAFE_WITH_SINGLE_SPLIT"

    # Incompatible split (split_removes missing salt)
    bad_dal = dal.model_copy(update={"split_removes": ["green_chilli"]})
    out_bad = evaluate_multi_member_conflict([m1, m2], bad_dal, ctx)
    assert out_bad["household_status"] == "EXCLUDED"


def test_zero_safe_dish_deadlock_recovery() -> None:
    """When competing restrictions block every recipe, engine emits 0 candidates and deadlock guidance."""
    ctx = _conflict_ctx()
    r1 = RecipeData(
        id="r1",
        key="alu_jhol",
        name_bn="আলুর ঝোল",
        ingredients=[RecipeIngredientData(ingredient_key="potato", qty=300, unit="g")],
    )
    r2 = RecipeData(
        id="r2",
        key="lau_chingri",
        name_bn="লাউ চিংড়ি",
        ingredients=[
            RecipeIngredientData(ingredient_key="lau", qty=300, unit="g"),
            RecipeIngredientData(ingredient_key="chingri", qty=150, unit="g"),
        ],
    )
    m1 = MemberData(id="m1", name="বাবা", diet_presets=["low_potassium"])
    m2 = MemberData(id="m2", name="আরিফ", allergies=["prawn_shellfish"])

    res = find_shared_pot_dishes([m1, m2], [r1, r2], ctx, date(2026, 11, 24))
    assert res.candidates == []
    assert len(res.excluded) == 2
    assert res.conflict_summary is not None
    assert res.conflict_summary.zero_safe_deadlock is True
    assert res.conflict_summary.deadlock_recovery_bn
    assert res.conflict_summary.deadlock_recovery_en

    # Also verify check_dish_safe records per-ingredient verdicts
    v = check_dish_safe(m2, r2, ctx)
    assert v.ingredient_verdicts["chingri"].status == "BLOCKED"
    assert v.ingredient_verdicts["lau"].status == "SAFE_DIRECT"

