"""add geo, 2fa, role, folder, proxy_type to accounts

Revision ID: 0003
Revises: 0001
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("country", sa.Text(), nullable=True))
    op.add_column(
        "accounts",
        sa.Column("has_2fa", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "accounts", sa.Column("role", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "accounts", sa.Column("folder", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "accounts",
        sa.Column("proxy_type", sa.Text(), nullable=False, server_default="socks5"),
    )


def downgrade() -> None:
    op.drop_column("accounts", "proxy_type")
    op.drop_column("accounts", "folder")
    op.drop_column("accounts", "role")
    op.drop_column("accounts", "has_2fa")
    op.drop_column("accounts", "country")
