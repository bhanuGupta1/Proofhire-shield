"""add audit_log

Revision ID: 0014_add_audit_log
Revises: 0013_add_notifications_outreach
Create Date: 2026-07-05 04:00:00.000000

Platform Phase 7 — append-only audit trail of consequential actions. entity_id
is a plain string, not a FK, so the log survives deletion of what it references.
"""
from alembic import op
import sqlalchemy as sa


revision = "0014_add_audit_log"
down_revision = "0013_add_notifications_outreach"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("org_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=True),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_org_id", "audit_log", ["org_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
