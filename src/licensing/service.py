"""
src/licensing/service.py — Local license gate.

Fail-closed by design: is_active() starts False and only becomes True after
a successful activate() against the central license server. A definitive
rejection (not found / revoked / expired / device mismatch) immediately
flips it back to False -- no grace period. A transient network failure
during periodic re-validation does NOT immediately revoke access; it's
tolerated for `offline_grace` on top of the normal `revalidate_interval`,
so a brief license-server outage or the customer being briefly offline
doesn't lock out someone who is legitimately licensed.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.db.license_repository import LicenseStateRepository, StoredLicenseState
from src.licensing.client import LicenseError, LicenseServerClient, LicenseServerUnavailableError
from src.licensing.signature import verify_activation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LicenseStatus:
    valid: bool
    tier: Optional[str] = None
    expires_at: Optional[datetime] = None
    reason: str = ""


class LicenseService:
    def __init__(
        self,
        client: LicenseServerClient,
        repository: Optional[LicenseStateRepository],
        *,
        revalidate_interval: timedelta,
        offline_grace: timedelta,
    ) -> None:
        self._client = client
        self._repository = repository
        self._revalidate_interval = revalidate_interval
        self._offline_grace = offline_grace

        self._valid = False
        self._tier: Optional[str] = None
        self._expires_at: Optional[datetime] = None
        self._last_confirmed_at: Optional[datetime] = None
        self._last_reason = "not_activated"
        self._license_key: Optional[str] = None
        self._hwid: Optional[str] = None

    def is_active(self) -> bool:
        if not self._valid or self._last_confirmed_at is None:
            return False
        age = datetime.now(timezone.utc) - self._last_confirmed_at
        return age <= self._revalidate_interval + self._offline_grace

    def status(self) -> LicenseStatus:
        if self.is_active():
            return LicenseStatus(valid=True, tier=self._tier, expires_at=self._expires_at)
        return LicenseStatus(valid=False, reason=self._last_reason)

    async def restore_cached(self) -> None:
        """
        Best-effort warm start from the last locally cached activation, so
        is_active() isn't hard-False for the brief window before the first
        live activate() call lands (WPF calls activate() with its stored
        key immediately on every startup, so this mainly covers that gap
        and the periodic-revalidation loop's offline-grace bookkeeping).
        """
        if self._repository is None:
            return
        cached = await self._repository.load()
        if cached is None:
            return
        if cached.signature:
            verified = verify_activation(
                license_key=cached.license_key,
                hwid=cached.hwid,
                tier=cached.tier,
                expires_at=cached.expires_at.isoformat(),
                signature_hex=cached.signature,
            )
            if not verified:
                logger.error(
                    "Cached license state failed signature verification -- discarding "
                    "(local database was modified outside the app, or corrupted)"
                )
                return
        else:
            logger.warning("Cached license state has no signature (written before signing was enabled) -- "
                            "trusting it for this warm start, but it will not survive tampering checks")
        self._license_key = cached.license_key
        self._hwid = cached.hwid
        self._tier = cached.tier
        self._expires_at = cached.expires_at
        self._last_confirmed_at = cached.last_validated_at
        self._valid = True

    async def activate(self, license_key: str, hwid: str) -> LicenseStatus:
        try:
            result = await self._client.activate(license_key, hwid)
        except LicenseServerUnavailableError as exc:
            if self._license_key is None:
                # No prior good state to fall back on -- first activation needs the server.
                self._valid = False
                self._last_reason = f"license_server_unreachable: {exc}"
                return LicenseStatus(valid=False, reason=self._last_reason)
            logger.warning("License re-validation failed (server unreachable): %s", exc)
            return self.status()  # keep riding the existing grace window
        except LicenseError as exc:
            self._valid = False
            self._last_reason = type(exc).__name__
            return LicenseStatus(valid=False, reason=self._last_reason)

        if result.signature:
            verified = verify_activation(
                license_key=license_key,
                hwid=hwid,
                tier=result.tier,
                expires_at=result.expires_at.isoformat(),
                signature_hex=result.signature,
            )
            if not verified:
                self._valid = False
                self._last_reason = "signature_invalid"
                logger.error(
                    "License server response failed signature verification -- rejecting "
                    "(possible network tampering or impersonation)"
                )
                return LicenseStatus(valid=False, reason=self._last_reason)
        else:
            logger.warning(
                "License server response is unsigned -- accepting without verification "
                "(upgrade the license server to enable tamper protection)"
            )

        self._license_key = license_key
        self._hwid = hwid
        self._tier = result.tier
        self._expires_at = result.expires_at
        self._last_confirmed_at = datetime.now(timezone.utc)
        self._last_reason = ""
        self._valid = True

        if self._repository is not None:
            await self._repository.save(
                StoredLicenseState(
                    license_key=license_key,
                    hwid=hwid,
                    tier=result.tier,
                    expires_at=result.expires_at,
                    last_validated_at=self._last_confirmed_at,
                    signature=result.signature,
                )
            )
        return LicenseStatus(valid=True, tier=result.tier, expires_at=result.expires_at)

    async def run_periodic_revalidation(self) -> None:
        """Runs for the lifetime of the app; start as a background asyncio task."""
        while True:
            await asyncio.sleep(self._revalidate_interval.total_seconds())
            if self._license_key is None or self._hwid is None:
                continue
            await self.activate(self._license_key, self._hwid)
