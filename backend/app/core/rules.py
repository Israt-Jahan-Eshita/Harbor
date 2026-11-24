"""Deterministic food-safety evaluation (`check_dish_safe`) — pure Python."""

from __future__ import annotations

from app.core.types import (
    IngredientData,
    IngredientVerdict,
    MemberData,
    MemberSafetyResult,
    RecipeData,
    RuleContext,
    SafetyStatus,
)

LEVEL_RANK: dict[str, int] = {"low": 1, "medium": 2, "high": 3}
STATUS_PRECEDENCE: dict[str, int] = {
    "SAFE_DIRECT": 0,
    "SAFE_WITH_SPLIT": 1,
    "BLOCKED": 2,
    "UNVERIFIED": 3,
}

ALLERGEN_SYNONYMS: dict[str, str] = {
    "prawn_shellfish": "prawn_shellfish",
    "prawn": "prawn_shellfish",
    "shrimp": "prawn_shellfish",
    "shellfish": "prawn_shellfish",
    "chingri": "prawn_shellfish",
    "চিংড়ি": "prawn_shellfish",
    "fish": "fish",
    "mach": "fish",
    "মাছ": "fish",
    "egg": "egg",
    "dim": "egg",
    "ডিম": "egg",
    "milk": "milk",
    "dairy": "milk",
    "dudh": "milk",
    "দুধ": "milk",
    "peanut": "peanut",
    "badam": "peanut",
    "chinabadam": "peanut",
    "চিনাবাদাম": "peanut",
    "বাদাম": "peanut",
    "tree_nut": "tree_nut",
    "wheat_gluten": "wheat_gluten",
    "wheat": "wheat_gluten",
    "gluten": "wheat_gluten",
    "গম": "wheat_gluten",
    "soy": "soy",
    "soybean": "soy",
    "সয়া": "soy",
    "sesame": "sesame",
    "til": "sesame",
    "তিল": "sesame",
}

ALLERGEN_RULE_NAMES: dict[str, str] = {
    "prawn_shellfish": "PRAWN_ALLERGY",
    "fish": "FISH_ALLERGY",
    "egg": "EGG_ALLERGY",
    "milk": "MILK_ALLERGY",
    "peanut": "PEANUT_ALLERGY",
    "tree_nut": "TREE_NUT_ALLERGY",
    "wheat_gluten": "WHEAT_GLUTEN_ALLERGY",
    "soy": "SOY_ALLERGY",
    "sesame": "SESAME_ALLERGY",
}

AGE_PROFILE_RULES: dict[str, tuple[str, str]] = {
    "child_under_1": ("honey", "CHILD_UNDER_1_HONEY"),
    "child_under_5": ("whole_nuts", "CHILD_UNDER_5_WHOLE_NUTS"),
}


def normalize_allergen(raw: str) -> str:
    """Normalize English, Bangla, or Banglish allergen terms to canonical tag."""
    cleaned = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if cleaned in ALLERGEN_SYNONYMS:
        return ALLERGEN_SYNONYMS[cleaned]
    raw_stripped = raw.strip().lower()
    return ALLERGEN_SYNONYMS.get(raw_stripped, cleaned)


def _append_unique(target: list[str], item: str) -> None:
    if item not in target:
        target.append(item)


def _has_valid_nutrition_attrs(ing: IngredientData) -> bool:
    for attr in ("potassium_level", "purine_level", "sodium_level", "gi_level"):
        val = getattr(ing, attr, None)
        if val not in LEVEL_RANK:
            return False
    return True


def _record_verdict(
    verdicts: dict[str, IngredientVerdict],
    ingredient_key: str,
    status: SafetyStatus,
    reason: str | None = None,
    split_removable: bool = False,
) -> None:
    """Escalate per-ingredient verdict following strict fail-closed precedence."""
    cur = verdicts.get(ingredient_key)
    if cur is None:
        cur = IngredientVerdict(ingredient_key=ingredient_key)
        verdicts[ingredient_key] = cur
    if STATUS_PRECEDENCE[status] > STATUS_PRECEDENCE[cur.status]:
        cur.status = status
    if cur.status == "SAFE_WITH_SPLIT" and split_removable and status == "SAFE_WITH_SPLIT":
        cur.split_removable = True
    elif cur.status != "SAFE_WITH_SPLIT":
        cur.split_removable = False
    if reason:
        _append_unique(cur.reasons, reason)


def check_dish_safe(
    member: MemberData,
    recipe: RecipeData,
    context: RuleContext,
) -> MemberSafetyResult:
    """Evaluate dish safety for one member in strict SPEC §7.1 order.

    1. Unverified checks (unknown/incomplete ingredient, unmapped confirmed active medicine).
    2. Allergens (member allergies vs ingredient allergen_tags, plus explicit guest exclusions).
    3. Drug-food rules (confirmed active medicines only).
    4. Diet presets & age profiles (checking single-step split eligibility).
    5. Safe direct if nothing triggered.

    Collects ALL triggered reasons, per-ingredient verdicts, and full trace lines.
    """
    trace: list[str] = []
    unverified_reasons: list[str] = []
    blocked_reasons: list[str] = []
    splittable_reasons: list[str] = []
    split_ingredients: list[str] = []
    verdicts: dict[str, IngredientVerdict] = {
        ri.ingredient_key: IngredientVerdict(ingredient_key=ri.ingredient_key)
        for ri in recipe.ingredients
    }

    resolved_ingredients: list[IngredientData] = []

    # Step 1: Unverified checks
    if not recipe.ingredients:
        _append_unique(unverified_reasons, "UNKNOWN_INGREDIENT")
        _record_verdict(verdicts, "__recipe__", "UNVERIFIED", "UNKNOWN_INGREDIENT")
        trace.append(f"UNVERIFIED recipe '{recipe.key}' has no ingredients -> UNVERIFIED: UNKNOWN_INGREDIENT")

    for ri in recipe.ingredients:
        ing = context.ingredients.get(ri.ingredient_key)
        if ing is None:
            _append_unique(unverified_reasons, "UNKNOWN_INGREDIENT")
            _record_verdict(verdicts, ri.ingredient_key, "UNVERIFIED", "UNKNOWN_INGREDIENT")
            trace.append(
                f"UNVERIFIED missing ingredient '{ri.ingredient_key}' in recipe '{recipe.key}' -> UNVERIFIED: UNKNOWN_INGREDIENT"
            )
            continue
        if not _has_valid_nutrition_attrs(ing):
            _append_unique(unverified_reasons, "UNKNOWN_INGREDIENT")
            _record_verdict(verdicts, ing.key, "UNVERIFIED", "UNKNOWN_INGREDIENT")
            trace.append(
                f"UNVERIFIED incomplete attributes on ingredient '{ing.key}' -> UNVERIFIED: UNKNOWN_INGREDIENT"
            )
            continue
        resolved_ingredients.append(ing)

    confirmed_active_meds = []
    for med in member.medicines:
        if not med.active:
            trace.append(f"SKIPPED inactive medicine '{med.name_as_written}'")
            continue
        if not med.verified_by_caregiver:
            trace.append(
                f"SKIPPED unconfirmed medicine '{med.name_as_written}' (caregiver confirmation gate)"
            )
            continue
        if not med.drug_class or med.drug_class not in context.known_drug_classes:
            _append_unique(unverified_reasons, "UNMAPPED_MEDICINE")
            if recipe.ingredients:
                for ri in recipe.ingredients:
                    _record_verdict(verdicts, ri.ingredient_key, "UNVERIFIED", "UNMAPPED_MEDICINE")
            else:
                _record_verdict(verdicts, "__medicine__", "UNVERIFIED", "UNMAPPED_MEDICINE")
            trace.append(
                f"UNVERIFIED medicine '{med.name_as_written}' (drug_class={med.drug_class}) -> UNVERIFIED: UNMAPPED_MEDICINE"
            )
            continue
        confirmed_active_meds.append(med)

    # Step 2: Allergens & explicit ingredient exclusions (e.g. guest no_beef)
    member_allergens = {normalize_allergen(a) for a in member.allergies if a.strip()}
    for ing in resolved_ingredients:
        ing_allergens = {normalize_allergen(t) for t in ing.allergen_tags if t.strip()}
        for tag in sorted(member_allergens & ing_allergens):
            rule_code = ALLERGEN_RULE_NAMES.get(tag, f"{tag.upper()}_ALLERGY")
            _append_unique(blocked_reasons, rule_code)
            _record_verdict(verdicts, ing.key, "BLOCKED", rule_code)
            trace.append(f"ALLERGEN {tag} matches ingredient {ing.key} -> BLOCKED: {rule_code}")

        if ing.key in member.excluded_ingredient_keys or any(
            tag in member.excluded_ingredient_keys for tag in ing.tags
        ):
            rule_code = f"GUEST_EXCLUDES_{ing.key.upper()}"
            _append_unique(blocked_reasons, rule_code)
            _record_verdict(verdicts, ing.key, "BLOCKED", rule_code)
            trace.append(f"EXCLUSION {ing.key} restricted for {member.name} -> BLOCKED: {rule_code}")

    # Step 3: Drug-food rules (confirmed active medicines only)
    for med in confirmed_active_meds:
        if med.drug_class == "none_modelled":
            trace.append(f"MEDICINE '{med.name_as_written}' mapped as none_modelled -> OK")
            continue
        matching_rules = [r for r in context.drug_food_rules if r.drug_class == med.drug_class]
        for rule in matching_rules:
            for ing in resolved_ingredients:
                matched = False
                if rule.ingredient_attr == "tag":
                    matched = rule.attr_value in ing.tags
                else:
                    matched = getattr(ing, rule.ingredient_attr, None) == rule.attr_value
                if matched:
                    _append_unique(blocked_reasons, rule.rule_id)
                    _record_verdict(verdicts, ing.key, "BLOCKED", rule.rule_id)
                    trace.append(
                        f"DRUG_FOOD {med.name_as_written} ({med.drug_class}) + "
                        f"{ing.key}.{rule.ingredient_attr}={rule.attr_value} -> BLOCKED: {rule.rule_id}"
                    )

    # Step 4: Diet presets & age profiles
    preset_lookup: dict[str, list] = {}
    for p in context.diet_presets:
        preset_lookup.setdefault(p.preset, []).append(p)

    for preset_name in member.diet_presets:
        for preset_rule in preset_lookup.get(preset_name, []):
            max_rank = LEVEL_RANK[preset_rule.max_level]
            attr_short = preset_rule.attr.replace("_level", "").upper()
            reason_code = f"{preset_name.upper()}_{attr_short}"

            for ing in resolved_ingredients:
                val = getattr(ing, preset_rule.attr, None)
                if val in LEVEL_RANK and LEVEL_RANK[val] > max_rank:
                    can_split = (
                        preset_rule.split_allowed
                        and bool(recipe.split_step_bn)
                        and ing.key in recipe.split_removes
                    )
                    if can_split:
                        _append_unique(splittable_reasons, reason_code)
                        _append_unique(split_ingredients, ing.key)
                        _record_verdict(
                            verdicts,
                            ing.key,
                            "SAFE_WITH_SPLIT",
                            reason_code,
                            split_removable=True,
                        )
                        trace.append(
                            f"PRESET {preset_name} ({preset_rule.attr}={val} > {preset_rule.max_level}) "
                            f"on {ing.key} splittable before '{recipe.split_step_bn}' -> SAFE_WITH_SPLIT: {reason_code}"
                        )
                    else:
                        _append_unique(blocked_reasons, reason_code)
                        _record_verdict(verdicts, ing.key, "BLOCKED", reason_code)
                        trace.append(
                            f"PRESET {preset_name} ({preset_rule.attr}={val} > {preset_rule.max_level}) "
                            f"on {ing.key} -> BLOCKED: {reason_code}"
                        )

    if member.age_group in AGE_PROFILE_RULES:
        blocked_tag, age_rule_id = AGE_PROFILE_RULES[member.age_group]
        for ing in resolved_ingredients:
            if blocked_tag in ing.tags:
                _append_unique(blocked_reasons, age_rule_id)
                _record_verdict(verdicts, ing.key, "BLOCKED", age_rule_id)
                trace.append(
                    f"AGE_PROFILE {member.age_group} blocks tag '{blocked_tag}' on {ing.key} -> BLOCKED: {age_rule_id}"
                )

    # Step 5: Aggregate status
    all_reasons: list[str] = []
    for r in unverified_reasons + blocked_reasons + splittable_reasons:
        _append_unique(all_reasons, r)

    if unverified_reasons:
        status: SafetyStatus = "UNVERIFIED"
    elif blocked_reasons:
        status = "BLOCKED"
    elif splittable_reasons:
        status = "SAFE_WITH_SPLIT"
    else:
        status = "SAFE_DIRECT"
        trace.append(f"ALL_CHECKS_PASSED for {member.name} on {recipe.key} -> SAFE_DIRECT")

    return MemberSafetyResult(
        member_id=member.id,
        member_name=member.name,
        recipe_id=recipe.id,
        recipe_key=recipe.key,
        status=status,
        reasons=all_reasons,
        trace=trace,
        split_step_bn=recipe.split_step_bn if status == "SAFE_WITH_SPLIT" else None,
        split_ingredients=split_ingredients if status == "SAFE_WITH_SPLIT" else [],
        ingredient_verdicts=verdicts,
    )
