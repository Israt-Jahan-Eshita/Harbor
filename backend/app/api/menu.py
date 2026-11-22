"""Daily menu suggest, guest/absence review, and cooked logging endpoints (B15)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from fastmcp import FastMCP
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import get_db
from app.deps import enforce_rate_limit, get_current_household
from app.errors import AppError
from app.llm.agent import run_deterministic_menu_pipeline, run_menu_planning_agent
from app.llm.client import LLMClient
from app.llm.explain import generate_grounded_explanations
from app.mcp.server import create_mcp_server
from app.models import Household, HouseholdEvent, Ingredient, InventoryEvent, MenuSuggestion, Recipe
from app.schemas import MenuCookedRequest, MenuReviewRequest, MenuSuggestRequest
from app.services.context_loader import load_rule_context_and_recipes

router = APIRouter(prefix="/menu", tags=["menu"])


def get_llm_client() -> LLMClient:
    return LLMClient()


def get_mcp_server(db: Session = Depends(get_db)) -> FastMCP:
    """Create FastMCP server bound to the active request's SQLAlchemy engine."""
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind(), class_=Session)
    return create_mcp_server(factory)


def _format_menu_response(
    for_date: date,
    meal: str,
    pipeline_out: dict[str, Any],
) -> dict[str, Any]:
    shared = pipeline_out["shared"]
    top_3 = pipeline_out["top_3"]
    explanations = pipeline_out["explanations_by_recipe"]

    top_cards = []
    for scored in top_3:
        rec = scored.recipe
        exp = explanations.get(rec.id, {})
        top_cards.append(
            {
                "recipe_id": rec.id,
                "key": rec.key,
                "name_bn": rec.name_bn,
                "name_en": rec.name_en,
                "category": rec.category,
                "servings_base": rec.servings_base,
                "scaled_servings": max(1, shared.people_count),
                "status": scored.status,
                "split_for": scored.split_for,
                "split_step_bn": scored.split_step_bn,
                "reasons": scored.reasons,
                "score": scored.score,
                "components": scored.components,
                "missing_ingredients": scored.missing_ingredients,
                "shortfall_cost_bdt": scored.shortfall_cost_bdt,
                "explanation_bn": exp.get("explanation_bn", ""),
                "explanation_en": exp.get("explanation_en", ""),
                "split_instruction_bn": exp.get("split_instruction_bn"),
                "split_instruction_en": exp.get("split_instruction_en"),
                "rule_ids": exp.get("rule_ids", scored.reasons or ["SAFE_DIRECT"]),
                "used_template": exp.get("used_template", True),
            }
        )

    excluded_cards = []
    for excl in shared.excluded:
        bad_details = [
            {
                "member_name": mr.member_name,
                "status": mr.status,
                "reasons": mr.reasons,
                "trace": mr.trace,
            }
            for mr in excl.member_results
            if mr.status in ("BLOCKED", "UNVERIFIED")
        ]
        excluded_cards.append(
            {
                "recipe_id": excl.recipe.id,
                "key": excl.recipe.key,
                "name_bn": excl.recipe.name_bn,
                "name_en": excl.recipe.name_en,
                "reasons": excl.reasons,
                "member_details": bad_details,
            }
        )

    return {
        "for_date": for_date.isoformat(),
        "meal": meal,
        "people_count": shared.people_count,
        "present_member_names": shared.present_member_names,
        "guest_count": shared.guest_count,
        "total_candidates": len(shared.candidates),
        "top_3": top_cards,
        "excluded": excluded_cards,
        "validated": pipeline_out.get("validated", True),
        "used_template": pipeline_out.get("used_template", True),
        "used_fallback": pipeline_out.get("used_fallback", False),
    }


@router.post(
    "/suggest",
    dependencies=[Depends(enforce_rate_limit("menu_suggest", max_calls=30, window_seconds=60))],
)
async def suggest_menu(
    payload: MenuSuggestRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
    mcp_server: FastMCP = Depends(get_mcp_server),
):
    budget = hh.monthly_budget_bdt or 15000
    if payload.use_agent and llm_client.groq_api_key:
        out = await run_menu_planning_agent(
            db=db,
            household_id=hh.id,
            for_date=payload.for_date,
            meal=payload.meal,
            monthly_budget_bdt=budget,
            llm_client=llm_client,
            mcp_server=mcp_server,
        )
    else:
        det = run_deterministic_menu_pipeline(
            db=db,
            household_id=hh.id,
            for_date=payload.for_date,
            meal=payload.meal,
            monthly_budget_bdt=budget,
        )
        cands_by_id = {c.recipe.id: c for c in det["shared"].candidates}
        if llm_client.groq_api_key and payload.use_agent:
            exp_res = generate_grounded_explanations(
                det["top_3"],
                cands_by_id,
                det["tool_log"],
                det["context"].ingredients,
                det["recipes_by_id"],
                llm_client,
                db=db,
            )
            det["explanations_by_recipe"] = exp_res["explanations_by_recipe"]
            det["validated"] = exp_res["validated"]
            det["used_template"] = exp_res["used_template"]
        else:
            det["validated"] = True
            det["used_template"] = True
        det["used_fallback"] = False
        out = det

    response_payload = _format_menu_response(payload.for_date, payload.meal, out)

    db.add(
        MenuSuggestion(
            household_id=hh.id,
            for_date=payload.for_date,
            meal=payload.meal,
            payload={"top_keys": [c["key"] for c in response_payload["top_3"]]},
            validated=bool(response_payload["validated"]),
            used_template=bool(response_payload["used_template"]),
        )
    )
    db.commit()
    return response_payload


@router.post("/review")
async def review_menu(
    payload: MenuReviewRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
    mcp_server: FastMCP = Depends(get_mcp_server),
):
    """Apply guest / member-away changes for for_date and recalculate menu."""
    if payload.guest_count > 0:
        db.add(
            HouseholdEvent(
                household_id=hh.id,
                kind="GUESTS",
                for_date=payload.for_date,
                payload={
                    "guest_count": payload.guest_count,
                    "restrictions": payload.guest_restrictions,
                },
            )
        )
    else:
        db.add(
            HouseholdEvent(
                household_id=hh.id,
                kind="GUESTS_CANCELLED",
                for_date=payload.for_date,
                payload={},
            )
        )

    for mid in payload.away_member_ids:
        db.add(
            HouseholdEvent(
                household_id=hh.id,
                kind="MEMBER_AWAY",
                for_date=payload.for_date,
                payload={"member_id": mid},
            )
        )

    db.commit()

    suggest_req = MenuSuggestRequest(for_date=payload.for_date, meal=payload.meal, use_agent=bool(llm_client.groq_api_key))
    return await suggest_menu(suggest_req, hh=hh, db=db, llm_client=llm_client, mcp_server=mcp_server)


@router.post("/cooked")
def mark_menu_cooked(
    payload: MenuCookedRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    """Log negative COOKED inventory events for scaled recipe quantities and trigger 7-day repeat penalty."""
    recipe = None
    try:
        rid_uuid = uuid.UUID(payload.recipe_id)
        recipe = db.scalar(select(Recipe).where(Recipe.id == rid_uuid))
    except ValueError:
        recipe = db.scalar(select(Recipe).where(Recipe.key == payload.recipe_id))

    if recipe is None:
        raise AppError("RECIPE_NOT_FOUND", "Recipe not found.", status_code=404)

    ing_by_key = {row.key: row for row in db.scalars(select(Ingredient)).all()}
    scale = payload.servings / max(1, recipe.servings_base)
    written = 0

    for item in recipe.ingredients or []:
        ing_obj = ing_by_key.get(item["ingredient_key"])
        if ing_obj is None:
            continue
        used_qty = -round(float(item["qty"]) * scale, 3)
        db.add(
            InventoryEvent(
                household_id=hh.id,
                event_type="COOKED",
                ingredient_id=ing_obj.id,
                qty_base=Decimal(str(used_qty)),
                source="ui",
                raw_text=f"cooked_recipe:{recipe.key}",
            )
        )
        written += 1

    db.add(
        MenuSuggestion(
            household_id=hh.id,
            for_date=payload.for_date,
            meal="dinner",
            payload={"cooked_recipe_key": recipe.key, "servings": payload.servings},
            validated=True,
            used_template=True,
        )
    )
    db.commit()
    return {
        "cooked_recipe_key": recipe.key,
        "recipe_name_bn": recipe.name_bn,
        "servings": payload.servings,
        "inventory_events_written": written,
    }
