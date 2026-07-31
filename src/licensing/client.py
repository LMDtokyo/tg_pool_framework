"""
src/licensing/client.py — HTTP client for the central license server.

This backend is the only thing that ever talks to the license authority;
the WPF launcher goes through this backend (see src/api/app.py), same as
every other external integration (Datamoll, Hero SMS, ...).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx


class LicenseError(Exception):
    """Base for every rejection the license server can return."""


class LicenseNotFoundError(LicenseError):
    pass


class LicenseRevokedError(LicenseError):
    pass


class LicenseExpiredError(LicenseError):
    pass


class LicenseDeviceMismatchError(LicenseError):
    pass


class LicenseServerUnavailableError(LicenseError):
    """Network failure or an unexpected server response -- not a rejection,
    just "couldn't get an answer". Callers treat this as transient."""


@dataclass(frozen=True)
class LicenseActivation:
    tier: str
    activated_at: datetime
    expires_at: datetime
    signature: str = ""


_ERROR_BY_REASON = {
    "not_found": LicenseNotFoundError,
    "revoked": LicenseRevokedError,
    "expired": LicenseExpiredError,
    "device_mismatch": LicenseDeviceMismatchError,
}


class LicenseServerClient:
    def __init__(self, base_url: str, *, timeout: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def activate(self, license_key: str, hwid: str) -> LicenseActivation:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/license/activate",
                    json={"license_key": license_key, "hwid": hwid},
                )
        except httpx.HTTPError as exc:
            raise LicenseServerUnavailableError(str(exc)) from exc

        if response.status_code == 200:
            body = response.json()
            return LicenseActivation(
                tier=body["tier"],
                activated_at=datetime.fromisoformat(body["activated_at"]),
                expires_at=datetime.fromisoformat(body["expires_at"]),
                signature=body.get("signature", ""),
            )

        reason, message = self._parse_error(response)
        error_cls = _ERROR_BY_REASON.get(reason)
        if error_cls is not None:
            raise error_cls(message)
        raise LicenseServerUnavailableError(f"Unexpected response {response.status_code}: {message}")

    async def fetch_profile_names(self) -> tuple[list[str], list[str]]:
        """
        (first_names, last_names) from the shared server-side pool (see
        license_server/profile_names.py). Raises LicenseServerUnavailableError
        on any network/response problem -- callers treat this as best-effort
        and fall back to a small built-in default list.
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self._base_url}/profile-names")
        except httpx.HTTPError as exc:
            raise LicenseServerUnavailableError(str(exc)) from exc

        if response.status_code != 200:
            raise LicenseServerUnavailableError(f"Unexpected response {response.status_code}")
        body = response.json()
        first_names = body.get("first_names") or []
        last_names = body.get("last_names") or []
        if not first_names or not last_names:
            raise LicenseServerUnavailableError("Profile name pool response was empty")
        return first_names, last_names

    @staticmethod
    def _parse_error(response: httpx.Response) -> tuple[str, str]:
        try:
            detail = response.json().get("detail")
        except ValueError:
            return "", response.text
        if isinstance(detail, dict):
            return detail.get("reason", ""), detail.get("message", str(detail))
        return "", str(detail)
