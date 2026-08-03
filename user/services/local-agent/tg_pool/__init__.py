"""
tg_pool_framework.src
=====================
Пакет исходного кода.

Публичный API:
    from tg_pool.config import AccountConfig, ProxyConfig, TimingPolicy
    from tg_pool.accounts.connection_manager import ClientPool
    from tg_pool.extraction.data_extraction import extract_members
    from tg_pool.messaging.messaging_service import send_notifications, BatchReport
    from tg_pool.orchestrator import orchestrate
"""

__version__ = "1.0.0"
