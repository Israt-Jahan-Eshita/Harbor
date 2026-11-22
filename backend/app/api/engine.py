"""Read-only Engine Explorer endpoint (`POST /engine/check`) for presentation & Q&A (B19)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.rules import check_dish_safe
from app.core.types import MedicineData, MemberData
from app.db import get_db
from app.deps import verify_session_token
from app.errors import AppError
from app.schemas import EngineCheckRequest
from app.services.context_loader import load_household_members, load_rule_context_and_recipes

router = APIRouter(prefix="/engine", tags=["engine"])


@router.get("/catalog")
def get_engine_catalog(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Return available recipes, presets, allergens, drug classes, and (if authenticated) members."""
    ctx, recipes, _ = load_rule_context_and_recipes(db)
    members_out = []
    if authorization and authorization.lower().startswith("bearer "):
        try:
            hh_id = verify_session_token(authorization.split(" ", 1)[1].strip())
            members_out = [m.model_dump() for m in load_household_members(db, hh_id)]
        except AppError:
            members_out = []

    return {
        "recipes": [
            {
                "id": r.id,
                "key": r.key,
                "name_bn": r.name_bn,
                "name_en": r.name_en,
                "category": r.category,
                "split_step_bn": r.split_step_bn,
                "split_removes": r.split_removes,
            }
            for r in recipes
        ],
        "members": members_out,
        "presets": ["low_gi", "low_sodium", "low_purine", "low_potassium"],
        "allergens": [
            "prawn_shellfish",
            "fish",
            "egg",
            "milk",
            "peanut",
            "tree_nut",
            "wheat_gluten",
            "soy",
            "sesame",
        ],
        "drug_classes": [
            "ace_inhibitor",
            "arb",
            "k_sparing_diuretic",
            "statin_cyp3a4",
            "none_modelled",
        ],
        "age_groups": ["child_under_1", "child_under_5", "child", "adult", "elder"],
    }


@router.post("/check")
def check_engine_rule_trace(
    payload: EngineCheckRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Run deterministic check_dish_safe for a member (or custom profile) and recipe key."""
    ctx, recipes, recipes_by_id = load_rule_context_and_recipes(db)
    recipe = recipes_by_id.get(payload.recipe_key) or next(
        (r for r in recipes if r.key == payload.recipe_key), None
    )
    if recipe is None:
        raise AppError("RECIPE_NOT_FOUND", f"Recipe '{payload.recipe_key}' not found.", status_code=404)

    target_member: MemberData | None = None
    if payload.custom_member:
        cm = payload.custom_member
        meds = [
            MedicineData(
                name_as_written=m.get("name_as_written", "Med"),
                drug_class=m.get("drug_class"),
                verified_by_caregiver=bool(m.get("verified_by_caregiver", True)),
                active=bool(m.get("active", True)),
            )
            for m in cm.get("medicines", [])
        ]
        target_member = MemberData(
            id="custom",
            name=str(cm.get("name", "পরীক্ষামূলক সদস্য / Custom Member")),
            role=str(cm.get("role", "patient")),
            age_group=str(cm.get("age_group", "adult")),
            allergies=list(cm.get("allergies", [])),
            diet_presets=list(cm.get("diet_presets", [])),
            medicines=meds,
        )
    elif payload.member_id:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise AppError("UNAUTHORIZED", "Session token required to inspect household member.", status_code=401)
        hh_id = verify_session_token(authorization.split(" ", 1)[1].strip())
        members = load_household_members(db, hh_id)
        target_member = next((m for m in members if m.id == payload.member_id), None)
        if target_member is None:
            raise AppError("MEMBER_NOT_FOUND", "Member not found in household.", status_code=404)
    else:
        raise AppError("INVALID_INPUT", "Provide either member_id or custom_member.", status_code=400)

    res = check_dish_safe(target_member, recipe, ctx)
    return {
        "member_name": res.member_name,
        "recipe_key": recipe.key,
        "recipe_name_bn": recipe.name_bn,
        "recipe_name_en": recipe.name_en,
        "status": res.status,
        "reasons": res.reasons,
        "trace": res.trace,
        "split_step_bn": res.split_step_bn,
        "split_ingredients": res.split_ingredients,
        "ingredients": [
            {
                "key": ri.ingredient_key,
                "name_bn": ctx.ingredients[ri.ingredient_key].name_bn if ri.ingredient_key in ctx.ingredients else ri.ingredient_key,
                "name_en": ctx.ingredients[ri.ingredient_key].name_en if ri.ingredient_key in ctx.ingredients else ri.ingredient_key,
                "potassium_level": ctx.ingredients[ri.ingredient_key].potassium_level if ri.ingredient_key in ctx.ingredients else None,
                "purine_level": ctx.ingredients[ri.ingredient_key].purine_level if ri.ingredient_key in ctx.ingredients else None,
                "sodium_level": ctx.ingredients[ri.ingredient_key].sodium_level if ri.ingredient_key in ctx.ingredients else None,
                "gi_level": ctx.ingredients[ri.ingredient_key].gi_level if ri.ingredient_key in ctx.ingredients else None,
                "allergen_tags": ctx.ingredients[ri.ingredient_key].allergen_tags if ri.ingredient_key in ctx.ingredients else [],
            }
            for ri in recipe.ingredients
        ],
    }
