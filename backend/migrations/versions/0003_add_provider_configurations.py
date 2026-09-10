"""Add encrypted provider configurations.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_configurations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("default_model", sa.String(length=120), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("api_key_last4", sa.String(length=4), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_test_status", sa.String(length=16), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_message", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )


def downgrade() -> None:
    op.drop_table("provider_configurations")
