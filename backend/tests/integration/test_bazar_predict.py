"""Integration tests for Bazar price/budget/safety prediction & pre-approval checklist."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.bazar import _AIPriceEstimateOutput
from app.deps import reset_rate_limits
from app.llm.client import LLMClient
from app.seed.load import seed_reference_data


def _setup_household_and_members(client: TestClient, db_session: Session):
    seed_reference_data(db_session)
    reset_rate_limits()
    hh = client.post(
        "/households",
        json={"name": "Bazar Family", "pin": "1234", "consent_given": True, "monthly_budget_bdt": 15000},
    ).json()
    headers = {"Authorization": f"Bearer {hh['token']}"}

    m = client.post(
        "/members",
        headers=headers,
        json={
            "name": "Arif",
            "role": "child",
            "age_group": "child",
            "allergies": ["prawn_shellfish"],
            "diet_presets": [],
        },
    )
    assert m.status_code == 201
    return hh, headers


def test_bazar_predict_verified_safety_custom_ai_and_confirm(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    _hh, headers = _setup_household_and_members(client, db_session)

    # 1. Verified safe ingredient (lau) -> deterministic ref price, 0 AI calls, empty warnings
    safe_res = client.post(
        "/bazar/predict-item",
        headers=headers,
        json={
            "ingredient_key": "lau",
            "qty": 1000,
            "unit": "g",
            "month": "2026-11",
            "budget_bdt": 500,
            "current_total_bdt": 400,
            "use_ai_estimate": False,
        },
    )
    assert safe_res.status_code == 200
    safe_data = safe_res.json()
    assert safe_data["used_ai"] is False
    assert safe_data["prediction_source"] in ("reference_table", "user_purchase")
    assert safe_data["item"]["est_price_bdt"] > 0
    assert safe_data["safety_warnings"] == []
    assert safe_data["projected_total_bdt"] == round(400 + safe_data["item"]["est_price_bdt"], 2)

    # 2. Verified unsafe ingredient (chingri) triggers family BLOCKED warning before adding
    unsafe_res = client.post(
        "/bazar/predict-item",
        headers=headers,
        json={
            "ingredient_key": "chingri",
            "qty": 500,
            "unit": "g",
            "month": "2026-11",
            "budget_bdt": 500,
            "current_total_bdt": 400,
            "use_ai_estimate": False,
        },
    )
    assert unsafe_res.status_code == 200
    unsafe_data = unsafe_res.json()
    assert len(unsafe_data["safety_warnings"]) == 1
    assert unsafe_data["safety_warnings"][0]["member_name"] == "Arif"
    assert unsafe_data["safety_warnings"][0]["status"] == "BLOCKED"
    assert unsafe_data["over_budget"] is True

    # 3. Custom uncatalogued item with use_ai_estimate=True (mocked LLMClient)
    def fake_call_groq_json(self, **kwargs):  # noqa: ARG001
        return _AIPriceEstimateOutput(
            est_price_bdt=350.0,
            market_note_bn="ঢাকা খুচরা বাজারে দেশি আম প্রায় ৩৫০ টাকা/কেজি।",
            market_note_en="Dhaka retail fresh mangoes are roughly 350 BDT/kg.",
        )

    monkeypatch.setattr(LLMClient, "call_groq_json", fake_call_groq_json)

    custom_res = client.post(
        "/bazar/predict-item",
        headers=headers,
        json={
            "custom_name": "Deshi Mango",
            "qty": 1000,
            "unit": "g",
            "month": "2026-11",
            "budget_bdt": 1000,
            "current_total_bdt": 700,
            "use_ai_estimate": True,
        },
    )
    assert custom_res.status_code == 200
    c_data = custom_res.json()
    assert c_data["used_ai"] is True
    assert c_data["prediction_source"] == "ai_market_estimate"
    assert c_data["item"]["ingredient_key"] == "custom_deshi_mango"
    assert c_data["item"]["est_price_bdt"] == 350.0
    assert c_data["projected_total_bdt"] == 1050.0
    assert c_data["over_budget"] is True
    assert c_data["budget_delta_bdt"] == 50.0
    assert c_data["safety_warnings"][0]["status"] == "UNVERIFIED"

    # 4. Build bazar list, add predicted item, confirm checked subset, and verify custom key skip on /purchased
    plan = client.post(
        "/bazar/build",
        headers=headers,
        json={"month": "2026-11", "budget_bdt": 15000},
    ).json()
    combined_items = list(plan["items"]) + [c_data["item"]]
    conf = client.post(
        "/bazar/confirm",
        headers=headers,
        json={"bazar_list_id": plan["bazar_list_id"], "items": combined_items},
    )
    assert conf.status_code == 200
    assert conf.json()["status"] == "confirmed"
    assert any(it["ingredient_key"] == "custom_deshi_mango" for it in conf.json()["items"])

    purch = client.post(
        "/bazar/purchased",
        headers=headers,
        json={
            "bazar_list_id": plan["bazar_list_id"],
            "items": [
                {"ingredient_key": "custom_deshi_mango", "qty_base": 1000, "price_bdt": 350, "per_qty": 1000},
                {"ingredient_key": "lau", "qty_base": 1000, "price_bdt": 60, "per_qty": 1000},
            ],
        },
    )
    assert purch.status_code == 201 or purch.status_code == 200
    p_data = purch.json()
    assert p_data["events_written"] == 1
    assert p_data["skipped_custom_count"] == 1

