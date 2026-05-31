"""add user_id columns to scans and assessments

Revision ID: 0002_add_user_id
Revises: 0001_initial
Create Date: 2026-05-31 00:00:01.000000

Phase 4: each row optionally carries the Clerk user_id (sub claim) of the
authenticated caller who created it. Nullable so Phase-3 rows survive
unchanged. Indexed because every per-user list / fetch query filters on it.
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_add_user_id"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scans", sa.Column("user_id", sa.String(length=64), nullable=True))
    op.create_index("ix_scans_user_id", "scans", ["user_id"])

    op.add_column("assessments", sa.Column("user_id", sa.String(length=64), nullable=True))
    op.create_index("ix_assessments_user_id", "assessments", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_assessments_user_id", table_name="assessments")
    op.drop_column("assessments", "user_id")

    op.drop_index("ix_scans_user_id", table_name="scans")
    op.drop_column("scans", "user_id")
