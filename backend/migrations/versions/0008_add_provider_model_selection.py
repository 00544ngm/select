"""Add persistent provider model selection.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("provider_model_validations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_selected",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("provider_model_validations") as batch_op:
        batch_op.drop_column("is_selected")

