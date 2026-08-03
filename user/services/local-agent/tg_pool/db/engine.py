"""
tg_pool/db/engine.py — Async engine/session factory for the durable account store.

Opt-in by design: if DATABASE_URL is unset, the framework runs exactly as
before (AccountRegistry stays in-memory-only). Same pattern as
main.py::build_rate_limiter() for Redis.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


def build_engine_and_session_factory(
    database_url: str, *, echo: bool = False
) -> Tuple[AsyncEngine, async_sessionmaker]:
    """Create an async engine + session factory bound to database_url."""
    engine: AsyncEngine = create_async_engine(database_url, echo=echo, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def build_session_factory(database_url: str, *, echo: bool = False) -> async_sessionmaker:
    """Same as build_engine_and_session_factory(), minus the engine handle."""
    _, session_factory = build_engine_and_session_factory(database_url, echo=echo)
    return session_factory


def build_session_factory_from_env() -> Optional[async_sessionmaker]:
    """
    Build a session factory from the DATABASE_URL env var.

    Returns None if DATABASE_URL is not set — callers must treat this as
    "persistence disabled" rather than an error.
    """
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        return None
    return build_session_factory(database_url, echo=os.getenv("DATABASE_ECHO", "") == "1")
