"""add notifications + outreach_messages

Revision ID: 0013_add_notifications_outreach
Revises: 0012_add_clients_shares
Create Date: 2026-07-05 03:00:00.000000

Platform Phase 6 — in-app notifications (SET NULL on candidate) and a logged
outreach history per candidate (CASCADE on candidate). Both tenant-scoped.
"""
from alembic import op
import sqlalchemy as sa


revision = "0013_add_notifications_outreach"
down_revision = "0012_add_clients_shares"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("org_id", sa.String(length=64), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False, server_default="info"),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=True),
        sa.Column("read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_org_id", "notifications", ["org_id"])
    op.create_index("ix_notifications_candidate_id", "notifications", ["candidate_id"])

    op.create_table(
        "outreach_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("org_id", sa.String(length=64), nullable=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="note"),
        sa.Column("subject", sa.String(length=256), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_outreach_messages_candidate_id", "outreach_messages", ["candidate_id"]
    )
    op.create_index("ix_outreach_messages_user_id", "outreach_messages", ["user_id"])
    op.create_index("ix_outreach_messages_org_id", "outreach_messages", ["org_id"])


def downgrade() -> None:
    op.drop_table("outreach_messages")
    op.drop_table("notifications")
