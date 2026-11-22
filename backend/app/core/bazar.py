"""Bazar shortfall, safety-rechecked substitutes, and simplified monthly list — pure Python."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core.prices import get_price_estimate
from app.core.rules import check_dish_safe
from app.core.scoring import score_dishes
from app.core.shared_pot import find_shared_pot_dishes
from app.core.types import (
    MemberData,
    RecipeData,
    RecipeIngredientData,
    RuleContext,
    StockItemState,
)


def calculate_bazar_shortfall(
    plan_items: list[dict[str, Any]],
    stock_map: dict[str, StockItemState],
    reserved_map: dict[str, float] | None = None,
) -> dict[str, float]:
    """Compute per-ingredient shortfall = max(0, needed - (stock - reserved))."""
    reserved = reserved_map or {}
    totals_needed: dict[str, float] = {}
    for item in plan_items:
        ikey = item["ingredient_key"]
        totals_needed[ikey] = totals_needed.get(ikey, 0.0) + float(item["qty"])

    shortfalls: dict[str, float] = {}
    for ikey, needed in sorted(totals_needed.items()):
        stock_qty = stock_map[ikey].qty_base if ikey in stock_map else 0.0
        res_qty = float(reserved.get(ikey, 0.0))
        net_available = max(0.0, stock_qty - res_qty)
        shortfall = round(max(0.0, needed - net_available), 3)
        if shortfall > 0.0:
            shortfalls[ikey] = shortfall
    return shortfalls


def find_safe_substitute(
    ingredient_key: str,
    members: list[MemberData],
    planned_recipes: list[RecipeData],
    context: RuleContext,
    substitution_groups: dict[str, list[str]],
    current_month: int,
    user_price_observations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return same-group substitutes that keep EVERY planned recipe safe for EVERY member."""
    candidate_keys: list[str] = []
    for _grp, keys in substitution_groups.items():
        if ingredient_key in keys:
            for k in keys:
                if k != ingredient_key and k not in candidate_keys:
                    candidate_keys.append(k)

    affected_recipes = [
        r for r in planned_recipes if any(ri.ingredient_key == ingredient_key for ri in r.ingredients)
    ]

    safe_options: list[dict[str, Any]] = []
    for cand_key in candidate_keys:
        cand_ing = context.ingredients.get(cand_key)
        if cand_ing is None:
            continue

        all_safe = True
        for recipe in affected_recipes:
            swapped_ings = [
                RecipeIngredientData(
                    ingredient_key=cand_key if ri.ingredient_key == ingredient_key else ri.ingredient_key,
                    qty=ri.qty,
                    unit=cand_ing.base_unit if ri.ingredient_key == ingredient_key else ri.unit,
                )
                for ri in recipe.ingredients
            ]
            swapped_recipe = recipe.model_copy(update={"ingredients": swapped_ings})
            for member in members:
                res = check_dish_safe(member, swapped_recipe, context)
                if res.status in ("BLOCKED", "UNVERIFIED"):
                    all_safe = False
                    break
            if not all_safe:
                break

        if not all_safe:
            continue

        price_est = get_price_estimate(cand_ing, user_price_observations)
        unit_price = (
            price_est.price_bdt / price_est.per_qty
            if (price_est.price_bdt is not None and price_est.per_qty > 0)
            else float("inf")
        )
        in_season = current_month in cand_ing.season_months
        safe_options.append(
            {
                "ingredient_key": cand_key,
                "name_bn": cand_ing.name_bn,
                "in_season": in_season,
                "price_bdt": price_est.price_bdt,
                "per_qty": price_est.per_qty,
                "unit": cand_ing.base_unit,
                "unit_price": unit_price,
                "is_estimated": True,
                "label_bn": "আনুমানিক",
            }
        )

    safe_options.sort(key=lambda o: (not o["in_season"], o["unit_price"], o["ingredient_key"]))
    return safe_options


def build_monthly_list(
    members: list[MemberData],
    recipes: list[RecipeData],
    context: RuleContext,
    stock_map: dict[str, StockItemState],
    month: str,
    current_month: int,
    budget_bdt: int,
    substitution_groups: dict[str, list[str]],
    user_price_observations: list[dict[str, Any]] | None = None,
    reserved_map: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Build simplified 30-day dinner bazar list within budget (SPEC §7.5)."""
    shared_res = find_shared_pot_dishes(
        members=members,
        recipes=recipes,
        context=context,
        for_date=date(2026, current_month, 1),
        meal="dinner",
    )

    sim_stock = {k: v.model_copy(deep=True) for k, v in stock_map.items()}
    remaining_cands = [c for c in shared_res.candidates if c.recipe.category != "snack"]
    if not remaining_cands:
        remaining_cands = list(shared_res.candidates)

    picked_recipes: list[RecipeData] = []
    picked_keys: set[str] = set()
    people_count = max(1, len(members))

    for _ in range(min(7, len(remaining_cands))):
        scored = score_dishes(
            candidates=remaining_cands,
            stock_map=sim_stock,
            context=context,
            current_month=current_month,
            household_budget_bdt=budget_bdt,
            people_count=people_count,
            recent_cooked_recipe_keys=picked_keys,
            user_price_observations=user_price_observations,
        )
        # Prefer distinct recipes across the 7-day rotation
        chosen = next((s for s in scored if s.recipe.key not in picked_keys), scored[0])
        picked_recipes.append(chosen.recipe)
        picked_keys.add(chosen.recipe.key)

        scale = people_count / max(1, chosen.recipe.servings_base)
        for ri in chosen.recipe.ingredients:
            if ri.ingredient_key in sim_stock:
                sim_stock[ri.ingredient_key].qty_base = max(
                    0.0, sim_stock[ri.ingredient_key].qty_base - ri.qty * scale
                )

    month_factor = 30.0 / max(1, len(picked_recipes)) if picked_recipes else 0.0
    plan_items: list[dict[str, Any]] = []
    for recipe in picked_recipes:
        scale = (people_count / max(1, recipe.servings_base)) * month_factor
        for ri in recipe.ingredients:
            plan_items.append({"ingredient_key": ri.ingredient_key, "qty": ri.qty * scale})

    shortfalls = calculate_bazar_shortfall(plan_items, stock_map, reserved_map)

    items: list[dict[str, Any]] = []
    for ikey, qty_needed in shortfalls.items():
        ing = context.ingredients.get(ikey)
        if ing is None:
            continue
        est = get_price_estimate(ing, user_price_observations)
        est_cost = (
            round((qty_needed / est.per_qty) * est.price_bdt, 2)
            if (est.price_bdt is not None and est.per_qty > 0)
            else 0.0
        )
        items.append(
            {
                "ingredient_key": ikey,
                "name_bn": ing.name_bn,
                "qty": round(qty_needed, 2),
                "unit": ing.base_unit,
                "est_price_bdt": est_cost,
                "price_source": est.source,
                "missing_price": est.missing_price,
                "is_estimated": True,
                "label_bn": "আনুমানিক",
                "in_season": current_month in ing.season_months,
                "substitute_used": False,
                "substituted_from": None,
                "dropped": False,
                "flag": None,
                "category": ing.category,
            }
        )

    def _total(cur_items: list[dict[str, Any]]) -> float:
        return round(sum(i["est_price_bdt"] for i in cur_items if not i["dropped"]), 2)

    # Budget pass 1: swap expensive or out-of-season items with safe substitutes
    if _total(items) > budget_bdt:
        # Try out-of-season first, then highest cost
        candidates_to_swap = sorted(
            items,
            key=lambda it: (it["in_season"], -it["est_price_bdt"]),
        )
        for item in candidates_to_swap:
            if _total(items) <= budget_bdt:
                break
            subs = find_safe_substitute(
                ingredient_key=item["ingredient_key"],
                members=members,
                planned_recipes=picked_recipes,
                context=context,
                substitution_groups=substitution_groups,
                current_month=current_month,
                user_price_observations=user_price_observations,
            )
            if not subs:
                continue
            best_sub = subs[0]
            if best_sub["price_bdt"] is None or best_sub["per_qty"] <= 0:
                continue
            new_cost = round((item["qty"] / best_sub["per_qty"]) * best_sub["price_bdt"], 2)
            if new_cost < item["est_price_bdt"] or not item["in_season"]:
                old_key = item["ingredient_key"]
                item["ingredient_key"] = best_sub["ingredient_key"]
                item["name_bn"] = best_sub["name_bn"]
                item["unit"] = best_sub["unit"]
                item["est_price_bdt"] = new_cost
                item["in_season"] = best_sub["in_season"]
                item["substitute_used"] = True
                item["substituted_from"] = old_key
                item["flag"] = f"নিরাপদ ও সাশ্রয়ী বিকল্প ({old_key} -> {best_sub['ingredient_key']})"

    # Budget pass 2: drop non-essential / highest-cost items if still over budget
    if _total(items) > budget_bdt:
        priority_drop = sorted(
            items,
            key=lambda it: (it["category"] == "spice", -it["est_price_bdt"]),
        )
        for item in priority_drop:
            if _total(items) <= budget_bdt:
                break
            item["dropped"] = True
            item["flag"] = "বাজেটের বাইরে হওয়ায় বাদ চিহ্নিত"

    est_total = _total(items)
    return {
        "month": month,
        "budget_bdt": budget_bdt,
        "planned_recipes": [{"key": r.key, "name_bn": r.name_bn} for r in picked_recipes],
        "items": items,
        "est_total_bdt": est_total,
        "over_budget": est_total > budget_bdt,
        "price_label_bn": "আনুমানিক",
    }
