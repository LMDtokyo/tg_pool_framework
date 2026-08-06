from __future__ import annotations

import asyncio
import os
from typing import Optional

import hvac


DATAMOLL_SECRET_PATH = "payment-server/datamoll"
DATAMOLL_SECRET_MOUNT = "secret"


class VaultError(RuntimeError):
    """Raised when Vault is configured but a secret can't be read from it."""


def _read_datamoll_credentials_sync(addr: str, role_id: str, secret_id: str) -> tuple[str, str]:
    client = hvac.Client(url=addr)
    try:
        client.auth.approle.login(role_id=role_id, secret_id=secret_id)
    except Exception as exc:
        raise VaultError(f"Vault AppRole login failed: {exc}") from exc
    if not client.is_authenticated():
        raise VaultError("Vault AppRole login did not return a valid token")

    try:
        response = client.secrets.kv.v2.read_secret_version(
            path=DATAMOLL_SECRET_PATH,
            mount_point=DATAMOLL_SECRET_MOUNT,
            raise_on_deleted_version=True,
        )
    except Exception as exc:
        raise VaultError(f"Unable to read {DATAMOLL_SECRET_PATH} from Vault: {exc}") from exc

    data = response.get("data", {}).get("data", {})
    provider_key = str(data.get("provider_key") or "").strip()
    provider_secret = str(data.get("provider_secret") or "").strip()
    if not provider_key or not provider_secret:
        raise VaultError(
            f"Vault secret {DATAMOLL_SECRET_PATH} is missing provider_key/provider_secret"
        )
    return provider_key, provider_secret


async def load_datamoll_credentials() -> Optional[tuple[str, str]]:
    """Best-effort-free, fail-loud Vault lookup for the Datamoll provider
    credentials. Returns None (not an error) when Vault isn't configured at
    all -- that's the documented local/dev path, which keeps reading
    DATAMOLL_PROVIDER_KEY/SECRET straight from the environment. Once
    VAULT_ADDR is set, though, a failure to reach Vault or read the secret
    raises -- silently falling back to a missing/stale env var would be
    worse than refusing to start.
    """
    addr = os.getenv("VAULT_ADDR", "").strip()
    if not addr:
        return None
    role_id = os.getenv("VAULT_ROLE_ID", "").strip()
    secret_id = os.getenv("VAULT_SECRET_ID", "").strip()
    if not role_id or not secret_id:
        raise VaultError("VAULT_ADDR is set but VAULT_ROLE_ID/VAULT_SECRET_ID are missing")
    return await asyncio.to_thread(_read_datamoll_credentials_sync, addr, role_id, secret_id)
