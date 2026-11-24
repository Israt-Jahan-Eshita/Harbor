"""add_clinician_reviews

Revision ID: b4a8f19c2e01
Revises: d1eaa253e60e
Create Date: 2026-11-24 06:18:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b4a8f19c2e01"
down_revision = "d1eaa253e60e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinician_reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("household_id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("review_token", sa.Text(), nullable=False),
        sa.Column("doctor_name", sa.Text(), nullable=False),
        sa.Column("doctor_email", sa.Text(), nullable=True),
        sa.Column("contact_mode", sa.Text(), nullable=False),
        sa.Column("request_note", sa.Text(), nullable=True),
        sa.Column("clinical_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fee_bdt", sa.Integer(), nullable=False),
        sa.Column("payment_status", sa.Text(), nullable=False),
        sa.Column("payment_method", sa.Text(), nullable=True),
        sa.Column("payment_ref", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_status", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("clinician_reg_no", sa.Text(), nullable=True),
        sa.Column("clinician_note", sa.Text(), nullable=True),
        sa.Column("approved_diet_presets", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("apply_presets_on_approve", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "contact_mode IN ('email_invite', 'family_direct')",
            name="ck_clinician_reviews_contact_mode",
        ),
        sa.CheckConstraint("fee_bdt >= 0", name="ck_clinician_reviews_fee_non_negative"),
        sa.CheckConstraint(
            "payment_status IN ('unpaid', 'paid', 'waived')",
            name="ck_clinician_reviews_payment_status",
        ),
        sa.CheckConstraint(
            "payment_method IS NULL OR payment_method IN ('bkash', 'nagad', 'card', 'cash_clinic', 'waived')",
            name="ck_clinician_reviews_payment_method",
        ),
        sa.CheckConstraint(
            "email_status IN ('sent', 'link_ready', 'not_requested', 'failed')",
            name="ck_clinician_reviews_email_status",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'changes_requested')",
            name="ck_clinician_reviews_status",
        ),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_clinician_reviews_household_id"), "clinician_reviews", ["household_id"], unique=False
    )
    op.create_index(
        op.f("ix_clinician_reviews_member_id"), "clinician_reviews", ["member_id"], unique=False
    )
    op.create_index(
        op.f("ix_clinician_reviews_review_token"), "clinician_reviews", ["review_token"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_clinician_reviews_review_token"), table_name="clinician_reviews")
    op.drop_index(op.f("ix_clinician_reviews_member_id"), table_name="clinician_reviews")
    op.drop_index(op.f("ix_clinician_reviews_household_id"), table_name="clinician_reviews")
    op.drop_table("clinician_reviews")

