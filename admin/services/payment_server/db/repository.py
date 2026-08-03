from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Optional

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from payment_server.db.models import (
    ApiKeyRow,
    Base,
    DepositRow,
    LedgerEntryRow,
    OrderRow,
    ProductRow,
    ProviderOrderRow,
    RetailPricingRow,
    UserRow,
    WalletRow,
    WalletSweepRow,
    WebhookEventRow,
)
from payment_server.keycodes import generate_api_key, hash_api_key, last4


MONEY_QUANTUM = Decimal("0.00000001")


def money(value: Any) -> Decimal:
    result = Decimal(str(value)).quantize(MONEY_QUANTUM)
    if not result.is_finite():
        raise ValueError("Amount must be finite")
    return result


async def ensure_payment_tables(session_factory: async_sessionmaker) -> None:
    engine = session_factory.kw["bind"]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


class ExistingUserError(RuntimeError):
    pass


class AddressUnavailableError(RuntimeError):
    pass


class InsufficientFundsError(RuntimeError):
    pass


class OrderConflictError(RuntimeError):
    pass


class SweepConflictError(RuntimeError):
    pass


class WalletNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class IssuedUser:
    user_id: int
    api_key: str
    address: str


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    telegram_user_id: Optional[str]
    telegram_username: Optional[str]
    display_name: str
    wallet_address: str
    network: str
    asset: str


class ReservationKind(str, Enum):
    NEW = "new"
    RETRY = "retry"
    COMPLETED = "completed"


@dataclass(frozen=True)
class OrderReservation:
    kind: ReservationKind
    order_id: int
    attempt: int
    completed_order: Optional["CompletedOrder"] = None


@dataclass(frozen=True)
class CompletedOrder:
    provider_payload: dict[str, Any]
    unit_price: Decimal
    total_amount: Decimal
    currency: str


@dataclass(frozen=True)
class DepositResult:
    status: str
    credited: bool
    duplicate: bool
    newly_credited: bool = False
    user_id: Optional[int] = None
    telegram_user_id: Optional[str] = None


@dataclass(frozen=True)
class AdminWallet:
    user_id: int
    telegram_user_id: Optional[str]
    display_name: str
    wallet_id: int
    address: str
    network: str
    asset: str


@dataclass(frozen=True)
class AdminUserSummary:
    user_id: int
    telegram_user_id: Optional[str]
    telegram_username: Optional[str]
    display_name: str
    disabled: bool
    address: str
    network: str
    asset: str
    database_balance: Decimal
    total_accounts_purchased: int
    total_amount_paid: Decimal


@dataclass(frozen=True)
class SalesTotal:
    gross_sales: Decimal
    completed_orders: int
    accounts_sold: int


@dataclass(frozen=True)
class DailySales:
    date: date
    gross_sales: Decimal
    completed_orders: int
    accounts_sold: int


@dataclass(frozen=True)
class SalesStatistics:
    days: int
    all_time: SalesTotal
    period: SalesTotal
    today: SalesTotal
    daily: list[DailySales]


@dataclass(frozen=True)
class DepositTotal:
    total_deposited: Decimal
    deposit_count: int


@dataclass(frozen=True)
class DailyDeposit:
    date: date
    total_deposited: Decimal
    deposit_count: int


@dataclass(frozen=True)
class DepositStatistics:
    days: int
    all_time: DepositTotal
    period: DepositTotal
    today: DepositTotal
    daily: list[DailyDeposit]


@dataclass(frozen=True)
class SweepCreation:
    sweep: WalletSweepRow
    created: bool


class PaymentRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        *,
        currency: str = "USD",
        network: str = "tron",
        asset: str = "USDT",
    ) -> None:
        self._session_factory = session_factory
        self.currency = currency
        self.network = network
        self.asset = asset

    async def issue_user(
        self,
        *,
        telegram_user_id: Optional[str],
        display_name: str,
        address_candidates: Iterable[str],
        telegram_username: Optional[str] = None,
    ) -> IssuedUser:
        candidates = [item.strip() for item in address_candidates if item.strip()]
        if not candidates:
            raise AddressUnavailableError("No deposit address is available")

        api_key = generate_api_key()
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    if telegram_user_id:
                        existing = await session.scalar(
                            select(UserRow.id).where(
                                UserRow.telegram_user_id == telegram_user_id
                            )
                        )
                        if existing is not None:
                            raise ExistingUserError("A payment account already exists")

                    used = set(
                        (
                            await session.execute(
                                select(WalletRow.address).where(
                                    WalletRow.network == self.network,
                                    WalletRow.address.in_(candidates),
                                )
                            )
                        ).scalars()
                    )
                    address = next(
                        (candidate for candidate in candidates if candidate not in used), None
                    )
                    if address is None:
                        raise AddressUnavailableError("No unused deposit address is available")

                    user = UserRow(
                        telegram_user_id=telegram_user_id,
                        telegram_username=(telegram_username or "").strip() or None,
                        display_name=display_name.strip(),
                    )
                    session.add(user)
                    await session.flush()
                    session.add_all(
                        [
                            ApiKeyRow(
                                user_id=user.id,
                                key_hash=hash_api_key(api_key),
                                key_last4=last4(api_key),
                            ),
                            WalletRow(
                                user_id=user.id,
                                network=self.network,
                                asset=self.asset,
                                address=address,
                            ),
                        ]
                    )
                    user_id = user.id
        except IntegrityError as exc:
            raise ExistingUserError("User or deposit address already exists") from exc
        return IssuedUser(user_id=user_id, api_key=api_key, address=address)

    async def user_by_telegram_id(
        self, telegram_user_id: str
    ) -> Optional[AuthenticatedUser]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(UserRow, WalletRow)
                .join(WalletRow, WalletRow.user_id == UserRow.id)
                .where(UserRow.telegram_user_id == telegram_user_id)
            )
            row = result.one_or_none()
            if row is None:
                return None
            user, wallet = row
            return AuthenticatedUser(
                id=user.id,
                telegram_user_id=user.telegram_user_id,
                telegram_username=user.telegram_username,
                display_name=user.display_name,
                wallet_address=wallet.address,
                network=wallet.network,
                asset=wallet.asset,
            )

    async def update_telegram_profile(
        self,
        telegram_user_id: str,
        *,
        telegram_username: Optional[str],
        display_name: str,
    ) -> None:
        values: dict[str, Any] = {}
        if telegram_username and telegram_username.strip():
            values["telegram_username"] = telegram_username.strip().lstrip("@")
        if display_name.strip():
            values["display_name"] = display_name.strip()
        if not values:
            return
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(UserRow)
                    .where(UserRow.telegram_user_id == telegram_user_id)
                    .values(**values)
                )

    async def admin_users(
        self, *, search: str = "", limit: int = 200
    ) -> list[AdminUserSummary]:
        ledger_totals = (
            select(
                LedgerEntryRow.user_id.label("user_id"),
                func.coalesce(func.sum(LedgerEntryRow.amount), 0).label("balance"),
            )
            .where(LedgerEntryRow.currency == self.currency)
            .group_by(LedgerEntryRow.user_id)
            .subquery()
        )
        order_totals = (
            select(
                OrderRow.user_id.label("user_id"),
                func.coalesce(func.sum(OrderRow.quantity), 0).label("accounts"),
                func.coalesce(func.sum(OrderRow.total_amount), 0).label("paid"),
            )
            .where(
                OrderRow.status == "completed",
                OrderRow.currency == self.currency,
            )
            .group_by(OrderRow.user_id)
            .subquery()
        )
        statement = (
            select(
                UserRow,
                WalletRow,
                func.coalesce(ledger_totals.c.balance, 0),
                func.coalesce(order_totals.c.accounts, 0),
                func.coalesce(order_totals.c.paid, 0),
            )
            .join(WalletRow, WalletRow.user_id == UserRow.id)
            .outerjoin(ledger_totals, ledger_totals.c.user_id == UserRow.id)
            .outerjoin(order_totals, order_totals.c.user_id == UserRow.id)
            .where(
                WalletRow.network == self.network,
                WalletRow.asset == self.asset,
            )
            .order_by(UserRow.id.desc())
            .limit(limit)
        )
        normalized = search.strip()
        if normalized:
            pattern = f"%{normalized}%"
            filters = [
                UserRow.telegram_user_id.ilike(pattern),
                UserRow.telegram_username.ilike(pattern),
                UserRow.display_name.ilike(pattern),
                WalletRow.address.ilike(pattern),
            ]
            if normalized.isdigit():
                filters.append(UserRow.id == int(normalized))
            statement = statement.where(or_(*filters))
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
            return [
                AdminUserSummary(
                    user_id=user.id,
                    telegram_user_id=user.telegram_user_id,
                    telegram_username=user.telegram_username,
                    display_name=user.display_name,
                    disabled=user.disabled,
                    address=wallet.address,
                    network=wallet.network,
                    asset=wallet.asset,
                    database_balance=money(database_balance),
                    total_accounts_purchased=int(accounts),
                    total_amount_paid=money(paid),
                )
                for user, wallet, database_balance, accounts, paid in rows
            ]

    async def sales_statistics(
        self, *, days: int, now: Optional[datetime] = None
    ) -> SalesStatistics:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        first_date = current.date() - timedelta(days=days - 1)
        period_start = datetime.combine(first_date, time.min, tzinfo=timezone.utc)
        completed = (
            OrderRow.status == "completed",
            OrderRow.currency == self.currency,
        )
        engine = self._session_factory.kw["bind"]
        sale_date_expression = (
            func.date(func.timezone("UTC", OrderRow.updated_at))
            if engine.dialect.name == "postgresql"
            else func.date(OrderRow.updated_at)
        )
        totals = select(
            func.coalesce(func.sum(OrderRow.total_amount), 0),
            func.count(OrderRow.id),
            func.coalesce(func.sum(OrderRow.quantity), 0),
        ).where(*completed)
        daily_statement = (
            select(
                sale_date_expression.label("sale_date"),
                func.coalesce(func.sum(OrderRow.total_amount), 0),
                func.count(OrderRow.id),
                func.coalesce(func.sum(OrderRow.quantity), 0),
            )
            .where(*completed, OrderRow.updated_at >= period_start)
            .group_by(sale_date_expression)
            .order_by(sale_date_expression)
        )
        async with self._session_factory() as session:
            all_time_row = (await session.execute(totals)).one()
            daily_rows = (await session.execute(daily_statement)).all()

        by_date: dict[date, SalesTotal] = {}
        for raw_date, gross_sales, completed_orders, accounts_sold in daily_rows:
            sale_date = (
                raw_date
                if isinstance(raw_date, date)
                else date.fromisoformat(str(raw_date))
            )
            by_date[sale_date] = SalesTotal(
                gross_sales=money(gross_sales),
                completed_orders=int(completed_orders),
                accounts_sold=int(accounts_sold),
            )

        zero = SalesTotal(Decimal("0").quantize(MONEY_QUANTUM), 0, 0)
        daily = [
            DailySales(
                date=day,
                gross_sales=by_date.get(day, zero).gross_sales,
                completed_orders=by_date.get(day, zero).completed_orders,
                accounts_sold=by_date.get(day, zero).accounts_sold,
            )
            for day in (first_date + timedelta(days=index) for index in range(days))
        ]
        period = SalesTotal(
            gross_sales=money(sum((item.gross_sales for item in daily), Decimal("0"))),
            completed_orders=sum(item.completed_orders for item in daily),
            accounts_sold=sum(item.accounts_sold for item in daily),
        )
        all_time = SalesTotal(
            gross_sales=money(all_time_row[0]),
            completed_orders=int(all_time_row[1]),
            accounts_sold=int(all_time_row[2]),
        )
        today = by_date.get(current.date(), zero)
        return SalesStatistics(
            days=days,
            all_time=all_time,
            period=period,
            today=today,
            daily=daily,
        )

    async def deposit_statistics(
        self, *, days: int, now: Optional[datetime] = None
    ) -> DepositStatistics:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        first_date = current.date() - timedelta(days=days - 1)
        period_start = datetime.combine(first_date, time.min, tzinfo=timezone.utc)
        confirmed = (
            DepositRow.status == "confirmed",
            DepositRow.credited_at.isnot(None),
            DepositRow.network == self.network,
            DepositRow.asset == self.asset,
        )
        engine = self._session_factory.kw["bind"]
        deposit_date_expression = (
            func.date(func.timezone("UTC", DepositRow.credited_at))
            if engine.dialect.name == "postgresql"
            else func.date(DepositRow.credited_at)
        )
        totals = select(
            func.coalesce(func.sum(DepositRow.amount), 0),
            func.count(DepositRow.id),
        ).where(*confirmed)
        daily_statement = (
            select(
                deposit_date_expression.label("deposit_date"),
                func.coalesce(func.sum(DepositRow.amount), 0),
                func.count(DepositRow.id),
            )
            .where(*confirmed, DepositRow.credited_at >= period_start)
            .group_by(deposit_date_expression)
            .order_by(deposit_date_expression)
        )
        async with self._session_factory() as session:
            all_time_row = (await session.execute(totals)).one()
            daily_rows = (await session.execute(daily_statement)).all()

        by_date: dict[date, DepositTotal] = {}
        for raw_date, total_deposited, deposit_count in daily_rows:
            deposit_date = (
                raw_date
                if isinstance(raw_date, date)
                else date.fromisoformat(str(raw_date))
            )
            by_date[deposit_date] = DepositTotal(
                total_deposited=money(total_deposited),
                deposit_count=int(deposit_count),
            )

        zero = DepositTotal(Decimal("0").quantize(MONEY_QUANTUM), 0)
        daily = [
            DailyDeposit(
                date=day,
                total_deposited=by_date.get(day, zero).total_deposited,
                deposit_count=by_date.get(day, zero).deposit_count,
            )
            for day in (first_date + timedelta(days=index) for index in range(days))
        ]
        period = DepositTotal(
            total_deposited=money(
                sum((item.total_deposited for item in daily), Decimal("0"))
            ),
            deposit_count=sum(item.deposit_count for item in daily),
        )
        all_time = DepositTotal(
            total_deposited=money(all_time_row[0]),
            deposit_count=int(all_time_row[1]),
        )
        today = by_date.get(current.date(), zero)
        return DepositStatistics(
            days=days,
            all_time=all_time,
            period=period,
            today=today,
            daily=daily,
        )

    async def wallet_addresses(self) -> list[str]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(WalletRow.address)
                .where(
                    WalletRow.network == self.network,
                    WalletRow.asset == self.asset,
                )
                .order_by(WalletRow.id)
            )
            return list(rows)

    async def authenticate(self, api_key: str) -> Optional[AuthenticatedUser]:
        key_hash = hash_api_key(api_key)
        now = datetime.now(timezone.utc)
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(ApiKeyRow, UserRow, WalletRow)
                    .join(UserRow, UserRow.id == ApiKeyRow.user_id)
                    .join(WalletRow, WalletRow.user_id == UserRow.id)
                    .where(
                        ApiKeyRow.key_hash == key_hash,
                        ApiKeyRow.revoked.is_(False),
                        UserRow.disabled.is_(False),
                    )
                )
                row = result.one_or_none()
                if row is None:
                    return None
                key, user, wallet = row
                key.last_used_at = now
                return AuthenticatedUser(
                    id=user.id,
                    telegram_user_id=user.telegram_user_id,
                    telegram_username=user.telegram_username,
                    display_name=user.display_name,
                    wallet_address=wallet.address,
                    network=wallet.network,
                    asset=wallet.asset,
                )

    async def regenerate_api_key(self, user_id: int) -> str:
        api_key = generate_api_key()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(ApiKeyRow)
                    .where(ApiKeyRow.user_id == user_id, ApiKeyRow.revoked.is_(False))
                    .values(revoked=True)
                )
                session.add(
                    ApiKeyRow(
                        user_id=user_id,
                        key_hash=hash_api_key(api_key),
                        key_last4=last4(api_key),
                    )
                )
        return api_key

    async def revoke_api_keys(self, user_id: int) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(ApiKeyRow)
                    .where(ApiKeyRow.user_id == user_id, ApiKeyRow.revoked.is_(False))
                    .values(revoked=True)
                )
        return result.rowcount > 0

    async def balance(self, user_id: int) -> Decimal:
        async with self._session_factory() as session:
            value = await session.scalar(
                select(func.coalesce(func.sum(LedgerEntryRow.amount), 0)).where(
                    LedgerEntryRow.user_id == user_id,
                    LedgerEntryRow.currency == self.currency,
                )
            )
        return money(value)

    async def admin_wallet(self, user_id: int) -> AdminWallet:
        async with self._session_factory() as session:
            result = await session.execute(
                select(UserRow, WalletRow)
                .join(WalletRow, WalletRow.user_id == UserRow.id)
                .where(UserRow.id == user_id)
            )
            row = result.one_or_none()
            if row is None:
                raise WalletNotFoundError("User wallet not found")
            user, wallet = row
            return AdminWallet(
                user_id=user.id,
                telegram_user_id=user.telegram_user_id,
                display_name=user.display_name,
                wallet_id=wallet.id,
                address=wallet.address,
                network=wallet.network,
                asset=wallet.asset,
            )

    async def create_sweep(
        self,
        *,
        wallet: AdminWallet,
        amount: Decimal,
        destination_address: str,
        idempotency_key: str,
        requested_by: str,
        chain_balance_before: Decimal,
    ) -> SweepCreation:
        async with self._session_factory() as session:
            async with session.begin():
                existing = await session.scalar(
                    select(WalletSweepRow).where(
                        WalletSweepRow.idempotency_key == idempotency_key
                    )
                )
                if existing is not None:
                    if (
                        existing.user_id != wallet.user_id
                        or money(existing.requested_amount) != amount
                        or existing.destination_address != destination_address
                    ):
                        raise SweepConflictError(
                            "Idempotency key was already used for another withdrawal"
                        )
                    return SweepCreation(existing, False)

                await session.execute(
                    select(WalletRow.id)
                    .where(WalletRow.id == wallet.wallet_id)
                    .with_for_update()
                )
                active = await session.scalar(
                    select(WalletSweepRow.id).where(
                        WalletSweepRow.wallet_id == wallet.wallet_id,
                        WalletSweepRow.status.in_(
                            ("created", "submitted", "review_required")
                        ),
                    )
                )
                if active is not None:
                    raise SweepConflictError(
                        "This wallet already has an unresolved withdrawal"
                    )

                sweep = WalletSweepRow(
                    user_id=wallet.user_id,
                    wallet_id=wallet.wallet_id,
                    idempotency_key=idempotency_key,
                    source_address=wallet.address,
                    destination_address=destination_address,
                    requested_amount=amount,
                    asset=wallet.asset,
                    network=wallet.network,
                    status="created",
                    chain_balance_before=chain_balance_before,
                    requested_by=requested_by.strip() or "admin",
                )
                session.add(sweep)
                await session.flush()
                await session.refresh(sweep)
                return SweepCreation(sweep, True)

    async def sweep_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[WalletSweepRow]:
        async with self._session_factory() as session:
            return await session.scalar(
                select(WalletSweepRow).where(
                    WalletSweepRow.idempotency_key == idempotency_key
                )
            )

    async def mark_sweep_submitted(
        self,
        sweep_id: int,
        *,
        transaction_hash: str,
        transferred_amount: Decimal,
        chain_balance_before: Decimal,
        network_fee: Optional[Decimal],
    ) -> WalletSweepRow:
        async with self._session_factory() as session:
            async with session.begin():
                sweep = await session.get(WalletSweepRow, sweep_id)
                if sweep is None:
                    raise WalletNotFoundError("Withdrawal not found")
                sweep.status = "submitted"
                sweep.transaction_hash = transaction_hash
                sweep.transferred_amount = transferred_amount
                sweep.chain_balance_before = chain_balance_before
                sweep.network_fee = network_fee
                sweep.error_message = ""
                await session.flush()
                await session.refresh(sweep)
                return sweep

    async def mark_sweep_status(
        self,
        sweep_id: int,
        *,
        status: str,
        error_message: str = "",
        chain_balance_after: Optional[Decimal] = None,
        network_fee: Optional[Decimal] = None,
    ) -> WalletSweepRow:
        async with self._session_factory() as session:
            async with session.begin():
                sweep = await session.get(WalletSweepRow, sweep_id)
                if sweep is None:
                    raise WalletNotFoundError("Withdrawal not found")
                sweep.status = status
                sweep.error_message = error_message[:2000]
                if chain_balance_after is not None:
                    sweep.chain_balance_after = chain_balance_after
                if network_fee is not None:
                    sweep.network_fee = network_fee
                await session.flush()
                await session.refresh(sweep)
                return sweep

    async def sweep(self, sweep_id: int) -> WalletSweepRow:
        async with self._session_factory() as session:
            sweep = await session.get(WalletSweepRow, sweep_id)
            if sweep is None:
                raise WalletNotFoundError("Withdrawal not found")
            return sweep

    async def sweeps(self, *, limit: int) -> list[WalletSweepRow]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(WalletSweepRow)
                .order_by(WalletSweepRow.id.desc())
                .limit(limit)
            )
            return list(result.scalars())

    async def sweeps_for_wallet(
        self,
        wallet_id: int,
        *,
        statuses: Iterable[str],
    ) -> list[WalletSweepRow]:
        status_list = tuple(statuses)
        if not status_list:
            return []
        async with self._session_factory() as session:
            result = await session.execute(
                select(WalletSweepRow)
                .where(
                    WalletSweepRow.wallet_id == wallet_id,
                    WalletSweepRow.status.in_(status_list),
                )
                .order_by(WalletSweepRow.id.asc())
            )
            return list(result.scalars())

    async def transactions(self, user_id: int, *, limit: int) -> list[LedgerEntryRow]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(LedgerEntryRow)
                .where(LedgerEntryRow.user_id == user_id)
                .order_by(LedgerEntryRow.id.desc())
                .limit(limit)
            )
            return list(result.scalars())

    async def add_adjustment(
        self, *, user_id: int, amount: Decimal, description: str, reference: str
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                session.add(
                    LedgerEntryRow(
                        user_id=user_id,
                        amount=amount,
                        currency=self.currency,
                        entry_type="adjustment",
                        reference_type="admin",
                        reference_id=reference,
                        description=description,
                    )
                )

    async def get_retail_pricing(self) -> Optional[tuple[Decimal, Decimal]]:
        async with self._session_factory() as session:
            row = await session.get(RetailPricingRow, 1)
            if row is None:
                return None
            return money(row.markup_percent), money(row.markup_fixed)

    async def ensure_retail_pricing(
        self,
        *,
        markup_percent: Decimal,
        markup_fixed: Decimal,
    ) -> tuple[Decimal, Decimal]:
        percent = money(markup_percent)
        fixed = money(markup_fixed)
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(RetailPricingRow, 1)
                if row is None:
                    session.add(
                        RetailPricingRow(
                            id=1,
                            markup_percent=percent,
                            markup_fixed=fixed,
                        )
                    )
                    return percent, fixed
                return money(row.markup_percent), money(row.markup_fixed)

    async def set_retail_pricing(
        self,
        *,
        markup_percent: Decimal,
        markup_fixed: Decimal,
    ) -> tuple[Decimal, Decimal]:
        percent = money(markup_percent)
        fixed = money(markup_fixed)
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(RetailPricingRow, 1)
                if row is None:
                    session.add(
                        RetailPricingRow(
                            id=1,
                            markup_percent=percent,
                            markup_fixed=fixed,
                        )
                    )
                else:
                    row.markup_percent = percent
                    row.markup_fixed = fixed
        return percent, fixed

    async def cache_products(self, products: list[dict[str, Any]]) -> None:
        now = datetime.now(timezone.utc)
        async with self._session_factory() as session:
            async with session.begin():
                for product in products:
                    product_id = int(product["product_id"])
                    row = await session.get(ProductRow, product_id)
                    if row is None:
                        session.add(
                            ProductRow(
                                provider_product_id=product_id,
                                payload=product,
                                active=True,
                                refreshed_at=now,
                            )
                        )
                    else:
                        row.payload = product
                        row.active = True
                        row.refreshed_at = now

    async def cached_products(self) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ProductRow)
                .where(ProductRow.active.is_(True))
                .order_by(ProductRow.provider_product_id)
            )
            return [row.payload for row in result.scalars()]

    async def completed_order(
        self,
        *,
        user_id: int,
        external_order_id: str,
        product_id: int,
        quantity: int,
    ) -> Optional[CompletedOrder]:
        async with self._session_factory() as session:
            order = await session.scalar(
                select(OrderRow).where(
                    OrderRow.user_id == user_id,
                    OrderRow.external_order_id == external_order_id,
                )
            )
            if order is None or order.status != "completed":
                return None
            if order.provider_product_id != product_id or order.quantity != quantity:
                raise OrderConflictError(
                    "This external order ID was already used for another purchase"
                )
            return CompletedOrder(
                provider_payload=order.provider_payload,
                unit_price=money(order.unit_price),
                total_amount=money(order.total_amount),
                currency=order.currency,
            )

    async def reserve_order(
        self,
        *,
        user_id: int,
        external_order_id: str,
        product_id: int,
        quantity: int,
        unit_price: Decimal,
        currency: str,
    ) -> OrderReservation:
        total = money(unit_price * quantity)
        if currency != self.currency:
            raise OrderConflictError(
                f"Product currency {currency} does not match wallet currency {self.currency}"
            )

        async with self._session_factory() as session:
            async with session.begin():
                # Locking the user serializes balance checks for this wallet on PostgreSQL.
                await session.execute(
                    select(UserRow.id).where(UserRow.id == user_id).with_for_update()
                )
                order = await session.scalar(
                    select(OrderRow).where(
                        OrderRow.user_id == user_id,
                        OrderRow.external_order_id == external_order_id,
                    )
                )
                kind = ReservationKind.NEW
                if order is not None:
                    if (
                        order.provider_product_id != product_id
                        or order.quantity != quantity
                    ):
                        raise OrderConflictError(
                            "This external order ID was already used for another purchase"
                        )
                    if order.status == "completed":
                        return OrderReservation(
                            ReservationKind.COMPLETED,
                            order.id,
                            order.attempt_count,
                            CompletedOrder(
                                provider_payload=order.provider_payload,
                                unit_price=money(order.unit_price),
                                total_amount=money(order.total_amount),
                                currency=order.currency,
                            ),
                        )
                    if order.status in {"pending", "processing"}:
                        raise OrderConflictError("This order is already being processed")
                    kind = ReservationKind.RETRY

                current = await session.scalar(
                    select(func.coalesce(func.sum(LedgerEntryRow.amount), 0)).where(
                        LedgerEntryRow.user_id == user_id,
                        LedgerEntryRow.currency == self.currency,
                    )
                )
                if money(current) < total:
                    raise InsufficientFundsError(
                        f"Insufficient balance: {money(current)} available, {total} required"
                    )

                if order is None:
                    order = OrderRow(
                        user_id=user_id,
                        external_order_id=external_order_id,
                        provider_product_id=product_id,
                        quantity=quantity,
                        unit_price=unit_price,
                        total_amount=total,
                        currency=currency,
                        status="pending",
                        attempt_count=1,
                    )
                    session.add(order)
                    await session.flush()
                else:
                    order.attempt_count += 1
                    order.unit_price = unit_price
                    order.total_amount = total
                    order.status = "pending"
                    order.error_message = ""

                reference = f"{order.id}:{order.attempt_count}:debit"
                session.add(
                    LedgerEntryRow(
                        user_id=user_id,
                        amount=-total,
                        currency=currency,
                        entry_type="purchase",
                        reference_type="order",
                        reference_id=reference,
                        description=f"Order {external_order_id}",
                    )
                )
                session.add(
                    ProviderOrderRow(
                        order_id=order.id,
                        attempt=order.attempt_count,
                        provider="datamoll",
                        status="pending",
                    )
                )
                return OrderReservation(kind, order.id, order.attempt_count)

    async def complete_order(
        self, order_id: int, attempt: int, payload: dict[str, Any]
    ) -> CompletedOrder:
        async with self._session_factory() as session:
            async with session.begin():
                order = await session.get(OrderRow, order_id)
                if order is None or order.attempt_count != attempt:
                    raise OrderConflictError("Order attempt is no longer current")
                order.status = "completed"
                order.provider_order_id = str(payload.get("order_id") or "")
                order.provider_payload = payload
                provider_order = await session.scalar(
                    select(ProviderOrderRow).where(
                        ProviderOrderRow.order_id == order_id,
                        ProviderOrderRow.attempt == attempt,
                    )
                )
                if provider_order is not None:
                    provider_order.status = "completed"
                    provider_order.provider_order_id = order.provider_order_id
                    provider_order.response_payload = payload
                return CompletedOrder(
                    provider_payload=payload,
                    unit_price=money(order.unit_price),
                    total_amount=money(order.total_amount),
                    currency=order.currency,
                )

    async def fail_order(self, order_id: int, attempt: int, error: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                order = await session.get(OrderRow, order_id)
                if order is None or order.attempt_count != attempt:
                    return
                order.status = "refunded"
                order.error_message = error[:2000]
                session.add(
                    LedgerEntryRow(
                        user_id=order.user_id,
                        amount=order.total_amount,
                        currency=order.currency,
                        entry_type="refund",
                        reference_type="order",
                        reference_id=f"{order.id}:{attempt}:refund",
                        description=f"Refund for order {order.external_order_id}",
                    )
                )
                provider_order = await session.scalar(
                    select(ProviderOrderRow).where(
                        ProviderOrderRow.order_id == order_id,
                        ProviderOrderRow.attempt == attempt,
                    )
                )
                if provider_order is not None:
                    provider_order.status = "failed"
                    provider_order.error_message = error[:2000]

    async def record_deposit(
        self,
        *,
        event_id: str,
        payload: dict[str, Any],
        address: str,
        network: str,
        asset: str,
        transaction_hash: str,
        event_index: int,
        amount: Decimal,
        confirmations: int,
        required_confirmations: int,
    ) -> DepositResult:
        if amount <= 0:
            raise ValueError("Deposit amount must be greater than zero")
        if network != self.network or asset != self.asset:
            raise ValueError("Unsupported deposit network or asset")

        now = datetime.now(timezone.utc)
        async with self._session_factory() as session:
            async with session.begin():
                webhook = await session.scalar(
                    select(WebhookEventRow).where(WebhookEventRow.event_id == event_id)
                )
                duplicate = webhook is not None
                if webhook is None:
                    webhook = WebhookEventRow(
                        event_id=event_id,
                        event_type="deposit",
                        payload=payload,
                    )
                    session.add(webhook)
                else:
                    original = webhook.payload
                    identity_fields = ("address", "network", "asset", "transaction_hash", "event_index")
                    if any(original.get(field) != payload.get(field) for field in identity_fields):
                        raise ValueError("Webhook event ID conflicts with an existing event")

                wallet = await session.scalar(
                    select(WalletRow).where(
                        WalletRow.network == network,
                        WalletRow.address == address,
                        WalletRow.asset == asset,
                    )
                )
                if wallet is None:
                    raise ValueError("Deposit address is not assigned")

                deposit = await session.scalar(
                    select(DepositRow).where(
                        DepositRow.network == network,
                        DepositRow.transaction_hash == transaction_hash,
                        DepositRow.event_index == event_index,
                    )
                )
                if deposit is None:
                    deposit = DepositRow(
                        user_id=wallet.user_id,
                        wallet_id=wallet.id,
                        network=network,
                        asset=asset,
                        transaction_hash=transaction_hash,
                        event_index=event_index,
                        amount=amount,
                        confirmations=confirmations,
                        status="pending",
                    )
                    session.add(deposit)
                    await session.flush()
                else:
                    if deposit.user_id != wallet.user_id or money(deposit.amount) != amount:
                        raise ValueError("Deposit event conflicts with an existing transaction")
                    deposit.confirmations = max(deposit.confirmations, confirmations)

                credited = deposit.credited_at is not None
                newly_credited = False
                if not credited and deposit.confirmations >= required_confirmations:
                    deposit.status = "confirmed"
                    deposit.credited_at = now
                    session.add(
                        LedgerEntryRow(
                            user_id=wallet.user_id,
                            amount=amount,
                            currency=self.currency,
                            entry_type="deposit",
                            reference_type="deposit",
                            reference_id=f"{network}:{transaction_hash}:{event_index}",
                            description=f"{asset} deposit",
                        )
                    )
                    credited = True
                    newly_credited = True
                webhook.processed = True
                telegram_user_id = None
                if newly_credited:
                    telegram_user_id = await session.scalar(
                        select(UserRow.telegram_user_id).where(
                            UserRow.id == wallet.user_id
                        )
                    )
                return DepositResult(
                    status=deposit.status,
                    credited=credited,
                    duplicate=duplicate,
                    newly_credited=newly_credited,
                    user_id=wallet.user_id,
                    telegram_user_id=telegram_user_id,
                )
