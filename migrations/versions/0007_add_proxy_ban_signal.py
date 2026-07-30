"""add ban signal tracking to proxies

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "proxies",
        sa.Column("ban_signal_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "proxies",
        sa.Column("last_ban_signal_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("proxies", "last_ban_signal_at")
    op.drop_column("proxies", "ban_signal_count")
