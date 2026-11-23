"""Transparent weighted dish scoring (`score_dishes`) — pure Python."""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from app.core.prices import get_price_estimate
from app.core.types import (
    HouseholdCandidate,
    RecipeData,
    RuleContext,
    ScoredDish,
    StockItemState,
)

DEFAULT_SCORE_WEIGHTS: dict[str, float] = {
    "stock_fit": 0.25,
    "expiry_bonus": 0.15,
    "season_bonus": 0.10,
    "health_fit": 0.15,
    "taste": 0.10,
    "price_fit": 0.15,
    "repeat_penalty": 0.30,
}

BREAKFAST_FAVORED_KEYS: set[str] = {
    "chola_dal_bhuna",
    "patla_masoor_dal",
    "pepe_moog_dal",
    "mishti_shobji",
    "alu_fulkopi_jhol",
    "dudh_kola_madhu",
}

LUNCH_FAVORED_KEYS: set[str] = {
    "fulkopi_roast_curry",
    "alu_fulkopi_jhol",
    "potol_bhuna",
    "begun_torkari",
    "pui_shak_kumra",
    "gajor_sheem_torkari",
    "lau_masoor_dal",
    "chalkumra_moog_dal",
    "shosha_salad",
}

DINNER_FAVORED_KEYS: set[str] = {
    "lau_masoor_dal",
    "pepe_moog_dal",
    "patla_masoor_dal",
    "chalkumra_moog_dal",
    "mishti_shobji",
    "jhinge_jhol",
    "begun_torkari",
    "gajor_sheem_torkari",
    "murgir_pepe_jhol",
    "murgir_jhol",
    "dim_bhuna",
    "dim_begun_curry",
    "rui_lau_jhol",
}


def _meal_affinity_adjustment(recipe: RecipeData, meal: str | None) -> float:
    """Return culinary meal-of-day adjustment so breakfast, lunch, and dinner feel distinct."""
    if not meal:
        return 0.0
    m = meal.strip().lower()
    cat = (recipe.category or "").strip().lower()
    key = recipe.key

    if m == "breakfast":
        if cat in ("fish", "meat"):
            return -0.50
        if cat in ("bhaji", "egg", "sweet", "snack") or key in BREAKFAST_FAVORED_KEYS:
            return 0.22
        if cat in ("dal", "vegetable"):
            return 0.04
        return -0.10

    if m == "lunch":
        if key in ("dudh_kola_madhu", "chola_dal_bhuna"):
            return -0.22
        if cat in ("fish", "meat") or key in LUNCH_FAVORED_KEYS:
            return 0.18
        if cat in ("vegetable", "dal", "salad"):
            return 0.08
        return -0.04

    if m == "dinner":
        if key in ("gorur_bhuna", "shorshe_ilish", "dudh_kola_madhu", "chola_dal_bhuna"):
            return -0.20
        if key in DINNER_FAVORED_KEYS:
            return 0.18
        if cat in ("dal", "vegetable", "egg"):
            return 0.08
        return -0.02

    return 0.0


def _daily_variety_adjustment(recipe_key: str, for_date: date | None, meal: str | None) -> float:
    """Deterministic [-0.22, +0.22] daily rotation offset keyed by (for_date, meal, recipe_key)."""
    if for_date is None and meal is None:
        return 0.0
    date_part = for_date.isoformat() if for_date is not None else "static"
    meal_part = (meal or "dinner").strip().lower()
    digest = hashlib.sha256(f"{date_part}:{meal_part}:{recipe_key}".encode("utf-8")).digest()
    unit_val = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF  # 0.0 .. 1.0
    return round((unit_val - 0.5) * 0.44, 4)


def _diversify_top_candidates(scored: list[ScoredDish]) -> list[ScoredDish]:
    """Ensure the top 3 dishes span distinct categories when viable candidates exist."""
    if len(scored) <= 3:
        return scored

    top_score = scored[0].score
    viable_window = 0.35
    chosen_top: list[ScoredDish] = []
    seen_categories: set[str] = set()

    for item in scored:
        if len(chosen_top) >= 3:
            break
        if top_score - item.score > viable_window:
            break
        cat = (item.recipe.category or item.recipe.key).lower()
        if cat not in seen_categories:
            chosen_top.append(item)
            seen_categories.add(cat)

    if len(chosen_top) < 3:
        for item in scored:
            if len(chosen_top) >= 3:
                break
            if item not in chosen_top:
                chosen_top.append(item)

    chosen_ids = {id(x) for x in chosen_top}
    remainder = [x for x in scored if id(x) not in chosen_ids]
    return chosen_top + remainder


def score_dishes(
    candidates: list[HouseholdCandidate],
    stock_map: dict[str, StockItemState],
    context: RuleContext,
    current_month: int,
    household_budget_bdt: int = 15000,
    people_count: int = 4,
    recent_cooked_recipe_keys: set[str] | None = None,
    user_price_observations: list[dict[str, Any]] | None = None,
    weights: dict[str, float] | None = None,
    meal: str | None = None,
    for_date: date | None = None,
) -> list[ScoredDish]:
    """Rank safe household dishes using SPEC §7.3 weighted breakdown plus meal/date variety."""
    w = {**DEFAULT_SCORE_WEIGHTS, **(weights or {})}
    recent_keys = recent_cooked_recipe_keys or set()
    per_meal_budget = max(50.0, float(household_budget_bdt) / 60.0)

    scored: list[ScoredDish] = []
    for cand in candidates:
        recipe = cand.recipe
        scale = max(1, people_count) / max(1, recipe.servings_base)
        ings = recipe.ingredients

        stock_ratios: list[float] = []
        expiry_scores: list[float] = []
        season_hits = 0
        missing_list: list[dict[str, Any]] = []
        shortfall_cost = 0.0

        for ri in ings:
            needed = ri.qty * scale
            stock_item = stock_map.get(ri.ingredient_key)
            available = stock_item.qty_base if stock_item else 0.0
            ratio = min(1.0, available / needed) if needed > 0 else 1.0
            stock_ratios.append(ratio)

            if available > 0 and stock_item and stock_item.near_expiry:
                expiry_scores.append(1.0)
            elif available > 0:
                expiry_scores.append(0.0)

            ing_meta = context.ingredients.get(ri.ingredient_key)
            if ing_meta and current_month in ing_meta.season_months:
                season_hits += 1

            missing_qty = max(0.0, needed - available)
            if missing_qty > 0.001:
                est_item_cost = 0.0
                if ing_meta is not None:
                    est = get_price_estimate(ing_meta, user_price_observations)
                    if est.price_bdt is not None and est.per_qty > 0:
                        est_item_cost = round((missing_qty / est.per_qty) * est.price_bdt, 2)
                shortfall_cost += est_item_cost
                missing_list.append(
                    {
                        "ingredient_key": ri.ingredient_key,
                        "name_bn": ing_meta.name_bn if ing_meta else ri.ingredient_key,
                        "missing_qty": round(missing_qty, 2),
                        "unit": ri.unit,
                        "est_cost_bdt": est_item_cost,
                        "is_estimated": True,
                    }
                )

        n_ings = max(1, len(ings))
        stock_fit = round(sum(stock_ratios) / n_ings, 4)
        expiry_bonus = round(sum(expiry_scores) / max(1, len(expiry_scores)), 4) if expiry_scores else 0.0
        season_bonus = round(season_hits / n_ings, 4)
        health_fit = 1.0 if cand.status == "SAFE_DIRECT" else 0.7
        taste = max(0.0, min(1.0, float(recipe.taste_score)))
        price_fit = round(1.0 - min(1.0, shortfall_cost / per_meal_budget), 4)
        repeat_penalty = 1.0 if recipe.key in recent_keys else 0.0

        meal_adj = _meal_affinity_adjustment(recipe, meal)
        variety_adj = _daily_variety_adjustment(recipe.key, for_date, meal)

        total_score = round(
            w["stock_fit"] * stock_fit
            + w["expiry_bonus"] * expiry_bonus
            + w["season_bonus"] * season_bonus
            + w["health_fit"] * health_fit
            + w["taste"] * taste
            + w["price_fit"] * price_fit
            - w["repeat_penalty"] * repeat_penalty
            + meal_adj
            + variety_adj,
            4,
        )

        scored.append(
            ScoredDish(
                recipe=recipe,
                status=cand.status,
                split_for=cand.split_for,
                split_step_bn=cand.split_step_bn,
                reasons=cand.reasons,
                score=total_score,
                components={
                    "stock_fit": stock_fit,
                    "expiry_bonus": expiry_bonus,
                    "season_bonus": season_bonus,
                    "health_fit": health_fit,
                    "taste": taste,
                    "price_fit": price_fit,
                    "repeat_penalty": repeat_penalty,
                },
                missing_ingredients=missing_list,
                shortfall_cost_bdt=round(shortfall_cost, 2),
            )
        )

    scored.sort(key=lambda s: (-s.score, -s.recipe.taste_score, s.recipe.key))
    if meal is not None or for_date is not None:
        return _diversify_top_candidates(scored)
    return scored
