"""Voice/text event parsing (Groq Whisper + LLM) and deterministic alias/qty resolution."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field
from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from app.core.bangla_qty import normalize_bangla_qty
from app.core.inventory import compute_adjust_delta
from app.core.types import IngredientData, StockItemState
from app.llm.client import LLMClient
from app.llm.prompts import EVENT_PARSE_SYSTEM_PROMPT


class ParsedEventRaw(BaseModel):
    type: Literal[
        "PURCHASED",
        "COOKED",
        "SPOILED",
        "ADJUST",
        "GUESTS",
        "GUESTS_CANCELLED",
        "MEMBER_AWAY",
    ]
    item_raw: str | None = Field(default=None, max_length=120)
    qty_phrase: str | None = Field(default=None, max_length=120)
    guest_count: int | None = Field(default=None, ge=0, le=100)
    for_date: str | None = Field(default=None, max_length=32)
    guest_restrictions: list[str] = Field(default_factory=list, max_length=20)


class EventParseOutput(BaseModel):
    events: list[ParsedEventRaw] = Field(default_factory=list, max_length=20)


def resolve_ingredient_alias(
    item_raw: str | None,
    aliases_map: dict[str, IngredientData],
) -> tuple[IngredientData | None, float]:
    """Match raw Bangla/Banglish/English item name against aliases_map using rapidfuzz >= 85."""
    if not item_raw or not item_raw.strip() or not aliases_map:
        return None, 0.0

    cleaned = item_raw.strip().lower()
    if cleaned in aliases_map:
        return aliases_map[cleaned], 1.0

    # Also check exact stripped match against keys
    lower_lookup = {k.lower(): v for k, v in aliases_map.items()}
    if cleaned in lower_lookup:
        return lower_lookup[cleaned], 1.0

    match = process.extractOne(
        cleaned,
        list(lower_lookup.keys()),
        scorer=fuzz.WRatio,
        score_cutoff=85,
    )
    if match:
        matched_alias, score, _ = match
        return lower_lookup[matched_alias], round(score / 100.0, 2)

    return None, 0.0


def _resolve_date_str(raw_date: str | None, today: date) -> str:
    if not raw_date or not raw_date.strip():
        return today.isoformat()
    cleaned = raw_date.strip().lower()
    if cleaned in ("today", "আজ", "aj", "ajke", "আজকে"):
        return today.isoformat()
    if cleaned in ("tomorrow", "কাল", "আগামীকাল", "kal", "agamikal"):
        return (today + timedelta(days=1)).isoformat()
    try:
        parsed = date.fromisoformat(raw_date.strip()[:10])
        return parsed.isoformat()
    except ValueError:
        return today.isoformat()


def resolve_event_proposals(
    parsed: EventParseOutput,
    aliases_map: dict[str, IngredientData],
    stock_map: dict[str, StockItemState],
    today: date,
) -> list[dict[str, Any]]:
    """Deterministically resolve LLM raw phrases into typed, reviewable event chips."""
    proposals: list[dict[str, Any]] = []

    for ev in parsed.events:
        proposal_id = str(uuid.uuid4())
        resolved_date = _resolve_date_str(ev.for_date, today)

        if ev.type in ("GUESTS", "GUESTS_CANCELLED", "MEMBER_AWAY"):
            proposals.append(
                {
                    "proposal_id": proposal_id,
                    "type": ev.type,
                    "item_raw": ev.item_raw,
                    "qty_phrase": ev.qty_phrase,
                    "ingredient_key": None,
                    "ingredient_name_bn": None,
                    "ingredient_name_en": None,
                    "qty_base": None,
                    "unit_base": None,
                    "confidence": 0.95,
                    "needs_review": False,
                    "guest_count": ev.guest_count,
                    "for_date": resolved_date,
                    "guest_restrictions": ev.guest_restrictions,
                    "note": "Household schedule event",
                }
            )
            continue

        ing, alias_conf = resolve_ingredient_alias(ev.item_raw, aliases_map)
        current_stock = stock_map[ing.key].qty_base if (ing and ing.key in stock_map) else 0.0
        last_known = current_stock if (ing and ing.key in stock_map and stock_map[ing.key].last_purchased_at) else (current_stock or None)

        qty_res = normalize_bangla_qty(
            ev.qty_phrase or "",
            ingredient=ing,
            last_known_stock=last_known,
        )

        signed_qty: float | None = None
        unit_base = qty_res.unit_base or (ing.base_unit if ing else None)
        needs_review = ing is None or qty_res.needs_review

        if ev.type == "ADJUST":
            if qty_res.is_relative_target:
                if qty_res.target_ratio == 0.0:
                    signed_qty = compute_adjust_delta(current_stock, 0.0)
                elif last_known is not None and qty_res.qty_base is not None:
                    signed_qty = compute_adjust_delta(current_stock, qty_res.qty_base)
                else:
                    # Unknown prior stock: fallback small delta placeholder and flag review
                    signed_qty = 0.0
                    needs_review = True
            elif qty_res.qty_base is not None:
                signed_qty = compute_adjust_delta(current_stock, qty_res.qty_base)
        elif ev.type == "PURCHASED":
            signed_qty = abs(qty_res.qty_base) if qty_res.qty_base is not None else None
        elif ev.type in ("COOKED", "SPOILED"):
            if qty_res.qty_base is not None:
                # If user said "half of a gourd" (0.5 piece) for a gram-based vegetable, estimate from stock or 500g and flag review
                if qty_res.unit_base == "piece" and ing is not None and ing.base_unit != "piece":
                    approx_whole = current_stock if current_stock > 0 else 1000.0
                    signed_qty = -round(approx_whole * qty_res.qty_base, 3)
                    unit_base = ing.base_unit
                    needs_review = True
                else:
                    signed_qty = -abs(qty_res.qty_base)

        if signed_qty is None:
            needs_review = True

        proposals.append(
            {
                "proposal_id": proposal_id,
                "type": ev.type,
                "item_raw": ev.item_raw,
                "qty_phrase": ev.qty_phrase,
                "ingredient_key": ing.key if ing else None,
                "ingredient_name_bn": ing.name_bn if ing else None,
                "ingredient_name_en": ing.name_en if ing else None,
                "qty_base": signed_qty,
                "unit_base": unit_base,
                "confidence": round(min(alias_conf or 0.3, qty_res.confidence or 0.3), 2),
                "needs_review": needs_review,
                "guest_count": None,
                "for_date": resolved_date,
                "guest_restrictions": [],
                "note": "চেনা যায়নি, তালিকা থেকে বেছে নিন" if ing is None else qty_res.note,
            }
        )

    return proposals


def parse_events_from_text(
    raw_text: str,
    llm_client: LLMClient,
    aliases_map: dict[str, IngredientData],
    stock_map: dict[str, StockItemState],
    today: date,
    db: Session | None = None,
) -> dict[str, Any]:
    """Parse raw Bangla/Banglish/English text into resolved event proposals (never auto-written)."""
    user_prompt = (
        f"Reference today date: {today.isoformat()}\n"
        f"Input text: {raw_text.strip()}\n"
        "Extract events as JSON."
    )
    parsed = llm_client.call_groq_json(
        task="parse_events",
        system_prompt=EVENT_PARSE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema_cls=EventParseOutput,
        db=db,
        input_summary=raw_text[:200],
        model_override=llm_client.llm_fast_model,
        max_completion_tokens=600,
    )
    if parsed is None:
        return {
            "raw_text": raw_text,
            "proposals": [],
            "parse_failed": True,
        }

    proposals = resolve_event_proposals(parsed, aliases_map, stock_map, today)
    return {
        "raw_text": raw_text,
        "proposals": proposals,
        "parse_failed": False,
    }
