"""Voice/text event parsing and caregiver-confirmed inventory/household event commits (B14)."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import (
    compute_payload_digest,
    enforce_rate_limit,
    get_current_household,
    sign_confirmation_token,
    verify_confirmation_token,
)
from app.errors import AppError
from app.llm.client import LLMClient
from app.llm.parse_events import parse_events_from_text
from app.models import Household, HouseholdEvent, Ingredient, InventoryEvent
from app.schemas import EventParseTextRequest, EventsConfirmRequest
from app.services.context_loader import (
    load_aliases_map,
    load_household_stock,
    load_rule_context_and_recipes,
)

router = APIRouter(prefix="/events", tags=["events"])

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB


def get_llm_client() -> LLMClient:
    return LLMClient()


@router.post(
    "/parse",
    dependencies=[Depends(enforce_rate_limit("events_parse", max_calls=25, window_seconds=60))],
)
async def parse_events_endpoint(
    request: Request,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
):
    """Parse typed text JSON `{text}` or multipart `audio` upload into confirmable event chips."""
    content_type = (request.headers.get("content-type") or "").lower()
    raw_text = ""
    input_source = "text"

    if "multipart/form-data" in content_type:
        form = await request.form()
        text_field = form.get("text")
        audio_field = form.get("audio")
        if audio_field is not None and hasattr(audio_field, "read"):
            if not hh.consent_given:
                raise AppError(
                    "CONSENT_REQUIRED",
                    "Caregiver consent is required before uploading voice recordings to third-party AI APIs.",
                    status_code=403,
                )
            audio_bytes = await audio_field.read()
            if not audio_bytes or len(audio_bytes) > MAX_AUDIO_BYTES:
                raise AppError("INVALID_AUDIO", "Audio file must be non-empty and under 10 MB.", status_code=400)
            filename = getattr(audio_field, "filename", None) or "voice.webm"
            try:
                transcript = llm_client.transcribe_audio(audio_bytes, filename=filename, language="bn", db=db)
            finally:
                del audio_bytes
            if not transcript:
                raise AppError(
                    "STT_FAILED",
                    "Could not transcribe voice recording. Please type your update.",
                    status_code=502,
                )
            raw_text = transcript
            input_source = "voice"
        elif isinstance(text_field, str) and text_field.strip():
            raw_text = text_field.strip()
        else:
            raise AppError("EMPTY_INPUT", "Provide either text or audio.", status_code=400)
    else:
        try:
            body_json = await request.json()
            parsed_req = EventParseTextRequest.model_validate(body_json)
            raw_text = parsed_req.text.strip()
        except Exception as exc:
            raise AppError("INVALID_INPUT", "Expected JSON with non-empty 'text' field.", status_code=400) from exc

    settings = get_settings()
    today = datetime.now(ZoneInfo(settings.tz)).date()
    ctx, _, _ = load_rule_context_and_recipes(db)
    aliases_map = load_aliases_map(db, ctx.ingredients)
    stock_map = load_household_stock(db, hh.id, ctx.ingredients)

    parsed_res = parse_events_from_text(
        raw_text=raw_text,
        llm_client=llm_client,
        aliases_map=aliases_map,
        stock_map=stock_map,
        today=today,
        db=db,
    )
    db.commit()  # commit llm_calls audit record only; NO inventory/household events written yet!

    confirmation_token = sign_confirmation_token(
        str(hh.id),
        "events_confirm",
        compute_payload_digest({"raw_text": raw_text, "count": len(parsed_res["proposals"])}),
    )

    return {
        "raw_text": parsed_res["raw_text"],
        "source": input_source,
        "audio_stored": False,
        "proposals": parsed_res["proposals"],
        "parse_failed": parsed_res["parse_failed"],
        "confirmation_token": confirmation_token,
    }


@router.post("/confirm")
def confirm_events(
    payload: EventsConfirmRequest,
    hh: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    """Write caregiver-confirmed inventory & household events and compute stock deltas."""
    verify_confirmation_token(payload.confirmation_token, str(hh.id), "events_confirm")

    settings = get_settings()
    today = datetime.now(ZoneInfo(settings.tz)).date()
    ing_by_key = {row.key: row for row in db.scalars(select(Ingredient)).all()}
    ctx, _, _ = load_rule_context_and_recipes(db)
    before_stock = load_household_stock(db, hh.id, ctx.ingredients)

    written_ids: list[str] = []
    menu_stale = False
    touched_keys: set[str] = set()

    for ev in payload.events:
        ev_date = ev.for_date or today
        if ev.type in ("GUESTS", "GUESTS_CANCELLED", "MEMBER_AWAY"):
            hhe = HouseholdEvent(
                household_id=hh.id,
                kind=ev.type,
                for_date=ev_date,
                payload={
                    "guest_count": ev.guest_count or 0,
                    "restrictions": ev.guest_restrictions,
                    "member_id": ev.member_id,
                },
            )
            db.add(hhe)
            db.flush()
            written_ids.append(str(hhe.id))
            if ev_date == today:
                menu_stale = True
        else:
            if not ev.ingredient_key or ev.ingredient_key not in ing_by_key:
                raise AppError(
                    "UNRESOLVED_INGREDIENT",
                    f"Ingredient '{ev.ingredient_key}' is not recognized. Please select a valid ingredient.",
                    status_code=400,
                )
            if ev.qty_base is None:
                raise AppError(
                    "MISSING_QUANTITY",
                    f"Quantity missing for {ev.ingredient_key}.",
                    status_code=400,
                )
            ing_obj = ing_by_key[ev.ingredient_key]
            signed_qty = float(ev.qty_base)
            if ev.type in ("COOKED", "SPOILED") and signed_qty > 0:
                signed_qty = -signed_qty
            inv = InventoryEvent(
                household_id=hh.id,
                event_type=ev.type,
                ingredient_id=ing_obj.id,
                qty_base=Decimal(str(round(signed_qty, 3))),
                source=ev.source,
                raw_text=ev.raw_text,
            )
            db.add(inv)
            db.flush()
            written_ids.append(str(inv.id))
            touched_keys.add(ev.ingredient_key)
            if ev.type in ("SPOILED", "ADJUST", "COOKED"):
                menu_stale = True

    db.commit()
    after_stock = load_household_stock(db, hh.id, ctx.ingredients)

    deltas = [
        {
            "ingredient_key": k,
            "name_bn": ctx.ingredients[k].name_bn,
            "name_en": ctx.ingredients[k].name_en,
            "before_qty": before_stock[k].qty_base if k in before_stock else 0.0,
            "after_qty": after_stock[k].qty_base if k in after_stock else 0.0,
            "unit": ctx.ingredients[k].base_unit,
        }
        for k in sorted(touched_keys)
        if k in ctx.ingredients
    ]

    return {
        "written_count": len(written_ids),
        "written_event_ids": written_ids,
        "stock_deltas": deltas,
        "menu_stale": menu_stale,
    }
