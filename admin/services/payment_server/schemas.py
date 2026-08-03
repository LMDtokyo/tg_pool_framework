from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class IssueUserRequest(BaseModel):
    telegram_user_id: Optional[str] = Field(default=None, max_length=64)
    telegram_username: Optional[str] = Field(default=None, max_length=64)
    display_name: str = Field(default="", max_length=200)
    deposit_address: Optional[str] = Field(default=None, min_length=10, max_length=128)


class IssuedUserOut(BaseModel):
    user_id: int
    api_key: str
    network: str
    asset: str
    deposit_address: str


class MeOut(BaseModel):
    user_id: int
    telegram_user_id: Optional[str] = None
    telegram_username: Optional[str] = None
    display_name: str
    deposit_address: str
    network: str
    asset: str


class BalanceOut(BaseModel):
    balance: str
    credit_limit: str = "0"
    available_balance: str
    currency: str


class TransactionOut(BaseModel):
    amount: str
    currency: str
    entry_type: str
    description: str
    created_at: datetime


class TransactionsOut(BaseModel):
    items: list[TransactionOut] = Field(default_factory=list)


class ProductOut(BaseModel):
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


class CatalogOut(BaseModel):
    items: list[ProductOut] = Field(default_factory=list)


class OrderRequest(BaseModel):
    product_id: int = Field(ge=1)
    quantity: int = Field(ge=1)
    external_order_id: str = Field(min_length=1, max_length=255)


class OrderOut(BaseModel):
    order_id: int
    external_order_id: str
    status: str
    payment_status: str
    product_id: int
    quantity: int
    unit_price: str
    total_amount: str
    currency: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    reused_existing: bool = False


class DepositEventRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    network: str = Field(default="tron", min_length=1, max_length=32)
    asset: str = Field(default="USDT", min_length=1, max_length=16)
    address: str = Field(min_length=10, max_length=128)
    transaction_hash: str = Field(min_length=1, max_length=128)
    event_index: int = Field(default=0, ge=0)
    amount: str
    confirmations: int = Field(ge=0)


class DepositEventOut(BaseModel):
    status: str
    credited: bool
    duplicate: bool = False
    newly_credited: bool = False


class RegeneratedKeyOut(BaseModel):
    api_key: str


class AdjustmentRequest(BaseModel):
    user_id: int = Field(ge=1)
    amount: str
    description: str = Field(min_length=1, max_length=500)


class AdminWalletOut(BaseModel):
    user_id: int
    telegram_user_id: Optional[str] = None
    display_name: str
    address: str
    network: str
    asset: str
    on_chain_balance: str
    database_balance: str
    currency: str


class AdminUserSummaryOut(BaseModel):
    user_id: int
    telegram_user_id: Optional[str] = None
    telegram_username: Optional[str] = None
    display_name: str
    disabled: bool
    address: str
    network: str
    asset: str
    on_chain_balance: Optional[str] = None
    trx_balance: Optional[str] = None
    chain_error: str = ""
    database_balance: str
    currency: str
    total_accounts_purchased: int
    total_amount_paid: str


class AdminUsersOut(BaseModel):
    items: list[AdminUserSummaryOut] = Field(default_factory=list)


class SalesTotalOut(BaseModel):
    gross_sales: str
    completed_orders: int
    accounts_sold: int


class DailySalesOut(SalesTotalOut):
    date: str


class SalesStatisticsOut(BaseModel):
    days: int
    currency: str
    today: SalesTotalOut
    period: SalesTotalOut
    all_time: SalesTotalOut
    daily: list[DailySalesOut] = Field(default_factory=list)


class DepositTotalOut(BaseModel):
    total_deposited: str
    deposit_count: int


class DailyDepositOut(DepositTotalOut):
    date: str


class DepositStatisticsOut(BaseModel):
    days: int
    asset: str
    today: DepositTotalOut
    period: DepositTotalOut
    all_time: DepositTotalOut
    daily: list[DailyDepositOut] = Field(default_factory=list)


class WithdrawalRequest(BaseModel):
    amount: Optional[str] = None


class WithdrawalOut(BaseModel):
    id: int
    user_id: int
    source_address: str
    destination_address: str
    requested_amount: str
    transferred_amount: Optional[str] = None
    asset: str
    network: str
    status: str
    transaction_hash: Optional[str] = None
    chain_balance_before: Optional[str] = None
    chain_balance_after: Optional[str] = None
    network_fee: Optional[str] = None
    requested_by: str
    error_message: str = ""
    created_at: datetime
    updated_at: datetime


class WithdrawalsOut(BaseModel):
    items: list[WithdrawalOut] = Field(default_factory=list)


class RetailPricingOut(BaseModel):
    markup_percent: str
    markup_fixed: str


class RetailPricingUpdate(BaseModel):
    markup_percent: str
    markup_fixed: str


class TreasuryWalletOut(BaseModel):
    address: str
    network: str
    asset: str
    on_chain_balance: str
    trx_balance: str = "0"


class TreasuryWalletUpdate(BaseModel):
    address: str = Field(min_length=34, max_length=64)
