"""Plain data models for the pure-Python core engine (no ORM/network coupling)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

LevelType = Literal["low", "medium", "high"]
SafetyStatus = Literal["SAFE_DIRECT", "SAFE_WITH_SPLIT", "BLOCKED", "UNVERIFIED"]
HouseholdDishStatus = Literal["SAFE_DIRECT", "SAFE_WITH_SPLIT", "EXCLUDED"]


class IngredientData(BaseModel):
    key: str
    name_en: str
    name_bn: str
    category: str = "other"
    allergen_tags: list[str] = Field(default_factory=list)
    potassium_level: str | None = None
    purine_level: str | None = None
    sodium_level: str | None = None
    gi_level: str | None = None
    tags: list[str] = Field(default_factory=list)
    season_months: list[int] = Field(default_factory=list)
    perishable_days: int = 7
    base_unit: str = "g"
    ref_price_bdt: float | None = None
    ref_price_per: float = 1000.0


class RecipeIngredientData(BaseModel):
    ingredient_key: str
    qty: float
    unit: str


class RecipeData(BaseModel):
    id: str
    key: str
    name_bn: str
    name_en: str = ""
    servings_base: int = 4
    ingredients: list[RecipeIngredientData] = Field(default_factory=list)
    steps_bn: list[str] = Field(default_factory=list)
    split_step_bn: str | None = None
    split_removes: list[str] = Field(default_factory=list)
    taste_score: float = 0.75
    category: str = "mixed"
    est_cost_bdt: float | None = None


class MedicineData(BaseModel):
    id: str = ""
    name_as_written: str
    generic_name: str | None = None
    drug_class: str | None = None
    timing: str = "any"
    meal_slots: list[str] = Field(default_factory=list)
    verified_by_caregiver: bool = False
    active: bool = True


class MemberData(BaseModel):
    id: str
    name: str
    role: str = "other"
    age_group: str = "adult"
    conditions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    diet_presets: list[str] = Field(default_factory=list)
    medicines: list[MedicineData] = Field(default_factory=list)
    is_guest: bool = False
    excluded_ingredient_keys: list[str] = Field(default_factory=list)


class DrugFoodRuleData(BaseModel):
    rule_id: str
    drug_class: str
    ingredient_attr: str
    attr_value: str
    severity: str = "block"
    message_bn: str = ""
    message_en: str = ""
    source_note: str = ""


class DietPresetData(BaseModel):
    preset: str
    attr: str
    max_level: LevelType
    split_allowed: bool = False


class RuleContext(BaseModel):
    ingredients: dict[str, IngredientData] = Field(default_factory=dict)
    drug_food_rules: list[DrugFoodRuleData] = Field(default_factory=list)
    diet_presets: list[DietPresetData] = Field(default_factory=list)
    known_drug_classes: set[str] = Field(
        default_factory=lambda: {
            "ace_inhibitor",
            "arb",
            "k_sparing_diuretic",
            "statin_cyp3a4",
            "none_modelled",
        }
    )


class IngredientVerdict(BaseModel):
    ingredient_key: str
    status: SafetyStatus = "SAFE_DIRECT"
    reasons: list[str] = Field(default_factory=list)
    split_removable: bool = False


class MemberSafetyResult(BaseModel):
    member_id: str
    member_name: str
    recipe_id: str
    recipe_key: str
    status: SafetyStatus
    reasons: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    split_step_bn: str | None = None
    split_ingredients: list[str] = Field(default_factory=list)
    ingredient_verdicts: dict[str, IngredientVerdict] = Field(default_factory=dict)


class MemberIngredientPosition(BaseModel):
    member_id: str
    member_name: str
    status: SafetyStatus
    reasons: list[str] = Field(default_factory=list)


class IngredientConflict(BaseModel):
    ingredient_key: str
    ingredient_name_bn: str
    ingredient_name_en: str
    conflict_type: Literal[
        "UNVERIFIED_FAIL_CLOSED",
        "SEVERITY_ESCALATION",
        "MULTI_RULE_COLLISION",
        "CONVERGENT_SPLIT",
        "INCOMPATIBLE_SPLIT_BLOCKED",
    ]
    resolution: Literal[
        "UNVERIFIED_FAIL_CLOSED",
        "BLOCKED_MOST_RESTRICTIVE_WINS",
        "SAFE_WITH_SINGLE_SPLIT",
        "EXCLUDED_INCOMPATIBLE_SPLIT",
    ]
    winning_status: SafetyStatus
    winning_reasons: list[str] = Field(default_factory=list)
    positions: list[MemberIngredientPosition] = Field(default_factory=list)
    explanation_bn: str
    explanation_en: str
    safe_substitutes: list[dict[str, Any]] = Field(default_factory=list)


class ConflictResolutionSummary(BaseModel):
    total_recipes_checked: int
    safe_direct_count: int
    safe_with_split_count: int
    excluded_count: int
    conflicted_ingredients: list[IngredientConflict] = Field(default_factory=list)
    zero_safe_deadlock: bool = False
    deadlock_recovery_bn: str | None = None
    deadlock_recovery_en: str | None = None


class GuestEventData(BaseModel):
    guest_count: int = 0
    restrictions: list[str] = Field(default_factory=list)


class HouseholdCandidate(BaseModel):
    recipe: RecipeData
    status: Literal["SAFE_DIRECT", "SAFE_WITH_SPLIT"]
    split_for: list[str] = Field(default_factory=list)
    split_step_bn: str | None = None
    split_removes: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    member_results: list[MemberSafetyResult] = Field(default_factory=list)
    ingredient_conflicts: list[IngredientConflict] = Field(default_factory=list)


class HouseholdExcluded(BaseModel):
    recipe: RecipeData
    status: Literal["EXCLUDED"] = "EXCLUDED"
    reasons: list[str] = Field(default_factory=list)
    member_results: list[MemberSafetyResult] = Field(default_factory=list)
    ingredient_conflicts: list[IngredientConflict] = Field(default_factory=list)


class SharedPotResult(BaseModel):
    for_date: date
    meal: str
    people_count: int
    present_member_names: list[str] = Field(default_factory=list)
    guest_count: int = 0
    candidates: list[HouseholdCandidate] = Field(default_factory=list)
    excluded: list[HouseholdExcluded] = Field(default_factory=list)
    conflict_summary: ConflictResolutionSummary | None = None


class InventoryEventData(BaseModel):
    event_type: Literal["PURCHASED", "COOKED", "SPOILED", "RESERVED", "ADJUST"]
    ingredient_key: str
    qty_base: float
    created_at: datetime


class StockItemState(BaseModel):
    ingredient_key: str
    raw_qty: float
    qty_base: float
    clamped_negative: bool = False
    last_purchased_at: datetime | None = None
    expiry_ratio: float | None = None
    near_expiry: bool = False


class NormalizedQty(BaseModel):
    phrase: str
    qty_base: float | None = None
    unit_base: str | None = None
    confidence: float = 0.0
    is_relative_target: bool = False
    target_ratio: float | None = None
    needs_review: bool = False
    note: str = ""


class PriceEstimate(BaseModel):
    ingredient_key: str
    price_bdt: float | None = None
    per_qty: float = 1000.0
    unit: str = "g"
    source: str = "missing"
    as_of: datetime | None = None
    is_estimated: bool = True
    label_bn: str = "আনুমানিক"
    missing_price: bool = False
    cross_check_note: str | None = None
    cross_check_skipped: bool = False


class ScoredDish(BaseModel):
    recipe: RecipeData
    status: Literal["SAFE_DIRECT", "SAFE_WITH_SPLIT"]
    split_for: list[str] = Field(default_factory=list)
    split_step_bn: str | None = None
    reasons: list[str] = Field(default_factory=list)
    score: float
    components: dict[str, float] = Field(default_factory=dict)
    missing_ingredients: list[dict[str, Any]] = Field(default_factory=list)
    shortfall_cost_bdt: float = 0.0


class DoseRecord(BaseModel):
    id: str
    medicine_id: str
    member_id: str
    member_name: str = ""
    due_at: datetime
    window_end: datetime
    status: Literal["pending", "taken", "taken_late", "missed", "escalated"] = "pending"
    confirmed_at: datetime | None = None
