"""add org_id columns to scans and assessments

Revision ID: 0003_add_org_id
Revises: 0002_add_user_id
Create Date: 2026-05-31 00:00:02.000000

Phase 5 (Clerk Organizations): each row optionally carries the Clerk org_id
of the active organisation at creation time. Nullable so Phase-3/4 rows survive
unchanged. Indexed because every per-org list / fetch query filters on it.
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_add_org_id"
down_revision = "0002_add_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scans", sa.Column("org_id", sa.String(length=64), nullable=True))
    op.create_index("ix_scans_org_id", "scans", ["org_id"])

    op.add_column("assessments", sa.Column("org_id", sa.String(length=64), nullable=True))
    op.create_index("ix_assessments_org_id", "assessments", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_assessments_org_id", table_name="assessments")
    op.drop_column("assessments", "org_id")

    op.drop_index("ix_scans_org_id", table_name="scans")
    op.drop_column("scans", "org_id")
