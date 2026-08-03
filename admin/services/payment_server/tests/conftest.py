import pytest

from payment_server.db.engine import build_engine_and_session_factory
from payment_server.db.models import Base
from payment_server.db.repository import PaymentRepository


@pytest.fixture
async def repository():
    engine, session_factory = build_engine_and_session_factory(
        "sqlite+aiosqlite:///:memory:"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield PaymentRepository(session_factory)
    finally:
        await engine.dispose()
