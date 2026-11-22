"""End-to-end PostgreSQL integration tests for all REST API routers (B12-B17, B19)."""

from __future__ import annotations

import json
import struct
import zlib
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import events as events_api
from app.api import menu as menu_api
from app.api import prescriptions as rx_api
from app.config import get_settings
from app.deps import reset_rate_limits
from app.llm.client import LLMClient
from app.llm.parse_events import EventParseOutput
from app.main import app
from app.seed.load import seed_reference_data


def _tiny_png_bytes() -> bytes:
    def _chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack("!IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\xff\xff")
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def test_households_auth_isolation_and_members_crud(client: TestClient, db_session: Session) -> None:
    seed_reference_data(db_session)
    reset_rate_limits()

    # 1. Create two households
    r1 = client.post(
        "/households",
        json={"name": "Family A", "pin": "1111", "consent_given": False, "monthly_budget_bdt": 12000},
    )
    assert r1.status_code == 201
    h1 = r1.json()
    assert len(h1["access_code"]) >= 6

    r2 = client.post(
        "/households",
        json={"name": "Family B", "pin": "2222", "consent_given": True, "monthly_budget_bdt": 15000},
    )
    assert r2.status_code == 201
    h2 = r2.json()

    # 2. Wrong PIN rejected
    bad_login = client.post("/households/login", json={"access_code": h1["access_code"], "pin": "9999"})
    assert bad_login.status_code == 401

    # 3. Valid login returns token
    good_login = client.post("/households/login", json={"access_code": h1["access_code"], "pin": "1111"})
    assert good_login.status_code == 200
    headers1 = {"Authorization": f"Bearer {good_login.json()['token']}"}
    headers2 = {"Authorization": f"Bearer {h2['token']}"}

    # 4. Cross-household state forbidden
    assert client.get(f"/households/{h2['household_id']}/state", headers=headers1).status_code == 403
    assert client.get(f"/households/{h1['household_id']}/state", headers=headers1).status_code == 200

    # 5. Member CRUD
    m_res = client.post(
        "/members",
        headers=headers1,
        json={"name": "মা", "role": "patient", "age_group": "adult", "conditions": ["hypertension"], "diet_presets": ["low_sodium"]},
    )
    assert m_res.status_code == 201
    member_id = m_res.json()["id"]
    assert m_res.json()["patient_token"].startswith("pt-")

    patch_res = client.patch(f"/members/{member_id}", headers=headers1, json={"allergies": ["egg"]})
    assert patch_res.status_code == 200
    assert patch_res.json()["allergies"] == ["egg"]

    # Family B cannot access Family A member
    assert client.get(f"/members/{member_id}", headers=headers2).status_code == 404


def test_prescription_consent_and_confirm_gate(client: TestClient, db_session: Session) -> None:
    seed_reference_data(db_session)
    reset_rate_limits()

    # Household without consent cannot upload prescription
    h_no = client.post("/households", json={"name": "NoConsent", "pin": "1234", "consent_given": False}).json()
    hdr_no = {"Authorization": f"Bearer {h_no['token']}"}
    m_no = client.post("/members", headers=hdr_no, json={"name": "Patient", "role": "patient"}).json()

    blocked_upload = client.post(
        f"/members/{m_no['id']}/prescription",
        headers=hdr_no,
        files={"file": ("rx.png", _tiny_png_bytes(), "image/png")},
    )
    assert blocked_upload.status_code == 403
    assert blocked_upload.json()["code"] == "CONSENT_REQUIRED"

    # Give consent
    client.patch(f"/households/{h_no['household_id']}/settings", headers=hdr_no, json={"consent_given": True})

    class FakeRxLLM(LLMClient):
        def __init__(self):
            super().__init__(groq_api_key="", gemini_api_key="")

        def call_gemini_vision_json(self, **kwargs):
            return kwargs["schema_cls"].model_validate(
                {
                    "medicines": [
                        {
                            "name_as_written": "Tab. Enalapril 5mg",
                            "generic_guess": "enalapril",
                            "timing": "after_food",
                            "times_per_day": 1,
                            "confidence": 0.91,
                        },
                        {
                            "name_as_written": "Ignored Vitamin",
                            "generic_guess": None,
                            "timing": "any",
                            "times_per_day": 1,
                            "confidence": 0.50,
                        },
                    ],
                    "diet_notes": ["Low salt"],
                    "overall_confidence": 0.78,
                }
            )

    app.dependency_overrides[rx_api.get_llm_client] = lambda: FakeRxLLM()
    try:
        draft_res = client.post(
            f"/members/{m_no['id']}/prescription",
            headers=hdr_no,
            files={"file": ("rx.png", _tiny_png_bytes(), "image/png")},
        )
        assert draft_res.status_code == 200
        draft = draft_res.json()
        assert draft["status"] == "draft"
        assert draft["image_stored"] is False
        assert draft["medicines"][0]["suggested_drug_class"] == "ace_inhibitor"
        assert "5mg" not in draft["medicines"][0]["name_as_written"].lower()

        # Before confirmation, palong_shak_bhaji MUST still NOT be blocked by unconfirmed prescription
        menu_before = client.post(
            "/menu/suggest",
            headers=hdr_no,
            json={"for_date": "2026-11-22", "meal": "dinner", "use_agent": False},
        ).json()
        excl_keys_before = {e["key"] for e in menu_before["excluded"]}
        assert "palong_shak_bhaji" not in excl_keys_before

        # Confirm ONLY row 0 (Enalapril), skip row 1
        confirm_res = client.post(
            f"/prescriptions/{draft['prescription_id']}/confirm",
            headers=hdr_no,
            json={
                "rows": [
                    {
                        "name_as_written": draft["medicines"][0]["name_as_written"],
                        "generic_name": "enalapril",
                        "drug_class": "ace_inhibitor",
                        "timing": "after_food",
                        "meal_slots": ["dinner"],
                        "confirmed": True,
                    },
                    {
                        "name_as_written": "Ignored Vitamin",
                        "drug_class": "none_modelled",
                        "timing": "any",
                        "meal_slots": ["dinner"],
                        "confirmed": False,
                    },
                ]
            },
        )
        assert confirm_res.status_code == 200
        cdata = confirm_res.json()
        assert cdata["status"] == "confirmed"
        assert len(cdata["confirmed_medicines"]) == 1
        assert cdata["scheduled_doses_count"] == 1

        # After confirmation, palong_shak_bhaji MUST be excluded with ACE_INHIBITOR_HIGH_POTASSIUM
        menu_after = client.post(
            "/menu/suggest",
            headers=hdr_no,
            json={"for_date": "2026-11-22", "meal": "dinner", "use_agent": False},
        ).json()
        excl_map_after = {e["key"]: e["reasons"] for e in menu_after["excluded"]}
        assert "palong_shak_bhaji" in excl_map_after
        assert "ACE_INHIBITOR_HIGH_POTASSIUM" in excl_map_after["palong_shak_bhaji"]
    finally:
        app.dependency_overrides.pop(rx_api.get_llm_client, None)


def test_events_parse_confirm_demo_menu_review_cooked_bazar_reminders_and_engine(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_reference_data(db_session)
    reset_rate_limits()

    # Load Demo Household (SPEC §9.7)
    demo = client.post("/households/demo?reset=true").json()
    headers = {"Authorization": f"Bearer {demo['token']}"}

    # 1. Event parse with SPEC §8.2 sentence (mocked LLM) -> nothing written before confirm
    class FakeEventLLM(LLMClient):
        def __init__(self):
            super().__init__(groq_api_key="", gemini_api_key="")

        def call_groq_json(self, **kwargs):
            return EventParseOutput.model_validate(
                {
                    "events": [
                        {"type": "ADJUST", "item_raw": "তেল", "qty_phrase": "প্রায় শেষ"},
                        {"type": "SPOILED", "item_raw": "লাউ", "qty_phrase": "অর্ধেকটা"},
                        {"type": "GUESTS", "guest_count": 4, "for_date": "2026-11-23", "guest_restrictions": ["no_beef"]},
                    ]
                }
            )

    app.dependency_overrides[events_api.get_llm_client] = lambda: FakeEventLLM()
    try:
        stock_before = {i["ingredient_key"]: i["qty_base"] for i in client.get("/stock", headers=headers).json()["items"]}
        assert stock_before["oil"] == 1000.0

        parse_res = client.post(
            "/events/parse",
            headers=headers,
            json={"text": "তেল প্রায় শেষ, অর্ধেকটা লাউ পচে গেছে, কাল ৪ জন মেহমান আসবে"},
        )
        assert parse_res.status_code == 200
        pdata = parse_res.json()
        assert len(pdata["proposals"]) == 3

        # Nothing written to DB before confirm!
        stock_mid = {i["ingredient_key"]: i["qty_base"] for i in client.get("/stock", headers=headers).json()["items"]}
        assert stock_mid["oil"] == 1000.0

        # Confirm events
        confirm_ev_payload = {
            "confirmation_token": pdata["confirmation_token"],
            "events": [
                {
                    "type": p["type"],
                    "ingredient_key": p["ingredient_key"],
                    "qty_base": p["qty_base"],
                    "source": "text",
                    "raw_text": pdata["raw_text"],
                    "guest_count": p["guest_count"],
                    "for_date": p["for_date"],
                    "guest_restrictions": p["guest_restrictions"],
                }
                for p in pdata["proposals"]
            ],
        }
        conf_res = client.post("/events/confirm", headers=headers, json=confirm_ev_payload)
        assert conf_res.status_code == 200
        assert conf_res.json()["written_count"] == 3
        assert conf_res.json()["menu_stale"] is True

        stock_after = {i["ingredient_key"]: i["qty_base"] for i in client.get("/stock", headers=headers).json()["items"]}
        assert stock_after["oil"] == 100.0  # 10% of 1000ml
        assert stock_after["lau"] == 600.0  # half spoiled from 1200g
    finally:
        app.dependency_overrides.pop(events_api.get_llm_client, None)

    # 2. Demo Menu suggest (using mocked hostile agent -> deterministic fallback + template)
    class HostileAgentLLM(LLMClient):
        def __init__(self):
            super().__init__(groq_api_key="x", gemini_api_key="")

        def call_groq_tools(self, **kwargs):
            return type("Msg", (), {"content": "bad", "tool_calls": []})()

    app.dependency_overrides[menu_api.get_llm_client] = lambda: HostileAgentLLM()
    try:
        menu_res = client.post(
            "/menu/suggest",
            headers=headers,
            json={"for_date": "2026-11-22", "meal": "dinner", "use_agent": True},
        )
        assert menu_res.status_code == 200
        mdata = menu_res.json()
        assert len(mdata["top_3"]) == 3
        assert mdata["used_fallback"] is True
        excl_map = {e["key"]: e["reasons"] for e in mdata["excluded"]}
        assert "PRAWN_ALLERGY" in excl_map["lau_chingri"]
        assert "ACE_INHIBITOR_HIGH_POTASSIUM" in excl_map["palong_shak_bhaji"]
        assert "LOW_POTASSIUM_POTASSIUM" in excl_map["palong_shak_bhaji"]

        # Review button: add 4 guests with no_beef -> people_count=8, gorur_bhuna excluded
        rev_res = client.post(
            "/menu/review",
            headers=headers,
            json={
                "for_date": "2026-11-22",
                "meal": "dinner",
                "guest_count": 4,
                "guest_restrictions": ["no_beef"],
                "away_member_ids": [],
            },
        )
        assert rev_res.status_code == 200
        rdata = rev_res.json()
        assert rdata["people_count"] == 8
        rev_excl = {e["key"]: e["reasons"] for e in rdata["excluded"]}
        assert "GUEST_EXCLUDES_BEEF" in rev_excl["gorur_bhuna"]

        # Mark top dish cooked -> deducts stock & sets repeat penalty
        top_dish = rdata["top_3"][0]
        cooked_res = client.post(
            "/menu/cooked",
            headers=headers,
            json={"recipe_id": top_dish["recipe_id"], "servings": 8, "for_date": "2026-11-22"},
        )
        assert cooked_res.status_code == 200
        assert cooked_res.json()["inventory_events_written"] > 0
    finally:
        app.dependency_overrides.pop(menu_api.get_llm_client, None)

    # 3. Monthly Bazar build -> confirm -> purchased
    bazar_build = client.post(
        "/bazar/build",
        headers=headers,
        json={"month": "2026-11", "budget_bdt": 5000},
    )
    assert bazar_build.status_code == 200
    bdata = bazar_build.json()
    assert bdata["price_label_bn"] == "আনুমানিক"
    assert len(bdata["items"]) > 0

    bazar_conf = client.post(
        "/bazar/confirm",
        headers=headers,
        json={"bazar_list_id": bdata["bazar_list_id"], "items": bdata["items"]},
    )
    assert bazar_conf.status_code == 200
    assert bazar_conf.json()["status"] == "confirmed"

    bazar_buy = client.post(
        "/bazar/purchased",
        headers=headers,
        json={"bazar_list_id": bdata["bazar_list_id"], "items": [{"ingredient_key": "oil", "qty_base": 2000, "price_bdt": 360, "per_qty": 2000}]},
    )
    assert bazar_buy.status_code == 200
    assert bazar_buy.json()["prices_recorded"] == 1

    # 4. Reminders + Tick idempotency + generic text + patient isolation
    settings = get_settings()
    # Unauthorized tick rejected
    assert client.post("/internal/tick").status_code == 401

    members_list = client.get("/members", headers=headers).json()["members"]
    mother = next(m for m in members_list if m["name"] == "মা")
    child = next(m for m in members_list if m["name"] == "আরিফ")

    # Mother's Enalapril is after_food for dinner (21:00 -> due 21:20, window_end 21:50)
    tick_due = client.post(
        "/internal/tick",
        headers={"X-Tick-Secret": settings.tick_secret},
        params={"now": "2026-11-25T21:25:00+06:00"},
    )
    assert tick_due.status_code == 200
    assert tick_due.json()["patient_notifications_sent"] >= 1

    # Idempotent repeat tick at 21:30 sends 0 new notifications
    tick_repeat = client.post(
        "/internal/tick",
        headers={"X-Tick-Secret": settings.tick_secret},
        params={"now": "2026-11-25T21:30:00+06:00"},
    )
    assert tick_repeat.status_code == 200
    assert tick_repeat.json()["patient_notifications_sent"] == 0

    # Patient polling screen sees due dose with NO disease names
    due_res = client.get(
        "/reminders/due",
        params={"token": mother["patient_token"], "now": "2026-11-25T21:25:00+06:00"},
    )
    assert due_res.status_code == 200
    ddata = due_res.json()
    assert ddata["has_due_dose"] is True
    dose_id = ddata["due_doses"][0]["dose_id"]
    raw_patient_json = json.dumps(ddata, ensure_ascii=False).lower()
    assert "diabetes" not in raw_patient_json
    assert "hypertension" not in raw_patient_json
    assert "enalapril" not in raw_patient_json

    # Child's token CANNOT confirm Mother's dose
    bad_take = client.post(f"/reminders/{dose_id}/taken", params={"token": child["patient_token"]})
    assert bad_take.status_code == 404

    # Escalation after grace window (21:55+06:00)
    tick_esc = client.post(
        "/internal/tick",
        headers={"X-Tick-Secret": settings.tick_secret},
        params={"now": "2026-11-25T21:55:00+06:00"},
    )
    assert tick_esc.status_code == 200
    assert tick_esc.json()["caregiver_escalations_sent"] >= 1

    # Caregiver dashboard sees escalated dose & alert (without disease name)
    dash = client.get("/dashboard/doses", headers=headers, params={"for_date": "2026-11-25"}).json()
    assert dash["summary"]["escalated"] >= 1
    for alert in dash["alerts"]:
        txt = json.dumps(alert["payload"], ensure_ascii=False).lower()
        assert "diabetes" not in txt
        assert "hypertension" not in txt

    # Late confirmation stops further escalations -> taken_late
    take_late = client.post(
        f"/reminders/{dose_id}/taken",
        params={"token": mother["patient_token"], "now": "2026-11-25T22:00:00+06:00"},
    )
    assert take_late.status_code == 200
    assert take_late.json()["status"] == "taken_late"

    # Push subscribe (caregiver + patient) & Day-1 monthly bazar prompt
    vapid_res = client.get("/push/vapid-public-key")
    assert vapid_res.status_code == 200
    assert "public_key" in vapid_res.json()
    assert vapid_res.headers.get("X-Content-Type-Options") == "nosniff"
    assert vapid_res.headers.get("X-Frame-Options") == "DENY"

    sub_res = client.post(
        "/push/subscribe",
        headers=headers,
        json={"member_id": mother["id"], "endpoint": "https://push.test/1", "p256dh": "k", "auth": "a"},
    )
    assert sub_res.status_code == 200

    pt_sub_res = client.post(
        "/push/subscribe-patient",
        params={"token": mother["patient_token"]},
        json={"endpoint": "https://push.test/pt1", "p256dh": "k2", "auth": "a2"},
    )
    assert pt_sub_res.status_code == 200
    assert client.post(
        "/push/subscribe-patient",
        params={"token": "invalid-pt-token"},
        json={"endpoint": "https://push.test/pt2", "p256dh": "k3", "auth": "a3"},
    ).status_code == 401

    tick_day1 = client.post(
        "/internal/tick",
        headers={"X-Tick-Secret": settings.tick_secret},
        params={"now": "2026-12-01T09:00:00+06:00"},
    )
    assert tick_day1.status_code == 200
    assert tick_day1.json()["bazar_prompts_sent"] >= 1

    # 5. Engine Explorer & Eval measured results
    cat = client.get("/engine/catalog", headers=headers)
    assert cat.status_code == 200
    assert len(cat.json()["recipes"]) == 40

    eng = client.post(
        "/engine/check",
        headers=headers,
        json={"member_id": mother["id"], "recipe_key": "palong_shak_bhaji"},
    )
    assert eng.status_code == 200
    assert eng.json()["status"] == "BLOCKED"
    assert "ACE_INHIBITOR_HIGH_POTASSIUM" in eng.json()["reasons"]

    ev_res = client.get("/eval/results")
    assert ev_res.status_code == 200
    assert ev_res.json()["status"] == "available"
    assert ev_res.json()["results"]["case_count"] == 30
