"""Unit tests for Bangla quantity phrase normalization (core/bangla_qty.py)."""

from __future__ import annotations

from app.core.bangla_qty import bangla_digits_to_ascii, normalize_bangla_qty
from app.core.types import IngredientData


def test_bangla_digits_conversion() -> None:
    assert bangla_digits_to_ascii("১২৩৪৫৬৭৮৯০") == "1234567890"
    assert bangla_digits_to_ascii("২.৫ কেজি") == "2.5 কেজি"


def test_spec_8_3_table_phrases() -> None:
    leafy = IngredientData(
        key="palong_shak", name_en="Spinach", name_bn="পালং শাক",
        category="leafy", tags=["leafy"], base_unit="g",
    )
    dal = IngredientData(
        key="masoor_dal", name_en="Dal", name_bn="মসুর ডাল",
        category="dal", tags=[], base_unit="g",
    )
    lau = IngredientData(
        key="lau", name_en="Lau", name_bn="লাউ",
        category="vegetable", tags=[], base_unit="g",
    )
    oil = IngredientData(
        key="oil", name_en="Oil", name_bn="তেল",
        category="oil", tags=[], base_unit="ml",
    )

    assert normalize_bangla_qty("এক কেজি").qty_base == 1000.0
    assert normalize_bangla_qty("১ কেজি").unit_base == "g"
    assert normalize_bangla_qty("আধা কেজি").qty_base == 500.0
    assert normalize_bangla_qty("আধ কেজি").qty_base == 500.0
    assert normalize_bangla_qty("এক পোয়া").qty_base == 250.0
    assert normalize_bangla_qty("আধা পোয়া").qty_base == 125.0

    # Leafy greens vs general handful
    assert normalize_bangla_qty("এক মুঠো", ingredient=leafy).qty_base == 30.0
    assert normalize_bangla_qty("এক মুঠো", ingredient=dal).qty_base == 50.0
    assert normalize_bangla_qty("দুই মুঠো", ingredient=dal).qty_base == 100.0

    hali = normalize_bangla_qty("এক হালি")
    assert hali.qty_base == 4.0 and hali.unit_base == "piece"

    dozen = normalize_bangla_qty("এক ডজন")
    assert dozen.qty_base == 12.0 and dozen.unit_base == "piece"

    cup = normalize_bangla_qty("এক কাপ")
    assert cup.qty_base == 240.0 and cup.unit_base == "ml"

    spoon = normalize_bangla_qty("এক চামচ")
    assert spoon.qty_base == 15.0 and spoon.unit_base == "ml"

    half_lau = normalize_bangla_qty("অর্ধেকটা", ingredient=lau)
    assert half_lau.qty_base == 0.5 and half_lau.unit_base == "piece"
    assert normalize_bangla_qty("আধখানা").qty_base == 0.5

    almost_done = normalize_bangla_qty("প্রায় শেষ", ingredient=oil, last_known_stock=1000.0)
    assert almost_done.is_relative_target is True
    assert almost_done.target_ratio == 0.10
    assert almost_done.qty_base == 100.0

    little_left = normalize_bangla_qty("একটু আছে", ingredient=oil, last_known_stock=800.0)
    assert little_left.target_ratio == 0.25
    assert little_left.qty_base == 200.0

    finished = normalize_bangla_qty("শেষ", ingredient=oil, last_known_stock=500.0)
    assert finished.target_ratio == 0.0
    assert finished.qty_base == 0.0
    assert normalize_bangla_qty("নেই").qty_base == 0.0


def test_unknown_phrase_returns_low_confidence() -> None:
    res = normalize_bangla_qty("অদ্ভুত কিছু পরিমাণ")
    assert res.qty_base is None
    assert res.confidence < 0.5
    assert res.needs_review is True
