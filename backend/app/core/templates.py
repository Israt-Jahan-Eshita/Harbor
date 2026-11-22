"""Deterministic bilingual (BN/EN) fallback templates when LLM fails or is rejected — pure Python."""

from __future__ import annotations

from app.core.types import HouseholdCandidate


def render_fallback_menu_item(candidate: HouseholdCandidate) -> dict:
    """Build SPEC §8.5 fixed Bangla & English fallback explanations from validated recipe data."""
    lines_bn = [f"আজকের জন্য নিরাপদ: {candidate.recipe.name_bn}"]
    dish_en = candidate.recipe.name_en or candidate.recipe.name_bn
    lines_en = [f"Safe for today: {dish_en}"]

    split_instruction_bn: str | None = None
    split_instruction_en: str | None = None

    if candidate.status == "SAFE_WITH_SPLIT" and candidate.split_step_bn:
        members_bn = " ও ".join(candidate.split_for) if candidate.split_for else "সদস্য"
        members_en = " & ".join(candidate.split_for) if candidate.split_for else "member"
        step = candidate.split_step_bn.strip()
        if step.endswith("আগে"):
            split_instruction_bn = f"{members_bn}-এর অংশ {step} আলাদা করে তুলে রাখুন।"
        else:
            split_instruction_bn = f"{members_bn}-এর অংশ {step} আগে আলাদা করে তুলে রাখুন।"
        lines_bn.append(split_instruction_bn)

        removed_en = ", ".join(candidate.split_removes) if candidate.split_removes else "salt/chilli"
        split_instruction_en = (
            f"Set aside {members_en}'s portion before adding {removed_en} ({step})."
        )
        lines_en.append(split_instruction_en)

    rule_ids = candidate.reasons if candidate.reasons else ["SAFE_DIRECT"]
    rule_line = f"[Rule: {', '.join(rule_ids)}]"
    lines_bn.append(rule_line)
    lines_en.append(rule_line)

    return {
        "recipe_id": candidate.recipe.id,
        "explanation_bn": "\n".join(lines_bn),
        "explanation_en": "\n".join(lines_en),
        "split_instruction_bn": split_instruction_bn,
        "split_instruction_en": split_instruction_en,
        "rule_ids": rule_ids,
        "used_template": True,
    }
