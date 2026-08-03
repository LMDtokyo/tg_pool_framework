"""create payment authority schema

Revision ID: payment_0001
Revises:
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "payment_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        )
    ]


def upgrade() -> None:
    op.create_table(
        "payment_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_user_id", sa.String(64), nullable=True),
        sa.Column("display_name", sa.Text(), server_default="", nullable=False),
        sa.Column("disabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("telegram_user_id"),
    )
    op.create_index(
        "ix_payment_users_telegram_user_id",
        "payment_users",
        ["telegram_user_id"],
    )
    op.create_table(
        "payment_api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("payment_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("key_last4", sa.String(4), nullable=False),
        sa.Column("revoked", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index("ix_payment_api_keys_user_id", "payment_api_keys", ["user_id"])
    op.create_index("ix_payment_api_keys_key_hash", "payment_api_keys", ["key_hash"])
    op.create_table(
        "payment_wallets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("payment_users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("network", sa.String(32), nullable=False),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("address", sa.String(128), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("network", "address", name="uq_payment_wallet_address"),
    )
    op.create_table(
        "payment_ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("payment_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("currency", sa.String(16), nullable=False),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("reference_type", sa.String(32), nullable=False),
        sa.Column("reference_id", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "reference_type", "reference_id", name="uq_payment_ledger_reference"
        ),
    )
    op.create_index(
        "ix_payment_ledger_entries_user_id", "payment_ledger_entries", ["user_id"]
    )
    op.create_index(
        "ix_payment_ledger_entries_created_at", "payment_ledger_entries", ["created_at"]
    )
    op.create_table(
        "payment_deposits",
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
        sa.Column("network", sa.String(32), nullable=False),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("transaction_hash", sa.String(128), nullable=False),
        sa.Column("event_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("confirmations", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("credited_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "network",
            "transaction_hash",
            "event_index",
            name="uq_payment_deposit_event",
        ),
    )
    op.create_index("ix_payment_deposits_user_id", "payment_deposits", ["user_id"])
    op.create_table(
        "payment_products",
        sa.Column("provider_product_id", sa.Integer(), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "payment_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("payment_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_order_id", sa.String(255), nullable=False),
        sa.Column("provider_product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("total_amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("currency", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("provider_order_id", sa.String(128), nullable=True),
        sa.Column("provider_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), server_default="", nullable=False),
        *_timestamps(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "external_order_id", name="uq_payment_order_external"
        ),
    )
    op.create_index("ix_payment_orders_user_id", "payment_orders", ["user_id"])
    op.create_table(
        "payment_provider_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("payment_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_order_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), server_default="", nullable=False),
        *_timestamps(),
    )
    op.create_index(
        "ix_payment_provider_orders_order_id", "payment_provider_orders", ["order_id"]
    )
    op.create_table(
        "payment_webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("processed", sa.Boolean(), server_default=sa.false(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index(
        "ix_payment_webhook_events_event_id",
        "payment_webhook_events",
        ["event_id"],
    )


def downgrade() -> None:
    op.drop_table("payment_webhook_events")
    op.drop_table("payment_provider_orders")
    op.drop_table("payment_orders")
    op.drop_table("payment_products")
    op.drop_table("payment_deposits")
    op.drop_table("payment_ledger_entries")
    op.drop_table("payment_wallets")
    op.drop_table("payment_api_keys")
    op.drop_table("payment_users")
