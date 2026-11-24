"""Whole-week (7 days x 3 meals) household shared-pot meal planner — pure Python."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.core.bazar import calculate_bazar_shortfall
from app.core.prices import get_price_estimate
from app.core.rules import STATUS_PRECEDENCE
from app.core.scoring import score_dishes
from app.core.shared_pot import find_shared_pot_dishes
from app.core.templates import render_fallback_menu_item
from app.core.types import (
    GuestEventData,
    HouseholdCandidate,
    IngredientConflict,
    MemberData,
    RecipeData,
    RuleContext,
    ScoredDish,
    StockItemState,
)

MEAL_SLOTS: tuple[str, ...] = ("breakfast", "lunch", "dinner")

WEEKDAYS_BN: list[str] = [
    "সোমবার",
    "মঙ্গলবার",
    "বুধবার",
    "বৃহস্পতিবার",
    "শুক্রবার",
    "শনিবার",
    "রবিবার",
]

WEEKDAYS_EN: list[str] = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def _pick_weekly_slot_dish(
    scored: list[ScoredDish],
    used_for_meal: set[str],
    recent_window: list[str],
    locked_recipe_key: str | None = None,
) -> tuple[ScoredDish, bool, bool]:
    """Select best safe dish balancing rolling variety, unless safely locked by caregiver.

    Returns `(chosen_dish, is_locked, lock_overridden)`.
    """
    if locked_recipe_key:
        match = next((s for s in scored if s.recipe.key == locked_recipe_key), None)
        if match is not None:
            return match, True, False
        # Locked dish became unsafe/excluded under active rules -> fail-safe override
        chosen = _pick_non_repeating_dish(scored, used_for_meal, recent_window)
        return chosen, False, True

    chosen = _pick_non_repeating_dish(scored, used_for_meal, recent_window)
    return chosen, False, False


def _pick_non_repeating_dish(
    scored: list[ScoredDish],
    used_for_meal: set[str],
    recent_window: list[str],
) -> ScoredDish:
    last_four = set(recent_window[-4:])
    last_three = set(recent_window[-3:])
    last_one = set(recent_window[-1:])

    return (
        next((s for s in scored if s.recipe.key not in used_for_meal and s.recipe.key not in last_four), None)
        or next((s for s in scored if s.recipe.key not in last_three), None)
        or next((s for s in scored if s.recipe.key not in last_one), None)
        or scored[0]
    )


def _linked_medicines_for_slot(
    present_members: list[MemberData],
    meal: str,
    meal_times: dict[str, str],
) -> list[dict[str, Any]]:
    linked: list[dict[str, Any]] = []
    meal_time_str = meal_times.get(meal, "")
    for m in present_members:
        for med in m.medicines:
            if not med.active or not med.verified_by_caregiver:
                continue
            if meal in (med.meal_slots or []):
                linked.append(
                    {
                        "member_id": m.id,
                        "member_name": m.name,
                        "medicine_name": med.name_as_written,
                        "generic_name": med.generic_name,
                        "timing": med.timing,
                        "meal_time": meal_time_str,
                    }
                )
    return linked


def _build_shortfall_items(
    weekly_plan_items: list[dict[str, Any]],
    context: RuleContext,
    stock_map: dict[str, StockItemState],
    current_month: int,
    user_price_observations: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], float]:
    shortfalls = calculate_bazar_shortfall(weekly_plan_items, stock_map)
    items: list[dict[str, Any]] = []
    total_bdt = 0.0

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
        total_bdt += est_cost
        items.append(
            {
                "ingredient_key": ikey,
                "name_bn": ing.name_bn,
                "name_en": ing.name_en,
                "qty": round(qty_needed, 2),
                "unit": ing.base_unit,
                "est_price_bdt": est_cost,
                "price_source": est.source,
                "missing_price": est.missing_price,
                "is_estimated": True,
                "in_season": current_month in ing.season_months,
                "category": ing.category,
            }
        )

    items.sort(key=lambda it: (-it["est_price_bdt"], it["ingredient_key"]))
    return items, round(total_bdt, 2)


def build_weekly_meal_plan(
    members: list[MemberData],
    recipes: list[RecipeData],
    context: RuleContext,
    stock_map: dict[str, StockItemState],
    start_date: date,
    *,
    days: int = 7,
    household_budget_bdt: int = 15000,
    meal_times: dict[str, str] | None = None,
    day_events_by_date: dict[date, tuple[list[GuestEventData], set[str]]] | None = None,
    initial_recent_keys: set[str] | None = None,
    locked_slots: dict[str, str] | None = None,
    substitution_groups: dict[str, list[str]] | None = None,
    user_price_observations: list[dict[str, Any]] | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Generate a consolidated whole-week (7 x 3 = 21 slot) safe household meal plan."""
    effective_meal_times = meal_times or {"breakfast": "08:00", "lunch": "13:30", "dinner": "21:00"}
    events_map = day_events_by_date or {}
    locks = locked_slots or {}
    sim_stock = {k: v.model_copy(deep=True) for k, v in stock_map.items()}

    recent_window: list[str] = sorted(initial_recent_keys or set())[-6:]
    used_by_meal: dict[str, set[str]] = {m: set() for m in MEAL_SLOTS}
    weekly_plan_items: list[dict[str, Any]] = []
    conflict_by_ing: dict[str, IngredientConflict] = {}

    day_entries: list[dict[str, Any]] = []
    unique_recipe_keys: set[str] = set()
    safe_slots_count = 0
    split_slots_count = 0
    deadlock_slots_count = 0
    total_linked_meds = 0

    for offset in range(days):
        cur_date = start_date + timedelta(days=offset)
        guests, away_ids = events_map.get(cur_date, ([], set()))

        shared = find_shared_pot_dishes(
            members=members,
            recipes=recipes,
            context=context,
            for_date=cur_date,
            meal="dinner",
            away_member_ids=away_ids,
            guests=guests,
            substitution_groups=substitution_groups,
            user_price_observations=user_price_observations,
        )
        cands_by_id: dict[str, HouseholdCandidate] = {c.recipe.id: c for c in shared.candidates}
        present_members = [m for m in members if m.id not in away_ids]

        if shared.conflict_summary:
            for conf in shared.conflict_summary.conflicted_ingredients:
                prev = conflict_by_ing.get(conf.ingredient_key)
                if prev is None or (
                    STATUS_PRECEDENCE[conf.winning_status],
                    len(conf.winning_reasons),
                ) > (
                    STATUS_PRECEDENCE[prev.winning_status],
                    len(prev.winning_reasons),
                ):
                    conflict_by_ing[conf.ingredient_key] = conf

        meal_slots_out: list[dict[str, Any]] = []
        for meal in MEAL_SLOTS:
            linked_meds = _linked_medicines_for_slot(present_members, meal, effective_meal_times)
            total_linked_meds += len(linked_meds)
            slot_key = f"{cur_date.isoformat()}:{meal}"

            if not shared.candidates:
                deadlock_slots_count += 1
                meal_slots_out.append(
                    {
                        "meal": meal,
                        "recipe_id": None,
                        "recipe_key": None,
                        "name_bn": "এক হাঁড়িতে নিরাপদ পদ নেই",
                        "name_en": "No single shared-pot dish",
                        "category": "deadlock",
                        "scaled_servings": max(1, shared.people_count),
                        "status": "DEADLOCK_NO_SAFE_DISH",
                        "split_for": [],
                        "split_step_bn": None,
                        "reasons": [],
                        "explanation_bn": shared.conflict_summary.deadlock_recovery_bn if shared.conflict_summary else None,
                        "explanation_en": shared.conflict_summary.deadlock_recovery_en if shared.conflict_summary else None,
                        "locked": False,
                        "lock_overridden": False,
                        "lock_override_reason_bn": None,
                        "alternatives": [],
                        "linked_medicines": linked_meds,
                    }
                )
                continue

            scored = score_dishes(
                candidates=shared.candidates,
                stock_map=sim_stock,
                context=context,
                current_month=cur_date.month,
                household_budget_bdt=household_budget_bdt,
                people_count=max(1, shared.people_count),
                recent_cooked_recipe_keys=set(recent_window),
                user_price_observations=user_price_observations,
                weights=weights,
                meal=meal,
                for_date=cur_date,
            )
            chosen, is_locked, lock_overridden = _pick_weekly_slot_dish(
                scored=scored,
                used_for_meal=used_by_meal[meal],
                recent_window=recent_window,
                locked_recipe_key=locks.get(slot_key),
            )
            cand = cands_by_id[chosen.recipe.id]
            tpl = render_fallback_menu_item(cand)

            safe_slots_count += 1
            if chosen.status == "SAFE_WITH_SPLIT":
                split_slots_count += 1
            unique_recipe_keys.add(chosen.recipe.key)
            used_by_meal[meal].add(chosen.recipe.key)
            recent_window.append(chosen.recipe.key)
            if len(recent_window) > 6:
                recent_window.pop(0)

            scale = max(1, shared.people_count) / max(1, chosen.recipe.servings_base)
            for ri in chosen.recipe.ingredients:
                used_qty = ri.qty * scale
                weekly_plan_items.append({"ingredient_key": ri.ingredient_key, "qty": used_qty})
                if ri.ingredient_key in sim_stock:
                    sim_stock[ri.ingredient_key].qty_base = max(
                        0.0, sim_stock[ri.ingredient_key].qty_base - used_qty
                    )

            alternatives = [
                {
                    "recipe_id": alt.recipe.id,
                    "recipe_key": alt.recipe.key,
                    "name_bn": alt.recipe.name_bn,
                    "name_en": alt.recipe.name_en,
                    "category": alt.recipe.category,
                    "status": alt.status,
                    "score": alt.score,
                    "split_for": alt.split_for,
                    "split_step_bn": alt.split_step_bn,
                }
                for alt in scored
                if alt.recipe.key != chosen.recipe.key
            ][:5]

            meal_slots_out.append(
                {
                    "meal": meal,
                    "recipe_id": chosen.recipe.id,
                    "recipe_key": chosen.recipe.key,
                    "name_bn": chosen.recipe.name_bn,
                    "name_en": chosen.recipe.name_en,
                    "category": chosen.recipe.category,
                    "scaled_servings": max(1, shared.people_count),
                    "status": chosen.status,
                    "split_for": chosen.split_for,
                    "split_step_bn": chosen.split_step_bn,
                    "reasons": chosen.reasons,
                    "explanation_bn": tpl["explanation_bn"],
                    "explanation_en": tpl["explanation_en"],
                    "locked": is_locked,
                    "lock_overridden": lock_overridden,
                    "lock_override_reason_bn": (
                        "নিরাপত্তা/অতিথি বিধিনিষেধের কারণে লক করা পদটি বাদ দিয়ে নিরাপদ পদ বাছাই করা হয়েছে।"
                        if lock_overridden
                        else None
                    ),
                    "alternatives": alternatives,
                    "linked_medicines": linked_meds,
                }
            )

        day_entries.append(
            {
                "for_date": cur_date.isoformat(),
                "weekday_bn": WEEKDAYS_BN[cur_date.weekday()],
                "weekday_en": WEEKDAYS_EN[cur_date.weekday()],
                "people_count": max(1, shared.people_count),
                "present_member_names": shared.present_member_names,
                "guest_count": shared.guest_count,
                "excluded_count": len(shared.excluded),
                "slots": meal_slots_out,
            }
        )

    shortfall_items, est_weekly_shortfall_bdt = _build_shortfall_items(
        weekly_plan_items=weekly_plan_items,
        context=context,
        stock_map=stock_map,
        current_month=start_date.month,
        user_price_observations=user_price_observations,
    )
    weekly_budget_target_bdt = round(float(household_budget_bdt) * (days / 30.0), 2)
    over_weekly_budget = est_weekly_shortfall_bdt > weekly_budget_target_bdt

    conflict_matrix = sorted(
        [c.model_dump(mode="json") for c in conflict_by_ing.values()],
        key=lambda c: (-STATUS_PRECEDENCE[c["winning_status"]], -len(c["winning_reasons"]), c["ingredient_key"]),
    )

    total_slots = days * len(MEAL_SLOTS)
    end_date = start_date + timedelta(days=days - 1)
    coach_bn = (
        f"{days} দিনের {total_slots} বেলার মধ্যে {safe_slots_count} বেলা সবার জন্য নিরাপদ পদ ({len(unique_recipe_keys)}টি ভিন্ন পদ) সাজানো হয়েছে। "
        f"{split_slots_count}টি বেলা এক হাঁড়িতে আলাদা অংশ তুলে রাখার নির্দেশনাসহ নিরাপদ, এবং {len(conflict_matrix)}টি উপাদানে সদস্যদের বিধিনিষেধ সংঘাত স্থিরভাবে সমাধান হয়েছে।"
    )
    coach_en = (
        f"Planned {safe_slots_count}/{total_slots} safe family meals across {days} days ({len(unique_recipe_keys)} unique dishes). "
        f"{split_slots_count} slots use a single-step pot split, and {len(conflict_matrix)} ingredient conflicts were resolved steadily."
    )

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "days_count": days,
        "total_slots": total_slots,
        "safe_slots_count": safe_slots_count,
        "split_slots_count": split_slots_count,
        "deadlock_slots_count": deadlock_slots_count,
        "unique_dishes_count": len(unique_recipe_keys),
        "total_linked_medicines": total_linked_meds,
        "days": day_entries,
        "conflict_matrix": conflict_matrix,
        "shortfall_items": shortfall_items,
        "est_weekly_shortfall_bdt": est_weekly_shortfall_bdt,
        "weekly_budget_target_bdt": weekly_budget_target_bdt,
        "over_weekly_budget": over_weekly_budget,
        "coach_summary_bn": coach_bn,
        "coach_summary_en": coach_en,
        "used_ai_summary": False,
    }


def recalculate_weekly_plan_totals(
    plan_payload: dict[str, Any],
    recipes_by_key: dict[str, RecipeData],
    context: RuleContext,
    stock_map: dict[str, StockItemState],
    household_budget_bdt: int,
    user_price_observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Recompute shortfall, unique dishes, and safety counts after a slot swap/lock edit."""
    updated = dict(plan_payload)
    weekly_plan_items: list[dict[str, Any]] = []
    unique_keys: set[str] = set()
    safe_slots = 0
    split_slots = 0
    deadlock_slots = 0

    for day in updated.get("days", []):
        people = max(1, int(day.get("people_count", 1)))
        for slot in day.get("slots", []):
            status = slot.get("status")
            rkey = slot.get("recipe_key")
            if status == "DEADLOCK_NO_SAFE_DISH" or not rkey:
                deadlock_slots += 1
                continue
            safe_slots += 1
            if status == "SAFE_WITH_SPLIT":
                split_slots += 1
            unique_keys.add(rkey)
            rec = recipes_by_key.get(rkey)
            if rec is not None:
                scale = people / max(1, rec.servings_base)
                for ri in rec.ingredients:
                    weekly_plan_items.append({"ingredient_key": ri.ingredient_key, "qty": ri.qty * scale})

    start_date_str = updated.get("start_date", "")
    try:
        start_month = date.fromisoformat(start_date_str).month
    except ValueError:
        start_month = 11

    shortfall_items, est_weekly_shortfall_bdt = _build_shortfall_items(
        weekly_plan_items=weekly_plan_items,
        context=context,
        stock_map=stock_map,
        current_month=start_month,
        user_price_observations=user_price_observations,
    )
    days_count = int(updated.get("days_count", len(updated.get("days", [])) or 7))
    weekly_budget_target = round(float(household_budget_bdt) * (days_count / 30.0), 2)

    updated["safe_slots_count"] = safe_slots
    updated["split_slots_count"] = split_slots
    updated["deadlock_slots_count"] = deadlock_slots
    updated["unique_dishes_count"] = len(unique_keys)
    updated["shortfall_items"] = shortfall_items
    updated["est_weekly_shortfall_bdt"] = est_weekly_shortfall_bdt
    updated["weekly_budget_target_bdt"] = weekly_budget_target
    updated["over_weekly_budget"] = est_weekly_shortfall_bdt > weekly_budget_target
    return updated

