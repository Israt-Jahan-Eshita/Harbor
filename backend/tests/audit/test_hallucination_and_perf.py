"""Phase 6 Audit: 8 hallucination/grounding checks & latency benchmark (docs/05 §5 & §7)."""

from __future__ import annotations

import ast
import json
import statistics
import time
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from sqlalchemy.orm import Session

from app.core.scoring import score_dishes
from app.core.shared_pot import find_shared_pot_dishes
from app.core.types import MemberData, StockItemState
from app.core.validator import validate_response
from app.deps import reset_rate_limits
from app.llm.agent import run_menu_planning_agent
from app.llm.client import LLMClient
from app.mcp.server import create_mcp_server
from app.seed.load import seed_demo_household, seed_reference_data
from app.services.context_loader import load_rule_context_and_recipes
from tests.integration.conftest import TestSessionLocal

CORE_DIR = Path(__file__).resolve().parents[2] / "app" / "core"


@pytest.mark.asyncio
async def test_hallucination_and_grounding_checks(client: TestClient) -> None:
    """Verify all grounding, whitelist, loop-cap, missing-attr, determinism, and token checks (docs/05 §5)."""
    db = TestSessionLocal()
    try:
        seed_reference_data(db)
        hh = seed_demo_household(db, reset=True)
        reset_rate_limits()
        ctx, recipes, recipes_by_id = load_rule_context_and_recipes(db)
        mcp_srv = create_mcp_server(TestSessionLocal)

        # 1. Hostile fake outputs rejected by validator (invented recipe, invented rule, extra ingredient, Bangla/EN doses, blocked claimed safe)
        lau = next(r for r in recipes if r.key == "lau_masoor_dal")
        chingri = next(r for r in recipes if r.key == "lau_chingri")
        tool_log = [
            {
                "tool": "find_shared_pot_dishes",
                "result": {
                    "candidate_ids": [lau.id],
                    "allowed_rules_by_recipe": {lau.id: ["SAFE_DIRECT", "LOW_SODIUM_SPLIT"]},
                    "excluded_ids": [chingri.id],
                    "excluded_names_bn": [chingri.name_bn, chingri.name_en],
                },
            }
        ]
        bad_payloads = [
            {"items": [{"recipe_id": "invented-id", "explanation_bn": "নিরাপদ।", "rule_ids": ["SAFE_DIRECT"]}]},
            {"items": [{"recipe_id": lau.id, "explanation_bn": "নিরাপদ।", "rule_ids": ["FAKE_RULE_999"]}]},
            {"items": [{"recipe_id": lau.id, "explanation_bn": "ইলিশ মাছ ও আলু দিয়ে নিরাপদ।", "rule_ids": ["SAFE_DIRECT"]}]},
            {"items": [{"recipe_id": lau.id, "explanation_bn": "খেয়ে ৫০ মিগ্রা ওষুধ নিন।", "rule_ids": ["SAFE_DIRECT"]}]},
            {"items": [{"recipe_id": lau.id, "explanation_bn": "Take 10mg after food.", "rule_ids": ["SAFE_DIRECT"]}]},
            {"items": [{"recipe_id": lau.id, "explanation_bn": f"{chingri.name_bn} নিরাপদ।", "rule_ids": ["SAFE_DIRECT"]}]},
        ]
        for bp in bad_payloads:
            vres = validate_response(bp, tool_log, ctx.ingredients, recipes_by_id)
            assert vres.valid is False, f"Validator failed to reject hostile payload: {bp}"

        # 2 & 3. Non-whitelisted MCP tool call and >6 tool call loop halted -> deterministic fallback
        class NonWhitelistLLM(LLMClient):
            def __init__(self):
                super().__init__(groq_api_key="x", gemini_api_key="")

            def call_groq_tools(self, **kwargs):
                fn = type("Fn", (), {"name": "schedule_reminder", "arguments": "{}"})()
                tc = type("TC", (), {"id": "c1", "function": fn})()
                return type("Msg", (), {"content": "", "tool_calls": [tc]})()

        res_nw = await run_menu_planning_agent(db, hh.id, date(2026, 11, 22), "dinner", 14000, NonWhitelistLLM(), mcp_srv)
        assert res_nw["used_fallback"] is True
        assert "NON_WHITELISTED_TOOL" in res_nw["fallback_reason"]

        class ExcessLoopLLM(LLMClient):
            def __init__(self):
                super().__init__(groq_api_key="x", gemini_api_key="")

            def call_groq_tools(self, **kwargs):
                fn1 = type("Fn", (), {"name": "get_seasonal_items", "arguments": '{"month": 11}'})()
                fn2 = type("Fn", (), {"name": "get_seasonal_items", "arguments": '{"month": 12}'})()
                tcs = [type("TC", (), {"id": "a", "function": fn1})(), type("TC", (), {"id": "b", "function": fn2})()]
                return type("Msg", (), {"content": "", "tool_calls": tcs})()

        res_loop = await run_menu_planning_agent(db, hh.id, date(2026, 11, 22), "dinner", 14000, ExcessLoopLLM(), mcp_srv, max_tool_calls=6)
        assert res_loop["used_fallback"] is True
        assert res_loop["fallback_reason"] == "MAX_TOOL_CALLS_EXCEEDED"

        # 4. Removing an ingredient marks dependent dishes UNVERIFIED
        ctx_missing = ctx.model_copy(deep=True)
        ctx_missing.ingredients.pop("lau")
        sp_missing = find_shared_pot_dishes(
            members=[MemberData(id="m1", name="Test")],
            recipes=[lau],
            context=ctx_missing,
            for_date=date(2026, 11, 22),
        )
        assert len(sp_missing.candidates) == 0
        assert "UNKNOWN_INGREDIENT" in sp_missing.excluded[0].reasons

        # 5. Determinism across 20 runs -> byte-identical output
        outputs = []
        for _ in range(20):
            sp = find_shared_pot_dishes(
                members=[MemberData(id="m1", name="বাবা", diet_presets=["low_potassium"])],
                recipes=recipes,
                context=ctx,
                for_date=date(2026, 11, 22),
            )
            outputs.append(json.dumps([c.recipe.key for c in sp.candidates]))
        assert len(set(outputs)) == 1

        # 6. Static AST check confirming core/ imports zero network/DB/LLM modules
        forbidden_prefixes = ("httpx", "requests", "urllib", "groq", "google", "sqlalchemy", "psycopg", "fastapi")
        for py_file in CORE_DIR.glob("*.py"):
            tree = ast.parse(py_file.read_text("utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith(forbidden_prefixes), f"Forbidden import {alias.name} in {py_file.name}"
                elif isinstance(node, ast.ImportFrom) and node.module:
                    assert not node.module.startswith(forbidden_prefixes), f"Forbidden from-import {node.module} in {py_file.name}"

        # 7. Write attempts without valid confirmation_token fail
        async with Client(mcp_srv) as mcp_client:
            with pytest.raises(Exception):
                await mcp_client.call_tool(
                    "update_inventory_event",
                    {"household_id": str(hh.id), "events": [{"type": "PURCHASED", "ingredient_key": "lau", "qty_base": 500}], "confirmation_token": "forged"},
                )

        auth_tok = client.post("/households/demo").json()["token"]
        bad_conf = client.post(
            "/events/confirm",
            headers={"Authorization": f"Bearer {auth_tok}"},
            json={"confirmation_token": "forged.token", "events": [{"type": "PURCHASED", "ingredient_key": "lau", "qty_base": 500}]},
        )
        assert bad_conf.status_code == 400
    finally:
        db.close()


def test_core_and_api_latency_benchmark(client: TestClient, db_session: Session) -> None:
    """Measure pure-Python core latency and deterministic /menu/suggest API latency (docs/05 §7)."""
    seed_reference_data(db_session)
    demo = seed_demo_household(db_session, reset=True)
    ctx, recipes, _ = load_rule_context_and_recipes(db_session)
    members = [MemberData(id="p1", name="বাবা", diet_presets=["low_potassium"]), MemberData(id="p2", name="আরিফ", allergies=["prawn_shellfish"])]
    stock_full = {k: StockItemState(ingredient_key=k, raw_qty=1000.0, qty_base=1000.0) for k in ctx.ingredients}

    core_timings_ms: list[float] = []
    for _ in range(50):
        t0 = time.perf_counter()
        sp = find_shared_pot_dishes(members=members, recipes=recipes, context=ctx, for_date=date(2026, 11, 22))
        score_dishes(sp.candidates, stock_full, ctx, current_month=11)
        core_timings_ms.append((time.perf_counter() - t0) * 1000.0)

    core_median = round(statistics.median(core_timings_ms), 2)
    core_max = round(max(core_timings_ms), 2)
    assert core_median < 100.0

    hh_auth = client.post("/households/demo").json()
    headers = {"Authorization": f"Bearer {hh_auth['token']}"}
    _ = demo

    api_timings_ms: list[float] = []
    for _ in range(15):
        t0 = time.perf_counter()
        res = client.post(
            "/menu/suggest",
            headers=headers,
            json={"for_date": "2026-11-22", "meal": "dinner", "use_agent": False},
        )
        assert res.status_code == 200
        api_timings_ms.append((time.perf_counter() - t0) * 1000.0)

    api_median = round(statistics.median(api_timings_ms), 2)
    api_max = round(max(api_timings_ms), 2)
    print(
        f"\nPERF_METRICS: core_median_ms={core_median} core_max_ms={core_max} "
        f"api_menu_median_ms={api_median} api_menu_max_ms={api_max}"
    )
    assert api_median < 2000.0
