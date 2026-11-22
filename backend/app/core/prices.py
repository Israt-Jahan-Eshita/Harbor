"""Approximate price estimation following SPEC §7.6 priority order — pure Python."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.types import IngredientData, PriceEstimate

AGRI_PRICE_BD_COMMODITIES = {"garlic", "chola_dal", "green_chilli", "shosha", "mishti_kumra"}


def get_price_estimate(
    ingredient: IngredientData,
    user_observations: list[dict[str, Any]] | None = None,
    agripricebd_data: dict[str, dict[str, Any]] | None = None,
) -> PriceEstimate:
    """Return estimated price (`আনুমানিক`) without scraping or inventing prices.

    Priority:
    1. Household's most recent `user_purchase` observation.
    2. `ref_price_bdt` from seed reference table.
    3. Cross-check 5 AgriPriceBD commodities when dataset is actually loaded (>30% diff note).
    """
    if user_observations:
        matching = [
            obs
            for obs in user_observations
            if obs.get("ingredient_key") == ingredient.key
            and obs.get("source") == "user_purchase"
            and obs.get("price_bdt") is not None
        ]
        if matching:
            latest = max(matching, key=lambda o: o.get("observed_at") or datetime.min)
            return PriceEstimate(
                ingredient_key=ingredient.key,
                price_bdt=float(latest["price_bdt"]),
                per_qty=float(latest.get("per_qty") or ingredient.ref_price_per),
                unit=ingredient.base_unit,
                source="user_purchase",
                as_of=latest.get("observed_at"),
                is_estimated=True,
                label_bn="আনুমানিক",
                missing_price=False,
            )

    if ingredient.ref_price_bdt is not None:
        cross_note: str | None = None
        skipped = False
        if ingredient.key in AGRI_PRICE_BD_COMMODITIES:
            if agripricebd_data and ingredient.key in agripricebd_data:
                agri = agripricebd_data[ingredient.key]
                agri_price = float(agri["price_bdt"])
                agri_per = float(agri.get("per_qty") or 1000.0)
                if agri_price > 0 and agri_per > 0 and ingredient.ref_price_per > 0:
                    ref_per_unit = ingredient.ref_price_bdt / ingredient.ref_price_per
                    agri_per_unit = agri_price / agri_per
                    diff_ratio = abs(ref_per_unit - agri_per_unit) / agri_per_unit
                    if diff_ratio > 0.30:
                        cross_note = (
                            f"Reference price differs by {round(diff_ratio * 100, 1)}% "
                            f"from AgriPriceBD ({agri_price} BDT/{agri_per}{ingredient.base_unit})."
                        )
            else:
                skipped = True

        return PriceEstimate(
            ingredient_key=ingredient.key,
            price_bdt=float(ingredient.ref_price_bdt),
            per_qty=float(ingredient.ref_price_per),
            unit=ingredient.base_unit,
            source="reference_table",
            as_of=None,
            is_estimated=True,
            label_bn="আনুমানিক",
            missing_price=False,
            cross_check_note=cross_note,
            cross_check_skipped=skipped,
        )

    return PriceEstimate(
        ingredient_key=ingredient.key,
        price_bdt=None,
        per_qty=float(ingredient.ref_price_per),
        unit=ingredient.base_unit,
        source="missing",
        is_estimated=True,
        label_bn="আনুমানিক",
        missing_price=True,
    )
