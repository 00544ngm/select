"""Track who last verified/selected each provider model.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "provider_model_validations",
    "api_group_provider_model_validations",
)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table, sa.Column("last_acted_by", sa.String(length=64), nullable=True)
        )
        op.add_column(
            table,
            sa.Column("last_acted_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "last_acted_at")
        op.drop_column(table, "last_acted_by")
