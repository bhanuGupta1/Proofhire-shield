"""add monthly_usage atomic counter

Revision ID: 0007_add_monthly_usage
Revises: 0006_add_last_event_at
Create Date: 2026-06-03 00:00:00.000000

Phase 8.1 — atomic free-tier quota counter that closes the Codex P7 round-2
MED race in the existing COUNT(*)-based gate. Composite PK on
(user_id, period) lets the DB serialise concurrent reservations so the
INSERT/UPDATE-WHERE-count<limit pattern can replace check-then-write.

No backfill: callers carrying Scan rows from before this migration get a
one-time fresh bucket on their next /scan-cv. That's a generous deploy-day
gift, not a recurring exploit.
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_add_monthly_usage"
down_revision = "0006_add_last_event_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_usage",
        sa.Column("user_id", sa.String(length=64), primary_key=True),
        sa.Column("period", sa.String(length=7), primary_key=True),
        sa.Column(
            "count", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    op.drop_table("monthly_usage")
