"""add subscriptions table

Revision ID: 0004_add_subscriptions
Revises: 0003_add_org_id
Create Date: 2026-06-01 00:00:00.000000

Phase 7 (monetisation): one row per Clerk user with a Stripe subscription.
user_id is the PK because we are per-user Pro for v1 — at most one sub per user.
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_add_subscriptions"
down_revision = "0003_add_org_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("user_id", sa.String(length=64), primary_key=True),
        sa.Column("stripe_customer_id", sa.String(length=64), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(length=64), nullable=True),
        sa.Column("plan", sa.String(length=16), nullable=False, server_default="pro"),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
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
        "ix_subscriptions_stripe_customer_id",
        "subscriptions",
        ["stripe_customer_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_subscriptions_stripe_customer_id", table_name="subscriptions"
    )
    op.drop_table("subscriptions")
