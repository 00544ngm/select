"""Add auditable model attempts for analysis jobs.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_model_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("api_protocol", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "ordinal"),
    )
    op.create_index(
        "ix_job_model_attempts_job_ordinal",
        "job_model_attempts",
        ["job_id", "ordinal"],
    )
    op.create_index(
        "ix_job_model_attempts_job_status",
        "job_model_attempts",
        ["job_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_job_model_attempts_job_status", table_name="job_model_attempts")
    op.drop_index("ix_job_model_attempts_job_ordinal", table_name="job_model_attempts")
    op.drop_table("job_model_attempts")
