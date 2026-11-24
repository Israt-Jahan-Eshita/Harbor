"""add_weekly_plans

Revision ID: d4e7a82b1c03
Revises: c9d2e41a7b02
Create Date: 2026-11-24 09:50:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4e7a82b1c03"
down_revision = "c9d2e41a7b02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weekly_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "household_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("plan_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("est_shortfall_bdt", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('draft', 'confirmed')", name="ck_weekly_plans_status"),
    )
    op.create_index("ix_weekly_plans_household_id", "weekly_plans", ["household_id"])
    op.create_index("ix_weekly_plans_start_date", "weekly_plans", ["start_date"])
    op.create_index("ix_weekly_plans_hh_start", "weekly_plans", ["household_id", "start_date"])


def downgrade() -> None:
    op.drop_index("ix_weekly_plans_hh_start", table_name="weekly_plans")
    op.drop_index("ix_weekly_plans_start_date", table_name="weekly_plans")
    op.drop_index("ix_weekly_plans_household_id", table_name="weekly_plans")
    op.drop_table("weekly_plans")

