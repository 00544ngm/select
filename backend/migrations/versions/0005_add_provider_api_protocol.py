"""Persist the API protocol used by provider configurations.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_configurations",
        sa.Column(
            "api_protocol",
            sa.String(length=20),
            nullable=False,
            server_default="openai",
        ),
    )
    with op.batch_alter_table("provider_configurations") as batch_op:
        batch_op.alter_column("api_protocol", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("provider_configurations") as batch_op:
        batch_op.drop_column("api_protocol")
