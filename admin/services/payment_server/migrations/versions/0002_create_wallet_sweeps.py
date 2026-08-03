"""create wallet sweep audit table

Revision ID: payment_0002
Revises: payment_0001
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "payment_0002"
down_revision: Union[str, Sequence[str], None] = "payment_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_wallet_sweeps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("payment_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "wallet_id",
            sa.Integer(),
            sa.ForeignKey("payment_wallets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("source_address", sa.String(128), nullable=False),
        sa.Column("destination_address", sa.String(128), nullable=False),
        sa.Column("requested_amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("transferred_amount", sa.Numeric(24, 8), nullable=True),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("network", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("transaction_hash", sa.String(128), nullable=True),
        sa.Column("chain_balance_before", sa.Numeric(24, 8), nullable=True),
        sa.Column("chain_balance_after", sa.Numeric(24, 8), nullable=True),
        sa.Column("network_fee", sa.Numeric(24, 8), nullable=True),
        sa.Column("requested_by", sa.Text(), server_default="admin", nullable=False),
        sa.Column("error_message", sa.Text(), server_default="", nullable=False),
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
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_payment_wallet_sweeps_user_id",
        "payment_wallet_sweeps",
        ["user_id"],
    )
    op.create_index(
        "ix_payment_wallet_sweeps_wallet_id",
        "payment_wallet_sweeps",
        ["wallet_id"],
    )
    op.create_index(
        "ix_payment_wallet_sweeps_idempotency_key",
        "payment_wallet_sweeps",
        ["idempotency_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_wallet_sweeps_idempotency_key",
        table_name="payment_wallet_sweeps",
    )
    op.drop_index(
        "ix_payment_wallet_sweeps_wallet_id",
        table_name="payment_wallet_sweeps",
    )
    op.drop_index(
        "ix_payment_wallet_sweeps_user_id",
        table_name="payment_wallet_sweeps",
    )
    op.drop_table("payment_wallet_sweeps")
