"""
src/connection_manager.py — Proxy & Connection Manager.

Реализует:
  1. ClientFactory  — строит TelegramClient с fingerprint и прокси.
  2. ClientPool     — управляет жизненным циклом пула клиентов:
                      initialize() / close_all() / get_worker_pairs().

Архитектурные решения:
  - ClientPool хранит словарь phone → client, что гарантирует
    уникальность: один телефон = один активный клиент.
  - initialize() использует asyncio.gather для параллельного
    подключения всех аккаунтов. Упавший аккаунт не блокирует остальных.
  - close_all() вызывает disconnect() параллельно через gather.
  - Метод close_all() идемпотентен: повторный вызов безопасен.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Dict, List, Optional, Tuple

from telethon import TelegramClient
from telethon.tl import types

from src.config import AccountConfig, TimingPolicy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ClientFactory: единственное место создания TelegramClient
# ---------------------------------------------------------------------------

class ClientFactory:
    """
    Фабрика TelegramClient.

    Почему класс со static method вместо обычной функции?
      1. Удобнее мокировать в тестах: mock.patch('src.accounts.connection_manager.ClientFactory.build').
      2. Открыт для расширения: можно добавить MTProto-прокси,
         кастомный тип подключения (HTTP вместо TCP) без изменения вызывающего кода.
    """

    @staticmethod
    def build(account: AccountConfig) -> TelegramClient:
        """
        Создаёт TelegramClient с изолированными параметрами.

        Proxy передаётся как кортеж PySocks-формата.
        Параметры fingerprint задаются только в конструкторе —
        Telethon не позволяет их менять после инициализации.

        connection_retries и retry_delay — встроенный retry
        транспортного уровня (не путать с retry при FloodWait).
        """
        # Гарантируем существование директории сессий
        session_dir = os.path.dirname(account.session_path)
        if session_dir:
            os.makedirs(session_dir, exist_ok=True)

        proxy: Optional[tuple] = None
        if account.proxy is not None:
            proxy = account.proxy.as_tuple()
            logger.debug("Worker %s → proxy %s", account.phone, account.proxy)

        client = TelegramClient(
            session=account.session_path,
            api_id=account.api_id,
            api_hash=account.api_hash,
            proxy=proxy,
            # --- Device fingerprint (изоляция между воркерами) ---
            device_model=account.device_model,
            system_version=account.system_version,
            app_version=account.app_version,
            lang_code=account.lang_code,
            system_lang_code=account.system_lang_code,
            # --- Транспортная resilience ---
            connection_retries=3,
            retry_delay=2,
            auto_reconnect=True,
            request_retries=5,
        )
        # Telethon deliberately leaves lang_pack empty for third-party clients.
        # Imported Android fingerprints need the complete InitConnection tuple,
        # including the JSON parameters used by the official Android client.
        client._init_request.lang_pack = account.lang_pack
        client._init_request.params = types.JsonObject(
            [
                types.JsonObjectValue(
                    "tz_offset", types.JsonNumber(float(account.tz_offset))
                ),
                types.JsonObjectValue(
                    "perf_cat", types.JsonNumber(float(account.perf_cat))
                ),
            ]
        )
        return client


# ---------------------------------------------------------------------------
# ClientPool: управление жизненным циклом пула
# ---------------------------------------------------------------------------

class ClientPool:
    """
    Пул асинхронных Telegram-клиентов.

    Паттерн: Resource Pool (GoF).
    Клиенты создаются один раз в initialize(), переиспользуются
    через get_worker_pairs(), освобождаются в close_all().

    Использование:
        pool = ClientPool(accounts, policy)
        await pool.initialize()
        try:
            workers = pool.get_worker_pairs()
            # ... работаем с workers ...
        finally:
            await pool.close_all()
    """

    def __init__(
        self,
        accounts: List[AccountConfig],
        policy: TimingPolicy,
        session_encryption_key: Optional[bytes] = None,
    ) -> None:
        self._accounts = accounts
        self._policy = policy
        # phone → TelegramClient (только авторизованные клиенты)
        self._clients: Dict[str, TelegramClient] = {}
        self._initialized = False
        # opt-in: decrypt session-at-rest on connect, re-encrypt on disconnect
        self._session_encryption_key = session_encryption_key
        self._accounts_by_phone = {acc.phone: acc for acc in accounts}

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """
        Параллельно подключает и авторизует все аккаунты.

        return_exceptions=True → один упавший аккаунт не прерывает остальных.
        Ошибки логируются, проблемный аккаунт пропускается.
        """
        if self._initialized:
            logger.warning("Pool already initialized. Call close_all() first.")
            return

        logger.info(
            "Initializing pool: %d accounts ...", len(self._accounts)
        )

        tasks = [self._connect_one_with_timeout(acc) for acc in self._accounts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Failed to initialize account %s: %s",
                    self._accounts[i].phone, result
                )

        self._initialized = True
        logger.info(
            "Pool ready: %d/%d clients active.",
            len(self._clients), len(self._accounts)
        )

    async def close_all(self) -> None:
        """
        Параллельно отключает все активные клиенты.

        Метод идемпотентен: повторный вызов не вызовет ошибки.
        """
        if not self._clients:
            return

        logger.info("Closing all %d clients ...", len(self._clients))
        tasks = [
            self._disconnect_one(phone, client)
            for phone, client in list(self._clients.items())
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        self._clients.clear()
        self._initialized = False
        logger.info("All clients disconnected.")

    def get_worker_pairs(self) -> List[Tuple[TelegramClient, str]]:
        """
        Возвращает список (client, phone) для активных клиентов.

        Используется оркестратором для распределения задач.
        """
        return [(client, phone) for phone, client in self._clients.items()]

    def __len__(self) -> int:
        return len(self._clients)

    def __bool__(self) -> bool:
        return len(self._clients) > 0

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    async def _connect_one(self, account: AccountConfig) -> None:
        """
        Подключает и авторизует один клиент.

        Добавляет стартовый jitter чтобы не генерировать burst
        одновременных подключений при большом пуле.
        """
        startup_delay = self._policy.startup_jitter()
        if startup_delay > 0.01:
            logger.debug(
                "Worker %s: startup jitter %.2fs", account.phone, startup_delay
            )
            await asyncio.sleep(startup_delay)

        if self._session_encryption_key is not None:
            from src.accounts.session_crypto import ensure_decrypted
            ensure_decrypted(account.session_path, self._session_encryption_key)

        client = ClientFactory.build(account)

        try:
            await client.connect()
        except Exception as exc:
            raise ConnectionError(
                f"Cannot connect {account.phone}: {exc}"
            ) from exc

        if not await client.is_user_authorized():
            await self._safe_disconnect(client, account.phone)
            self._reencrypt_session(account.phone)
            raise PermissionError(
                f"Session '{account.session_path}' is not authorized. "
                "Run interactive login first."
            )

        self._clients[account.phone] = client
        logger.info("Client %s authorized.", account.phone)

    async def _connect_one_with_timeout(self, account: AccountConfig) -> None:
        timeout = float(os.getenv("CLIENT_CONNECT_TIMEOUT_SEC", "45"))
        if timeout <= 0:
            await self._connect_one(account)
            return
        try:
            await asyncio.wait_for(self._connect_one(account), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"Timed out connecting {account.phone} after {timeout:g}s"
            ) from exc

    async def _disconnect_one(self, phone: str, client: TelegramClient) -> None:
        await self._safe_disconnect(client, phone)
        self._reencrypt_session(phone)

    def _reencrypt_session(self, phone: str) -> None:
        if self._session_encryption_key is None:
            return
        account = self._accounts_by_phone.get(phone)
        if account is None:
            return
        from src.accounts.session_crypto import ensure_encrypted
        ensure_encrypted(account.session_path, self._session_encryption_key)

    @staticmethod
    async def _safe_disconnect(client: TelegramClient, phone: str) -> None:
        """Disconnect с защитой от двойного вызова и исключений."""
        try:
            if client.is_connected():
                await client.disconnect()
                logger.info("Client %s disconnected.", phone)
        except Exception as exc:
            logger.warning("Error disconnecting %s: %s", phone, exc)
