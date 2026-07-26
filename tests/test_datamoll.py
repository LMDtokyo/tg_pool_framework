from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from src.api.datamoll import (
    DatamollApiError,
    DatamollDeliveryError,
    create_order_with_recovery,
    download_and_import_deliveries,
    fetch_balance,
    fetch_telegram_catalog,
    save_order_receipt,
)


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_fetch_balance_uses_provider_credentials_header():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://datamollcore.com/api/v1/provider/balance"
        assert request.headers["X-Provider-Key"] == "public:private"
        assert request.headers["User-Agent"] == "tg-pool-framework/1.0"
        return httpx.Response(
            200,
            json={
                "partner_id": 72,
                "balance": "10.00",
                "credit_limit": "2.00",
                "available_balance": "12.00",
                "currency": "USD",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_balance("public", "private", client=client)

    assert result == {
        "balance": "10.00",
        "credit_limit": "2.00",
        "available_balance": "12.00",
        "currency": "USD",
    }


@pytest.mark.asyncio
async def test_catalog_paginates_and_keeps_only_telegram_products():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.params["limit"] == "500"
        assert request.url.params["only_in_stock"] == "true"
        assert request.url.params["language"] == "en"
        if calls == 1:
            assert "after_id" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"product_id": 1, "name": "Telegram USA"},
                        {"product_id": 2, "name": "Facebook USA"},
                    ],
                    "has_more": True,
                    "next_after_id": 2,
                },
            )
        assert request.url.params["after_id"] == "2"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "product_id": 3,
                        "name": "Autoreg USA",
                        "category_name": "Telegram",
                    }
                ],
                "has_more": False,
                "next_after_id": None,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_telegram_catalog("public", "private", client=client)

    assert [item["product_id"] for item in result] == [1, 3]


@pytest.mark.asyncio
async def test_create_order_uses_stable_idempotency_identity():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "https://datamollcore.com/api/v1/provider/orders"
        assert request.headers["Idempotency-Key"] == "tgpool-order-1"
        assert json.loads(request.content) == {
            "product_id": 5,
            "quantity": 2,
            "external_order_id": "tgpool-order-1",
        }
        return httpx.Response(
            201,
            json={
                "order_id": 4012,
                "external_order_id": "tgpool-order-1",
                "status": "fulfilled",
                "payment_status": "paid",
                "product_id": 5,
                "quantity": 2,
                "unit_price": "10.00",
                "total_amount": "20.00",
                "currency": "USD",
                "items": ["account-one", "account-two"],
                "created_at": "2026-04-13T08:10:00Z",
                "reused_existing": False,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await create_order_with_recovery(
            "public",
            "private",
            product_id=5,
            quantity=2,
            external_order_id="tgpool-order-1",
            client=client,
        )

    assert result["order_id"] == 4012
    assert result["items"] == ["account-one", "account-two"]


@pytest.mark.asyncio
async def test_processing_order_is_recovered_by_external_order_id():
    calls = 0

    async def no_sleep(_: float) -> None:
        return None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                202,
                headers={"Retry-After": "0"},
                json={
                    "error": {
                        "code": "order_processing",
                        "message": "Order processing",
                        "details": None,
                    }
                },
            )
        assert request.method == "GET"
        assert request.url.path.endswith("/orders/by-external-id/tgpool-order-2")
        return httpx.Response(
            200,
            json={
                "order_id": 4013,
                "external_order_id": "tgpool-order-2",
                "status": "fulfilled",
                "payment_status": "paid",
                "product_id": 6,
                "quantity": 1,
                "unit_price": "8.00",
                "total_amount": "8.00",
                "currency": "USD",
                "items": ["account"],
                "created_at": "2026-04-13T08:10:00Z",
                "reused_existing": False,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await create_order_with_recovery(
            "public",
            "private",
            product_id=6,
            quantity=1,
            external_order_id="tgpool-order-2",
            client=client,
            recovery_delay_sec=0,
            sleep_func=no_sleep,
        )

    assert calls == 2
    assert result["order_id"] == 4013


@pytest.mark.asyncio
async def test_provider_error_message_is_preserved():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            402,
            json={
                "error": {
                    "code": "insufficient_balance",
                    "message": "Not enough partner balance",
                    "details": None,
                }
            },
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(DatamollApiError, match="Not enough partner balance"):
            await create_order_with_recovery(
                "public",
                "private",
                product_id=5,
                quantity=1,
                external_order_id="tgpool-order-3",
                client=client,
            )


def test_order_receipt_keeps_delivered_items_server_side(tmp_path):
    order = {
        "order_id": 4012,
        "external_order_id": "tgpool-order-1",
        "items": ["sensitive-account-data"],
    }

    path = save_order_receipt(order, str(tmp_path))

    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    assert saved["items"] == ["sensitive-account-data"]
    assert "tgpool-order-1-4012.json" in path


def _account_archive(*, unsafe_name: str | None = None) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        if unsafe_name is not None:
            archive.writestr(unsafe_name, b"unsafe")
        else:
            root = "CA_+1_1pcs_2026-07-26_03-04"
            archive.writestr(
                f"{root}/sessions_2040/12499460883.session",
                b"sqlite-session",
            )
            archive.writestr(
                f"{root}/sessions_2040/12499460883.json",
                json.dumps(
                    {
                        "app_id": 2040,
                        "app_hash": "hash",
                        "phone": "+12499460883",
                    }
                ),
            )
            archive.writestr(
                f"{root}/tdatas/12499460883/2FA.txt",
                "secret",
            )
            archive.writestr(
                f"{root}/tdatas/12499460883/tdata/key_datas",
                b"key-data",
            )
            archive.writestr(
                f"{root}/tdatas/12499460883/tdata/D877F783D5D3EF8C/maps",
                b"maps",
            )
    return output.getvalue()


@pytest.mark.asyncio
async def test_delivery_archive_is_imported_into_existing_account_storage(tmp_path):
    archive_bytes = _account_archive()
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, content=archive_bytes)
    )
    accounts_dir = tmp_path / "Accounts"
    tdata_dir = tmp_path / "Tdata"

    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=True,
    ) as client:
        result = await download_and_import_deliveries(
            ["https://dl-cloude.org/files/account"],
            accounts_dir=str(accounts_dir),
            tdata_dir=str(tdata_dir),
            client=client,
        )
        repeated = await download_and_import_deliveries(
            ["https://dl-cloude.org/files/account"],
            accounts_dir=str(accounts_dir),
            tdata_dir=str(tdata_dir),
            client=client,
        )

    assert result.downloaded_files == 1
    assert result.imported_sessions == 1
    assert result.imported_tdata == 1
    assert (accounts_dir / "12499460883.session").read_bytes() == b"sqlite-session"
    assert (accounts_dir / "12499460883.json").is_file()
    assert (tdata_dir / "12499460883" / "2FA.txt").read_text() == "secret"
    assert (tdata_dir / "12499460883" / "tdata" / "key_datas").is_file()
    assert repeated.imported_sessions == 0
    assert repeated.imported_tdata == 0
    assert repeated.skipped_existing == 2


@pytest.mark.asyncio
async def test_delivery_archive_rejects_path_traversal(tmp_path):
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, content=_account_archive(unsafe_name="../escape"))
    )
    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=True,
    ) as client:
        with pytest.raises(DatamollDeliveryError, match="unsafe file path"):
            await download_and_import_deliveries(
                ["https://dl-cloude.org/files/account"],
                accounts_dir=str(tmp_path / "Accounts"),
                tdata_dir=str(tmp_path / "Tdata"),
                client=client,
            )

    assert not (tmp_path / "escape").exists()
