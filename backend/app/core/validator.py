"""Deterministic validator guarding all LLM explanation outputs (`validate_response`) — pure Python."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.core.types import IngredientData, RecipeData

DOSE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"[0-9০-৯]+\s*(?:mg|mcg|মিগ্রা|মিলিগ্রাম|মি\.গ্রা\.|ট্যাবলেট|ক্যাপসুল)", re.IGNORECASE),
    re.compile(r"(?:ডোজ|বাড়ান|কমান|বন্ধ\s*করুন|dose|dosage|increase\s+dose|decrease\s+dose|stop\s+taking|discontinue)", re.IGNORECASE),
]

BANGLA_CHAR_CLASS = r"\u0980-\u09FF"
BANGLA_SUFFIX_GROUP = r"(?:য়ের|ের|র|ে|তে|কে|য়|টা|টি|গুলো)?"


class ExplanationItem(BaseModel):
    recipe_id: str = Field(..., min_length=1, max_length=128)
    explanation_bn: str = Field(..., min_length=1, max_length=500)
    split_instruction_bn: str | None = Field(default=None, max_length=300)
    rule_ids: list[str] = Field(default_factory=list)


class ExplanationOutput(BaseModel):
    items: list[ExplanationItem] = Field(..., min_length=1, max_length=10)


class ValidationResult(BaseModel):
    valid: bool
    reasons: list[str] = Field(default_factory=list)
    parsed: ExplanationOutput | None = None


def _compile_ingredient_pattern(name: str, is_bangla: bool) -> re.Pattern[str]:
    escaped = re.escape(name.strip())
    if is_bangla:
        return re.compile(rf"(?<![{BANGLA_CHAR_CLASS}]){escaped}{BANGLA_SUFFIX_GROUP}(?![{BANGLA_CHAR_CLASS}])")
    return re.compile(rf"\b{escaped}s?\b", re.IGNORECASE)


def _extract_allowed_from_tool_log(tool_log: list[dict[str, Any]]) -> tuple[set[str], dict[str, set[str]], set[str], list[str]]:
    candidate_ids: set[str] = set()
    allowed_rules_by_recipe: dict[str, set[str]] = {}
    excluded_ids: set[str] = set()
    excluded_names: list[str] = []

    for entry in tool_log:
        tool_name = entry.get("tool")
        res = entry.get("result") or {}
        if tool_name == "find_shared_pot_dishes":
            for cand in res.get("candidates", []):
                recipe_obj = cand.get("recipe") or {}
                rid = str(recipe_obj.get("id") or cand.get("recipe_id") or "")
                if rid:
                    candidate_ids.add(rid)
                    rules = set(cand.get("reasons", []))
                    if cand.get("status") == "SAFE_DIRECT":
                        rules.add("SAFE_DIRECT")
                    allowed_rules_by_recipe[rid] = rules
            for cid in res.get("candidate_ids", []):
                candidate_ids.add(str(cid))
            for rid, rlist in (res.get("allowed_rules_by_recipe") or {}).items():
                allowed_rules_by_recipe.setdefault(str(rid), set()).update(rlist)
            for excl in res.get("excluded", []):
                recipe_obj = excl.get("recipe") or {}
                eid = str(recipe_obj.get("id") or excl.get("recipe_id") or "")
                if eid:
                    excluded_ids.add(eid)
                for nm in (recipe_obj.get("name_bn"), recipe_obj.get("name_en")):
                    if nm:
                        excluded_names.append(str(nm))
            for eid in res.get("excluded_ids", []):
                excluded_ids.add(str(eid))
            for nm in res.get("excluded_names_bn", []):
                excluded_names.append(str(nm))

    return candidate_ids, allowed_rules_by_recipe, excluded_ids, excluded_names


def validate_response(
    output: dict[str, Any] | ExplanationOutput,
    tool_log: list[dict[str, Any]],
    known_ingredients: dict[str, IngredientData],
    recipes_by_id: dict[str, RecipeData],
) -> ValidationResult:
    """Validate untrusted LLM explanation output against tool_log and recipe records (SPEC §8.5)."""
    reasons: list[str] = []

    try:
        parsed = output if isinstance(output, ExplanationOutput) else ExplanationOutput.model_validate(output)
    except ValidationError as exc:
        return ValidationResult(valid=False, reasons=[f"SCHEMA_INVALID: {exc.errors()[0]['msg']}"])

    candidate_ids, allowed_rules_by_recipe, excluded_ids, excluded_names = _extract_allowed_from_tool_log(tool_log)

    if not candidate_ids:
        return ValidationResult(valid=False, reasons=["NO_TOOL_CANDIDATES_IN_LOG"])

    ing_patterns: dict[str, tuple[re.Pattern[str], re.Pattern[str]]] = {}
    for ikey, ing in known_ingredients.items():
        ing_patterns[ikey] = (
            _compile_ingredient_pattern(ing.name_bn, is_bangla=True),
            _compile_ingredient_pattern(ing.name_en, is_bangla=False),
        )

    for item in parsed.items:
        if item.recipe_id in excluded_ids or item.recipe_id not in candidate_ids:
            reasons.append(f"UNGROUNDED_RECIPE_ID:{item.recipe_id}")
            continue

        allowed_rules = allowed_rules_by_recipe.get(item.recipe_id, set())
        for rule_id in item.rule_ids:
            if rule_id not in allowed_rules:
                reasons.append(f"UNGROUNDED_RULE_ID:{rule_id}")

        combined_text = item.explanation_bn
        if item.split_instruction_bn:
            combined_text += " " + item.split_instruction_bn

        # Check dose / advice patterns
        for pat in DOSE_PATTERNS:
            if pat.search(combined_text):
                reasons.append(f"FORBIDDEN_DOSE_OR_ADVICE_PATTERN:{item.recipe_id}")
                break

        # Check no excluded recipe claimed safe inside explanation
        for excl_name in excluded_names:
            if excl_name and excl_name.lower() in combined_text.lower():
                if any(w in combined_text.lower() for w in ("নিরাপদ", "safe", "খেতে পারেন", "রান্না করুন")):
                    reasons.append(f"CLAIMED_EXCLUDED_SAFE:{excl_name}")

        # Check no ungrounded ingredient mentioned outside recipe's ingredients
        recipe = recipes_by_id.get(item.recipe_id)
        if recipe is None:
            reasons.append(f"UNKNOWN_RECIPE_RECORD:{item.recipe_id}")
        else:
            recipe_ing_keys = {ri.ingredient_key for ri in recipe.ingredients}
            for ikey, (bn_pat, en_pat) in ing_patterns.items():
                if ikey in recipe_ing_keys:
                    continue
                if bn_pat.search(combined_text) or en_pat.search(combined_text):
                    reasons.append(f"UNGROUNDED_INGREDIENT:{ikey}")

    if reasons:
        return ValidationResult(valid=False, reasons=reasons, parsed=None)

    return ValidationResult(valid=True, reasons=[], parsed=parsed)
