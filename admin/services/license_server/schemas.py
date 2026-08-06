from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from license_server.tiers import Tier


class GenerateKeysRequest(BaseModel):
    tier: Tier
    count: int = Field(ge=1, le=200)
    note: str = Field(default="", max_length=200)


class IssuedKeyOut(BaseModel):
    id: int
    key_code: str
    tier: Tier


class GenerateKeysResponse(BaseModel):
    keys: List[IssuedKeyOut]


class LicenseKeySummaryOut(BaseModel):
    id: int
    key_last4: str
    tier: str
    note: str
    status: str
    hwid_bound: bool
    activated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    created_at: datetime


class ListKeysResponse(BaseModel):
    items: List[LicenseKeySummaryOut]
    total: int


class ActivateRequest(BaseModel):
    license_key: str = Field(min_length=1, max_length=64)
    hwid: str = Field(min_length=1, max_length=256)


class ActivateResponse(BaseModel):
    tier: str
    activated_at: datetime
    expires_at: datetime
    signature: str


class VersionOut(BaseModel):
    latest_version: str
    notes: str = ""
    download_url: str = ""


class ProfileNamesOut(BaseModel):
    first_names: List[str]
    last_names: List[str]
