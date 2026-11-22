"""Shared-pot safety aggregation across household members and guests — pure Python."""

from __future__ import annotations

from datetime import date

from app.core.rules import ALLERGEN_SYNONYMS, check_dish_safe, normalize_allergen
from app.core.types import (
    GuestEventData,
    HouseholdCandidate,
    HouseholdExcluded,
    MemberData,
    MemberSafetyResult,
    RecipeData,
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


def find_shared_pot_dishes(
    members: list[MemberData],
    recipes: list[RecipeData],
    context: RuleContext,
    for_date: date,
    meal: str = "dinner",
    away_member_ids: set[str] | None = None,
    guests: list[GuestEventData] | None = None,
) -> SharedPotResult:
    """Evaluate every recipe for all present household members and guests.

    - Any BLOCKED or UNVERIFIED person excludes the recipe (reasons kept).
    - All SAFE_DIRECT -> SAFE_DIRECT.
    - Any SAFE_WITH_SPLIT -> SAFE_WITH_SPLIT iff one single split step handles
      every splitting member; otherwise EXCLUDED.
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
            all_reasons: list[str] = []
            for r in bad_results:
                for reason in r.reasons:
                    if reason not in all_reasons:
                        all_reasons.append(reason)
            excluded.append(
                HouseholdExcluded(
                    recipe=recipe,
                    reasons=all_reasons,
                    member_results=member_results,
                )
            )
            continue

        split_results = [r for r in member_results if r.status == "SAFE_WITH_SPLIT"]
        if not split_results:
            candidates.append(
                HouseholdCandidate(
                    recipe=recipe,
                    status="SAFE_DIRECT",
                    member_results=member_results,
                )
            )
            continue

        split_steps = {r.split_step_bn for r in split_results if r.split_step_bn}
        if not recipe.split_step_bn or len(split_steps) != 1:
            excluded.append(
                HouseholdExcluded(
                    recipe=recipe,
                    reasons=["INCOMPATIBLE_SPLIT_STEPS"],
                    member_results=member_results,
                )
            )
            continue

        split_reasons: list[str] = []
        for r in split_results:
            for reason in r.reasons:
                if reason not in split_reasons:
                    split_reasons.append(reason)

        candidates.append(
            HouseholdCandidate(
                recipe=recipe,
                status="SAFE_WITH_SPLIT",
                split_for=[r.member_name for r in split_results],
                split_step_bn=recipe.split_step_bn,
                split_removes=list(recipe.split_removes),
                reasons=split_reasons,
                member_results=member_results,
            )
        )

    return SharedPotResult(
        for_date=for_date,
        meal=meal,
        people_count=people_count,
        present_member_names=present_names,
        guest_count=total_guests,
        candidates=candidates,
        excluded=excluded,
    )
