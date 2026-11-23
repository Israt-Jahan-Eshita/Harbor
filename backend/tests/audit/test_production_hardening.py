"""Regression tests for Sprint 1-3 production hardening, Groq quota guards, and dynamic behavior."""

from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, time as dt_time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import events as events_api, menu as menu_api, prescriptions as rx_api
from app.config import get_settings
from app.core.types import ScoredDish
from app.deps import reset_rate_limits
from app.llm import agent as agent_mod
from app.llm.client import LLMClient, reset_llm_guards
from app.llm.explain import clear_explanation_cache, generate_grounded_explanations
from app.llm.parse_events import EventParseOutput, parse_events_from_text
from app.models import DoseSchedule, LLMCall, Medicine, Member, MenuSuggestion
from app.seed.load import seed_demo_household, seed_reference_data
from app.services.context_loader import load_rule_context_and_recipes


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_groq_429_cooldown_and_daily_token_cap(monkeypatch: pytest.MonkeyPatch, db_session: Session) -> None:
    """HTTP 429 triggers cooldown circuit breaker; exceeding groq_daily_token_cap short-circuits calls."""
    seed_reference_data(db_session)
    monkeypatch.setenv("GROQ_DAILY_TOKEN_CAP", "100")
    monkeypatch.setenv("GROQ_429_COOLDOWN_SECONDS", "900")
    get_settings.cache_clear()
    reset_llm_guards()

    llm = LLMClient(groq_api_key="test-key", gemini_api_key="")
    calls = {"n": 0}

    class FakeRateLimitErr(Exception):
        status_code = 429

        def __init__(self):
            super().__init__("Error code: 429 - Rate limit reached for org_secret123")

    def fake_create(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise FakeRateLimitErr()
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"events": []}'))],
            usage=SimpleNamespace(prompt_tokens=60, completion_tokens=60, total_tokens=120),
        )

    assert llm._groq is not None
    monkeypatch.setattr(llm._groq.chat.completions, "create", fake_create)

    # First call hits 429 -> triggers cooldown & redacts org_ id in llm_calls
    out1 = llm.call_groq_json("parse_events", "sys", "usr", EventParseOutput, db=db_session)
    assert out1 is None
    assert calls["n"] == 1

    # Second call immediately skipped with ZERO network calls
    out2 = llm.call_groq_json("parse_events", "sys", "usr2", EventParseOutput, db=db_session)
    assert out2 is None
    assert calls["n"] == 1

    # Clear cooldown only, run one call consuming 120 > 100 cap -> next call blocked by token cap
    reset_llm_guards()
    out3 = llm.call_groq_json("parse_events", "sys", "usr3", EventParseOutput, db=db_session)
    assert out3 is not None
    assert calls["n"] == 2

    out4 = llm.call_groq_json("parse_events", "sys", "usr4", EventParseOutput, db=db_session)
    assert out4 is None
    assert calls["n"] == 2

    # Verify org_id redacted and skipped reasons logged
    logged = db_session.scalars(select(LLMCall).order_by(LLMCall.created_at.desc()).limit(4)).all()
    logged_strs = [json.dumps(r.output or {}) for r in logged]
    assert all("org_secret123" not in s for s in logged_strs)
    assert any("GROQ_COOLDOWN_ACTIVE" in s for s in logged_strs)
    assert any("GROQ_DAILY_TOKEN_CAP" in s for s in logged_strs)


def test_fast_model_explain_cache_and_trimmed_agent_tools(client: TestClient, db_session: Session) -> None:
    """Verify parse_events & menu_explain use llm_fast_model + cache, and agent sends only 5 tools."""
    seed_reference_data(db_session)
    demo = seed_demo_household(db_session, reset=True)
    ctx, recipes, recipes_by_id = load_rule_context_and_recipes(db_session)

    recorded_models: list[tuple[str, str | None, int]] = []

    class RecordingLLM(LLMClient):
        def __init__(self):
            super().__init__(groq_api_key="x", gemini_api_key="")

        def call_groq_json(self, task, system_prompt, user_prompt, schema_cls, **kwargs):
            recorded_models.append((task, kwargs.get("model_override"), kwargs.get("max_completion_tokens", 0)))
            if task == "parse_events":
                return schema_cls.model_validate({"events": []})
            items = []
            payload = json.loads(user_prompt.split("\n", 1)[1])["dishes"]
            for d in payload:
                items.append(
                    {
                        "recipe_id": d["recipe_id"],
                        "explanation_bn": f"{d['name_bn']} পরিবারের জন্য নিরাপদ।",
                        "explanation_en": f"{d['name_en']} is safe for everyone.",
                        "split_instruction_bn": None,
                        "split_instruction_en": None,
                        "rule_ids": d["allowed_rule_ids"],
                    }
                )
            return schema_cls.model_validate({"items": items})

    spy_llm = RecordingLLM()
    parse_events_from_text("১ কেজি লাউ কিনলাম", spy_llm, {}, {}, datetime.now(ZoneInfo("Asia/Dhaka")).date(), db=db_session)
    assert recorded_models[-1] == ("parse_events", spy_llm.llm_fast_model, 600)

    # Explanation caching test
    det = agent_mod.run_deterministic_menu_pipeline(
        db=db_session,
        household_id=demo.id,
        for_date=datetime.now(ZoneInfo("Asia/Dhaka")).date(),
        meal="dinner",
    )
    top_3: list[ScoredDish] = det["top_3"]
    cands_by_id = {c.recipe.id: c for c in det["shared"].candidates}
    clear_explanation_cache()

    res1 = generate_grounded_explanations(
        top_3, cands_by_id, det["tool_log"], ctx.ingredients, recipes_by_id, spy_llm, db=db_session
    )
    res2 = generate_grounded_explanations(
        top_3, cands_by_id, det["tool_log"], ctx.ingredients, recipes_by_id, spy_llm, db=db_session
    )
    assert res1["validated"] is True and res1["used_template"] is False
    assert res2.get("cached") is True
    explain_calls = [m for m in recorded_models if m[0] == "menu_explain"]
    assert len(explain_calls) == 1
    assert explain_calls[0] == ("menu_explain", spy_llm.llm_fast_model, 700)

    # Verify MCP agent exposes only 5 menu tools (not 11)
    seen_tool_names: list[str] = []

    class ToolInspectLLM(LLMClient):
        def __init__(self):
            super().__init__(groq_api_key="x", gemini_api_key="")

        def call_groq_tools(self, messages, tools, **kwargs):
            seen_tool_names.extend(t["function"]["name"] for t in tools)
            return None

    factory = menu_api.sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind(), class_=Session)
    mcp_server = menu_api.create_mcp_server(factory)
    import asyncio

    asyncio.run(
        agent_mod.run_menu_planning_agent(
            db=db_session,
            household_id=demo.id,
            for_date=datetime.now(ZoneInfo("Asia/Dhaka")).date(),
            meal="dinner",
            monthly_budget_bdt=15000,
            llm_client=ToolInspectLLM(),
            mcp_server=mcp_server,
        )
    )
    assert set(seen_tool_names) == agent_mod.MENU_AGENT_TOOL_NAMES


def test_menu_defaults_rate_limits_and_cooked_meal(client: TestClient, db_session: Session) -> None:
    """/menu/suggest & /menu/review default use_agent=False (0 LLM calls), review is rate-limited, cooked saves meal."""
    seed_reference_data(db_session)
    reset_rate_limits()
    login = client.post("/households/demo?reset=true").json()
    hdrs = _hdr(login["token"])

    llm_calls_made = {"tools": 0, "json": 0}

    class ZeroCallAssertLLM(LLMClient):
        def __init__(self):
            super().__init__(groq_api_key="fake-key", gemini_api_key="")

        def call_groq_tools(self, **kwargs):
            llm_calls_made["tools"] += 1
            return None

        def call_groq_json(self, **kwargs):
            llm_calls_made["json"] += 1
            return None

    client.app.dependency_overrides[menu_api.get_llm_client] = lambda: ZeroCallAssertLLM()
    try:
        sug = client.post("/menu/suggest", headers=hdrs, json={"meal": "lunch"})
        assert sug.status_code == 200
        assert sug.json()["used_template"] is True
        assert llm_calls_made == {"tools": 0, "json": 0}

        rev = client.post(
            "/menu/review",
            headers=hdrs,
            json={"meal": "lunch", "guest_count": 2, "guest_restrictions": [], "away_member_ids": []},
        )
        assert rev.status_code == 200
        assert rev.json()["people_count"] == 6
        assert llm_calls_made == {"tools": 0, "json": 0}

        top_id = rev.json()["top_3"][0]["recipe_id"]
        cooked = client.post(
            "/menu/cooked",
            headers=hdrs,
            json={"recipe_id": top_id, "servings": 6, "meal": "lunch"},
        )
        assert cooked.status_code == 200
        latest_log = db_session.scalars(
            select(MenuSuggestion)
            .where(MenuSuggestion.household_id == uuid.UUID(login["household_id"]))
            .order_by(MenuSuggestion.created_at.desc())
        ).first()
        assert latest_log is not None
        assert latest_log.meal == "lunch"

        # Rate limit check on /menu/review (15 req / 60s -> 16th hits 429)
        reset_rate_limits()
        for idx in range(15):
            r = client.post(
                "/menu/review",
                headers=hdrs,
                json={"meal": "dinner", "guest_count": 0, "guest_restrictions": [], "away_member_ids": []},
            )
            assert r.status_code == 200, idx
        blocked = client.post(
            "/menu/review",
            headers=hdrs,
            json={"meal": "dinner", "guest_count": 0, "guest_restrictions": [], "away_member_ids": []},
        )
        assert blocked.status_code == 429
    finally:
        client.app.dependency_overrides.pop(menu_api.get_llm_client, None)


def test_dynamic_reschedule_and_catalog(client: TestClient, db_session: Session) -> None:
    """Changing household meal_times reschedules today's pending doses; /engine/catalog reflects DB."""
    seed_reference_data(db_session)
    reset_rate_limits()
    login = client.post("/households/demo?reset=true").json()
    hdrs = _hdr(login["token"])
    hh_id = uuid.UUID(login["household_id"])

    # Trigger tick to ensure today's DoseSchedules exist
    tz = ZoneInfo(get_settings().tz)
    today = datetime.now(tz).date()
    tick = client.post(
        "/internal/tick",
        headers={"X-Tick-Secret": get_settings().tick_secret},
        params={"now": datetime.combine(today, dt_time(12, 0), tzinfo=tz).isoformat()},
    )
    assert tick.status_code == 200

    # Mark Mother's breakfast dose taken (if any) and verify dinner pending dose moves when dinner changes 21:00 -> 19:30
    patch_res = client.patch(
        f"/households/{hh_id}/settings",
        headers=hdrs,
        json={"meal_times": {"breakfast": "08:00", "lunch": "13:30", "dinner": "19:30"}},
    )
    assert patch_res.status_code == 200

    pending_doses = db_session.scalars(
        select(DoseSchedule)
        .join(Medicine)
        .join(Member)
        .where(
            Member.household_id == hh_id,
            DoseSchedule.status == "pending",
            DoseSchedule.due_at >= datetime.combine(today, dt_time(18, 0), tzinfo=tz),
            DoseSchedule.due_at < datetime.combine(today + timedelta(days=1), dt_time(0, 0), tzinfo=tz),
        )
    ).all()
    # At least one evening dose (19:30 + 20m = 19:50 or 19:30 - 30m = 19:00)
    assert pending_doses
    assert all(d.due_at.astimezone(tz).hour == 19 for d in pending_doses)

    cat = client.get("/engine/catalog", headers=hdrs)
    assert cat.status_code == 200
    cdata = cat.json()
    assert len(cdata["recipes"]) >= 40
    assert {"low_gi", "low_potassium", "low_purine", "low_sodium"}.issubset(set(cdata["presets"]))
    assert "prawn_shellfish" in cdata["allergens"]
    assert "ace_inhibitor" in cdata["drug_classes"]


def test_prod_security_guards_and_upload_limits(monkeypatch: pytest.MonkeyPatch, client: TestClient, db_session: Session) -> None:
    """Test ENV=prod guards on demo reset, tick override, login rate limiting, and upload >10MB rejection."""
    seed_reference_data(db_session)
    reset_rate_limits()

    # Create a consented household for upload limit test before flipping env=prod
    created = client.post(
        "/households",
        json={"name": "Upload Guard Test", "pin": "1234", "consent_given": True},
    ).json()
    hdrs = _hdr(created["token"])
    mem = client.post("/members", headers=hdrs, json={"name": "Sadia", "role": "other", "age_group": "adult"}).json()

    # Over-10MB upload rejected cleanly with 413 PAYLOAD_TOO_LARGE
    too_big = b"A" * (10 * 1024 * 1024 + 256)
    rx_big = client.post(
        f"/members/{mem['id']}/prescription",
        headers=hdrs,
        files={"file": ("huge.jpg", io.BytesIO(too_big), "image/jpeg")},
    )
    assert rx_big.status_code == 413

    aud_big = client.post(
        "/events/parse",
        headers=hdrs,
        files={"audio": ("huge.webm", io.BytesIO(too_big), "audio/webm")},
    )
    assert aud_big.status_code == 413

    # Switch settings to prod
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("ALLOW_DEMO_TICK_OVERRIDE", "false")
    get_settings.cache_clear()

    # /households/demo?reset=true forbidden without X-Tick-Secret in prod
    r_forbidden = client.post("/households/demo?reset=true")
    assert r_forbidden.status_code == 403
    assert r_forbidden.json()["code"] == "DEMO_RESET_FORBIDDEN"

    # /households/demo?reset=false still works for read/login
    r_login_only = client.post("/households/demo")
    assert r_login_only.status_code == 200

    # /households/demo?reset=true works in prod with valid X-Tick-Secret
    r_authorized = client.post(
        "/households/demo?reset=true",
        headers={"X-Tick-Secret": get_settings().tick_secret},
    )
    assert r_authorized.status_code == 200

    # /internal/tick?now=... forbidden in prod when ALLOW_DEMO_TICK_OVERRIDE=false
    r_tick_now = client.post(
        "/internal/tick",
        headers={"X-Tick-Secret": get_settings().tick_secret},
        params={"now": "2026-11-23T21:00:00+06:00"},
    )
    assert r_tick_now.status_code == 403
    assert r_tick_now.json()["code"] == "TICK_OVERRIDE_FORBIDDEN"

    # /households/login brute-force rate limit (10 calls / 300s -> 11th returns 429)
    reset_rate_limits()
    for _ in range(10):
        res = client.post("/households/login", json={"access_code": created["access_code"], "pin": "0000"})
        assert res.status_code == 401
    res_11 = client.post("/households/login", json={"access_code": created["access_code"], "pin": "1234"})
    assert res_11.status_code == 429

