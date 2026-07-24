"""create accounts table

Revision ID: 0001
Revises:
Create Date: 2026-07-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("api_id", sa.Integer(), nullable=False),
        sa.Column("api_hash", sa.Text(), nullable=False),
        sa.Column("device_model", sa.Text(), nullable=False),
        sa.Column("system_version", sa.Text(), nullable=False),
        sa.Column("app_version", sa.Text(), nullable=False),
        sa.Column("session_dir", sa.Text(), nullable=False),
        sa.Column("proxy_host", sa.Text(), nullable=True),
        sa.Column("proxy_port", sa.Integer(), nullable=True),
        sa.Column("proxy_username", sa.Text(), nullable=True),
        sa.Column("proxy_password", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("is_premium", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("restriction_expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("username", sa.Text(), nullable=False, server_default=""),
        sa.Column("first_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_accounts_phone", "accounts", ["phone"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_accounts_phone", table_name="accounts")
    op.drop_table("accounts")
