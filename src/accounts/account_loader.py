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
import os
import uuid
from pathlib import Path
from typing import List, Optional, Set, TYPE_CHECKING

from src.config import AccountConfig, ProxyConfig

if TYPE_CHECKING:
    from src.api.telegram_auth import FingerprintCatalog, TelegramFingerprint

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

def _optional_int(value: object, default: int = 0) -> int:
    """Return an int for optional metadata fields, falling back on invalid exports."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

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
      app_id (or api_id)   (int)   Telegram API ID
      app_hash (or api_hash) (str) Telegram API hash
      phone                 (str) Account phone, e.g. "+79001234567"

    api_id/api_hash are accepted as aliases for app_id/app_hash -- Telethon's
    own constructor parameters (and most third-party tools/marketplaces that
    export a Telegram session) use that naming, not this app's app_id/app_hash,
    so requiring the exact latter name would silently reject most externally
    -sourced account files.

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

    app_id_value = data.get("app_id", data.get("api_id"))
    app_hash_value = data.get("app_hash", data.get("api_hash"))
    missing = [
        name for name, value in (
            ("app_id/api_id", app_id_value), ("app_hash/api_hash", app_hash_value), ("phone", data.get("phone")),
        ) if value is None
    ]
    if missing:
        raise ValueError(f"JSON {json_file} missing required fields: {', '.join(missing)}")

    return AccountConfig(
        api_id=int(app_id_value),
        api_hash=str(app_hash_value),
        phone=str(data["phone"]),
        proxy=proxy,
        device_model=str(data.get("device", "Samsung Galaxy S23")),
        system_version=str(data.get("system", "Android 14")),
        app_version=str(data.get("app_version", "10.3.1")),
        lang_code=str(data.get("lang_code", "en")),
        system_lang_code=str(data.get("system_lang_code", "en")),
        lang_pack=str(data.get("lang_pack", "android")),
        sdk=_optional_int(data.get("sdk"), 0),
        tz_offset=_optional_int(data.get("tz_offset"), 0),
        perf_cat=_optional_int(data.get("perf_cat"), 0),
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

def _write_fingerprint_sidecar(
    base_text: str, *, api_id: int, api_hash: str, phone: str, fingerprint: "TelegramFingerprint"
) -> None:
    """
    Persists a chosen fingerprint next to a bare-imported session (same shape
    src/api/json_generator.py writes), so every future load finds the .json
    companion and reuses this exact fingerprint via load_from_session_json_pair()
    instead of choosing (or falling back to a default) again.
    """
    payload = {
        "app_id": api_id,
        "app_hash": api_hash,
        "phone": phone,
        "device": fingerprint.device,
        "system": f"SDK {fingerprint.sdk}",
        "app_version": fingerprint.app_version,
        "lang_code": fingerprint.lang_code,
        "system_lang_code": fingerprint.system_lang_code,
        "lang_pack": fingerprint.lang_pack,
        "sdk": fingerprint.sdk,
        "tz_offset": fingerprint.tz_offset,
        "perf_cat": fingerprint.perf_cat,
    }
    json_path = Path(f"{base_text}.json")
    temporary = json_path.with_suffix(f".json.{uuid.uuid4().hex[:8]}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, json_path)


def load_accounts_from_directory(
    directory: str,
    api_id: int = 0,
    api_hash: str = "",
    proxies: Optional[List[ProxyConfig]] = None,
    accounts_per_proxy: int = 1,
    fingerprint_catalog: "Optional[FingerprintCatalog]" = None,
    used_fingerprints: Optional[Set[tuple]] = None,
    load_failures: Optional[List[dict]] = None,
) -> List[AccountConfig]:
    """
    Scans a directory for .session files and loads all accounts found.

    Resolution per .session file:
      1. If a .json companion exists → load_from_session_json_pair().
      2. Otherwise, if api_id/api_hash were supplied → bare session load. If
         fingerprint_catalog is given, a fresh (device, app_version) pair is
         chosen and persisted as a .json companion right here -- without a
         catalog, every such account instead falls back to AccountConfig's
         identical hardcoded defaults, which is exactly the duplicate-device
         signal this catalog exists to avoid.
      3. Otherwise → skip with a warning.

    used_fingerprints, if given, is updated in place with every signature
    assigned here -- pass the same set across multiple directories (e.g.
    primary + spare) so accounts in different directories don't collide either.

    load_failures, if given, is appended in place with {"file": ..., "reason": ...}
    for every session skipped or errored -- lets a caller report back to the
    operator exactly what didn't load and why, instead of only a backend log line.

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
    used_fingerprints = used_fingerprints if used_fingerprints is not None else set()

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
                used_fingerprints.add((account.device_model, account.app_version))
            elif api_id and api_hash:
                phone_raw = Path(base_text).name
                phone = phone_raw if phone_raw.startswith("+") else f"+{phone_raw}"
                if fingerprint_catalog is not None:
                    fingerprint = fingerprint_catalog.choose(avoid=used_fingerprints)
                    used_fingerprints.add(fingerprint.signature())
                    _write_fingerprint_sidecar(
                        base_text, api_id=api_id, api_hash=api_hash, phone=phone, fingerprint=fingerprint
                    )
                    account = AccountConfig(
                        api_id=api_id,
                        api_hash=api_hash,
                        phone=phone,
                        proxy=proxy,
                        device_model=fingerprint.device,
                        system_version=f"SDK {fingerprint.sdk}",
                        app_version=fingerprint.app_version,
                        lang_code=fingerprint.lang_code,
                        system_lang_code=fingerprint.system_lang_code,
                        lang_pack=fingerprint.lang_pack,
                        sdk=fingerprint.sdk,
                        tz_offset=fingerprint.tz_offset,
                        perf_cat=fingerprint.perf_cat,
                        session_dir=str(dir_path),
                    )
                else:
                    logger.warning(
                        "No fingerprint catalog configured -- %s will fall back to "
                        "AccountConfig's default device signature, identical to every "
                        "other bare-imported account with no catalog.",
                        sf.name,
                    )
                    account = AccountConfig(
                        api_id=api_id,
                        api_hash=api_hash,
                        phone=phone,
                        proxy=proxy,
                        session_dir=str(dir_path),
                    )
            else:
                reason = "no .json companion and no default api_id/api_hash configured"
                logger.warning("Skipping %s: %s.", sf.name, reason)
                if load_failures is not None:
                    load_failures.append({"file": sf.name, "reason": reason})
                continue

            accounts.append(account)
            logger.debug("Loaded %s → proxy=%s", account.phone, proxy)

        except Exception as exc:
            logger.error("Failed to load %s: %s", sf.name, exc)
            if load_failures is not None:
                load_failures.append({"file": sf.name, "reason": str(exc)})

    logger.info("Loaded %d accounts from '%s'.", len(accounts), directory)
    return accounts
