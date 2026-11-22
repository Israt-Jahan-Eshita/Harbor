"""Plain LLM baseline runner (no Harbor deterministic core or MCP tools) for 30-case benchmark."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from groq import Groq
from pydantic import BaseModel, Field, ValidationError


class BaselineLLMOutput(BaseModel):
    recommended_keys: list[str] = Field(default_factory=list, max_length=10)
    cited_rules: list[str] = Field(default_factory=list, max_length=20)
    rationale: str = Field(default="", max_length=1000)


BASELINE_SYSTEM_PROMPT = (
    "You are a helpful family cooking assistant in Bangladesh. "
    "Given household members, dietary conditions, allergies, confirmed medications, any guests, "
    "and a list of candidate Bangladeshi dishes, recommend UP TO 3 dishes that are completely safe "
    "for EVERY person present to eat from a shared pot.\n"
    "Rules:\n"
    "- Never recommend a dish if an ingredient could conflict with any allergy, diet preset, age rule, "
    "or confirmed medication.\n"
    "- If a member has an unmapped or unknown medication safety status, do NOT guess safety: "
    "return an empty recommended_keys list [].\n"
    "- If fewer than 3 dishes are safe, return only the safe dishes.\n"
    "- Return STRICT JSON ONLY matching this exact schema:\n"
    '{"recommended_keys": ["recipe_key_1"], "cited_rules": ["RULE_ID"], "rationale": "short summary"}'
)


def _strip_fences(raw: str) -> str:
    cleaned = (raw or "").strip()
    m = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", cleaned, re.IGNORECASE)
    return m.group(1).strip() if m else cleaned


def build_baseline_user_prompt(
    case: dict[str, Any],
    recipes_by_key: dict[str, dict[str, Any]],
) -> str:
    """Build realistic natural-language + profile prompt without Harbor's core/ingredient DB."""
    cand_lines = []
    for rkey in case["candidate_recipe_keys"]:
        rec = recipes_by_key.get(rkey, {})
        cand_lines.append(
            f"- {rkey}: {rec.get('name_bn', rkey)} ({rec.get('name_en', rkey)})"
        )

    members_summary = []
    for m in case.get("members", []):
        meds = [
            f"{med['name_as_written']} (class={med.get('drug_class')}, confirmed={med.get('verified_by_caregiver')})"
            for med in m.get("medicines", [])
        ]
        members_summary.append(
            f"- {m['name']} [age={m['age_group']}, allergies={m.get('allergies', [])}, "
            f"diet_presets={m.get('diet_presets', [])}, medicines={meds}]"
        )

    guests_summary = case.get("guests", [])
    return (
        f"Household Situation: {case['prompt_bn']}\n"
        f"Members:\n" + "\n".join(members_summary) + "\n"
        f"Guests: {json.dumps(guests_summary, ensure_ascii=False)}\n"
        f"Candidate Dishes (pick up to 3 SAFE keys from this exact list):\n"
        + "\n".join(cand_lines)
        + "\nReturn JSON only."
    )


def run_plain_groq_case(
    client: Groq,
    model: str,
    case: dict[str, Any],
    recipes_by_key: dict[str, dict[str, Any]],
    max_retries: int = 4,
) -> dict[str, Any]:
    """Call plain Groq LLM once on a single benchmark case with backoff on rate limits."""
    user_prompt = build_baseline_user_prompt(case, recipes_by_key)
    last_err: Exception | None = None
    start = time.perf_counter()

    for attempt in range(max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": BASELINE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"},
                timeout=35.0,
            )
            raw_content = resp.choices[0].message.content or ""
            latency_ms = int((time.perf_counter() - start) * 1000)
            cleaned = _strip_fences(raw_content)
            try:
                parsed_json = json.loads(cleaned)
                validated = BaselineLLMOutput.model_validate(parsed_json)
                allowed_candidates = set(case["candidate_recipe_keys"])
                recs: list[str] = []
                for k in validated.recommended_keys:
                    if k in allowed_candidates and k not in recs:
                        recs.append(k)
                return {
                    "valid_json": True,
                    "recommended_keys": recs[:3],
                    "cited_rules": [str(r) for r in validated.cited_rules if str(r).strip()],
                    "rationale": validated.rationale,
                    "latency_ms": latency_ms,
                    "error": None,
                }
            except (json.JSONDecodeError, ValidationError) as parse_exc:
                return {
                    "valid_json": False,
                    "recommended_keys": [],
                    "cited_rules": [],
                    "rationale": cleaned[:300],
                    "latency_ms": latency_ms,
                    "error": f"PARSE_ERROR: {parse_exc}",
                }
        except Exception as exc:
            last_err = exc
            if attempt < max_retries:
                backoff = min(16.0, 1.5 * (2**attempt))
                time.sleep(backoff)
                continue
            break

    latency_ms = int((time.perf_counter() - start) * 1000)
    return {
        "valid_json": False,
        "recommended_keys": [],
        "cited_rules": [],
        "rationale": "",
        "latency_ms": latency_ms,
        "error": str(last_err) if last_err else "UNKNOWN_ERROR",
    }

