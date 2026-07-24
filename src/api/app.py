from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import replace
from decimal import Decimal
from typing import List, Optional

from fastapi import FastAPI, HTTPException, WebSocket
from dotenv import load_dotenv

from src import bootstrap
from src.accounts.account_manager_service import AccountManagerService
from src.accounts.account_registry import AccountRegistry, RegistryEntry
from src.accounts.health_checker import AccountStatus
from src.accounts.session_crypto import load_key_from_env
from src.api import schemas
from src.api.campaign import CampaignAlreadyRunningError, CampaignManager
from src.api.events import handle_event_stream
from src.api.grizzly_sms import (
    GRIZZLY_SMS_API_URL,
    GRIZZLY_SMS_PROVIDER_NAME,
    close_activation as close_grizzly_sms_activation,
    fetch_balance as fetch_grizzly_sms_balance,
    fetch_countries as fetch_grizzly_sms_countries,
    fetch_operators as fetch_grizzly_sms_operators,
    fetch_telegram_price as fetch_grizzly_sms_telegram_price,
    request_number_v2 as request_grizzly_sms_number,
)
from src.api.hero_sms import (
    HeroSmsApiError,
    fetch_balance,
    fetch_countries,
    fetch_operators,
    fetch_telegram_offers,
    fetch_telegram_price,
)
from src.api.hero_sms_activation import (
    HeroSmsActivationAlreadyRunningError,
    HeroSmsActivationManager,
    HeroSmsTwoFactorError,
)
from src.api.invite_by_number import (
    InviteByNumberAlreadyRunningError,
    InviteByNumberManager,
    InviteRecipient,
    InviteSenderLink,
)
from src.api.json_generator import JsonGeneratorAlreadyRunningError, JsonGeneratorManager
from src.api.parsing import ParsingAlreadyRunningError, ParsingManager
from src.api.pool_guard import PoolAccessGuard, PoolBusyError
from src.api.proxy_check import ProxyCheckAlreadyRunningError, ProxyCheckManager
from src.api.proxy_pool_check import (
    ProxyPoolCheckAlreadyRunningError,
    ProxyPoolCheckManager,
)
from src.api.session_convert import SessionConvertAlreadyRunningError, SessionConvertManager
from src.api.stored_proxy_check import (
    StoredProxyCheckAlreadyRunningError,
    StoredProxyCheckManager,
)
from src.api.send_by_numbers import (
    SendByNumbersAlreadyRunningError,
    SendByNumbersManager,
)
from src.api.sms_pool import (
    SMSPOOL_API_URL,
    SMSPOOL_PROVIDER_NAME,
    SMSPOOL_STUB_PARAMS,
    fetch_balance as fetch_sms_pool_balance,
    fetch_countries as fetch_sms_pool_countries,
    fetch_operators as fetch_sms_pool_operators,
    fetch_telegram_price as fetch_sms_pool_telegram_price,
    get_activation_status as get_sms_pool_activation_status,
    request_number as request_sms_pool_number,
    close_activation as close_sms_pool_activation,
)
from src.api.tdata_convert import TdataConvertAlreadyRunningError, TdataConvertManager
from src.api.telegram_auth import TelegramAuthenticator
from src.config import AccountConfig, ProxyConfig, TimingPolicy
from src.db.proxy_repository import ProxyRepository, ensure_proxy_table
from src.messaging.messaging_service import MessagePayload
from src.monitoring.event_bus import EventBus
from src.proxy.proxy_parser import parse_proxy_lines

logger = logging.getLogger("api")


def _build_session_encryption_key() -> Optional[bytes]:
    """Like bootstrap.build_session_encryption_key(), but raises ValueError instead of exiting."""
    if os.getenv("SESSION_ENCRYPTION_ENABLED", "0").lower() not in ("1", "true", "yes"):
        return None
    return load_key_from_env()


def _build_timing_policy() -> TimingPolicy:
    return TimingPolicy(
        base_delay_sec=bootstrap.env_float("DELAY_BASE", "2.0"),
        jitter_sec=bootstrap.env_float("DELAY_JITTER", "1.5"),
        inter_message_delay_sec=bootstrap.env_float("MSG_DELAY", "3.0"),
        inter_message_jitter_sec=bootstrap.env_float("MSG_JITTER", "2.0"),
        max_flood_retries=bootstrap.env_int("MAX_RETRIES", "5"),
        startup_jitter_max_sec=bootstrap.env_float("STARTUP_JITTER", "3.0"),
    )


def _dedupe_accounts_by_phone(accounts: List) -> List:
    """Keep the first source for each phone so one .session is opened by one client."""
    seen: set[str] = set()
    unique = []
    for account in accounts:
        if account.phone in seen:
            logger.warning("Skipping duplicate account source for %s.", account.phone)
            continue
        seen.add(account.phone)
        unique.append(account)
    return unique


def _stored_proxy_to_config(proxy) -> ProxyConfig:
    return ProxyConfig(
        host=proxy.host,
        port=proxy.port,
        username=proxy.username or None,
        password=proxy.password or None,
        proxy_type=proxy.proxy_type,
    )


def _apply_proxy_inventory(
    accounts: List[AccountConfig],
    proxies: List[ProxyConfig],
    *,
    clear_when_empty: bool = False,
) -> List[AccountConfig]:
    """Assign stored proxy DB rows to accounts using the existing round-robin rule."""
    if not accounts:
        return accounts
    if not proxies:
        if clear_when_empty:
            return [replace(account, proxy=None) for account in accounts]
        return accounts

    from src.accounts.account_loader import ProxyAllocator

    allocator = ProxyAllocator(
        proxies,
        accounts_per_proxy=bootstrap.env_int("ACCOUNTS_PER_PROXY", "1"),
    )
    return [replace(account, proxy=allocator.next()) for account in accounts]


async def _load_proxy_inventory(repository: Optional[ProxyRepository]) -> List[ProxyConfig]:
    if repository is None:
        return []
    stored = await repository.list_all()
    return [_stored_proxy_to_config(proxy) for proxy in stored]


async def _refresh_account_proxy_assignments() -> None:
    repository: Optional[ProxyRepository] = app.state.proxy_repository
    proxy_inventory = await _load_proxy_inventory(repository)

    primary: List[AccountConfig] = app.state.primary_accounts
    spares: List[AccountConfig] = app.state.spare_accounts
    primary[:] = _apply_proxy_inventory(primary, proxy_inventory, clear_when_empty=True)
    spares[:] = _apply_proxy_inventory(spares, proxy_inventory, clear_when_empty=True)

    updated_accounts = primary + spares
    registry: AccountRegistry = app.state.registry
    await registry.register_many(updated_accounts)

    invite_manager: InviteByNumberManager = app.state.invite_by_number_manager
    send_manager: SendByNumbersManager = app.state.send_by_numbers_manager
    for account in updated_accounts:
        invite_manager.register_account(account)
        send_manager.register_account(account)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    bootstrap.configure_logging(debug=False, log_dir=os.getenv("LOG_DIR", ""))

    event_bus = EventBus()
    session_factory = bootstrap.build_db_session_factory()
    proxy_session_factory = bootstrap.build_proxy_db_session_factory(session_factory)
    owns_proxy_engine = (
        proxy_session_factory is not None and proxy_session_factory is not session_factory
    )
    if proxy_session_factory is not None:
        await ensure_proxy_table(proxy_session_factory)
    proxy_repository = (
        ProxyRepository(proxy_session_factory) if proxy_session_factory else None
    )

    primary, spares = bootstrap.load_accounts()
    primary = _dedupe_accounts_by_phone(primary + await bootstrap.load_tdata_accounts())
    spares = _dedupe_accounts_by_phone(spares)
    proxy_inventory = await _load_proxy_inventory(proxy_repository)
    primary = _apply_proxy_inventory(primary, proxy_inventory)
    spares = _apply_proxy_inventory(spares, proxy_inventory)

    registry = AccountRegistry(repository=bootstrap.build_account_repository(session_factory))
    await registry.load_from_repository()
    # Safe to call unconditionally: register_many() only adds new phones, existing ones keep their state.
    await registry.register_many(primary + spares)

    policy = _build_timing_policy()
    health_checker = bootstrap.build_health_checker(policy, event_bus)
    account_manager = AccountManagerService(registry, health_checker)

    try:
        session_encryption_key = _build_session_encryption_key()
    except ValueError as exc:
        logger.error("Invalid SESSION_ENCRYPTION_KEY at startup — sessions will run unencrypted: %s", exc)
        session_encryption_key = None

    pool_guard = PoolAccessGuard()

    campaign_manager = CampaignManager(
        event_bus=event_bus,
        registry=registry,
        accounts=primary,
        spare_accounts=spares,
        policy=policy,
        session_encryption_key=session_encryption_key,
        pool_guard=pool_guard,
    )
    parsing_manager = ParsingManager(
        event_bus=event_bus,
        accounts=primary,
        spare_accounts=spares,
        policy=policy,
        session_encryption_key=session_encryption_key,
        pool_guard=pool_guard,
    )

    app.state.event_bus = event_bus
    app.state.registry = registry
    app.state.account_manager = account_manager
    app.state.pool_guard = pool_guard
    app.state.campaign_manager = campaign_manager
    app.state.parsing_manager = parsing_manager
    app.state.primary_accounts = primary
    app.state.spare_accounts = spares
    app.state.session_encryption_key = session_encryption_key
    app.state.proxy_check_manager = ProxyCheckManager()
    app.state.proxy_repository = proxy_repository
    app.state.stored_proxy_check_manager = (
        StoredProxyCheckManager(app.state.proxy_repository)
        if app.state.proxy_repository is not None
        else None
    )
    app.state.proxy_pool_check_manager = ProxyPoolCheckManager()
    app.state.tdata_convert_manager = TdataConvertManager()
    app.state.session_convert_manager = SessionConvertManager()
    app.state.json_generator_manager = JsonGeneratorManager()
    app.state.invite_by_number_manager = InviteByNumberManager(
        accounts=list(primary) + list(spares),
        pool_guard=pool_guard,
        session_encryption_key=session_encryption_key,
    )
    app.state.send_by_numbers_manager = SendByNumbersManager(
        accounts=list(primary) + list(spares),
        pool_guard=pool_guard,
        session_encryption_key=session_encryption_key,
    )

    accounts_dir = os.getenv("ACCOUNTS_DIR", "accounts")
    fingerprint_file = os.getenv(
        "TELEGRAM_FINGERPRINT_FILE",
        os.path.join(os.path.dirname(accounts_dir), "Fingerprints", "telegram_devices.xlsx"),
    )

    async def register_saved_account(account) -> None:
        known_phones = {item.phone for item in primary} | {item.phone for item in spares}
        if account.phone not in known_phones:
            primary.append(account)
            await registry.register_many([account])
            app.state.invite_by_number_manager.register_account(account)
            app.state.send_by_numbers_manager.register_account(account)

    telegram_authenticator = TelegramAuthenticator(
        fingerprint_file=fingerprint_file,
        accounts_dir=accounts_dir,
        encryption_key=session_encryption_key,
    )
    app.state.hero_sms_activation_manager = HeroSmsActivationManager(
        authenticator=telegram_authenticator,
        on_account_saved=register_saved_account,
        enforce_exact_price=True,
    )
    app.state.sms_pool_activation_manager = HeroSmsActivationManager(
        authenticator=telegram_authenticator,
        on_account_saved=register_saved_account,
        provider_name=SMSPOOL_PROVIDER_NAME,
        api_url=SMSPOOL_API_URL,
        provider_params=SMSPOOL_STUB_PARAMS,
        request_number_func=request_sms_pool_number,
        get_activation_status_func=get_sms_pool_activation_status,
        close_activation_func=close_sms_pool_activation,
    )
    app.state.grizzly_sms_activation_manager = HeroSmsActivationManager(
        authenticator=telegram_authenticator,
        on_account_saved=register_saved_account,
        provider_name=GRIZZLY_SMS_PROVIDER_NAME,
        api_url=GRIZZLY_SMS_API_URL,
        request_number_func=request_grizzly_sms_number,
        close_activation_func=close_grizzly_sms_activation,
    )

    logger.info("API ready: %d accounts loaded, %d spares.", len(primary), len(spares))
    try:
        yield
    finally:
        await app.state.invite_by_number_manager.stop()
        await app.state.send_by_numbers_manager.stop()
        await app.state.hero_sms_activation_manager.stop()
        await app.state.sms_pool_activation_manager.stop()
        await app.state.grizzly_sms_activation_manager.stop()
        if app.state.stored_proxy_check_manager is not None:
            await app.state.stored_proxy_check_manager.stop()
        await registry.close()
        if owns_proxy_engine:
            await proxy_session_factory.kw["bind"].dispose()


app = FastAPI(title="tg_pool_framework control API", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/hero_sms/countries", response_model=List[schemas.HeroSmsCountryOut])
async def hero_sms_countries(
    body: schemas.HeroSmsApiKeyRequest,
) -> List[schemas.HeroSmsCountryOut]:
    try:
        countries = await fetch_countries(body.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeroSmsApiError as exc:
        logger.warning("Hero SMS countries request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [schemas.HeroSmsCountryOut(**country) for country in countries]


@app.post("/hero_sms/balance", response_model=schemas.HeroSmsBalanceOut)
async def hero_sms_balance(
    body: schemas.HeroSmsApiKeyRequest,
) -> schemas.HeroSmsBalanceOut:
    try:
        balance = await fetch_balance(body.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeroSmsApiError as exc:
        logger.warning("Hero SMS balance request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return schemas.HeroSmsBalanceOut(balance=float(balance))


@app.post("/hero_sms/operators", response_model=schemas.HeroSmsOperatorsOut)
async def hero_sms_operators(
    body: schemas.HeroSmsOperatorsRequest,
) -> schemas.HeroSmsOperatorsOut:
    try:
        operators = await fetch_operators(body.api_key, body.country_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeroSmsApiError as exc:
        logger.warning("Hero SMS operators request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return schemas.HeroSmsOperatorsOut(operators=operators)


@app.post("/hero_sms/telegram-price", response_model=schemas.HeroSmsPriceOut)
async def hero_sms_telegram_price(
    body: schemas.HeroSmsPriceRequest,
) -> schemas.HeroSmsPriceOut:
    try:
        catalog = await fetch_telegram_offers(body.api_key, body.country_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeroSmsApiError as exc:
        logger.warning("Hero SMS Telegram price request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    price = catalog.get("price")
    return schemas.HeroSmsPriceOut(
        price=float(price) if price is not None else None,
        available=int(catalog.get("available", 0)),
        offers=[
            schemas.HeroSmsPriceOfferOut(
                price=float(offer["price"]),
                available=int(offer["available"]),
            )
            for offer in catalog.get("offers", [])
            if isinstance(offer, dict)
        ],
    )


@app.post(
    "/hero_sms/activations/start",
    response_model=schemas.HeroSmsActivationStartResponse,
)
async def hero_sms_activations_start(
    body: schemas.HeroSmsActivationStartRequest,
) -> schemas.HeroSmsActivationStartResponse:
    manager: HeroSmsActivationManager = app.state.hero_sms_activation_manager
    try:
        job_id = manager.start(
            api_key=body.api_key,
            country_id=body.country_id,
            operator=body.operator,
            target_count=body.target_count,
            concurrency=body.concurrency,
            timeout_sec=body.timeout_sec,
            max_price=Decimal(str(body.max_price)),
            price_ceiling=(
                Decimal(str(body.price_ceiling))
                if body.price_ceiling is not None
                else Decimal(str(body.max_price))
            ),
            price_offers=[Decimal(str(price)) for price in body.price_offers],
        )
    except HeroSmsActivationAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return schemas.HeroSmsActivationStartResponse(job_id=job_id, started=True)


@app.post("/hero_sms/activations/stop")
async def hero_sms_activations_stop() -> dict:
    manager: HeroSmsActivationManager = app.state.hero_sms_activation_manager
    await manager.stop()
    return {"ok": True}


@app.post("/hero_sms/activations/clear")
async def hero_sms_activations_clear() -> dict:
    manager: HeroSmsActivationManager = app.state.hero_sms_activation_manager
    try:
        manager.clear()
    except HeroSmsActivationAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/hero_sms/activations/{row_id}/two-factor")
async def hero_sms_activations_two_factor(
    row_id: str,
    body: schemas.HeroSmsTwoFactorRequest,
) -> dict:
    manager: HeroSmsActivationManager = app.state.hero_sms_activation_manager
    try:
        manager.submit_two_factor(row_id, body.password)
    except HeroSmsTwoFactorError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"accepted": True}


@app.get(
    "/hero_sms/activations/status",
    response_model=schemas.HeroSmsActivationStatusResponse,
)
async def hero_sms_activations_status() -> schemas.HeroSmsActivationStatusResponse:
    manager: HeroSmsActivationManager = app.state.hero_sms_activation_manager
    return schemas.HeroSmsActivationStatusResponse(**manager.status())


@app.post("/sms_pool/countries", response_model=List[schemas.HeroSmsCountryOut])
async def sms_pool_countries(
    body: schemas.HeroSmsApiKeyRequest,
) -> List[schemas.HeroSmsCountryOut]:
    try:
        countries = await fetch_sms_pool_countries(body.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeroSmsApiError as exc:
        logger.warning("SMSpool countries request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [schemas.HeroSmsCountryOut(**country) for country in countries]


@app.post("/sms_pool/balance", response_model=schemas.HeroSmsBalanceOut)
async def sms_pool_balance(
    body: schemas.HeroSmsApiKeyRequest,
) -> schemas.HeroSmsBalanceOut:
    try:
        balance = await fetch_sms_pool_balance(body.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeroSmsApiError as exc:
        logger.warning("SMSpool balance request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return schemas.HeroSmsBalanceOut(balance=float(balance))


@app.post("/sms_pool/operators", response_model=schemas.HeroSmsOperatorsOut)
async def sms_pool_operators(
    body: schemas.HeroSmsOperatorsRequest,
) -> schemas.HeroSmsOperatorsOut:
    try:
        operators = await fetch_sms_pool_operators(body.api_key, body.country_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeroSmsApiError as exc:
        logger.warning("SMSpool operators request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return schemas.HeroSmsOperatorsOut(operators=operators)


@app.post("/sms_pool/telegram-price", response_model=schemas.HeroSmsPriceOut)
async def sms_pool_telegram_price(
    body: schemas.HeroSmsPriceRequest,
) -> schemas.HeroSmsPriceOut:
    try:
        price, available = await fetch_sms_pool_telegram_price(
            body.api_key,
            body.country_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeroSmsApiError as exc:
        logger.warning("SMSpool Telegram price request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return schemas.HeroSmsPriceOut(
        price=float(price) if price is not None else None,
        available=available,
    )


@app.post(
    "/sms_pool/activations/start",
    response_model=schemas.HeroSmsActivationStartResponse,
)
async def sms_pool_activations_start(
    body: schemas.HeroSmsActivationStartRequest,
) -> schemas.HeroSmsActivationStartResponse:
    manager: HeroSmsActivationManager = app.state.sms_pool_activation_manager
    try:
        job_id = manager.start(
            api_key=body.api_key,
            country_id=body.country_id,
            operator=body.operator,
            target_count=body.target_count,
            concurrency=body.concurrency,
            timeout_sec=body.timeout_sec,
            max_price=Decimal(str(body.max_price)),
            price_ceiling=(
                Decimal(str(body.price_ceiling))
                if body.price_ceiling is not None
                else Decimal(str(body.max_price))
            ),
            price_offers=[Decimal(str(price)) for price in body.price_offers],
        )
    except HeroSmsActivationAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return schemas.HeroSmsActivationStartResponse(job_id=job_id, started=True)


@app.post("/sms_pool/activations/stop")
async def sms_pool_activations_stop() -> dict:
    manager: HeroSmsActivationManager = app.state.sms_pool_activation_manager
    await manager.stop()
    return {"ok": True}


@app.post("/sms_pool/activations/clear")
async def sms_pool_activations_clear() -> dict:
    manager: HeroSmsActivationManager = app.state.sms_pool_activation_manager
    try:
        manager.clear()
    except HeroSmsActivationAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/sms_pool/activations/{row_id}/two-factor")
async def sms_pool_activations_two_factor(
    row_id: str,
    body: schemas.HeroSmsTwoFactorRequest,
) -> dict:
    manager: HeroSmsActivationManager = app.state.sms_pool_activation_manager
    try:
        manager.submit_two_factor(row_id, body.password)
    except HeroSmsTwoFactorError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"accepted": True}


@app.get(
    "/sms_pool/activations/status",
    response_model=schemas.HeroSmsActivationStatusResponse,
)
async def sms_pool_activations_status() -> schemas.HeroSmsActivationStatusResponse:
    manager: HeroSmsActivationManager = app.state.sms_pool_activation_manager
    return schemas.HeroSmsActivationStatusResponse(**manager.status())


@app.post("/grizzly_sms/countries", response_model=List[schemas.HeroSmsCountryOut])
async def grizzly_sms_countries(
    body: schemas.HeroSmsApiKeyRequest,
) -> List[schemas.HeroSmsCountryOut]:
    try:
        countries = await fetch_grizzly_sms_countries(body.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeroSmsApiError as exc:
        logger.warning("GrizzlySMS countries request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [schemas.HeroSmsCountryOut(**country) for country in countries]


@app.post("/grizzly_sms/balance", response_model=schemas.HeroSmsBalanceOut)
async def grizzly_sms_balance(
    body: schemas.HeroSmsApiKeyRequest,
) -> schemas.HeroSmsBalanceOut:
    try:
        balance = await fetch_grizzly_sms_balance(body.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeroSmsApiError as exc:
        logger.warning("GrizzlySMS balance request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return schemas.HeroSmsBalanceOut(balance=float(balance))


@app.post("/grizzly_sms/operators", response_model=schemas.HeroSmsOperatorsOut)
async def grizzly_sms_operators(
    body: schemas.HeroSmsOperatorsRequest,
) -> schemas.HeroSmsOperatorsOut:
    try:
        operators = await fetch_grizzly_sms_operators(body.api_key, body.country_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeroSmsApiError as exc:
        logger.warning("GrizzlySMS operators request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return schemas.HeroSmsOperatorsOut(operators=operators)


@app.post("/grizzly_sms/telegram-price", response_model=schemas.HeroSmsPriceOut)
async def grizzly_sms_telegram_price(
    body: schemas.HeroSmsPriceRequest,
) -> schemas.HeroSmsPriceOut:
    try:
        price, available = await fetch_grizzly_sms_telegram_price(
            body.api_key,
            body.country_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HeroSmsApiError as exc:
        logger.warning("GrizzlySMS Telegram price request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return schemas.HeroSmsPriceOut(
        price=float(price) if price is not None else None,
        available=available,
    )


@app.post(
    "/grizzly_sms/activations/start",
    response_model=schemas.HeroSmsActivationStartResponse,
)
async def grizzly_sms_activations_start(
    body: schemas.HeroSmsActivationStartRequest,
) -> schemas.HeroSmsActivationStartResponse:
    manager: HeroSmsActivationManager = app.state.grizzly_sms_activation_manager
    try:
        job_id = manager.start(
            api_key=body.api_key,
            country_id=body.country_id,
            operator=body.operator,
            target_count=body.target_count,
            concurrency=body.concurrency,
            timeout_sec=body.timeout_sec,
            max_price=Decimal(str(body.max_price)),
            price_ceiling=(
                Decimal(str(body.price_ceiling))
                if body.price_ceiling is not None
                else Decimal(str(body.max_price))
            ),
            price_offers=[Decimal(str(price)) for price in body.price_offers],
        )
    except HeroSmsActivationAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return schemas.HeroSmsActivationStartResponse(job_id=job_id, started=True)


@app.post("/grizzly_sms/activations/stop")
async def grizzly_sms_activations_stop() -> dict:
    manager: HeroSmsActivationManager = app.state.grizzly_sms_activation_manager
    await manager.stop()
    return {"ok": True}


@app.post("/grizzly_sms/activations/clear")
async def grizzly_sms_activations_clear() -> dict:
    manager: HeroSmsActivationManager = app.state.grizzly_sms_activation_manager
    try:
        manager.clear()
    except HeroSmsActivationAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/grizzly_sms/activations/{row_id}/two-factor")
async def grizzly_sms_activations_two_factor(
    row_id: str,
    body: schemas.HeroSmsTwoFactorRequest,
) -> dict:
    manager: HeroSmsActivationManager = app.state.grizzly_sms_activation_manager
    try:
        manager.submit_two_factor(row_id, body.password)
    except HeroSmsTwoFactorError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"accepted": True}


@app.get(
    "/grizzly_sms/activations/status",
    response_model=schemas.HeroSmsActivationStatusResponse,
)
async def grizzly_sms_activations_status() -> schemas.HeroSmsActivationStatusResponse:
    manager: HeroSmsActivationManager = app.state.grizzly_sms_activation_manager
    return schemas.HeroSmsActivationStatusResponse(**manager.status())


def _proxy_identity(proxy: ProxyConfig) -> tuple[str, str, int, str]:
    return (
        proxy.proxy_type,
        proxy.host,
        proxy.port,
        proxy.username or "",
    )


async def _load_proxy_statuses(repository: Optional[ProxyRepository]) -> dict[tuple[str, str, int, str], str]:
    if repository is None:
        return {}
    return {
        (proxy.proxy_type, proxy.host, proxy.port, proxy.username or ""): proxy.status
        for proxy in await repository.list_all()
    }


def _entry_to_out(
    entry: RegistryEntry,
    proxy_statuses: Optional[dict[tuple[str, str, int, str], str]] = None,
) -> schemas.AccountOut:
    state = entry.state
    proxy = entry.proxy_state
    configured_proxy = entry.account.proxy
    proxy_label = (
        f"{configured_proxy.host}:{configured_proxy.port}"
        if configured_proxy else None
    )
    proxy_status = (
        proxy_statuses.get(_proxy_identity(configured_proxy))
        if configured_proxy and proxy_statuses
        else None
    )
    return schemas.AccountOut(
        phone=entry.account.phone,
        status=state.status.value if state else "unknown",
        is_premium=state.is_premium if state else False,
        has_2fa=state.has_2fa if state else False,
        country=state.country if state else None,
        username=state.username if state else "",
        first_name=state.first_name if state else "",
        error_message=state.error_message if state else None,
        restriction_expires=state.restriction_expires if state else None,
        role=entry.role,
        folder=entry.folder,
        first_seen=entry.first_seen,
        last_checked=entry.last_checked,
        uses_proxy=configured_proxy is not None,
        proxy_label=proxy_label,
        proxy_status=proxy_status,
        proxy=schemas.ProxyStateOut(
            is_active=proxy.is_active,
            latency_ms=proxy.latency_ms,
            proxy_type=proxy.proxy_type.value,
            error_message=proxy.error_message,
        ) if proxy else None,
    )


@app.get("/accounts", response_model=List[schemas.AccountOut])
async def list_accounts(
    status: Optional[str] = None,
    premium: Optional[bool] = None,
    has_2fa: Optional[bool] = None,
    country: Optional[str] = None,
    role: Optional[str] = None,
    folder: Optional[str] = None,
    text: Optional[str] = None,
    sort_by: Optional[str] = None,
    reverse: bool = False,
) -> List[schemas.AccountOut]:
    manager: AccountManagerService = app.state.account_manager
    try:
        status_filter = AccountStatus(status) if status else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown status {status!r}") from exc

    entries = manager.search(
        status=status_filter,
        premium=premium,
        has_2fa=has_2fa,
        country=country,
        role=role,
        folder=folder,
        text=text,
        sort_by=sort_by,
        reverse=reverse,
    )
    proxy_statuses = await _load_proxy_statuses(app.state.proxy_repository)
    return [_entry_to_out(e, proxy_statuses) for e in entries]


@app.post("/accounts/{phone}/role")
async def assign_role(phone: str, body: schemas.AssignValueRequest) -> dict:
    manager: AccountManagerService = app.state.account_manager
    await manager.assign_role(phone, body.value)
    return {"ok": True}


@app.post("/accounts/{phone}/folder")
async def assign_folder(phone: str, body: schemas.AssignValueRequest) -> dict:
    manager: AccountManagerService = app.state.account_manager
    await manager.assign_folder(phone, body.value)
    return {"ok": True}


@app.post("/accounts/recheck", response_model=schemas.RecheckResponse)
async def recheck_accounts(body: schemas.RecheckRequest) -> schemas.RecheckResponse:
    manager: AccountManagerService = app.state.account_manager
    pool_guard: PoolAccessGuard = app.state.pool_guard
    holder = f"account_recheck:{uuid.uuid4().hex}"
    try:
        pool_guard.try_acquire(holder)
    except PoolBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        report = await manager.recheck(phones=body.phones, deep=body.deep)
        return schemas.RecheckResponse(
            checked=len(report.results),
            alive=len(report.alive),
            banned=len(report.banned),
            unauthorized=len(report.unauthorized),
            spamblock=len(report.spamblocked),
            frozen=len(report.frozen),
            flood=len(report.flooded),
        )
    finally:
        pool_guard.release(holder)


@app.post("/accounts/rescan", response_model=schemas.RescanResponse)
async def rescan_accounts() -> schemas.RescanResponse:
    """Re-scans the accounts directories for new .session+.json pairs and registers them."""
    registry: AccountRegistry = app.state.registry
    primary: list = app.state.primary_accounts
    spares: list = app.state.spare_accounts

    fresh_primary, fresh_spares = bootstrap.load_accounts()
    proxy_inventory = await _load_proxy_inventory(app.state.proxy_repository)
    fresh_primary = _apply_proxy_inventory(fresh_primary, proxy_inventory)
    fresh_spares = _apply_proxy_inventory(fresh_spares, proxy_inventory)
    known_phones = {a.phone for a in primary} | {a.phone for a in spares}

    new_primary = [a for a in fresh_primary if a.phone not in known_phones]
    new_spares = [a for a in fresh_spares if a.phone not in known_phones]

    primary.extend(new_primary)
    spares.extend(new_spares)
    await registry.register_many(new_primary + new_spares)
    invite_manager: InviteByNumberManager = app.state.invite_by_number_manager
    for account in new_primary + new_spares:
        invite_manager.register_account(account)
        app.state.send_by_numbers_manager.register_account(account)

    return schemas.RescanResponse(new_accounts=len(new_primary) + len(new_spares))


@app.post("/send_by_numbers/start", response_model=schemas.SendByNumbersStartResponse)
async def start_send_by_numbers(
    body: schemas.SendByNumbersStartRequest,
) -> schemas.SendByNumbersStartResponse:
    manager: SendByNumbersManager = app.state.send_by_numbers_manager
    try:
        job_id = manager.start(
            phone_numbers=body.phone_numbers,
            message=body.message,
            sender_phones=body.sender_phones,
            sms_per_account_min=body.sms_per_account_min,
            sms_per_account_max=body.sms_per_account_max,
            delay_min_sec=body.delay_min_sec,
            delay_max_sec=body.delay_max_sec,
            max_flood_wait_sec=body.max_flood_wait_sec,
            use_base_data=body.use_base_data,
            request_profile=body.request_profile,
            delete_dialog=body.delete_dialog,
            link_preview=body.link_preview,
            silent=body.silent,
            auto_repost=body.auto_repost,
            pin_message=body.pin_message,
            video_note=body.video_note,
            self_destruct_sec=body.self_destruct_sec,
            sending_by_time=body.sending_by_time,
            streams_control=body.streams_control,
            auto_stop=body.auto_stop,
        )
    except SendByNumbersAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.SendByNumbersStartResponse(job_id=job_id, started=True)


@app.post("/send_by_numbers/stop")
async def stop_send_by_numbers() -> dict:
    manager: SendByNumbersManager = app.state.send_by_numbers_manager
    await manager.stop()
    return {"ok": True}


@app.get("/send_by_numbers/status", response_model=schemas.SendByNumbersStatusResponse)
async def send_by_numbers_status() -> schemas.SendByNumbersStatusResponse:
    manager: SendByNumbersManager = app.state.send_by_numbers_manager
    return schemas.SendByNumbersStatusResponse(**manager.status())


@app.post("/invite_by_number/start", response_model=schemas.InviteByNumberStartResponse)
async def start_invite_by_number(
    body: schemas.InviteByNumberStartRequest,
) -> schemas.InviteByNumberStartResponse:
    manager: InviteByNumberManager = app.state.invite_by_number_manager
    recipients = [
        InviteRecipient(
            recipient_id=item.id,
            username=item.username,
            phone=item.phone,
        )
        for item in body.recipients
    ]
    if not recipients and body.recipient_ids:
        recipients = [InviteRecipient(recipient_id=item) for item in body.recipient_ids]
    try:
        job_id = manager.start(
            recipients=recipients,
            sender_links=[
                InviteSenderLink(sender_phone=item.sender_phone, invite_link=item.invite_link)
                for item in body.sender_links
            ],
            max_per_account=body.max_per_account,
            delay_min_sec=body.delay_min_sec,
            delay_max_sec=body.delay_max_sec,
            max_flood_wait_sec=body.max_flood_wait_sec,
            message_template=body.message_template,
        )
    except InviteByNumberAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.InviteByNumberStartResponse(job_id=job_id, started=True)


@app.post("/invite_by_number/stop")
async def stop_invite_by_number() -> dict:
    manager: InviteByNumberManager = app.state.invite_by_number_manager
    await manager.stop()
    return {"ok": True}


@app.get("/invite_by_number/status", response_model=schemas.InviteByNumberStatusResponse)
async def invite_by_number_status() -> schemas.InviteByNumberStatusResponse:
    manager: InviteByNumberManager = app.state.invite_by_number_manager
    return schemas.InviteByNumberStatusResponse(**manager.status())


@app.post("/campaign/start", response_model=schemas.CampaignStartResponse)
async def start_campaign(body: schemas.CampaignStartRequest) -> schemas.CampaignStartResponse:
    manager: CampaignManager = app.state.campaign_manager
    payload = MessagePayload(
        text=body.message,
        media_path=body.media_path,
        media_paths=body.media_paths,
        media_kind=body.media_kind,
        buttons_raw=body.buttons_raw,
        parse_mode=body.parse_mode,
        silent=body.silent,
        link_preview=body.link_preview,
        forward_link=body.forward_link,
        bot_relay_username=body.bot_relay_username,
        bot_relay_message_ids=body.bot_relay_message_ids,
        schedule_at=body.schedule_at,
        pin_after_send=body.pin_after_send,
    )
    try:
        campaign_id = manager.start(
            body.target,
            payload,
            account_folder=body.account_folder,
            messages_per_account_min=body.messages_per_account_min,
            messages_per_account_max=body.messages_per_account_max,
            exact_total_target=body.exact_total_target,
            worker_batch_size=body.worker_batch_size,
            worker_batch_delay_sec=body.worker_batch_delay_sec,
            repeat_every_hours=body.repeat_every_hours,
        )
    except CampaignAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.CampaignStartResponse(campaign_id=campaign_id, started=True)


@app.post("/campaign/stop")
async def stop_campaign() -> dict:
    manager: CampaignManager = app.state.campaign_manager
    await manager.stop()
    return {"ok": True}


@app.get("/campaign/status", response_model=schemas.CampaignStatusResponse)
async def campaign_status() -> schemas.CampaignStatusResponse:
    manager: CampaignManager = app.state.campaign_manager
    return schemas.CampaignStatusResponse(**manager.status())


@app.post("/parsing/start", response_model=schemas.ParseStartResponse)
async def start_parsing(body: schemas.ParseStartRequest) -> schemas.ParseStartResponse:
    manager: ParsingManager = app.state.parsing_manager
    try:
        job_id = manager.start(
            entities=body.entities,
            strategy_name=body.strategy,
            topic_id=body.topic_id,
            filters=body.filters.model_dump(),
            export_mode=body.export_mode,
            export_path=body.export_path,
            redis_dedup_enabled=body.redis_dedup_enabled,
            job_key=body.job_key,
        )
    except ParsingAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.ParseStartResponse(job_id=job_id, started=True)


@app.post("/parsing/stop")
async def stop_parsing() -> dict:
    manager: ParsingManager = app.state.parsing_manager
    await manager.stop()
    return {"ok": True}


@app.get("/parsing/status", response_model=schemas.ParseStatusResponse)
async def parsing_status() -> schemas.ParseStatusResponse:
    manager: ParsingManager = app.state.parsing_manager
    return schemas.ParseStatusResponse(**manager.status())


@app.post("/proxy_check/start", response_model=schemas.ProxyCheckStartResponse)
async def start_proxy_check(body: schemas.ProxyCheckStartRequest) -> schemas.ProxyCheckStartResponse:
    manager: ProxyCheckManager = app.state.proxy_check_manager
    proxies = [p.model_dump() for p in body.proxies]
    try:
        job_id = manager.start(proxies, concurrency=body.concurrency)
    except ProxyCheckAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return schemas.ProxyCheckStartResponse(job_id=job_id, started=True)


@app.get("/proxy_check/status", response_model=schemas.ProxyCheckStatusResponse)
async def proxy_check_status() -> schemas.ProxyCheckStatusResponse:
    manager: ProxyCheckManager = app.state.proxy_check_manager
    return schemas.ProxyCheckStatusResponse(**manager.status())


def _proxy_repository() -> ProxyRepository:
    repository = app.state.proxy_repository
    if repository is None:
        raise HTTPException(status_code=503, detail="Proxy storage requires DATABASE_URL.")
    return repository


def _stored_proxy_check_manager() -> StoredProxyCheckManager:
    manager = app.state.stored_proxy_check_manager
    if manager is None:
        raise HTTPException(status_code=503, detail="Proxy storage requires DATABASE_URL.")
    return manager


def _stored_proxy_out(proxy) -> schemas.StoredProxyOut:
    return schemas.StoredProxyOut(
        id=proxy.id,
        proxy_type=proxy.proxy_type,
        host=proxy.host,
        port=proxy.port,
        username=proxy.username,
        password=proxy.password,
        version=proxy.version,
        status=proxy.status,
        response_ms=proxy.response_ms,
        country=proxy.country,
        error_message=proxy.error_message,
        last_checked_at=proxy.last_checked_at,
    )


@app.get("/proxies", response_model=List[schemas.StoredProxyOut])
async def list_stored_proxies() -> List[schemas.StoredProxyOut]:
    return [_stored_proxy_out(proxy) for proxy in await _proxy_repository().list_all()]


@app.post("/proxies", response_model=List[schemas.StoredProxyOut])
async def add_stored_proxies(
    body: schemas.ProxyBulkCreateRequest,
) -> List[schemas.StoredProxyOut]:
    try:
        proxies = parse_proxy_lines(body.proxy_list, body.protocol)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    repository = _proxy_repository()
    await repository.upsert_many(proxies)
    return [_stored_proxy_out(proxy) for proxy in await repository.list_all()]


@app.delete("/proxies/bad", response_model=schemas.ProxyDeleteResponse)
async def delete_bad_stored_proxies() -> schemas.ProxyDeleteResponse:
    deleted = await _proxy_repository().delete_bad()
    if deleted:
        await _refresh_account_proxy_assignments()
    return schemas.ProxyDeleteResponse(deleted=deleted)


@app.delete("/proxies", response_model=schemas.ProxyDeleteResponse)
async def delete_all_stored_proxies() -> schemas.ProxyDeleteResponse:
    deleted = await _proxy_repository().delete_all()
    if deleted:
        await _refresh_account_proxy_assignments()
    return schemas.ProxyDeleteResponse(deleted=deleted)


@app.delete("/proxies/{proxy_id}", response_model=schemas.ProxyDeleteResponse)
async def delete_stored_proxy(proxy_id: int) -> schemas.ProxyDeleteResponse:
    deleted = await _proxy_repository().delete_one(proxy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Proxy not found.")
    await _refresh_account_proxy_assignments()
    return schemas.ProxyDeleteResponse(deleted=1)


@app.post("/proxies/check", response_model=schemas.ProxyCheckStartResponse)
async def start_stored_proxy_check(
    body: schemas.StoredProxyCheckRequest,
) -> schemas.ProxyCheckStartResponse:
    try:
        job_id = _stored_proxy_check_manager().start(
            body.proxy_ids,
            concurrency=body.concurrency,
            timeout=body.timeout,
            retries=body.retries,
            retry_delay=body.retry_delay,
        )
    except StoredProxyCheckAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return schemas.ProxyCheckStartResponse(job_id=job_id, started=True)


@app.get(
    "/proxies/check/status",
    response_model=schemas.StoredProxyCheckStatusResponse,
)
async def stored_proxy_check_status() -> schemas.StoredProxyCheckStatusResponse:
    return schemas.StoredProxyCheckStatusResponse(**_stored_proxy_check_manager().status())


@app.post("/proxy_pool_check/start", response_model=schemas.ProxyPoolCheckStartResponse)
async def start_proxy_pool_check(
    body: schemas.ProxyPoolCheckStartRequest,
) -> schemas.ProxyPoolCheckStartResponse:
    manager: ProxyPoolCheckManager = app.state.proxy_pool_check_manager
    proxies = [p.model_dump() | {"type": body.protocol} for p in body.proxies]
    try:
        job_id = manager.start(
            mode=body.mode,
            proxies=proxies,
            request_count=body.request_count,
            concurrency=body.concurrency,
        )
    except ProxyPoolCheckAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return schemas.ProxyPoolCheckStartResponse(job_id=job_id, started=True)


@app.get("/proxy_pool_check/status", response_model=schemas.ProxyPoolCheckStatusResponse)
async def proxy_pool_check_status() -> schemas.ProxyPoolCheckStatusResponse:
    manager: ProxyPoolCheckManager = app.state.proxy_pool_check_manager
    return schemas.ProxyPoolCheckStatusResponse(**manager.status())


@app.post("/tdata_convert/start", response_model=schemas.TdataConvertStartResponse)
async def start_tdata_convert(body: schemas.TdataConvertStartRequest) -> schemas.TdataConvertStartResponse:
    manager: TdataConvertManager = app.state.tdata_convert_manager
    try:
        job_id = manager.start(
            body.tdata_dir, body.output_dir, body.all_accounts, body.passwords,
        )
    except TdataConvertAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.TdataConvertStartResponse(job_id=job_id, started=True)


@app.get("/tdata_convert/status", response_model=schemas.TdataConvertStatusResponse)
async def tdata_convert_status() -> schemas.TdataConvertStatusResponse:
    manager: TdataConvertManager = app.state.tdata_convert_manager
    return schemas.TdataConvertStatusResponse(**manager.status())


@app.post("/session_convert/start", response_model=schemas.SessionConvertStartResponse)
async def start_session_convert(
    body: schemas.SessionConvertStartRequest,
) -> schemas.SessionConvertStartResponse:
    manager: SessionConvertManager = app.state.session_convert_manager
    session_configs = [
        (item.session_path, item.json_path, item.output_subdir) for item in body.items
    ]
    try:
        job_id = manager.start(session_configs, body.output_base_dir)
    except SessionConvertAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return schemas.SessionConvertStartResponse(job_id=job_id, started=True)


@app.get("/session_convert/status", response_model=schemas.SessionConvertStatusResponse)
async def session_convert_status() -> schemas.SessionConvertStatusResponse:
    manager: SessionConvertManager = app.state.session_convert_manager
    return schemas.SessionConvertStatusResponse(**manager.status())


@app.post("/json_generator/start", response_model=schemas.JsonGeneratorStartResponse)
async def start_json_generator(
    body: schemas.JsonGeneratorStartRequest,
) -> schemas.JsonGeneratorStartResponse:
    manager: JsonGeneratorManager = app.state.json_generator_manager
    try:
        job_id = manager.start(body.database_path, body.sessions_dir, body.output_dir)
    except JsonGeneratorAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.JsonGeneratorStartResponse(job_id=job_id, started=True)


@app.post("/json_generator/stop")
async def stop_json_generator() -> dict:
    manager: JsonGeneratorManager = app.state.json_generator_manager
    await manager.stop()
    return {"ok": True}


@app.post("/json_generator/clear")
async def clear_json_generator() -> dict:
    manager: JsonGeneratorManager = app.state.json_generator_manager
    try:
        manager.clear()
    except JsonGeneratorAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@app.get("/json_generator/status", response_model=schemas.JsonGeneratorStatusResponse)
async def json_generator_status() -> schemas.JsonGeneratorStatusResponse:
    manager: JsonGeneratorManager = app.state.json_generator_manager
    return schemas.JsonGeneratorStatusResponse(**manager.status())


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    event_bus: EventBus = websocket.app.state.event_bus
    await handle_event_stream(websocket, event_bus)
