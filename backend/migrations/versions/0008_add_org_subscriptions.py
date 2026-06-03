"""add org_subscriptions table

Revision ID: 0008_add_org_subscriptions
Revises: 0007_add_monthly_usage
Create Date: 2026-06-03 00:00:01.000000

Phase 8.3 — one row per Clerk organization with an active Stripe sub. Mirrors
the per-user `subscriptions` schema; webhooks (Phase 8.5) route to either
table based on the `metadata.scope` field stamped at Checkout.
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_add_org_subscriptions"
down_revision = "0007_add_monthly_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_subscriptions",
        sa.Column("org_id", sa.String(length=64), primary_key=True),
        sa.Column("stripe_customer_id", sa.String(length=64), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(length=64), nullable=True),
        sa.Column(
            "plan", sa.String(length=16), nullable=False, server_default="pro"
        ),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "current_period_end", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index(
        "ix_org_subscriptions_stripe_customer_id",
        "org_subscriptions",
        ["stripe_customer_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_org_subscriptions_stripe_customer_id",
        table_name="org_subscriptions",
    )
    op.drop_table("org_subscriptions")
