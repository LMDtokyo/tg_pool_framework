"""create proxies table

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "proxies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("proxy_type", sa.Text(), server_default="socks5", nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.Text(), server_default="", nullable=False),
        sa.Column("password", sa.Text(), server_default="", nullable=False),
        sa.Column("version", sa.Text(), server_default="ipv4", nullable=False),
        sa.Column("status", sa.Text(), server_default="unknown", nullable=False),
        sa.Column("response_ms", sa.Float(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "proxy_type", "host", "port", "username", name="uq_proxies_endpoint_user"
        ),
    )
    op.create_index("ix_proxies_status", "proxies", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_proxies_status", table_name="proxies")
    op.drop_table("proxies")
