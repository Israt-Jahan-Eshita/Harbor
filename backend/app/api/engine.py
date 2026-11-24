"""Read-only Engine Explorer endpoint (`POST /engine/check`) for presentation & Q&A (B19)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.api.prescriptions import DRUG_CLASS_CATALOG
from app.core.rules import ALLERGEN_RULE_NAMES, check_dish_safe
from app.core.shared_pot import evaluate_multi_member_conflict
from app.core.types import MedicineData, MemberData
from app.db import get_db
from app.deps import verify_session_token
from app.errors import AppError
from app.schemas import EngineCheckRequest, EngineConflictCheckRequest, dhaka_today
from app.services.context_loader import (
    load_household_members,
    load_rule_context_and_recipes,
    load_substitution_groups,
)

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

    presets_out = sorted({dp.preset for dp in ctx.diet_presets})
    allergens_out = sorted(
        {tag for ing in ctx.ingredients.values() for tag in ing.allergen_tags}
        | set(ALLERGEN_RULE_NAMES.keys())
    )
    drug_classes_out = sorted(
        {entry["value"] for entry in DRUG_CLASS_CATALOG} | set(ctx.known_drug_classes)
    )

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
        "presets": presets_out,
        "allergens": allergens_out,
        "drug_classes": drug_classes_out,
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


@router.post("/conflict-check")
def check_multi_member_conflicts_endpoint(
    payload: EngineConflictCheckRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Evaluate multi-member restriction conflicts on the same ingredient and prove order invariance."""
    ctx, recipes, recipes_by_id = load_rule_context_and_recipes(db)
    recipe = recipes_by_id.get(payload.recipe_key) or next(
        (r for r in recipes if r.key == payload.recipe_key), None
    )
    if recipe is None:
        raise AppError("RECIPE_NOT_FOUND", f"Recipe '{payload.recipe_key}' not found.", status_code=404)

    target_members: list[MemberData] = []
    if payload.custom_members:
        for idx, cm in enumerate(payload.custom_members):
            meds = [
                MedicineData(
                    name_as_written=str(m.get("name_as_written", "Med")),
                    drug_class=m.get("drug_class"),
                    verified_by_caregiver=bool(m.get("verified_by_caregiver", True)),
                    active=bool(m.get("active", True)),
                )
                for m in cm.medicines
            ]
            target_members.append(
                MemberData(
                    id=f"custom-{idx + 1}",
                    name=cm.name,
                    role=cm.role,
                    age_group=cm.age_group,
                    allergies=list(cm.allergies),
                    diet_presets=list(cm.diet_presets),
                    medicines=meds,
                )
            )
    else:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise AppError(
                "UNAUTHORIZED",
                "Provide at least 2 custom_members or sign in to inspect household member conflicts.",
                status_code=401,
            )
        hh_id = verify_session_token(authorization.split(" ", 1)[1].strip())
        hh_members = load_household_members(db, hh_id)
        if payload.member_ids:
            wanted = set(payload.member_ids)
            target_members = [m for m in hh_members if m.id in wanted]
        else:
            target_members = hh_members

    if len(target_members) < 2:
        raise AppError(
            "NEED_AT_LEAST_TWO_MEMBERS",
            "Select or configure at least 2 family members to test restriction conflicts.",
            status_code=400,
        )

    eval_out = evaluate_multi_member_conflict(
        members=target_members,
        recipe=recipe,
        context=ctx,
        substitution_groups=load_substitution_groups(),
        current_month=dhaka_today().month,
    )
    eval_out["ingredients"] = [
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
    ]
    return eval_out
