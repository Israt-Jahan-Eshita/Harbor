"""Pydantic v2 request and response schemas for Harbor REST API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.config import get_settings


def dhaka_today() -> date:
    """Return today's calendar date in the household's configured timezone (Asia/Dhaka)."""
    return datetime.now(ZoneInfo(get_settings().tz)).date()


class MealTimesSchema(BaseModel):
    breakfast: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    lunch: str = Field(default="13:30", pattern=r"^\d{2}:\d{2}$")
    dinner: str = Field(default="21:00", pattern=r"^\d{2}:\d{2}$")


class HouseholdCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    pin: str = Field(..., min_length=4, max_length=12)
    consent_given: bool = False
    meal_times: MealTimesSchema = Field(default_factory=MealTimesSchema)
    monthly_budget_bdt: int | None = Field(default=15000, ge=0, le=1000000)


class HouseholdLoginRequest(BaseModel):
    access_code: str = Field(..., min_length=3, max_length=24)
    pin: str = Field(..., min_length=4, max_length=12)


class HouseholdSettingsUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    consent_given: bool | None = None
    meal_times: MealTimesSchema | None = None
    monthly_budget_bdt: int | None = Field(default=None, ge=0, le=1000000)


class HouseholdAuthResponse(BaseModel):
    household_id: str
    name: str
    access_code: str
    token: str
    consent_given: bool
    meal_times: dict[str, str]
    monthly_budget_bdt: int | None


class MemberCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    role: Literal["caregiver", "patient", "child", "elder", "other"] = "other"
    age_group: Literal["child_under_1", "child_under_5", "child", "adult", "elder"] = "adult"
    conditions: list[str] = Field(default_factory=list, max_length=20)
    allergies: list[str] = Field(default_factory=list, max_length=20)
    diet_presets: list[str] = Field(default_factory=list, max_length=10)
    notify_email: str | None = Field(default=None, max_length=200)


class MemberUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Literal["caregiver", "patient", "child", "elder", "other"] | None = None
    age_group: Literal["child_under_1", "child_under_5", "child", "adult", "elder"] | None = None
    conditions: list[str] | None = None
    allergies: list[str] | None = None
    diet_presets: list[str] | None = None
    notify_email: str | None = None


class MedicineCreateRequest(BaseModel):
    name_as_written: str = Field(..., min_length=1, max_length=150)
    generic_name: str | None = Field(default=None, max_length=150)
    drug_class: Literal[
        "ace_inhibitor", "arb", "k_sparing_diuretic", "statin_cyp3a4", "none_modelled"
    ]
    timing: Literal["before_food", "after_food", "with_food", "any", "unknown"] = "after_food"
    meal_slots: list[Literal["breakfast", "lunch", "dinner"]] = Field(
        default_factory=lambda: ["dinner"]
    )
    verified_by_caregiver: bool = True


class MedicineUpdateRequest(BaseModel):
    drug_class: (
        Literal["ace_inhibitor", "arb", "k_sparing_diuretic", "statin_cyp3a4", "none_modelled"]
        | None
    ) = None
    timing: Literal["before_food", "after_food", "with_food", "any", "unknown"] | None = None
    meal_slots: list[Literal["breakfast", "lunch", "dinner"]] | None = None
    verified_by_caregiver: bool | None = None
    active: bool | None = None


class PrescriptionConfirmRow(BaseModel):
    name_as_written: str = Field(..., min_length=1, max_length=150)
    generic_name: str | None = Field(default=None, max_length=150)
    drug_class: Literal[
        "ace_inhibitor", "arb", "k_sparing_diuretic", "statin_cyp3a4", "none_modelled"
    ]
    timing: Literal["before_food", "after_food", "with_food", "any", "unknown"] = "any"
    meal_slots: list[Literal["breakfast", "lunch", "dinner"]] = Field(
        default_factory=lambda: ["dinner"]
    )
    confirmed: bool = True


class PrescriptionConfirmRequest(BaseModel):
    rows: list[PrescriptionConfirmRow] = Field(..., min_length=1, max_length=30)


class EventParseTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class ConfirmedEventItem(BaseModel):
    type: Literal[
        "PURCHASED",
        "COOKED",
        "SPOILED",
        "ADJUST",
        "GUESTS",
        "GUESTS_CANCELLED",
        "MEMBER_AWAY",
    ]
    ingredient_key: str | None = None
    qty_base: float | None = None
    source: Literal["voice", "text", "ui", "system"] = "text"
    raw_text: str | None = None
    guest_count: int | None = Field(default=None, ge=0, le=100)
    for_date: date | None = None
    guest_restrictions: list[str] = Field(default_factory=list)
    member_id: str | None = None


class EventsConfirmRequest(BaseModel):
    confirmation_token: str = Field(..., min_length=1)
    events: list[ConfirmedEventItem] = Field(..., min_length=1, max_length=30)


class StockAdjustRequest(BaseModel):
    ingredient_key: str = Field(..., min_length=1)
    target_qty_base: float = Field(..., ge=0, le=1000000)
    note: str | None = Field(default=None, max_length=200)


class MenuSuggestRequest(BaseModel):
    for_date: date = Field(default_factory=dhaka_today)
    meal: Literal["breakfast", "lunch", "dinner"] = "dinner"
    use_agent: bool = False
    use_llm_explain: bool = False


class MenuReviewRequest(BaseModel):
    for_date: date = Field(default_factory=dhaka_today)
    meal: Literal["breakfast", "lunch", "dinner"] = "dinner"
    guest_count: int = Field(default=0, ge=0, le=50)
    guest_restrictions: list[str] = Field(default_factory=list)
    away_member_ids: list[str] = Field(default_factory=list)
    use_agent: bool = False
    use_llm_explain: bool = False


class MenuCookedRequest(BaseModel):
    recipe_id: str = Field(..., min_length=1)
    servings: int = Field(..., ge=1, le=50)
    for_date: date = Field(default_factory=dhaka_today)
    meal: Literal["breakfast", "lunch", "dinner"] = "dinner"


class BazarBuildRequest(BaseModel):
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    budget_bdt: int = Field(..., ge=100, le=1000000)


class BazarConfirmRequest(BaseModel):
    bazar_list_id: str
    items: list[dict[str, Any]]


class BazarPurchasedItem(BaseModel):
    ingredient_key: str
    qty_base: float = Field(..., gt=0)
    price_bdt: float | None = Field(default=None, ge=0)
    per_qty: float = Field(default=1000.0, gt=0)


class BazarPurchasedRequest(BaseModel):
    bazar_list_id: str | None = None
    items: list[BazarPurchasedItem] = Field(..., min_length=1, max_length=100)


class PushSubscribeRequest(BaseModel):
    member_id: str | None = None
    endpoint: str = Field(..., min_length=1)
    p256dh: str = Field(..., min_length=1)
    auth: str = Field(..., min_length=1)


class EngineCheckRequest(BaseModel):
    member_id: str | None = None
    recipe_key: str = Field(..., min_length=1)
    custom_member: dict[str, Any] | None = None
