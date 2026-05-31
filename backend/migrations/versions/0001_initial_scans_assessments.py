"""create scans and assessments tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filename", sa.String(length=256), nullable=False),
        sa.Column("risk_level", sa.String(length=8), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("prompt_injection_findings", sa.JSON(), nullable=False),
        sa.Column("pii_findings", sa.JSON(), nullable=False),
        sa.Column("ai_text_likelihood", sa.String(length=8), nullable=False),
        sa.Column("ai_text_score", sa.Float(), nullable=False),
        sa.Column("safe_copy_text", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("match_analysis", sa.JSON(), nullable=False),
    )
    op.create_table(
        "assessments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "scan_id",
            sa.Uuid(),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("framework", sa.String(length=64), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("dimensions", sa.JSON(), nullable=False),
        sa.Column("overall_recommendation", sa.Text(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("next_steps", sa.JSON(), nullable=False),
        sa.Column("provider_used", sa.String(length=16), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("assessments")
    op.drop_table("scans")
