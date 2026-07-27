"""
license_server/db/models.py — SQLAlchemy 2.0 declarative models for the
license authority's own database. Independent from src/db/models.py: this is
a separately deployed service with its own schema and its own migration
history.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Text, false, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class LicenseKeyRow(Base):
    """
    One row per issued license key.

    The plaintext key is never stored -- only its SHA-256 hash (for lookup)
    and last 4 characters (for an admin to recognize it in a list without
    being able to reconstruct the whole key). hwid_hash is null until first
    activation; expires_at is null until first activation (the subscription
    clock starts when the customer actually uses the key, not when it's
    minted).
    """

    __tablename__ = "license_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    key_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    key_last4: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    hwid_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())

    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
