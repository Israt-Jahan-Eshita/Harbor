"""Bangla quantity phrase normalization (`normalize_bangla_qty`) — pure Python."""

from __future__ import annotations

import re

from app.core.types import IngredientData, NormalizedQty

BANGLA_DIGIT_MAP = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

BANGLA_NUMBER_WORDS: dict[str, float] = {
    "আধা": 0.5,
    "আধ": 0.5,
    "অর্ধেক": 0.5,
    "এক": 1.0,
    "একের": 1.0,
    "দেড়": 1.5,
    "দুই": 2.0,
    "দু": 2.0,
    "আড়াই": 2.5,
    "তিন": 3.0,
    "চার": 4.0,
    "পাঁচ": 5.0,
    "ছয়": 6.0,
    "সাত": 7.0,
    "আট": 8.0,
    "নয়": 9.0,
    "দশ": 10.0,
    "half": 0.5,
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
}

RELATIVE_STOCK_PHRASES: list[tuple[tuple[str, ...], float, float, str]] = [
    (("প্রায় শেষ", "pray shesh", "almost empty", "almost finished"), 0.10, 0.85, "Set stock to 10% of last known stock"),
    (("একটু আছে", "সামান্য আছে", "ektu ache", "a little left"), 0.25, 0.80, "Set stock to 25% of last known stock"),
    (("শেষ", "নেই", "নাই", "shesh", "nai", "empty", "finished", "out of stock"), 0.0, 0.90, "Set stock to 0"),
]


def bangla_digits_to_ascii(text: str) -> str:
    """Convert Bangla numerals (০-৯) to ASCII digits (0-9)."""
    return text.translate(BANGLA_DIGIT_MAP)


def _extract_leading_number(token: str) -> float | None:
    token_clean = bangla_digits_to_ascii(token.strip().lower())
    if token_clean in BANGLA_NUMBER_WORDS:
        return BANGLA_NUMBER_WORDS[token_clean]
    m = re.match(r"^(\d+(?:\.\d+)?)$", token_clean)
    if m:
        return float(m.group(1))
    return None


def _is_leafy(ingredient: IngredientData | None) -> bool:
    if ingredient is None:
        return False
    return "leafy" in ingredient.tags or ingredient.category == "leafy"


def normalize_bangla_qty(
    phrase: str,
    ingredient: IngredientData | None = None,
    last_known_stock: float | None = None,
) -> NormalizedQty:
    """Normalize Bangla / Banglish / English quantity phrases per SPEC §8.3."""
    if not phrase or not phrase.strip():
        return NormalizedQty(phrase=phrase or "", confidence=0.0, needs_review=True, note="Empty quantity phrase")

    raw_clean = bangla_digits_to_ascii(phrase.strip())
    lowered = re.sub(r"\s+", " ", raw_clean.lower())

    # 1. Relative stock phrases (check longer phrases before single 'শেষ')
    for keywords, ratio, conf, note in RELATIVE_STOCK_PHRASES:
        if any(kw in lowered for kw in keywords):
            target = 0.0 if ratio == 0.0 else (round(last_known_stock * ratio, 3) if last_known_stock is not None else None)
            unit = ingredient.base_unit if ingredient else None
            return NormalizedQty(
                phrase=phrase,
                qty_base=target,
                unit_base=unit,
                confidence=conf,
                is_relative_target=True,
                target_ratio=ratio,
                needs_review=(target is None),
                note=note,
            )

    # 2. Half item phrases ("অর্ধেকটা", "আধখানা")
    if any(kw in lowered for kw in ("অর্ধেকটা", "আধখানা", "অর্ধেক", "half piece", "half a")):
        needs_rev = ingredient is not None and ingredient.base_unit != "piece"
        return NormalizedQty(
            phrase=phrase,
            qty_base=0.5,
            unit_base="piece",
            confidence=0.80 if not needs_rev else 0.70,
            needs_review=needs_rev,
            note="Approximate 0.5 of whole item (piece)",
        )

    # 3. Parse "<number_or_word> <unit>"
    # Support compact tokens like "1kg", "500g", "১কেজি"
    compact = re.sub(r"(\d+(?:\.\d+)?)([a-zA-Z\u0980-\u09FF]+)", r"\1 \2", lowered)
    tokens = compact.split()

    qty_val: float | None = None
    unit_token: str = ""
    if len(tokens) >= 2:
        maybe_num = _extract_leading_number(tokens[0])
        if maybe_num is not None:
            qty_val = maybe_num
            unit_token = " ".join(tokens[1:])
        else:
            unit_token = compact
    else:
        # Handle words like "একটা", "দুটো", "দুইটা"
        if tokens[0] in ("একটা", "একটি", "১টা", "1টা"):
            return NormalizedQty(phrase=phrase, qty_base=1.0, unit_base="piece", confidence=0.90, note="1 piece")
        if tokens[0] in ("দুটো", "দুইটা", "দুটি", "২টা", "2টা"):
            return NormalizedQty(phrase=phrase, qty_base=2.0, unit_base="piece", confidence=0.90, note="2 pieces")
        unit_token = tokens[0]

    # Unit mappings
    if qty_val is not None:
        if any(u in unit_token for u in ("কেজি", "kg", "kilo")):
            return NormalizedQty(phrase=phrase, qty_base=qty_val * 1000.0, unit_base="g", confidence=0.95)
        if any(u in unit_token for u in ("পোয়া", "poya", "poa")):
            return NormalizedQty(phrase=phrase, qty_base=qty_val * 250.0, unit_base="g", confidence=0.90, note="Approximate poya = 250g")
        if any(u in unit_token for u in ("মুঠো", "মুঠি", "mutho", "handful")):
            per_mutho = 30.0 if _is_leafy(ingredient) else 50.0
            return NormalizedQty(
                phrase=phrase,
                qty_base=qty_val * per_mutho,
                unit_base="g",
                confidence=0.75,
                note=f"Approximate handful ({per_mutho}g each)",
            )
        if any(u in unit_token for u in ("হালি", "hali")):
            return NormalizedQty(phrase=phrase, qty_base=qty_val * 4.0, unit_base="piece", confidence=0.95)
        if any(u in unit_token for u in ("ডজন", "dozen", "dozon")):
            return NormalizedQty(phrase=phrase, qty_base=qty_val * 12.0, unit_base="piece", confidence=0.95)
        if any(u in unit_token for u in ("কাপ", "cup")):
            return NormalizedQty(phrase=phrase, qty_base=qty_val * 240.0, unit_base="ml", confidence=0.80, note="Approximate cup = 240ml")
        if any(u in unit_token for u in ("চামচ", "chamoch", "spoon", "tbsp")):
            return NormalizedQty(phrase=phrase, qty_base=qty_val * 15.0, unit_base="ml", confidence=0.75, note="Approximate tablespoon = 15ml")
        if any(u in unit_token for u in ("লিটার", "liter", "litre", "ltr")) or unit_token.strip() == "l":
            return NormalizedQty(phrase=phrase, qty_base=qty_val * 1000.0, unit_base="ml", confidence=0.95)
        if any(u in unit_token for u in ("মিলি", "ml")):
            return NormalizedQty(phrase=phrase, qty_base=qty_val, unit_base="ml", confidence=0.95)
        if any(u in unit_token for u in ("গ্রাম", "gm", "gram")) or unit_token.strip() == "g":
            return NormalizedQty(phrase=phrase, qty_base=qty_val, unit_base="g", confidence=0.95)
        if any(u in unit_token for u in ("টা", "টি", "পিস", "piece", "pieces", "pcs")):
            return NormalizedQty(phrase=phrase, qty_base=qty_val, unit_base="piece", confidence=0.90)

    # Pure ASCII/Bangla number without unit when ingredient base_unit is piece
    num_only = _extract_leading_number(lowered)
    if num_only is not None and ingredient is not None:
        return NormalizedQty(
            phrase=phrase,
            qty_base=num_only,
            unit_base=ingredient.base_unit,
            confidence=0.60,
            needs_review=True,
            note="Unit omitted; assumed ingredient base_unit",
        )

    return NormalizedQty(
        phrase=phrase,
        qty_base=None,
        unit_base=None,
        confidence=0.20,
        needs_review=True,
        note="Unrecognized Bangla/English quantity phrase",
    )
