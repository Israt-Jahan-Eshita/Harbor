"""Unit tests for deterministic food-safety rule engine (core/rules.py)."""

from __future__ import annotations

from app.core.rules import check_dish_safe
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


def _base_context() -> RuleContext:
    ingredients = {
        "lau": IngredientData(
            key="lau", name_en="Bottle Gourd", name_bn="লাউ",
            potassium_level="low", purine_level="low", sodium_level="low", gi_level="low",
        ),
        "palong_shak": IngredientData(
            key="palong_shak", name_en="Spinach", name_bn="পালং শাক",
            potassium_level="high", purine_level="medium", sodium_level="low", gi_level="low",
            tags=["leafy"],
        ),
        "chingri": IngredientData(
            key="chingri", name_en="Prawn", name_bn="চিংড়ি",
            allergen_tags=["prawn_shellfish"],
            potassium_level="medium", purine_level="high", sodium_level="medium", gi_level="low",
        ),
        "grapefruit": IngredientData(
            key="grapefruit", name_en="Pomelo", name_bn="জাম্বুরা",
            potassium_level="medium", purine_level="low", sodium_level="low", gi_level="low",
            tags=["grapefruit_like"],
        ),
        "salt": IngredientData(
            key="salt", name_en="Salt", name_bn="লবণ",
            potassium_level="low", purine_level="low", sodium_level="high", gi_level="low",
            tags=["splittable"],
        ),
        "potato": IngredientData(
            key="potato", name_en="Potato", name_bn="আলু",
            potassium_level="high", purine_level="low", sodium_level="low", gi_level="high",
        ),
        "honey": IngredientData(
            key="honey", name_en="Honey", name_bn="মধু",
            potassium_level="low", purine_level="low", sodium_level="low", gi_level="high",
            tags=["honey"],
        ),
        "peanut": IngredientData(
            key="peanut", name_en="Peanut", name_bn="চিনাবাদাম",
            allergen_tags=["peanut"],
            potassium_level="medium", purine_level="low", sodium_level="low", gi_level="low",
            tags=["whole_nuts"],
        ),
    }
    rules = [
        DrugFoodRuleData(
            rule_id="ACE_INHIBITOR_HIGH_POTASSIUM",
            drug_class="ace_inhibitor",
            ingredient_attr="potassium_level",
            attr_value="high",
        ),
        DrugFoodRuleData(
            rule_id="ARB_HIGH_POTASSIUM",
            drug_class="arb",
            ingredient_attr="potassium_level",
            attr_value="high",
        ),
        DrugFoodRuleData(
            rule_id="K_SPARING_DIURETIC_HIGH_POTASSIUM",
            drug_class="k_sparing_diuretic",
            ingredient_attr="potassium_level",
            attr_value="high",
        ),
        DrugFoodRuleData(
            rule_id="STATIN_GRAPEFRUIT",
            drug_class="statin_cyp3a4",
            ingredient_attr="tag",
            attr_value="grapefruit_like",
        ),
    ]
    presets = [
        DietPresetData(preset="low_gi", attr="gi_level", max_level="medium", split_allowed=False),
        DietPresetData(preset="low_sodium", attr="sodium_level", max_level="medium", split_allowed=True),
        DietPresetData(preset="low_purine", attr="purine_level", max_level="medium", split_allowed=False),
        DietPresetData(preset="low_potassium", attr="potassium_level", max_level="medium", split_allowed=False),
    ]
    return RuleContext(ingredients=ingredients, drug_food_rules=rules, diet_presets=presets)


def test_allergen_blocks_prawn_and_variants() -> None:
    ctx = _base_context()
    recipe = RecipeData(
        id="r1", key="lau_chingri", name_bn="লাউ চিংড়ি",
        ingredients=[
            RecipeIngredientData(ingredient_key="lau", qty=300, unit="g"),
            RecipeIngredientData(ingredient_key="chingri", qty=150, unit="g"),
        ],
    )
    for raw_allergy in ("prawn_shellfish", "Prawn", "চিংড়ি"):
        member = MemberData(id="m1", name="Child", allergies=[raw_allergy])
        res = check_dish_safe(member, recipe, ctx)
        assert res.status == "BLOCKED"
        assert "PRAWN_ALLERGY" in res.reasons


def test_drug_food_rules_all_four_classes() -> None:
    ctx = _base_context()
    spinach_dish = RecipeData(
        id="r2", key="palong_shak_bhaji", name_bn="পালং শাক",
        ingredients=[RecipeIngredientData(ingredient_key="palong_shak", qty=300, unit="g")],
    )
    for drug_class, expected_rule in (
        ("ace_inhibitor", "ACE_INHIBITOR_HIGH_POTASSIUM"),
        ("arb", "ARB_HIGH_POTASSIUM"),
        ("k_sparing_diuretic", "K_SPARING_DIURETIC_HIGH_POTASSIUM"),
    ):
        member = MemberData(
            id="m", name="Patient",
            medicines=[
                MedicineData(
                    name_as_written="Med",
                    drug_class=drug_class,
                    verified_by_caregiver=True,
                    active=True,
                )
            ],
        )
        res = check_dish_safe(member, spinach_dish, ctx)
        assert res.status == "BLOCKED"
        assert expected_rule in res.reasons

    pomelo_dish = RecipeData(
        id="r3", key="jambura", name_bn="জাম্বুরা",
        ingredients=[RecipeIngredientData(ingredient_key="grapefruit", qty=1, unit="piece")],
    )
    statin_member = MemberData(
        id="m4", name="Patient",
        medicines=[
            MedicineData(
                name_as_written="Atorvastatin",
                drug_class="statin_cyp3a4",
                verified_by_caregiver=True,
                active=True,
            )
        ],
    )
    res_statin = check_dish_safe(statin_member, pomelo_dish, ctx)
    assert res_statin.status == "BLOCKED"
    assert "STATIN_GRAPEFRUIT" in res_statin.reasons


def test_unconfirmed_medicine_is_not_auto_activated() -> None:
    ctx = _base_context()
    spinach_dish = RecipeData(
        id="r2", key="palong_shak_bhaji", name_bn="পালং শাক",
        ingredients=[RecipeIngredientData(ingredient_key="palong_shak", qty=300, unit="g")],
    )
    member = MemberData(
        id="m", name="Patient",
        medicines=[
            MedicineData(
                name_as_written="Enalapril",
                drug_class="ace_inhibitor",
                verified_by_caregiver=False,
                active=True,
            )
        ],
    )
    res = check_dish_safe(member, spinach_dish, ctx)
    assert res.status == "SAFE_DIRECT"
    assert any("unconfirmed" in line for line in res.trace)


def test_unverified_unknown_ingredient_and_unmapped_medicine() -> None:
    ctx = _base_context()
    unknown_recipe = RecipeData(
        id="r_unk", key="mystery", name_bn="অজানা",
        ingredients=[RecipeIngredientData(ingredient_key="not_in_db", qty=100, unit="g")],
    )
    res_ing = check_dish_safe(MemberData(id="m1", name="Adult"), unknown_recipe, ctx)
    assert res_ing.status == "UNVERIFIED"
    assert "UNKNOWN_INGREDIENT" in res_ing.reasons

    safe_recipe = RecipeData(
        id="r_safe", key="lau_only", name_bn="লাউ",
        ingredients=[RecipeIngredientData(ingredient_key="lau", qty=100, unit="g")],
    )
    unmapped_member = MemberData(
        id="m2", name="Patient",
        medicines=[
            MedicineData(
                name_as_written="MysteryMed",
                drug_class=None,
                verified_by_caregiver=True,
                active=True,
            )
        ],
    )
    res_med = check_dish_safe(unmapped_member, safe_recipe, ctx)
    assert res_med.status == "UNVERIFIED"
    assert "UNMAPPED_MEDICINE" in res_med.reasons


def test_none_modelled_medicine_does_not_trigger_unverified() -> None:
    ctx = _base_context()
    safe_recipe = RecipeData(
        id="r_safe", key="lau_only", name_bn="লাউ",
        ingredients=[RecipeIngredientData(ingredient_key="lau", qty=100, unit="g")],
    )
    member = MemberData(
        id="m", name="Patient",
        medicines=[
            MedicineData(
                name_as_written="Vitamin D",
                drug_class="none_modelled",
                verified_by_caregiver=True,
                active=True,
            )
        ],
    )
    res = check_dish_safe(member, safe_recipe, ctx)
    assert res.status == "SAFE_DIRECT"


def test_diet_presets_splittable_vs_blocked_and_age_profiles() -> None:
    ctx = _base_context()

    # Splittable salt -> SAFE_WITH_SPLIT
    splittable_recipe = RecipeData(
        id="r_split", key="lau_salt", name_bn="লাউ",
        ingredients=[
            RecipeIngredientData(ingredient_key="lau", qty=200, unit="g"),
            RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
        ],
        split_step_bn="লবণ দেওয়ার আগে",
        split_removes=["salt"],
    )
    low_na_member = MemberData(id="m_na", name="Mother", diet_presets=["low_sodium"])
    res_split = check_dish_safe(low_na_member, splittable_recipe, ctx)
    assert res_split.status == "SAFE_WITH_SPLIT"
    assert "LOW_SODIUM_SODIUM" in res_split.reasons

    # Non-splittable (no split_step_bn) -> BLOCKED
    no_split_recipe = RecipeData(
        id="r_nosplit", key="lau_salt_mixed", name_bn="লাউ ভর্তা",
        ingredients=[
            RecipeIngredientData(ingredient_key="lau", qty=200, unit="g"),
            RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
        ],
        split_step_bn=None,
        split_removes=[],
    )
    res_blocked = check_dish_safe(low_na_member, no_split_recipe, ctx)
    assert res_blocked.status == "BLOCKED"
    assert "LOW_SODIUM_SODIUM" in res_blocked.reasons

    # Multiple reasons collected (potato violates low_potassium AND low_gi)
    alu_recipe = RecipeData(
        id="r_alu", key="alu_curry", name_bn="আলু",
        ingredients=[RecipeIngredientData(ingredient_key="potato", qty=200, unit="g")],
    )
    multi_member = MemberData(
        id="m_multi", name="Both",
        diet_presets=["low_potassium", "low_gi"],
        medicines=[
            MedicineData(name_as_written="Enalapril", drug_class="ace_inhibitor", verified_by_caregiver=True),
            MedicineData(name_as_written="Losartan", drug_class="arb", verified_by_caregiver=True),
        ],
    )
    res_multi = check_dish_safe(multi_member, alu_recipe, ctx)
    assert res_multi.status == "BLOCKED"
    assert set(res_multi.reasons) >= {
        "ACE_INHIBITOR_HIGH_POTASSIUM",
        "ARB_HIGH_POTASSIUM",
        "LOW_POTASSIUM_POTASSIUM",
        "LOW_GI_GI",
    }

    # Age profiles
    honey_recipe = RecipeData(
        id="r_h", key="honey_item", name_bn="মধু",
        ingredients=[RecipeIngredientData(ingredient_key="honey", qty=10, unit="ml")],
    )
    infant = MemberData(id="baby", name="Baby", age_group="child_under_1")
    res_baby = check_dish_safe(infant, honey_recipe, ctx)
    assert res_baby.status == "BLOCKED"
    assert "CHILD_UNDER_1_HONEY" in res_baby.reasons

    nut_recipe = RecipeData(
        id="r_n", key="nut_item", name_bn="বাদাম",
        ingredients=[RecipeIngredientData(ingredient_key="peanut", qty=30, unit="g")],
    )
    toddler = MemberData(id="tod", name="Toddler", age_group="child_under_5")
    res_toddler = check_dish_safe(toddler, nut_recipe, ctx)
    assert res_toddler.status == "BLOCKED"
    assert "CHILD_UNDER_5_WHOLE_NUTS" in res_toddler.reasons
