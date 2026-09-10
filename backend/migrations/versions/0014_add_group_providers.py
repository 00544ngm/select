"""Add per-ApiGroup provider slots (group = its own multi-provider API set).

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json() -> sa.JSON:
    from sqlalchemy.dialects.postgresql import JSONB

    return sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "api_group_providers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("api_group_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("api_protocol", sa.String(length=20), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("default_model", sa.String(length=120), nullable=False),
        sa.Column("supported_models", _json(), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("api_key_last4", sa.String(length=4), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_test_status", sa.String(length=16), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_message", sa.String(length=255), nullable=True),
        sa.Column("validation_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["api_group_id"],
            ["api_groups.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_group_id", "slug"),
    )
    op.create_index(
        "ix_api_group_providers_group",
        "api_group_providers",
        ["api_group_id"],
        unique=False,
    )
    op.create_table(
        "api_group_provider_model_validations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("api_group_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("provider_slug", sa.String(length=32), nullable=False),
        sa.Column("api_protocol", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("message", sa.String(length=255), nullable=False),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_selected", sa.Boolean(), nullable=False),
        sa.Column("connection_revision", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("last_auto_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validation_kind", sa.String(length=16), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=True),
        sa.Column("quality_status", sa.String(length=32), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("transport_mode", sa.String(length=24), nullable=True),
        sa.Column("structured_output_mode", sa.String(length=24), nullable=True),
        sa.ForeignKeyConstraint(
            ["api_group_id"],
            ["api_groups.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["api_group_providers.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "api_protocol", "model"),
    )
    op.create_index(
        "ix_api_group_provider_models_provider_status",
        "api_group_provider_model_validations",
        ["provider_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_api_group_provider_models_provider_status",
        table_name="api_group_provider_model_validations",
    )
    op.drop_table("api_group_provider_model_validations")
    op.drop_index(
        "ix_api_group_providers_group",
        table_name="api_group_providers",
    )
    op.drop_table("api_group_providers")
