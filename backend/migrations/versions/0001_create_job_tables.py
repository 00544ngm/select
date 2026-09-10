"""Create durable analysis job tables.

Revision ID: 0001
Revises:
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "request_payload",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()),
                "postgresql",
            ),
            nullable=False,
        ),
        sa.Column(
            "result_payload",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()),
                "postgresql",
            ),
            nullable=True,
        ),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_of_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["retry_of_id"], ["analysis_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analysis_jobs_status_created",
        "analysis_jobs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_analysis_jobs_mode_created",
        "analysis_jobs",
        ["mode", "created_at"],
    )
    op.create_table(
        "product_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_url", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column(
            "scraped_data",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()),
                "postgresql",
            ),
            nullable=False,
        ),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "job_products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("product_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["product_snapshot_id"],
            ["product_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "role", "position"),
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "kind"),
    )


def downgrade() -> None:
    op.drop_table("artifacts")
    op.drop_table("job_products")
    op.drop_table("product_snapshots")
    op.drop_index("ix_analysis_jobs_mode_created", table_name="analysis_jobs")
    op.drop_index("ix_analysis_jobs_status_created", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
