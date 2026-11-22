"""Contract tests (mocked failure modes) and optional live smoke tests for app/llm/."""

from __future__ import annotations

import os
from datetime import date

import pytest

from app.core.types import HouseholdCandidate, IngredientData, RecipeData, RecipeIngredientData, ScoredDish, StockItemState
from app.llm.client import LLMClient
from app.llm.explain import generate_grounded_explanations
from app.llm.extract_prescription import extract_prescription_draft, strip_dose_text
from app.llm.parse_events import EventParseOutput, parse_events_from_text


def _ingredients() -> dict[str, IngredientData]:
    return {
        "lau": IngredientData(key="lau", name_en="Bottle Gourd", name_bn="লাউ", base_unit="g"),
        "masoor_dal": IngredientData(key="masoor_dal", name_en="Red Lentils", name_bn="মসুর ডাল", base_unit="g"),
        "oil": IngredientData(key="oil", name_en="Soybean Oil", name_bn="তেল", base_unit="ml"),
        "salt": IngredientData(key="salt", name_en="Salt", name_bn="লবণ", base_unit="g"),
        "chingri": IngredientData(key="chingri", name_en="Prawn", name_bn="চিংড়ি", base_unit="g"),
    }


def _aliases(ings: dict[str, IngredientData]) -> dict[str, IngredientData]:
    return {
        "তেল": ings["oil"],
        "oil": ings["oil"],
        "লাউ": ings["lau"],
        "lau": ings["lau"],
    }


def test_dose_stripping_in_prescription_extraction() -> None:
    assert "mg" not in strip_dose_text("Tab. Enalapril 5mg").lower()
    assert "মিগ্রা" not in strip_dose_text("লোসার্টান ৫০ মিগ্রা")

    class FakeGeminiLLM(LLMClient):
        def __init__(self):
            super().__init__(groq_api_key="", gemini_api_key="")

        def call_gemini_vision_json(self, **kwargs):
            schema = kwargs["schema_cls"]
            return schema.model_validate(
                {
                    "medicines": [
                        {
                            "name_as_written": "Tab. Enalapril 10mg",
                            "generic_guess": "enalapril 10 mg",
                            "timing": "after_food",
                            "times_per_day": 1,
                            "confidence": 0.92,
                        },
                        {
                            "name_as_written": "UnknownHerbal",
                            "generic_guess": None,
                            "timing": "unknown",
                            "times_per_day": None,
                            "confidence": 0.45,
                        },
                    ],
                    "diet_notes": ["Keep salt low", "Take 500mg calcium"],
                    "overall_confidence": 0.72,
                }
            )

    draft = extract_prescription_draft(
        b"fakeimg",
        "image/png",
        FakeGeminiLLM(),
        {"enalapril": "ace_inhibitor"},
    )
    assert draft["extraction_failed"] is False
    meds = draft["medicines"]
    assert len(meds) == 2
    assert "10mg" not in meds[0]["name_as_written"].lower()
    assert meds[0]["suggested_drug_class"] == "ace_inhibitor"
    assert meds[0]["low_confidence"] is False
    assert meds[1]["suggested_drug_class"] is None
    assert meds[1]["low_confidence"] is True
    assert all("500mg" not in n.lower() for n in draft["diet_notes"])


def test_prescription_failure_returns_safe_empty_draft() -> None:
    class FailingLLM(LLMClient):
        def __init__(self):
            super().__init__(groq_api_key="", gemini_api_key="")

        def call_gemini_vision_json(self, **kwargs):
            return None

    draft = extract_prescription_draft(b"bytes", "image/jpeg", FailingLLM(), {})
    assert draft["extraction_failed"] is True
    assert draft["medicines"] == []


def test_event_parser_contract_and_unresolved_item() -> None:
    ings = _ingredients()
    aliases = _aliases(ings)
    stock = {
        "oil": StockItemState(ingredient_key="oil", raw_qty=1000.0, qty_base=1000.0),
        "lau": StockItemState(ingredient_key="lau", raw_qty=1200.0, qty_base=1200.0),
    }

    class FakeEventLLM(LLMClient):
        def __init__(self):
            super().__init__(groq_api_key="", gemini_api_key="")

        def call_groq_json(self, **kwargs):
            return EventParseOutput.model_validate(
                {
                    "events": [
                        {"type": "ADJUST", "item_raw": "তেল", "qty_phrase": "প্রায় শেষ"},
                        {"type": "SPOILED", "item_raw": "লাউ", "qty_phrase": "অর্ধেকটা"},
                        {"type": "GUESTS", "guest_count": 4, "for_date": "কাল", "guest_restrictions": ["no_beef"]},
                        {"type": "PURCHASED", "item_raw": "অজানা_মশলা", "qty_phrase": "১ কেজি"},
                    ]
                }
            )

    res = parse_events_from_text(
        "তেল প্রায় শেষ, অর্ধেকটা লাউ পচে গেছে, কাল ৪ জন মেহমান আসবে",
        FakeEventLLM(),
        aliases,
        stock,
        today=date(2026, 11, 22),
    )
    assert res["parse_failed"] is False
    props = res["proposals"]
    assert len(props) == 4
    # Oil ADJUST from 1000 -> 100 => delta -900
    assert props[0]["ingredient_key"] == "oil"
    assert props[0]["qty_base"] == -900.0
    # Lau SPOILED half
    assert props[1]["ingredient_key"] == "lau"
    assert props[1]["qty_base"] < 0
    # Guests tomorrow
    assert props[2]["type"] == "GUESTS"
    assert props[2]["guest_count"] == 4
    assert props[2]["for_date"] == "2026-11-23"
    # Unresolved item flagged for caregiver review
    assert props[3]["ingredient_key"] is None
    assert props[3]["needs_review"] is True


def test_explainer_falls_back_on_hostile_llm_and_timeout() -> None:
    ings = _ingredients()
    dal = RecipeData(
        id="rec-dal",
        key="lau_masoor_dal",
        name_bn="লাউ দিয়ে মসুর ডাল",
        name_en="Bottle Gourd Dal",
        ingredients=[
            RecipeIngredientData(ingredient_key="lau", qty=300, unit="g"),
            RecipeIngredientData(ingredient_key="masoor_dal", qty=120, unit="g"),
            RecipeIngredientData(ingredient_key="salt", qty=5, unit="g"),
        ],
        split_step_bn="লবণ দেওয়ার আগে",
        split_removes=["salt"],
    )
    cand = HouseholdCandidate(
        recipe=dal,
        status="SAFE_WITH_SPLIT",
        split_for=["মা"],
        split_step_bn="লবণ দেওয়ার আগে",
        reasons=["LOW_SODIUM_SODIUM"],
    )
    scored = [ScoredDish(recipe=dal, status="SAFE_WITH_SPLIT", split_for=["মা"], split_step_bn="লবণ দেওয়ার আগে", reasons=["LOW_SODIUM_SODIUM"], score=0.9)]
    tool_log = [
        {
            "tool": "find_shared_pot_dishes",
            "result": {
                "candidates": [{"recipe": {"id": "rec-dal"}, "status": "SAFE_WITH_SPLIT", "reasons": ["LOW_SODIUM_SODIUM"]}],
                "excluded": [{"recipe": {"id": "rec-prawn", "name_bn": "লাউ চিংড়ি"}, "reasons": ["PRAWN_ALLERGY"]}],
            },
        }
    ]

    class HostileLLM(LLMClient):
        def __init__(self):
            super().__init__(groq_api_key="", gemini_api_key="")

        def call_groq_json(self, **kwargs):
            return kwargs["schema_cls"].model_validate(
                {
                    "items": [
                        {
                            "recipe_id": "rec-dal",
                            "explanation_bn": "চিংড়ি দিয়ে রান্না করুন এবং ওষুধ ১০ মিগ্রা বাড়ান।",
                            "explanation_en": "Add Prawn and take 10mg.",
                            "rule_ids": ["LOW_SODIUM_SODIUM"],
                        }
                    ]
                }
            )

    res_hostile = generate_grounded_explanations(
        scored, {"rec-dal": cand}, tool_log, ings, {"rec-dal": dal}, HostileLLM()
    )
    assert res_hostile["validated"] is False
    assert res_hostile["used_template"] is True
    assert "আজকের জন্য নিরাপদ: লাউ দিয়ে মসুর ডাল" in res_hostile["explanations_by_recipe"]["rec-dal"]["explanation_bn"]
    assert "Safe for today: Bottle Gourd Dal" in res_hostile["explanations_by_recipe"]["rec-dal"]["explanation_en"]


def test_repair_retry_recovers_malformed_json_in_client() -> None:
    class MockChoice:
        def __init__(self, text: str):
            self.message = type("Msg", (), {"content": text})()

    class MockResp:
        def __init__(self, text: str):
            self.choices = [MockChoice(text)]

    class FakeGroqSdk:
        def __init__(self):
            self.calls = 0
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return MockResp("{not valid json")
            return MockResp('{"events": [{"type": "GUESTS", "guest_count": 3}]}')

    client = LLMClient(groq_api_key="dummy", gemini_api_key="")
    client._groq = FakeGroqSdk()  # type: ignore[assignment]
    parsed = client.call_groq_json("parse_events", "sys", "3 guests", EventParseOutput)
    assert parsed is not None
    assert len(parsed.events) == 1
    assert parsed.events[0].guest_count == 3


@pytest.mark.skipif(os.environ.get("HARBOR_LIVE_TESTS") != "1", reason="Set HARBOR_LIVE_TESTS=1 for live LLM smoke tests")
def test_live_groq_and_gemini_smoke() -> None:
    ings = _ingredients()
    aliases = _aliases(ings)
    stock = {
        "oil": StockItemState(ingredient_key="oil", raw_qty=1000.0, qty_base=1000.0),
        "lau": StockItemState(ingredient_key="lau", raw_qty=1200.0, qty_base=1200.0),
    }
    client = LLMClient()
    res = parse_events_from_text(
        "তেল প্রায় শেষ, অর্ধেকটা লাউ পচে গেছে, কাল ৪ জন মেহমান আসবে",
        client,
        aliases,
        stock,
        today=date(2026, 11, 22),
    )
    assert res["parse_failed"] is False
    types_seen = {p["type"] for p in res["proposals"]}
    assert "GUESTS" in types_seen
    assert "SPOILED" in types_seen

    # Tiny 1x1 valid PNG generated purely in Python stdlib (no Pillow needed)
    import struct
    import zlib

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack("!IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\xff\xff")
    tiny_png = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")

    rx_draft = extract_prescription_draft(tiny_png, "image/png", client, {"enalapril": "ace_inhibitor"})
    assert rx_draft["extraction_failed"] is False
    assert isinstance(rx_draft["medicines"], list)
