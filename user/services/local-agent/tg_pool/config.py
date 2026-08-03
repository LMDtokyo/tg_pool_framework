"""
tg_pool/config.py — Централизованная, иммутабельная конфигурация фреймворка.

Ключевые решения:
  - frozen=True на всех публичных конфигах: нельзя мутировать объект
    после его создания, что устраняет целый класс ошибок в многозадачной среде.
  - TimingPolicy — тоже frozen, но содержит методы с random: они читают
    состояние, но не изменяют его — это совместимо с frozen=True.
  - Явные __repr__ скрывают чувствительные данные из логов.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

# Maps our proxy_type string to the PySocks constant name. PySocks has no
# separate "connect to the proxy itself over TLS" type — an "https" proxy_type
# (used by tg_pool/proxy/proxy_checker.py's own TLS-to-proxy check) still goes
# through Telethon/PySocks as a plain HTTP CONNECT tunnel.
_PYSOCKS_TYPE_NAMES = {
    "socks4": "SOCKS4",
    "socks5": "SOCKS5",
    "http": "HTTP",
    "https": "HTTP",
}


# ---------------------------------------------------------------------------
# ProxyConfig — дескриптор прокси (SOCKS4/SOCKS5/HTTP/HTTPS)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProxyConfig:
    """
    Иммутабельный дескриптор одного прокси.

    frozen=True гарантирует, что после привязки прокси к воркеру
    его параметры не могут быть изменены ни одной другой задачей.
    Это устраняет класс ошибок «подменённого прокси» в пуле.

    Пример:
        proxy = ProxyConfig(host="10.0.0.1", port=1080)
        proxy.port = 9999  # -> raises FrozenInstanceError (защита!)
    """
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    proxy_type: str = "socks5"  # "socks4" | "socks5" | "http" | "https"

    # rdns=True: DNS-резолвинг выполняется на стороне прокси-сервера.
    # Критично для анонимности и обхода локальных DNS-блокировок.
    _RDNS: bool = True

    def as_tuple(self) -> tuple:
        """
        Сериализует прокси в кортеж, понятный Telethon.

        Формат: (socks_type, host, port, rdns, username, password).
        """
        import socks  # PySocks — ленивый импорт, не нужен при unit-тестах
        pysocks_type = getattr(socks, _PYSOCKS_TYPE_NAMES.get(self.proxy_type, "SOCKS5"))
        return (
            pysocks_type,
            self.host,
            self.port,
            self._RDNS,
            self.username,
            self.password,
        )

    def __repr__(self) -> str:
        # Пароль не попадает в repr → не утекает в логи и трейсбэки
        return (
            f"ProxyConfig(host={self.host!r}, port={self.port}, "
            f"type={self.proxy_type!r}, user={self.username!r}, rdns={self._RDNS})"
        )


# ---------------------------------------------------------------------------
# AccountConfig — дескриптор одного Telegram-аккаунта / воркера
# ---------------------------------------------------------------------------

def normalize_account_phone(value: str) -> str:
    """Return one stable identity for phone-shaped account identifiers."""
    raw = str(value).strip()
    digits = "".join(character for character in raw if character.isdigit())
    separators = set("+ -()./")
    if digits and all(character.isdigit() or character in separators for character in raw):
        return f"+{digits}"
    return raw


@dataclass(frozen=True)
class AccountConfig:
    """
    Иммутабельный дескриптор аккаунта и его «цифрового отпечатка».

    Каждый AccountConfig — ровно один воркер, ровно один TelegramClient,
    ровно одна asyncio.Task. Нарушение этого соответствия 1:1:1
    приводит к конфликтам сессий.

    frozen=True + уникальный session_dir гарантируют изоляцию.
    """
    api_id: int
    api_hash: str
    phone: str                          # номер телефона = идентификатор сессии

    proxy: Optional[ProxyConfig] = None

    # «Цифровой отпечаток» устройства. Разные значения → разные «устройства»
    # с точки зрения сервера → нет конфликтов сессий между воркерами.
    device_model: str = "Samsung Galaxy S23"
    system_version: str = "Android 14"
    app_version: str = "10.3.1"
    lang_code: str = "en"
    system_lang_code: str = "en"
    lang_pack: str = "android"
    sdk: int = 0
    tz_offset: int = 0
    perf_cat: int = 0

    # Директория хранения .session файлов
    session_dir: str = "sessions"

    def __post_init__(self) -> None:
        # JSON exports and session filenames frequently disagree only on '+'.
        # The phone is the identity everywhere, so canonicalize it once here.
        object.__setattr__(self, "phone", normalize_account_phone(self.phone))

    @property
    def session_path(self) -> str:
        """
        Уникальный путь к SQLite-файлу сессии.

        Нормализуем номер телефона, убирая '+',
        чтобы получить валидное имя файла.
        """
        normalized = self.phone.lstrip("+").replace(" ", "_")
        return f"{self.session_dir}/{normalized}"

    def __repr__(self) -> str:
        return (
            f"AccountConfig(phone={self.phone!r}, "
            f"device={self.device_model!r}, proxy={self.proxy!r})"
        )


# ---------------------------------------------------------------------------
# TimingPolicy — политика задержек и retry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TimingPolicy:
    """
    Иммутабельная политика задержек между сетевыми запросами.

    Рандомизация (jitter) — ключевая защита от детерминированных
    паттернов трафика, которые тривиально детектируются rate-limiter-ами.

    Формула расчёта задержки:
        delay = clamp(base_delay + U(-jitter, +jitter), min_val, ∞)

    frozen=True: политика — константа на время работы пула.
    """
    # Базовая пауза между запросами (iter_participants, iter_messages)
    base_delay_sec: float = 2.0
    # Максимальное отклонение от базы (±)
    jitter_sec: float = 1.5
    # Пауза между отправкой сообщений
    inter_message_delay_sec: float = 3.0
    inter_message_jitter_sec: float = 2.0
    # Максимум попыток при FloodWait до пробрасывания исключения
    max_flood_retries: int = 5
    # Максимальная стартовая задержка воркера
    startup_jitter_max_sec: float = 3.0

    def next_delay(self) -> float:
        """Следующая задержка для запросов к API (с jitter)."""
        return max(0.1, self.base_delay_sec + random.uniform(
            -self.jitter_sec, self.jitter_sec
        ))

    def next_message_delay(self) -> float:
        """Задержка между отправкой сообщений (с jitter)."""
        return max(0.5, self.inter_message_delay_sec + random.uniform(
            -self.inter_message_jitter_sec, self.inter_message_jitter_sec
        ))

    def startup_jitter(self) -> float:
        """Случайная задержка при старте воркера."""
        return random.uniform(0.0, self.startup_jitter_max_sec)
