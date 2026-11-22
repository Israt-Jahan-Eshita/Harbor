"""Event-sourced inventory stock calculation and expiry awareness — pure Python."""

from __future__ import annotations

from datetime import datetime

from app.core.types import IngredientData, InventoryEventData, StockItemState


def compute_stock(
    events: list[InventoryEventData],
    ingredients: dict[str, IngredientData],
    now: datetime,
) -> dict[str, StockItemState]:
    """Compute current stock per ingredient as signed sum over append-only events.

    Negative totals are clamped to 0.0 and flagged with `clamped_negative=True`.
    Ingredients in stock that reached >= 70% of `perishable_days` since the last
    PURCHASED event are flagged `near_expiry=True`.
    """
    raw_totals: dict[str, float] = {}
    last_purchased: dict[str, datetime] = {}

    for ev in sorted(events, key=lambda e: e.created_at):
        key = ev.ingredient_key
        raw_totals[key] = raw_totals.get(key, 0.0) + float(ev.qty_base)
        if ev.event_type == "PURCHASED" and ev.qty_base > 0:
            prev = last_purchased.get(key)
            if prev is None or ev.created_at > prev:
                last_purchased[key] = ev.created_at

    result: dict[str, StockItemState] = {}
    all_keys = set(ingredients.keys()) | set(raw_totals.keys())
    for key in sorted(all_keys):
        raw_qty = round(raw_totals.get(key, 0.0), 3)
        clamped_neg = raw_qty < 0.0
        qty_base = max(0.0, raw_qty)
        lp = last_purchased.get(key)

        expiry_ratio: float | None = None
        near_expiry = False
        ing = ingredients.get(key)
        if qty_base > 0.0 and lp is not None and ing is not None and ing.perishable_days > 0:
            elapsed_days = max(0.0, (now - lp).total_seconds() / 86400.0)
            expiry_ratio = round(elapsed_days / ing.perishable_days, 3)
            near_expiry = expiry_ratio >= 0.70

        result[key] = StockItemState(
            ingredient_key=key,
            raw_qty=raw_qty,
            qty_base=qty_base,
            clamped_negative=clamped_neg,
            last_purchased_at=lp,
            expiry_ratio=expiry_ratio,
            near_expiry=near_expiry,
        )

    return result


def compute_adjust_delta(current_stock: float, target_stock: float) -> float:
    """Return signed ADJUST delta needed to bring current_stock to target_stock."""
    return round(max(0.0, target_stock) - max(0.0, current_stock), 3)
