from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "payment_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    telegram_username: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ApiKeyRow(Base):
    __tablename__ = "payment_api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("payment_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    key_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WalletRow(Base):
    __tablename__ = "payment_wallets"
    __table_args__ = (UniqueConstraint("network", "address", name="uq_payment_wallet_address"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("payment_users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    network: Mapped[str] = mapped_column(String(32), nullable=False)
    asset: Mapped[str] = mapped_column(String(16), nullable=False)
    address: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WalletSweepRow(Base):
    __tablename__ = "payment_wallet_sweeps"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("payment_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("payment_wallets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    source_address: Mapped[str] = mapped_column(String(128), nullable=False)
    destination_address: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    transferred_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(24, 8), nullable=True
    )
    asset: Mapped[str] = mapped_column(String(16), nullable=False)
    network: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    transaction_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    chain_balance_before: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(24, 8), nullable=True
    )
    chain_balance_after: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(24, 8), nullable=True
    )
    network_fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 8), nullable=True)
    requested_by: Mapped[str] = mapped_column(Text, nullable=False, server_default="admin")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class LedgerEntryRow(Base):
    __tablename__ = "payment_ledger_entries"
    __table_args__ = (
        UniqueConstraint("reference_type", "reference_id", name="uq_payment_ledger_reference"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("payment_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class DepositRow(Base):
    __tablename__ = "payment_deposits"
    __table_args__ = (
        UniqueConstraint(
            "network", "transaction_hash", "event_index", name="uq_payment_deposit_event"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("payment_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("payment_wallets.id", ondelete="RESTRICT"), nullable=False
    )
    network: Mapped[str] = mapped_column(String(32), nullable=False)
    asset: Mapped[str] = mapped_column(String(16), nullable=False)
    transaction_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    event_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    confirmations: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    credited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProductRow(Base):
    __tablename__ = "payment_products"

    provider_product_id: Mapped[int] = mapped_column(primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OrderRow(Base):
    __tablename__ = "payment_orders"
    __table_args__ = (
        UniqueConstraint("user_id", "external_order_id", name="uq_payment_order_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("payment_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_order_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    provider_order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProviderOrderRow(Base):
    __tablename__ = "payment_provider_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("payment_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    response_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WebhookEventRow(Base):
    __tablename__ = "payment_webhook_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RetailPricingRow(Base):
    __tablename__ = "payment_retail_pricing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    markup_percent: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    markup_fixed: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CountryPricingRow(Base):
    __tablename__ = "payment_country_pricing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    markup_percent: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    markup_fixed: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
