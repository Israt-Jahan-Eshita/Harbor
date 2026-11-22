"""Tests for FastMCP 13-tool server and bounded planning agent guardrails (Step B11)."""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastmcp import Client
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import sign_confirmation_token
from app.llm.agent import run_menu_planning_agent
from app.llm.client import LLMClient
from app.mcp.server import create_mcp_server
from app.models import Member, Medicine
from app.seed.load import seed_demo_household, seed_reference_data
from tests.integration.conftest import TestSessionLocal


@pytest.fixture()
def db_session():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _fake_tool_call(call_id: str, name: str, args: dict):
    fn = type("Fn", (), {"name": name, "arguments": json.dumps(args)})()
    return type("ToolCall", (), {"id": call_id, "function": fn})()


@pytest.mark.asyncio
async def test_mcp_server_registers_all_13_tools_and_enforces_write_tokens(
    db_session: Session,
) -> None:
    seed_reference_data(db_session)
    hh = seed_demo_household(db_session, reset=True)
    mcp_srv = create_mcp_server(TestSessionLocal)

    async with Client(mcp_srv) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools}
        expected_13 = {
            "get_household_state",
            "get_inventory",
            "update_inventory_event",
            "normalize_bangla_qty",
            "check_dish_safe",
            "find_shared_pot_dishes",
            "score_dishes",
            "get_seasonal_items",
            "get_price_estimate",
            "calculate_bazar_shortfall",
            "find_safe_substitute",
            "build_monthly_list",
            "schedule_reminder",
        }
        assert expected_13.issubset(names)

        # Read tool works through FastMCP in-process client
        sp_res = await client.call_tool(
            "find_shared_pot_dishes",
            {"household_id": str(hh.id), "for_date": "2026-11-22", "meal": "dinner"},
        )
        assert len(sp_res.data["candidates"]) > 0

        # Write tools MUST reject missing confirmation_token
        with pytest.raises(Exception):
            await client.call_tool(
                "update_inventory_event",
                {
                    "household_id": str(hh.id),
                    "events": [{"type": "PURCHASED", "ingredient_key": "lau", "qty_base": 500}],
                    "confirmation_token": "",
                },
            )

        med = db_session.scalar(
            select(Medicine).join(Member).where(Member.household_id == hh.id)
        )
        assert med is not None
        with pytest.raises(Exception):
            await client.call_tool(
                "schedule_reminder",
                {"medicine_id": str(med.id), "for_date": "2026-11-22", "confirmation_token": "bad"},
            )

        # Valid signed confirmation token succeeds
        tok = sign_confirmation_token(str(hh.id), "events_confirm", "abc")
        ok_res = await client.call_tool(
            "update_inventory_event",
            {
                "household_id": str(hh.id),
                "events": [{"type": "PURCHASED", "ingredient_key": "lau", "qty_base": 100, "source": "ui"}],
                "confirmation_token": tok,
            },
        )
        assert len(ok_res.data["written_event_ids"]) == 1


@pytest.mark.asyncio
async def test_agent_rejects_non_whitelisted_tool_excess_calls_and_excluded_recipe(
    db_session: Session,
) -> None:
    seed_reference_data(db_session)
    hh = seed_demo_household(db_session, reset=True)
    mcp_srv = create_mcp_server(TestSessionLocal)

    # 1. Fake LLM tries write tool update_inventory_event (not in READ_TOOL_WHITELIST)
    class WriteToolAgentLLM(LLMClient):
        def __init__(self):
            super().__init__(groq_api_key="x", gemini_api_key="")

        def call_groq_tools(self, messages, tools, temperature=0.1):
            return type(
                "Msg",
                (),
                {
                    "content": "",
                    "tool_calls": [_fake_tool_call("c1", "update_inventory_event", {"household_id": str(hh.id)})],
                },
            )()

    res_blocked_tool = await run_menu_planning_agent(
        db_session, hh.id, date(2026, 11, 22), "dinner", 14000, WriteToolAgentLLM(), mcp_srv
    )
    assert res_blocked_tool["used_fallback"] is True
    assert "NON_WHITELISTED_TOOL" in res_blocked_tool["fallback_reason"]
    assert len(res_blocked_tool["top_3"]) == 3

    # 2. Fake LLM exceeds 6 tool calls -> stops at 6 and falls back
    class LoopAgentLLM(LLMClient):
        def __init__(self):
            super().__init__(groq_api_key="x", gemini_api_key="")

        def call_groq_tools(self, messages, tools, temperature=0.1):
            return type(
                "Msg",
                (),
                {
                    "content": "",
                    "tool_calls": [
                        _fake_tool_call("c1", "get_seasonal_items", {"month": 11}),
                        _fake_tool_call("c2", "get_seasonal_items", {"month": 12}),
                    ],
                },
            )()

    res_cap = await run_menu_planning_agent(
        db_session, hh.id, date(2026, 11, 22), "dinner", 14000, LoopAgentLLM(), mcp_srv, max_tool_calls=6
    )
    assert res_cap["used_fallback"] is True
    assert res_cap["fallback_reason"] == "MAX_TOOL_CALLS_EXCEEDED"
    assert len(res_cap["tool_log"]) == 6

    # 3. Fake LLM calls find_shared_pot_dishes then suggests excluded lau_chingri -> validator rejects
    class ExcludedRecipeAgentLLM(LLMClient):
        def __init__(self):
            super().__init__(groq_api_key="x", gemini_api_key="")
            self.step = 0

        def call_groq_tools(self, messages, tools, temperature=0.1):
            self.step += 1
            if self.step == 1:
                return type(
                    "Msg",
                    (),
                    {
                        "content": "",
                        "tool_calls": [
                            _fake_tool_call(
                                "c1",
                                "find_shared_pot_dishes",
                                {"household_id": str(hh.id), "for_date": "2026-11-22", "meal": "dinner"},
                            )
                        ],
                    },
                )()
            # Find lau_chingri id from compact tool result
            tool_payload = json.loads(messages[-1]["content"])
            prawn_id = next(
                e["recipe_id"]
                for e in tool_payload["excluded"]
                if e["key"] == "lau_chingri"
            )
            return type(
                "Msg",
                (),
                {
                    "content": json.dumps(
                        {
                            "items": [
                                {
                                    "recipe_id": prawn_id,
                                    "explanation_bn": "লাউ চিংড়ি রান্না করুন।",
                                    "explanation_en": "Cook bottle gourd prawn.",
                                    "rule_ids": [],
                                }
                            ]
                        }
                    ),
                    "tool_calls": [],
                },
            )()

    res_excl = await run_menu_planning_agent(
        db_session, hh.id, date(2026, 11, 22), "dinner", 14000, ExcludedRecipeAgentLLM(), mcp_srv
    )
    assert res_excl["validated"] is False
    assert res_excl["used_fallback"] is True
    assert "UNGROUNDED_RECIPE_ID" in res_excl["fallback_reason"]
    assert all(s.recipe.key != "lau_chingri" for s in res_excl["top_3"])
