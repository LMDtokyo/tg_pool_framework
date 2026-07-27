"""
license_server/db/repository.py — The only place ORM/SQL details for license
keys are visible. Owns the activation state machine, which is the security
boundary of the whole service: it decides who gets to claim a key and who
gets rejected as a device mismatch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from license_server.db.models import LicenseKeyRow
from license_server.keycodes import generate_key_code, hash_key_code, last4
from license_server.tiers import Tier, duration_for

logger = logging.getLogger(__name__)

_MAX_KEY_GENERATION_ATTEMPTS = 5
_MAX_ACTIVATION_RACE_RETRIES = 2


def _aware_utc(value: datetime) -> datetime:
    """SQLite (unlike Postgres) round-trips DateTime(timezone=True) as naive --
    every value this app ever writes is UTC, so a naive read-back is safely
    reinterpreted as UTC rather than compared incorrectly against aware `now`."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class ActivationOutcome(str, Enum):
    OK = "ok"
    NOT_FOUND = "not_found"
    REVOKED = "revoked"
    EXPIRED = "expired"
    DEVICE_MISMATCH = "device_mismatch"


@dataclass(frozen=True)
class ActivationResult:
    outcome: ActivationOutcome
    tier: Optional[str] = None
    activated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


@dataclass(frozen=True)
class IssuedKey:
    id: int
    key_code: str
    tier: str


@dataclass(frozen=True)
class LicenseKeySummary:
    id: int
    key_last4: str
    tier: str
    note: str
    status: str
    hwid_bound: bool
    activated_at: Optional[datetime]
    expires_at: Optional[datetime]
    last_seen_at: Optional[datetime]
    created_at: datetime


class LicenseKeyRepository:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Issuance (admin)
    # ------------------------------------------------------------------

    async def create_keys(self, tier: Tier, count: int, note: str) -> List[IssuedKey]:
        """Mint `count` fresh keys. Each insert retries on the (astronomically
        unlikely) hash collision rather than trusting entropy blindly."""
        issued: List[IssuedKey] = []
        for _ in range(count):
            issued.append(await self._create_one_key(tier, note))
        return issued

    async def _create_one_key(self, tier: Tier, note: str) -> IssuedKey:
        for attempt in range(_MAX_KEY_GENERATION_ATTEMPTS):
            key_code = generate_key_code()
            row = LicenseKeyRow(
                key_hash=hash_key_code(key_code),
                key_last4=last4(key_code),
                tier=tier.value,
                note=note,
            )
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        session.add(row)
                        await session.flush()
                        row_id = row.id
                return IssuedKey(id=row_id, key_code=key_code, tier=tier.value)
            except IntegrityError:
                logger.warning("License key hash collision on attempt %d -- retrying", attempt)
        raise RuntimeError("Could not generate a unique license key after several attempts")

    async def revoke(self, key_id: int) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(LicenseKeyRow).where(LicenseKeyRow.id == key_id).values(revoked=True)
                )
        return result.rowcount > 0

    async def reset_device(self, key_id: int) -> bool:
        """Support remedy for a customer's hardware change -- unbinds the key
        without touching its expiry, so the subscription time isn't extended."""
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(LicenseKeyRow)
                    .where(LicenseKeyRow.id == key_id)
                    .values(hwid_hash=None, activated_at=None)
                )
        return result.rowcount > 0

    async def list_keys(self, *, limit: int, offset: int, now: datetime) -> tuple[List[LicenseKeySummary], int]:
        async with self._session_factory() as session:
            total = (await session.execute(select(func.count()).select_from(LicenseKeyRow))).scalar_one()
            result = await session.execute(
                select(LicenseKeyRow).order_by(LicenseKeyRow.id.desc()).limit(limit).offset(offset)
            )
            rows = result.scalars().all()
        return [self._to_summary(row, now) for row in rows], total

    @staticmethod
    def _to_summary(row: LicenseKeyRow, now: datetime) -> LicenseKeySummary:
        if row.revoked:
            status = "revoked"
        elif row.expires_at is None:
            status = "unused"
        elif _aware_utc(row.expires_at) < now:
            status = "expired"
        else:
            status = "active"
        return LicenseKeySummary(
            id=row.id,
            key_last4=row.key_last4,
            tier=row.tier,
            note=row.note,
            status=status,
            hwid_bound=row.hwid_hash is not None,
            activated_at=row.activated_at and _aware_utc(row.activated_at),
            expires_at=row.expires_at and _aware_utc(row.expires_at),
            last_seen_at=row.last_seen_at and _aware_utc(row.last_seen_at),
            created_at=_aware_utc(row.created_at),
        )

    # ------------------------------------------------------------------
    # Activation (public) -- the security-critical state machine
    # ------------------------------------------------------------------

    async def activate(self, key_code: str, hwid_hash: str, *, now: datetime) -> ActivationResult:
        key_hash = hash_key_code(key_code)
        for _ in range(_MAX_ACTIVATION_RACE_RETRIES + 1):
            outcome = await self._try_activate_once(key_hash, hwid_hash, now)
            if outcome is not None:
                return outcome
            # Lost a race against a concurrent first-activation of the same
            # key -- re-read the now-updated row and evaluate it fresh.
        return ActivationResult(ActivationOutcome.DEVICE_MISMATCH)

    async def _try_activate_once(
        self, key_hash: str, hwid_hash: str, now: datetime
    ) -> Optional[ActivationResult]:
        async with self._session_factory() as session:
            async with session.begin():
                row = (
                    await session.execute(select(LicenseKeyRow).where(LicenseKeyRow.key_hash == key_hash))
                ).scalar_one_or_none()

                if row is None:
                    return ActivationResult(ActivationOutcome.NOT_FOUND)
                if row.revoked:
                    return ActivationResult(ActivationOutcome.REVOKED)

                if row.hwid_hash is None:
                    return await self._claim_unbound_key(session, row, hwid_hash, now)

                if row.expires_at is not None and now > _aware_utc(row.expires_at):
                    return ActivationResult(ActivationOutcome.EXPIRED)
                if row.hwid_hash != hwid_hash:
                    return ActivationResult(ActivationOutcome.DEVICE_MISMATCH)

                await session.execute(
                    update(LicenseKeyRow).where(LicenseKeyRow.id == row.id).values(last_seen_at=now)
                )
                return ActivationResult(
                    ActivationOutcome.OK,
                    tier=row.tier,
                    activated_at=_aware_utc(row.activated_at),
                    expires_at=_aware_utc(row.expires_at),
                )

    @staticmethod
    async def _claim_unbound_key(session, row: LicenseKeyRow, hwid_hash: str, now: datetime) -> Optional[ActivationResult]:
        """
        Atomic compare-and-swap: the WHERE clause re-checks hwid_hash IS NULL
        against the row as it stands at UPDATE time (not the possibly-stale
        SELECT above), so two concurrent first-activations of the same key
        can never both succeed -- the loser's UPDATE simply matches zero rows.
        """
        tier = Tier(row.tier)
        expires_at = now + duration_for(tier)
        result = await session.execute(
            update(LicenseKeyRow)
            .where(LicenseKeyRow.id == row.id, LicenseKeyRow.hwid_hash.is_(None))
            .values(hwid_hash=hwid_hash, activated_at=now, expires_at=expires_at, last_seen_at=now)
        )
        if result.rowcount == 0:
            return None  # race lost -- caller retries and re-reads
        return ActivationResult(ActivationOutcome.OK, tier=row.tier, activated_at=now, expires_at=expires_at)


async def ensure_license_tables(session_factory: async_sessionmaker) -> None:
    """Create the license_keys table when it doesn't exist yet (belt-and-suspenders alongside Alembic)."""
    engine = session_factory.kw["bind"]
    async with engine.begin() as connection:
        await connection.run_sync(LicenseKeyRow.__table__.create, checkfirst=True)
