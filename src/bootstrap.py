"""
src/bootstrap.py — Shared env-driven bootstrap for every feature entry point.

Every mode (messaging campaign, parsing, account check, proxy check, tdata
conversion) needs the same handful of things: numeric env parsing that names
the offending variable, logging setup, graceful-shutdown signal handling,
loading accounts/proxies from .env or a directory, and the shared DB session
factory / account repository / session-encryption key. Extracted here instead
of duplicated per feature module (src/features/*.py) or left trapped in
main.py as it was before the mode split.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import List, Tuple

from src.config import AccountConfig, ProxyConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Numeric env parsing with a clear "which variable" error
# ---------------------------------------------------------------------------

def parse_int(raw: str, var_name: str) -> int:
    """Parse an already-fetched env value as an int, naming the variable in the error."""
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{var_name} must be an integer, got {raw!r}") from None


def parse_float(raw: str, var_name: str) -> float:
    """Parse an already-fetched env value as a float, naming the variable in the error."""
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"{var_name} must be a number, got {raw!r}") from None


def env_int(var_name: str, default: str) -> int:
    """Read var_name as an int, raising a clear error naming the variable on a bad value."""
    return parse_int(os.getenv(var_name, default), var_name)


def env_float(var_name: str, default: str) -> float:
    """Read var_name as a float, raising a clear error naming the variable on a bad value."""
    return parse_float(os.getenv(var_name, default), var_name)


# ---------------------------------------------------------------------------
# Logging / crypto backend
# ---------------------------------------------------------------------------

def log_crypto_backend(logger: logging.Logger) -> None:
    """Log whether Telethon is using the C-accelerated cryptg backend."""
    try:
        import cryptg  # noqa: F401
        logger.info("MTProto crypto: cryptg (C-accelerated) активен.")
    except ImportError:
        logger.warning(
            "MTProto crypto: cryptg не установлен — используется медленный "
            "чистый Python. Установи cryptg для ускорения (см. requirements.txt)."
        )


def configure_logging(debug: bool = False, log_dir: str = "") -> None:
    """
    log_dir, if given, adds a rotating file handler (backend.log, 5x5MB) on
    top of the stdout stream -- lets the WPF launcher point this at its
    managed Data\\Logs folder without the caller needing to know the format.
    """
    level = logging.DEBUG if debug else logging.INFO
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_dir:
        from logging.handlers import RotatingFileHandler
        os.makedirs(log_dir, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                os.path.join(log_dir, "backend.log"),
                maxBytes=5 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
        )

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)-30s %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )
    logging.getLogger("telethon").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

def setup_signal_handlers(shutdown_event, loop) -> None:
    """
    Registers OS signal handlers for graceful shutdown.

    Linux/macOS: loop.add_signal_handler() is async-safe and triggers
                 directly from the event loop.
    Windows:     signal.signal() is used since add_signal_handler() is not
                 supported.  The handler uses loop.call_soon_threadsafe() to
                 safely set the asyncio.Event from the signal thread.
    """
    handler_logger = logging.getLogger("main")

    def _request_shutdown() -> None:
        if not shutdown_event.is_set():
            handler_logger.warning(
                "Shutdown requested. Finishing in-flight sends and draining queue..."
            )
            loop.call_soon_threadsafe(shutdown_event.set)

    if sys.platform != "win32":
        import signal
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _request_shutdown)
            except (NotImplementedError, RuntimeError):
                # Fallback for environments that don't support add_signal_handler
                signal.signal(sig, lambda s, f: _request_shutdown())
    else:
        import signal
        signal.signal(signal.SIGINT, lambda s, f: _request_shutdown())
        # SIGTERM on Windows is an alias for SIGINT in CPython
        try:
            signal.signal(signal.SIGTERM, lambda s, f: _request_shutdown())
        except (OSError, ValueError):
            pass


# ---------------------------------------------------------------------------
# Accounts / proxies
# ---------------------------------------------------------------------------

def load_proxies_from_env(max_slots: int = 19) -> List[ProxyConfig]:
    """
    Reads PROXY_HOST_i/PROXY_PORT_i/PROXY_USER_i/PROXY_PASS_i (i=1..max_slots)
    into a flat list, stopping at the first gap. Used both to round-robin
    assign proxies to accounts (load_accounts()) and standalone by the proxy
    checker, which needs the raw list rather than proxies already bound to
    accounts.
    """
    proxies: List[ProxyConfig] = []
    for i in range(1, max_slots + 1):
        host = os.getenv(f"PROXY_HOST_{i}")
        port_str = os.getenv(f"PROXY_PORT_{i}")
        if not host or not port_str:
            break
        proxies.append(ProxyConfig(
            host=host,
            port=parse_int(port_str, f"PROXY_PORT_{i}"),
            username=os.getenv(f"PROXY_USER_{i}") or None,
            password=os.getenv(f"PROXY_PASS_{i}") or None,
        ))
    return proxies


def _load_proxy_from_env(suffix: str):
    host = os.getenv(f"PROXY_HOST_{suffix}")
    port_str = os.getenv(f"PROXY_PORT_{suffix}")
    if not host or not port_str:
        return None
    return ProxyConfig(
        host=host,
        port=parse_int(port_str, f"PROXY_PORT_{suffix}"),
        username=os.getenv(f"PROXY_USER_{suffix}") or None,
        password=os.getenv(f"PROXY_PASS_{suffix}") or None,
    )


def _load_accounts_from_env() -> List[AccountConfig]:
    accounts = []
    for i in range(1, 50):
        api_id_str = os.getenv(f"TG_API_ID_{i}")
        api_hash = os.getenv(f"TG_API_HASH_{i}")
        phone = os.getenv(f"TG_PHONE_{i}")
        if not api_id_str or not api_hash or not phone:
            break
        accounts.append(AccountConfig(
            api_id=parse_int(api_id_str, f"TG_API_ID_{i}"),
            api_hash=api_hash,
            phone=phone,
            proxy=_load_proxy_from_env(str(i)),
            device_model=os.getenv(f"TG_DEVICE_{i}", "Samsung Galaxy S23"),
            system_version=os.getenv(f"TG_SYSVER_{i}", "Android 14"),
            session_dir=os.getenv("SESSION_DIR", "sessions"),
        ))
    return accounts


def load_accounts() -> Tuple[List[AccountConfig], List[AccountConfig]]:
    from src.accounts.account_loader import load_accounts_from_directory

    proxies_raw = load_proxies_from_env()

    accounts_dir = os.getenv("ACCOUNTS_DIR", "")
    if accounts_dir and os.path.isdir(accounts_dir):
        primary = load_accounts_from_directory(
            directory=accounts_dir,
            api_id=env_int("TG_API_ID_DEFAULT", "0"),
            api_hash=os.getenv("TG_API_HASH_DEFAULT", ""),
            proxies=proxies_raw or None,
            accounts_per_proxy=env_int("ACCOUNTS_PER_PROXY", "1"),
        )
    else:
        primary = _load_accounts_from_env()

    spare_dir = os.getenv("SPARE_ACCOUNTS_DIR", "")
    spare = []
    if spare_dir and os.path.isdir(spare_dir):
        spare = load_accounts_from_directory(
            directory=spare_dir,
            api_id=env_int("TG_API_ID_DEFAULT", "0"),
            api_hash=os.getenv("TG_API_HASH_DEFAULT", ""),
            proxies=proxies_raw or None,
            accounts_per_proxy=env_int("ACCOUNTS_PER_PROXY", "1"),
        )

    return primary, spare


async def load_tdata_accounts() -> List[AccountConfig]:
    """
    Convert every tdata folder found under TDATA_ACCOUNTS_DIR into AccountConfig,
    via load_from_tdata() (src/accounts/account_loader.py -> TDataConverter).

    Optional TDATA_PASSWORDS_FILE: a JSON file mapping tdata folder path (as
    returned by find_tdata_folders()) -> 2FA cloud password, for accounts
    protected by two-step verification. A folder with no matching entry is
    converted with password=None -- fine unless that specific account has 2FA.
    """
    tdata_dir = os.getenv("TDATA_ACCOUNTS_DIR", "")
    if not tdata_dir or not os.path.isdir(tdata_dir):
        return []

    import json
    from src.accounts.account_loader import load_from_tdata
    from src.proxy.tdata_converter import find_tdata_folders

    passwords: dict = {}
    passwords_file = os.getenv("TDATA_PASSWORDS_FILE", "")
    if passwords_file and os.path.isfile(passwords_file):
        with open(passwords_file, encoding="utf-8") as fh:
            passwords = json.load(fh)

    session_dir = os.getenv("SESSION_DIR", "sessions")
    accounts = []
    for tdata_path in find_tdata_folders(tdata_dir):
        try:
            account = await load_from_tdata(
                tdata_path, session_dir=session_dir, password=passwords.get(tdata_path),
            )
            accounts.append(account)
        except Exception as exc:
            logger.error("Failed to convert tdata folder %s: %s", tdata_path, exc)

    logger.info("Converted %d account(s) from tdata under %s.", len(accounts), tdata_dir)
    return accounts


# ---------------------------------------------------------------------------
# DB / repository
# ---------------------------------------------------------------------------

def build_db_session_factory():
    """Shared session factory so account + campaign repositories reuse one engine."""
    database_url = os.getenv("DATABASE_URL", "") or os.getenv("ACCOUNT_DATABASE_URL", "")
    if not database_url:
        return None
    from src.db.engine import build_session_factory
    return build_session_factory(database_url, echo=os.getenv("DATABASE_ECHO", "") == "1")


def build_proxy_db_session_factory(fallback_session_factory=None):
    """Use a dedicated proxy database when configured, otherwise share the main DB."""
    database_url = os.getenv("PROXY_DATABASE_URL", "")
    if database_url:
        from src.db.engine import build_session_factory
        return build_session_factory(database_url)
    return fallback_session_factory


def build_account_repository(session_factory=None):
    session_factory = session_factory if session_factory is not None else build_db_session_factory()
    if session_factory is None:
        return None
    from src.db.repository import AccountRepository
    return AccountRepository(session_factory)


# ---------------------------------------------------------------------------
# Session encryption / health checker
# ---------------------------------------------------------------------------

def build_session_encryption_key(logger: logging.Logger):
    if os.getenv("SESSION_ENCRYPTION_ENABLED", "0").lower() not in ("1", "true", "yes"):
        return None
    from src.accounts.session_crypto import load_key_from_env
    try:
        return load_key_from_env()
    except ValueError as exc:
        logger.error(str(exc))
        sys.exit(1)


def build_health_checker(policy, event_bus):
    from src.accounts.health_checker import HealthChecker
    concurrency = env_int("HEALTH_CONCURRENCY", "5")
    account_timeout_sec = env_float("HEALTH_ACCOUNT_TIMEOUT_SEC", "90")
    return HealthChecker(
        policy=policy,
        concurrency=concurrency,
        event_bus=event_bus,
        account_timeout_sec=account_timeout_sec,
    )


# ---------------------------------------------------------------------------
# Redis client — shared by messaging (rate limiting/warm-up) and parsing
# (dedup/anti-flood)
# ---------------------------------------------------------------------------

def build_redis_client():
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        return None
    try:
        import redis.asyncio as aioredis
        return aioredis.from_url(redis_url, decode_responses=True)
    except ImportError:
        logger.warning("redis не установлен.")
        return None
