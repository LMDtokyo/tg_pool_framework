from fastapi.testclient import TestClient

from payment_server.app import app
from payment_server.signer import (
    SignerConfig,
    SignerError,
    SignerSweepResult,
    SignerTransactionResult,
    SignerWallet,
)
from decimal import Decimal


class FakeProvider:
    def __init__(self):
        self.external_order_ids = []

    async def catalog(self):
        return [
            {
                "product_id": 7,
                "name": "Telegram account",
                "price": "3.50",
                "currency": "USD",
                "stock": 10,
                "min_order": 1,
                "max_order": 10,
            }
        ]

    async def create_order(self, *, product_id, quantity, external_order_id):
        self.external_order_ids.append(external_order_id)
        return {
            "order_id": 99,
            "external_order_id": external_order_id,
            "status": "completed",
            "payment_status": "paid",
            "product_id": product_id,
            "quantity": quantity,
            "unit_price": "3.50",
            "total_amount": "3.50",
            "currency": "USD",
            "items": [{"download_url": "https://example.test/delivery.zip"}],
        }


class FailingProvider:
    async def catalog(self):
        raise RuntimeError("provider unavailable")


class FakeSigner:
    def __init__(self):
        self.balance_value = Decimal("10")
        self.trx_balance_value = Decimal("987.455")
        self.sweep_calls = []
        self.wallet_calls = []
        self.fail_uncertain = False
        self.treasury_address = "TTreasuryAddress111111111111111111111"

    async def create_wallet(self, request_id):
        self.wallet_calls.append(request_id)
        return SignerWallet(
            address="TTestAddress111111111111111111111111",
            network="mainnet",
            asset="USDT",
        )

    async def balance(self, address):
        return self.balance_value

    async def wallet_balances(self, address):
        from payment_server.signer import SignerWalletBalances

        return SignerWalletBalances(
            token_balance=self.balance_value,
            trx_balance=self.trx_balance_value,
            asset="USDT",
        )

    async def config(self):
        return SignerConfig(
            treasury_address=self.treasury_address,
            contract_address="TTokenContract11111111111111111111111",
            network="mainnet",
            asset="USDT",
        )

    async def update_treasury(self, treasury_address):
        self.treasury_address = treasury_address
        return await self.config()

    async def sweep(self, *, sweep_id, source_address, amount):
        if self.fail_uncertain:
            raise SignerError("signer response lost", uncertain=True)
        self.sweep_calls.append((sweep_id, source_address, amount))
        self.balance_value -= amount
        return SignerSweepResult(
            transaction_hash="chain-tx-1",
            amount=amount,
            balance_before=amount + self.balance_value,
            destination_address=self.treasury_address,
            network_fee=None,
        )

    async def transaction(self, transaction_hash, source_address):
        return SignerTransactionResult(
            status="confirmed",
            balance_after=self.balance_value,
            network_fee=Decimal("8"),
        )


def test_full_api_key_deposit_and_purchase_flow(tmp_path, monkeypatch):
    notifications = []

    async def fake_notify_deposit(**kwargs):
        notifications.append(kwargs)

    monkeypatch.setattr(
        "payment_server.app.notify_deposit",
        fake_notify_deposit,
    )
    database = tmp_path / "payments.db"
    monkeypatch.setenv(
        "PAYMENT_DATABASE_URL", f"sqlite+aiosqlite:///{database.as_posix()}"
    )
    monkeypatch.setenv("PAYMENT_ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("PAYMENT_WEBHOOK_KEY", "webhook-secret")
    monkeypatch.setenv(
        "PAYMENT_DEPOSIT_ADDRESSES", "TTestAddress111111111111111111111111"
    )
    monkeypatch.setenv("PAYMENT_REQUIRED_CONFIRMATIONS", "2")
    monkeypatch.setenv("PAYMENT_RETAIL_MARKUP_PERCENT", "20")
    monkeypatch.setenv("PAYMENT_RETAIL_MARKUP_FIXED", "0.25")
    monkeypatch.setenv("PAYMENT_CHAIN_NETWORK", "mainnet")
    with TestClient(app) as client:
        provider = FakeProvider()
        signer = FakeSigner()
        app.state.provider = provider
        app.state.signer = signer
        treasury = client.get(
            "/admin/treasury-wallet",
            headers={"X-Admin-Key": "admin-secret"},
        )
        assert treasury.status_code == 200
        assert treasury.json()["address"] == signer.treasury_address
        assert treasury.json()["on_chain_balance"] == "10.00000000"
        assert treasury.json()["trx_balance"] == "987.45500000"
        assert treasury.json()["asset"] == "USDT"

        changed_address = "TChangedTreasury11111111111111111111111"
        changed = client.put(
            "/admin/treasury-wallet",
            headers={"X-Admin-Key": "admin-secret"},
            json={"address": changed_address},
        )
        assert changed.status_code == 200
        assert changed.json()["address"] == changed_address
        assert changed.json()["on_chain_balance"] == "10.00000000"
        assert changed.json()["trx_balance"] == "987.45500000"
        assert signer.treasury_address == changed_address

        issued = client.post(
            "/admin/users",
            headers={"X-Admin-Key": "admin-secret"},
            json={
                "telegram_user_id": "123",
                "telegram_username": "test_user",
                "display_name": "Test User",
            },
        )
        assert issued.status_code == 200
        account = issued.json()
        assert account["api_key"].startswith("sk_live_")
        assert signer.wallet_calls == ["telegram:123"]

        duplicate = client.post(
            "/admin/users",
            headers={"X-Admin-Key": "admin-secret"},
            json={
                "telegram_user_id": "123",
                "telegram_username": "updated_user",
                "display_name": "Updated User",
            },
        )
        assert duplicate.status_code == 409
        assert signer.wallet_calls == ["telegram:123"]
        existing = client.get(
            "/admin/telegram-users/123",
            headers={"X-Admin-Key": "admin-secret"},
        )
        assert existing.status_code == 200
        assert existing.json()["deposit_address"] == account["deposit_address"]

        bearer = {"Authorization": f"Bearer {account['api_key']}"}
        assert client.get("/v1/me", headers=bearer).status_code == 200
        assert client.get("/v1/balance", headers=bearer).json()["balance"] == "0.00000000"
        telegram_balance = client.get(
            "/admin/telegram-users/123/balance",
            headers={"X-Admin-Key": "admin-secret"},
        )
        assert telegram_balance.status_code == 200
        assert telegram_balance.json()["available_balance"] == "0.00000000"

        deposit = {
            "event_id": "evt-1",
            "network": "tron",
            "asset": "USDT",
            "address": account["deposit_address"],
            "transaction_hash": "tx-1",
            "event_index": 0,
            "amount": "10",
            "confirmations": 2,
        }
        credited = client.post(
            "/webhooks/tron/deposits",
            headers={"X-Webhook-Key": "webhook-secret"},
            json=deposit,
        )
        assert credited.status_code == 200
        assert credited.json()["credited"]
        assert credited.json()["newly_credited"]
        assert notifications == [
            {
                "telegram_user_id": "123",
                "amount": "10.00000000",
                "asset": "USDT",
                "transaction_hash": "tx-1",
            }
        ]
        replayed_deposit = client.post(
            "/webhooks/tron/deposits",
            headers={"X-Webhook-Key": "webhook-secret"},
            json=deposit,
        )
        assert replayed_deposit.status_code == 200
        assert replayed_deposit.json()["duplicate"]
        assert not replayed_deposit.json()["newly_credited"]
        assert len(notifications) == 1
        assert client.get("/v1/balance", headers=bearer).json()["balance"] == "10.00000000"
        assert (
            client.get(
                "/admin/telegram-users/123/balance",
                headers={"X-Admin-Key": "admin-secret"},
            ).json()["available_balance"]
            == "10.00000000"
        )

        old_bearer = bearer
        regenerated = client.post(
            "/admin/telegram-users/123/regenerate-key",
            headers={"X-Admin-Key": "admin-secret"},
        )
        assert regenerated.status_code == 200
        assert regenerated.json()["api_key"].startswith("sk_live_")
        assert client.get("/v1/me", headers=old_bearer).status_code == 401
        bearer = {"Authorization": f"Bearer {regenerated.json()['api_key']}"}
        assert client.get("/v1/me", headers=bearer).status_code == 200

        pricing = client.get(
            "/admin/pricing",
            headers={"X-Admin-Key": "admin-secret"},
        )
        assert pricing.status_code == 200
        assert pricing.json() == {
            "markup_percent": "20.00000000",
            "markup_fixed": "0.25000000",
        }

        catalog = client.get("/v1/products", headers=bearer)
        assert catalog.status_code == 200
        assert catalog.json()["items"][0]["product_id"] == 7
        assert catalog.json()["items"][0]["price"] == "4.45000000"
        app.state.provider = FailingProvider()
        cached_catalog = client.get("/v1/products", headers=bearer)
        assert cached_catalog.status_code == 200
        assert cached_catalog.json()["items"][0]["product_id"] == 7
        assert cached_catalog.json()["items"][0]["price"] == "4.45000000"
        app.state.provider = provider

        updated_pricing = client.put(
            "/admin/pricing",
            headers={"X-Admin-Key": "admin-secret"},
            json={"markup_percent": "10", "markup_fixed": "0.50"},
        )
        assert updated_pricing.status_code == 200
        assert updated_pricing.json() == {
            "markup_percent": "10.00000000",
            "markup_fixed": "0.50000000",
        }
        repriced = client.get("/v1/products", headers=bearer)
        assert repriced.status_code == 200
        assert repriced.json()["items"][0]["price"] == "4.35000000"
        restore_pricing = client.put(
            "/admin/pricing",
            headers={"X-Admin-Key": "admin-secret"},
            json={"markup_percent": "20", "markup_fixed": "0.25"},
        )
        assert restore_pricing.status_code == 200

        order_body = {
            "product_id": 7,
            "quantity": 1,
            "external_order_id": "desktop-order-1",
        }
        order = client.post("/v1/orders", headers=bearer, json=order_body)
        assert order.status_code == 200
        assert order.json()["order_id"] == 99
        assert order.json()["external_order_id"] == "desktop-order-1"
        assert order.json()["unit_price"] == "4.45000000"
        assert order.json()["total_amount"] == "4.45000000"
        assert provider.external_order_ids == ["tgpool-payment-1"]
        assert client.get("/v1/balance", headers=bearer).json()["balance"] == "5.55000000"

        assert client.get("/admin/statistics/sales").status_code == 401
        invalid_statistics = client.get(
            "/admin/statistics/sales?days=14",
            headers={"X-Admin-Key": "admin-secret"},
        )
        assert invalid_statistics.status_code == 422
        statistics = client.get(
            "/admin/statistics/sales?days=7",
            headers={"X-Admin-Key": "admin-secret"},
        )
        assert statistics.status_code == 200
        sales = statistics.json()
        assert sales["currency"] == "USD"
        assert sales["days"] == 7
        assert sales["today"] == {
            "gross_sales": "4.45000000",
            "completed_orders": 1,
            "accounts_sold": 1,
        }
        assert sales["period"] == sales["today"]
        assert sales["all_time"] == sales["today"]
        assert len(sales["daily"]) == 7
        assert sales["daily"][-1]["gross_sales"] == "4.45000000"

        assert client.get("/admin/statistics/deposits").status_code == 401
        invalid_deposits = client.get(
            "/admin/statistics/deposits?days=14",
            headers={"X-Admin-Key": "admin-secret"},
        )
        assert invalid_deposits.status_code == 422
        deposit_statistics = client.get(
            "/admin/statistics/deposits?days=7",
            headers={"X-Admin-Key": "admin-secret"},
        )
        assert deposit_statistics.status_code == 200
        deposits = deposit_statistics.json()
        assert deposits["asset"] == "USDT"
        assert deposits["days"] == 7
        assert deposits["today"] == {
            "total_deposited": "10.00000000",
            "deposit_count": 1,
        }
        assert deposits["period"] == deposits["today"]
        assert deposits["all_time"] == deposits["today"]
        assert len(deposits["daily"]) == 7
        assert deposits["daily"][-1]["total_deposited"] == "10.00000000"

        users = client.get(
            "/admin/users",
            headers={"X-Admin-Key": "admin-secret"},
        )
        assert users.status_code == 200
        summary = users.json()["items"][0]
        assert summary["telegram_user_id"] == "123"
        assert summary["telegram_username"] == "updated_user"
        assert summary["on_chain_balance"] == "10.00000000"
        assert summary["trx_balance"] == "987.45500000"
        assert summary["database_balance"] == "5.55000000"
        assert summary["total_accounts_purchased"] == 1
        assert summary["total_amount_paid"] == "4.45000000"

        replay = client.post("/v1/orders", headers=bearer, json=order_body)
        assert replay.status_code == 200
        assert replay.json()["reused_existing"]
        assert replay.json()["unit_price"] == "4.45000000"
        assert replay.json()["total_amount"] == "4.45000000"
        assert client.get("/v1/balance", headers=bearer).json()["balance"] == "5.55000000"

        wallet = client.get(
            f"/admin/users/{account['user_id']}/wallet",
            headers={"X-Admin-Key": "admin-secret"},
        )
        assert wallet.status_code == 200
        assert wallet.json()["on_chain_balance"] == "10.00000000"
        assert wallet.json()["database_balance"] == "5.55000000"

        withdrawal = client.post(
            f"/admin/users/{account['user_id']}/withdrawals",
            headers={
                "X-Admin-Key": "admin-secret",
                "X-Admin-Actor": "operator-1",
                "Idempotency-Key": "withdrawal-api-test-1",
            },
            json={"amount": "4"},
        )
        assert withdrawal.status_code == 200
        assert withdrawal.json()["status"] == "confirmed"
        assert withdrawal.json()["transaction_hash"] == "chain-tx-1"
        assert withdrawal.json()["chain_balance_after"] == "6.00000000"
        assert len(signer.sweep_calls) == 1

        withdrawal_replay = client.post(
            f"/admin/users/{account['user_id']}/withdrawals",
            headers={
                "X-Admin-Key": "admin-secret",
                "Idempotency-Key": "withdrawal-api-test-1",
            },
            json={"amount": "4"},
        )
        assert withdrawal_replay.status_code == 200
        assert withdrawal_replay.json()["status"] == "confirmed"
        assert len(signer.sweep_calls) == 1

        # A confirmed sweep must not block the next withdrawal.
        follow_up = client.post(
            f"/admin/users/{account['user_id']}/withdrawals",
            headers={
                "X-Admin-Key": "admin-secret",
                "Idempotency-Key": "withdrawal-api-test-1b",
            },
            json={"amount": "1"},
        )
        assert follow_up.status_code == 200
        assert follow_up.json()["status"] == "confirmed"
        assert len(signer.sweep_calls) == 2

        refreshed = client.post(
            f"/admin/withdrawals/{withdrawal.json()['id']}/refresh",
            headers={"X-Admin-Key": "admin-secret"},
        )
        assert refreshed.status_code == 200
        assert refreshed.json()["status"] == "confirmed"
        assert refreshed.json()["chain_balance_after"] == "6.00000000"

        # Sweeping chain funds is an asset movement, not a customer ledger debit.
        assert client.get("/v1/balance", headers=bearer).json()["balance"] == "5.55000000"

        signer.fail_uncertain = True
        uncertain = client.post(
            f"/admin/users/{account['user_id']}/withdrawals",
            headers={
                "X-Admin-Key": "admin-secret",
                "Idempotency-Key": "withdrawal-api-test-2",
            },
            json={"amount": "1"},
        )
        assert uncertain.status_code == 503
        assert uncertain.json()["detail"]["status"] == "review_required"
        stuck_id = uncertain.json()["detail"]["withdrawal_id"]
        listed = client.get(
            "/admin/withdrawals",
            headers={"X-Admin-Key": "admin-secret"},
        )
        assert listed.json()["items"][0]["status"] == "review_required"
        assert client.get("/v1/balance", headers=bearer).json()["balance"] == "5.55000000"

        blocked = client.post(
            f"/admin/users/{account['user_id']}/withdrawals",
            headers={
                "X-Admin-Key": "admin-secret",
                "Idempotency-Key": "withdrawal-api-test-3",
            },
            json={"amount": "1"},
        )
        assert blocked.status_code == 409
        assert "unresolved withdrawal" in blocked.json()["detail"]

        abandoned = client.post(
            f"/admin/withdrawals/{stuck_id}/refresh",
            headers={"X-Admin-Key": "admin-secret"},
        )
        assert abandoned.status_code == 200
        assert abandoned.json()["status"] == "failed"

        signer.fail_uncertain = False
        retried = client.post(
            f"/admin/users/{account['user_id']}/withdrawals",
            headers={
                "X-Admin-Key": "admin-secret",
                "Idempotency-Key": "withdrawal-api-test-3",
            },
            json={"amount": "1"},
        )
        assert retried.status_code == 200
        assert retried.json()["status"] == "confirmed"
        assert len(signer.sweep_calls) == 3
