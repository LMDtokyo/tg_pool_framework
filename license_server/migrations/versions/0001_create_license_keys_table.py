"""create license_keys table

Revision ID: 0001
Revises:
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "license_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("key_last4", sa.Text(), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("hwid_hash", sa.Text(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("key_hash", name="uq_license_keys_key_hash"),
    )
    op.create_index("ix_license_keys_key_hash", "license_keys", ["key_hash"], unique=False)
    op.create_index("ix_license_keys_hwid_hash", "license_keys", ["hwid_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_license_keys_hwid_hash", table_name="license_keys")
    op.drop_index("ix_license_keys_key_hash", table_name="license_keys")
    op.drop_table("license_keys")
