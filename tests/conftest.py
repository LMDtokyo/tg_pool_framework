"""
tests/conftest.py — Env isolation shared by every test.

src/api/app.py's lifespan calls load_dotenv() on every startup, which reads
whatever real .env the developer running the suite happens to have on disk.
Most existing fixtures already neutralize the vars they care about via
monkeypatch, but a var no test file explicitly touches (e.g.
LICENSE_SERVER_URL, set locally to exercise the licensing feature by hand)
would otherwise leak straight through and change test behavior depending on
whose machine the suite runs on.

Setting it to "" rather than delenv matters: python-dotenv's load_dotenv()
only fills in vars that are absent from os.environ, so a deleted var gets
silently repopulated from the real .env on the next lifespan startup, while
an explicitly-empty one is left alone -- same trick test_api.py already
uses for DATABASE_URL.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_licensing_env(monkeypatch):
    monkeypatch.setenv("LICENSE_SERVER_URL", "")
