import pytest

from license_server.db.engine import build_engine_and_session_factory
from license_server.db.models import Base
from license_server.db.repository import LicenseKeyRepository


@pytest.fixture
async def repository():
    engine, session_factory = build_engine_and_session_factory("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield LicenseKeyRepository(session_factory)
    finally:
        await engine.dispose()
