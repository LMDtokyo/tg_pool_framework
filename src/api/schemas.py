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


class RecheckResponse(BaseModel):
    checked: int
    alive: int
    banned: int
    unauthorized: int
    spamblock: int
    frozen: int
    flood: int


class RescanResponse(BaseModel):
    new_accounts: int


class CampaignStartRequest(BaseModel):
    target: str = Field(min_length=1)
    # Blank is valid when forward_link/bot_relay_* supplies the whole message.
    message: str = ""
    media_path: Optional[str] = None
    media_paths: Optional[List[str]] = None
    media_kind: str = "auto"
    buttons_raw: Optional[str] = None
    parse_mode: Optional[str] = "markdown"
    silent: bool = False
    link_preview: bool = True
    forward_link: Optional[str] = None
    bot_relay_username: Optional[str] = None
    bot_relay_message_ids: Optional[List[int]] = None
    account_folder: Optional[str] = None
    messages_per_account_min: int = 1
    messages_per_account_max: Optional[int] = None
    exact_total_target: Optional[int] = None
    schedule_at: Optional[datetime] = None
    pin_after_send: bool = False
    worker_batch_size: Optional[int] = None
    worker_batch_delay_sec: float = 0.0
    repeat_every_hours: Optional[float] = None


class CampaignStartResponse(BaseModel):
    campaign_id: str
    started: bool


class CampaignStatusResponse(BaseModel):
    running: bool
    campaign_id: Optional[str] = None
    target: Optional[str] = None
    total: int = 0
    sent: int = 0
    failed: int = 0
    per_account: Dict[str, int] = Field(default_factory=dict)
    finished: bool = False
    error: Optional[str] = None


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


class ParseStartResponse(BaseModel):
    job_id: str
    started: bool


class ParseStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    entities: List[str] = Field(default_factory=list)
    total_collected: int = 0
    sources: List[str] = Field(default_factory=list)
    export_path: Optional[str] = None
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


class ProxyDeleteResponse(BaseModel):
    deleted: int


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
    results: List[InviteByNumberResultOut] = Field(default_factory=list)


class SendByNumbersStartRequest(BaseModel):
    phone_numbers: List[str] = Field(min_length=1)
    message: str = Field(min_length=1)
    sender_phones: List[str] = Field(default_factory=list)
    sms_per_account_min: int = 1
    sms_per_account_max: int = 40
    delay_min_sec: float = 1.0
    delay_max_sec: float = 10.0
    max_flood_wait_sec: float = 500.0
    use_base_data: bool = False
    request_profile: bool = False
    delete_dialog: bool = False
    link_preview: bool = True
    silent: bool = False
    auto_repost: bool = False
    pin_message: bool = False
    video_note: bool = False
    self_destruct_sec: Optional[int] = None
    sending_by_time: bool = False
    streams_control: bool = False
    auto_stop: bool = False


class SendByNumbersStartResponse(BaseModel):
    job_id: str
    started: bool


class SendByNumbersResultOut(BaseModel):
    recipient_phone: str
    sender_phone: str = ""
    state: str = "pending"
    message: str = ""
    first_name: str = ""
    last_name: str = ""
    bio: str = ""


class SendByNumbersStatusResponse(BaseModel):
    running: bool
    job_id: Optional[str] = None
    total: int = 0
    sent: int = 0
    failed: int = 0
    per_account: Dict[str, int] = Field(default_factory=dict)
    finished: bool = False
    error: Optional[str] = None
    results: List[SendByNumbersResultOut] = Field(default_factory=list)
