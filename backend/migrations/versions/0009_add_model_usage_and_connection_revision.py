"""Add model usage history and provider connection revisions.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("provider_configurations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "validation_revision",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
    with op.batch_alter_table("provider_model_validations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "connection_revision",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.add_column(
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "use_count", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column(
                "last_auto_tested_at", sa.DateTime(timezone=True), nullable=True
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("provider_model_validations") as batch_op:
        batch_op.drop_column("last_auto_tested_at")
        batch_op.drop_column("use_count")
        batch_op.drop_column("last_used_at")
        batch_op.drop_column("connection_revision")
    with op.batch_alter_table("provider_configurations") as batch_op:
        batch_op.drop_column("validation_revision")
