"""Persist per-model provider verification results.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_model_validations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_slug", sa.String(length=32), nullable=False),
        sa.Column("api_protocol", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("message", sa.String(length=255), nullable=False),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_slug"],
            ["provider_configurations.slug"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_slug", "api_protocol", "model"),
    )
    op.create_index(
        "ix_provider_model_validations_provider_status",
        "provider_model_validations",
        ["provider_slug", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_model_validations_provider_status",
        table_name="provider_model_validations",
    )
    op.drop_table("provider_model_validations")
