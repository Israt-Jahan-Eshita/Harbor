"""Integration tests for pantry quick-add and clinician review / fee payment workflow."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.deps import reset_rate_limits
from app.seed.load import seed_reference_data


def _setup_household_and_member(client: TestClient, db_session: Session):
    seed_reference_data(db_session)
    reset_rate_limits()
    hh_res = client.post(
        "/households",
        json={"name": "Care Family", "pin": "1234", "consent_given": True, "monthly_budget_bdt": 15000},
    )
    assert hh_res.status_code == 201
    hh = hh_res.json()
    headers = {"Authorization": f"Bearer {hh['token']}"}

    m_res = client.post(
        "/members",
        headers=headers,
        json={
            "name": "বাবা",
            "role": "patient",
            "age_group": "elder",
            "conditions": ["ckd", "hypertension"],
            "allergies": ["prawn_shellfish"],
            "diet_presets": ["low_potassium"],
        },
    )
    assert m_res.status_code == 201
    member = m_res.json()
    return hh, headers, member


def test_stock_quick_add_records_purchase_and_optional_price(
    client: TestClient, db_session: Session
) -> None:
    _hh, headers, _member = _setup_household_and_member(client, db_session)

    # First quick add of lau (Bottle Gourd) without price
    res1 = client.post(
        "/stock/quick-add",
        headers=headers,
        json={"ingredient_key": "lau", "qty_base": 1500, "note": "Weekly lau"},
    )
    assert res1.status_code == 201
    d1 = res1.json()
    assert d1["ingredient_key"] == "lau"
    assert d1["previous_qty"] == 0.0
    assert d1["added_qty"] == 1500
    assert d1["new_qty"] == 1500.0
    assert d1["unit"] == "g"

    # Second quick add increments existing balance and accepts price_bdt
    res2 = client.post(
        "/stock/quick-add",
        headers=headers,
        json={"ingredient_key": "lau", "qty_base": 500, "price_bdt": 42},
    )
    assert res2.status_code == 201
    d2 = res2.json()
    assert d2["previous_qty"] == 1500.0
    assert d2["new_qty"] == 2000.0
    assert d2["last_purchased_at"] is not None

    # Unknown ingredient returns 404
    bad = client.post(
        "/stock/quick-add",
        headers=headers,
        json={"ingredient_key": "nonexistent_item", "qty_base": 100},
    )
    assert bad.status_code == 404


def test_clinician_review_payment_and_portal_approval_flow(
    client: TestClient, db_session: Session
) -> None:
    _hh, headers, member = _setup_household_and_member(client, db_session)

    # 1. Create review request via email_invite
    create_res = client.post(
        "/clinician/reviews",
        headers=headers,
        json={
            "member_id": member["id"],
            "doctor_name": "Dr. Ayesha Rahman",
            "doctor_email": "ayesha.clinic@example.com",
            "contact_mode": "email_invite",
            "fee_bdt": 500,
            "request_note": "Please confirm if low_sodium should also be enabled alongside low_potassium.",
            "frontend_origin": "http://localhost:3000",
        },
    )
    assert create_res.status_code == 201
    review = create_res.json()
    assert review["status"] == "pending"
    assert review["payment_status"] == "unpaid"
    assert review["fee_bdt"] == 500
    assert review["email_status"] in ("link_ready", "sent")
    assert review["review_token"].startswith("cr-")
    assert review["clinical_snapshot"]["conditions"] == ["ckd", "hypertension"]

    # 2. List shows pending + unpaid summary
    list_res = client.get("/clinician/reviews", headers=headers)
    assert list_res.status_code == 200
    summary = list_res.json()["payment_summary"]
    assert summary["unpaid_count"] == 1
    assert summary["total_unpaid_bdt"] == 500
    assert summary["pending_count"] == 1

    # 3. Record fee payment
    pay_res = client.post(
        f"/clinician/reviews/{review['id']}/pay",
        headers=headers,
        json={"payment_method": "bkash", "payment_ref": "TRX889900"},
    )
    assert pay_res.status_code == 200
    paid_review = pay_res.json()
    assert paid_review["payment_status"] == "paid"
    assert paid_review["payment_method"] == "bkash"
    assert paid_review["payment_ref"] == "TRX889900"
    assert paid_review["paid_at"] is not None

    # Double payment is rejected
    dup_pay = client.post(
        f"/clinician/reviews/{review['id']}/pay",
        headers=headers,
        json={"payment_method": "nagad"},
    )
    assert dup_pay.status_code == 400

    # 4. Token-gated portal works without household auth header
    portal_res = client.get(f"/clinician/portal/{review['review_token']}")
    assert portal_res.status_code == 200
    portal = portal_res.json()
    assert portal["member_name"] == "বাবা"
    assert "low_potassium" in portal["available_presets"]
    assert "low_sodium" in portal["available_presets"]

    # 5. Clinician approves and adds low_sodium preset
    decision_res = client.post(
        f"/clinician/portal/{review['review_token']}/decision",
        json={
            "decision": "approved",
            "clinician_reg_no": "BMDC-A-45210",
            "clinician_note": "Continue low potassium and add low sodium monitoring.",
            "approved_diet_presets": ["low_potassium", "low_sodium"],
            "apply_presets_to_member": True,
        },
    )
    assert decision_res.status_code == 200
    decided = decision_res.json()
    assert decided["status"] == "approved"
    assert decided["clinician_reg_no"] == "BMDC-A-45210"
    assert decided["approved_diet_presets"] == ["low_potassium", "low_sodium"]
    assert decided["member_current_diet_presets"] == ["low_potassium", "low_sodium"]

    # 6. Member profile now reflects clinician verification + updated diet_presets
    member_res = client.get(f"/members/{member['id']}", headers=headers)
    assert member_res.status_code == 200
    m_data = member_res.json()
    assert m_data["diet_presets"] == ["low_potassium", "low_sodium"]
    assert m_data["latest_clinician_review"] is not None
    assert m_data["latest_clinician_review"]["doctor_name"] == "Dr. Ayesha Rahman"
    assert m_data["latest_clinician_review"]["clinician_reg_no"] == "BMDC-A-45210"

    # 7. Payment & approval summary reflects paid + approved counts
    list_after = client.get("/clinician/reviews", headers=headers).json()
    assert list_after["payment_summary"]["paid_count"] == 1
    assert list_after["payment_summary"]["total_paid_bdt"] == 500
    assert list_after["payment_summary"]["approved_count"] == 1

