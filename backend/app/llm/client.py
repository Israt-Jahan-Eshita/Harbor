"""Groq (LLM + Whisper STT) and Gemini (Vision) wrapper with timeouts, repair retry, and llm_calls audit logging."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, TypeVar

from google import genai
from google.genai import types as genai_types
from groq import Groq
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LLMCall

logger = logging.getLogger("harbor.llm.client")

TModel = TypeVar("TModel", bound=BaseModel)


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
        stt_model: str | None = None,
        vision_model: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        settings = get_settings()
        self.groq_api_key = groq_api_key if groq_api_key is not None else settings.groq_api_key
        self.gemini_api_key = gemini_api_key if gemini_api_key is not None else settings.gemini_api_key
        self.llm_model = llm_model or settings.llm_model
        self.stt_model = stt_model or settings.stt_model
        self.vision_model = vision_model or settings.vision_model
        self.timeout_seconds = timeout_seconds

        self._groq: Groq | None = (
            Groq(api_key=self.groq_api_key, timeout=timeout_seconds, max_retries=1)
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
    ) -> TModel | None:
        """Call Groq JSON mode, parse into Pydantic schema, retry once on parse error."""
        if self._groq is None:
            logger.info("Groq client disabled (missing key) for task=%s", task)
            return None

        start = time.perf_counter()
        summary = input_summary or user_prompt[:200]
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        last_output: dict[str, Any] | None = None
        for attempt in range(2):
            try:
                resp = self._groq.chat.completions.create(
                    model=self.llm_model,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    response_format={"type": "json_object"},
                    max_completion_tokens=1500,
                )
                raw_text = resp.choices[0].message.content or ""
                data = json.loads(_strip_json_fences(raw_text))
                last_output = data if isinstance(data, dict) else {"raw": data}
                parsed = schema_cls.model_validate(data)
                latency_ms = int((time.perf_counter() - start) * 1000)
                _log_llm_call(db, task, self.llm_model, summary, last_output, True, latency_ms)
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
                    self.llm_model,
                    summary,
                    last_output or {"error": str(parse_err)[:250]},
                    False,
                    latency_ms,
                )
                return None
            except Exception as exc:
                logger.warning("Groq call error task=%s attempt=%d: %s", task, attempt, exc)
                latency_ms = int((time.perf_counter() - start) * 1000)
                _log_llm_call(db, task, self.llm_model, summary, {"error": str(exc)[:250]}, False, latency_ms)
                return None

        return None

    def call_groq_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float = 0.1,
    ) -> Any | None:
        """Single tool-calling completion turn for the bounded agent loop."""
        if self._groq is None:
            return None
        try:
            resp = self._groq.chat.completions.create(
                model=self.llm_model,
                messages=messages,  # type: ignore[arg-type]
                tools=tools,  # type: ignore[arg-type]
                tool_choice="auto",
                temperature=temperature,
                max_completion_tokens=1024,
            )
            return resp.choices[0].message
        except Exception as exc:
            logger.warning("Groq tool call turn failed: %s", exc)
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
        start = time.perf_counter()
        summary = f"audio_bytes={len(audio_bytes)}, filename={filename}"
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
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.warning("Whisper STT failed: %s", exc)
            _log_llm_call(db, "stt_transcribe", self.stt_model, summary, {"error": str(exc)[:200]}, False, latency_ms)
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

        for attempt in range(2):
            try:
                resp = self._gemini.models.generate_content(
                    model=self.vision_model,
                    contents=[image_part, prompt_text],
                    config=genai_types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.1,
                        response_mime_type="application/json",
                    ),
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
                    last_output or {"error": str(parse_err)[:250]},
                    False,
                    latency_ms,
                )
                return None
            except Exception as exc:
                latency_ms = int((time.perf_counter() - start) * 1000)
                logger.warning("Gemini vision error task=%s: %s", task, exc)
                _log_llm_call(db, task, self.vision_model, summary, {"error": str(exc)[:250]}, False, latency_ms)
                return None

        return None
