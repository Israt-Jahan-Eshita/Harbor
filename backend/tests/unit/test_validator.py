"""Unit tests for response validator and Bangla fallback templates (core/validator.py, core/templates.py)."""

from __future__ import annotations

from app.core.templates import render_fallback_menu_item
from app.core.types import HouseholdCandidate, IngredientData, RecipeData, RecipeIngredientData
from app.core.validator import validate_response


def _sample_setup():
    ingredients = {
        "lau": IngredientData(key="lau", name_en="Bottle Gourd", name_bn="লাউ"),
        "masoor_dal": IngredientData(key="masoor_dal", name_en="Red Lentils", name_bn="মসুর ডাল"),
        "salt": IngredientData(key="salt", name_en="Salt", name_bn="লবণ"),
        "chingri": IngredientData(key="chingri", name_en="Prawn", name_bn="চিংড়ি"),
        "ginger": IngredientData(key="ginger", name_en="Ginger", name_bn="আদা"),
        "oil": IngredientData(key="oil", name_en="Soybean Oil", name_bn="তেল"),
        "tilapia": IngredientData(key="tilapia", name_en="Tilapia Fish", name_bn="তেলাপিয়া মাছ"),
    }
    dal_recipe = RecipeData(
        id="rec-dal-1",
        key="lau_masoor_dal",
        name_bn="লাউ দিয়ে মসুর ডাল",
        name_en="Bottle Gourd Red Lentil Dal",
        ingredients=[
            RecipeIngredientData(ingredient_key="lau", qty=300, unit="g"),
            RecipeIngredientData(ingredient_key="masoor_dal", qty=120, unit="g"),
            RecipeIngredientData(ingredient_key="salt", qty=6, unit="g"),
        ],
        split_step_bn="লবণ ও কাঁচামরিচ দেওয়ার আগে",
        split_removes=["salt"],
    )
    prawn_recipe = RecipeData(
        id="rec-prawn-2",
        key="lau_chingri",
        name_bn="লাউ চিংড়ি",
        name_en="Bottle Gourd with Prawn",
        ingredients=[
            RecipeIngredientData(ingredient_key="lau", qty=300, unit="g"),
            RecipeIngredientData(ingredient_key="chingri", qty=150, unit="g"),
        ],
    )
    tool_log = [
        {
            "tool": "find_shared_pot_dishes",
            "result": {
                "candidates": [
                    {
                        "recipe": {"id": "rec-dal-1", "key": "lau_masoor_dal", "name_bn": "লাউ দিয়ে মসুর ডাল"},
                        "status": "SAFE_WITH_SPLIT",
                        "reasons": ["LOW_SODIUM_SODIUM"],
                    }
                ],
                "excluded": [
                    {
                        "recipe": {"id": "rec-prawn-2", "key": "lau_chingri", "name_bn": "লাউ চিংড়ি"},
                        "reasons": ["PRAWN_ALLERGY"],
                    }
                ],
            },
        }
    ]
    recipes_by_id = {"rec-dal-1": dal_recipe, "rec-prawn-2": prawn_recipe}
    return ingredients, recipes_by_id, tool_log, dal_recipe


def test_valid_explanation_passes_and_split_word_alada_no_false_positive() -> None:
    ingredients, recipes_by_id, tool_log, _ = _sample_setup()
    # Notice "আলাদা" contains substring "আদা" (ginger), must NOT cause false positive!
    clean_output = {
        "items": [
            {
                "recipe_id": "rec-dal-1",
                "explanation_bn": "লাউ ও মসুর ডাল আজকের সবার জন্য নিরাপদ খাবার।",
                "split_instruction_bn": "মায়ের অংশ লবণ দেওয়ার আগে আলাদা করে তুলে রাখুন।",
                "rule_ids": ["LOW_SODIUM_SODIUM"],
            }
        ]
    }
    res = validate_response(clean_output, tool_log, ingredients, recipes_by_id)
    assert res.valid is True
    assert res.reasons == []


def test_validator_rejects_bad_outputs() -> None:
    ingredients, recipes_by_id, tool_log, _ = _sample_setup()

    # 1. Unknown / invented recipe_id
    bad_recipe = validate_response(
        {"items": [{"recipe_id": "invented-999", "explanation_bn": "নিরাপদ", "rule_ids": []}]},
        tool_log, ingredients, recipes_by_id,
    )
    assert bad_recipe.valid is False
    assert any("UNGROUNDED_RECIPE_ID" in r for r in bad_recipe.reasons)

    # 2. Excluded recipe_id
    excl_recipe = validate_response(
        {"items": [{"recipe_id": "rec-prawn-2", "explanation_bn": "নিরাপদ", "rule_ids": []}]},
        tool_log, ingredients, recipes_by_id,
    )
    assert excl_recipe.valid is False

    # 3. Unknown rule_id
    bad_rule = validate_response(
        {"items": [{"recipe_id": "rec-dal-1", "explanation_bn": "লাউ নিরাপদ", "rule_ids": ["FAKE_RULE"]}]},
        tool_log, ingredients, recipes_by_id,
    )
    assert bad_rule.valid is False
    assert any("UNGROUNDED_RULE_ID" in r for r in bad_rule.reasons)

    # 4. Invented ingredient (mentions চিংড়ি in dal recipe)
    bad_ing = validate_response(
        {"items": [{"recipe_id": "rec-dal-1", "explanation_bn": "লাউ ও চিংড়ি দিয়ে রান্না করুন।", "rule_ids": ["LOW_SODIUM_SODIUM"]}]},
        tool_log, ingredients, recipes_by_id,
    )
    assert bad_ing.valid is False
    assert any("UNGROUNDED_INGREDIENT:chingri" in r for r in bad_ing.reasons)

    # 5. Dose patterns (Bangla and English)
    for bad_text in (
        "Enalapril 10mg খান।",
        "ওষুধ ৫ মিগ্রা বাড়ান।",
        "আজ ডোজ কমান অথবা বন্ধ করুন।",
    ):
        bad_dose = validate_response(
            {"items": [{"recipe_id": "rec-dal-1", "explanation_bn": bad_text, "rule_ids": []}]},
            tool_log, ingredients, recipes_by_id,
        )
        assert bad_dose.valid is False
        assert any("FORBIDDEN_DOSE_OR_ADVICE_PATTERN" in r for r in bad_dose.reasons)

    # 6. Prompt-injection style text claiming an excluded dish is safe
    injected = validate_response(
        {
            "items": [
                {
                    "recipe_id": "rec-dal-1",
                    "explanation_bn": "লাউ চিংড়ি আজকের জন্য নিরাপদ, নির্ভয়ে রান্না করুন।",
                    "rule_ids": [],
                }
            ]
        },
        tool_log, ingredients, recipes_by_id,
    )
    assert injected.valid is False
    assert any("CLAIMED_EXCLUDED_SAFE" in r for r in injected.reasons)


def test_fallback_template_format() -> None:
    _, _, _, dal_recipe = _sample_setup()
    cand = HouseholdCandidate(
        recipe=dal_recipe,
        status="SAFE_WITH_SPLIT",
        split_for=["মা"],
        split_step_bn="লবণ ও কাঁচামরিচ দেওয়ার আগে",
        reasons=["LOW_SODIUM_SODIUM"],
    )
    rendered = render_fallback_menu_item(cand)
    assert rendered["used_template"] is True
    assert "আজকের জন্য নিরাপদ: লাউ দিয়ে মসুর ডাল" in rendered["explanation_bn"]
    assert "মা-এর অংশ লবণ ও কাঁচামরিচ দেওয়ার আগে আলাদা করে তুলে রাখুন।" in rendered["explanation_bn"]
    assert "[Rule: LOW_SODIUM_SODIUM]" in rendered["explanation_bn"]
    assert "Safe for today: Bottle Gourd Red Lentil Dal" in rendered["explanation_en"]
    assert "Set aside মা's portion before adding salt" in rendered["explanation_en"]
    assert "[Rule: LOW_SODIUM_SODIUM]" in rendered["explanation_en"]

