"""Daily menu suggest, guest/absence review, and cooked logging endpoints (B15)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from fastmcp import FastMCP
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from app.config import get_settings
from app.core.scoring import score_dishes
from app.core.shared_pot import find_shared_pot_dishes
from app.core.templates import render_fallback_menu_item
from app.core.types import GuestEventData
from app.core.weekly_plan import build_weekly_meal_plan, recalculate_weekly_plan_totals
from app.db import get_db
from app.deps import enforce_rate_limit, get_current_household
from app.errors import AppError
from app.llm.agent import run_deterministic_menu_pipeline, run_menu_planning_agent
from app.llm.client import LLMClient
from app.llm.explain import generate_grounded_explanations
from app.mcp.server import create_mcp_server
from app.models import (
    BazarList,
    Household,
    HouseholdEvent,
    Ingredient,
    InventoryEvent,
    MenuSuggestion,
    Recipe,
    WeeklyPlan,
)
from app.schemas import (
    MenuCookedRequest,
    MenuReviewRequest,
    MenuSuggestRequest,
    WeeklyPlanRequest,
    WeeklySlotUpdateRequest,
)
from app.services.context_loader import (
    load_day_events,
    load_household_members,
    load_household_stock,
    load_recent_cooked_keys,
    load_rule_context_and_recipes,
    load_substitution_groups,
    load_user_price_observations,
)

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
                "ingredient_conflicts": [c.model_dump(mode="json") for c in excl.ingredient_conflicts],
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
        "conflict_summary": (
            shared.conflict_summary.model_dump(mode="json") if shared.conflict_summary else None
        ),
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
    budget = (
        hh.monthly_budget_bdt
        if hh.monthly_budget_bdt is not None
        else get_settings().default_monthly_budget_bdt
    )
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
        if payload.use_llm_explain and llm_client.groq_api_key and det["top_3"]:
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


@router.post(
    "/review",
    dependencies=[Depends(enforce_rate_limit("menu_review", max_calls=15, window_seconds=60))],
)
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

    suggest_req = MenuSuggestRequest(
        for_date=payload.for_date,
        meal=payload.meal,
        use_agent=payload.use_agent,
        use_llm_explain=payload.use_llm_explain,
    )
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
            meal=payload.meal,
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


class _WeeklyCoachSummary(BaseModel):
    coach_summary_bn: str = Field(..., min_length=10, max_length=600)
    coach_summary_en: str = Field(..., min_length=10, max_length=600)


def _format_weekly_plan_row(row: WeeklyPlan) -> dict[str, Any]:
    return {
        "plan_id": str(row.id),
        "status": row.status,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        **(row.plan_payload or {}),
    }


@router.post(
    "/week/plan",
    dependencies=[Depends(enforce_rate_limit("menu_week_plan", max_calls=20, window_seconds=60))],
)
def generate_weekly_plan_endpoint(
    payload: WeeklyPlanRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
):
    """Generate and persist a consolidated whole-week (days x 3 meals) safe household plan."""
    settings = get_settings()
    budget = hh.monthly_budget_bdt if hh.monthly_budget_bdt is not None else settings.default_monthly_budget_bdt
    ctx, recipes, _ = load_rule_context_and_recipes(db)
    members = load_household_members(db, hh.id)
    stock = load_household_stock(db, hh.id, ctx.ingredients)
    user_prices = load_user_price_observations(db, hh.id)
    recent = load_recent_cooked_keys(db, hh.id, payload.start_date)
    sub_groups = load_substitution_groups()

    overrides_by_date = {ov.for_date: ov for ov in payload.day_overrides}
    day_events_map: dict[date, tuple[list[GuestEventData], set[str]]] = {}
    for off in range(payload.days):
        d = payload.start_date + timedelta(days=off)
        guests, away_ids, _ = load_day_events(db, hh.id, d)
        if d in overrides_by_date:
            ov = overrides_by_date[d]
            guests = (
                [GuestEventData(guest_count=ov.guest_count, restrictions=ov.guest_restrictions)]
                if ov.guest_count > 0
                else []
            )
            away_ids = set(ov.away_member_ids)
        day_events_map[d] = (guests, away_ids)

    plan_payload = build_weekly_meal_plan(
        members=members,
        recipes=recipes,
        context=ctx,
        stock_map=stock,
        start_date=payload.start_date,
        days=payload.days,
        household_budget_bdt=budget,
        meal_times=hh.meal_times,
        day_events_by_date=day_events_map,
        initial_recent_keys=recent,
        locked_slots=payload.locked_slots,
        substitution_groups=sub_groups,
        user_price_observations=user_prices,
        weights=settings.score_weights,
    )

    if payload.use_ai_summary and llm_client.groq_api_key:
        coach_prompt = (
            f"Household: {hh.name}\n"
            f"Period: {plan_payload['start_date']} to {plan_payload['end_date']} ({plan_payload['days_count']} days)\n"
            f"Safe slots: {plan_payload['safe_slots_count']}/{plan_payload['total_slots']}, "
            f"Split-pot slots: {plan_payload['split_slots_count']}, "
            f"Unique dishes: {plan_payload['unique_dishes_count']}\n"
            f"Estimated 7-day bazar shortfall: {plan_payload['est_weekly_shortfall_bdt']} BDT "
            f"(target {plan_payload['weekly_budget_target_bdt']} BDT)\n"
            f"Ingredient conflicts resolved deterministically: {len(plan_payload['conflict_matrix'])}\n"
            "Write a calm 2-sentence Bangla summary (`coach_summary_bn`) and 2-sentence English summary (`coach_summary_en`) "
            "grounded strictly in these exact verified figures. Never invent medicine doses or extra numbers. "
            'Output JSON: {"coach_summary_bn": "...", "coach_summary_en": "..."}'
        )
        ai_sum = llm_client.call_groq_json(
            task="weekly_coach_summary",
            system_prompt="You write brief, factual bilingual caregiver summaries strictly grounded in provided verified plan stats.",
            user_prompt=coach_prompt,
            schema_cls=_WeeklyCoachSummary,
            db=db,
            temperature=0.1,
            model_override=settings.llm_fast_model,
            max_completion_tokens=300,
        )
        if ai_sum is not None:
            plan_payload["coach_summary_bn"] = ai_sum.coach_summary_bn
            plan_payload["coach_summary_en"] = ai_sum.coach_summary_en
            plan_payload["used_ai_summary"] = True

    row = WeeklyPlan(
        household_id=hh.id,
        start_date=payload.start_date,
        end_date=payload.start_date + timedelta(days=payload.days - 1),
        status="draft",
        plan_payload=plan_payload,
        est_shortfall_bdt=Decimal(str(plan_payload["est_weekly_shortfall_bdt"])),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _format_weekly_plan_row(row)


@router.get("/week/latest")
def get_latest_weekly_plan(
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    """Return the most recently generated weekly meal plan for this household."""
    row = db.scalar(
        select(WeeklyPlan)
        .where(WeeklyPlan.household_id == hh.id)
        .order_by(WeeklyPlan.created_at.desc())
        .limit(1)
    )
    if row is None:
        return {"plan": None}
    return {"plan": _format_weekly_plan_row(row)}


@router.patch("/week/{plan_id}/slot")
def update_weekly_plan_slot(
    plan_id: str,
    payload: WeeklySlotUpdateRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    """Swap or lock one meal slot inside a weekly plan after enforcing deterministic safety rules."""
    try:
        pid = uuid.UUID(plan_id)
    except ValueError as exc:
        raise AppError("INVALID_PLAN_ID", "Invalid weekly plan ID.", status_code=400) from exc

    row = db.scalar(
        select(WeeklyPlan).where(WeeklyPlan.id == pid, WeeklyPlan.household_id == hh.id)
    )
    if row is None:
        raise AppError("WEEKLY_PLAN_NOT_FOUND", "Weekly plan not found.", status_code=404)

    plan_data = dict(row.plan_payload or {})
    target_date_str = payload.for_date.isoformat()
    day_entry = next((d for d in plan_data.get("days", []) if d.get("for_date") == target_date_str), None)
    if day_entry is None:
        raise AppError("DAY_NOT_IN_PLAN", f"Date {target_date_str} not found in weekly plan.", status_code=404)

    slot_entry = next((s for s in day_entry.get("slots", []) if s.get("meal") == payload.meal), None)
    if slot_entry is None:
        raise AppError("SLOT_NOT_FOUND", f"Meal slot {payload.meal} not found.", status_code=404)

    ctx, recipes, _ = load_rule_context_and_recipes(db)
    recipes_by_key = {r.key: r for r in recipes}
    members = load_household_members(db, hh.id)
    stock = load_household_stock(db, hh.id, ctx.ingredients)
    user_prices = load_user_price_observations(db, hh.id)
    settings = get_settings()
    budget = hh.monthly_budget_bdt if hh.monthly_budget_bdt is not None else settings.default_monthly_budget_bdt

    if payload.recipe_key is not None:
        guests, away_ids, _ = load_day_events(db, hh.id, payload.for_date)
        shared = find_shared_pot_dishes(
            members=members,
            recipes=recipes,
            context=ctx,
            for_date=payload.for_date,
            meal=payload.meal,
            away_member_ids=away_ids,
            guests=guests,
            substitution_groups=load_substitution_groups(),
            user_price_observations=user_prices,
        )
        cand = next((c for c in shared.candidates if c.recipe.key == payload.recipe_key), None)
        if cand is None:
            excl = next((e for e in shared.excluded if e.recipe.key == payload.recipe_key), None)
            if excl is None and payload.recipe_key not in recipes_by_key:
                raise AppError("RECIPE_NOT_FOUND", "Recipe not found.", status_code=404)
            raise AppError(
                "UNSAFE_SLOT_SWAP",
                f"Cannot place '{payload.recipe_key}' on {target_date_str} {payload.meal}: blocked by household safety rules.",
                status_code=400,
                details={
                    "reasons": excl.reasons if excl else ["EXCLUDED"],
                    "ingredient_conflicts": (
                        [c.model_dump(mode="json") for c in excl.ingredient_conflicts] if excl else []
                    ),
                },
            )

        tpl = render_fallback_menu_item(cand)
        scored = score_dishes(
            candidates=shared.candidates,
            stock_map=stock,
            context=ctx,
            current_month=payload.for_date.month,
            household_budget_bdt=budget,
            people_count=max(1, shared.people_count),
            recent_cooked_recipe_keys=set(),
            user_price_observations=user_prices,
            weights=settings.score_weights,
            meal=payload.meal,
            for_date=payload.for_date,
        )
        slot_entry["recipe_id"] = cand.recipe.id
        slot_entry["recipe_key"] = cand.recipe.key
        slot_entry["name_bn"] = cand.recipe.name_bn
        slot_entry["name_en"] = cand.recipe.name_en
        slot_entry["category"] = cand.recipe.category
        slot_entry["scaled_servings"] = max(1, shared.people_count)
        slot_entry["status"] = cand.status
        slot_entry["split_for"] = list(cand.split_for)
        slot_entry["split_step_bn"] = cand.split_step_bn
        slot_entry["reasons"] = list(cand.reasons)
        slot_entry["explanation_bn"] = tpl["explanation_bn"]
        slot_entry["explanation_en"] = tpl["explanation_en"]
        slot_entry["lock_overridden"] = False
        slot_entry["lock_override_reason_bn"] = None
        slot_entry["alternatives"] = [
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
            if alt.recipe.key != cand.recipe.key
        ][:5]

    if payload.locked is not None:
        slot_entry["locked"] = payload.locked

    updated_payload = recalculate_weekly_plan_totals(
        plan_payload=plan_data,
        recipes_by_key=recipes_by_key,
        context=ctx,
        stock_map=stock,
        household_budget_bdt=budget,
        user_price_observations=user_prices,
    )
    row.plan_payload = updated_payload
    flag_modified(row, "plan_payload")
    row.est_shortfall_bdt = Decimal(str(updated_payload["est_weekly_shortfall_bdt"]))
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _format_weekly_plan_row(row)


@router.post("/week/{plan_id}/to-bazar")
def convert_weekly_plan_to_bazar(
    plan_id: str,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    """Create a draft BazarList directly from this weekly plan's consolidated 7-day shortfall."""
    try:
        pid = uuid.UUID(plan_id)
    except ValueError as exc:
        raise AppError("INVALID_PLAN_ID", "Invalid weekly plan ID.", status_code=400) from exc

    row = db.scalar(
        select(WeeklyPlan).where(WeeklyPlan.id == pid, WeeklyPlan.household_id == hh.id)
    )
    if row is None:
        raise AppError("WEEKLY_PLAN_NOT_FOUND", "Weekly plan not found.", status_code=404)

    settings = get_settings()
    budget = hh.monthly_budget_bdt if hh.monthly_budget_bdt is not None else settings.default_monthly_budget_bdt
    shortfall_items = (row.plan_payload or {}).get("shortfall_items", [])
    bazar_items = [
        {
            "ingredient_key": it["ingredient_key"],
            "name_bn": it["name_bn"],
            "qty": it["qty"],
            "unit": it["unit"],
            "est_price_bdt": it["est_price_bdt"],
            "price_source": it.get("price_source", "reference_table"),
            "missing_price": bool(it.get("missing_price", False)),
            "is_estimated": bool(it.get("is_estimated", True)),
            "label_bn": "আনুমানিক",
            "in_season": bool(it.get("in_season", True)),
            "substitute_used": False,
            "substituted_from": None,
            "dropped": False,
            "flag": f"সাপ্তাহিক মেনু ({row.start_date.isoformat()} – {row.end_date.isoformat()})",
            "category": it.get("category", "other"),
        }
        for it in shortfall_items
    ]
    est_total = round(sum(float(i["est_price_bdt"]) for i in bazar_items), 2)
    bl = BazarList(
        household_id=hh.id,
        month=row.start_date.strftime("%Y-%m"),
        budget_bdt=budget,
        items=bazar_items,
        est_total_bdt=Decimal(str(est_total)),
        status="draft",
    )
    db.add(bl)
    row.status = "confirmed"
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(bl)
    return {
        "bazar_list_id": str(bl.id),
        "month": bl.month,
        "items_count": len(bazar_items),
        "est_total_bdt": est_total,
    }
