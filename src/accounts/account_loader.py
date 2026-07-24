"""
src/account_loader.py — Multi-format account loader with Round-Robin proxy allocation.

Supported formats:
  1. Bare .session file  (api_id/api_hash supplied externally)
  2. .session + .json pair  (json carries app_id, app_hash, phone, fingerprint)
  3. TData folder  (Telegram Desktop local storage, requires opentele)

Proxy allocation — ProxyAllocator:
  Distributes a proxy list across accounts using accounts_per_proxy ratio.
  With accounts_per_proxy=2 and 2 proxies for 5 accounts:
    A1→P1, A2→P1, A3→P2, A4→P2, A5→P1  (cycling)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

from src.config import AccountConfig, ProxyConfig

logger = logging.getLogger(__name__)

try:
    import opentele  # noqa: F401  -- presence check only; TDataConverter does the real work
    _OPENTELE_OK = True
except ImportError:
    _OPENTELE_OK = False
    logger.debug("opentele not installed — TData loading unavailable.")


# ---------------------------------------------------------------------------
# ProxyAllocator: Round-Robin with configurable accounts-per-proxy ratio
# ---------------------------------------------------------------------------

class ProxyAllocator:
    """
    Assigns proxies to accounts with a configurable ratio and Round-Robin cycling.

    accounts_per_proxy=2 means each proxy is assigned to 2 consecutive accounts
    before the allocator moves to the next proxy.  When proxies run out, the
    cycle restarts from index 0.

    Example — 3 proxies, accounts_per_proxy=2, 7 accounts:
      A0→P0, A1→P0, A2→P1, A3→P1, A4→P2, A5→P2, A6→P0
    """

    def __init__(
        self,
        proxies: List[ProxyConfig],
        accounts_per_proxy: int = 1,
    ) -> None:
        if accounts_per_proxy < 1:
            raise ValueError("accounts_per_proxy must be >= 1")
        self._proxies = proxies
        self._ratio = accounts_per_proxy
        self._call_count = 0

    def next(self) -> Optional[ProxyConfig]:
        """Returns the proxy for the next account in the allocation sequence."""
        if not self._proxies:
            return None
        proxy_index = (self._call_count // self._ratio) % len(self._proxies)
        self._call_count += 1
        return self._proxies[proxy_index]

    def assign(self, n: int) -> List[Optional[ProxyConfig]]:
        """Returns a list of N proxy assignments."""
        return [self.next() for _ in range(n)]


# ---------------------------------------------------------------------------
# Format loaders
# ---------------------------------------------------------------------------

def load_from_session_file(
    session_path: str,
    api_id: int,
    api_hash: str,
    phone: str,
    proxy: Optional[ProxyConfig] = None,
) -> AccountConfig:
    """
    Creates AccountConfig from a bare .session path.

    session_path may or may not include the .session extension.
    The file must already exist (produced by an earlier interactive login).
    """
    p = Path(session_path)
    actual = p if p.suffix == ".session" else p.with_suffix(".session")
    if not actual.exists():
        raise FileNotFoundError(f"Session file not found: {actual}")

    return AccountConfig(
        api_id=api_id,
        api_hash=api_hash,
        phone=phone,
        proxy=proxy,
        session_dir=str(actual.parent),
    )


def load_from_session_json_pair(
    session_path: str,
    proxy: Optional[ProxyConfig] = None,
) -> AccountConfig:
    """
    Loads account credentials from a .session + .json companion pair.

    Required JSON keys:
      app_id      (int)   Telegram API ID
      app_hash    (str)   Telegram API hash
      phone       (str)   Account phone, e.g. "+79001234567"

    Optional JSON keys:
      device      (str)   Device model string (default: "Samsung Galaxy S23")
      system      (str)   System version    (default: "Android 14")
      app_version (str)   App version       (default: "10.3.1")
    """
    supplied = Path(session_path)
    supplied_text = str(supplied)
    if supplied_text.endswith(".session.enc"):
        base = Path(supplied_text[: -len(".session.enc")])
    else:
        base = supplied.with_suffix("")
    json_file = Path(f"{base}.json")
    session_file = Path(f"{base}.session")
    encrypted_session_file = Path(f"{base}.session.enc")

    if not json_file.exists():
        raise FileNotFoundError(f"JSON companion not found: {json_file}")
    if not session_file.exists() and not encrypted_session_file.exists():
        raise FileNotFoundError(
            f"Session file not found: {session_file} or {encrypted_session_file}"
        )

    with json_file.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    missing = {"app_id", "app_hash", "phone"} - data.keys()
    if missing:
        raise ValueError(f"JSON {json_file} missing required fields: {missing}")

    return AccountConfig(
        api_id=int(data["app_id"]),
        api_hash=str(data["app_hash"]),
        phone=str(data["phone"]),
        proxy=proxy,
        device_model=str(data.get("device", "Samsung Galaxy S23")),
        system_version=str(data.get("system", "Android 14")),
        app_version=str(data.get("app_version", "10.3.1")),
        lang_code=str(data.get("lang_code", "en")),
        system_lang_code=str(data.get("system_lang_code", "en")),
        lang_pack=str(data.get("lang_pack", "android")),
        sdk=int(data.get("sdk", 0)),
        tz_offset=int(data.get("tz_offset", 0)),
        perf_cat=int(data.get("perf_cat", 0)),
        session_dir=str(session_file.parent),
    )


async def load_from_tdata(
    tdata_path: str,
    proxy: Optional[ProxyConfig] = None,
    session_dir: str = "sessions",
    password: Optional[str] = None,
) -> AccountConfig:
    """
    Converts a Telegram Desktop TData folder to a Telethon-compatible session.

    Delegates to TDataConverter (src/proxy/tdata_converter.py) so tdata loading
    has exactly one implementation, instead of two independently-maintained
    copies of the same opentele plumbing. That implementation already:
      - accepts a 2FA cloud password (`password`) instead of failing unhandled;
      - keeps the produced session under the SAME api_id/api_hash/device
        fingerprint its auth key was created under, rather than this
        AccountConfig's unrelated defaults (opentele's own docs warn that
        mixing API layers on one session risks a ban);
      - runs the blocking tdata read off the event loop;
      - lets a mid-conversion FloodWaitError propagate instead of masking it
        as a generic "invalid tdata" error.

    The first (main) account found in the TData folder is converted; call
    TDataConverter.tdata_to_sessions_all() directly if the folder holds more
    than one account and you need all of them.

    Requires: pip install opentele
    """
    if not _OPENTELE_OK:
        raise ImportError(
            "opentele is required for TData loading. "
            "Install: pip install opentele"
        )

    from src.proxy.tdata_converter import TDataConverter

    result = await TDataConverter().tdata_to_session(tdata_path, session_dir, password)
    fp = result.fingerprint
    phone = result.phone or Path(tdata_path).name

    logger.info("TData converted: phone=%s → %s.session", phone, result.session_path)

    return AccountConfig(
        api_id=fp.api_id,
        api_hash=fp.api_hash,
        phone=phone,
        proxy=proxy,
        device_model=fp.device_model,
        system_version=fp.system_version,
        app_version=fp.app_version,
        session_dir=session_dir,
    )


# ---------------------------------------------------------------------------
# Batch directory loader
# ---------------------------------------------------------------------------

def load_accounts_from_directory(
    directory: str,
    api_id: int = 0,
    api_hash: str = "",
    proxies: Optional[List[ProxyConfig]] = None,
    accounts_per_proxy: int = 1,
) -> List[AccountConfig]:
    """
    Scans a directory for .session files and loads all accounts found.

    Resolution per .session file:
      1. If a .json companion exists → load_from_session_json_pair().
      2. Otherwise, if api_id/api_hash were supplied → bare session load.
      3. Otherwise → skip with a warning.

    Proxy assignment follows the accounts_per_proxy Round-Robin rule.
    Files are processed in alphabetical order for deterministic allocation.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    by_base: dict[str, Path] = {}
    for session_file in dir_path.glob("*.session"):
        by_base[str(session_file.with_suffix(""))] = session_file
    for encrypted_file in dir_path.glob("*.session.enc"):
        base_text = str(encrypted_file)[: -len(".session.enc")]
        by_base.setdefault(base_text, encrypted_file)
    session_files = sorted(by_base.values(), key=lambda path: path.name)
    if not session_files:
        logger.warning("No .session files found in: %s", directory)
        return []

    allocator = ProxyAllocator(proxies or [], accounts_per_proxy=accounts_per_proxy)
    accounts: List[AccountConfig] = []

    for sf in session_files:
        proxy = allocator.next()
        base_text = (
            str(sf)[: -len(".session.enc")]
            if str(sf).endswith(".session.enc")
            else str(sf.with_suffix(""))
        )
        json_companion = Path(f"{base_text}.json")

        try:
            if json_companion.exists():
                account = load_from_session_json_pair(str(sf), proxy=proxy)
            elif api_id and api_hash:
                phone_raw = Path(base_text).name
                phone = phone_raw if phone_raw.startswith("+") else f"+{phone_raw}"
                account = AccountConfig(
                    api_id=api_id,
                    api_hash=api_hash,
                    phone=phone,
                    proxy=proxy,
                    session_dir=str(dir_path),
                )
            else:
                logger.warning(
                    "Skipping %s: no .json companion and no api_id/api_hash provided.",
                    sf.name,
                )
                continue

            accounts.append(account)
            logger.debug("Loaded %s → proxy=%s", account.phone, proxy)

        except Exception as exc:
            logger.error("Failed to load %s: %s", sf.name, exc)

    logger.info("Loaded %d accounts from '%s'.", len(accounts), directory)
    return accounts
