from __future__ import annotations

import asyncio
import inspect
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from src.api.hero_sms import (
    HERO_SMS_API_URL,
    HeroSmsApiError,
    close_activation,
    get_activation_status,
    request_number_v2,
)
from src.api.telegram_auth import PendingTelegramLogin, TelegramAuthenticator


class HeroSmsActivationAlreadyRunningError(RuntimeError):
    pass


class HeroSmsTwoFactorError(RuntimeError):
    pass


@dataclass
class HeroSmsActivationRow:
    started_at: str
    row_id: str = ""
    activation_id: str = ""
    phone_number: str = ""
    operator: str = ""
    cost: float = 0.0
    status: str = "requesting"
    stage: str = "purchasing_number"
    code: str = ""
    message: str = "Requesting a Telegram number"
    needs_2fa: bool = False
    session_file: str = ""
    created_new_account: bool = False
    timeout_sec: int = 0
    deadline_at: float = 0.0


class HeroSmsActivationManager:
    """Purchases Hero SMS Telegram activations and polls them to completion."""

    def __init__(
        self,
        *,
        authenticator: TelegramAuthenticator | None = None,
        on_account_saved=None,
        two_factor_timeout_sec: int = 300,
        provider_name: str = "Hero SMS",
        api_url: str = HERO_SMS_API_URL,
        provider_params: dict | None = None,
        enforce_exact_price: bool = False,
        request_number_func=None,
        get_activation_status_func=None,
        close_activation_func=None,
    ) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._rows: list[HeroSmsActivationRow] = []
        self._job_id: str | None = None
        self._error: str | None = None
        self._target_count = 0
        self._success_count = 0
        self._concurrency = 0
        self._active_count = 0
        self._target_reached_event = asyncio.Event()
        self._authenticator = authenticator
        self._on_account_saved = on_account_saved
        self._two_factor_timeout_sec = two_factor_timeout_sec
        self._pending_logins: dict[str, PendingTelegramLogin] = {}
        self._password_futures: dict[str, asyncio.Future[str]] = {}
        self._provider_name = provider_name
        self._api_url = api_url
        self._provider_params = provider_params
        self._enforce_exact_price = enforce_exact_price
        self._request_number_func = request_number_func or request_number_v2
        self._get_activation_status_func = (
            get_activation_status_func or get_activation_status
        )
        self._close_activation_func = close_activation_func or close_activation

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(
        self,
        *,
        api_key: str,
        country_id: int,
        operator: str,
        target_count: int,
        concurrency: int,
        timeout_sec: int,
        max_price: Decimal,
        price_offers: list[Decimal] | None = None,
        price_ceiling: Decimal | None = None,
    ) -> str:
        if self.running:
            raise HeroSmsActivationAlreadyRunningError(
                f"A {self._provider_name} activation batch is already running"
            )
        if not api_key.strip():
            raise ValueError(f"{self._provider_name} API key is required")
        if country_id < 0:
            raise ValueError("A valid country is required")
        if not operator.strip():
            raise ValueError("A valid operator is required")
        if target_count < 1:
            raise ValueError("Target account count must be at least 1")
        if not 1 <= concurrency <= 10:
            raise ValueError("Concurrent phone count must be between 1 and 10")
        if not 30 <= timeout_sec <= 1200:
            raise ValueError("SMS timeout must be between 30 and 1200 seconds")
        if max_price <= 0:
            raise ValueError("A current positive Telegram price is required")
        ceiling = max_price if price_ceiling is None else price_ceiling
        if ceiling <= 0:
            raise ValueError("Purchase ceiling must be greater than zero")
        if ceiling < max_price:
            raise ValueError("Purchase ceiling must be at least the selected start price")
        if self._authenticator is not None:
            self._authenticator.validate_ready()

        normalized_offers = self._normalize_price_offers(
            max_price, price_offers, price_ceiling=ceiling
        )

        self._rows.clear()
        self._error = None
        self._stop_event = asyncio.Event()
        self._target_reached_event = asyncio.Event()
        self._target_count = target_count
        self._success_count = 0
        self._concurrency = concurrency
        self._active_count = 0
        self._job_id = uuid4().hex
        self._task = asyncio.create_task(
            self._run(
                api_key=api_key,
                country_id=country_id,
                operator=operator,
                target_count=target_count,
                concurrency=concurrency,
                timeout_sec=timeout_sec,
                max_price=max_price,
                price_ceiling=ceiling,
                price_offers=normalized_offers,
            ),
            name=f"{self._provider_name.lower().replace(' ', '-')}-{self._job_id}",
        )
        return self._job_id

    async def stop(self) -> None:
        if not self.running:
            return
        self._stop_event.set()
        assert self._task is not None
        await self._task

    def clear(self) -> None:
        if self.running:
            raise HeroSmsActivationAlreadyRunningError(
                f"Stop the {self._provider_name} activation batch before clearing it"
            )
        self._rows.clear()
        self._error = None
        self._job_id = None
        self._target_count = 0
        self._success_count = 0
        self._concurrency = 0
        self._active_count = 0

    def status(self) -> dict:
        return {
            "running": self.running,
            "job_id": self._job_id,
            "rows": [self._row_status(row) for row in self._rows],
            "error": self._error,
            "target_count": self._target_count,
            "success_count": self._success_count,
            "concurrency": self._concurrency,
            "active_count": self._active_count,
        }

    @staticmethod
    def _row_status(row: HeroSmsActivationRow) -> dict:
        data = asdict(row)
        deadline_at = float(data.pop("deadline_at", 0.0) or 0.0)
        timeout_sec = int(data.pop("timeout_sec", 0) or 0)
        if row.status in {"completed", "canceled", "failed", "timed_out"}:
            remaining_timeout_sec = 0
        elif deadline_at > 0:
            remaining_timeout_sec = max(0, math.ceil(deadline_at - time.monotonic()))
        else:
            remaining_timeout_sec = max(0, timeout_sec)
        data["remaining_timeout_sec"] = remaining_timeout_sec
        return data

    def submit_two_factor(self, row_id: str, password: str) -> None:
        future = self._password_futures.get(row_id)
        if future is None or future.done():
            raise HeroSmsTwoFactorError(
                "This activation is not waiting for a 2-step verification password"
            )
        if not password:
            raise ValueError("Telegram 2-step verification password is required")
        future.set_result(password)

    async def _run(
        self,
        *,
        api_key: str,
        country_id: int,
        operator: str,
        target_count: int,
        concurrency: int,
        timeout_sec: int,
        max_price: Decimal,
        price_ceiling: Decimal,
        price_offers: list[Decimal],
    ) -> None:
        active: set[asyncio.Task[bool]] = set()
        try:
            while not self._stop_event.is_set() and self._success_count < target_count:
                # Reserve only the attempts still needed so the final wave cannot overshoot.
                remaining = target_count - self._success_count - len(active)
                slots = min(concurrency - len(active), remaining)
                for _ in range(max(0, slots)):
                    active.add(asyncio.create_task(
                        self._run_attempt(
                            api_key=api_key,
                            country_id=country_id,
                            operator=operator,
                            timeout_sec=timeout_sec,
                            max_price=max_price,
                            price_ceiling=price_ceiling,
                            price_offers=price_offers,
                        ),
                        name=f"{self._provider_name}-activation-attempt",
                    ))

                if not active:
                    break

                done, active = await asyncio.wait(
                    active,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    if task.result():
                        self._success_count += 1

            if self._success_count >= target_count:
                self._target_reached_event.set()
        except Exception as exc:  # defensive: attempt errors should not escape
            self._error = str(exc)
            self._stop_event.set()
        finally:
            if active:
                await asyncio.gather(*active, return_exceptions=True)

    async def _run_attempt(
        self,
        *,
        api_key: str,
        country_id: int,
        operator: str,
        timeout_sec: int,
        max_price: Decimal,
        price_ceiling: Decimal,
        price_offers: list[Decimal],
    ) -> bool:
        self._active_count += 1
        try:
            created_account = await self._run_one(
                api_key=api_key,
                country_id=country_id,
                operator=operator,
                timeout_sec=timeout_sec,
                max_price=max_price,
                price_ceiling=price_ceiling,
                price_offers=price_offers,
            )
            if not created_account and not self._should_finish():
                await self._wait_or_stop(1.0)
            return created_account
        finally:
            self._active_count -= 1

    async def _run_one(
        self,
        *,
        api_key: str,
        country_id: int,
        operator: str,
        timeout_sec: int,
        max_price: Decimal,
        price_offers: list[Decimal] | None = None,
        price_ceiling: Decimal | None = None,
    ) -> bool:
        row = HeroSmsActivationRow(
            started_at=datetime.now(timezone.utc).isoformat(),
            row_id=uuid4().hex,
            operator=operator,
            timeout_sec=timeout_sec,
        )
        self._rows.append(row)
        if self._stop_event.is_set():
            row.status = "stopped"
            row.message = "Stopped before purchase"
            return False

        purchase_prices = self._purchase_prices(
            max_price,
            price_offers,
            price_ceiling=price_ceiling,
        )
        activation: dict | None = None
        for index, purchase_price in enumerate(purchase_prices):
            try:
                if index > 0:
                    row.message = (
                        f"No numbers at USD {purchase_prices[index - 1]}; "
                        f"trying USD {purchase_price}"
                    )
                activation = await self._call_provider_func(
                    self._request_number_func,
                    api_key,
                    country_id,
                    operator,
                    max_price=purchase_price,
                    **self._provider_call_kwargs(),
                )
                activation_cost = Decimal(str(activation["activation_cost"]))
                if self._enforce_exact_price and activation_cost != purchase_price:
                    row.activation_id = str(activation["activation_id"])
                    row.phone_number = str(activation["phone_number"])
                    row.operator = str(activation["operator"])
                    row.cost = float(activation_cost)
                    row.status = "failed"
                    row.stage = "purchase_price_mismatch"
                    row.message = (
                        f"{self._provider_name} returned USD {activation_cost} "
                        f"for selected tier USD {purchase_price}; activation canceled"
                    )
                    await self._close_quietly(
                        api_key, row.activation_id, cancel=True
                    )
                    self._error = row.message
                    self._stop_event.set()
                    return False
                break
            except (HeroSmsApiError, ValueError) as exc:
                if (
                    index + 1 < len(purchase_prices)
                    and self._is_no_numbers_error(exc)
                ):
                    continue
                row.status = "failed"
                row.message = str(exc)
                return False

        if activation is None:
            row.status = "failed"
            row.message = f"{self._provider_name} has no matching numbers available"
            return False

        row.activation_id = activation["activation_id"]
        row.phone_number = activation["phone_number"]
        row.operator = activation["operator"]
        row.cost = float(activation["activation_cost"])
        row.status = "waiting"
        row.stage = "requesting_telegram_code"
        row.message = "Requesting the Telegram login code"

        login: PendingTelegramLogin | None = None
        session_saved = False
        if self._authenticator is not None:
            try:
                login = await self._authenticator.begin(row.phone_number)
                self._pending_logins[row.row_id] = login
                row.phone_number = login.phone
                row.stage = "waiting_sms"
                row.message = f"Telegram code requested; waiting for {self._provider_name}"
            except Exception as exc:
                row.status = "failed"
                row.stage = "telegram_code_request_failed"
                row.message = f"Unable to request Telegram code: {exc}"
                await self._close_quietly(api_key, row.activation_id, cancel=True)
                return False
        else:
            row.stage = "waiting_sms"
            row.message = "Waiting for Telegram SMS"

        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout_sec
            row.deadline_at = deadline
            while loop.time() < deadline and not self._should_finish():
                try:
                    status, code = await self._call_provider_func(
                        self._get_activation_status_func,
                        api_key,
                        row.activation_id,
                        **self._provider_call_kwargs(),
                    )
                except (HeroSmsApiError, ValueError) as exc:
                    row.message = str(exc)
                    await self._wait_or_stop(3.0)
                    continue

                if status == "STATUS_OK" and code:
                    row.code = code
                    await self._close_quietly(
                        api_key, row.activation_id, cancel=False
                    )
                    if login is None:
                        row.status = "completed"
                        row.stage = "sms_received"
                        row.message = "Telegram SMS received"
                        return self._authenticator is None
                    await self._authorize_and_save(row, login, code)
                    session_saved = bool(row.session_file)
                    return row.created_new_account
                if status == "STATUS_CANCEL":
                    row.status = "canceled"
                    row.stage = "provider_canceled"
                    row.message = f"Activation was canceled by {self._provider_name}"
                    return False

                row.status = "waiting"
                row.stage = "waiting_sms"
                row.message = "Waiting for Telegram SMS"
                await self._wait_or_stop(3.0)

            cancel_reason = (
                "Stopped by user" if self._stop_event.is_set() else "SMS timeout"
            )
            await self._close_quietly(api_key, row.activation_id, cancel=True)
            row.status = "canceled" if self._stop_event.is_set() else "timed_out"
            row.stage = "stopped" if self._stop_event.is_set() else "sms_timed_out"
            if self._target_reached_event.is_set():
                row.status = "canceled"
                row.stage = "target_reached"
                cancel_reason = "Registration target reached"
            row.message = f"{cancel_reason}; activation canceled"
            return False
        finally:
            self._pending_logins.pop(row.row_id, None)
            password_future = self._password_futures.pop(row.row_id, None)
            if password_future is not None and not password_future.done():
                password_future.cancel()
            if (
                login is not None
                and not session_saved
                and self._authenticator is not None
            ):
                await self._authenticator.discard(login)

    async def _authorize_and_save(
        self,
        row: HeroSmsActivationRow,
        login: PendingTelegramLogin,
        code: str,
    ) -> None:
        assert self._authenticator is not None
        try:
            row.status = "authorizing"
            row.stage = "submitting_code"
            row.message = f"Submitting the {self._provider_name} code to Telegram"
            authorized = await self._authenticator.submit_code(login, code)
            if not authorized:
                row.status = "waiting_2fa"
                row.stage = "waiting_2fa"
                row.needs_2fa = True
                row.message = "Enter this account's Telegram 2-step verification password"
                password = await self._wait_for_two_factor(row.row_id)
                row.needs_2fa = False
                if password is None:
                    row.status = "canceled" if self._stop_event.is_set() else "failed"
                    row.stage = "stopped" if self._stop_event.is_set() else "two_factor_timed_out"
                    row.message = (
                        "Stopped while waiting for 2-step verification"
                        if self._stop_event.is_set()
                        else "Timed out waiting for 2-step verification"
                    )
                    return
                row.status = "authorizing"
                row.stage = "submitting_2fa"
                row.message = "Submitting Telegram 2-step verification"
                await self._authenticator.submit_password(login, password)

            row.stage = "saving_session"
            row.message = "Saving the authorized Telegram session"
            saved = await self._authenticator.save(login)
            row.session_file = saved.session_file
            row.created_new_account = saved.created_new_account
            row.status = "completed"
            row.stage = "session_saved"
            account_kind = "new account" if saved.created_new_account else "existing account"
            row.message = f"Telegram {account_kind} authorized; reusable session saved"
            if self._on_account_saved is not None:
                result = self._on_account_saved(saved.account)
                if inspect.isawaitable(result):
                    await result
        except Exception as exc:
            row.needs_2fa = False
            row.status = "failed"
            row.stage = "telegram_auth_failed"
            row.message = f"Telegram authentication failed: {exc}"

    async def _wait_for_two_factor(self, row_id: str) -> str | None:
        loop = asyncio.get_running_loop()
        password_future: asyncio.Future[str] = loop.create_future()
        self._password_futures[row_id] = password_future
        stop_task = asyncio.create_task(self._stop_event.wait())
        try:
            done, _ = await asyncio.wait(
                {password_future, stop_task},
                timeout=self._two_factor_timeout_sec,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if password_future in done:
                return password_future.result()
            return None
        finally:
            stop_task.cancel()

    async def _close_quietly(
        self,
        api_key: str,
        activation_id: str,
        *,
        cancel: bool,
    ) -> None:
        try:
            await self._call_provider_func(
                self._close_activation_func,
                api_key,
                activation_id,
                cancel=cancel,
                **self._provider_call_kwargs(),
            )
        except (HeroSmsApiError, ValueError):
            pass

    @staticmethod
    async def _call_provider_func(func, *args, **kwargs):
        signature = inspect.signature(func)
        accepts_arbitrary_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        if not accepts_arbitrary_kwargs:
            kwargs = {
                key: value
                for key, value in kwargs.items()
                if key in signature.parameters
            }
        return await func(*args, **kwargs)

    def _provider_call_kwargs(self) -> dict:
        kwargs = {}
        if self._api_url != HERO_SMS_API_URL:
            kwargs["api_url"] = self._api_url
        if self._provider_name != "Hero SMS":
            kwargs["provider_name"] = self._provider_name
        if self._provider_params is not None:
            kwargs["provider_params"] = self._provider_params
        return kwargs

    async def _wait_or_stop(self, seconds: float) -> None:
        if self._should_finish():
            return
        stop_task = asyncio.create_task(self._stop_event.wait())
        target_task = asyncio.create_task(self._target_reached_event.wait())
        try:
            await asyncio.wait(
                {stop_task, target_task},
                timeout=seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            stop_task.cancel()
            target_task.cancel()

    def _should_finish(self) -> bool:
        return self._stop_event.is_set() or self._target_reached_event.is_set()

    @staticmethod
    def _normalize_price_offers(
        max_price: Decimal,
        price_offers: list[Decimal] | None,
        *,
        price_ceiling: Decimal | None = None,
    ) -> list[Decimal]:
        offers: list[Decimal] = []
        seen: set[Decimal] = set()
        for value in price_offers or []:
            try:
                price = value if isinstance(value, Decimal) else Decimal(str(value))
            except Exception:  # noqa: BLE001 - skip malformed offer values
                continue
            if price <= 0 or price in seen:
                continue
            seen.add(price)
            offers.append(price)
        for bound in (max_price, price_ceiling):
            if bound is not None and bound > 0 and bound not in seen:
                seen.add(bound)
                offers.append(bound)
        offers.sort()
        return offers

    @classmethod
    def _purchase_prices(
        cls,
        max_price: Decimal,
        price_offers: list[Decimal] | None,
        *,
        price_ceiling: Decimal | None = None,
    ) -> list[Decimal]:
        ceiling = max_price if price_ceiling is None else price_ceiling
        if ceiling < max_price:
            ceiling = max_price
        offers = cls._normalize_price_offers(
            max_price, price_offers, price_ceiling=ceiling
        )
        prices = [price for price in offers if max_price <= price <= ceiling]
        return prices or [max_price]

    @staticmethod
    def _is_no_numbers_error(exc: BaseException) -> bool:
        message = str(exc).casefold()
        return (
            "no matching numbers" in message
            or "no_numbers" in message
            or "http 404" in message
            or "returned http 404" in message
        )
