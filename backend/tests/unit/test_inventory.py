"""Unit tests for event-sourced inventory math and expiry flags (core/inventory.py)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.inventory import compute_adjust_delta, compute_stock
from app.core.types import IngredientData, InventoryEventData


def test_stock_events_spoiled_adjust_and_clamp() -> None:
    now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
    ingredients = {
        "lau": IngredientData(key="lau", name_en="Lau", name_bn="লাউ", perishable_days=7, base_unit="g"),
        "oil": IngredientData(key="oil", name_en="Oil", name_bn="তেল", perishable_days=365, base_unit="ml"),
    }
    events = [
        InventoryEventData(
            event_type="PURCHASED", ingredient_key="lau", qty_base=1000.0,
            created_at=now - timedelta(days=5),  # 5/7 = 0.714 >= 0.70 near_expiry!
        ),
        InventoryEventData(
            event_type="SPOILED", ingredient_key="lau", qty_base=-400.0,
            created_at=now - timedelta(days=1),
        ),
        InventoryEventData(
            event_type="PURCHASED", ingredient_key="oil", qty_base=500.0,
            created_at=now - timedelta(days=10),
        ),
        InventoryEventData(
            event_type="COOKED", ingredient_key="oil", qty_base=-700.0,
            created_at=now - timedelta(days=2),
        ),
    ]
    stock = compute_stock(events, ingredients, now)

    assert stock["lau"].qty_base == 600.0
    assert stock["lau"].clamped_negative is False
    assert stock["lau"].near_expiry is True
    assert stock["lau"].expiry_ratio >= 0.70

    # Oil went negative (-200), must clamp to 0 and flag
    assert stock["oil"].raw_qty == -200.0
    assert stock["oil"].qty_base == 0.0
    assert stock["oil"].clamped_negative is True

    # Adjust delta to set 600 -> 100
    assert compute_adjust_delta(600.0, 100.0) == -500.0
