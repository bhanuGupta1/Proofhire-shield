"""add assessments_used column to monthly_usage

Revision ID: 0009_add_assessments_used
Revises: 0008_add_org_subscriptions
Create Date: 2026-06-04 00:00:00.000000

Phase 9 — separate Free-tier counter for /assessment runs (limit 5/month),
parallel to the existing scan counter (`count`, limit 10/month). Sharing
the same (user_id, period) row keeps both reservations on a single
lockable row so the same INSERT-then-UPDATE pattern from Phase 8.1 works.

server_default="0" so existing rows back-fill cleanly under Alembic's
batch migration on Postgres + SQLite.
"""
from alembic import op
import sqlalchemy as sa


revision = "0009_add_assessments_used"
down_revision = "0008_add_org_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monthly_usage",
        sa.Column(
            "assessments_used",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("monthly_usage", "assessments_used")
