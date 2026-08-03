"""add Telegram username to payment users

Revision ID: payment_0003
Revises: payment_0002
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "payment_0003"
down_revision: Union[str, Sequence[str], None] = "payment_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payment_users",
        sa.Column("telegram_username", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_payment_users_telegram_username",
        "payment_users",
        ["telegram_username"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_users_telegram_username", table_name="payment_users"
    )
    op.drop_column("payment_users", "telegram_username")
