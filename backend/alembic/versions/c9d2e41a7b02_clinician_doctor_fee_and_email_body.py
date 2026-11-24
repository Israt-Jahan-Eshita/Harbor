"""clinician_doctor_fee_and_email_body

Revision ID: c9d2e41a7b02
Revises: b4a8f19c2e01
Create Date: 2026-11-24 06:40:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9d2e41a7b02"
down_revision = "b4a8f19c2e01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_clinician_reviews_payment_status", "clinician_reviews", type_="check")
    op.create_check_constraint(
        "ck_clinician_reviews_payment_status",
        "clinician_reviews",
        "payment_status IN ('awaiting_fee', 'unpaid', 'paid', 'waived')",
    )
    op.add_column("clinician_reviews", sa.Column("fee_note", sa.Text(), nullable=True))
    op.add_column("clinician_reviews", sa.Column("email_body", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("clinician_reviews", "email_body")
    op.drop_column("clinician_reviews", "fee_note")
    op.drop_constraint("ck_clinician_reviews_payment_status", "clinician_reviews", type_="check")
    op.create_check_constraint(
        "ck_clinician_reviews_payment_status",
        "clinician_reviews",
        "payment_status IN ('unpaid', 'paid', 'waived')",
    )

