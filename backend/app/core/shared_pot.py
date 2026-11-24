"""Shared-pot safety aggregation and multi-member ingredient conflict resolution — pure Python."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core.prices import get_price_estimate
from app.core.rules import ALLERGEN_SYNONYMS, STATUS_PRECEDENCE, check_dish_safe, normalize_allergen
from app.core.types import (
    ConflictResolutionSummary,
    GuestEventData,
    HouseholdCandidate,
    HouseholdExcluded,
    IngredientConflict,
    IngredientVerdict,
    MemberData,
    MemberIngredientPosition,
    MemberSafetyResult,
    RecipeData,
    RecipeIngredientData,
    RuleContext,
    SharedPotResult,
)

KNOWN_PRESETS = {"low_gi", "low_sodium", "low_purine", "low_potassium"}


def _build_guest_members(guests: list[GuestEventData] | None) -> tuple[list[MemberData], int]:
    """Convert guest events into temporary MemberData profiles for safety checks."""
    if not guests:
        return [], 0

    total_guests = 0
    guest_members: list[MemberData] = []
    for idx, ge in enumerate(guests):
        if ge.guest_count <= 0:
            continue
        total_guests += ge.guest_count
        allergies: list[str] = []
        presets: list[str] = []
        excluded_keys: list[str] = []

        for raw_r in ge.restrictions:
            token = raw_r.strip().lower().replace("-", "_").replace(" ", "_")
            if not token:
                continue
            if token in KNOWN_PRESETS:
                presets.append(token)
            elif token.startswith("no_"):
                target = token[3:]
                if target in ALLERGEN_SYNONYMS:
                    allergies.append(normalize_allergen(target))
                else:
                    excluded_keys.append(target)
                    if target == "beef":
                        excluded_keys.append("red_meat")
            elif token.endswith("_allergy"):
                allergies.append(normalize_allergen(token[: -len("_allergy")]))
            elif token in ALLERGEN_SYNONYMS:
                allergies.append(normalize_allergen(token))
            else:
                excluded_keys.append(token)

        guest_members.append(
            MemberData(
                id=f"guest-group-{idx + 1}",
                name=f"অতিথি ({ge.guest_count} জন)" if ge.guest_count > 1 else "অতিথি",
                role="other",
                age_group="adult",
                allergies=allergies,
                diet_presets=presets,
                medicines=[],
                is_guest=True,
                excluded_ingredient_keys=excluded_keys,
            )
        )

    return guest_members, total_guests


def _find_safe_substitutes_for_ingredient(
    ingredient_key: str,
    members: list[MemberData],
    recipe: RecipeData,
    context: RuleContext,
    substitution_groups: dict[str, list[str]],
    current_month: int = 11,
    user_price_observations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return same-group ingredient swaps that keep the dish safe or safely splittable for everyone."""
    candidate_keys: list[str] = []
    for _grp, keys in substitution_groups.items():
        if ingredient_key in keys:
            for k in keys:
                if k != ingredient_key and k not in candidate_keys:
                    candidate_keys.append(k)

    if not candidate_keys:
        return []

    options: list[dict[str, Any]] = []
    for cand_key in candidate_keys:
        cand_ing = context.ingredients.get(cand_key)
        if cand_ing is None:
            continue
        swapped_ings = [
            RecipeIngredientData(
                ingredient_key=cand_key if ri.ingredient_key == ingredient_key else ri.ingredient_key,
                qty=ri.qty,
                unit=cand_ing.base_unit if ri.ingredient_key == ingredient_key else ri.unit,
            )
            for ri in recipe.ingredients
        ]
        swapped_recipe = recipe.model_copy(update={"ingredients": swapped_ings})
        results = [check_dish_safe(m, swapped_recipe, context) for m in members]
        if any(r.status in ("BLOCKED", "UNVERIFIED") for r in results):
            continue
        split_steps = {r.split_step_bn for r in results if r.status == "SAFE_WITH_SPLIT" and r.split_step_bn}
        if any(r.status == "SAFE_WITH_SPLIT" for r in results) and len(split_steps) != 1:
            continue

        price_est = get_price_estimate(cand_ing, user_price_observations)
        unit_price = (
            price_est.price_bdt / price_est.per_qty
            if (price_est.price_bdt is not None and price_est.per_qty > 0)
            else float("inf")
        )
        in_season = current_month in cand_ing.season_months
        options.append(
            {
                "ingredient_key": cand_key,
                "name_bn": cand_ing.name_bn,
                "name_en": cand_ing.name_en,
                "in_season": in_season,
                "price_bdt": price_est.price_bdt,
                "per_qty": price_est.per_qty,
                "unit": cand_ing.base_unit,
                "unit_price": None if unit_price == float("inf") else round(unit_price, 4),
                "resulting_status": "SAFE_WITH_SPLIT" if split_steps else "SAFE_DIRECT",
            }
        )

    options.sort(
        key=lambda o: (
            o["resulting_status"] != "SAFE_DIRECT",
            not o["in_season"],
            o["unit_price"] if o["unit_price"] is not None else float("inf"),
            o["ingredient_key"],
        )
    )
    return options[:3]


def analyze_recipe_ingredient_conflicts(
    recipe: RecipeData,
    member_results: list[MemberSafetyResult],
    context: RuleContext,
    *,
    incompatible_split: bool = False,
    substitution_groups: dict[str, list[str]] | None = None,
    current_month: int = 11,
    user_price_observations: list[dict[str, Any]] | None = None,
    eating_roster: list[MemberData] | None = None,
) -> list[IngredientConflict]:
    """Identify every ingredient where >=2 household members hold conflicting or overlapping restrictions."""
    if len(member_results) < 2:
        return []

    keys_to_inspect = sorted({ri.ingredient_key for ri in recipe.ingredients})
    if not keys_to_inspect:
        keys_to_inspect = sorted({k for mr in member_results for k in mr.ingredient_verdicts.keys()})

    conflicts: list[IngredientConflict] = []
    for ikey in keys_to_inspect:
        positions: list[MemberIngredientPosition] = []
        for mr in member_results:
            verdict = mr.ingredient_verdicts.get(ikey) or IngredientVerdict(ingredient_key=ikey)
            positions.append(
                MemberIngredientPosition(
                    member_id=mr.member_id,
                    member_name=mr.member_name,
                    status=verdict.status,
                    reasons=sorted(set(verdict.reasons)),
                )
            )

        non_safe = [p for p in positions if p.status != "SAFE_DIRECT"]
        distinct_statuses = {p.status for p in positions}
        if not non_safe or (len(distinct_statuses) <= 1 and len(non_safe) < 2):
            continue

        # Sort positions canonically so [A, B] and [B, A] yield identical conflict objects
        positions.sort(key=lambda p: (-STATUS_PRECEDENCE[p.status], p.member_name, p.member_id))

        winning_status = max((p.status for p in positions), key=lambda s: STATUS_PRECEDENCE[s])
        winning_reasons = sorted({r for p in positions for r in p.reasons})

        if winning_status == "UNVERIFIED":
            conflict_type = "UNVERIFIED_FAIL_CLOSED"
            resolution = "UNVERIFIED_FAIL_CLOSED"
        elif winning_status == "BLOCKED":
            if len(non_safe) >= 2 and len(winning_reasons) >= 2:
                conflict_type = "MULTI_RULE_COLLISION"
            else:
                conflict_type = "SEVERITY_ESCALATION"
            resolution = "BLOCKED_MOST_RESTRICTIVE_WINS"
        else:
            if incompatible_split:
                conflict_type = "INCOMPATIBLE_SPLIT_BLOCKED"
                resolution = "EXCLUDED_INCOMPATIBLE_SPLIT"
            else:
                conflict_type = "CONVERGENT_SPLIT"
                resolution = "SAFE_WITH_SINGLE_SPLIT"

        ing_meta = context.ingredients.get(ikey)
        name_bn = ing_meta.name_bn if ing_meta else ikey
        name_en = ing_meta.name_en if ing_meta else ikey

        summary_pairs_bn = "; ".join(
            f"{p.member_name}: {', '.join(p.reasons) if p.reasons else 'নিরাপদ'}" for p in positions
        )
        summary_pairs_en = "; ".join(
            f"{p.member_name}: {', '.join(p.reasons) if p.reasons else 'SAFE'}" for p in positions
        )

        if resolution == "UNVERIFIED_FAIL_CLOSED":
            exp_bn = f"{name_bn} নিয়ে অনিশ্চিত তথ্য থাকায় ফেইল-ক্লোজড নীতিতে পদটি UNVERIFIED হিসেবে স্থগিত রাখা হয়েছে ({summary_pairs_bn})।"
            exp_en = f"Fail-closed UNVERIFIED held steady on {name_en} because verification is incomplete ({summary_pairs_en})."
        elif resolution == "BLOCKED_MOST_RESTRICTIVE_WINS":
            exp_bn = f"{name_bn} নিয়ে সদস্যদের বিধিনিষেধ সংঘাত ({summary_pairs_bn}) — কঠোরতম নিরাপত্তা নিয়ম ({', '.join(winning_reasons)}) বিজয়ী হওয়ায় পদটি বাদ দেওয়া হয়েছে।"
            exp_en = f"Restriction conflict on {name_en} ({summary_pairs_en}) — strictest rule wins ({', '.join(winning_reasons)}), dish safely excluded."
        elif resolution == "SAFE_WITH_SINGLE_SPLIT":
            exp_bn = f"{name_bn} নিয়ে একাধিক সদস্যের চাহিদা এক ধাপে সমাধানযোগ্য ({summary_pairs_bn}) — \"{recipe.split_step_bn}\" অংশ আলাদা করলে সবার জন্য নিরাপদ।"
            exp_en = f"Restrictions on {name_en} converge on one safe split step ({summary_pairs_en}) before '{recipe.split_step_bn}'."
        else:
            exp_bn = f"{name_bn} নিয়ে আলাদা করার ধাপ সামঞ্জস্যপূর্ণ না হওয়ায় নিরাপত্তা নিশ্চিতে পদটি বাদ দেওয়া হয়েছে ({summary_pairs_bn})।"
            exp_en = f"Incompatible split steps on {name_en} caused safe exclusion ({summary_pairs_en})."

        substitutes: list[dict[str, Any]] = []
        if substitution_groups and eating_roster and winning_status != "SAFE_WITH_SPLIT":
            substitutes = _find_safe_substitutes_for_ingredient(
                ingredient_key=ikey,
                members=eating_roster,
                recipe=recipe,
                context=context,
                substitution_groups=substitution_groups,
                current_month=current_month,
                user_price_observations=user_price_observations,
            )

        conflicts.append(
            IngredientConflict(
                ingredient_key=ikey,
                ingredient_name_bn=name_bn,
                ingredient_name_en=name_en,
                conflict_type=conflict_type,
                resolution=resolution,
                winning_status=winning_status,
                winning_reasons=winning_reasons,
                positions=positions,
                explanation_bn=exp_bn,
                explanation_en=exp_en,
                safe_substitutes=substitutes,
            )
        )

    conflicts.sort(
        key=lambda c: (-STATUS_PRECEDENCE[c.winning_status], -len(c.winning_reasons), c.ingredient_key)
    )
    return conflicts


def _build_conflict_summary(
    recipes: list[RecipeData],
    candidates: list[HouseholdCandidate],
    excluded: list[HouseholdExcluded],
) -> ConflictResolutionSummary:
    safe_direct_count = sum(1 for c in candidates if c.status == "SAFE_DIRECT")
    safe_with_split_count = sum(1 for c in candidates if c.status == "SAFE_WITH_SPLIT")

    best_by_ing: dict[str, IngredientConflict] = {}
    for item in [*candidates, *excluded]:
        for conf in item.ingredient_conflicts:
            existing = best_by_ing.get(conf.ingredient_key)
            if existing is None or (
                STATUS_PRECEDENCE[conf.winning_status],
                len(conf.winning_reasons),
            ) > (
                STATUS_PRECEDENCE[existing.winning_status],
                len(existing.winning_reasons),
            ):
                best_by_ing[conf.ingredient_key] = conf

    conflicted = sorted(
        best_by_ing.values(),
        key=lambda c: (-STATUS_PRECEDENCE[c.winning_status], -len(c.winning_reasons), c.ingredient_key),
    )

    zero_safe_deadlock = bool(recipes) and len(candidates) == 0
    recovery_bn: str | None = None
    recovery_en: str | None = None
    if zero_safe_deadlock:
        bottleneck_bn = ", ".join(c.ingredient_name_bn for c in conflicted[:3]) or "সদস্যদের বিপরীতমুখী নিয়ম"
        bottleneck_en = ", ".join(c.ingredient_name_en for c in conflicted[:3]) or "competing member restrictions"
        recovery_bn = (
            f"পরস্পরবিরোধী বিধিনিষেধের ({bottleneck_bn}) কারণে এক হাঁড়িতে সবার উপযোগী কোনো পদ পাওয়া যায়নি। "
            "নিরাপত্তার স্বার্থে ইঞ্জিন অনিরাপদ খাবার দেখায়নি; আজ ২-হাঁড়ি পদ্ধতিতে আলাদা রান্না বা মেহমান/সদস্য ফিল্টার রিভিউ করুন।"
        )
        recovery_en = (
            f"Zero shared-pot dishes satisfy all competing rules simultaneously ({bottleneck_en}). "
            "Engine held steady with 0 unsafe leaks; use a 2-pot split for conflicting members or review guest/away filters."
        )

    return ConflictResolutionSummary(
        total_recipes_checked=len(recipes),
        safe_direct_count=safe_direct_count,
        safe_with_split_count=safe_with_split_count,
        excluded_count=len(excluded),
        conflicted_ingredients=conflicted,
        zero_safe_deadlock=zero_safe_deadlock,
        deadlock_recovery_bn=recovery_bn,
        deadlock_recovery_en=recovery_en,
    )


def find_shared_pot_dishes(
    members: list[MemberData],
    recipes: list[RecipeData],
    context: RuleContext,
    for_date: date,
    meal: str = "dinner",
    away_member_ids: set[str] | None = None,
    guests: list[GuestEventData] | None = None,
    substitution_groups: dict[str, list[str]] | None = None,
    user_price_observations: list[dict[str, Any]] | None = None,
) -> SharedPotResult:
    """Evaluate every recipe for all present household members and guests.

    - Any BLOCKED or UNVERIFIED person excludes the recipe (reasons kept in deterministic order).
    - All SAFE_DIRECT -> SAFE_DIRECT.
    - Any SAFE_WITH_SPLIT -> SAFE_WITH_SPLIT iff one single split step handles
      every splitting member and every splitting ingredient; otherwise EXCLUDED.
    - Tracks same-ingredient conflicts and order-invariant precedence across members.
    """
    away_ids = away_member_ids or set()
    present_members = [m for m in members if m.id not in away_ids]
    guest_profiles, total_guests = _build_guest_members(guests)
    eating_roster = present_members + guest_profiles

    people_count = len(present_members) + total_guests
    present_names = [m.name for m in present_members]

    candidates: list[HouseholdCandidate] = []
    excluded: list[HouseholdExcluded] = []

    for recipe in recipes:
        member_results: list[MemberSafetyResult] = [
            check_dish_safe(person, recipe, context) for person in eating_roster
        ]

        bad_results = [r for r in member_results if r.status in ("BLOCKED", "UNVERIFIED")]
        if bad_results:
            all_reasons = sorted({reason for r in bad_results for reason in r.reasons})
            conflicts = analyze_recipe_ingredient_conflicts(
                recipe,
                member_results,
                context,
                incompatible_split=False,
                substitution_groups=substitution_groups,
                current_month=for_date.month,
                user_price_observations=user_price_observations,
                eating_roster=eating_roster,
            )
            excluded.append(
                HouseholdExcluded(
                    recipe=recipe,
                    reasons=all_reasons,
                    member_results=member_results,
                    ingredient_conflicts=conflicts,
                )
            )
            continue

        split_results = [r for r in member_results if r.status == "SAFE_WITH_SPLIT"]
        if not split_results:
            conflicts = analyze_recipe_ingredient_conflicts(
                recipe,
                member_results,
                context,
                incompatible_split=False,
                eating_roster=eating_roster,
            )
            candidates.append(
                HouseholdCandidate(
                    recipe=recipe,
                    status="SAFE_DIRECT",
                    member_results=member_results,
                    ingredient_conflicts=conflicts,
                )
            )
            continue

        split_steps = {r.split_step_bn for r in split_results if r.split_step_bn}
        allowed_removes = set(recipe.split_removes)
        all_split_removable = all(
            set(r.split_ingredients).issubset(allowed_removes) for r in split_results
        )
        incompatible = not recipe.split_step_bn or len(split_steps) != 1 or not all_split_removable
        conflicts = analyze_recipe_ingredient_conflicts(
            recipe,
            member_results,
            context,
            incompatible_split=incompatible,
            substitution_groups=substitution_groups if incompatible else None,
            current_month=for_date.month,
            user_price_observations=user_price_observations,
            eating_roster=eating_roster,
        )
        if incompatible:
            excluded.append(
                HouseholdExcluded(
                    recipe=recipe,
                    reasons=["INCOMPATIBLE_SPLIT_STEPS"],
                    member_results=member_results,
                    ingredient_conflicts=conflicts,
                )
            )
            continue

        split_reasons = sorted({reason for r in split_results for reason in r.reasons})
        candidates.append(
            HouseholdCandidate(
                recipe=recipe,
                status="SAFE_WITH_SPLIT",
                split_for=[r.member_name for r in split_results],
                split_step_bn=recipe.split_step_bn,
                split_removes=list(recipe.split_removes),
                reasons=split_reasons,
                member_results=member_results,
                ingredient_conflicts=conflicts,
            )
        )

    summary = _build_conflict_summary(recipes, candidates, excluded)
    return SharedPotResult(
        for_date=for_date,
        meal=meal,
        people_count=people_count,
        present_member_names=present_names,
        guest_count=total_guests,
        candidates=candidates,
        excluded=excluded,
        conflict_summary=summary,
    )


def evaluate_multi_member_conflict(
    members: list[MemberData],
    recipe: RecipeData,
    context: RuleContext,
    *,
    substitution_groups: dict[str, list[str]] | None = None,
    current_month: int = 11,
    user_price_observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run forward and reversed member evaluations to verify steady conflict resolution & commutativity."""
    eval_date = date(2026, max(1, min(12, current_month)), 1)
    forward = find_shared_pot_dishes(
        members=members,
        recipes=[recipe],
        context=context,
        for_date=eval_date,
        meal="dinner",
        substitution_groups=substitution_groups,
        user_price_observations=user_price_observations,
    )
    reversed_res = find_shared_pot_dishes(
        members=list(reversed(members)),
        recipes=[recipe],
        context=context,
        for_date=eval_date,
        meal="dinner",
        substitution_groups=substitution_groups,
        user_price_observations=user_price_observations,
    )

    fwd_entry: HouseholdCandidate | HouseholdExcluded = (
        forward.candidates[0] if forward.candidates else forward.excluded[0]
    )
    rev_entry: HouseholdCandidate | HouseholdExcluded = (
        reversed_res.candidates[0] if reversed_res.candidates else reversed_res.excluded[0]
    )

    fwd_reasons = sorted(set(fwd_entry.reasons))
    rev_reasons = sorted(set(rev_entry.reasons))
    fwd_conf_sig = [
        (c.ingredient_key, c.conflict_type, c.winning_status, c.winning_reasons)
        for c in fwd_entry.ingredient_conflicts
    ]
    rev_conf_sig = [
        (c.ingredient_key, c.conflict_type, c.winning_status, c.winning_reasons)
        for c in rev_entry.ingredient_conflicts
    ]
    order_invariant = (
        fwd_entry.status == rev_entry.status
        and fwd_reasons == rev_reasons
        and fwd_conf_sig == rev_conf_sig
    )

    return {
        "recipe_key": recipe.key,
        "recipe_name_bn": recipe.name_bn,
        "recipe_name_en": recipe.name_en,
        "household_status": fwd_entry.status,
        "reasons": fwd_reasons,
        "split_for": list(fwd_entry.split_for) if isinstance(fwd_entry, HouseholdCandidate) else [],
        "split_step_bn": fwd_entry.split_step_bn if isinstance(fwd_entry, HouseholdCandidate) else None,
        "order_invariant": order_invariant,
        "forward_reasons": fwd_reasons,
        "reversed_reasons": rev_reasons,
        "member_results": [mr.model_dump(mode="json") for mr in fwd_entry.member_results],
        "ingredient_conflicts": [c.model_dump(mode="json") for c in fwd_entry.ingredient_conflicts],
        "zero_safe_deadlock": bool(forward.candidates == []),
        "deadlock_recovery_bn": forward.conflict_summary.deadlock_recovery_bn if forward.conflict_summary else None,
        "deadlock_recovery_en": forward.conflict_summary.deadlock_recovery_en if forward.conflict_summary else None,
    }
