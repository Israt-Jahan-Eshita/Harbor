"""Prescription photo extraction (Gemini vision) + dose stripping + fuzzy drug class mapping."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from app.llm.client import LLMClient
from app.llm.prompts import PRESCRIPTION_SYSTEM_PROMPT

DOSE_SUBSTR_RE = re.compile(
    r"(?:(?<![a-zA-Z\u0980-\u09FF])[0-9০-৯]+(?:\.[0-9০-৯]+)?\s*(?:mg|mcg|gm|g|ml|iu|%|মিগ্রা|মিলিগ্রাম|মি\.গ্রা\.|tab(?:let)?s?|cap(?:sule)?s?|ট্যাবলেট|ক্যাপসুল)(?![a-zA-Z\u0980-\u09FF]))"
    r"|(?:(?<![0-9০-৯])[0-9০-৯]+\s*\+\s*[0-9০-৯]+\s*\+\s*[0-9০-৯]+(?![0-9০-৯]))",
    re.IGNORECASE,
)

FORM_PREFIX_RE = re.compile(r"^(?:tab\.?|cap\.?|syp\.?|inj\.?|ট্যাব\.?|ক্যাপ\.?)\s*", re.IGNORECASE)


def strip_dose_text(value: str) -> str:
    """Remove any dose numbers/units so Harbor never surfaces or stores medicine dosages."""
    cleaned = DOSE_SUBSTR_RE.sub("", value)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;-")
    return cleaned


class ExtractedMedicineRow(BaseModel):
    name_as_written: str = Field(..., min_length=1, max_length=150)
    generic_guess: str | None = Field(default=None, max_length=150)
    timing: Literal["before_food", "after_food", "with_food", "any", "unknown"] = "unknown"
    times_per_day: int | None = Field(default=None, ge=1, le=6)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("name_as_written")
    @classmethod
    def sanitize_name(cls, value: str) -> str:
        stripped = strip_dose_text(value)
        return stripped or value.strip()[:150]

    @field_validator("generic_guess")
    @classmethod
    def sanitize_generic(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = strip_dose_text(value)
        return stripped or None


class PrescriptionExtractionDraft(BaseModel):
    medicines: list[ExtractedMedicineRow] = Field(default_factory=list, max_length=30)
    diet_notes: list[str] = Field(default_factory=list, max_length=20)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("diet_notes")
    @classmethod
    def sanitize_notes(cls, notes: list[str]) -> list[str]:
        return [strip_dose_text(n) for n in notes if strip_dose_text(n)]


def suggest_drug_class(
    name_as_written: str,
    generic_guess: str | None,
    drug_class_map: dict[str, str],
) -> tuple[str | None, float]:
    """Fuzzy-match extracted drug name or generic guess against seed drug_class_map."""
    if not drug_class_map:
        return None, 0.0

    candidates: list[str] = []
    for raw in (generic_guess, name_as_written):
        if not raw:
            continue
        cleaned = FORM_PREFIX_RE.sub("", strip_dose_text(raw)).strip().lower()
        if cleaned:
            candidates.append(cleaned)
            # Also try the first alphabetic word (e.g., "enalapril maleate" -> "enalapril")
            first_word = cleaned.split()[0]
            if first_word not in candidates:
                candidates.append(first_word)

    known_names = list(drug_class_map.keys())
    for cand in candidates:
        if cand in drug_class_map:
            return drug_class_map[cand], 1.0

    best_class: str | None = None
    best_score = 0.0
    for cand in candidates:
        match = process.extractOne(cand, known_names, scorer=fuzz.WRatio, score_cutoff=82)
        if match:
            matched_name, score, _ = match
            norm_score = round(score / 100.0, 2)
            if norm_score > best_score:
                best_score = norm_score
                best_class = drug_class_map[matched_name]

    return best_class, best_score


def extract_prescription_draft(
    image_bytes: bytes,
    mime_type: str,
    llm_client: LLMClient,
    drug_class_map: dict[str, str],
    db: Session | None = None,
) -> dict:
    """Call Gemini vision for draft prescription extraction (never auto-activates medicines)."""
    user_prompt = (
        "Read all medicines and dietary notes visible in this prescription image. "
        "Do NOT include any doses or mg numbers. Return JSON only."
    )
    parsed = llm_client.call_gemini_vision_json(
        task="prescription_extract",
        system_prompt=PRESCRIPTION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        image_bytes=image_bytes,
        mime_type=mime_type,
        schema_cls=PrescriptionExtractionDraft,
        db=db,
    )
    if parsed is None:
        return {
            "medicines": [],
            "diet_notes": [],
            "overall_confidence": 0.0,
            "extraction_failed": True,
        }

    enriched_rows = []
    for row in parsed.medicines:
        suggested_class, match_conf = suggest_drug_class(
            row.name_as_written,
            row.generic_guess,
            drug_class_map,
        )
        enriched_rows.append(
            {
                "name_as_written": row.name_as_written,
                "generic_guess": row.generic_guess,
                "timing": row.timing,
                "times_per_day": row.times_per_day,
                "confidence": row.confidence,
                "suggested_drug_class": suggested_class,
                "drug_match_confidence": match_conf,
                "low_confidence": row.confidence < 0.70 or suggested_class is None,
            }
        )

    return {
        "medicines": enriched_rows,
        "diet_notes": parsed.diet_notes,
        "overall_confidence": parsed.overall_confidence,
        "extraction_failed": False,
    }
