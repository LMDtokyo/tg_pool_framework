from __future__ import annotations

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from typing import Any

from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query

from payment_server.db.engine import build_session_factory_from_env
from payment_server.db.repository import (
    AdminWallet,
    AddressUnavailableError,
    CompletedOrder,
    ExistingUserError,
    InsufficientFundsError,
    OrderConflictError,
    PaymentRepository,
    ReservationKind,
    SweepConflictError,
    WalletNotFoundError,
    ensure_payment_tables,
    money,
)
from payment_server.pricing import RetailPricing
from payment_server.provider import DatamollProvider
from payment_server.schemas import (
    AdjustmentRequest,
    AdminUserSummaryOut,
    AdminUsersOut,
    AdminWalletOut,
    BalanceOut,
    CatalogOut,
    DailyDepositOut,
    DepositEventOut,
    DepositEventRequest,
    DepositStatisticsOut,
    DepositTotalOut,
    IssuedUserOut,
    IssueUserRequest,
    MeOut,
    OrderOut,
    OrderRequest,
    ProductOut,
    RegeneratedKeyOut,
    RetailPricingOut,
    RetailPricingUpdate,
    TreasuryWalletOut,
    TreasuryWalletUpdate,
    DailySalesOut,
    SalesStatisticsOut,
    SalesTotalOut,
    TransactionOut,
    TransactionsOut,
    WithdrawalOut,
    WithdrawalRequest,
    WithdrawalsOut,
)
from payment_server.signer import PaymentSignerClient, SignerError
from payment_server.telegram import notify_deposit

logger = logging.getLogger("payment_server")


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set")
    return value


@asynccontextmanager
async def lifespan(app: FastAPI):
    env_file = os.getenv("PAYMENT_ENV_FILE", str(Path(__file__).resolve().parent / ".env"))
    load_dotenv(env_file)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(name)s %(message)s",
    )
    active_surface = getattr(app.state, "active_surface", "combined")
    if active_surface in {"admin", "combined"}:
        _required_env("PAYMENT_ADMIN_API_KEY")
    if active_surface in {"webhook", "combined"}:
        _required_env("PAYMENT_WEBHOOK_KEY")
    session_factory = build_session_factory_from_env()
    await ensure_payment_tables(session_factory)
    app.state.repository = PaymentRepository(
        session_factory,
        currency=os.getenv("PAYMENT_CURRENCY", "USD").strip().upper(),
        network=os.getenv("PAYMENT_NETWORK", "tron").strip().lower(),
        asset=os.getenv("PAYMENT_ASSET", "USDT").strip().upper(),
    )
    app.state.provider = DatamollProvider()
    seeded = RetailPricing.from_env()
    percent, fixed = await app.state.repository.ensure_retail_pricing(
        markup_percent=seeded.markup_percent,
        markup_fixed=seeded.markup_fixed,
    )
    app.state.pricing = RetailPricing(markup_percent=percent, markup_fixed=fixed)
    app.state.signer = PaymentSignerClient()
    try:
        yield
    finally:
        await session_factory.kw["bind"].dispose()


app = FastAPI(title="tg_pool_framework payment authority", lifespan=lifespan)


def require_admin(x_admin_key: str = Header(default="")) -> None:
    expected = os.getenv("PAYMENT_ADMIN_API_KEY", "")
    if not expected or not secrets.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing admin key")


def require_webhook(x_webhook_key: str = Header(default="")) -> None:
    expected = os.getenv("PAYMENT_WEBHOOK_KEY", "")
    if not expected or not secrets.compare_digest(x_webhook_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing webhook key")


async def require_user(authorization: str = Header(default="")):
    scheme, _, api_key = authorization.partition(" ")
    if scheme.lower() != "bearer" or not api_key.strip():
        raise HTTPException(status_code=401, detail="Missing Bearer API key")
    repository: PaymentRepository = app.state.repository
    user = await repository.authenticate(api_key)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    return user


def _address_pool(explicit: str | None) -> list[str]:
    if explicit:
        return [explicit]
    return [
        address.strip()
        for address in os.getenv("PAYMENT_DEPOSIT_ADDRESSES", "").split(",")
        if address.strip()
    ]


def _product_out(product: dict[str, Any], pricing: RetailPricing) -> ProductOut:
    return ProductOut(
        product_id=int(product["product_id"]),
        name=str(product.get("name") or ""),
        price=format(pricing.price(product.get("price") or "0"), "f"),
        currency=str(product.get("currency") or "USD"),
        stock=max(0, int(product.get("stock") or 0)),
        min_order=max(1, int(product.get("min_order") or 1)),
        max_order=(
            int(product["max_order"]) if product.get("max_order") is not None else None
        ),
        category_name=product.get("category_name"),
        description=product.get("description"),
        country=product.get("country"),
        content_language=str(product.get("content_language") or ""),
    )


def _pricing_out(pricing: RetailPricing) -> RetailPricingOut:
    return RetailPricingOut(
        markup_percent=format(pricing.markup_percent, "f"),
        markup_fixed=format(pricing.markup_fixed, "f"),
    )


async def _current_pricing() -> RetailPricing:
    repository: PaymentRepository = app.state.repository
    stored = await repository.get_retail_pricing()
    if stored is None:
        pricing = RetailPricing.from_env()
        percent, fixed = await repository.ensure_retail_pricing(
            markup_percent=pricing.markup_percent,
            markup_fixed=pricing.markup_fixed,
        )
        pricing = RetailPricing(markup_percent=percent, markup_fixed=fixed)
    else:
        pricing = RetailPricing(markup_percent=stored[0], markup_fixed=stored[1])
    app.state.pricing = pricing
    return pricing


def _order_out(
    order: CompletedOrder, external_order_id: str, reused: bool
) -> OrderOut:
    payload = order.provider_payload
    items = payload.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Datamoll returned an order without delivered account data")
    return OrderOut(
        order_id=int(payload["order_id"]),
        external_order_id=external_order_id,
        status=str(payload.get("status") or "completed"),
        payment_status=str(payload.get("payment_status") or "paid"),
        product_id=int(payload["product_id"]),
        quantity=int(payload["quantity"]),
        unit_price=format(order.unit_price, "f"),
        total_amount=format(order.total_amount, "f"),
        currency=order.currency,
        items=items,
        reused_existing=reused or bool(payload.get("reused_existing")),
    )


def _optional_money(value) -> str | None:
    return format(value, "f") if value is not None else None


def _withdrawal_out(row) -> WithdrawalOut:
    return WithdrawalOut(
        id=row.id,
        user_id=row.user_id,
        source_address=row.source_address,
        destination_address=row.destination_address,
        requested_amount=format(row.requested_amount, "f"),
        transferred_amount=_optional_money(row.transferred_amount),
        asset=row.asset,
        network=row.network,
        status=row.status,
        transaction_hash=row.transaction_hash,
        chain_balance_before=_optional_money(row.chain_balance_before),
        chain_balance_after=_optional_money(row.chain_balance_after),
        network_fee=_optional_money(row.network_fee),
        requested_by=row.requested_by,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _finalize_withdrawal_from_chain(
    repository: PaymentRepository,
    signer: PaymentSignerClient,
    row,
    *,
    abandon_without_hash: bool = False,
):
    """Sync a withdrawal with chain status when a transaction hash exists."""
    if row.status in {"confirmed", "failed"}:
        return row
    if not row.transaction_hash:
        if not abandon_without_hash or row.status not in {"created", "review_required"}:
            return row
        return await repository.mark_sweep_status(
            row.id,
            status="failed",
            error_message=(
                row.error_message or "Abandoned: no transaction hash was recorded"
            ),
        )
    result = await signer.transaction(row.transaction_hash, row.source_address)
    status = (
        result.status
        if result.status in {"submitted", "confirmed", "failed"}
        else "submitted"
    )
    return await repository.mark_sweep_status(
        row.id,
        status=status,
        error_message=result.error_message,
        chain_balance_after=result.balance_after,
        network_fee=result.network_fee,
    )


async def _resolve_submitted_wallet_sweeps(
    repository: PaymentRepository,
    signer: PaymentSignerClient,
    wallet_id: int,
) -> None:
    """Promote prior submitted sweeps so a successful sweep no longer blocks the wallet."""
    pending = await repository.sweeps_for_wallet(wallet_id, statuses=("submitted",))
    for row in pending:
        try:
            await _finalize_withdrawal_from_chain(repository, signer, row)
        except SignerError:
            # Leave submitted in place; create_sweep will still conflict if unresolved.
            continue


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/admin/users",
    response_model=IssuedUserOut,
    dependencies=[Depends(require_admin)],
)
async def issue_user(body: IssueUserRequest) -> IssuedUserOut:
    repository: PaymentRepository = app.state.repository
    signer: PaymentSignerClient = app.state.signer
    try:
        if body.telegram_user_id:
            existing = await repository.user_by_telegram_id(body.telegram_user_id)
            if existing:
                await repository.update_telegram_profile(
                    body.telegram_user_id,
                    telegram_username=body.telegram_username,
                    display_name=body.display_name,
                )
                raise ExistingUserError("A payment account already exists")
        if body.deposit_address:
            address_candidates = [body.deposit_address]
        elif os.getenv("PAYMENT_AUTO_CREATE_WALLETS", "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            request_id = (
                f"telegram:{body.telegram_user_id}"
                if body.telegram_user_id
                else f"admin:{secrets.token_urlsafe(24)}"
            )
            wallet = await signer.create_wallet(request_id)
            expected_chain = (
                os.getenv("PAYMENT_CHAIN_NETWORK", "mainnet").strip().lower()
            )
            if wallet.network != expected_chain or wallet.asset != repository.asset:
                raise SignerError(
                    "Signer wallet network or asset does not match the payment service",
                    uncertain=False,
                )
            address_candidates = [wallet.address]
        else:
            address_candidates = _address_pool(None)
        issued = await repository.issue_user(
            telegram_user_id=body.telegram_user_id,
            telegram_username=body.telegram_username,
            display_name=body.display_name,
            address_candidates=address_candidates,
        )
    except ExistingUserError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AddressUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SignerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return IssuedUserOut(
        user_id=issued.user_id,
        api_key=issued.api_key,
        network=repository.network,
        asset=repository.asset,
        deposit_address=issued.address,
    )


@app.get(
    "/admin/telegram-users/{telegram_user_id}",
    response_model=MeOut,
    dependencies=[Depends(require_admin)],
)
async def telegram_user(telegram_user_id: str) -> MeOut:
    repository: PaymentRepository = app.state.repository
    user = await repository.user_by_telegram_id(telegram_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Payment account not found")
    return MeOut(
        user_id=user.id,
        telegram_user_id=user.telegram_user_id,
        telegram_username=user.telegram_username,
        display_name=user.display_name,
        deposit_address=user.wallet_address,
        network=user.network,
        asset=user.asset,
    )


@app.get(
    "/admin/users",
    response_model=AdminUsersOut,
    dependencies=[Depends(require_admin)],
)
async def admin_users(
    search: str = Query(default="", max_length=200),
    limit: int = Query(default=200, ge=1, le=500),
) -> AdminUsersOut:
    repository: PaymentRepository = app.state.repository
    signer: PaymentSignerClient = app.state.signer
    users = await repository.admin_users(search=search, limit=limit)
    semaphore = asyncio.Semaphore(10)

    async def load_chain_balances(user):
        async with semaphore:
            try:
                balances = await signer.wallet_balances(user.address)
                return (
                    format(money(balances.token_balance), "f"),
                    format(money(balances.trx_balance), "f"),
                    "",
                )
            except SignerError as exc:
                return None, None, str(exc)

    chain_results = await asyncio.gather(
        *(load_chain_balances(user) for user in users)
    )
    return AdminUsersOut(
        items=[
            AdminUserSummaryOut(
                user_id=user.user_id,
                telegram_user_id=user.telegram_user_id,
                telegram_username=user.telegram_username,
                display_name=user.display_name,
                disabled=user.disabled,
                address=user.address,
                network=user.network,
                asset=user.asset,
                on_chain_balance=chain_balance,
                trx_balance=trx_balance,
                chain_error=chain_error,
                database_balance=format(user.database_balance, "f"),
                currency=repository.currency,
                total_accounts_purchased=user.total_accounts_purchased,
                total_amount_paid=format(user.total_amount_paid, "f"),
            )
            for user, (chain_balance, trx_balance, chain_error) in zip(
                users, chain_results
            )
        ]
    )


@app.get(
    "/admin/statistics/sales",
    response_model=SalesStatisticsOut,
    dependencies=[Depends(require_admin)],
)
async def sales_statistics(
    days: int = Query(default=30),
) -> SalesStatisticsOut:
    if days not in {7, 30, 90}:
        raise HTTPException(status_code=422, detail="days must be one of 7, 30, or 90")
    repository: PaymentRepository = app.state.repository
    statistics = await repository.sales_statistics(days=days)

    def total_out(total) -> SalesTotalOut:
        return SalesTotalOut(
            gross_sales=format(total.gross_sales, "f"),
            completed_orders=total.completed_orders,
            accounts_sold=total.accounts_sold,
        )

    return SalesStatisticsOut(
        days=statistics.days,
        currency=repository.currency,
        today=total_out(statistics.today),
        period=total_out(statistics.period),
        all_time=total_out(statistics.all_time),
        daily=[
            DailySalesOut(
                date=item.date.isoformat(),
                gross_sales=format(item.gross_sales, "f"),
                completed_orders=item.completed_orders,
                accounts_sold=item.accounts_sold,
            )
            for item in statistics.daily
        ],
    )


@app.get(
    "/admin/statistics/deposits",
    response_model=DepositStatisticsOut,
    dependencies=[Depends(require_admin)],
)
async def deposit_statistics(
    days: int = Query(default=30),
) -> DepositStatisticsOut:
    if days not in {7, 30, 90}:
        raise HTTPException(status_code=422, detail="days must be one of 7, 30, or 90")
    repository: PaymentRepository = app.state.repository
    statistics = await repository.deposit_statistics(days=days)

    def total_out(total) -> DepositTotalOut:
        return DepositTotalOut(
            total_deposited=format(total.total_deposited, "f"),
            deposit_count=total.deposit_count,
        )

    return DepositStatisticsOut(
        days=statistics.days,
        asset=repository.asset,
        today=total_out(statistics.today),
        period=total_out(statistics.period),
        all_time=total_out(statistics.all_time),
        daily=[
            DailyDepositOut(
                date=item.date.isoformat(),
                total_deposited=format(item.total_deposited, "f"),
                deposit_count=item.deposit_count,
            )
            for item in statistics.daily
        ],
    )


@app.get(
    "/admin/telegram-users/{telegram_user_id}/balance",
    response_model=BalanceOut,
    dependencies=[Depends(require_admin)],
)
async def telegram_user_balance(telegram_user_id: str) -> BalanceOut:
    repository: PaymentRepository = app.state.repository
    user = await repository.user_by_telegram_id(telegram_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Payment account not found")
    value = format(await repository.balance(user.id), "f")
    return BalanceOut(
        balance=value,
        available_balance=value,
        currency=repository.currency,
    )


@app.post(
    "/admin/telegram-users/{telegram_user_id}/regenerate-key",
    response_model=RegeneratedKeyOut,
    dependencies=[Depends(require_admin)],
)
async def regenerate_telegram_user_key(telegram_user_id: str) -> RegeneratedKeyOut:
    repository: PaymentRepository = app.state.repository
    user = await repository.user_by_telegram_id(telegram_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Payment account not found")
    return RegeneratedKeyOut(api_key=await repository.regenerate_api_key(user.id))


@app.get("/v1/me", response_model=MeOut)
async def me(user=Depends(require_user)) -> MeOut:
    return MeOut(
        user_id=user.id,
        telegram_user_id=user.telegram_user_id,
        telegram_username=user.telegram_username,
        display_name=user.display_name,
        deposit_address=user.wallet_address,
        network=user.network,
        asset=user.asset,
    )


@app.get("/v1/balance", response_model=BalanceOut)
async def balance(user=Depends(require_user)) -> BalanceOut:
    repository: PaymentRepository = app.state.repository
    value = await repository.balance(user.id)
    formatted = format(value, "f")
    return BalanceOut(
        balance=formatted,
        available_balance=formatted,
        currency=repository.currency,
    )


@app.get("/v1/transactions", response_model=TransactionsOut)
async def transactions(
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(require_user),
) -> TransactionsOut:
    repository: PaymentRepository = app.state.repository
    rows = await repository.transactions(user.id, limit=limit)
    return TransactionsOut(
        items=[
            TransactionOut(
                amount=format(row.amount, "f"),
                currency=row.currency,
                entry_type=row.entry_type,
                description=row.description,
                created_at=row.created_at,
            )
            for row in rows
        ]
    )


@app.post("/v1/api-keys/regenerate", response_model=RegeneratedKeyOut)
async def regenerate_key(user=Depends(require_user)) -> RegeneratedKeyOut:
    repository: PaymentRepository = app.state.repository
    return RegeneratedKeyOut(api_key=await repository.regenerate_api_key(user.id))


@app.post(
    "/admin/users/{user_id}/revoke-keys",
    dependencies=[Depends(require_admin)],
)
async def revoke_user_keys(user_id: int) -> dict[str, str]:
    repository: PaymentRepository = app.state.repository
    if not await repository.revoke_api_keys(user_id):
        raise HTTPException(status_code=404, detail="No active API key found")
    return {"status": "revoked"}


@app.get(
    "/admin/users/{user_id}/wallet",
    response_model=AdminWalletOut,
    dependencies=[Depends(require_admin)],
)
async def admin_wallet(user_id: int) -> AdminWalletOut:
    repository: PaymentRepository = app.state.repository
    signer: PaymentSignerClient = app.state.signer
    try:
        wallet = await repository.admin_wallet(user_id)
        chain_balance = money(await signer.balance(wallet.address))
    except WalletNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SignerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    database_balance = await repository.balance(user_id)
    return AdminWalletOut(
        user_id=wallet.user_id,
        telegram_user_id=wallet.telegram_user_id,
        display_name=wallet.display_name,
        address=wallet.address,
        network=wallet.network,
        asset=wallet.asset,
        on_chain_balance=format(chain_balance, "f"),
        database_balance=format(database_balance, "f"),
        currency=repository.currency,
    )


@app.post(
    "/admin/users/{user_id}/withdrawals",
    response_model=WithdrawalOut,
    dependencies=[Depends(require_admin)],
)
async def withdraw_user_wallet(
    user_id: int,
    body: WithdrawalRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    x_admin_actor: str = Header(default="admin"),
) -> WithdrawalOut:
    repository: PaymentRepository = app.state.repository
    signer: PaymentSignerClient = app.state.signer
    try:
        signer_config = await signer.config()
    except SignerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    treasury_address = signer_config.treasury_address
    normalized_idempotency_key = idempotency_key.strip()

    existing = await repository.sweep_by_idempotency_key(normalized_idempotency_key)
    if existing is not None:
        if existing.user_id != user_id:
            raise HTTPException(
                status_code=409,
                detail="Idempotency key was already used for another withdrawal",
            )
        if body.amount is not None:
            try:
                requested = money(body.amount)
            except (InvalidOperation, ValueError) as exc:
                raise HTTPException(status_code=422, detail="Invalid withdrawal amount") from exc
            if requested != money(existing.requested_amount):
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key was already used with another amount",
                )
        return _withdrawal_out(existing)

    try:
        wallet: AdminWallet = await repository.admin_wallet(user_id)
        if signer_config.asset != wallet.asset:
            raise HTTPException(
                status_code=503,
                detail="Payment server and signer assets do not match",
            )
        expected_chain_network = os.getenv("PAYMENT_CHAIN_NETWORK", "mainnet").strip().lower()
        if signer_config.network != expected_chain_network:
            raise HTTPException(
                status_code=503,
                detail="Payment server and signer chain networks do not match",
            )
        await _resolve_submitted_wallet_sweeps(repository, signer, wallet.wallet_id)
        chain_balance = money(await signer.balance(wallet.address))
        amount = money(body.amount) if body.amount is not None else chain_balance
        if amount <= 0:
            raise HTTPException(status_code=409, detail="Wallet has no withdrawable balance")
        if amount > chain_balance:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Requested amount {amount} exceeds on-chain balance {chain_balance}"
                ),
            )
        creation = await repository.create_sweep(
            wallet=wallet,
            amount=amount,
            destination_address=treasury_address,
            idempotency_key=normalized_idempotency_key,
            requested_by=x_admin_actor,
            chain_balance_before=chain_balance,
        )
        if not creation.created:
            return _withdrawal_out(creation.sweep)
    except HTTPException:
        raise
    except WalletNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SweepConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid withdrawal amount") from exc
    except SignerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        result = await signer.sweep(
            sweep_id=creation.sweep.id,
            source_address=wallet.address,
            amount=amount,
        )
        if result.destination_address != treasury_address:
            await repository.mark_sweep_status(
                creation.sweep.id,
                status="review_required",
                error_message="Signer returned an unexpected treasury destination",
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "withdrawal_id": creation.sweep.id,
                    "status": "review_required",
                    "message": "Signer returned an unexpected treasury destination",
                },
            )
        row = await repository.mark_sweep_submitted(
            creation.sweep.id,
            transaction_hash=result.transaction_hash,
            transferred_amount=result.amount,
            chain_balance_before=result.balance_before,
            network_fee=result.network_fee,
        )
        try:
            row = await _finalize_withdrawal_from_chain(repository, signer, row)
        except SignerError:
            # Broadcast succeeded; confirmation can be completed on the next withdraw/refresh.
            pass
        return _withdrawal_out(row)
    except SignerError as exc:
        status = "review_required" if exc.uncertain else "failed"
        await repository.mark_sweep_status(
            creation.sweep.id,
            status=status,
            error_message=str(exc),
        )
        code = 503 if exc.uncertain else 422
        raise HTTPException(
            status_code=code,
            detail={"withdrawal_id": creation.sweep.id, "status": status, "message": str(exc)},
        ) from exc


@app.get(
    "/admin/withdrawals",
    response_model=WithdrawalsOut,
    dependencies=[Depends(require_admin)],
)
async def list_withdrawals(
    limit: int = Query(default=50, ge=1, le=200),
) -> WithdrawalsOut:
    repository: PaymentRepository = app.state.repository
    return WithdrawalsOut(
        items=[_withdrawal_out(row) for row in await repository.sweeps(limit=limit)]
    )


@app.post(
    "/admin/withdrawals/{withdrawal_id}/refresh",
    response_model=WithdrawalOut,
    dependencies=[Depends(require_admin)],
)
async def refresh_withdrawal(withdrawal_id: int) -> WithdrawalOut:
    repository: PaymentRepository = app.state.repository
    signer: PaymentSignerClient = app.state.signer
    try:
        row = await repository.sweep(withdrawal_id)
    except WalletNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if row.status in {"confirmed", "failed"}:
        return _withdrawal_out(row)
    if not row.transaction_hash and row.status not in {"created", "review_required"}:
        raise HTTPException(
            status_code=409,
            detail="Withdrawal has no transaction hash and cannot be refreshed",
        )
    try:
        row = await _finalize_withdrawal_from_chain(
            repository,
            signer,
            row,
            abandon_without_hash=True,
        )
    except SignerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if row.status not in {"confirmed", "failed"} and not row.transaction_hash:
        raise HTTPException(
            status_code=409,
            detail="Withdrawal has no transaction hash and cannot be refreshed",
        )
    return _withdrawal_out(row)


@app.get("/v1/products", response_model=CatalogOut)
async def products(user=Depends(require_user)) -> CatalogOut:
    del user
    provider: DatamollProvider = app.state.provider
    pricing = await _current_pricing()
    repository: PaymentRepository = app.state.repository
    try:
        catalog = await provider.catalog()
        await repository.cache_products(catalog)
        return CatalogOut(items=[_product_out(product, pricing) for product in catalog])
    except Exception as exc:
        logger.warning("Provider catalog request failed: %s", exc)
        cached = await repository.cached_products()
        if cached:
            return CatalogOut(items=[_product_out(product, pricing) for product in cached])
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/orders", response_model=OrderOut)
async def create_order(body: OrderRequest, user=Depends(require_user)) -> OrderOut:
    provider: DatamollProvider = app.state.provider
    pricing = await _current_pricing()
    repository: PaymentRepository = app.state.repository
    try:
        existing = await repository.completed_order(
            user_id=user.id,
            external_order_id=body.external_order_id.strip(),
            product_id=body.product_id,
            quantity=body.quantity,
        )
        if existing is not None:
            return _order_out(existing, body.external_order_id, True)
        catalog = await provider.catalog()
        await repository.cache_products(catalog)
        product = next(
            (item for item in catalog if int(item.get("product_id") or 0) == body.product_id),
            None,
        )
        if product is None:
            raise HTTPException(status_code=404, detail="Product is unavailable")
        stock = int(product.get("stock") or 0)
        minimum = max(1, int(product.get("min_order") or 1))
        maximum = int(product.get("max_order") or stock)
        if body.quantity < minimum or body.quantity > min(stock, maximum):
            raise HTTPException(status_code=409, detail="Requested quantity is unavailable")
        unit_price = pricing.price(product.get("price") or "0")
        currency = str(product.get("currency") or repository.currency).upper()
        reservation = await repository.reserve_order(
            user_id=user.id,
            external_order_id=body.external_order_id.strip(),
            product_id=body.product_id,
            quantity=body.quantity,
            unit_price=unit_price,
            currency=currency,
        )
        if reservation.kind is ReservationKind.COMPLETED:
            assert reservation.completed_order is not None
            return _order_out(reservation.completed_order, body.external_order_id, True)
    except HTTPException:
        raise
    except InsufficientFundsError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except OrderConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Invalid provider price: {exc}") from exc
    except Exception as exc:
        logger.warning("Unable to prepare order %s: %s", body.external_order_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        payload = await provider.create_order(
            product_id=body.product_id,
            quantity=body.quantity,
            external_order_id=f"tgpool-payment-{reservation.order_id}",
        )
        completed = await repository.complete_order(
            reservation.order_id, reservation.attempt, payload
        )
        return _order_out(
            completed,
            body.external_order_id,
            reservation.kind is ReservationKind.RETRY,
        )
    except Exception as exc:
        await repository.fail_order(reservation.order_id, reservation.attempt, str(exc))
        logger.warning("Order %s failed and was refunded: %s", body.external_order_id, exc)
        raise HTTPException(
            status_code=502,
            detail=f"Provider order failed; reserved funds were refunded: {exc}",
        ) from exc


@app.post(
    "/webhooks/tron/deposits",
    response_model=DepositEventOut,
    dependencies=[Depends(require_webhook)],
)
async def tron_deposit(body: DepositEventRequest) -> DepositEventOut:
    repository: PaymentRepository = app.state.repository
    try:
        amount = money(body.amount)
        result = await repository.record_deposit(
            event_id=body.event_id,
            payload=body.model_dump(),
            address=body.address,
            network=body.network.lower(),
            asset=body.asset.upper(),
            transaction_hash=body.transaction_hash,
            event_index=body.event_index,
            amount=amount,
            confirmations=body.confirmations,
            required_confirmations=max(
                1, int(os.getenv("PAYMENT_REQUIRED_CONFIRMATIONS", "20"))
            ),
        )
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result.newly_credited:
        await notify_deposit(
            telegram_user_id=result.telegram_user_id,
            amount=format(amount, "f"),
            asset=body.asset.upper(),
            transaction_hash=body.transaction_hash,
        )
    return DepositEventOut(
        status=result.status,
        credited=result.credited,
        duplicate=result.duplicate,
        newly_credited=result.newly_credited,
    )


@app.get(
    "/admin/pricing",
    response_model=RetailPricingOut,
    dependencies=[Depends(require_admin)],
)
async def get_pricing() -> RetailPricingOut:
    return _pricing_out(await _current_pricing())


@app.put(
    "/admin/pricing",
    response_model=RetailPricingOut,
    dependencies=[Depends(require_admin)],
)
async def update_pricing(body: RetailPricingUpdate) -> RetailPricingOut:
    repository: PaymentRepository = app.state.repository
    try:
        pricing = RetailPricing.from_values(body.markup_percent, body.markup_fixed)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    percent, fixed = await repository.set_retail_pricing(
        markup_percent=pricing.markup_percent,
        markup_fixed=pricing.markup_fixed,
    )
    updated = RetailPricing(markup_percent=percent, markup_fixed=fixed)
    app.state.pricing = updated
    return _pricing_out(updated)


@app.get(
    "/admin/treasury-wallet",
    response_model=TreasuryWalletOut,
    dependencies=[Depends(require_admin)],
)
async def get_treasury_wallet() -> TreasuryWalletOut:
    signer: PaymentSignerClient = app.state.signer
    try:
        config = await signer.config()
        balances = await signer.wallet_balances(config.treasury_address)
    except SignerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TreasuryWalletOut(
        address=config.treasury_address,
        network=config.network,
        asset=config.asset,
        on_chain_balance=format(money(balances.token_balance), "f"),
        trx_balance=format(money(balances.trx_balance), "f"),
    )


@app.put(
    "/admin/treasury-wallet",
    response_model=TreasuryWalletOut,
    dependencies=[Depends(require_admin)],
)
async def update_treasury_wallet(body: TreasuryWalletUpdate) -> TreasuryWalletOut:
    signer: PaymentSignerClient = app.state.signer
    try:
        config = await signer.update_treasury(body.address.strip())
        balances = await signer.wallet_balances(config.treasury_address)
    except SignerError as exc:
        status = 503 if exc.uncertain else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return TreasuryWalletOut(
        address=config.treasury_address,
        network=config.network,
        asset=config.asset,
        on_chain_balance=format(money(balances.token_balance), "f"),
        trx_balance=format(money(balances.trx_balance), "f"),
    )


@app.post(
    "/admin/adjustments",
    dependencies=[Depends(require_admin)],
)
async def adjustment(body: AdjustmentRequest) -> dict[str, str]:
    repository: PaymentRepository = app.state.repository
    try:
        amount = money(body.amount)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid adjustment amount") from exc
    if amount == Decimal("0"):
        raise HTTPException(status_code=422, detail="Adjustment amount cannot be zero")
    reference = secrets.token_hex(16)
    await repository.add_adjustment(
        user_id=body.user_id,
        amount=amount,
        description=body.description,
        reference=reference,
    )
    return {"status": "recorded", "reference": reference}
