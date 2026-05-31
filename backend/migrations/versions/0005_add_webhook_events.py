"""add webhook_events table

Revision ID: 0005_add_webhook_events
Revises: 0004_add_subscriptions
Create Date: 2026-06-01 00:00:00.000000

Phase 7.5 (billing webhook): idempotency ledger of processed Stripe event ids.
event_id (the Stripe `evt_...`) is the PK so a re-delivered event is a no-op.
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_add_webhook_events"
down_revision = "0004_add_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    op.drop_table("webhook_events")
