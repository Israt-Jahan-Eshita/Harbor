"""Grounded bilingual menu explanation writer guarded by core/validator.py & fallback templates."""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.templates import render_fallback_menu_item
from app.core.types import HouseholdCandidate, IngredientData, RecipeData, ScoredDish
from app.core.validator import DOSE_PATTERNS, ExplanationItem, ExplanationOutput, validate_response
from app.llm.client import LLMClient
from app.llm.prompts import EXPLAIN_SYSTEM_PROMPT

_EXPLAIN_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_EXPLAIN_CACHE_TTL_SECONDS = 6 * 3600
_EXPLAIN_CACHE_MAX_SIZE = 200


def clear_explanation_cache() -> None:
    """Clear in-memory grounded explanation cache (used by tests)."""
    _EXPLAIN_CACHE.clear()


class BilingualExplanationItem(BaseModel):
    recipe_id: str = Field(..., min_length=1, max_length=128)
    explanation_bn: str = Field(..., min_length=1, max_length=500)
    explanation_en: str = Field(..., min_length=1, max_length=500)
    split_instruction_bn: str | None = Field(default=None, max_length=300)
    split_instruction_en: str | None = Field(default=None, max_length=300)
    rule_ids: list[str] = Field(default_factory=list)


class BilingualExplanationOutput(BaseModel):
    items: list[BilingualExplanationItem] = Field(..., min_length=1, max_length=5)


def _check_english_safety(
    item: BilingualExplanationItem,
    recipe: RecipeData | None,
    known_ingredients: dict[str, IngredientData],
) -> list[str]:
    errors: list[str] = []
    combined_en = f"{item.explanation_en} {item.split_instruction_en or ''}"
    for pat in DOSE_PATTERNS:
        if pat.search(combined_en):
            errors.append(f"EN_FORBIDDEN_DOSE_PATTERN:{item.recipe_id}")
            break
    if recipe is not None:
        allowed_keys = {ri.ingredient_key for ri in recipe.ingredients}
        for ikey, ing in known_ingredients.items():
            if ikey in allowed_keys:
                continue
            en_pat = re.compile(rf"\b{re.escape(ing.name_en.strip())}s?\b", re.IGNORECASE)
            if en_pat.search(combined_en):
                errors.append(f"EN_UNGROUNDED_INGREDIENT:{ikey}")
    return errors


def build_fallback_explanations(top_candidates: list[HouseholdCandidate]) -> dict[str, dict[str, Any]]:
    """Build deterministic template explanation map keyed by recipe_id."""
    out: dict[str, dict[str, Any]] = {}
    for cand in top_candidates:
        out[cand.recipe.id] = render_fallback_menu_item(cand)
    return out


def generate_grounded_explanations(
    top_scored: list[ScoredDish],
    candidates_by_id: dict[str, HouseholdCandidate],
    tool_log: list[dict[str, Any]],
    known_ingredients: dict[str, IngredientData],
    recipes_by_id: dict[str, RecipeData],
    llm_client: LLMClient | None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Generate LLM bilingual explanations for top 3 safe dishes, validated before display."""
    top_3 = top_scored[:3]
    top_candidates = [candidates_by_id[s.recipe.id] for s in top_3 if s.recipe.id in candidates_by_id]
    fallback_map = build_fallback_explanations(top_candidates)

    if not top_3 or llm_client is None:
        return {
            "explanations_by_recipe": fallback_map,
            "validated": True,
            "used_template": True,
            "validation_reasons": [],
        }

    cache_key_payload = [
        {
            "recipe_id": s.recipe.id,
            "status": s.status,
            "split_for": sorted(s.split_for),
            "reasons": sorted(
                candidates_by_id[s.recipe.id].reasons
                if s.recipe.id in candidates_by_id and candidates_by_id[s.recipe.id].reasons
                else ["SAFE_DIRECT"]
            ),
        }
        for s in top_3
    ]
    cache_key = hashlib.sha256(
        json.dumps(cache_key_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    now_mono = time.monotonic()
    cached_entry = _EXPLAIN_CACHE.get(cache_key)
    if cached_entry is not None:
        exp_ts, cached_val = cached_entry
        if now_mono < exp_ts:
            return {
                "explanations_by_recipe": dict(cached_val["explanations_by_recipe"]),
                "validated": cached_val["validated"],
                "used_template": cached_val["used_template"],
                "validation_reasons": list(cached_val["validation_reasons"]),
                "cached": True,
            }
        _EXPLAIN_CACHE.pop(cache_key, None)

    dish_context_payload = []
    for scored in top_3:
        cand = candidates_by_id.get(scored.recipe.id)
        ing_names = [
            {
                "key": ri.ingredient_key,
                "name_bn": known_ingredients[ri.ingredient_key].name_bn
                if ri.ingredient_key in known_ingredients
                else ri.ingredient_key,
                "name_en": known_ingredients[ri.ingredient_key].name_en
                if ri.ingredient_key in known_ingredients
                else ri.ingredient_key,
            }
            for ri in scored.recipe.ingredients
        ]
        dish_context_payload.append(
            {
                "recipe_id": scored.recipe.id,
                "name_bn": scored.recipe.name_bn,
                "name_en": scored.recipe.name_en,
                "status": scored.status,
                "split_for": scored.split_for,
                "split_step_bn": scored.split_step_bn,
                "allowed_rule_ids": (cand.reasons if cand and cand.reasons else ["SAFE_DIRECT"]),
                "ingredients": ing_names,
            }
        )

    user_prompt = (
        "Write concise 1-2 sentence Bangla and English explanations for ONLY these verified dishes:\n"
        + json.dumps({"dishes": dish_context_payload}, ensure_ascii=False)
    )

    llm_out = llm_client.call_groq_json(
        task="menu_explain",
        system_prompt=EXPLAIN_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema_cls=BilingualExplanationOutput,
        db=db,
        input_summary=f"top3_recipes={[s.recipe.key for s in top_3]}",
        model_override=llm_client.llm_fast_model,
        max_completion_tokens=700,
    )

    if llm_out is None:
        return {
            "explanations_by_recipe": fallback_map,
            "validated": False,
            "used_template": True,
            "validation_reasons": ["LLM_UNAVAILABLE_FALLBACK"],
        }

    # Validate strictly with deterministic core.validator
    bn_payload = ExplanationOutput(
        items=[
            ExplanationItem(
                recipe_id=item.recipe_id,
                explanation_bn=item.explanation_bn,
                split_instruction_bn=item.split_instruction_bn,
                rule_ids=item.rule_ids,
            )
            for item in llm_out.items
        ]
    )
    val_res = validate_response(bn_payload, tool_log, known_ingredients, recipes_by_id)
    en_errors: list[str] = []
    for item in llm_out.items:
        en_errors.extend(_check_english_safety(item, recipes_by_id.get(item.recipe_id), known_ingredients))

    all_errors = val_res.reasons + en_errors
    if not val_res.valid or en_errors:
        return {
            "explanations_by_recipe": fallback_map,
            "validated": False,
            "used_template": True,
            "validation_reasons": all_errors,
        }

    # Map validated LLM explanations by recipe_id, filling any missing card from template
    by_id = dict(fallback_map)
    for item in llm_out.items:
        if item.recipe_id in by_id:
            by_id[item.recipe_id] = {
                "recipe_id": item.recipe_id,
                "explanation_bn": item.explanation_bn,
                "explanation_en": item.explanation_en,
                "split_instruction_bn": item.split_instruction_bn,
                "split_instruction_en": item.split_instruction_en,
                "rule_ids": item.rule_ids,
                "used_template": False,
            }

    used_template = all(v.get("used_template") for v in by_id.values())
    result = {
        "explanations_by_recipe": by_id,
        "validated": True,
        "used_template": used_template,
        "validation_reasons": [],
    }
    if not used_template:
        if len(_EXPLAIN_CACHE) >= _EXPLAIN_CACHE_MAX_SIZE:
            oldest_key = next(iter(_EXPLAIN_CACHE))
            _EXPLAIN_CACHE.pop(oldest_key, None)
        _EXPLAIN_CACHE[cache_key] = (
            time.monotonic() + _EXPLAIN_CACHE_TTL_SECONDS,
            {
                "explanations_by_recipe": dict(by_id),
                "validated": True,
                "used_template": False,
                "validation_reasons": [],
            },
        )
    return result
