from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ProxyStateOut(BaseModel):
    is_active: bool
    latency_ms: float
    proxy_type: str
    error_message: Optional[str] = None


class AccountOut(BaseModel):
    phone: str
    session_path: str = ""
    status: str = "unknown"
    is_premium: bool = False
    has_2fa: bool = False
    country: Optional[str] = None
    username: str = ""
    first_name: str = ""
    error_message: Optional[str] = None
    restriction_expires: Optional[datetime] = None
    role: str = ""
    folder: str = ""
    first_seen: Optional[datetime] = None
    last_checked: Optional[datetime] = None
    uses_proxy: bool = False
    proxy_label: Optional[str] = None
    proxy_status: Optional[str] = None
    proxy: Optional[ProxyStateOut] = None


class AssignValueRequest(BaseModel):
    value: str = Field(min_length=1)


class RecheckRequest(BaseModel):
    phones: Optional[List[str]] = None
    deep: bool = False


class HeroSmsApiKeyRequest(BaseModel):
    api_key: str = Field(min_length=1)


class HeroSmsCountryOut(BaseModel):
    id: int
    rus: str
    eng: str
    chn: str
    visible: int
    retry: int


class HeroSmsBalanceOut(BaseModel):
    balance: float


class HeroSmsOperatorsRequest(HeroSmsApiKeyRequest):
    country_id: int = Field(ge=0)


class HeroSmsOperatorsOut(BaseModel):
    operators: List[str] = Field(default_factory=list)


class HeroSmsPriceRequest(HeroSmsApiKeyRequest):
    country_id: int = Field(ge=0)


class HeroSmsPriceOfferOut(BaseModel):
    price: float = Field(gt=0)
    available: int = Field(ge=0)


class HeroSmsPriceOut(BaseModel):
    price: Optional[float] = None
    available: int = 0
    offers: List[HeroSmsPriceOfferOut] = Field(default_factory=list)


class HeroSmsActivationStartRequest(HeroSmsApiKeyRequest):
    country_id: int = Field(ge=0)
    operator: str = Field(min_length=1)
    target_count: int = Field(ge=1)
    concurrency: int = Field(ge=1, le=10)
    timeout_sec: int = Field(ge=30, le=1200)
    # Selected starting Telegram maxPrice tier.
    max_price: float = Field(gt=0)
    # Highest Telegram maxPrice the batch may climb to when lower tiers
    # return NO_NUMBERS / HTTP 404. Defaults to max_price (no climb).
    price_ceiling: Optional[float] = Field(default=None, gt=0)
    # Ascending Telegram max-price tiers from the offers catalog.
    price_offers: List[float] = Field(default_factory=list)


class HeroSmsActivationStartResponse(BaseModel):
    job_id: str
    started: bool


class HeroSmsActivationRowOut(BaseModel):
    started_at: str
    remaining_timeout_sec: int = 0
    row_id: str = ""
    activation_id: str = ""
    phone_number: str = ""
    operator: str = ""
    cost: float = 0.0
    status: str
    stage: str = ""
    code: str = ""
    message: str = ""
    needs_2fa: bool = False
    session_file: str = ""
    created_new_account: bool = False


class HeroSmsTwoFactorRequest(BaseModel):
    password: str = Field(min_length=1)


class HeroSmsActivationStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    rows: List[HeroSmsActivationRowOut] = Field(default_factory=list)
    error: Optional[str] = None
    target_count: int = 0
    success_count: int = 0
    concurrency: int = 0
    active_count: int = 0


class DatamollCredentialsRequest(BaseModel):
    api_key: str = Field(min_length=1)
    api_secret: str = Field(min_length=1)


class DatamollBalanceOut(BaseModel):
    balance: str
    credit_limit: str
    available_balance: str
    currency: str


class DatamollProductOut(BaseModel):
    product_id: int
    name: str
    price: str
    currency: str
    stock: int = Field(ge=0)
    min_order: int = Field(ge=1)
    max_order: Optional[int] = Field(default=None, ge=1)
    category_name: Optional[str] = None
    description: Optional[str] = None
    country: Optional[str] = None
    content_language: str = ""


class DatamollCatalogOut(BaseModel):
    items: List[DatamollProductOut] = Field(default_factory=list)


class DatamollPurchaseRequest(DatamollCredentialsRequest):
    product_id: int = Field(ge=1)
    quantity: int = Field(ge=1)
    external_order_id: str = Field(min_length=1, max_length=255)


class DatamollPurchaseOut(BaseModel):
    order_id: int
    external_order_id: str
    status: str
    payment_status: str
    product_id: int
    quantity: int
    unit_price: str
    total_amount: str
    currency: str
    delivered_count: int = Field(ge=0)
    receipt_file: str
    reused_existing: bool = False
    downloaded_files: int = Field(default=0, ge=0)
    imported_sessions: int = Field(default=0, ge=0)
    imported_tdata: int = Field(default=0, ge=0)
    skipped_existing: int = Field(default=0, ge=0)
    registered_accounts: int = Field(default=0, ge=0)


class RecheckResponse(BaseModel):
    checked: int
    alive: int
    banned: int
    unauthorized: int
    spamblock: int
    frozen: int
    flood: int


class AccountLoadFailureOut(BaseModel):
    file: str
    reason: str


class RescanResponse(BaseModel):
    new_accounts: int
    new_phones: List[str] = Field(default_factory=list)
    failures: List[AccountLoadFailureOut] = Field(default_factory=list)


class ParseFilterIn(BaseModel):
    last_seen_days: Optional[int] = None
    gender: Optional[str] = None
    has_avatar: bool = False
    premium: bool = False
    exclude_bots: bool = True


class ParseStartRequest(BaseModel):
    entities: List[str] = Field(min_length=1)
    strategy: str = "members"
    topic_id: Optional[int] = None
    filters: ParseFilterIn = Field(default_factory=ParseFilterIn)
    export_mode: str = "full"
    export_path: Optional[str] = None
    redis_dedup_enabled: bool = False
    job_key: Optional[str] = None
    language: str = "ru"


class ParseStartResponse(BaseModel):
    job_id: str
    started: bool


class ParseSourceOut(BaseModel):
    identifier: str
    title: str
    kind: str
    members_count: Optional[int] = None


class ParseSourcesResponse(BaseModel):
    sources: List[ParseSourceOut] = Field(default_factory=list)


class ParseStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    entities: List[str] = Field(default_factory=list)
    total_collected: int = 0
    sources: List[str] = Field(default_factory=list)
    export_path: Optional[str] = None
    db_path: Optional[str] = None
    report_path: Optional[str] = None
    txt_path: Optional[str] = None
    accounts_used: int = 0
    stats: Optional[Dict[str, int]] = None
    finished: bool = False
    error: Optional[str] = None


class ProxyCheckItemIn(BaseModel):
    type: str = "socks5"
    host: str = Field(min_length=1)
    port: int
    username: Optional[str] = None
    password: Optional[str] = None


class ProxyCheckStartRequest(BaseModel):
    proxies: List[ProxyCheckItemIn] = Field(min_length=1)
    concurrency: int = 10


class ProxyCheckStartResponse(BaseModel):
    job_id: str
    started: bool


class ProxyCheckResultOut(BaseModel):
    host: str
    port: int
    proxy_type: str
    is_active: bool
    latency_ms: float
    error_message: Optional[str] = None
    country: Optional[str] = None


class ProxyCheckStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    total: int = 0
    results: List[ProxyCheckResultOut] = Field(default_factory=list)
    finished: bool = False
    error: Optional[str] = None


class ProxyBulkCreateRequest(BaseModel):
    protocol: str = Field(pattern="^(http|socks5)$")
    proxy_list: str = Field(min_length=1)


class StoredProxyOut(BaseModel):
    id: int
    proxy_type: str
    host: str
    port: int
    username: str
    password: str
    version: str
    status: str
    response_ms: Optional[float] = None
    country: Optional[str] = None
    error_message: Optional[str] = None
    last_checked_at: Optional[datetime] = None
    ban_signal_count: int = 0
    last_ban_signal_at: Optional[datetime] = None


class ProxyCoverageOut(BaseModel):
    total_accounts: int
    unproxied_count: int
    unproxied_phones: List[str] = Field(default_factory=list)
    shared_proxy_group_count: int
    largest_shared_group_size: int = 0


class ProxyDeleteResponse(BaseModel):
    deleted: int


class DefaultCredentialsIn(BaseModel):
    api_id: int = Field(gt=0)
    api_hash: str = Field(pattern="^[0-9a-fA-F]{32}$")


class DefaultCredentialsOut(BaseModel):
    api_id: int = 0
    api_hash: str = ""


class StoredProxyCheckRequest(BaseModel):
    proxy_ids: Optional[List[int]] = None
    concurrency: int = Field(default=10, ge=1, le=100)
    timeout: float = Field(default=10.0, ge=1.0, le=45.0)
    retries: int = Field(default=2, ge=0, le=15)
    retry_delay: float = Field(default=0.5, ge=0.0, le=10.0)


class StoredProxyCheckStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    total: int = 0
    completed: int = 0
    finished: bool = False
    error: Optional[str] = None


class ProxyPoolCheckStartRequest(BaseModel):
    mode: str = Field(pattern="^(rotating|sticky)$")
    protocol: str = Field(pattern="^(http|socks5)$")
    proxies: List[ProxyCheckItemIn] = Field(min_length=1)
    request_count: Optional[int] = Field(default=None, ge=1)
    concurrency: int = Field(default=10, ge=1, le=100)


class ProxyPoolCheckStartResponse(BaseModel):
    job_id: str
    started: bool


class ProxyPoolCheckStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    mode: str = ""
    total: int = 0
    unique: int = 0
    duplicates: int = 0
    connection_errors: int = 0
    finished: bool = False
    error: Optional[str] = None


class TdataConvertStartRequest(BaseModel):
    tdata_dir: str = Field(min_length=1)
    output_dir: str = "sessions"
    all_accounts: bool = False
    passwords: Optional[Dict[str, str]] = None


class TdataConvertStartResponse(BaseModel):
    job_id: str
    started: bool


class TdataConvertResultOut(BaseModel):
    source: str
    output: Optional[str] = None
    success: bool
    error: str = ""


class TdataConvertStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    total: int = 0
    results: List[TdataConvertResultOut] = Field(default_factory=list)
    finished: bool = False
    error: Optional[str] = None


class SessionConvertItemIn(BaseModel):
    session_path: str = Field(min_length=1)
    json_path: str = Field(min_length=1)
    output_subdir: str = Field(min_length=1)


class SessionConvertStartRequest(BaseModel):
    items: List[SessionConvertItemIn] = Field(min_length=1)
    output_base_dir: str = "tdata_exports"


class SessionConvertStartResponse(BaseModel):
    job_id: str
    started: bool


class SessionConvertResultOut(BaseModel):
    source: str
    output: Optional[str] = None
    success: bool
    error: str = ""


class SessionConvertStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    total: int = 0
    results: List[SessionConvertResultOut] = Field(default_factory=list)
    finished: bool = False
    error: Optional[str] = None


class JsonGeneratorStartRequest(BaseModel):
    database_path: str = Field(min_length=1)
    sessions_dir: str = Field(min_length=1)
    output_dir: str = Field(min_length=1)


class JsonGeneratorStartResponse(BaseModel):
    job_id: str
    started: bool


class JsonGeneratorResultOut(BaseModel):
    time: str
    account: str
    message: str
    success: bool


class JsonGeneratorStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    total: int = 0
    results: List[JsonGeneratorResultOut] = Field(default_factory=list)
    finished: bool = False
    cancelled: bool = False
    error: Optional[str] = None


class EventOut(BaseModel):
    type: str
    data: dict


class InviteSenderLinkIn(BaseModel):
    sender_phone: str = Field(min_length=1)
    invite_link: str = Field(min_length=1)


class InviteRecipientIn(BaseModel):
    id: str = ""
    username: Optional[str] = None
    phone: Optional[str] = None


class InviteByNumberStartRequest(BaseModel):
    recipients: List[InviteRecipientIn] = Field(default_factory=list)
    recipient_ids: List[str] = Field(default_factory=list)
    sender_links: List[InviteSenderLinkIn] = Field(min_length=1)
    max_per_account: int = 40
    delay_min_sec: float = 1.0
    delay_max_sec: float = 10.0
    max_flood_wait_sec: float = 500.0
    message_template: str = "{invite_link}"
    require_proxy: bool = True


class InviteByNumberStartResponse(BaseModel):
    job_id: str
    started: bool


class InviteByNumberResultOut(BaseModel):
    recipient_id: str
    sender_phone: str = ""
    invite_link: str = ""
    state: str = "pending"
    message: str = ""


class InviteByNumberStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    total: int = 0
    sent: int = 0
    failed: int = 0
    per_account: Dict[str, int] = Field(default_factory=dict)
    finished: bool = False
    error: Optional[str] = None
    unproxied_senders: List[str] = Field(default_factory=list)
    results: List[InviteByNumberResultOut] = Field(default_factory=list)


class NumberCheckerStartRequest(BaseModel):
    phone_numbers: List[str] = Field(default_factory=list)
    database_path: Optional[str] = None
    sender_phones: List[str] = Field(default_factory=list)
    request_profile_data: bool = False
    gender_detection: bool = False
    delay_min_sec: float = 5.0
    delay_max_sec: float = 10.0
    max_flood_wait_sec: float = 500.0
    requests_per_account: int = 8
    streams: int = 1
    stream_delay_min_sec: float = 30.0
    stream_delay_max_sec: float = 45.0
    remove_imported_contacts: bool = True
    results_dir: str = "exports"


class NumberCheckerStartResponse(BaseModel):
    job_id: str
    started: bool


class NumberCheckerResultOut(BaseModel):
    phone: str
    state: str = "pending"
    account_phone: str = ""
    telegram_id: str = ""
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    bio: str = ""
    online_status: str = ""
    last_seen: str = ""
    gender: str = ""
    message: str = ""


class NumberCheckerStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    database_path: Optional[str] = None
    export_path: Optional[str] = None
    total: int = 0
    found: int = 0
    not_found: int = 0
    failed: int = 0
    pending: int = 0
    per_account: Dict[str, int] = Field(default_factory=dict)
    finished: bool = False
    error: Optional[str] = None
    results: List[NumberCheckerResultOut] = Field(default_factory=list)


class SendByNumbersStartRequest(BaseModel):
    phone_numbers: List[str] = Field(min_length=1)
    message: str = ""
    sender_phones: List[str] = Field(default_factory=list)
    media_paths: List[str] = Field(default_factory=list)
    forward_links: List[str] = Field(default_factory=list)
    bot_relay_username: Optional[str] = None
    bot_relay_message_ids: List[int] = Field(default_factory=list)
    sms_per_account_min: int = 1
    sms_per_account_max: int = 40
    delay_min_sec: float = 1.0
    delay_max_sec: float = 10.0
    max_flood_wait_sec: float = 500.0
    delete_dialog: bool = False
    link_preview: bool = True
    silent: bool = False
    auto_repost: bool = False
    remove_imported_contacts: bool = True
    pin_message: bool = False
    video_note: bool = False
    self_destruct_sec: Optional[int] = None
    schedule_at: Optional[datetime] = None
    streams: int = 1
    auto_stop_ban: int = 0
    auto_stop_spamblock: int = 0
    auto_stop_floodwait: int = 0
    repeat_every_hours: Optional[float] = None
    require_proxy: bool = True
    results_dir: str = "exports"


class SendByNumbersStartResponse(BaseModel):
    job_id: str
    started: bool


class SendByNumbersResultOut(BaseModel):
    recipient_phone: str
    sender_phone: str = ""
    state: str = "pending"
    message: str = ""
    cycle: int = 1


class SendByNumbersStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    total: int = 0
    sent: int = 0
    failed: int = 0
    per_account: Dict[str, int] = Field(default_factory=dict)
    finished: bool = False
    error: Optional[str] = None
    unproxied_senders: List[str] = Field(default_factory=list)
    results: List[SendByNumbersResultOut] = Field(default_factory=list)


class SendByIdStartRequest(BaseModel):
    database_path: str = Field(min_length=1)
    message: str = ""
    sender_phones: List[str] = Field(default_factory=list)
    media_paths: List[str] = Field(default_factory=list)
    forward_links: List[str] = Field(default_factory=list)
    bot_relay_username: Optional[str] = None
    bot_relay_message_ids: List[int] = Field(default_factory=list)
    sms_per_account_min: int = 1
    sms_per_account_max: int = 40
    delay_min_sec: float = 1.0
    delay_max_sec: float = 10.0
    max_flood_wait_sec: float = 500.0
    delete_dialog: bool = False
    link_preview: bool = True
    silent: bool = False
    auto_repost: bool = False
    leave_donor_groups: bool = False
    pin_message: bool = False
    video_note: bool = False
    self_destruct_sec: Optional[int] = None
    schedule_at: Optional[datetime] = None
    streams: int = 1
    auto_stop_ban: int = 0
    auto_stop_spamblock: int = 0
    auto_stop_floodwait: int = 0
    repeat_every_hours: Optional[float] = None
    require_proxy: bool = True
    results_dir: str = "exports"


class SendByIdStartResponse(BaseModel):
    job_id: str
    started: bool


class SendByIdResultOut(BaseModel):
    recipient_id: int
    sender_phone: str = ""
    username: str = ""
    donor: str = ""
    state: str = "pending"
    message: str = ""
    cycle: int = 1


class SendByIdStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    total: int = 0
    sent: int = 0
    failed: int = 0
    per_account: Dict[str, int] = Field(default_factory=dict)
    finished: bool = False
    error: Optional[str] = None
    unproxied_senders: List[str] = Field(default_factory=list)
    ban_count: int = 0
    spamblock_count: int = 0
    floodwait_count: int = 0
    cycle: int = 1
    export_path: Optional[str] = None
    ban_count: int = 0
    spamblock_count: int = 0
    floodwait_count: int = 0
    cycle: int = 1
    export_path: Optional[str] = None
    results: List[SendByIdResultOut] = Field(default_factory=list)


class ScheduledCampaignCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    campaign_type: str = Field(pattern="^(send_by_id|send_by_numbers)$")
    send_by_id: Optional[SendByIdStartRequest] = None
    send_by_numbers: Optional[SendByNumbersStartRequest] = None
    start_at: datetime
    repeat_interval_hours: Optional[float] = Field(default=None, ge=1 / 60)
    max_occurrences: Optional[int] = Field(default=None, ge=1)


class ScheduledCampaignOut(BaseModel):
    id: int
    name: str
    campaign_type: str
    start_at: datetime
    repeat_interval_hours: Optional[float] = None
    max_occurrences: Optional[int] = None
    occurrences_run: int = 0
    enabled: bool = True
    next_run_at: datetime
    last_run_at: Optional[datetime] = None
    last_job_id: Optional[str] = None
    last_error: Optional[str] = None


class ScheduledCampaignDeleteResponse(BaseModel):
    deleted: int


class EngagementStartRequest(BaseModel):
    action_type: str = Field(pattern="^(reaction|view|poll_vote|comment)$")
    target_chat: str = Field(min_length=1)
    target_message_id: int = Field(gt=0)
    reaction_emoji: str = ""
    poll_option_index: Optional[int] = Field(default=None, ge=0)
    comment_text: str = ""
    sender_phones: List[str] = Field(default_factory=list)
    streams: int = Field(default=1, ge=1)
    delay_min_sec: float = 1.0
    delay_max_sec: float = 8.0
    max_flood_wait_sec: float = 120.0
    daily_cap_per_account: Optional[int] = Field(default=None, ge=1)
    max_total_accounts: Optional[int] = Field(default=None, ge=1)
    auto_stop_ban: int = 0
    auto_stop_spamblock: int = 0
    auto_stop_floodwait: int = 0
    require_proxy: bool = True
    results_dir: str = "exports"


class EngagementStartResponse(BaseModel):
    job_id: str
    started: bool


class EngagementResultOut(BaseModel):
    account_phone: str
    state: str = "pending"
    message: str = ""


class EngagementStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    action_type: Optional[str] = None
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped_daily_cap: int = 0
    finished: bool = False
    error: Optional[str] = None
    ban_count: int = 0
    spamblock_count: int = 0
    floodwait_count: int = 0
    unproxied_senders: List[str] = Field(default_factory=list)
    export_path: Optional[str] = None
    results: List[EngagementResultOut] = Field(default_factory=list)


class StoriesStartRequest(BaseModel):
    action_type: str = Field(pattern="^(view|reaction|post)$")
    target_chat: str = ""
    target_story_id: int = Field(default=0, ge=0)
    reaction_emoji: str = ""
    media_path: str = ""
    caption: str = ""
    privacy: str = Field(default="everyone", pattern="^(everyone|contacts)$")
    period_hours: Optional[int] = Field(default=None, ge=1)
    sender_phones: List[str] = Field(default_factory=list)
    streams: int = Field(default=1, ge=1)
    delay_min_sec: float = 1.0
    delay_max_sec: float = 8.0
    max_flood_wait_sec: float = 120.0
    daily_cap_per_account: Optional[int] = Field(default=None, ge=1)
    max_total_accounts: Optional[int] = Field(default=None, ge=1)
    auto_stop_ban: int = 0
    auto_stop_spamblock: int = 0
    auto_stop_floodwait: int = 0
    require_proxy: bool = True
    results_dir: str = "exports"


class StoriesStartResponse(BaseModel):
    job_id: str
    started: bool


class StoriesResultOut(BaseModel):
    account_phone: str
    state: str = "pending"
    message: str = ""


class StoriesStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    action_type: Optional[str] = None
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped_daily_cap: int = 0
    finished: bool = False
    error: Optional[str] = None
    ban_count: int = 0
    spamblock_count: int = 0
    floodwait_count: int = 0
    unproxied_senders: List[str] = Field(default_factory=list)
    export_path: Optional[str] = None
    results: List[StoriesResultOut] = Field(default_factory=list)


class LicenseActivateRequest(BaseModel):
    license_key: str = Field(min_length=1, max_length=64)
    hwid: str = Field(min_length=1, max_length=256)


class LicenseStatusOut(BaseModel):
    valid: bool
    tier: Optional[str] = None
    expires_at: Optional[datetime] = None
    reason: str = ""
