from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class BalanceOut(BaseModel):
    address: str
    balance: str
    asset: str
    trx_balance: str = "0"


class ConfigOut(BaseModel):
    treasury_address: str
    contract_address: str
    network: str
    asset: str


class TreasuryUpdate(BaseModel):
    treasury_address: str = Field(min_length=34, max_length=64)


class WalletCreateRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=200)


class WalletOut(BaseModel):
    address: str
    network: str
    asset: str


class SweepRequest(BaseModel):
    sweep_id: str = Field(min_length=1, max_length=128)
    source_address: str = Field(min_length=34, max_length=64)
    amount: str


class SweepOut(BaseModel):
    sweep_id: str
    transaction_hash: str
    amount: str
    balance_before: str
    destination_address: str
    network_fee: Optional[str] = None


class TransactionOut(BaseModel):
    status: str
    balance_after: Optional[str] = None
    network_fee: Optional[str] = None
    error_message: str = ""
