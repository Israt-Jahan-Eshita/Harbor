"""Validate prototype seed JSON integrity before loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SEED_DIR = Path(__file__).resolve().parent
VALID_LEVELS = {"low", "medium", "high"}
VALID_UNITS = {"g", "ml", "piece"}
REQUIRED_DISCLAIMER_SUBSTR = "Prototype data compiled from general nutrition guidance and pharmacology references. Not clinically reviewed."

SEED_FILES = [
    "drug_class_map.json",
    "rules.json",
    "diet_presets.json",
    "ingredients.json",
    "aliases.json",
    "prices.json",
    "substitution_groups.json",
    "recipes.json",
    "demo_household.json",
]


def load_json(filename: str) -> dict[str, Any]:
    path = SEED_DIR / filename
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_all_seeds() -> dict[str, Any]:
    """Validate cross-references, metadata disclaimers, and schema fields across all seed files."""
    errors: list[str] = []
    data: dict[str, dict[str, Any]] = {}

    for fname in SEED_FILES:
        payload = load_json(fname)
        data[fname] = payload
        meta = payload.get("_meta", {})
        disclaimer = str(meta.get("disclaimer", ""))
        if REQUIRED_DISCLAIMER_SUBSTR not in disclaimer:
            errors.append(f"{fname}: missing required prototype disclaimer in _meta.disclaimer")

    # Drug class map
    drug_classes = set(data["drug_class_map.json"].get("classes", {}).keys())
    if not {"ace_inhibitor", "arb", "k_sparing_diuretic", "statin_cyp3a4", "none_modelled"}.issubset(drug_classes):
        errors.append("drug_class_map.json: missing required seed drug classes")

    # Drug-food rules
    for rule in data["rules.json"].get("rules", []):
        if rule.get("drug_class") not in drug_classes:
            errors.append(f"rules.json: unknown drug_class {rule.get('drug_class')} in rule {rule.get('rule_id')}")

    # Diet presets
    for preset in data["diet_presets.json"].get("presets", []):
        if preset.get("max_level") not in VALID_LEVELS:
            errors.append(f"diet_presets.json: invalid max_level {preset.get('max_level')}")

    # Ingredients
    ingredients_by_key: dict[str, dict[str, Any]] = {}
    for ing in data["ingredients.json"].get("ingredients", []):
        key = ing.get("key")
        if not key:
            errors.append("ingredients.json: ingredient missing key")
            continue
        if key in ingredients_by_key:
            errors.append(f"ingredients.json: duplicate key {key}")
        ingredients_by_key[key] = ing
        for attr in ("potassium_level", "purine_level", "sodium_level", "gi_level"):
            if ing.get(attr) not in VALID_LEVELS:
                errors.append(f"ingredients.json: {key}.{attr} invalid level {ing.get(attr)}")
        if ing.get("base_unit") not in VALID_UNITS:
            errors.append(f"ingredients.json: {key}.base_unit invalid {ing.get('base_unit')}")
        if not ing.get("season_months") or not isinstance(ing.get("perishable_days"), int):
            errors.append(f"ingredients.json: {key} missing season_months or perishable_days")
        if ing.get("ref_price_bdt") is None or ing.get("ref_price_per") is None:
            errors.append(f"ingredients.json: {key} missing ref_price_bdt or ref_price_per")

    # Aliases
    for alias, ing_key in data["aliases.json"].get("aliases", {}).items():
        if ing_key not in ingredients_by_key:
            errors.append(f"aliases.json: alias '{alias}' points to unknown ingredient '{ing_key}'")

    # Prices
    for ing_key in data["prices.json"].get("reference_prices", {}):
        if ing_key not in ingredients_by_key:
            errors.append(f"prices.json: unknown ingredient '{ing_key}'")

    # Substitution groups
    for grp, keys in data["substitution_groups.json"].get("groups", {}).items():
        for k in keys:
            if k not in ingredients_by_key:
                errors.append(f"substitution_groups.json: group '{grp}' has unknown ingredient '{k}'")

    # Recipes
    recipe_keys: set[str] = set()
    for recipe in data["recipes.json"].get("recipes", []):
        rkey = recipe.get("key")
        if not rkey:
            errors.append("recipes.json: recipe missing key")
            continue
        if rkey in recipe_keys:
            errors.append(f"recipes.json: duplicate recipe key {rkey}")
        recipe_keys.add(rkey)
        if not recipe.get("name_bn"):
            errors.append(f"recipes.json: {rkey} missing name_bn")
        ing_keys_in_recipe: set[str] = set()
        for item in recipe.get("ingredients", []):
            ik = item.get("ingredient_key")
            if ik not in ingredients_by_key:
                errors.append(f"recipes.json: {rkey} references unknown ingredient '{ik}'")
            else:
                expected_unit = ingredients_by_key[ik]["base_unit"]
                if item.get("unit") != expected_unit:
                    errors.append(f"recipes.json: {rkey}.{ik} unit '{item.get('unit')}' != '{expected_unit}'")
                ing_keys_in_recipe.add(ik)
        for rem in recipe.get("split_removes", []):
            if rem not in ing_keys_in_recipe:
                errors.append(f"recipes.json: {rkey} split_removes '{rem}' not in recipe ingredients")
        if recipe.get("split_removes") and not recipe.get("split_step_bn"):
            errors.append(f"recipes.json: {rkey} has split_removes without split_step_bn")

    # Demo household
    for item in data["demo_household.json"].get("initial_stock", []):
        if item.get("ingredient_key") not in ingredients_by_key:
            errors.append(f"demo_household.json: unknown initial_stock key {item.get('ingredient_key')}")

    if errors:
        raise ValueError("Seed validation failed:\n" + "\n".join(f" - {e}" for e in errors))

    return {
        "ingredients": len(ingredients_by_key),
        "aliases": len(data["aliases.json"].get("aliases", {})),
        "recipes": len(recipe_keys),
        "rules": len(data["rules.json"].get("rules", [])),
        "presets": len(data["diet_presets.json"].get("presets", [])),
        "drug_classes": len(drug_classes),
    }


if __name__ == "__main__":
    summary = validate_all_seeds()
    print("Seed validation passed:", summary)
