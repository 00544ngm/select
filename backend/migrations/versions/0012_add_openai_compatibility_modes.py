"""Persist verified OpenAI-compatible request modes.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("provider_model_validations") as batch_op:
        batch_op.add_column(sa.Column("transport_mode", sa.String(24), nullable=True))
        batch_op.add_column(
            sa.Column("structured_output_mode", sa.String(24), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("provider_model_validations") as batch_op:
        batch_op.drop_column("structured_output_mode")
        batch_op.drop_column("transport_mode")
