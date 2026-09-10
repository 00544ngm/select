"""Add the persistent desktop job queue.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "local_queue_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("function", sa.String(length=64), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("claimed_by", sa.String(length=120), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_local_queue_items_status_created",
        "local_queue_items",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_local_queue_items_status_created",
        table_name="local_queue_items",
    )
    op.drop_table("local_queue_items")
