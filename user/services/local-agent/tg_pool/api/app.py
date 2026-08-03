from __future__ import annotations

import asyncio
import logging
import os
import secrets
import sqlite3
import uuid
from contextlib import asynccontextmanager, suppress
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import FastAPI, HTTPException, WebSocket
from dotenv import load_dotenv

from tg_pool import bootstrap
from tg_pool.accounts.account_manager_service import AccountManagerService
from tg_pool.accounts.account_registry import AccountRegistry, RegistryEntry
from tg_pool.accounts.cooldown_scheduler import CooldownScheduler
from tg_pool.accounts.discovery_poller import AccountDiscoveryPoller
from tg_pool.accounts.health_checker import AccountStatus
from tg_pool.accounts.proxy_safety import shared_proxy_groups, unproxied_phones
from tg_pool.accounts.session_crypto import load_key_from_env
from tg_pool.api import schemas
from tg_pool.api.datamoll import (
    DatamollDeliveryError,
    download_and_import_deliveries as import_datamoll_deliveries,
    save_order_receipt as save_datamoll_order_receipt,
)
from tg_pool.api.payment import (
    PaymentApiError,
    create_order as create_payment_order,
    fetch_balance as fetch_payment_balance,
    fetch_catalog as fetch_payment_catalog,
)
from tg_pool.api.events import handle_event_stream
from tg_pool.api.grizzly_sms import (
    GRIZZLY_SMS_API_URL,
    GRIZZLY_SMS_PROVIDER_NAME,
    close_activation as close_grizzly_sms_activation,
    fetch_balance as fetch_grizzly_sms_balance,
    fetch_countries as fetch_grizzly_sms_countries,
    fetch_operators as fetch_grizzly_sms_operators,
    fetch_telegram_price as fetch_grizzly_sms_telegram_price,
    request_number_v2 as request_grizzly_sms_number,
)
from tg_pool.api.hero_sms import (
    HeroSmsApiError,
    fetch_balance,
    fetch_countries,
    fetch_operators,
    fetch_telegram_offers,
)
from tg_pool.api.hero_sms_activation import (
    HeroSmsActivationAlreadyRunningError,
    HeroSmsActivationManager,
    HeroSmsTwoFactorError,
)
from tg_pool.api.invite_by_number import (
    InviteByNumberAlreadyRunningError,
    InviteByNumberManager,
    InviteRecipient,
    InviteSenderLink,
)
from tg_pool.api.number_checker import (
    NumberCheckerAlreadyRunningError,
    NumberCheckerManager,
)
from tg_pool.api.json_generator import JsonGeneratorAlreadyRunningError, JsonGeneratorManager
from tg_pool.api.license_gate import LicenseGateMiddleware
from tg_pool.api.local_auth import LocalAuthMiddleware
from tg_pool.features.messaging import build_warmup_policy
from tg_pool.api.parsing import ParsingAlreadyRunningError, ParsingManager
from tg_pool.api.pool_guard import PoolAccessGuard, PoolBusyError
from tg_pool.api.proxy_check import ProxyCheckAlreadyRunningError, ProxyCheckManager
from tg_pool.api.proxy_pool_check import (
    ProxyPoolCheckAlreadyRunningError,
    ProxyPoolCheckManager,
)
from tg_pool.api.session_convert import SessionConvertAlreadyRunningError, SessionConvertManager
from tg_pool.api.stored_proxy_check import (
    StoredProxyCheckAlreadyRunningError,
    StoredProxyCheckManager,
)
from tg_pool.api.send_by_numbers import (
    SendByNumbersAlreadyRunningError,
    SendByNumbersManager,
)
from tg_pool.api.send_by_id import SendByIdAlreadyRunningError, SendByIdManager
from tg_pool.api.scheduled_campaigns import ScheduledCampaignManager
from tg_pool.api.engagement import EngagementAlreadyRunningError, EngagementManager
from tg_pool.api.stories import StoriesAlreadyRunningError, StoriesManager
from tg_pool.api.sms_pool import (
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
from tg_pool.api.tdata_convert import TdataConvertAlreadyRunningError, TdataConvertManager
from tg_pool.api.telegram_auth import TelegramAuthenticator
from tg_pool.config import AccountConfig, ProxyConfig, TimingPolicy
from tg_pool.db.license_repository import LicenseStateRepository, ensure_license_state_table
from tg_pool.db.proxy_repository import ProxyRepository, ensure_proxy_table
from tg_pool.db.repository import ensure_durable_tables
from tg_pool.db.scheduled_campaign_repository import (
    ScheduledCampaignRepository,
    ensure_scheduled_campaigns_table,
)
from tg_pool.licensing.client import LicenseServerClient
from tg_pool.licensing.service import LicenseService
from tg_pool.monitoring.event_bus import EventBus
from tg_pool.proxy.proxy_parser import parse_proxy_lines

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

    from tg_pool.accounts.account_loader import ProxyAllocator

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
    number_checker_manager: NumberCheckerManager = app.state.number_checker_manager
    send_manager: SendByNumbersManager = app.state.send_by_numbers_manager
    send_by_id_manager: SendByIdManager = app.state.send_by_id_manager
    engagement_manager: EngagementManager = app.state.engagement_manager
    stories_manager: StoriesManager = app.state.stories_manager
    for account in updated_accounts:
        invite_manager.register_account(account)
        number_checker_manager.register_account(account)
        send_manager.register_account(account)
        send_by_id_manager.register_account(account)
        engagement_manager.register_account(account)
        stories_manager.register_account(account)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    bootstrap.configure_logging(debug=False, log_dir=os.getenv("LOG_DIR", ""))

    event_bus = EventBus()
    session_factory = bootstrap.build_db_session_factory()
    if session_factory is not None:
        await ensure_durable_tables(session_factory)
    proxy_session_factory = bootstrap.build_proxy_db_session_factory(session_factory)
    owns_proxy_engine = (
        proxy_session_factory is not None and proxy_session_factory is not session_factory
    )
    if proxy_session_factory is not None:
        await ensure_proxy_table(proxy_session_factory)
    proxy_repository = (
        ProxyRepository(proxy_session_factory) if proxy_session_factory else None
    )

    # Opt-in, same pattern as DATABASE_URL: unset -> engagement daily-account caps are
    # simply not enforced, everything else (streams, stagger delay, auto-stop) still works.
    redis_client = bootstrap.build_redis_client()

    # Opt-in shared secret between this process and whatever spawned it (see
    # tg_pool/api/local_auth.py) -- unset -> no local-auth enforcement, matching every
    # other opt-in env var in this app.
    app.state.local_api_token = os.getenv("LOCAL_API_TOKEN", "")

    # Licensing is opt-in via LICENSE_SERVER_URL, same as DATABASE_URL/REDIS_URL elsewhere in
    # this app: unset -> the gate middleware waves every request through unchanged, so local
    # development never needs a running license server. Set it once license_server is deployed.
    license_server_url = os.getenv("LICENSE_SERVER_URL", "")
    licensing_enabled = bool(license_server_url)
    if session_factory is not None:
        await ensure_license_state_table(session_factory)
    license_service = LicenseService(
        LicenseServerClient(license_server_url or "http://127.0.0.1:8100"),
        LicenseStateRepository(session_factory) if session_factory is not None else None,
        revalidate_interval=timedelta(
            minutes=bootstrap.env_int("LICENSE_REVALIDATE_INTERVAL_MINUTES", "30")
        ),
        offline_grace=timedelta(hours=bootstrap.env_int("LICENSE_OFFLINE_GRACE_HOURS", "72")),
    )
    if licensing_enabled:
        await license_service.restore_cached()
    app.state.license_service = license_service
    app.state.licensing_enabled = licensing_enabled
    license_revalidation_task = (
        asyncio.create_task(license_service.run_periodic_revalidation())
        if licensing_enabled
        else None
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

    # Opt-in (WARMUP_ENABLED) -- None means every manager below runs unthrottled by
    # account age, same as before this was wired in from tg_pool/features/messaging.py.
    warmup_policy = build_warmup_policy()

    policy = _build_timing_policy()
    health_checker = bootstrap.build_health_checker(policy, event_bus)
    account_manager = AccountManagerService(registry, health_checker)

    try:
        session_encryption_key = _build_session_encryption_key()
    except ValueError as exc:
        logger.error("Invalid SESSION_ENCRYPTION_KEY at startup — sessions will run unencrypted: %s", exc)
        session_encryption_key = None

    pool_guard = PoolAccessGuard()

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
    app.state.number_checker_manager = NumberCheckerManager(
        accounts=list(primary) + list(spares),
        pool_guard=pool_guard,
        session_encryption_key=session_encryption_key,
    )
    app.state.send_by_numbers_manager = SendByNumbersManager(
        accounts=list(primary) + list(spares),
        pool_guard=pool_guard,
        session_encryption_key=session_encryption_key,
        proxy_repository=proxy_repository,
        redis_client=redis_client,
        registry=registry,
        warmup_policy=warmup_policy,
    )
    app.state.send_by_id_manager = SendByIdManager(
        accounts=list(primary) + list(spares),
        pool_guard=pool_guard,
        session_encryption_key=session_encryption_key,
        proxy_repository=proxy_repository,
        redis_client=redis_client,
        registry=registry,
        warmup_policy=warmup_policy,
    )
    app.state.engagement_manager = EngagementManager(
        accounts=list(primary) + list(spares),
        pool_guard=pool_guard,
        session_encryption_key=session_encryption_key,
        redis_client=redis_client,
        proxy_repository=proxy_repository,
        registry=registry,
        warmup_policy=warmup_policy,
    )
    app.state.stories_manager = StoriesManager(
        accounts=list(primary) + list(spares),
        pool_guard=pool_guard,
        session_encryption_key=session_encryption_key,
        redis_client=redis_client,
        proxy_repository=proxy_repository,
        registry=registry,
        warmup_policy=warmup_policy,
    )

    scheduled_campaign_repository = (
        ScheduledCampaignRepository(session_factory) if session_factory is not None else None
    )
    if session_factory is not None:
        await ensure_scheduled_campaigns_table(session_factory)
    app.state.scheduled_campaign_repository = scheduled_campaign_repository
    app.state.scheduled_campaign_manager = (
        ScheduledCampaignManager(
            repository=scheduled_campaign_repository,
            send_by_id_manager=app.state.send_by_id_manager,
            send_by_numbers_manager=app.state.send_by_numbers_manager,
            poll_interval=bootstrap.env_float("SCHEDULED_CAMPAIGNS_POLL_INTERVAL_SEC", "30"),
        )
        if scheduled_campaign_repository is not None
        else None
    )
    scheduled_campaigns_shutdown = asyncio.Event()
    scheduled_campaigns_task = (
        asyncio.create_task(app.state.scheduled_campaign_manager.run(scheduled_campaigns_shutdown))
        if app.state.scheduled_campaign_manager is not None
        else None
    )

    # Opt-in (COOLDOWN_SCHEDULER_ENABLED), same convention as WARMUP_ENABLED --
    # was built (tg_pool/accounts/cooldown_scheduler.py) but never reachable from this
    # API; without it, an account flagged SPAMBLOCK/FROZEN/FLOOD stays excluded
    # from the pool forever even after Telegram lifts the restriction.
    cooldown_shutdown = asyncio.Event()
    cooldown_enabled = os.getenv("COOLDOWN_SCHEDULER_ENABLED", "0").lower() in ("1", "true", "yes")
    cooldown_task = (
        asyncio.create_task(
            CooldownScheduler(
                registry,
                health_checker,
                poll_interval=bootstrap.env_float("COOLDOWN_POLL_INTERVAL_SEC", "60"),
            ).run(cooldown_shutdown)
        )
        if cooldown_enabled
        else None
    )

    # On by default (unlike warmup/cooldown) -- this only reads directories and
    # registers whatever load_accounts_from_directory()/ensure_all_proxied() would
    # already accept via the manual Refresh button; it just does it on a timer so
    # an operator who drops a purchased account base into Data\Accounts doesn't
    # have to notice and click Refresh themselves.
    discovery_shutdown = asyncio.Event()
    discovery_enabled = os.getenv("ACCOUNT_DISCOVERY_ENABLED", "1").lower() in ("1", "true", "yes")
    discovery_task = (
        asyncio.create_task(
            AccountDiscoveryPoller(
                _rescan_account_storage,
                event_bus,
                poll_interval=bootstrap.env_float("ACCOUNT_DISCOVERY_POLL_INTERVAL_SEC", "20"),
            ).run(discovery_shutdown)
        )
        if discovery_enabled
        else None
    )

    accounts_dir = os.getenv("ACCOUNTS_DIR", "accounts")
    app.state.accounts_dir = accounts_dir
    app.state.tdata_accounts_dir = os.getenv(
        "TDATA_ACCOUNTS_DIR",
        os.path.join(os.path.dirname(accounts_dir), "Tdata"),
    )
    app.state.datamoll_receipts_dir = os.path.join(
        os.path.dirname(accounts_dir),
        "DatamollReceipts",
    )
    fingerprint_file = os.getenv(
        "TELEGRAM_FINGERPRINT_FILE",
        os.path.join(os.path.dirname(accounts_dir), "Fingerprints", "telegram_devices.xlsx"),
    )
    registration_proxy_lock = asyncio.Lock()
    registration_proxy_call_count = 0

    async def next_registration_proxy() -> Optional[ProxyConfig]:
        nonlocal registration_proxy_call_count
        proxies = await _load_proxy_inventory(app.state.proxy_repository)
        if not proxies:
            return None
        accounts_per_proxy = bootstrap.env_int("ACCOUNTS_PER_PROXY", "1")
        if accounts_per_proxy < 1:
            raise ValueError("accounts_per_proxy must be >= 1")
        async with registration_proxy_lock:
            proxy_index = (
                registration_proxy_call_count // accounts_per_proxy
            ) % len(proxies)
            registration_proxy_call_count += 1
            return proxies[proxy_index]

    async def register_saved_account(account) -> None:
        known_phones = {item.phone for item in primary} | {item.phone for item in spares}
        if account.phone not in known_phones:
            primary.append(account)
            await registry.register_many([account])
            app.state.invite_by_number_manager.register_account(account)
            app.state.number_checker_manager.register_account(account)
            app.state.send_by_numbers_manager.register_account(account)
            app.state.send_by_id_manager.register_account(account)
            app.state.engagement_manager.register_account(account)
            app.state.stories_manager.register_account(account)

    def current_fingerprint_signatures() -> List[tuple]:
        return [(account.device_model, account.app_version) for account in primary + spares]

    # Best-effort: a shared, centrally-updatable name pool (see
    # license_server/profile_names.py) instead of every install stamping new
    # accounts from the same fixed list baked into the build. Unreachable/disabled
    # license server -> TelegramAuthenticator falls back to its own built-in list.
    profile_name_provider = None
    if licensing_enabled:
        try:
            profile_first_names, profile_last_names = await LicenseServerClient(
                license_server_url
            ).fetch_profile_names()

            def profile_name_provider() -> tuple:
                return secrets.choice(profile_first_names), secrets.choice(profile_last_names)
        except Exception as exc:
            logger.warning(
                "Could not fetch the shared profile-name pool from the license server "
                "-- falling back to the built-in list: %s", exc
            )

    telegram_authenticator = TelegramAuthenticator(
        fingerprint_file=fingerprint_file,
        accounts_dir=accounts_dir,
        encryption_key=session_encryption_key,
        proxy_provider=next_registration_proxy,
        fingerprint_signatures_provider=current_fingerprint_signatures,
        profile_name_provider=profile_name_provider,
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
        if scheduled_campaigns_task is not None:
            scheduled_campaigns_shutdown.set()
            await scheduled_campaigns_task
        if cooldown_task is not None:
            cooldown_shutdown.set()
            await cooldown_task
        if discovery_task is not None:
            discovery_shutdown.set()
            await discovery_task
        await app.state.invite_by_number_manager.stop()
        await app.state.number_checker_manager.stop()
        await app.state.send_by_numbers_manager.stop()
        await app.state.send_by_id_manager.stop()
        await app.state.engagement_manager.stop()
        await app.state.stories_manager.stop()
        await app.state.hero_sms_activation_manager.stop()
        await app.state.sms_pool_activation_manager.stop()
        await app.state.grizzly_sms_activation_manager.stop()
        if app.state.stored_proxy_check_manager is not None:
            await app.state.stored_proxy_check_manager.stop()
        if license_revalidation_task is not None:
            license_revalidation_task.cancel()
            with suppress(asyncio.CancelledError):
                await license_revalidation_task
        await registry.close()
        if owns_proxy_engine:
            await proxy_session_factory.kw["bind"].dispose()
        if redis_client is not None:
            await redis_client.aclose()


app = FastAPI(title="tg_pool_framework control API", lifespan=lifespan)
app.add_middleware(LicenseGateMiddleware, allow_prefixes=("/health", "/license"))
app.add_middleware(LocalAuthMiddleware)


async def _rescan_account_storage() -> tuple[List[str], List[dict]]:
    """
    Picks up accounts dropped into ACCOUNTS_DIR/SPARE_ACCOUNTS_DIR/TDATA_ACCOUNTS_DIR
    since the last scan. Returns (newly_registered_phones, load_failures) so a
    caller (the manual /accounts/rescan endpoint, or the background discovery
    poller) can report back exactly what happened, not just a bare count.
    """
    registry: AccountRegistry = app.state.registry
    primary: list = app.state.primary_accounts
    spares: list = app.state.spare_accounts

    load_failures: List[dict] = []
    fresh_primary, fresh_spares = bootstrap.load_accounts(load_failures=load_failures)
    fresh_tdata = await bootstrap.load_tdata_accounts(load_failures=load_failures)
    fresh_primary = _dedupe_accounts_by_phone(fresh_primary + fresh_tdata)

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
        app.state.number_checker_manager.register_account(account)
        app.state.send_by_id_manager.register_account(account)
        app.state.send_by_numbers_manager.register_account(account)
        app.state.engagement_manager.register_account(account)
        app.state.stories_manager.register_account(account)

    new_phones = [a.phone for a in new_primary + new_spares]
    return new_phones, load_failures


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/license/activate", response_model=schemas.LicenseStatusOut)
async def license_activate(body: schemas.LicenseActivateRequest) -> schemas.LicenseStatusOut:
    license_service: LicenseService = app.state.license_service
    status = await license_service.activate(body.license_key, body.hwid)
    return schemas.LicenseStatusOut(
        valid=status.valid, tier=status.tier, expires_at=status.expires_at, reason=status.reason
    )


@app.get("/license/status", response_model=schemas.LicenseStatusOut)
async def license_status() -> schemas.LicenseStatusOut:
    license_service: LicenseService = app.state.license_service
    if not app.state.licensing_enabled:
        return schemas.LicenseStatusOut(valid=True, reason="licensing_disabled")
    status = license_service.status()
    return schemas.LicenseStatusOut(
        valid=status.valid, tier=status.tier, expires_at=status.expires_at, reason=status.reason
    )


@app.post("/datamoll/balance", response_model=schemas.DatamollBalanceOut)
async def datamoll_balance(
    body: schemas.PaymentApiKeyRequest,
) -> schemas.DatamollBalanceOut:
    try:
        balance = await fetch_payment_balance(body.api_key)
    except (PaymentApiError, ValueError) as exc:
        logger.warning("Payment balance request failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.DatamollBalanceOut(**balance)


@app.post("/datamoll/catalog", response_model=schemas.DatamollCatalogOut)
async def datamoll_catalog(
    body: schemas.PaymentApiKeyRequest,
) -> schemas.DatamollCatalogOut:
    try:
        products = await fetch_payment_catalog(body.api_key)
    except (PaymentApiError, ValueError) as exc:
        logger.warning("Payment catalog request failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.DatamollCatalogOut(
        items=[schemas.DatamollProductOut(**product) for product in products]
    )


@app.post("/datamoll/orders", response_model=schemas.DatamollPurchaseOut)
async def datamoll_purchase(
    body: schemas.DatamollPurchaseRequest,
) -> schemas.DatamollPurchaseOut:
    try:
        order = await create_payment_order(
            body.api_key,
            product_id=body.product_id,
            quantity=body.quantity,
            external_order_id=body.external_order_id,
        )
        items = order.get("items")
        if not isinstance(items, list):
            raise PaymentApiError(
                "Payment service returned an order without delivered account data"
            )
        receipt_file = save_datamoll_order_receipt(
            order,
            app.state.datamoll_receipts_dir,
        )
        imported = await import_datamoll_deliveries(
            items,
            accounts_dir=app.state.accounts_dir,
            tdata_dir=app.state.tdata_accounts_dir,
        )
        new_phones, _load_failures = await _rescan_account_storage()
        new_accounts = len(new_phones)
        return schemas.DatamollPurchaseOut(
            order_id=int(order["order_id"]),
            external_order_id=str(
                order.get("external_order_id") or body.external_order_id
            ),
            status=str(order.get("status") or ""),
            payment_status=str(order.get("payment_status") or ""),
            product_id=int(order["product_id"]),
            quantity=int(order["quantity"]),
            unit_price=str(order.get("unit_price") or "0"),
            total_amount=str(order.get("total_amount") or "0"),
            currency=str(order.get("currency") or "USD"),
            delivered_count=len(items),
            receipt_file=receipt_file,
            reused_existing=bool(order.get("reused_existing")),
            downloaded_files=imported.downloaded_files,
            imported_sessions=imported.imported_sessions,
            imported_tdata=imported.imported_tdata,
            skipped_existing=imported.skipped_existing,
            registered_accounts=new_accounts,
        )
    except (
        PaymentApiError,
        DatamollDeliveryError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        logger.warning(
            "Datamoll order %s failed or its delivery could not be imported: %s",
            body.external_order_id,
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
        session_path=f"{entry.account.session_path}.session",
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


@app.get("/accounts/proxy_coverage", response_model=schemas.ProxyCoverageOut)
async def accounts_proxy_coverage() -> schemas.ProxyCoverageOut:
    accounts: List[AccountConfig] = app.state.primary_accounts + app.state.spare_accounts
    missing = unproxied_phones(accounts)
    shared = shared_proxy_groups(accounts)
    largest = max((len(phones) for phones in shared.values()), default=0)
    return schemas.ProxyCoverageOut(
        total_accounts=len(accounts),
        unproxied_count=len(missing),
        unproxied_phones=missing,
        shared_proxy_group_count=len(shared),
        largest_shared_group_size=largest,
    )


@app.get("/accounts/default_credentials", response_model=schemas.DefaultCredentialsOut)
async def get_default_credentials() -> schemas.DefaultCredentialsOut:
    """
    The api_id/api_hash applied to bare .session files dropped into
    ACCOUNTS_DIR/SPARE_ACCOUNTS_DIR with no .json companion (see
    load_accounts_from_directory). Read fresh from the environment every call
    so it reflects whatever set_default_credentials() last wrote.
    """
    return schemas.DefaultCredentialsOut(
        api_id=int(os.getenv("TG_API_ID_DEFAULT", "0") or "0"),
        api_hash=os.getenv("TG_API_HASH_DEFAULT", ""),
    )


@app.post("/accounts/default_credentials", response_model=schemas.DefaultCredentialsOut)
async def set_default_credentials(body: schemas.DefaultCredentialsIn) -> schemas.DefaultCredentialsOut:
    """
    Takes effect immediately for the next rescan (manual or the background
    AccountDiscoveryPoller) -- no backend restart needed, since
    bootstrap.load_accounts() reads these env vars fresh on every call.
    Not persisted here; the WPF launcher re-sends its saved value on every
    startup (same pattern as LicenseGateway.SyncBackendAsync for the license key).
    """
    os.environ["TG_API_ID_DEFAULT"] = str(body.api_id)
    os.environ["TG_API_HASH_DEFAULT"] = body.api_hash
    return schemas.DefaultCredentialsOut(api_id=body.api_id, api_hash=body.api_hash)


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
    """Re-scans the accounts/tdata directories for newly dropped accounts and registers them."""
    new_phones, load_failures = await _rescan_account_storage()
    return schemas.RescanResponse(
        new_accounts=len(new_phones),
        new_phones=new_phones,
        failures=[schemas.AccountLoadFailureOut(**f) for f in load_failures],
    )


@app.post("/number_checker/start", response_model=schemas.NumberCheckerStartResponse)
async def start_number_checker(
    body: schemas.NumberCheckerStartRequest,
) -> schemas.NumberCheckerStartResponse:
    manager: NumberCheckerManager = app.state.number_checker_manager
    try:
        job_id = manager.start(
            phone_numbers=body.phone_numbers,
            database_path=body.database_path,
            sender_phones=body.sender_phones,
            request_profile_data=body.request_profile_data,
            gender_detection=body.gender_detection,
            delay_min_sec=body.delay_min_sec,
            delay_max_sec=body.delay_max_sec,
            max_flood_wait_sec=body.max_flood_wait_sec,
            requests_per_account=body.requests_per_account,
            streams=body.streams,
            stream_delay_min_sec=body.stream_delay_min_sec,
            stream_delay_max_sec=body.stream_delay_max_sec,
            remove_imported_contacts=body.remove_imported_contacts,
            results_dir=body.results_dir,
        )
    except NumberCheckerAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.NumberCheckerStartResponse(job_id=job_id, started=True)


@app.post("/number_checker/stop")
async def stop_number_checker() -> dict:
    manager: NumberCheckerManager = app.state.number_checker_manager
    await manager.stop()
    return {"ok": True}


@app.get("/number_checker/status", response_model=schemas.NumberCheckerStatusResponse)
async def number_checker_status() -> schemas.NumberCheckerStatusResponse:
    manager: NumberCheckerManager = app.state.number_checker_manager
    return schemas.NumberCheckerStatusResponse(**manager.status())


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
            media_paths=body.media_paths,
            forward_links=body.forward_links,
            bot_relay_username=body.bot_relay_username,
            bot_relay_message_ids=body.bot_relay_message_ids,
            sms_per_account_min=body.sms_per_account_min,
            sms_per_account_max=body.sms_per_account_max,
            delay_min_sec=body.delay_min_sec,
            delay_max_sec=body.delay_max_sec,
            max_flood_wait_sec=body.max_flood_wait_sec,
            delete_dialog=body.delete_dialog,
            link_preview=body.link_preview,
            silent=body.silent,
            auto_repost=body.auto_repost,
            remove_imported_contacts=body.remove_imported_contacts,
            pin_message=body.pin_message,
            video_note=body.video_note,
            self_destruct_sec=body.self_destruct_sec,
            schedule_at=body.schedule_at,
            streams=body.streams,
            auto_stop_ban=body.auto_stop_ban,
            auto_stop_spamblock=body.auto_stop_spamblock,
            auto_stop_floodwait=body.auto_stop_floodwait,
            repeat_every_hours=body.repeat_every_hours,
            require_proxy=body.require_proxy,
            results_dir=body.results_dir,
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


@app.post("/send_by_id/start", response_model=schemas.SendByIdStartResponse)
async def start_send_by_id(body: schemas.SendByIdStartRequest) -> schemas.SendByIdStartResponse:
    manager: SendByIdManager = app.state.send_by_id_manager
    try:
        job_id = manager.start(
            database_path=body.database_path,
            message=body.message,
            sender_phones=body.sender_phones,
            media_paths=body.media_paths,
            forward_links=body.forward_links,
            bot_relay_username=body.bot_relay_username,
            bot_relay_message_ids=body.bot_relay_message_ids,
            sms_per_account_min=body.sms_per_account_min,
            sms_per_account_max=body.sms_per_account_max,
            delay_min_sec=body.delay_min_sec,
            delay_max_sec=body.delay_max_sec,
            max_flood_wait_sec=body.max_flood_wait_sec,
            delete_dialog=body.delete_dialog,
            link_preview=body.link_preview,
            silent=body.silent,
            auto_repost=body.auto_repost,
            leave_donor_groups=body.leave_donor_groups,
            pin_message=body.pin_message,
            video_note=body.video_note,
            self_destruct_sec=body.self_destruct_sec,
            schedule_at=body.schedule_at,
            streams=body.streams,
            auto_stop_ban=body.auto_stop_ban,
            auto_stop_spamblock=body.auto_stop_spamblock,
            auto_stop_floodwait=body.auto_stop_floodwait,
            repeat_every_hours=body.repeat_every_hours,
            require_proxy=body.require_proxy,
            results_dir=body.results_dir,
        )
    except SendByIdAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.SendByIdStartResponse(job_id=job_id, started=True)


@app.post("/send_by_id/stop")
async def stop_send_by_id() -> dict:
    manager: SendByIdManager = app.state.send_by_id_manager
    await manager.stop()
    return {"ok": True}


@app.get("/send_by_id/status", response_model=schemas.SendByIdStatusResponse)
async def send_by_id_status() -> schemas.SendByIdStatusResponse:
    manager: SendByIdManager = app.state.send_by_id_manager
    return schemas.SendByIdStatusResponse(**manager.status())


def _scheduled_campaign_manager() -> ScheduledCampaignManager:
    manager = app.state.scheduled_campaign_manager
    if manager is None:
        raise HTTPException(status_code=503, detail="Scheduled campaigns require DATABASE_URL.")
    return manager


def _scheduled_campaign_out(campaign) -> schemas.ScheduledCampaignOut:
    return schemas.ScheduledCampaignOut(
        id=campaign.id,
        name=campaign.name,
        campaign_type=campaign.campaign_type,
        start_at=campaign.start_at,
        repeat_interval_hours=campaign.repeat_interval_hours,
        max_occurrences=campaign.max_occurrences,
        occurrences_run=campaign.occurrences_run,
        enabled=campaign.enabled,
        next_run_at=campaign.next_run_at,
        last_run_at=campaign.last_run_at,
        last_job_id=campaign.last_job_id,
        last_error=campaign.last_error,
    )


@app.post("/scheduled_campaigns", response_model=schemas.ScheduledCampaignOut)
async def create_scheduled_campaign(
    body: schemas.ScheduledCampaignCreateRequest,
) -> schemas.ScheduledCampaignOut:
    payload = body.send_by_id if body.campaign_type == "send_by_id" else body.send_by_numbers
    if payload is None:
        raise HTTPException(
            status_code=422,
            detail=f"campaign_type '{body.campaign_type}' requires a matching payload.",
        )
    try:
        campaign = await _scheduled_campaign_manager().create(
            name=body.name,
            campaign_type=body.campaign_type,
            payload=payload.model_dump(mode="json"),
            start_at=body.start_at,
            repeat_interval_hours=body.repeat_interval_hours,
            max_occurrences=body.max_occurrences,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _scheduled_campaign_out(campaign)


@app.get("/scheduled_campaigns", response_model=List[schemas.ScheduledCampaignOut])
async def list_scheduled_campaigns() -> List[schemas.ScheduledCampaignOut]:
    return [_scheduled_campaign_out(c) for c in await _scheduled_campaign_manager().list()]


@app.post("/scheduled_campaigns/{schedule_id}/cancel", response_model=schemas.ScheduledCampaignOut)
async def cancel_scheduled_campaign(schedule_id: int) -> schemas.ScheduledCampaignOut:
    campaign = await _scheduled_campaign_manager().cancel(schedule_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Scheduled campaign not found.")
    return _scheduled_campaign_out(campaign)


@app.delete("/scheduled_campaigns/{schedule_id}", response_model=schemas.ScheduledCampaignDeleteResponse)
async def delete_scheduled_campaign(schedule_id: int) -> schemas.ScheduledCampaignDeleteResponse:
    deleted = await _scheduled_campaign_manager().delete(schedule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Scheduled campaign not found.")
    return schemas.ScheduledCampaignDeleteResponse(deleted=1)


@app.post("/engagement/start", response_model=schemas.EngagementStartResponse)
async def start_engagement(body: schemas.EngagementStartRequest) -> schemas.EngagementStartResponse:
    manager: EngagementManager = app.state.engagement_manager
    try:
        job_id = manager.start(
            action_type=body.action_type,
            target_chat=body.target_chat,
            target_message_id=body.target_message_id,
            reaction_emoji=body.reaction_emoji,
            poll_option_index=body.poll_option_index,
            comment_text=body.comment_text,
            sender_phones=body.sender_phones,
            streams=body.streams,
            delay_min_sec=body.delay_min_sec,
            delay_max_sec=body.delay_max_sec,
            max_flood_wait_sec=body.max_flood_wait_sec,
            daily_cap_per_account=body.daily_cap_per_account,
            max_total_accounts=body.max_total_accounts,
            auto_stop_ban=body.auto_stop_ban,
            auto_stop_spamblock=body.auto_stop_spamblock,
            auto_stop_floodwait=body.auto_stop_floodwait,
            require_proxy=body.require_proxy,
            results_dir=body.results_dir,
        )
    except EngagementAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.EngagementStartResponse(job_id=job_id, started=True)


@app.post("/engagement/stop")
async def stop_engagement() -> dict:
    manager: EngagementManager = app.state.engagement_manager
    await manager.stop()
    return {"ok": True}


@app.get("/engagement/status", response_model=schemas.EngagementStatusResponse)
async def engagement_status() -> schemas.EngagementStatusResponse:
    manager: EngagementManager = app.state.engagement_manager
    return schemas.EngagementStatusResponse(**manager.status())


@app.post("/stories/start", response_model=schemas.StoriesStartResponse)
async def start_stories(body: schemas.StoriesStartRequest) -> schemas.StoriesStartResponse:
    manager: StoriesManager = app.state.stories_manager
    try:
        job_id = manager.start(
            action_type=body.action_type,
            target_chat=body.target_chat,
            target_story_id=body.target_story_id,
            reaction_emoji=body.reaction_emoji,
            media_path=body.media_path,
            caption=body.caption,
            privacy=body.privacy,
            period_hours=body.period_hours,
            sender_phones=body.sender_phones,
            streams=body.streams,
            delay_min_sec=body.delay_min_sec,
            delay_max_sec=body.delay_max_sec,
            max_flood_wait_sec=body.max_flood_wait_sec,
            daily_cap_per_account=body.daily_cap_per_account,
            max_total_accounts=body.max_total_accounts,
            auto_stop_ban=body.auto_stop_ban,
            auto_stop_spamblock=body.auto_stop_spamblock,
            auto_stop_floodwait=body.auto_stop_floodwait,
            require_proxy=body.require_proxy,
            results_dir=body.results_dir,
        )
    except StoriesAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.StoriesStartResponse(job_id=job_id, started=True)


@app.post("/stories/stop")
async def stop_stories() -> dict:
    manager: StoriesManager = app.state.stories_manager
    await manager.stop()
    return {"ok": True}


@app.get("/stories/status", response_model=schemas.StoriesStatusResponse)
async def stories_status() -> schemas.StoriesStatusResponse:
    manager: StoriesManager = app.state.stories_manager
    return schemas.StoriesStatusResponse(**manager.status())


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
            require_proxy=body.require_proxy,
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
            language=body.language,
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


@app.get("/parsing/sources", response_model=schemas.ParseSourcesResponse)
async def parsing_sources(limit: int = 200) -> schemas.ParseSourcesResponse:
    manager: ParsingManager = app.state.parsing_manager
    try:
        sources = await manager.list_sources(limit=limit)
    except ParsingAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return schemas.ParseSourcesResponse(sources=[schemas.ParseSourceOut(**s) for s in sources])


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
        ban_signal_count=proxy.ban_signal_count,
        last_ban_signal_at=proxy.last_ban_signal_at,
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
