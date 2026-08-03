"""
tg_pool/tdata_converter.py — Bidirectional TData ↔ Telethon Session Converter.

Поддерживает два направления:
  TData → Telethon .session   (import: Telegram Desktop → Telethon)
  Telethon .session → TData   (export: Telethon → Telegram Desktop)

Возможности:
  find_tdata_folders()    — рекурсивный поиск всех валидных папок tdata
  TDataConverter          — основной класс конвертации
    .tdata_to_session()   — конвертирует одну папку tdata в .session файл
    .session_to_tdata()   — конвертирует .session + .json в папку tdata
    .convert_batch_tdata()    — пакетная конвертация tdata → session (с джиттером)
    .convert_batch_sessions() — пакетная конвертация session → tdata (с джиттером)

Безопасность:
  При пакетной обработке между аккаунтами вставляется случайная задержка
  3–7 секунд для исключения спам-блокировок.

Зависимость: opentele>=1.15.2
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from opentele.api import UseCurrentSession
from opentele.td import Account, TDesktop
from opentele.tl import TelegramClient as OpenteleClient
from opentele import exception as ote_exc
from telethon.errors import FloodWaitError

from tg_pool.proxy.opentele_compat import install_opentele_compat

try:
    from telethon.errors import (
        PasswordHashInvalidError as TelethonPasswordHashInvalidError,
        SessionPasswordNeededError,
    )
except ImportError:  # pragma: no cover
    TelethonPasswordHashInvalidError = Exception  # type: ignore[assignment,misc]
    SessionPasswordNeededError = Exception  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

install_opentele_compat()

_JITTER_MIN = 3.0
_JITTER_MAX = 7.0
_MAX_BATCH = 50

# Require a 16-character hash with A-F so phone-number folders are not mistaken for it.
_HEX_DIR_RE = re.compile(r"^(?=.*[A-F])[0-9A-F]{16}$")


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class TwoFactorAuthRequiredError(RuntimeError):
    """2FA password is required but was not provided."""


class PasswordHashInvalidError(RuntimeError):
    """The provided 2FA password is incorrect."""


class TDataInvalidError(ValueError):
    """The tdata folder is missing, incomplete, or corrupted."""


# opentele's own exceptions (OpenTeleException) subclass BaseException directly,
# not Exception -- confirmed via OpenTeleException.__mro__. A bare `except
# Exception` silently lets them through uncaught, contradicting every method
# below's documented "raises TDataInvalidError" / "never raises" contract.
# Every catch-all meant to wrap "anything unexpected from opentele" needs this.
_OPENTELE_ERRORS = (Exception, ote_exc.OpenTeleException)


# ---------------------------------------------------------------------------
# ConversionResult / TDataFingerprint
# ---------------------------------------------------------------------------

@dataclass
class ConversionResult:
    """
    Result of a single account conversion attempt.

    api_id/api_hash/device_model/system_version/app_version (tdata → session
    direction only) carry the API identity the session's auth key was
    actually created under -- see TDataFingerprint for why this matters.
    """
    source: str
    output: Optional[str] = None
    success: bool = False
    error: str = ""
    api_id: Optional[int] = None
    api_hash: Optional[str] = None
    device_model: Optional[str] = None
    system_version: Optional[str] = None
    app_version: Optional[str] = None

    def __str__(self) -> str:
        if self.success:
            return f"OK   {self.source} → {self.output}"
        return f"FAIL {self.source}: {self.error}"

    def __repr__(self) -> str:
        # api_hash omitted -- same convention as config.py's ProxyConfig/
        # AccountConfig -- so it never leaks via %r, an f-string {!r}, or
        # logging a list of results (list repr calls repr() per element).
        return (
            f"ConversionResult(source={self.source!r}, output={self.output!r}, "
            f"success={self.success}, error={self.error!r}, api_id={self.api_id})"
        )


@dataclass(frozen=True)
class TDataFingerprint:
    """
    The API identity (api_id/api_hash/device fingerprint) actually used to
    create a converted session's auth key.

    opentele's own docs warn against mixing API layers on one session ("you
    might be banned") -- so callers building an AccountConfig from a
    tdata-converted session should reuse these fields as the account's
    permanent identity, not arbitrary/default device strings.
    """
    api_id: int
    api_hash: str
    device_model: str
    system_version: str
    app_version: str

    def __repr__(self) -> str:
        return (
            f"TDataFingerprint(api_id={self.api_id}, "
            f"device_model={self.device_model!r}, system_version={self.system_version!r}, "
            f"app_version={self.app_version!r})"
        )


@dataclass(frozen=True)
class TDataSessionResult:
    """Result of one successful tdata account -> Telethon session conversion."""
    session_path: Path
    fingerprint: TDataFingerprint
    phone: str = ""


# ---------------------------------------------------------------------------
# tdata validity detection
# ---------------------------------------------------------------------------

def _is_valid_tdata(path: Path) -> bool:
    """
    Returns True when path looks like a valid Telegram Desktop tdata folder.

    Heuristics (first match wins):
      1. Contains 'key_datas' file — primary indicator present in all TD versions.
      2. Contains a 16-char uppercase-hex subdirectory with A-F — user data pattern.
    """
    if (path / "key_datas").exists():
        return True
    try:
        for entry in path.iterdir():
            if entry.is_dir() and _HEX_DIR_RE.match(entry.name.upper()):
                return True
    except PermissionError:
        logger.warning("Permission denied reading %s while probing for tdata — skipped.", path)
    return False


def find_tdata_folders(base_path: str) -> List[str]:
    """
    Recursively search for valid tdata folders under base_path.

    Folder names are irrelevant: exports are commonly named after a phone
    number or account ID. Any directory accepted by _is_valid_tdata() is
    included, including base_path itself.

    Returns a list of absolute string paths, sorted for deterministic order.
    """
    root = Path(base_path)
    if not root.exists():
        raise FileNotFoundError(f"Base path not found: {base_path}")

    found: List[str] = []
    for dirpath, dirnames, _ in os.walk(root):
        current = Path(dirpath)
        # A valid root owns everything below it; don't discover cache/account
        # subdirectories as additional tdata inputs.
        if _is_valid_tdata(current):
            found.append(str(current.resolve()))
            dirnames.clear()

    return sorted(found)


def _session_stem_for_tdata(path: Path) -> str:
    """Derive an output name for both classic */tdata and named tdata roots."""
    if path.name.lower() == "tdata":
        return path.parent.stem or "session"
    return path.stem or "session"


# ---------------------------------------------------------------------------
# TDataConverter
# ---------------------------------------------------------------------------

class TDataConverter:
    """
    Bidirectional converter between Telegram Desktop (tdata) and Telethon sessions.

    Both conversion methods are async and must be awaited.
    Batch methods enforce jitter delays between accounts to avoid flood triggers.
    """

    # ------------------------------------------------------------------
    # TData → Telethon .session
    # ------------------------------------------------------------------

    @staticmethod
    async def _fetch_phone(client, fallback: str) -> str:
        """
        Best-effort phone lookup on a freshly-converted client.

        Never raises -- a get_me() hiccup shouldn't fail an otherwise
        successful conversion; the caller just falls back to a name derived
        from the tdata path instead of the real phone number.
        """
        try:
            me = await client.get_me()
            if me is not None and getattr(me, "phone", None):
                return f"+{me.phone}"
        except Exception:
            logger.debug("get_me() failed while deriving phone number", exc_info=True)
        return fallback

    @staticmethod
    def _fingerprint_from_api(api) -> TDataFingerprint:
        return TDataFingerprint(
            api_id=api.api_id,
            api_hash=api.api_hash,
            device_model=api.device_model,
            system_version=api.system_version,
            app_version=api.app_version,
        )

    async def _load_tdesktop(self, tdata_path: str) -> TDesktop:
        """
        Validate + load a tdata folder off the event loop.

        TDesktop(path) parses/decrypts tdata on disk synchronously (opentele
        has no async constructor) -- run in an executor so a large tdata
        folder can't stall the whole event loop while loading.
        """
        path = Path(tdata_path)
        if not path.exists():
            raise TDataInvalidError(f"tdata path not found: {tdata_path}")
        if not _is_valid_tdata(path):
            raise TDataInvalidError(
                f"Not a valid tdata folder (missing key_datas or hex subfolder): {tdata_path}"
            )

        logger.info("[tdata] Loading tdata: %s", tdata_path)
        loop = asyncio.get_running_loop()
        try:
            tdesktop = await loop.run_in_executor(None, TDesktop, str(path))
        except _OPENTELE_ERRORS as exc:
            raise TDataInvalidError(
                f"Failed to load tdata from '{tdata_path}': {exc}"
            ) from exc

        # isLoaded is a method, not a property -- `if not tdesktop.isLoaded:`
        # (no call) always evaluated the bound-method object's truthiness,
        # which is never falsy, making this check permanently dead in
        # production (only "worked" in tests because the mock set isLoaded
        # to a plain bool instead of a callable).
        if not tdesktop.isLoaded():
            raise TDataInvalidError(
                f"TDesktop could not load accounts from '{tdata_path}'. "
                "The folder may be corrupted or belong to a different OS user."
            )
        return tdesktop

    async def list_tdata_accounts(self, tdata_path: str) -> List[Account]:
        """
        Return every account found in a tdata folder.

        Telegram Desktop itself caps a tdata folder at 3 accounts -- this is
        opentele's real limit, unrelated to _MAX_BATCH (the number of tdata
        *folders* convert_batch_tdata() processes per call).
        """
        tdesktop = await self._load_tdesktop(tdata_path)
        return list(tdesktop.accounts)

    async def tdata_to_session(
        self,
        tdata_path: str,
        output_dir: str,
        password: Optional[str] = None,
    ) -> TDataSessionResult:
        """
        Convert a Telegram Desktop tdata folder's MAIN account to a Telethon
        .session file. If the folder holds more than one account, the others
        are logged and skipped — use tdata_to_sessions_all() (or
        convert_batch_tdata(..., all_accounts=True)) to convert every account.

        Args:
          tdata_path  — path to the tdata folder.
          output_dir  — directory where the .session file will be written.
          password    — cloud password (2FA) if the account is protected.

        Returns a TDataSessionResult (session path + the API fingerprint the
        session's auth key was created under — reuse it for AccountConfig
        rather than arbitrary device strings).

        Raises:
          TDataInvalidError          — folder missing, invalid, or load error.
          TwoFactorAuthRequiredError — 2FA needed but no password given.
          PasswordHashInvalidError   — 2FA password is wrong.
        """
        path = Path(tdata_path)
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        session_name = _session_stem_for_tdata(path)
        session_path = out_dir / session_name

        tdesktop = await self._load_tdesktop(tdata_path)
        if tdesktop.accountsCount > 1:
            logger.warning(
                "[tdata_to_session] %s contains %d accounts — only the main "
                "account is converted here. Use tdata_to_sessions_all() to "
                "convert all of them.", tdata_path, tdesktop.accountsCount,
            )

        logger.info("[tdata_to_session] Converting → %s", session_path)
        fingerprint = self._fingerprint_from_api(tdesktop.api)

        try:
            client = await tdesktop.ToTelethon(
                session=str(session_path),
                flag=UseCurrentSession,
                password=password,
            )
        except (ote_exc.NoPasswordProvided, SessionPasswordNeededError) as exc:
            raise TwoFactorAuthRequiredError(
                f"Account in '{tdata_path}' requires a 2FA cloud password. "
                "Pass it via the `password` argument."
            ) from exc
        except (ote_exc.PasswordIncorrect, TelethonPasswordHashInvalidError) as exc:
            raise PasswordHashInvalidError(
                f"The 2FA password provided for '{tdata_path}' is incorrect."
            ) from exc
        except FloodWaitError:
            # Not a data problem -- the caller needs to back off and retry,
            # not treat this account as permanently invalid.
            raise
        except _OPENTELE_ERRORS as exc:
            raise TDataInvalidError(
                f"Conversion failed for '{tdata_path}': {exc}"
            ) from exc

        phone = await self._fetch_phone(client, fallback=session_name)

        try:
            await client.disconnect()
        except Exception:
            logger.warning(
                "[tdata_to_session] client.disconnect() failed for %s", tdata_path, exc_info=True
            )

        logger.info("[tdata_to_session] ✓ %s → %s.session", tdata_path, session_path)
        return TDataSessionResult(session_path=session_path, fingerprint=fingerprint, phone=phone)

    async def tdata_to_sessions_all(
        self,
        tdata_path: str,
        output_dir: str,
        password: Optional[str] = None,
    ) -> List[TDataSessionResult]:
        """
        Convert EVERY account in a tdata folder (opentele/Telegram Desktop
        caps this at 3), instead of only the main one. Each account gets its
        own session file: the single-account case keeps the plain folder-stem
        name; multi-account folders get an "_acc{N}" suffix per session.
        """
        path = Path(tdata_path)
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        session_stem = _session_stem_for_tdata(path)

        tdesktop = await self._load_tdesktop(tdata_path)
        accounts = list(tdesktop.accounts)
        logger.info(
            "[tdata_to_sessions_all] %d account(s) found in %s", len(accounts), tdata_path
        )

        results: List[TDataSessionResult] = []
        for i, account in enumerate(accounts):
            session_path = out_dir / (
                session_stem if len(accounts) == 1 else f"{session_stem}_acc{i}"
            )
            fingerprint = self._fingerprint_from_api(account.api)

            try:
                client = await account.ToTelethon(
                    session=str(session_path),
                    flag=UseCurrentSession,
                    password=password,
                )
            except (ote_exc.NoPasswordProvided, SessionPasswordNeededError) as exc:
                raise TwoFactorAuthRequiredError(
                    f"Account {i} in '{tdata_path}' requires a 2FA cloud password."
                ) from exc
            except (ote_exc.PasswordIncorrect, TelethonPasswordHashInvalidError) as exc:
                raise PasswordHashInvalidError(
                    f"The 2FA password provided for account {i} in '{tdata_path}' is incorrect."
                ) from exc
            except FloodWaitError:
                raise
            except _OPENTELE_ERRORS as exc:
                raise TDataInvalidError(
                    f"Conversion failed for account {i} in '{tdata_path}': {exc}"
                ) from exc

            phone = await self._fetch_phone(client, fallback=f"{session_stem}_{i}")

            try:
                await client.disconnect()
            except Exception:
                logger.warning(
                    "[tdata_to_sessions_all] disconnect() failed for account %d in %s",
                    i, tdata_path, exc_info=True,
                )

            results.append(
                TDataSessionResult(session_path=session_path, fingerprint=fingerprint, phone=phone)
            )

        logger.info(
            "[tdata_to_sessions_all] ✓ %s → %d session(s)", tdata_path, len(results)
        )
        return results

    # ------------------------------------------------------------------
    # Telethon .session → TData
    # ------------------------------------------------------------------

    async def session_to_tdata(
        self,
        session_path: str,
        json_path: str,
        output_tdata_path: str,
    ) -> Path:
        """
        Convert a Telethon .session file to a Telegram Desktop tdata folder.

        The JSON sidecar must contain 'app_id' (or 'api_id') and 'app_hash'
        (or 'api_hash') fields to authenticate the Telethon client.

        Args:
          session_path      — path to the .session file (with or without extension).
          json_path         — path to the JSON credentials file.
          output_tdata_path — directory where the tdata folder will be written.

        Returns the Path of the created tdata folder.

        Raises:
          FileNotFoundError  — session or JSON file missing.
          TDataInvalidError  — session unauthorised or conversion failed.
        """
        sp = Path(session_path)
        # Normalise: remove .session suffix so telethon finds the file correctly
        sp_for_telethon = sp.with_suffix("") if sp.suffix == ".session" else sp

        actual_session_file = sp_for_telethon.with_suffix(".session")
        if not actual_session_file.exists():
            raise FileNotFoundError(f"Session file not found: {actual_session_file}")

        jp = Path(json_path)
        if not jp.exists():
            raise FileNotFoundError(f"JSON credentials file not found: {json_path}")

        with jp.open(encoding="utf-8") as fh:
            data: Dict = json.load(fh)

        # Accept both naming conventions (app_id / api_id)
        raw_id = data.get("app_id") or data.get("api_id")
        raw_hash = data.get("app_hash") or data.get("api_hash")
        if not raw_id or not raw_hash:
            raise TDataInvalidError(
                f"JSON '{json_path}' must contain 'app_id'/'api_id' and 'app_hash'/'api_hash'."
            )

        api_id = int(raw_id)
        api_hash = str(raw_hash)

        out_path = Path(output_tdata_path)
        out_path.mkdir(parents=True, exist_ok=True)

        logger.info("[session_to_tdata] Connecting session: %s", sp_for_telethon)

        client = OpenteleClient(str(sp_for_telethon), api_id, api_hash)
        try:
            await client.connect()

            if not await client.is_user_authorized():
                raise TDataInvalidError(
                    f"Session '{session_path}' is not authorised. "
                    "Re-authenticate before exporting to tdata."
                )

            me = await client.get_me()
            phone = f"+{me.phone}" if me and me.phone else sp.stem
            logger.info(
                "[session_to_tdata] Authorised as %s. Exporting to tdata…", phone
            )

            tdesktop = await client.ToTDesktop(flag=UseCurrentSession)
            # SaveTData is a synchronous disk write (opentele has no async
            # variant) -- run in an executor so it can't stall the event loop.
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, tdesktop.SaveTData, str(out_path))

        except TDataInvalidError:
            raise
        except FloodWaitError:
            raise
        except _OPENTELE_ERRORS as exc:
            raise TDataInvalidError(
                f"Failed to convert session '{session_path}' to tdata: {exc}"
            ) from exc
        finally:
            try:
                await client.disconnect()
            except Exception:
                logger.warning(
                    "[session_to_tdata] client.disconnect() failed for %s",
                    session_path, exc_info=True,
                )

        logger.info("[session_to_tdata] ✓ %s → %s", session_path, out_path)
        return out_path

    # ------------------------------------------------------------------
    # Batch: TData → Sessions
    # ------------------------------------------------------------------

    @staticmethod
    def _result_from_session(source: str, session_result: TDataSessionResult) -> ConversionResult:
        fp = session_result.fingerprint
        return ConversionResult(
            source=source,
            output=str(session_result.session_path),
            success=True,
            api_id=fp.api_id,
            api_hash=fp.api_hash,
            device_model=fp.device_model,
            system_version=fp.system_version,
            app_version=fp.app_version,
        )

    async def convert_batch_tdata(
        self,
        tdata_paths: List[str],
        output_dir: str,
        passwords: Optional[Dict[str, str]] = None,
        *,
        all_accounts: bool = False,
    ) -> List[ConversionResult]:
        """
        Convert up to 50 tdata folders to Telethon sessions with anti-flood jitter.

        Args:
          tdata_paths  — list of tdata folder paths.
          output_dir   — directory to write .session files into.
          passwords    — optional dict mapping tdata_path → 2FA password.
          all_accounts — if True, convert every account found in each tdata
                        folder (opentele/Telegram Desktop caps this at 3) via
                        tdata_to_sessions_all(), instead of only the main one.
                        A single input path can then yield multiple results.

        Returns a list of ConversionResult (one per input path, or one per
        account within a path when all_accounts=True). Never raises —
        failures are captured in ConversionResult.error.
        """
        paths = tdata_paths[:_MAX_BATCH]
        if len(tdata_paths) > _MAX_BATCH:
            logger.warning(
                "Batch size %d exceeds limit %d — truncated.", len(tdata_paths), _MAX_BATCH
            )

        passwords = passwords or {}
        results: List[ConversionResult] = []

        for i, tdata_path in enumerate(paths):
            if i > 0:
                jitter = random.uniform(_JITTER_MIN, _JITTER_MAX)
                logger.info(
                    "Anti-flood jitter: %.1fs before account %d/%d",
                    jitter, i + 1, len(paths),
                )
                await asyncio.sleep(jitter)

            pwd = passwords.get(tdata_path)
            logger.info("[%d/%d] tdata → session: %s", i + 1, len(paths), tdata_path)

            try:
                if all_accounts:
                    session_results = await self.tdata_to_sessions_all(tdata_path, output_dir, pwd)
                    results.extend(
                        self._result_from_session(tdata_path, sr) for sr in session_results
                    )
                else:
                    session_result = await self.tdata_to_session(tdata_path, output_dir, pwd)
                    results.append(self._result_from_session(tdata_path, session_result))
            except _OPENTELE_ERRORS as exc:
                logger.error(
                    "[%d/%d] FAILED %s: %s", i + 1, len(paths), tdata_path, exc
                )
                results.append(ConversionResult(
                    source=tdata_path,
                    success=False,
                    error=str(exc),
                ))

        ok = sum(r.success for r in results)
        logger.info("Batch tdata→session complete: %d/%d succeeded.", ok, len(results))
        return results

    # ------------------------------------------------------------------
    # Batch: Sessions → TData
    # ------------------------------------------------------------------

    async def convert_batch_sessions(
        self,
        session_configs: List[Tuple[str, str, str]],
        output_base_dir: str,
    ) -> List[ConversionResult]:
        """
        Convert up to 50 Telethon sessions to tdata folders with anti-flood jitter.

        Args:
          session_configs — list of (session_path, json_path, output_tdata_subdir).
                            output_tdata_subdir is appended to output_base_dir.
          output_base_dir — root directory for all output tdata folders.

        Returns a list of ConversionResult, one per input tuple.
        """
        configs = session_configs[:_MAX_BATCH]
        if len(session_configs) > _MAX_BATCH:
            logger.warning(
                "Batch size %d exceeds limit %d — truncated.", len(session_configs), _MAX_BATCH
            )

        base = Path(output_base_dir)
        results: List[ConversionResult] = []

        for i, (session_path, json_path, subdir) in enumerate(configs):
            if i > 0:
                jitter = random.uniform(_JITTER_MIN, _JITTER_MAX)
                logger.info(
                    "Anti-flood jitter: %.1fs before account %d/%d",
                    jitter, i + 1, len(configs),
                )
                await asyncio.sleep(jitter)

            out_tdata = str(base / subdir)
            logger.info(
                "[%d/%d] session → tdata: %s → %s",
                i + 1, len(configs), session_path, out_tdata,
            )

            try:
                out_path = await self.session_to_tdata(session_path, json_path, out_tdata)
                results.append(ConversionResult(
                    source=session_path,
                    output=str(out_path),
                    success=True,
                ))
            except _OPENTELE_ERRORS as exc:
                logger.error(
                    "[%d/%d] FAILED %s: %s", i + 1, len(configs), session_path, exc
                )
                results.append(ConversionResult(
                    source=session_path,
                    success=False,
                    error=str(exc),
                ))

        ok = sum(r.success for r in results)
        logger.info("Batch session→tdata complete: %d/%d succeeded.", ok, len(results))
        return results
