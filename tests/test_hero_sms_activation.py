from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.hero_sms_activation import HeroSmsActivationManager


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_activation_manager_completes_received_sms(monkeypatch):
    request = AsyncMock(
        return_value={
            "activation_id": "123",
            "phone_number": "15550001111",
            "activation_cost": Decimal("0.15"),
            "currency": 840,
            "operator": "tele2",
            "can_get_another_sms": True,
        }
    )
    status = AsyncMock(return_value=("STATUS_OK", "54321"))
    close = AsyncMock()
    monkeypatch.setattr("src.api.hero_sms_activation.request_number_v2", request)
    monkeypatch.setattr("src.api.hero_sms_activation.get_activation_status", status)
    monkeypatch.setattr("src.api.hero_sms_activation.close_activation", close)

    manager = HeroSmsActivationManager()
    manager.start(
        api_key="secret-key",
        country_id=6,
        operator="any",
        target_count=1,
        concurrency=1,
        timeout_sec=30,
        max_price=Decimal("0.15"),
    )
    while manager.running:
        await asyncio.sleep(0)

    row = manager.status()["rows"][0]
    assert row["status"] == "completed"
    assert row["code"] == "54321"
    assert row["phone_number"] == "15550001111"
    close.assert_awaited_once_with("secret-key", "123", cancel=False)


@pytest.mark.asyncio
async def test_activation_manager_cancels_on_timeout(monkeypatch):
    monkeypatch.setattr(
        "src.api.hero_sms_activation.request_number_v2",
        AsyncMock(
            return_value={
                "activation_id": "123",
                "phone_number": "15550001111",
                "activation_cost": Decimal("0.15"),
                "currency": 840,
                "operator": "any",
                "can_get_another_sms": False,
            }
        ),
    )
    close = AsyncMock()
    monkeypatch.setattr("src.api.hero_sms_activation.close_activation", close)

    manager = HeroSmsActivationManager()
    await manager._run_one(
        api_key="secret-key",
        country_id=6,
        operator="any",
        timeout_sec=0,
        max_price=Decimal("0.15"),
    )

    row = manager.status()["rows"][0]
    assert row["status"] == "timed_out"
    close.assert_awaited_once_with("secret-key", "123", cancel=True)


@pytest.mark.asyncio
async def test_activation_manager_reports_remaining_timeout(monkeypatch):
    monkeypatch.setattr(
        "src.api.hero_sms_activation.request_number_v2",
        AsyncMock(
            return_value={
                "activation_id": "123",
                "phone_number": "15550001111",
                "activation_cost": Decimal("0.15"),
                "currency": 840,
                "operator": "any",
                "can_get_another_sms": False,
            }
        ),
    )
    status_called = asyncio.Event()

    async def status(*args, **kwargs):
        status_called.set()
        return "STATUS_WAIT_CODE", ""

    monkeypatch.setattr("src.api.hero_sms_activation.get_activation_status", status)
    close = AsyncMock()
    monkeypatch.setattr("src.api.hero_sms_activation.close_activation", close)

    manager = HeroSmsActivationManager()
    task = asyncio.create_task(
        manager._run_one(
            api_key="secret-key",
            country_id=6,
            operator="any",
            timeout_sec=30,
            max_price=Decimal("0.15"),
        )
    )
    await status_called.wait()

    row = manager.status()["rows"][0]
    assert 0 < row["remaining_timeout_sec"] <= 30

    manager._stop_event.set()
    await task


def test_activation_manager_validates_concurrency_limit():
    manager = HeroSmsActivationManager()
    with pytest.raises(ValueError, match="between 1 and 10"):
        manager.start(
            api_key="secret-key",
            country_id=6,
            operator="any",
            target_count=1000,
            concurrency=11,
            timeout_sec=300,
            max_price=Decimal("0.15"),
        )


@pytest.mark.asyncio
async def test_activation_manager_replaces_failures_until_target_is_reached():
    attempts = 0

    async def request(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("number unavailable")
        return {
            "activation_id": str(attempts),
            "phone_number": f"1555000000{attempts}",
            "activation_cost": Decimal("0.15"),
            "operator": "any",
        }

    manager = HeroSmsActivationManager(
        request_number_func=request,
        get_activation_status_func=AsyncMock(return_value=("STATUS_OK", "54321")),
        close_activation_func=AsyncMock(),
    )
    manager._wait_or_stop = AsyncMock()
    manager.start(
        api_key="secret-key",
        country_id=6,
        operator="any",
        target_count=2,
        concurrency=1,
        timeout_sec=30,
        max_price=Decimal("0.15"),
    )
    while manager.running:
        await asyncio.sleep(0)

    result = manager.status()
    assert attempts == 3
    assert result["success_count"] == 2
    assert len(result["rows"]) == 3
    assert [row["status"] for row in result["rows"]] == [
        "failed",
        "completed",
        "completed",
    ]


@pytest.mark.asyncio
async def test_activation_manager_keeps_configured_concurrency_without_overshoot():
    attempts = 0
    purchases_in_flight = 0
    max_purchases_in_flight = 0

    async def request(*args, **kwargs):
        nonlocal attempts, purchases_in_flight, max_purchases_in_flight
        attempts += 1
        activation_id = str(attempts)
        purchases_in_flight += 1
        max_purchases_in_flight = max(max_purchases_in_flight, purchases_in_flight)
        await asyncio.sleep(0)
        purchases_in_flight -= 1
        return {
            "activation_id": activation_id,
            "phone_number": f"1555000000{activation_id}",
            "activation_cost": Decimal("0.15"),
            "operator": "any",
        }

    manager = HeroSmsActivationManager(
        request_number_func=request,
        get_activation_status_func=AsyncMock(return_value=("STATUS_OK", "54321")),
        close_activation_func=AsyncMock(),
    )
    manager.start(
        api_key="secret-key",
        country_id=6,
        operator="any",
        target_count=5,
        concurrency=3,
        timeout_sec=30,
        max_price=Decimal("0.15"),
    )
    while manager.running:
        await asyncio.sleep(0)

    result = manager.status()
    assert attempts == 5
    assert max_purchases_in_flight == 3
    assert result["success_count"] == 5


@pytest.mark.asyncio
async def test_existing_telegram_account_is_replaced_without_counting_toward_target():
    attempts = 0

    async def request(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        return {
            "activation_id": str(attempts),
            "phone_number": f"1555000000{attempts}",
            "activation_cost": Decimal("0.15"),
            "operator": "any",
        }

    class Authenticator:
        def validate_ready(self):
            pass

        async def begin(self, phone):
            return SimpleNamespace(phone=f"+{phone}")

        async def submit_code(self, login, code):
            return True

        async def save(self, login):
            return SimpleNamespace(
                account=SimpleNamespace(phone=login.phone),
                session_file=f"accounts/{login.phone}.session",
                created_new_account=attempts > 1,
            )

        async def discard(self, login):
            pass

    manager = HeroSmsActivationManager(
        authenticator=Authenticator(),
        request_number_func=request,
        get_activation_status_func=AsyncMock(return_value=("STATUS_OK", "54321")),
        close_activation_func=AsyncMock(),
    )
    manager._wait_or_stop = AsyncMock()
    manager.start(
        api_key="secret-key",
        country_id=6,
        operator="any",
        target_count=1,
        concurrency=1,
        timeout_sec=30,
        max_price=Decimal("0.15"),
    )
    while manager.running:
        await asyncio.sleep(0)

    result = manager.status()
    assert attempts == 2
    assert result["success_count"] == 1
    assert [row["created_new_account"] for row in result["rows"]] == [False, True]


@pytest.mark.asyncio
async def test_activation_manager_retries_one_higher_price_on_no_numbers():
    from src.api.hero_sms import HeroSmsApiError

    attempted_prices: list[Decimal] = []

    async def request(*args, **kwargs):
        price = Decimal(str(kwargs["max_price"]))
        attempted_prices.append(price)
        if price == Decimal("1.0742"):
            raise HeroSmsApiError("Hero SMS has no matching numbers available")
        return {
            "activation_id": "999",
            "phone_number": "40755111222",
            "activation_cost": Decimal("1.10"),
            "operator": "any",
        }

    manager = HeroSmsActivationManager(
        request_number_func=request,
        get_activation_status_func=AsyncMock(return_value=("STATUS_OK", "54321")),
        close_activation_func=AsyncMock(),
    )
    await manager._run_one(
        api_key="secret-key",
        country_id=32,
        operator="any",
        timeout_sec=30,
        max_price=Decimal("1.0742"),
        price_ceiling=Decimal("1.1000"),
        price_offers=[
            Decimal("1.0742"),
            Decimal("1.1000"),
            Decimal("1.6368"),
        ],
    )

    row = manager.status()["rows"][0]
    assert attempted_prices == [Decimal("1.0742"), Decimal("1.1000")]
    assert row["status"] == "completed"
    assert row["cost"] == 1.10
    assert row["phone_number"] == "40755111222"


@pytest.mark.asyncio
async def test_activation_manager_retries_one_higher_price_on_http_404():
    from src.api.hero_sms import HeroSmsApiError

    attempted_prices: list[Decimal] = []

    async def request(*args, **kwargs):
        price = Decimal(str(kwargs["max_price"]))
        attempted_prices.append(price)
        if price == Decimal("1.0742"):
            raise HeroSmsApiError("Hero SMS returned HTTP 404")
        return {
            "activation_id": "1001",
            "phone_number": "40755111333",
            "activation_cost": Decimal("1.10"),
            "operator": "any",
        }

    manager = HeroSmsActivationManager(
        request_number_func=request,
        get_activation_status_func=AsyncMock(return_value=("STATUS_OK", "12345")),
        close_activation_func=AsyncMock(),
    )
    await manager._run_one(
        api_key="secret-key",
        country_id=32,
        operator="any",
        timeout_sec=30,
        max_price=Decimal("1.0742"),
        price_ceiling=Decimal("1.1000"),
        price_offers=[Decimal("1.0742"), Decimal("1.1000"), Decimal("1.6368")],
    )

    assert attempted_prices == [Decimal("1.0742"), Decimal("1.1000")]
    assert manager.status()["rows"][0]["status"] == "completed"


@pytest.mark.asyncio
async def test_activation_manager_climbs_tiers_up_to_purchase_ceiling():
    from src.api.hero_sms import HeroSmsApiError

    attempted_prices: list[Decimal] = []

    async def request(*args, **kwargs):
        price = Decimal(str(kwargs["max_price"]))
        attempted_prices.append(price)
        if price < Decimal("1.6368"):
            raise HeroSmsApiError("Hero SMS has no matching numbers available")
        return {
            "activation_id": "1002",
            "phone_number": "40755111444",
            "activation_cost": Decimal("1.6368"),
            "operator": "any",
        }

    manager = HeroSmsActivationManager(
        request_number_func=request,
        get_activation_status_func=AsyncMock(return_value=("STATUS_OK", "99999")),
        close_activation_func=AsyncMock(),
    )
    await manager._run_one(
        api_key="secret-key",
        country_id=32,
        operator="any",
        timeout_sec=30,
        max_price=Decimal("1.0742"),
        price_ceiling=Decimal("1.6368"),
        price_offers=[
            Decimal("1.0742"),
            Decimal("1.1000"),
            Decimal("1.6368"),
            Decimal("2.3295"),
        ],
    )

    row = manager.status()["rows"][0]
    assert attempted_prices == [
        Decimal("1.0742"),
        Decimal("1.1000"),
        Decimal("1.6368"),
    ]
    assert row["status"] == "completed"
    assert row["cost"] == 1.6368


@pytest.mark.asyncio
async def test_activation_manager_does_not_exceed_purchase_ceiling():
    from src.api.hero_sms import HeroSmsApiError

    attempted_prices: list[Decimal] = []

    async def request(*args, **kwargs):
        price = Decimal(str(kwargs["max_price"]))
        attempted_prices.append(price)
        raise HeroSmsApiError("Hero SMS has no matching numbers available")

    manager = HeroSmsActivationManager(request_number_func=request)
    await manager._run_one(
        api_key="secret-key",
        country_id=32,
        operator="any",
        timeout_sec=30,
        max_price=Decimal("1.0742"),
        price_ceiling=Decimal("1.1000"),
        price_offers=[Decimal("1.0742"), Decimal("1.1000"), Decimal("1.6368")],
    )

    row = manager.status()["rows"][0]
    assert attempted_prices == [Decimal("1.0742"), Decimal("1.1000")]
    assert row["status"] == "failed"
    assert "no matching numbers" in row["message"].lower()


def test_purchase_prices_respects_ceiling():
    prices = HeroSmsActivationManager._purchase_prices(
        Decimal("1.0742"),
        [
            Decimal("1.0742"),
            Decimal("1.1000"),
            Decimal("1.6368"),
            Decimal("2.3295"),
        ],
        price_ceiling=Decimal("1.6368"),
    )
    assert prices == [
        Decimal("1.0742"),
        Decimal("1.1000"),
        Decimal("1.6368"),
    ]


@pytest.mark.asyncio
async def test_activation_manager_cancels_and_stops_on_price_mismatch():
    close = AsyncMock()

    async def request(*args, **kwargs):
        return {
            "activation_id": "price-mismatch",
            "phone_number": "40755111555",
            "activation_cost": Decimal("0.9765"),
            "operator": "telekom",
        }

    manager = HeroSmsActivationManager(
        enforce_exact_price=True,
        request_number_func=request,
        close_activation_func=close,
    )

    created = await manager._run_one(
        api_key="secret-key",
        country_id=32,
        operator="any",
        timeout_sec=30,
        max_price=Decimal("1.0742"),
    )

    status = manager.status()
    row = status["rows"][0]
    assert created is False
    assert row["status"] == "failed"
    assert row["stage"] == "purchase_price_mismatch"
    assert row["cost"] == 0.9765
    assert "selected tier USD 1.0742" in row["message"]
    assert status["error"] == row["message"]
    close.assert_awaited_once_with(
        "secret-key",
        "price-mismatch",
        cancel=True,
    )
