"""add candidates + jobs tables

Revision ID: 0010_add_candidates_jobs
Revises: 0009_add_assessments_used
Create Date: 2026-07-05 00:00:00.000000

Platform Phase 1 — the ATS backbone. `candidates` persists a scanned (or
manually entered) person as a durable pipeline record; `candidates.scan_id`
references the originating scan with ON DELETE SET NULL so the candidate
survives deletion of its origin scan. `jobs` holds the roles being filled.
Both tables are tenant-scoped (user_id / org_id) exactly like scans.
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_add_candidates_jobs"
down_revision = "0009_add_assessments_used"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("org_id", sa.String(length=64), nullable=True),
        sa.Column("scan_id", sa.Uuid(), nullable=True),
        sa.Column("full_name", sa.String(length=256), nullable=False),
        sa.Column("email", sa.String(length=256), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("headline", sa.String(length=256), nullable=True),
        sa.Column("location", sa.String(length=128), nullable=True),
        sa.Column(
            "source", sa.String(length=32), nullable=False, server_default="scan"
        ),
        sa.Column(
            "status", sa.String(length=24), nullable=False, server_default="new"
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
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
        sa.ForeignKeyConstraint(
            ["scan_id"], ["scans.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_candidates_user_id", "candidates", ["user_id"])
    op.create_index("ix_candidates_org_id", "candidates", ["org_id"])
    op.create_index("ix_candidates_scan_id", "candidates", ["scan_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("org_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("client_name", sa.String(length=256), nullable=True),
        sa.Column("location", sa.String(length=128), nullable=True),
        sa.Column("employment_type", sa.String(length=32), nullable=True),
        sa.Column("seniority", sa.String(length=32), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "required_skills",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "status", sa.String(length=24), nullable=False, server_default="open"
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
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])
    op.create_index("ix_jobs_org_id", "jobs", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_org_id", table_name="jobs")
    op.drop_index("ix_jobs_user_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_candidates_scan_id", table_name="candidates")
    op.drop_index("ix_candidates_org_id", table_name="candidates")
    op.drop_index("ix_candidates_user_id", table_name="candidates")
    op.drop_table("candidates")
