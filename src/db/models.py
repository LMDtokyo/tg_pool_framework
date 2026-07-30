"""
src/db/models.py — SQLAlchemy 2.0 declarative models for durable account state.

Only the account's aggregated state (config + health) is persisted here.
Per-run send counters (BatchReport) stay ephemeral by design — they describe
one batch, not the account's long-lived identity.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Text, UniqueConstraint, false, func, true
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


class ScheduledCampaignRow(Base):
    """
    A persisted, restart-durable definition of a future or recurring send job.

    payload stores the full validated SendByIdStartRequest/SendByNumbersStartRequest
    body (as JSON) so ScheduledCampaignManager can replay it into the matching
    manager's start() at fire time without a second schema layer. next_run_at is
    the sweep loop's only query condition; occurrences_run/enabled together decide
    whether a fired campaign gets rearmed or retired (see ScheduledCampaignManager).
    """

    __tablename__ = "scheduled_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    campaign_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    repeat_interval_hours: Mapped[Optional[float]] = mapped_column(nullable=True)
    max_occurrences: Mapped[Optional[int]] = mapped_column(nullable=True)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    occurrences_run: Mapped[int] = mapped_column(nullable=False, server_default="0")
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_job_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LicenseStateRow(Base):
    """
    Single-row cache of the last known-good license activation, keyed by a
    fixed id=1 -- this backend serves one install, so there's only ever one
    active subscription to remember. license_key is stored in plaintext (not
    hashed) because the periodic revalidation loop must resend it to the
    license server on every check; the security boundary is the server's
    hwid binding, not hiding the key from the machine it's licensed to.
    """

    __tablename__ = "license_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    license_key: Mapped[str] = mapped_column(Text, nullable=False)
    hwid: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
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

    # Distinct from status/response_ms above: those describe raw connectivity
    # (does the proxy answer at all), this describes whether Telegram itself
    # has started banning accounts that connect through it -- a proxy can be
    # perfectly "alive" and still be a burned/blacklisted exit IP. Bumped by
    # job managers (send_by_id, send_by_numbers, engagement) whenever a sender
    # using this exact proxy hits a ban/deactivation signal.
    ban_signal_count: Mapped[int] = mapped_column(nullable=False, server_default="0")
    last_ban_signal_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
