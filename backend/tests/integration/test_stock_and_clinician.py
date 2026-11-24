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

    # 1. Create review request WITHOUT custom_email_body -> auto-generated email + awaiting_fee
    create_res = client.post(
        "/clinician/reviews",
        headers=headers,
        json={
            "member_id": member["id"],
            "doctor_name": "Dr. Ayesha Rahman",
            "doctor_email": "ayesha.clinic@example.com",
            "contact_mode": "email_invite",
            "request_note": "Please confirm if low_sodium should also be enabled alongside low_potassium.",
            "frontend_origin": "http://localhost:3000",
        },
    )
    assert create_res.status_code == 201
    review = create_res.json()
    assert review["status"] == "pending"
    assert review["payment_status"] == "awaiting_fee"
    assert review["fee_bdt"] == 0
    assert review["email_status"] in ("link_ready", "sent")
    assert review["review_token"].startswith("cr-")
    assert f"http://localhost:3000/clinician/{review['review_token']}" in review["email_body"]
    assert "Please confirm if low_sodium" in review["email_body"]
    assert review["clinical_snapshot"]["conditions"] == ["ckd", "hypertension"]

    # 1b. Create second review WITH manual custom_email_body -> preserved + portal link included
    custom_res = client.post(
        "/clinician/reviews",
        headers=headers,
        json={
            "member_id": member["id"],
            "doctor_name": "Dt. Tania Karim",
            "doctor_email": "tania@clinic.example",
            "contact_mode": "email_invite",
            "custom_email_body": "Assalamu Alaikum Apu, please review Baba's sodium limits when free.",
            "frontend_origin": "http://localhost:3000",
        },
    )
    assert custom_res.status_code == 201
    custom_rev = custom_res.json()
    assert "Assalamu Alaikum Apu, please review Baba's sodium limits when free." in custom_rev["email_body"]
    assert f"http://localhost:3000/clinician/{custom_rev['review_token']}" in custom_rev["email_body"]

    # 2. List shows awaiting_fee_count and family cannot pay before doctor sets fee
    list_res = client.get("/clinician/reviews", headers=headers)
    assert list_res.status_code == 200
    assert list_res.json()["payment_summary"]["awaiting_fee_count"] == 2
    early_pay = client.post(
        f"/clinician/reviews/{review['id']}/pay",
        headers=headers,
        json={"payment_method": "bkash"},
    )
    assert early_pay.status_code == 400
    assert early_pay.json()["code"] == "FEE_NOT_SET"

    # 3. Doctor cannot approve while awaiting_fee
    early_approve = client.post(
        f"/clinician/portal/{review['review_token']}/decision",
        json={
            "decision": "approved",
            "clinician_note": "Trying to approve early",
            "approved_diet_presets": ["low_potassium"],
            "apply_presets_to_member": True,
        },
    )
    assert early_approve.status_code == 400
    assert early_approve.json()["code"] == "PAYMENT_REQUIRED"

    # 4. Doctor sets consultation fee (750 BDT) -> payment_status becomes unpaid
    fee_res = client.post(
        f"/clinician/portal/{review['review_token']}/fee",
        json={"fee_bdt": 750, "fee_note": "Full CKD + Hypertension diet plan review"},
    )
    assert fee_res.status_code == 200
    fee_data = fee_res.json()
    assert fee_data["fee_bdt"] == 750
    assert fee_data["fee_note"] == "Full CKD + Hypertension diet plan review"
    assert fee_data["payment_status"] == "unpaid"

    # Still blocked from approving while unpaid
    unpaid_approve = client.post(
        f"/clinician/portal/{review['review_token']}/decision",
        json={
            "decision": "approved",
            "clinician_note": "Still unpaid",
            "approved_diet_presets": ["low_potassium"],
            "apply_presets_to_member": True,
        },
    )
    assert unpaid_approve.status_code == 400
    assert unpaid_approve.json()["code"] == "PAYMENT_REQUIRED"

    # Summary now shows unpaid_count == 1 and total_unpaid_bdt == 750
    list_mid = client.get("/clinician/reviews", headers=headers).json()
    assert list_mid["payment_summary"]["unpaid_count"] == 1
    assert list_mid["payment_summary"]["total_unpaid_bdt"] == 750

    # 5. Family pays the doctor-requested 750 BDT fee
    pay_res = client.post(
        f"/clinician/reviews/{review['id']}/pay",
        headers=headers,
        json={"payment_method": "bkash", "payment_ref": "TRX889900"},
    )
    assert pay_res.status_code == 200
    paid_review = pay_res.json()
    assert paid_review["payment_status"] == "paid"
    assert paid_review["fee_bdt"] == 750
    assert paid_review["payment_method"] == "bkash"
    assert paid_review["payment_ref"] == "TRX889900"
    assert paid_review["paid_at"] is not None

    # Double payment rejected
    dup_pay = client.post(
        f"/clinician/reviews/{review['id']}/pay",
        headers=headers,
        json={"payment_method": "nagad"},
    )
    assert dup_pay.status_code == 400

    # 6. Token-gated portal reflects paid status cleanly
    portal_res = client.get(f"/clinician/portal/{review['review_token']}")
    assert portal_res.status_code == 200
    portal = portal_res.json()
    assert portal["member_name"] == "বাবা"
    assert portal["payment_status"] == "paid"
    assert "low_potassium" in portal["available_presets"]
    assert "low_sodium" in portal["available_presets"]

    # 7. Doctor approves after payment & adds low_sodium preset
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

    # 8. Second clinician can waive fee to 0 BDT and approve directly
    waive_res = client.post(
        f"/clinician/portal/{custom_rev['review_token']}/fee",
        json={"fee_bdt": 0, "fee_note": "Complimentary follow-up"},
    )
    assert waive_res.status_code == 200
    assert waive_res.json()["payment_status"] == "waived"
    waive_approve = client.post(
        f"/clinician/portal/{custom_rev['review_token']}/decision",
        json={
            "decision": "approved",
            "clinician_reg_no": "BDAA-204",
            "clinician_note": "Reviewed free of charge.",
            "approved_diet_presets": ["low_potassium", "low_sodium"],
            "apply_presets_to_member": False,
        },
    )
    assert waive_approve.status_code == 200

    # 9. Member profile reflects clinician verification + updated diet_presets
    member_res = client.get(f"/members/{member['id']}", headers=headers)
    assert member_res.status_code == 200
    m_data = member_res.json()
    assert m_data["diet_presets"] == ["low_potassium", "low_sodium"]
    assert m_data["latest_clinician_review"] is not None

    # 10. Payment & approval summary reflects 750 paid + 2 approved
    list_after = client.get("/clinician/reviews", headers=headers).json()
    assert list_after["payment_summary"]["paid_count"] == 1
    assert list_after["payment_summary"]["total_paid_bdt"] == 750
    assert list_after["payment_summary"]["approved_count"] == 2

