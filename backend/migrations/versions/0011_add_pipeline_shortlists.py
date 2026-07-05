"""add pipeline_stages, placements, shortlist_entries

Revision ID: 0011_add_pipeline_shortlists
Revises: 0010_add_candidates_jobs
Create Date: 2026-07-05 01:00:00.000000

Platform Phase 2 — the hiring funnel. pipeline_stages are a job's ordered
columns; placements put a candidate at a stage in a job (unique per
job+candidate); shortlist_entries star a candidate for a job. All tenant-scoped
and cascade-tied to their job/candidate.
"""
from alembic import op
import sqlalchemy as sa


revision = "0011_add_pipeline_shortlists"
down_revision = "0010_add_candidates_jobs"
branch_labels = None
depends_on = None


def _tenant_cols():
    return (
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("org_id", sa.String(length=64), nullable=True),
    )


def upgrade() -> None:
    op.create_table(
        "pipeline_stages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *_tenant_cols(),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_pipeline_stages_job_id", "pipeline_stages", ["job_id"])
    op.create_index("ix_pipeline_stages_user_id", "pipeline_stages", ["user_id"])
    op.create_index("ix_pipeline_stages_org_id", "pipeline_stages", ["org_id"])

    op.create_table(
        "placements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *_tenant_cols(),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("stage_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["stage_id"], ["pipeline_stages.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "job_id", "candidate_id", name="uq_placement_job_candidate"
        ),
    )
    op.create_index("ix_placements_job_id", "placements", ["job_id"])
    op.create_index("ix_placements_candidate_id", "placements", ["candidate_id"])
    op.create_index("ix_placements_stage_id", "placements", ["stage_id"])
    op.create_index("ix_placements_user_id", "placements", ["user_id"])
    op.create_index("ix_placements_org_id", "placements", ["org_id"])

    op.create_table(
        "shortlist_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *_tenant_cols(),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "job_id", "candidate_id", name="uq_shortlist_job_candidate"
        ),
    )
    op.create_index("ix_shortlist_entries_job_id", "shortlist_entries", ["job_id"])
    op.create_index(
        "ix_shortlist_entries_candidate_id", "shortlist_entries", ["candidate_id"]
    )
    op.create_index("ix_shortlist_entries_user_id", "shortlist_entries", ["user_id"])
    op.create_index("ix_shortlist_entries_org_id", "shortlist_entries", ["org_id"])


def downgrade() -> None:
    op.drop_table("shortlist_entries")
    op.drop_table("placements")
    op.drop_table("pipeline_stages")
