"""Integration test for prototype seed validation and idempotent loading."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    DietPreset,
    DrugClassMap,
    DrugFoodRule,
    Household,
    Ingredient,
    IngredientAlias,
    Medicine,
    Member,
    Recipe,
)
from app.seed.load import seed_demo_household, seed_reference_data
from app.seed.validate_seed import validate_all_seeds


def test_seed_validation_and_idempotent_load(db_session: Session) -> None:
    summary = validate_all_seeds()
    assert summary["ingredients"] >= 50
    assert summary["recipes"] == 40
    assert summary["rules"] == 4
    assert summary["presets"] == 4

    counts_1 = seed_reference_data(db_session)
    hh1 = seed_demo_household(db_session, reset=True)

    ing_count_1 = db_session.scalar(select(func.count()).select_from(Ingredient))
    rec_count_1 = db_session.scalar(select(func.count()).select_from(Recipe))
    rule_count_1 = db_session.scalar(select(func.count()).select_from(DrugFoodRule))
    preset_count_1 = db_session.scalar(select(func.count()).select_from(DietPreset))
    alias_count_1 = db_session.scalar(select(func.count()).select_from(IngredientAlias))
    dcm_count_1 = db_session.scalar(select(func.count()).select_from(DrugClassMap))

    # Run a second time to assert idempotency
    counts_2 = seed_reference_data(db_session)
    hh2 = seed_demo_household(db_session, reset=False)

    assert counts_1 == counts_2
    assert hh1.id == hh2.id
    assert db_session.scalar(select(func.count()).select_from(Ingredient)) == ing_count_1
    assert db_session.scalar(select(func.count()).select_from(Recipe)) == rec_count_1
    assert db_session.scalar(select(func.count()).select_from(DrugFoodRule)) == rule_count_1
    assert db_session.scalar(select(func.count()).select_from(DietPreset)) == preset_count_1
    assert db_session.scalar(select(func.count()).select_from(IngredientAlias)) == alias_count_1
    assert db_session.scalar(select(func.count()).select_from(DrugClassMap)) == dcm_count_1

    members = db_session.scalars(select(Member).where(Member.household_id == hh2.id)).all()
    assert len(members) == 4
    meds = db_session.scalars(select(Medicine).join(Member).where(Member.household_id == hh2.id)).all()
    assert len(meds) == 1
    assert meds[0].drug_class == "ace_inhibitor"
    assert meds[0].verified_by_caregiver is True
