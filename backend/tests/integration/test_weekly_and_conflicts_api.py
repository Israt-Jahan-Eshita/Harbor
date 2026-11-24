"""Integration tests for weekly meal planning and multi-member conflict endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.deps import sign_session_token
from app.seed.load import seed_demo_household, seed_reference_data


def test_weekly_plan_lifecycle_slot_swap_and_to_bazar(client: TestClient, db_session: Session) -> None:
    seed_reference_data(db_session)
    hh = seed_demo_household(db_session, reset=True)
    tok = sign_session_token(str(hh.id))
    headers = {"Authorization": f"Bearer {tok}"}

    # 1. Generate 7-day x 3-meal weekly plan in one go
    r_plan = client.post(
        "/menu/week/plan",
        json={"start_date": "2026-11-24", "days": 7, "use_ai_summary": False},
        headers=headers,
    )
    assert r_plan.status_code == 200, r_plan.text
    plan = r_plan.json()
    plan_id = plan["plan_id"]
    assert plan["days_count"] == 7
    assert plan["total_slots"] == 21
    assert plan["safe_slots_count"] == 21
    assert plan["unique_dishes_count"] >= 10
    assert len(plan["conflict_matrix"]) >= 1

    # 2. Fetch latest persisted weekly plan
    r_latest = client.get("/menu/week/latest", headers=headers)
    assert r_latest.status_code == 200
    assert r_latest.json()["plan"]["plan_id"] == plan_id

    # 3. Safe slot swap succeeds and updates shortfall
    first_slot = plan["days"][0]["slots"][0]
    alt_key = first_slot["alternatives"][0]["recipe_key"]
    r_swap = client.patch(
        f"/menu/week/{plan_id}/slot",
        json={"for_date": "2026-11-24", "meal": first_slot["meal"], "recipe_key": alt_key, "locked": True},
        headers=headers,
    )
    assert r_swap.status_code == 200, r_swap.text
    swapped = r_swap.json()
    updated_slot = swapped["days"][0]["slots"][0]
    assert updated_slot["recipe_key"] == alt_key
    assert updated_slot["locked"] is True

    # 4. Unsafe slot swap (lau_chingri blocked for Arif's prawn allergy) MUST return 400 UNSAFE_SLOT_SWAP
    r_unsafe = client.patch(
        f"/menu/week/{plan_id}/slot",
        json={"for_date": "2026-11-24", "meal": "dinner", "recipe_key": "lau_chingri"},
        headers=headers,
    )
    assert r_unsafe.status_code == 400
    assert r_unsafe.json()["code"] == "UNSAFE_SLOT_SWAP"

    # 5. Convert 7-day shortfall directly to draft bazar list
    r_bazar = client.post(f"/menu/week/{plan_id}/to-bazar", headers=headers)
    assert r_bazar.status_code == 200, r_bazar.text
    bz = r_bazar.json()
    assert bz["items_count"] >= 1
    assert bz["est_total_bdt"] > 0


def test_engine_conflict_check_custom_and_household(client: TestClient, db_session: Session) -> None:
    seed_reference_data(db_session)
    hh = seed_demo_household(db_session, reset=True)
    tok = sign_session_token(str(hh.id))
    headers = {"Authorization": f"Bearer {tok}"}

    # 1. Custom 2-member potato conflict
    r_custom = client.post(
        "/engine/conflict-check",
        json={
            "recipe_key": "alu_fulkopi_jhol",
            "custom_members": [
                {
                    "name": "বাবা",
                    "role": "elder",
                    "age_group": "elder",
                    "allergies": [],
                    "diet_presets": ["low_potassium"],
                    "medicines": [],
                },
                {
                    "name": "মা",
                    "role": "patient",
                    "age_group": "adult",
                    "allergies": [],
                    "diet_presets": ["low_gi", "low_sodium"],
                    "medicines": [
                        {
                            "name_as_written": "Enalapril",
                            "drug_class": "ace_inhibitor",
                            "verified_by_caregiver": True,
                            "active": True,
                        }
                    ],
                },
            ],
        },
    )
    assert r_custom.status_code == 200, r_custom.text
    body = r_custom.json()
    assert body["household_status"] == "EXCLUDED"
    assert body["order_invariant"] is True
    assert set(body["reasons"]) >= {
        "LOW_POTASSIUM_POTASSIUM",
        "LOW_GI_GI",
        "ACE_INHIBITOR_HIGH_POTASSIUM",
    }
    potato_conf = next(c for c in body["ingredient_conflicts"] if c["ingredient_key"] == "potato")
    assert potato_conf["conflict_type"] == "MULTI_RULE_COLLISION"

    # 2. Signed-in household conflict check across seeded DEMO26 family on lau_chingri
    r_hh = client.post(
        "/engine/conflict-check",
        json={"recipe_key": "lau_chingri"},
        headers=headers,
    )
    assert r_hh.status_code == 200, r_hh.text
    hh_body = r_hh.json()
    assert hh_body["household_status"] == "EXCLUDED"
    assert hh_body["order_invariant"] is True
    assert "PRAWN_ALLERGY" in hh_body["reasons"]


def test_menu_review_replaces_guest_and_away_events_idempotently(
    client: TestClient, db_session: Session
) -> None:
    seed_reference_data(db_session)
    hh = seed_demo_household(db_session, reset=True)
    tok = sign_session_token(str(hh.id))
    headers = {"Authorization": f"Bearer {tok}"}

    # 1. Set 2 guests + fish restriction + 1 away member on 2026-11-24 breakfast
    first_members = client.get("/members", headers=headers).json()["members"]
    away_id = first_members[0]["id"]
    r1 = client.post(
        "/menu/review",
        headers=headers,
        json={
            "for_date": "2026-11-24",
            "meal": "breakfast",
            "guest_count": 2,
            "guest_restrictions": ["fish"],
            "away_member_ids": [away_id],
        },
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["guest_count"] == 2
    assert d1["people_count"] == 5  # 3 present + 2 guests
    assert d1["guest_restrictions"] == ["fish"]
    assert d1["away_member_ids"] == [away_id]

    # 2. Update guests from 2 -> 3 and clear away member -> must replace cleanly (NOT stack 2+3=5)
    r2 = client.post(
        "/menu/review",
        headers=headers,
        json={
            "for_date": "2026-11-24",
            "meal": "dinner",
            "guest_count": 3,
            "guest_restrictions": ["egg"],
            "away_member_ids": [],
        },
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["guest_count"] == 3
    assert d2["people_count"] == 7  # 4 members + 3 guests
    assert d2["guest_restrictions"] == ["egg"]
    assert d2["away_member_ids"] == []


