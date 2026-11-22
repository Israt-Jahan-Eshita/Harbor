"""Transparent weighted dish scoring (`score_dishes`) — pure Python."""

from __future__ import annotations

from typing import Any

from app.core.prices import get_price_estimate
from app.core.types import (
    HouseholdCandidate,
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
) -> list[ScoredDish]:
    """Rank safe household dishes using SPEC §7.3 weighted breakdown."""
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

        total_score = round(
            w["stock_fit"] * stock_fit
            + w["expiry_bonus"] * expiry_bonus
            + w["season_bonus"] * season_bonus
            + w["health_fit"] * health_fit
            + w["taste"] * taste
            + w["price_fit"] * price_fit
            - w["repeat_penalty"] * repeat_penalty,
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
    return scored
