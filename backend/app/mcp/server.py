"""FastMCP 4.x server registering all 13 deterministic Harbor tools (SPEC §11)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from fastmcp import FastMCP
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.core.bangla_qty import normalize_bangla_qty as core_normalize_bangla_qty
from app.core.bazar import (
    build_monthly_list as core_build_monthly_list,
    calculate_bazar_shortfall as core_calculate_bazar_shortfall,
    find_safe_substitute as core_find_safe_substitute,
)
from app.core.prices import get_price_estimate as core_get_price_estimate
from app.core.reminders import build_dose_schedule as core_build_dose_schedule
from app.core.rules import check_dish_safe as core_check_dish_safe
from app.core.scoring import score_dishes as core_score_dishes
from app.core.shared_pot import find_shared_pot_dishes as core_find_shared_pot_dishes
from app.db import SessionLocal
from app.deps import verify_confirmation_token
from app.models import (
    DoseSchedule,
    Household,
    HouseholdEvent,
    Ingredient,
    InventoryEvent,
    Medicine,
    Member,
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


def create_mcp_server(session_factory: sessionmaker = SessionLocal) -> FastMCP:
    """Create a FastMCP server exposing all 13 deterministic tools from SPEC §11."""
    mcp = FastMCP("harbor-core-tools")

    @mcp.tool
    def get_household_state(household_id: str, for_date: str) -> dict[str, Any]:
        """Return household members, present people, meal times, budget, and events for a date."""
        with session_factory() as db:
            hh_uuid = uuid.UUID(household_id)
            hh = db.scalar(select(Household).where(Household.id == hh_uuid))
            if hh is None:
                raise ValueError(f"Household {household_id} not found")
            target_date = date.fromisoformat(for_date)
            members = load_household_members(db, hh_uuid)
            guests, away_ids, raw_events = load_day_events(db, hh_uuid, target_date)
            present_people = [m.name for m in members if m.id not in away_ids]
            return {
                "household_id": str(hh.id),
                "name": hh.name,
                "for_date": target_date.isoformat(),
                "meal_times": hh.meal_times,
                "monthly_budget_bdt": hh.monthly_budget_bdt,
                "members": [m.model_dump() for m in members],
                "present_people": present_people,
                "away_member_ids": sorted(away_ids),
                "guests": [g.model_dump() for g in guests],
                "today_events": raw_events,
            }

    @mcp.tool
    def get_inventory(household_id: str) -> dict[str, Any]:
        """Return current event-sourced pantry stock and expiry flags for a household."""
        with session_factory() as db:
            hh_uuid = uuid.UUID(household_id)
            ctx, _, _ = load_rule_context_and_recipes(db)
            stock = load_household_stock(db, hh_uuid, ctx.ingredients)
            return {
                "household_id": household_id,
                "items": {
                    k: v.model_dump(mode="json")
                    for k, v in stock.items()
                    if v.qty_base > 0 or v.clamped_negative
                },
            }

    @mcp.tool
    def update_inventory_event(
        household_id: str,
        events: list[dict[str, Any]],
        confirmation_token: str = "",
    ) -> dict[str, Any]:
        """Write confirmed inventory/household events (requires valid caregiver confirmation_token)."""
        verify_confirmation_token(confirmation_token, household_id, "events_confirm")
        with session_factory() as db:
            hh_uuid = uuid.UUID(household_id)
            ing_by_key = {row.key: row for row in db.scalars(select(Ingredient)).all()}
            written_ids: list[str] = []
            for ev in events:
                ev_type = ev["type"]
                if ev_type in ("GUESTS", "GUESTS_CANCELLED", "MEMBER_AWAY", "OTHER"):
                    row = HouseholdEvent(
                        household_id=hh_uuid,
                        kind=ev_type,
                        for_date=date.fromisoformat(ev["for_date"]),
                        payload={
                            "guest_count": ev.get("guest_count", 0),
                            "restrictions": ev.get("guest_restrictions", []),
                            "member_id": ev.get("member_id"),
                        },
                    )
                    db.add(row)
                    db.flush()
                    written_ids.append(str(row.id))
                else:
                    ing = ing_by_key.get(ev["ingredient_key"])
                    if ing is None:
                        raise ValueError(f"Unknown ingredient_key: {ev.get('ingredient_key')}")
                    row = InventoryEvent(
                        household_id=hh_uuid,
                        event_type=ev_type,
                        ingredient_id=ing.id,
                        qty_base=Decimal(str(ev["qty_base"])),
                        source=ev.get("source", "ui"),
                        raw_text=ev.get("raw_text"),
                    )
                    db.add(row)
                    db.flush()
                    written_ids.append(str(row.id))
            db.commit()
            return {"written_event_ids": written_ids}

    @mcp.tool
    def normalize_bangla_qty(phrase: str, ingredient_key: str | None = None) -> dict[str, Any]:
        """Normalize a Bangla/Banglish/English quantity phrase into base units."""
        ing_data = None
        if ingredient_key:
            with session_factory() as db:
                ctx, _, _ = load_rule_context_and_recipes(db)
                ing_data = ctx.ingredients.get(ingredient_key)
        res = core_normalize_bangla_qty(phrase, ingredient=ing_data)
        return res.model_dump()

    @mcp.tool
    def check_dish_safe(member_id: str, recipe_id: str) -> dict[str, Any]:
        """Deterministically check whether one recipe is safe for one household member."""
        with session_factory() as db:
            m_uuid = uuid.UUID(member_id)
            member_row = db.scalar(select(Member).where(Member.id == m_uuid))
            if member_row is None:
                raise ValueError(f"Member {member_id} not found")
            members = load_household_members(db, member_row.household_id)
            target_member = next(m for m in members if m.id == member_id)
            ctx, recipes, recipes_by_id = load_rule_context_and_recipes(db)
            recipe = recipes_by_id.get(recipe_id) or next(
                (r for r in recipes if r.key == recipe_id), None
            )
            if recipe is None:
                raise ValueError(f"Recipe {recipe_id} not found")
            return core_check_dish_safe(target_member, recipe, ctx).model_dump()

    @mcp.tool
    def find_shared_pot_dishes(
        household_id: str,
        for_date: str,
        meal: str = "dinner",
    ) -> dict[str, Any]:
        """Evaluate every recipe across all eating household members and guests."""
        with session_factory() as db:
            hh_uuid = uuid.UUID(household_id)
            target_date = date.fromisoformat(for_date)
            ctx, recipes, _ = load_rule_context_and_recipes(db)
            members = load_household_members(db, hh_uuid)
            guests, away_ids, _ = load_day_events(db, hh_uuid, target_date)
            res = core_find_shared_pot_dishes(
                members=members,
                recipes=recipes,
                context=ctx,
                for_date=target_date,
                meal=meal,
                away_member_ids=away_ids,
                guests=guests,
            )
            return res.model_dump(mode="json")

    @mcp.tool
    def score_dishes(
        candidate_recipe_ids: list[str],
        household_id: str,
        for_date: str,
        meal: str = "dinner",
    ) -> dict[str, Any]:
        """Score and rank safe shared-pot candidate dishes for a household."""
        with session_factory() as db:
            hh_uuid = uuid.UUID(household_id)
            hh = db.scalar(select(Household).where(Household.id == hh_uuid))
            if hh is None:
                raise ValueError(f"Household {household_id} not found")
            target_date = date.fromisoformat(for_date)
            ctx, recipes, _ = load_rule_context_and_recipes(db)
            members = load_household_members(db, hh_uuid)
            guests, away_ids, _ = load_day_events(db, hh_uuid, target_date)
            shared = core_find_shared_pot_dishes(
                members=members,
                recipes=recipes,
                context=ctx,
                for_date=target_date,
                meal=meal,
                away_member_ids=away_ids,
                guests=guests,
            )
            allowed_set = set(candidate_recipe_ids)
            filtered_cands = [
                c
                for c in shared.candidates
                if not allowed_set or c.recipe.id in allowed_set or c.recipe.key in allowed_set
            ]
            stock = load_household_stock(db, hh_uuid, ctx.ingredients)
            recent = load_recent_cooked_keys(db, hh_uuid, target_date)
            user_prices = load_user_price_observations(db, hh_uuid)
            scored = core_score_dishes(
                candidates=filtered_cands,
                stock_map=stock,
                context=ctx,
                current_month=target_date.month,
                household_budget_bdt=hh.monthly_budget_bdt or 15000,
                people_count=max(1, shared.people_count),
                recent_cooked_recipe_keys=recent,
                user_price_observations=user_prices,
                weights=get_settings().score_weights,
                meal=meal,
                for_date=target_date,
            )
            return {"ranked": [s.model_dump(mode="json") for s in scored]}

    @mcp.tool
    def get_seasonal_items(month: int) -> dict[str, Any]:
        """Return ingredient keys that are in season for the given month (1..12)."""
        with session_factory() as db:
            ctx, _, _ = load_rule_context_and_recipes(db)
            in_season = [
                {"key": k, "name_bn": ing.name_bn, "name_en": ing.name_en}
                for k, ing in sorted(ctx.ingredients.items())
                if month in ing.season_months
            ]
            return {"month": month, "items": in_season}

    @mcp.tool
    def get_price_estimate(ingredient_key: str, household_id: str | None = None) -> dict[str, Any]:
        """Return approximate BDT price estimate (household purchase priority, else reference table)."""
        with session_factory() as db:
            ctx, _, _ = load_rule_context_and_recipes(db)
            ing = ctx.ingredients.get(ingredient_key)
            if ing is None:
                raise ValueError(f"Unknown ingredient: {ingredient_key}")
            user_obs = (
                load_user_price_observations(db, uuid.UUID(household_id))
                if household_id
                else None
            )
            return core_get_price_estimate(ing, user_observations=user_obs).model_dump(mode="json")

    @mcp.tool
    def calculate_bazar_shortfall(plan: list[dict[str, Any]], household_id: str) -> dict[str, Any]:
        """Calculate per-ingredient bazar shortfall against current household stock."""
        with session_factory() as db:
            hh_uuid = uuid.UUID(household_id)
            ctx, _, _ = load_rule_context_and_recipes(db)
            stock = load_household_stock(db, hh_uuid, ctx.ingredients)
            shortfall = core_calculate_bazar_shortfall(plan, stock)
            return {"shortfall": shortfall}

    @mcp.tool
    def find_safe_substitute(
        ingredient_key: str,
        household_id: str,
        planned_recipe_ids: list[str],
        month: int = 11,
    ) -> dict[str, Any]:
        """Find same-category substitutes verified safe across every member and planned recipe."""
        with session_factory() as db:
            hh_uuid = uuid.UUID(household_id)
            ctx, recipes, recipes_by_id = load_rule_context_and_recipes(db)
            members = load_household_members(db, hh_uuid)
            planned = [
                recipes_by_id[rid]
                for rid in planned_recipe_ids
                if rid in recipes_by_id
            ] or [
                r for r in recipes if r.key in set(planned_recipe_ids)
            ]
            user_obs = load_user_price_observations(db, hh_uuid)
            subs = core_find_safe_substitute(
                ingredient_key=ingredient_key,
                members=members,
                planned_recipes=planned,
                context=ctx,
                substitution_groups=load_substitution_groups(),
                current_month=month,
                user_price_observations=user_obs,
            )
            return {"substitutes": subs}

    @mcp.tool
    def build_monthly_list(household_id: str, month: str, budget_bdt: int) -> dict[str, Any]:
        """Generate simplified 30-day bazar list within budget with estimated prices and safe substitutes."""
        with session_factory() as db:
            hh_uuid = uuid.UUID(household_id)
            ctx, recipes, _ = load_rule_context_and_recipes(db)
            members = load_household_members(db, hh_uuid)
            stock = load_household_stock(db, hh_uuid, ctx.ingredients)
            user_obs = load_user_price_observations(db, hh_uuid)
            current_month = int(month.split("-")[1])
            return core_build_monthly_list(
                members=members,
                recipes=recipes,
                context=ctx,
                stock_map=stock,
                month=month,
                current_month=current_month,
                budget_bdt=budget_bdt,
                substitution_groups=load_substitution_groups(),
                user_price_observations=user_obs,
            )

    @mcp.tool
    def schedule_reminder(
        medicine_id: str,
        for_date: str,
        confirmation_token: str = "",
    ) -> dict[str, Any]:
        """Create dose_schedule rows for a caregiver-confirmed medicine (requires confirmation_token)."""
        with session_factory() as db:
            med_uuid = uuid.UUID(medicine_id)
            med = db.scalar(select(Medicine).where(Medicine.id == med_uuid))
            if med is None:
                raise ValueError(f"Medicine {medicine_id} not found")
            member = db.scalar(select(Member).where(Member.id == med.member_id))
            if member is None:
                raise ValueError("Member not found")
            verify_confirmation_token(
                confirmation_token,
                str(member.household_id),
                "prescription_confirm",
            )
            hh = db.scalar(select(Household).where(Household.id == member.household_id))
            if hh is None:
                raise ValueError("Household not found")
            from app.core.types import MedicineData

            med_data = MedicineData(
                id=str(med.id),
                name_as_written=med.name_as_written,
                generic_name=med.generic_name,
                drug_class=med.drug_class,
                timing=med.timing,
                meal_slots=list(med.meal_slots or []),
                verified_by_caregiver=med.verified_by_caregiver,
                active=med.active,
            )
            settings = get_settings()
            records = core_build_dose_schedule(
                medicine=med_data,
                member_id=str(member.id),
                member_name=member.name,
                meal_times=hh.meal_times,
                for_date=date.fromisoformat(for_date),
                offsets_min=settings.reminder_offsets,
                grace_minutes=settings.reminder_grace_minutes,
                tz_name=settings.tz,
            )
            created_ids: list[str] = []
            for rec in records:
                existing = db.scalar(
                    select(DoseSchedule).where(
                        DoseSchedule.medicine_id == med.id,
                        DoseSchedule.due_at == rec.due_at,
                    )
                )
                if existing is None:
                    row = DoseSchedule(
                        medicine_id=med.id,
                        due_at=rec.due_at,
                        window_end=rec.window_end,
                        status="pending",
                    )
                    db.add(row)
                    db.flush()
                    created_ids.append(str(row.id))
            db.commit()
            return {"created_dose_ids": created_ids, "count": len(created_ids)}

    return mcp


mcp = create_mcp_server(SessionLocal)
