"""add last_event_at to subscriptions

Revision ID: 0006_add_last_event_at
Revises: 0005_add_webhook_events
Create Date: 2026-06-01 00:00:00.000000

Phase 7.7 hardening (Codex P7 MED #1): track the `created` timestamp of the
last Stripe event applied to each subscription row so out-of-order webhook
delivery can be rejected. Nullable so pre-migration rows survive untouched.
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_add_last_event_at"
down_revision = "0005_add_webhook_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "last_event_at")
