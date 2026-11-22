"""Integration test verifying every SQLAlchemy model can be created and read."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    BazarList,
    DietPreset,
    DoseSchedule,
    DrugClassMap,
    DrugFoodRule,
    Household,
    HouseholdEvent,
    Ingredient,
    IngredientAlias,
    InventoryEvent,
    LLMCall,
    Medicine,
    Member,
    MenuSuggestion,
    Prescription,
    PriceObservation,
    PushSubscription,
    Recipe,
)


def test_crud_all_tables(db_session: Session) -> None:
    suffix = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)

    hh = Household(
        name="Test Family",
        access_code=f"TST{suffix}",
        caregiver_pin_hash="hashedpin",
        consent_given=True,
        monthly_budget_bdt=12000,
    )
    db_session.add(hh)
    db_session.flush()

    member = Member(
        household_id=hh.id,
        name="Test Member",
        role="patient",
        age_group="adult",
        conditions=["hypertension"],
        allergies=["prawn_shellfish"],
        diet_presets=["low_sodium"],
        patient_token=f"tok-{suffix}",
    )
    db_session.add(member)
    db_session.flush()

    rx = Prescription(member_id=member.id, raw_extraction={"medicines": []}, status="draft")
    db_session.add(rx)
    db_session.flush()

    med = Medicine(
        member_id=member.id,
        prescription_id=rx.id,
        name_as_written="Enalapril 5mg",
        generic_name="enalapril",
        drug_class="ace_inhibitor",
        timing="after_food",
        meal_slots=["dinner"],
        verified_by_caregiver=True,
        active=True,
    )
    db_session.add(med)
    db_session.flush()

    dcm = DrugClassMap(drug_name=f"testdrug_{suffix}", drug_class="ace_inhibitor")
    db_session.add(dcm)

    ing = Ingredient(
        key=f"test_ing_{suffix}",
        name_en="Test Gourd",
        name_bn="টেস্ট লাউ",
        category="vegetable",
        allergen_tags=[],
        potassium_level="low",
        purine_level="low",
        sodium_level="low",
        gi_level="low",
        tags=[],
        season_months=[1, 2, 11, 12],
        perishable_days=7,
        base_unit="g",
        ref_price_bdt=Decimal("60.00"),
        ref_price_per=Decimal("1000.00"),
    )
    db_session.add(ing)
    db_session.flush()

    alias = IngredientAlias(alias=f"টেস্টলাউ_{suffix}", ingredient_id=ing.id)
    db_session.add(alias)

    recipe = Recipe(
        key=f"test_recipe_{suffix}",
        name_bn="টেস্ট তরকারি",
        name_en="Test Curry",
        servings_base=4,
        ingredients=[{"ingredient_key": ing.key, "qty": 200, "unit": "g"}],
        steps_bn=["ধাপ ১"],
        split_step_bn="লবণ দেওয়ার আগে",
        split_removes=[],
        taste_score=Decimal("0.80"),
        category="vegetable",
        est_cost_bdt=Decimal("30.00"),
    )
    db_session.add(recipe)

    rule = DrugFoodRule(
        rule_id=f"TEST_RULE_{suffix}",
        drug_class="ace_inhibitor",
        ingredient_attr="potassium_level",
        attr_value="high",
        severity="block",
        message_bn="বার্তা",
        message_en="Message",
        source_note="test",
    )
    db_session.add(rule)

    preset = DietPreset(preset=f"test_preset_{suffix}", attr="sodium_level", max_level="medium", split_allowed=True)
    db_session.add(preset)

    inv = InventoryEvent(
        household_id=hh.id,
        event_type="PURCHASED",
        ingredient_id=ing.id,
        qty_base=Decimal("500.000"),
        source="ui",
        raw_text="500g",
    )
    db_session.add(inv)

    hhe = HouseholdEvent(
        household_id=hh.id,
        kind="GUESTS",
        for_date=date(2026, 11, 25),
        payload={"guest_count": 2, "restrictions": []},
    )
    db_session.add(hhe)

    po = PriceObservation(
        household_id=hh.id,
        ingredient_id=ing.id,
        price_bdt=Decimal("55.00"),
        per_qty=Decimal("1000.00"),
        source="user_purchase",
    )
    db_session.add(po)

    ms = MenuSuggestion(
        household_id=hh.id,
        for_date=date(2026, 11, 25),
        meal="dinner",
        payload={"items": []},
        validated=True,
        used_template=True,
    )
    db_session.add(ms)

    bl = BazarList(
        household_id=hh.id,
        month="2026-11",
        budget_bdt=12000,
        items=[],
        est_total_bdt=Decimal("4500.00"),
        status="draft",
    )
    db_session.add(bl)

    ds = DoseSchedule(
        medicine_id=med.id,
        due_at=now,
        window_end=now + timedelta(minutes=30),
        status="pending",
    )
    db_session.add(ds)

    al = Alert(
        household_id=hh.id,
        member_id=member.id,
        kind="dose_due",
        channel="in_app",
        payload={"text": "ওষুধের সময় হয়েছে"},
    )
    db_session.add(al)

    llm = LLMCall(
        task="test",
        model="mock",
        input_summary="test",
        output={"ok": True},
        validated=True,
        latency_ms=10,
    )
    db_session.add(llm)

    ps = PushSubscription(
        household_id=hh.id,
        member_id=member.id,
        endpoint=f"https://push.example/{suffix}",
        p256dh="key",
        auth="auth",
    )
    db_session.add(ps)

    db_session.commit()

    # Read back key entities
    assert db_session.scalar(select(Household).where(Household.id == hh.id)) is not None
    assert db_session.scalar(select(DoseSchedule).where(DoseSchedule.id == ds.id)).status == "pending"
    assert db_session.scalar(select(Ingredient).where(Ingredient.id == ing.id)).key == ing.key

    # Cleanup synthetic rows
    for obj in (ps, llm, al, hhe, ms, bl, po, inv, recipe, alias, ing, rule, preset, dcm, hh):
        db_session.delete(obj)
    db_session.commit()
