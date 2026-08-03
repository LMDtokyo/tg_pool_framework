"""license_server/db/engine.py — Async engine/session factory, mirrors src/db/engine.py."""

from __future__ import annotations

import os
from typing import Tuple

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


def build_engine_and_session_factory(
    database_url: str, *, echo: bool = False
) -> Tuple[AsyncEngine, async_sessionmaker]:
    engine: AsyncEngine = create_async_engine(database_url, echo=echo, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def build_session_factory(database_url: str, *, echo: bool = False) -> async_sessionmaker:
    _, session_factory = build_engine_and_session_factory(database_url, echo=echo)
    return session_factory


def build_session_factory_from_env() -> async_sessionmaker:
    database_url = os.getenv("LICENSE_DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("LICENSE_DATABASE_URL must be set for the license server")
    return build_session_factory(database_url, echo=os.getenv("DATABASE_ECHO", "") == "1")
