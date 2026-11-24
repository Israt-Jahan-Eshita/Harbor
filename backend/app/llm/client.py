"""Groq (LLM + Whisper STT) and Gemini (Vision) wrapper with quota guards, repair retry, and llm_calls logging."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types as genai_types
from groq import Groq
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LLMCall

logger = logging.getLogger("harbor.llm.client")

TModel = TypeVar("TModel", bound=BaseModel)

_GROQ_LOCK = threading.Lock()
_GROQ_COOLDOWN_UNTIL: float = 0.0
_GROQ_DAILY_TOKENS: dict[str, int] = {}
_ORG_ID_RE = re.compile(r"org_[A-Za-z0-9]+")


def reset_llm_guards() -> None:
    """Reset in-memory Groq cooldown and daily token budget counters (used by tests)."""
    global _GROQ_COOLDOWN_UNTIL
    with _GROQ_LOCK:
        _GROQ_COOLDOWN_UNTIL = 0.0
        _GROQ_DAILY_TOKENS.clear()


def _sanitize_error_text(raw: Any) -> str:
    return _ORG_ID_RE.sub("org_REDACTED", str(raw))[:250]


def _dhaka_today_str(tz_name: str) -> str:
    try:
        return datetime.now(ZoneInfo(tz_name)).date().isoformat()
    except Exception:
        return datetime.now().date().isoformat()


def _is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    msg = str(exc).lower()
    return "429" in msg or "rate_limit" in msg or "rate limit" in msg or "tokens per day" in msg


def _rate_limit_cooldown_seconds(exc: Exception, settings: Any) -> int:
    """Use short cooldown for 1-minute TPM/RPM spikes, full cooldown for daily/generic 429 limits."""
    msg = str(exc).lower()
    is_minute_only = (
        ("per minute" in msg or "tpm" in msg or "rpm" in msg)
        and "per day" not in msg
        and "tpd" not in msg
    )
    if is_minute_only:
        return min(20, int(settings.groq_429_cooldown_seconds))
    return int(settings.groq_429_cooldown_seconds)


def _is_model_not_found_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 404:
        return True
    msg = str(exc).lower()
    return "model_not_found" in msg or "does not exist" in msg or "do not have access" in msg


def _check_groq_guard(settings: Any, *, check_token_cap: bool = True) -> str | None:
    today_str = _dhaka_today_str(settings.tz)
    with _GROQ_LOCK:
        if time.monotonic() < _GROQ_COOLDOWN_UNTIL:
            return "GROQ_COOLDOWN_ACTIVE"
        if check_token_cap and _GROQ_DAILY_TOKENS.get(today_str, 0) >= settings.groq_daily_token_cap:
            return "GROQ_DAILY_TOKEN_CAP"
    return None


def _trigger_groq_cooldown(seconds: int) -> None:
    global _GROQ_COOLDOWN_UNTIL
    with _GROQ_LOCK:
        _GROQ_COOLDOWN_UNTIL = max(_GROQ_COOLDOWN_UNTIL, time.monotonic() + max(1, seconds))


def _record_groq_usage(resp: Any, tz_name: str) -> dict[str, int]:
    usage_obj = getattr(resp, "usage", None)
    if usage_obj is None and isinstance(resp, dict):
        usage_obj = resp.get("usage")
    prompt_t = int(getattr(usage_obj, "prompt_tokens", 0) or (usage_obj.get("prompt_tokens", 0) if isinstance(usage_obj, dict) else 0) or 0)
    completion_t = int(getattr(usage_obj, "completion_tokens", 0) or (usage_obj.get("completion_tokens", 0) if isinstance(usage_obj, dict) else 0) or 0)
    total_t = int(getattr(usage_obj, "total_tokens", 0) or (usage_obj.get("total_tokens", 0) if isinstance(usage_obj, dict) else 0) or (prompt_t + completion_t))

    today_str = _dhaka_today_str(tz_name)
    with _GROQ_LOCK:
        _GROQ_DAILY_TOKENS.clear() if len(_GROQ_DAILY_TOKENS) > 7 and today_str not in _GROQ_DAILY_TOKENS else None
        _GROQ_DAILY_TOKENS[today_str] = _GROQ_DAILY_TOKENS.get(today_str, 0) + max(0, total_t)

    return {
        "prompt_tokens": prompt_t,
        "completion_tokens": completion_t,
        "total_tokens": total_t,
    }


def _strip_json_fences(raw: str) -> str:
    cleaned = raw.strip()
    fence_match = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", cleaned, re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    return cleaned


def _log_llm_call(
    db: Session | None,
    task: str,
    model: str,
    input_summary: str,
    output: dict[str, Any] | list[Any] | None,
    validated: bool,
    latency_ms: int,
) -> None:
    if db is None:
        return
    try:
        db.add(
            LLMCall(
                task=task,
                model=model,
                input_summary=input_summary[:250],
                output=output,
                validated=validated,
                latency_ms=max(0, latency_ms),
            )
        )
        db.flush()
    except Exception as exc:  # pragma: no cover - never crash caller on audit log write
        logger.warning("Failed to record llm_call task=%s: %s", task, exc)


class LLMClient:
    """Thin resilient client wrapping Groq and Gemini APIs (all outputs untrusted)."""

    def __init__(
        self,
        groq_api_key: str | None = None,
        gemini_api_key: str | None = None,
        llm_model: str | None = None,
        llm_fast_model: str | None = None,
        stt_model: str | None = None,
        vision_model: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        settings = get_settings()
        self.groq_api_key = groq_api_key if groq_api_key is not None else settings.groq_api_key
        self.gemini_api_key = gemini_api_key if gemini_api_key is not None else settings.gemini_api_key
        self.llm_model = llm_model or settings.llm_model
        self.llm_fast_model = llm_fast_model or settings.llm_fast_model
        self.stt_model = stt_model or settings.stt_model
        self.vision_model = vision_model or settings.vision_model
        self.timeout_seconds = timeout_seconds

        # max_retries=0 prevents hidden SDK double-retries when Groq returns 429 or transient errors
        self._groq: Groq | None = (
            Groq(api_key=self.groq_api_key, timeout=timeout_seconds, max_retries=0)
            if self.groq_api_key
            else None
        )
        self._gemini: genai.Client | None = (
            genai.Client(api_key=self.gemini_api_key)
            if self.gemini_api_key
            else None
        )

    def call_groq_json(
        self,
        task: str,
        system_prompt: str,
        user_prompt: str,
        schema_cls: type[TModel],
        db: Session | None = None,
        temperature: float = 0.1,
        input_summary: str | None = None,
        model_override: str | None = None,
        max_completion_tokens: int = 800,
    ) -> TModel | None:
        """Call Groq JSON mode, parse into Pydantic schema, retry once on parse error."""
        if self._groq is None:
            logger.info("Groq client disabled (missing key) for task=%s", task)
            return None

        settings = get_settings()
        active_model = model_override or self.llm_model
        summary = input_summary or user_prompt[:200]
        guard_reason = _check_groq_guard(settings)
        if guard_reason:
            logger.warning("Skipping Groq call task=%s due to %s", task, guard_reason)
            _log_llm_call(db, task, active_model, summary, {"skipped": guard_reason}, False, 0)
            return None

        start = time.perf_counter()
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        last_output: dict[str, Any] | None = None
        for attempt in range(2):
            if attempt > 0:
                guard_retry = _check_groq_guard(settings)
                if guard_retry:
                    _log_llm_call(db, task, active_model, summary, {"skipped": guard_retry}, False, 0)
                    return None
            try:
                req_kwargs: dict[str, Any] = {
                    "model": active_model,
                    "messages": messages,
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                    "max_completion_tokens": max_completion_tokens,
                }
                if "gpt-oss" in active_model.lower():
                    req_kwargs["reasoning_effort"] = "low"

                resp = self._groq.chat.completions.create(**req_kwargs)
                usage = _record_groq_usage(resp, settings.tz)
                raw_text = resp.choices[0].message.content or ""
                data = json.loads(_strip_json_fences(raw_text))
                last_output = data if isinstance(data, dict) else {"raw": data}
                parsed = schema_cls.model_validate(data)
                latency_ms = int((time.perf_counter() - start) * 1000)
                audit_payload = {**last_output, "_usage": usage}
                _log_llm_call(db, task, active_model, summary, audit_payload, True, latency_ms)
                return parsed
            except (json.JSONDecodeError, ValidationError) as parse_err:
                if attempt == 0:
                    messages.append({"role": "assistant", "content": raw_text if "raw_text" in locals() else "{}"})
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Your JSON failed validation with error: {parse_err}. Return corrected valid JSON only.",
                        }
                    )
                    continue
                latency_ms = int((time.perf_counter() - start) * 1000)
                _log_llm_call(
                    db,
                    task,
                    active_model,
                    summary,
                    last_output or {"error": _sanitize_error_text(parse_err)},
                    False,
                    latency_ms,
                )
                return None
            except Exception as exc:
                if _is_model_not_found_error(exc) and attempt == 0 and active_model != "openai/gpt-oss-20b":
                    logger.warning("Groq model %s unavailable; falling back to openai/gpt-oss-20b", active_model)
                    active_model = "openai/gpt-oss-20b"
                    continue
                if _is_rate_limit_error(exc):
                    _trigger_groq_cooldown(_rate_limit_cooldown_seconds(exc, settings))
                safe_err = _sanitize_error_text(exc)
                logger.warning("Groq call error task=%s attempt=%d: %s", task, attempt, safe_err)
                latency_ms = int((time.perf_counter() - start) * 1000)
                _log_llm_call(db, task, active_model, summary, {"error": safe_err}, False, latency_ms)
                return None

        return None

    def call_groq_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float = 0.1,
        db: Session | None = None,
        task: str = "menu_agent_turn",
        max_completion_tokens: int = 800,
        model_override: str | None = None,
    ) -> Any | None:
        """Single tool-calling completion turn for the bounded agent loop."""
        if self._groq is None:
            return None
        settings = get_settings()
        active_model = model_override or self.llm_model
        summary = f"turns={len(messages)} tools={len(tools)}"
        guard_reason = _check_groq_guard(settings)
        if guard_reason:
            logger.warning("Skipping Groq tool turn due to %s", guard_reason)
            _log_llm_call(db, task, active_model, summary, {"skipped": guard_reason}, False, 0)
            return None

        start = time.perf_counter()
        try:
            req_kwargs: dict[str, Any] = {
                "model": active_model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": temperature,
                "max_completion_tokens": max_completion_tokens,
            }
            if "gpt-oss" in active_model.lower():
                req_kwargs["reasoning_effort"] = "low"

            resp = self._groq.chat.completions.create(**req_kwargs)
            usage = _record_groq_usage(resp, settings.tz)
            msg = resp.choices[0].message
            latency_ms = int((time.perf_counter() - start) * 1000)
            _log_llm_call(
                db,
                task,
                active_model,
                summary,
                {"has_tool_calls": bool(getattr(msg, "tool_calls", None)), "_usage": usage},
                True,
                latency_ms,
            )
            return msg
        except Exception as exc:
            if _is_rate_limit_error(exc):
                _trigger_groq_cooldown(_rate_limit_cooldown_seconds(exc, settings))
            safe_err = _sanitize_error_text(exc)
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.warning("Groq tool call turn failed: %s", safe_err)
            _log_llm_call(db, task, active_model, summary, {"error": safe_err}, False, latency_ms)
            return None

    def transcribe_audio(
        self,
        audio_bytes: bytes,
        filename: str = "voice.webm",
        language: str = "bn",
        db: Session | None = None,
    ) -> str | None:
        """Transcribe voice note with Groq Whisper large v3; never persists audio bytes."""
        if self._groq is None or not audio_bytes:
            return None
        settings = get_settings()
        summary = f"audio_bytes={len(audio_bytes)}, filename={filename}"
        guard_reason = _check_groq_guard(settings, check_token_cap=False)
        if guard_reason:
            logger.warning("Skipping Whisper STT due to %s", guard_reason)
            _log_llm_call(db, "stt_transcribe", self.stt_model, summary, {"skipped": guard_reason}, False, 0)
            return None

        start = time.perf_counter()
        try:
            resp = self._groq.audio.transcriptions.create(
                file=(filename, audio_bytes),
                model=self.stt_model,
                language=language,
            )
            text = getattr(resp, "text", None) or (resp.get("text") if isinstance(resp, dict) else None)
            latency_ms = int((time.perf_counter() - start) * 1000)
            ok = bool(text and str(text).strip())
            _log_llm_call(
                db,
                "stt_transcribe",
                self.stt_model,
                summary,
                {"text_len": len(text) if text else 0},
                ok,
                latency_ms,
            )
            return str(text).strip() if ok else None
        except Exception as exc:
            if _is_rate_limit_error(exc):
                _trigger_groq_cooldown(_rate_limit_cooldown_seconds(exc, settings))
            safe_err = _sanitize_error_text(exc)
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.warning("Whisper STT failed: %s", safe_err)
            _log_llm_call(db, "stt_transcribe", self.stt_model, summary, {"error": safe_err[:200]}, False, latency_ms)
            return None

    def call_gemini_vision_json(
        self,
        task: str,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        mime_type: str,
        schema_cls: type[TModel],
        db: Session | None = None,
    ) -> TModel | None:
        """Extract JSON from an image via Gemini vision with one repair retry (never stores image)."""
        if self._gemini is None or not image_bytes:
            logger.info("Gemini client disabled or empty image for task=%s", task)
            return None

        start = time.perf_counter()
        summary = f"image_bytes={len(image_bytes)}, mime={mime_type}"
        image_part = genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        prompt_text = user_prompt
        last_output: dict[str, Any] | None = None

        gen_config_kwargs: dict[str, Any] = {
            "system_instruction": system_prompt,
            "temperature": 0.1,
            "max_output_tokens": 2048,
            "response_mime_type": "application/json",
        }
        if hasattr(genai_types, "ThinkingConfig"):
            gen_config_kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=0)

        for attempt in range(2):
            try:
                resp = self._gemini.models.generate_content(
                    model=self.vision_model,
                    contents=[image_part, prompt_text],
                    config=genai_types.GenerateContentConfig(**gen_config_kwargs),
                )
                raw_text = resp.text or ""
                data = json.loads(_strip_json_fences(raw_text))
                last_output = data if isinstance(data, dict) else {"raw": data}
                parsed = schema_cls.model_validate(data)
                latency_ms = int((time.perf_counter() - start) * 1000)
                _log_llm_call(
                    db,
                    task,
                    self.vision_model,
                    summary,
                    {"medicine_count": len(getattr(parsed, "medicines", []))},
                    True,
                    latency_ms,
                )
                return parsed
            except (json.JSONDecodeError, ValidationError) as parse_err:
                if attempt == 0:
                    prompt_text = (
                        f"{user_prompt}\nPrevious output failed validation: {parse_err}. "
                        "Return valid JSON only matching the schema."
                    )
                    continue
                latency_ms = int((time.perf_counter() - start) * 1000)
                _log_llm_call(
                    db,
                    task,
                    self.vision_model,
                    summary,
                    last_output or {"error": _sanitize_error_text(parse_err)},
                    False,
                    latency_ms,
                )
                return None
            except Exception as exc:
                safe_err = _sanitize_error_text(exc)
                latency_ms = int((time.perf_counter() - start) * 1000)
                logger.warning("Gemini vision error task=%s: %s", task, safe_err)
                _log_llm_call(db, task, self.vision_model, summary, {"error": safe_err}, False, latency_ms)
                return None

        return None
