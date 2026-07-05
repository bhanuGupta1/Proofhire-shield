"""add outcomes

Revision ID: 0015_add_outcomes
Revises: 0014_add_audit_log
Create Date: 2026-07-05 05:00:00.000000

Platform Phase 9 — placement-funnel event log per candidate+job (interviewed,
offered, hired, rejected, withdrawn, placed). Conversion metrics and client ROI
reports are derived from this. Both FKs CASCADE.
"""
from alembic import op
import sqlalchemy as sa


revision = "0015_add_outcomes"
down_revision = "0014_add_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outcomes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("org_id", sa.String(length=64), nullable=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_outcomes_candidate_id", "outcomes", ["candidate_id"])
    op.create_index("ix_outcomes_job_id", "outcomes", ["job_id"])
    op.create_index("ix_outcomes_user_id", "outcomes", ["user_id"])
    op.create_index("ix_outcomes_org_id", "outcomes", ["org_id"])


def downgrade() -> None:
    op.drop_table("outcomes")
