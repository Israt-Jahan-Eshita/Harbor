"""SQLAlchemy 2 ORM models for Harbor PostgreSQL schema."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Household(Base):
    __tablename__ = "households"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    access_code: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    caregiver_pin_hash: Mapped[str] = mapped_column(Text, nullable=False)
    consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    meal_times: Mapped[dict[str, str]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {"breakfast": "08:00", "lunch": "13:30", "dinner": "21:00"},
    )
    monthly_budget_bdt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    members: Mapped[list[Member]] = relationship(back_populates="household", cascade="all, delete-orphan")


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (
        CheckConstraint(
            "role IN ('caregiver', 'patient', 'child', 'elder', 'other')",
            name="ck_members_role",
        ),
        CheckConstraint(
            "age_group IN ('child_under_1', 'child_under_5', 'child', 'adult', 'elder')",
            name="ck_members_age_group",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="other")
    age_group: Mapped[str] = mapped_column(Text, nullable=False, default="adult")
    conditions: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    allergies: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    diet_presets: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    patient_token: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    notify_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    household: Mapped[Household] = relationship(back_populates="members")
    medicines: Mapped[list[Medicine]] = relationship(back_populates="member", cascade="all, delete-orphan")
    prescriptions: Mapped[list[Prescription]] = relationship(back_populates="member", cascade="all, delete-orphan")
    clinician_reviews: Mapped[list[ClinicianReview]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )


class Prescription(Base):
    """Stores only extracted JSON drafts/confirmations; images are NEVER persisted."""

    __tablename__ = "prescriptions"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'confirmed')", name="ck_prescriptions_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_extraction: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    member: Mapped[Member] = relationship(back_populates="prescriptions")


class Medicine(Base):
    __tablename__ = "medicines"
    __table_args__ = (
        CheckConstraint(
            "timing IN ('before_food', 'after_food', 'with_food', 'any', 'unknown')",
            name="ck_medicines_timing",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prescription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prescriptions.id", ondelete="SET NULL"), nullable=True
    )
    name_as_written: Mapped[str] = mapped_column(Text, nullable=False)
    generic_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    drug_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    timing: Mapped[str] = mapped_column(Text, nullable=False, default="any")
    meal_slots: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    verified_by_caregiver: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    member: Mapped[Member] = relationship(back_populates="medicines")
    doses: Mapped[list[DoseSchedule]] = relationship(back_populates="medicine", cascade="all, delete-orphan")


class DrugClassMap(Base):
    __tablename__ = "drug_class_map"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    drug_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    drug_class: Mapped[str] = mapped_column(Text, nullable=False)


class Ingredient(Base):
    __tablename__ = "ingredients"
    __table_args__ = (
        CheckConstraint("base_unit IN ('g', 'ml', 'piece')", name="ck_ingredients_base_unit"),
        CheckConstraint(
            "potassium_level IS NULL OR potassium_level IN ('low', 'medium', 'high')",
            name="ck_ingredients_potassium",
        ),
        CheckConstraint(
            "purine_level IS NULL OR purine_level IN ('low', 'medium', 'high')",
            name="ck_ingredients_purine",
        ),
        CheckConstraint(
            "sodium_level IS NULL OR sodium_level IN ('low', 'medium', 'high')",
            name="ck_ingredients_sodium",
        ),
        CheckConstraint(
            "gi_level IS NULL OR gi_level IN ('low', 'medium', 'high')",
            name="ck_ingredients_gi",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    name_bn: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    allergen_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    potassium_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    purine_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    sodium_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    gi_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    season_months: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False, default=list)
    perishable_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    base_unit: Mapped[str] = mapped_column(Text, nullable=False, default="g")
    ref_price_bdt: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    ref_price_per: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("1000"))

    aliases: Mapped[list[IngredientAlias]] = relationship(back_populates="ingredient", cascade="all, delete-orphan")


class IngredientAlias(Base):
    __tablename__ = "ingredient_aliases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alias: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False, index=True
    )

    ingredient: Mapped[Ingredient] = relationship(back_populates="aliases")


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    name_bn: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    servings_base: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    ingredients: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    steps_bn: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    split_step_bn: Mapped[str | None] = mapped_column(Text, nullable=True)
    split_removes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    taste_score: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("0.75"))
    category: Mapped[str] = mapped_column(Text, nullable=False, default="mixed")
    est_cost_bdt: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)


class DrugFoodRule(Base):
    __tablename__ = "drug_food_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    drug_class: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    ingredient_attr: Mapped[str] = mapped_column(Text, nullable=False)
    attr_value: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="block")
    message_bn: Mapped[str] = mapped_column(Text, nullable=False)
    message_en: Mapped[str] = mapped_column(Text, nullable=False)
    source_note: Mapped[str] = mapped_column(Text, nullable=False, default="")


class DietPreset(Base):
    __tablename__ = "diet_presets"
    __table_args__ = (
        UniqueConstraint("preset", "attr", name="uq_diet_presets_preset_attr"),
        CheckConstraint("max_level IN ('low', 'medium', 'high')", name="ck_diet_presets_max_level"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    preset: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    attr: Mapped[str] = mapped_column(Text, nullable=False)
    max_level: Mapped[str] = mapped_column(Text, nullable=False)
    split_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class InventoryEvent(Base):
    __tablename__ = "inventory_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('PURCHASED', 'COOKED', 'SPOILED', 'RESERVED', 'ADJUST')",
            name="ck_inventory_events_type",
        ),
        CheckConstraint(
            "source IN ('voice', 'text', 'ui', 'system')",
            name="ck_inventory_events_source",
        ),
        Index("ix_inventory_events_hh_ing_created", "household_id", "ingredient_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False
    )
    qty_base: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="ui")
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class HouseholdEvent(Base):
    __tablename__ = "household_events"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('GUESTS', 'GUESTS_CANCELLED', 'MEMBER_AWAY', 'OTHER')",
            name="ck_household_events_kind",
        ),
        Index("ix_household_events_hh_date", "household_id", "for_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    for_date: Mapped[date] = mapped_column(Date, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class PriceObservation(Base):
    __tablename__ = "price_observations"
    __table_args__ = (
        CheckConstraint(
            "source IN ('user_purchase', 'reference_table', 'agripricebd')",
            name="ck_price_observations_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=True, index=True
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price_bdt: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    per_qty: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class MenuSuggestion(Base):
    __tablename__ = "menu_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    for_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    meal: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    used_template: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class BazarList(Base):
    __tablename__ = "bazar_lists"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'confirmed')", name="ck_bazar_lists_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    month: Mapped[str] = mapped_column(Text, nullable=False)
    budget_bdt: Mapped[int] = mapped_column(Integer, nullable=False)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    est_total_bdt: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class DoseSchedule(Base):
    __tablename__ = "dose_schedule"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'taken', 'taken_late', 'missed', 'escalated')",
            name="ck_dose_schedule_status",
        ),
        Index("ix_dose_schedule_due_status", "due_at", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    medicine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medicines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    medicine: Mapped[Medicine] = relationship(back_populates="doses")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    input_summary: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=True
    )
    endpoint: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ClinicianReview(Base):
    """Care-plan escalation, fee payment tracking, and clinician approval records."""

    __tablename__ = "clinician_reviews"
    __table_args__ = (
        CheckConstraint(
            "contact_mode IN ('email_invite', 'family_direct')",
            name="ck_clinician_reviews_contact_mode",
        ),
        CheckConstraint("fee_bdt >= 0", name="ck_clinician_reviews_fee_non_negative"),
        CheckConstraint(
            "payment_status IN ('unpaid', 'paid', 'waived')",
            name="ck_clinician_reviews_payment_status",
        ),
        CheckConstraint(
            "payment_method IS NULL OR payment_method IN ('bkash', 'nagad', 'card', 'cash_clinic', 'waived')",
            name="ck_clinician_reviews_payment_method",
        ),
        CheckConstraint(
            "email_status IN ('sent', 'link_ready', 'not_requested', 'failed')",
            name="ck_clinician_reviews_email_status",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'changes_requested')",
            name="ck_clinician_reviews_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_token: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    doctor_name: Mapped[str] = mapped_column(Text, nullable=False)
    doctor_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_mode: Mapped[str] = mapped_column(Text, nullable=False, default="email_invite")
    request_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    clinical_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    fee_bdt: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    payment_status: Mapped[str] = mapped_column(Text, nullable=False, default="unpaid")
    payment_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_status: Mapped[str] = mapped_column(Text, nullable=False, default="link_ready")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    clinician_reg_no: Mapped[str | None] = mapped_column(Text, nullable=True)
    clinician_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_diet_presets: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    apply_presets_on_approve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    member: Mapped[Member] = relationship(back_populates="clinician_reviews")
