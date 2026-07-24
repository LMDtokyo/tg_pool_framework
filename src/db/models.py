"""
src/db/models.py — SQLAlchemy 2.0 declarative models for durable account state.

Only the account's aggregated state (config + health) is persisted here.
Per-run send counters (BatchReport) stay ephemeral by design — they describe
one batch, not the account's long-lived identity.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, UniqueConstraint, false, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AccountRow(Base):
    """
    One row per Telegram account, keyed by phone number.

    Mirrors src.config.AccountConfig + src.accounts.health_checker.AccountState so that
    AccountRepository can round-trip a RegistryEntry without a separate DTO layer.
    """

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)

    # --- AccountConfig fields ---
    api_id: Mapped[int] = mapped_column(nullable=False)
    api_hash: Mapped[str] = mapped_column(Text, nullable=False)
    device_model: Mapped[str] = mapped_column(Text, nullable=False)
    system_version: Mapped[str] = mapped_column(Text, nullable=False)
    app_version: Mapped[str] = mapped_column(Text, nullable=False)
    session_dir: Mapped[str] = mapped_column(Text, nullable=False)
    proxy_host: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    proxy_port: Mapped[Optional[int]] = mapped_column(nullable=True)
    proxy_username: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    proxy_password: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    proxy_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="socks5")

    # --- AccountState fields ---
    # server_default (not Python-side default=) so that AccountRepository's Core-level
    # INSERT ... ON CONFLICT statements — which bypass the ORM unit-of-work — still get
    # a value when register() persists an entry with state=None.
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="unknown")
    is_premium: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    restriction_expires: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    first_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    last_checked: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Search/organize: geo, 2FA, role, folder (see AccountQuery) ---
    country: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_2fa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    folder: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CampaignRow(Base):
    """One row per send campaign (one orchestrate_multi_source() run)."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    message_preview: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total: Mapped[int] = mapped_column(nullable=False, default=0)
    succeeded: Mapped[int] = mapped_column(nullable=False, default=0)
    failed: Mapped[int] = mapped_column(nullable=False, default=0)


class CampaignResultRow(Base):
    """One row per message delivery attempt within a campaign."""

    __tablename__ = "campaign_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id"), nullable=False, index=True
    )
    recipient: Mapped[str] = mapped_column(Text, nullable=False)
    worker_phone: Mapped[str] = mapped_column(Text, nullable=False)
    success: Mapped[bool] = mapped_column(nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProxyRow(Base):
    """A reusable proxy and the most recent Telegram connectivity result."""

    __tablename__ = "proxies"
    __table_args__ = (
        UniqueConstraint(
            "proxy_type", "host", "port", "username", name="uq_proxies_endpoint_user"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    proxy_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="socks5")
    host: Mapped[str] = mapped_column(Text, nullable=False)
    port: Mapped[int] = mapped_column(nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    password: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    version: Mapped[str] = mapped_column(Text, nullable=False, server_default="ipv4")

    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="unknown", index=True)
    response_ms: Mapped[Optional[float]] = mapped_column(nullable=True)
    country: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
