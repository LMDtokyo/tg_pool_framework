import httpx
import pytest

from payment_server.telegram_bot import (
    BALANCE_CALLBACK,
    MAIN_MENU,
    REISSUE_KEY_CALLBACK,
    _fetch_balance,
    _issue_account,
    _reissue_key,
)


def test_main_menu_uses_visible_inline_buttons():
    buttons = MAIN_MENU["inline_keyboard"][0]
    assert [button["callback_data"] for button in buttons] == [
        BALANCE_CALLBACK,
        REISSUE_KEY_CALLBACK,
    ]


@pytest.mark.asyncio
async def test_existing_telegram_user_reuses_public_wallet_without_api_key():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                409, json={"detail": "A payment account already exists"}
            )
        return httpx.Response(
            200,
            json={
                "user_id": 4,
                "telegram_user_id": "123",
                "display_name": "Test User",
                "deposit_address": "TExistingAddress1111111111111111111111",
                "network": "tron",
                "asset": "USDT",
            },
        )

    async with httpx.AsyncClient(
        base_url="https://payments.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        account = await _issue_account(
            client,
            user_id=123,
            display_name="Test User",
            admin_key="admin-secret",
        )

    assert account["existing"] is True
    assert account["deposit_address"].startswith("TExisting")
    assert "api_key" not in account


@pytest.mark.asyncio
async def test_fetch_balance_uses_telegram_scoped_admin_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/admin/telegram-users/123/balance"
        assert request.headers["X-Admin-Key"] == "admin-secret"
        return httpx.Response(
            200,
            json={
                "balance": "12.50000000",
                "available_balance": "12.50000000",
                "currency": "USD",
            },
        )

    async with httpx.AsyncClient(
        base_url="https://payments.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        balance = await _fetch_balance(
            client,
            user_id=123,
            admin_key="admin-secret",
        )

    assert balance["available_balance"] == "12.50000000"
    assert balance["currency"] == "USD"


@pytest.mark.asyncio
async def test_reissue_key_uses_telegram_scoped_admin_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/admin/telegram-users/123/regenerate-key"
        assert request.headers["X-Admin-Key"] == "admin-secret"
        return httpx.Response(200, json={"api_key": "sk_live_replacement"})

    async with httpx.AsyncClient(
        base_url="https://payments.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        regenerated = await _reissue_key(
            client,
            user_id=123,
            admin_key="admin-secret",
        )

    assert regenerated["api_key"] == "sk_live_replacement"
