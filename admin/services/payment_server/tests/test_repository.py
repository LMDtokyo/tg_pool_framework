from datetime import datetime, timezone
from decimal import Decimal

import pytest

from payment_server.db.repository import (
    InsufficientFundsError,
    ReservationKind,
)


@pytest.mark.asyncio
async def test_api_keys_are_hashed_and_can_be_rotated(repository):
    issued = await repository.issue_user(
        telegram_user_id="123",
        display_name="Test User",
        address_candidates=["TTestAddress111111111111111111111111"],
    )

    user = await repository.authenticate(issued.api_key)
    assert user is not None
    assert user.id == issued.user_id
    assert await repository.authenticate("sk_live_wrong") is None

    replacement = await repository.regenerate_api_key(issued.user_id)
    assert replacement != issued.api_key
    assert await repository.authenticate(issued.api_key) is None
    assert await repository.authenticate(replacement) is not None
    assert await repository.revoke_api_keys(issued.user_id)
    assert await repository.authenticate(replacement) is None


@pytest.mark.asyncio
async def test_deposit_is_credited_once_after_confirmations(repository):
    issued = await repository.issue_user(
        telegram_user_id="123",
        display_name="Test User",
        address_candidates=["TTestAddress111111111111111111111111"],
    )
    event = dict(
        address=issued.address,
        network="tron",
        asset="USDT",
        transaction_hash="abc123",
        event_index=0,
        amount=Decimal("25"),
        required_confirmations=20,
    )

    pending = await repository.record_deposit(
        event_id="evt-1",
        payload={"confirmations": 5},
        confirmations=5,
        **event,
    )
    assert pending.status == "pending"
    assert not pending.credited
    assert not pending.newly_credited
    assert await repository.balance(issued.user_id) == Decimal("0")

    confirmed = await repository.record_deposit(
        event_id="evt-2",
        payload={"confirmations": 20},
        confirmations=20,
        **event,
    )
    assert confirmed.credited
    assert confirmed.newly_credited
    assert confirmed.user_id == issued.user_id
    assert confirmed.telegram_user_id == "123"
    assert await repository.balance(issued.user_id) == Decimal("25")

    duplicate = await repository.record_deposit(
        event_id="evt-2",
        payload={"confirmations": 30},
        confirmations=30,
        **event,
    )
    assert duplicate.duplicate
    assert not duplicate.newly_credited
    assert await repository.balance(issued.user_id) == Decimal("25")


@pytest.mark.asyncio
async def test_order_debit_refund_retry_and_idempotent_completion(repository):
    issued = await repository.issue_user(
        telegram_user_id="123",
        display_name="Test User",
        address_candidates=["TTestAddress111111111111111111111111"],
    )
    await repository.add_adjustment(
        user_id=issued.user_id,
        amount=Decimal("20"),
        description="test credit",
        reference="test-credit",
    )

    reservation = await repository.reserve_order(
        user_id=issued.user_id,
        external_order_id="order-1",
        product_id=7,
        quantity=2,
        unit_price=Decimal("3.50"),
        currency="USD",
    )
    assert reservation.kind is ReservationKind.NEW
    assert await repository.balance(issued.user_id) == Decimal("13")

    await repository.fail_order(reservation.order_id, reservation.attempt, "provider down")
    assert await repository.balance(issued.user_id) == Decimal("20")

    retry = await repository.reserve_order(
        user_id=issued.user_id,
        external_order_id="order-1",
        product_id=7,
        quantity=2,
        unit_price=Decimal("3.50"),
        currency="USD",
    )
    assert retry.kind is ReservationKind.RETRY
    payload = {
        "order_id": 99,
        "product_id": 7,
        "quantity": 2,
        "unit_price": "3.50",
        "total_amount": "7.00",
        "currency": "USD",
        "items": [{"download_url": "https://example.test/delivery.zip"}],
    }
    await repository.complete_order(retry.order_id, retry.attempt, payload)
    assert await repository.balance(issued.user_id) == Decimal("13")

    existing = await repository.reserve_order(
        user_id=issued.user_id,
        external_order_id="order-1",
        product_id=7,
        quantity=2,
        unit_price=Decimal("3.50"),
        currency="USD",
    )
    assert existing.kind is ReservationKind.COMPLETED
    assert existing.completed_order is not None
    assert existing.completed_order.provider_payload == payload
    assert existing.completed_order.unit_price == Decimal("3.50000000")
    assert existing.completed_order.total_amount == Decimal("7.00000000")
    assert await repository.balance(issued.user_id) == Decimal("13")


@pytest.mark.asyncio
async def test_sales_statistics_include_only_completed_orders(repository):
    issued = await repository.issue_user(
        telegram_user_id="sales-user",
        display_name="Sales User",
        address_candidates=["TSalesAddress11111111111111111111111"],
    )
    await repository.add_adjustment(
        user_id=issued.user_id,
        amount=Decimal("100"),
        description="sales test credit",
        reference="sales-test-credit",
    )
    completed = await repository.reserve_order(
        user_id=issued.user_id,
        external_order_id="completed-sale",
        product_id=7,
        quantity=3,
        unit_price=Decimal("2.50"),
        currency="USD",
    )
    await repository.complete_order(completed.order_id, completed.attempt, {"items": []})

    refunded = await repository.reserve_order(
        user_id=issued.user_id,
        external_order_id="refunded-sale",
        product_id=8,
        quantity=4,
        unit_price=Decimal("5"),
        currency="USD",
    )
    await repository.fail_order(refunded.order_id, refunded.attempt, "provider failed")
    await repository.reserve_order(
        user_id=issued.user_id,
        external_order_id="pending-sale",
        product_id=9,
        quantity=2,
        unit_price=Decimal("9"),
        currency="USD",
    )

    now = datetime.now(timezone.utc)
    statistics = await repository.sales_statistics(days=7, now=now)

    assert statistics.all_time.gross_sales == Decimal("7.50000000")
    assert statistics.all_time.completed_orders == 1
    assert statistics.all_time.accounts_sold == 3
    assert statistics.period == statistics.all_time
    assert statistics.today == statistics.all_time
    assert len(statistics.daily) == 7
    assert all(day.gross_sales == Decimal("0E-8") for day in statistics.daily[:-1])
    assert statistics.daily[-1].date == now.date()
    assert statistics.daily[-1].gross_sales == Decimal("7.50000000")


@pytest.mark.asyncio
async def test_deposit_statistics_include_only_confirmed_deposits(repository):
    issued = await repository.issue_user(
        telegram_user_id="deposit-user",
        display_name="Deposit User",
        address_candidates=["TDepositAddress111111111111111111111"],
    )
    event = dict(
        address=issued.address,
        network="tron",
        asset="USDT",
        required_confirmations=2,
    )
    await repository.record_deposit(
        event_id="pending-event",
        transaction_hash="pending-tx",
        event_index=0,
        amount=Decimal("50"),
        confirmations=1,
        payload={"confirmations": 1},
        **event,
    )
    await repository.record_deposit(
        event_id="confirmed-event",
        transaction_hash="confirmed-tx",
        event_index=0,
        amount=Decimal("25"),
        confirmations=2,
        payload={"confirmations": 2},
        **event,
    )
    await repository.add_adjustment(
        user_id=issued.user_id,
        amount=Decimal("10"),
        description="not a wallet deposit",
        reference="deposit-stats-adjustment",
    )

    now = datetime.now(timezone.utc)
    statistics = await repository.deposit_statistics(days=7, now=now)

    assert statistics.all_time.total_deposited == Decimal("25.00000000")
    assert statistics.all_time.deposit_count == 1
    assert statistics.period == statistics.all_time
    assert statistics.today == statistics.all_time
    assert len(statistics.daily) == 7
    assert all(
        day.total_deposited == Decimal("0E-8") for day in statistics.daily[:-1]
    )
    assert statistics.daily[-1].date == now.date()
    assert statistics.daily[-1].total_deposited == Decimal("25.00000000")


@pytest.mark.asyncio
async def test_order_rejects_insufficient_balance(repository):
    issued = await repository.issue_user(
        telegram_user_id=None,
        display_name="No Funds",
        address_candidates=["TTestAddress222222222222222222222222"],
    )
    with pytest.raises(InsufficientFundsError):
        await repository.reserve_order(
            user_id=issued.user_id,
            external_order_id="order-2",
            product_id=8,
            quantity=1,
            unit_price=Decimal("1"),
            currency="USD",
        )


@pytest.mark.asyncio
async def test_wallet_sweep_does_not_change_customer_ledger(repository):
    issued = await repository.issue_user(
        telegram_user_id="sweep-user",
        display_name="Sweep User",
        address_candidates=["TTestAddress333333333333333333333333"],
    )
    await repository.add_adjustment(
        user_id=issued.user_id,
        amount=Decimal("50"),
        description="confirmed deposit",
        reference="sweep-test-credit",
    )
    wallet = await repository.admin_wallet(issued.user_id)
    created = await repository.create_sweep(
        wallet=wallet,
        amount=Decimal("25"),
        destination_address="TTreasuryAddress111111111111111111111",
        idempotency_key="withdrawal-test-1",
        requested_by="admin@example.test",
        chain_balance_before=Decimal("50"),
    )
    assert created.created
    submitted = await repository.mark_sweep_submitted(
        created.sweep.id,
        transaction_hash="tx-sweep-1",
        transferred_amount=Decimal("25"),
        chain_balance_before=Decimal("50"),
        network_fee=Decimal("12.5"),
    )
    assert submitted.status == "submitted"
    await repository.mark_sweep_status(
        submitted.id,
        status="confirmed",
        chain_balance_after=Decimal("25"),
    )

    assert await repository.balance(issued.user_id) == Decimal("50")
    replay = await repository.create_sweep(
        wallet=wallet,
        amount=Decimal("25"),
        destination_address="TTreasuryAddress111111111111111111111",
        idempotency_key="withdrawal-test-1",
        requested_by="admin@example.test",
        chain_balance_before=Decimal("25"),
    )
    assert not replay.created
    assert replay.sweep.transaction_hash == "tx-sweep-1"


@pytest.mark.asyncio
async def test_retail_pricing_is_seeded_once_and_can_be_updated(repository):
    assert await repository.get_retail_pricing() is None

    seeded = await repository.ensure_retail_pricing(
        markup_percent=Decimal("20"),
        markup_fixed=Decimal("0.25"),
    )
    assert seeded == (Decimal("20.00000000"), Decimal("0.25000000"))
    assert await repository.get_retail_pricing() == seeded

    unchanged = await repository.ensure_retail_pricing(
        markup_percent=Decimal("1"),
        markup_fixed=Decimal("1"),
    )
    assert unchanged == seeded

    updated = await repository.set_retail_pricing(
        markup_percent=Decimal("10"),
        markup_fixed=Decimal("0.50"),
    )
    assert updated == (Decimal("10.00000000"), Decimal("0.50000000"))
    assert await repository.get_retail_pricing() == updated
