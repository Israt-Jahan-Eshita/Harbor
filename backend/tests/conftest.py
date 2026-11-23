"""Root pytest configuration guaranteeing offline LLM safety unless HARBOR_LIVE_TESTS=1."""

from __future__ import annotations

import os

import pytest

from app.config import get_settings
from app.deps import reset_rate_limits
from app.llm.client import reset_llm_guards
from app.llm.explain import clear_explanation_cache


def _allow_live_tests() -> bool:
    return os.getenv("HARBOR_LIVE_TESTS") == "1"


def pytest_configure(config) -> None:  # noqa: ARG001
    if not _allow_live_tests():
        os.environ["GROQ_API_KEY"] = ""
        os.environ["GEMINI_API_KEY"] = ""
        get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_llm_and_guards(monkeypatch: pytest.MonkeyPatch):
    """Ensure tests never leak live Groq/Gemini API keys or cross-test guard/cache state."""
    if not _allow_live_tests():
        monkeypatch.setenv("GROQ_API_KEY", "")
        monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    reset_llm_guards()
    clear_explanation_cache()
    reset_rate_limits()
    yield
    get_settings.cache_clear()
    reset_llm_guards()
    clear_explanation_cache()
    reset_rate_limits()

