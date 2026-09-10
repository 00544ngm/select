"""Persist models discovered during provider connection tests.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_configurations",
        sa.Column(
            "supported_models",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    with op.batch_alter_table("provider_configurations") as batch_op:
        batch_op.alter_column("supported_models", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("provider_configurations") as batch_op:
        batch_op.drop_column("supported_models")
