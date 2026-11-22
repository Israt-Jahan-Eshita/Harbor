"""Deterministic Bangla fallback templates when LLM explanation fails or is rejected — pure Python."""

from __future__ import annotations

from app.core.types import HouseholdCandidate


def render_fallback_menu_item(candidate: HouseholdCandidate) -> dict:
    """Build SPEC §8.5 fixed Bangla fallback explanation from validated recipe data."""
    lines = [f"আজকের জন্য নিরাপদ: {candidate.recipe.name_bn}"]
    split_instruction_bn: str | None = None

    if candidate.status == "SAFE_WITH_SPLIT" and candidate.split_step_bn:
        members_str = " ও ".join(candidate.split_for) if candidate.split_for else "সদস্য"
        step = candidate.split_step_bn.strip()
        if step.endswith("আগে"):
            split_instruction_bn = f"{members_str}-এর অংশ {step} আলাদা করে তুলে রাখুন।"
        else:
            split_instruction_bn = f"{members_str}-এর অংশ {step} আগে আলাদা করে তুলে রাখুন।"
        lines.append(split_instruction_bn)

    rule_ids = candidate.reasons if candidate.reasons else ["SAFE_DIRECT"]
    lines.append(f"[Rule: {', '.join(rule_ids)}]")

    return {
        "recipe_id": candidate.recipe.id,
        "explanation_bn": "\n".join(lines),
        "split_instruction_bn": split_instruction_bn,
        "rule_ids": rule_ids,
        "used_template": True,
    }
