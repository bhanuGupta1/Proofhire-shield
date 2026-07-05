"""add clients + client_shares

Revision ID: 0012_add_clients_shares
Revises: 0011_add_pipeline_shortlists
Create Date: 2026-07-05 02:00:00.000000

Platform Phase 5 — client CRM records and unguessable public share links to a
job's shortlist. client_shares.token is unique; the share cascades with its job.
"""
from alembic import op
import sqlalchemy as sa


revision = "0012_add_clients_shares"
down_revision = "0011_add_pipeline_shortlists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("org_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("contact_name", sa.String(length=256), nullable=True),
        sa.Column("contact_email", sa.String(length=256), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
    op.create_index("ix_clients_user_id", "clients", ["user_id"])
    op.create_index("ix_clients_org_id", "clients", ["org_id"])

    op.create_table(
        "client_shares",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("org_id", sa.String(length=64), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token", name="uq_client_share_token"),
    )
    op.create_index("ix_client_shares_token", "client_shares", ["token"])
    op.create_index("ix_client_shares_job_id", "client_shares", ["job_id"])
    op.create_index("ix_client_shares_user_id", "client_shares", ["user_id"])
    op.create_index("ix_client_shares_org_id", "client_shares", ["org_id"])


def downgrade() -> None:
    op.drop_table("client_shares")
    op.drop_table("clients")
