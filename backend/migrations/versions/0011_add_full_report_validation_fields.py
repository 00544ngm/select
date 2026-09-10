"""Store representative full-report validation metadata.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("provider_model_validations") as batch_op:
        batch_op.add_column(
            sa.Column("validation_kind", sa.String(16), nullable=False, server_default="probe")
        )
        batch_op.add_column(sa.Column("schema_version", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("quality_status", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("duration_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("provider_model_validations") as batch_op:
        batch_op.drop_column("duration_ms")
        batch_op.drop_column("quality_status")
        batch_op.drop_column("schema_version")
        batch_op.drop_column("validation_kind")
