"""Bounded meal-planning agent loop calling FastMCP tools with deterministic fallback (SPEC §10)."""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

from fastmcp import Client, FastMCP
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.scoring import score_dishes
from app.core.shared_pot import find_shared_pot_dishes
from app.core.templates import render_fallback_menu_item
from app.core.types import HouseholdCandidate, ScoredDish
from app.core.validator import ExplanationItem, ExplanationOutput, validate_response
from app.llm.client import LLMClient, _strip_json_fences
from app.llm.explain import BilingualExplanationOutput, _check_english_safety
from app.llm.prompts import AGENT_SYSTEM_PROMPT
from app.services.context_loader import (
    load_day_events,
    load_household_members,
    load_household_stock,
    load_recent_cooked_keys,
    load_rule_context_and_recipes,
    load_user_price_observations,
)

READ_TOOL_WHITELIST: set[str] = {
    "get_household_state",
    "get_inventory",
    "normalize_bangla_qty",
    "check_dish_safe",
    "find_shared_pot_dishes",
    "score_dishes",
    "get_seasonal_items",
    "get_price_estimate",
    "calculate_bazar_shortfall",
    "find_safe_substitute",
    "build_monthly_list",
}


def _compact_tool_result_for_llm(fn_name: str, payload: Any) -> str:
    """Summarize large tool outputs into compact valid JSON for the agent context."""
    if fn_name == "find_shared_pot_dishes" and isinstance(payload, dict):
        compact = {
            "for_date": payload.get("for_date"),
            "meal": payload.get("meal"),
            "people_count": payload.get("people_count"),
            "candidates": [
                {
                    "recipe_id": (c.get("recipe") or {}).get("id"),
                    "key": (c.get("recipe") or {}).get("key"),
                    "name_bn": (c.get("recipe") or {}).get("name_bn"),
                    "name_en": (c.get("recipe") or {}).get("name_en"),
                    "status": c.get("status"),
                    "split_for": c.get("split_for", []),
                    "split_step_bn": c.get("split_step_bn"),
                    "reasons": c.get("reasons", []),
                }
                for c in (payload.get("candidates") or [])[:15]
            ],
            "excluded": [
                {
                    "recipe_id": (e.get("recipe") or {}).get("id"),
                    "key": (e.get("recipe") or {}).get("key"),
                    "name_bn": (e.get("recipe") or {}).get("name_bn"),
                    "reasons": e.get("reasons", []),
                }
                for e in (payload.get("excluded") or [])[:15]
            ],
        }
        return json.dumps(compact, ensure_ascii=False)
    if fn_name == "score_dishes" and isinstance(payload, dict):
        compact = {
            "ranked": [
                {
                    "recipe_id": (s.get("recipe") or {}).get("id"),
                    "key": (s.get("recipe") or {}).get("key"),
                    "name_bn": (s.get("recipe") or {}).get("name_bn"),
                    "name_en": (s.get("recipe") or {}).get("name_en"),
                    "status": s.get("status"),
                    "split_for": s.get("split_for", []),
                    "split_step_bn": s.get("split_step_bn"),
                    "reasons": s.get("reasons", []),
                    "score": s.get("score"),
                    "components": s.get("components"),
                }
                for s in (payload.get("ranked") or [])[:5]
            ]
        }
        return json.dumps(compact, ensure_ascii=False)
    return json.dumps(payload, ensure_ascii=False)


def _extract_mcp_result(call_result: Any) -> Any:
    data = getattr(call_result, "data", None)
    if data is not None:
        return data
    content = getattr(call_result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
    return {}


def run_deterministic_menu_pipeline(
    db: Session,
    household_id: uuid.UUID,
    for_date: date,
    meal: str = "dinner",
    monthly_budget_bdt: int = 15000,
) -> dict[str, Any]:
    """Run deterministic shared-pot + scoring + template explanations directly (zero LLM)."""
    ctx, recipes, recipes_by_id = load_rule_context_and_recipes(db)
    members = load_household_members(db, household_id)
    guests, away_ids, _ = load_day_events(db, household_id, for_date)
    shared = find_shared_pot_dishes(
        members=members,
        recipes=recipes,
        context=ctx,
        for_date=for_date,
        meal=meal,
        away_member_ids=away_ids,
        guests=guests,
    )
    stock = load_household_stock(db, household_id, ctx.ingredients)
    recent = load_recent_cooked_keys(db, household_id, for_date)
    user_prices = load_user_price_observations(db, household_id)
    ranked = score_dishes(
        candidates=shared.candidates,
        stock_map=stock,
        context=ctx,
        current_month=for_date.month,
        household_budget_bdt=monthly_budget_bdt,
        people_count=max(1, shared.people_count),
        recent_cooked_recipe_keys=recent,
        user_price_observations=user_prices,
        weights=get_settings().score_weights,
    )
    top_3 = ranked[:3]
    cands_by_id = {c.recipe.id: c for c in shared.candidates}
    explanations = {
        s.recipe.id: render_fallback_menu_item(cands_by_id[s.recipe.id])
        for s in top_3
        if s.recipe.id in cands_by_id
    }
    tool_log = [
        {"tool": "find_shared_pot_dishes", "args": {"household_id": str(household_id), "for_date": for_date.isoformat(), "meal": meal}, "result": shared.model_dump(mode="json")},
        {"tool": "score_dishes", "args": {"candidate_count": len(shared.candidates)}, "result": {"top_ids": [s.recipe.id for s in top_3]}},
    ]
    return {
        "shared": shared,
        "ranked": ranked,
        "top_3": top_3,
        "explanations_by_recipe": explanations,
        "tool_log": tool_log,
        "context": ctx,
        "recipes_by_id": recipes_by_id,
    }


async def run_menu_planning_agent(
    db: Session,
    household_id: uuid.UUID,
    for_date: date,
    meal: str,
    monthly_budget_bdt: int,
    llm_client: LLMClient | None,
    mcp_server: FastMCP,
    max_tool_calls: int = 6,
    user_request_text: str = "আজ কী রান্না করব?",
) -> dict[str, Any]:
    """Bounded Groq tool-calling loop over FastMCP whitelisted tools, validated with fallback."""
    # Always prepare deterministic baseline facts & fallback ready in O(recipes * people)
    baseline = run_deterministic_menu_pipeline(
        db=db,
        household_id=household_id,
        for_date=for_date,
        meal=meal,
        monthly_budget_bdt=monthly_budget_bdt,
    )
    shared = baseline["shared"]
    ranked: list[ScoredDish] = baseline["ranked"]
    top_3: list[ScoredDish] = baseline["top_3"]
    ctx = baseline["context"]
    recipes_by_id = baseline["recipes_by_id"]

    if llm_client is None or not top_3:
        return {
            "shared": shared,
            "top_3": top_3,
            "explanations_by_recipe": baseline["explanations_by_recipe"],
            "tool_log": baseline["tool_log"],
            "validated": True,
            "used_template": True,
            "used_fallback": True,
            "fallback_reason": "NO_LLM_CLIENT_OR_NO_CANDIDATES",
        }

    tool_log: list[dict[str, Any]] = []
    tool_calls_used = 0
    fallback_reason: str | None = None
    agent_final_json: dict[str, Any] | None = None

    try:
        async with Client(mcp_server) as client:
            mcp_tools = await client.list_tools()
            groq_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": getattr(t, "input_schema", None) or {"type": "object", "properties": {}},
                    },
                }
                for t in mcp_tools
                if t.name in READ_TOOL_WHITELIST
            ]

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Household ID: {household_id}\n"
                        f"Date: {for_date.isoformat()}\n"
                        f"Meal: {meal}\n"
                        f"User request: {user_request_text}\n"
                        f"Call find_shared_pot_dishes and score_dishes (max {max_tool_calls} tool calls), "
                        "then output final JSON for the top 3 safe dishes."
                    ),
                },
            ]

            for _ in range(max_tool_calls + 1):
                msg = llm_client.call_groq_tools(messages=messages, tools=groq_tools)
                if msg is None:
                    fallback_reason = "AGENT_LLM_CALL_FAILED"
                    break

                req_calls = getattr(msg, "tool_calls", None) or []
                if not req_calls:
                    raw_content = getattr(msg, "content", None) or ""
                    try:
                        agent_final_json = json.loads(_strip_json_fences(raw_content))
                    except Exception:
                        fallback_reason = "AGENT_INVALID_FINAL_JSON"
                    break

                # Record assistant turn
                messages.append(
                    {
                        "role": "assistant",
                        "content": getattr(msg, "content", None) or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in req_calls
                        ],
                    }
                )

                for tc in req_calls:
                    fn_name = tc.function.name
                    if fn_name not in READ_TOOL_WHITELIST:
                        fallback_reason = f"NON_WHITELISTED_TOOL:{fn_name}"
                        break
                    if tool_calls_used >= max_tool_calls:
                        fallback_reason = "MAX_TOOL_CALLS_EXCEEDED"
                        break

                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}

                    res = await client.call_tool(fn_name, args)
                    payload = _extract_mcp_result(res)
                    tool_calls_used += 1
                    tool_log.append({"tool": fn_name, "args": args, "result": payload})

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": _compact_tool_result_for_llm(fn_name, payload),
                        }
                    )

                if fallback_reason:
                    break
    except Exception as exc:
        fallback_reason = f"AGENT_RUNTIME_ERROR:{type(exc).__name__}"

    # Verify agent called find_shared_pot_dishes and passed strict core.validator
    has_shared_pot_tool = any(t["tool"] == "find_shared_pot_dishes" for t in tool_log)
    if fallback_reason or agent_final_json is None or not has_shared_pot_tool:
        return {
            "shared": shared,
            "top_3": top_3,
            "explanations_by_recipe": baseline["explanations_by_recipe"],
            "tool_log": tool_log or baseline["tool_log"],
            "validated": False,
            "used_template": True,
            "used_fallback": True,
            "fallback_reason": fallback_reason or "MISSING_TOOL_GROUNDING",
        }

    try:
        parsed_bi = BilingualExplanationOutput.model_validate(agent_final_json)
    except Exception:
        return {
            "shared": shared,
            "top_3": top_3,
            "explanations_by_recipe": baseline["explanations_by_recipe"],
            "tool_log": tool_log,
            "validated": False,
            "used_template": True,
            "used_fallback": True,
            "fallback_reason": "AGENT_SCHEMA_INVALID",
        }

    bn_payload = ExplanationOutput(
        items=[
            ExplanationItem(
                recipe_id=item.recipe_id,
                explanation_bn=item.explanation_bn,
                split_instruction_bn=item.split_instruction_bn,
                rule_ids=item.rule_ids,
            )
            for item in parsed_bi.items
        ]
    )
    val_res = validate_response(bn_payload, tool_log, ctx.ingredients, recipes_by_id)
    en_errs: list[str] = []
    for item in parsed_bi.items:
        en_errs.extend(_check_english_safety(item, recipes_by_id.get(item.recipe_id), ctx.ingredients))

    if not val_res.valid or en_errs:
        return {
            "shared": shared,
            "top_3": top_3,
            "explanations_by_recipe": baseline["explanations_by_recipe"],
            "tool_log": tool_log,
            "validated": False,
            "used_template": True,
            "used_fallback": True,
            "fallback_reason": ",".join(val_res.reasons + en_errs),
        }

    # Preserve agent-validated top 3 recipe order if matching scored candidates, else baseline top_3
    scored_by_id = {s.recipe.id: s for s in ranked}
    chosen_top: list[ScoredDish] = []
    for item in parsed_bi.items:
        if item.recipe_id in scored_by_id and scored_by_id[item.recipe_id] not in chosen_top:
            chosen_top.append(scored_by_id[item.recipe.id])
    for s in top_3:
        if len(chosen_top) >= 3:
            break
        if s not in chosen_top:
            chosen_top.append(s)

    explanations_by_id = dict(baseline["explanations_by_recipe"])
    for item in parsed_bi.items:
        explanations_by_id[item.recipe_id] = {
            "recipe_id": item.recipe_id,
            "explanation_bn": item.explanation_bn,
            "explanation_en": item.explanation_en,
            "split_instruction_bn": item.split_instruction_bn,
            "split_instruction_en": item.split_instruction_en,
            "rule_ids": item.rule_ids,
            "used_template": False,
        }

    return {
        "shared": shared,
        "top_3": chosen_top[:3],
        "explanations_by_recipe": explanations_by_id,
        "tool_log": tool_log,
        "validated": True,
        "used_template": False,
        "used_fallback": False,
        "fallback_reason": None,
    }
