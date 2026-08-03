from __future__ import annotations

import asyncio
import os
import secrets
import sqlite3
from contextlib import asynccontextmanager
from decimal import InvalidOperation
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query

from payment_signer.chain import ChainError, TronSweepService
from payment_signer.keyvault import KeyVault, KeyVaultError
from payment_signer.money import token_amount
from payment_signer.registry import SweepRegistry, SweepRegistryError
from payment_signer.schemas import (
    BalanceOut,
    ConfigOut,
    SweepOut,
    SweepRequest,
    TransactionOut,
    TreasuryUpdate,
    WalletCreateRequest,
    WalletOut,
)

_PACKAGE_DIR = Path(__file__).resolve().parent


def _resolve_path(value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = _PACKAGE_DIR / path
    return str(path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    env_file = os.getenv("SIGNER_ENV_FILE", "").strip()
    load_dotenv(dotenv_path=env_file or (_PACKAGE_DIR / ".env"))
    api_key = os.getenv("PAYMENT_SIGNER_API_KEY", "").strip()
    vault_path = os.getenv("SIGNER_VAULT_FILE", "").strip()
    vault_key = os.getenv("SIGNER_VAULT_KEY", "").strip()
    state_database = os.getenv("SIGNER_STATE_DATABASE", "").strip()
    if not api_key or not vault_path or not vault_key or not state_database:
        raise RuntimeError(
            "PAYMENT_SIGNER_API_KEY, SIGNER_VAULT_FILE, SIGNER_VAULT_KEY, "
            "and SIGNER_STATE_DATABASE must be set"
        )
    vault = KeyVault.load(_resolve_path(vault_path), vault_key)
    app.state.vault = vault
    app.state.registry = await asyncio.to_thread(
        SweepRegistry, _resolve_path(state_database)
    )
    persisted_treasury = await asyncio.to_thread(
        app.state.registry.setting, "treasury_address"
    )
    app.state.chain = await asyncio.to_thread(
        TronSweepService, vault, persisted_treasury
    )
    yield


app = FastAPI(title="tg_pool_framework isolated payment signer", lifespan=lifespan)


def require_signer_key(x_signer_key: str = Header(default="")) -> None:
    expected = os.getenv("PAYMENT_SIGNER_API_KEY", "")
    if not expected or not secrets.compare_digest(x_signer_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing signer key")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/v1/config",
    response_model=ConfigOut,
    dependencies=[Depends(require_signer_key)],
)
async def config() -> ConfigOut:
    chain: TronSweepService = app.state.chain
    return ConfigOut(
        treasury_address=chain.treasury_address,
        contract_address=chain.contract_address,
        network=chain.network,
        asset=os.getenv("SIGNER_ASSET", "USDT").upper(),
    )


@app.put(
    "/v1/config/treasury",
    response_model=ConfigOut,
    dependencies=[Depends(require_signer_key)],
)
async def update_treasury(body: TreasuryUpdate) -> ConfigOut:
    chain: TronSweepService = app.state.chain
    registry: SweepRegistry = app.state.registry
    previous = chain.treasury_address
    try:
        address = await asyncio.to_thread(
            chain.set_treasury_address, body.treasury_address
        )
        await asyncio.to_thread(registry.set_setting, "treasury_address", address)
    except (ChainError, SweepRegistryError, sqlite3.Error) as exc:
        chain.set_treasury_address(previous)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await config()


@app.post(
    "/v1/wallets",
    response_model=WalletOut,
    dependencies=[Depends(require_signer_key)],
)
async def create_wallet(body: WalletCreateRequest) -> WalletOut:
    if os.getenv("SIGNER_AUTO_CREATE_WALLETS", "1").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise HTTPException(
            status_code=403, detail="Automatic wallet creation is disabled"
        )
    vault: KeyVault = app.state.vault
    chain: TronSweepService = app.state.chain
    try:
        address = await asyncio.to_thread(vault.create_wallet, body.request_id)
    except KeyVaultError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return WalletOut(
        address=address,
        network=chain.network,
        asset=os.getenv("SIGNER_ASSET", "USDT").upper(),
    )


@app.get(
    "/v1/wallets/{address}/balance",
    response_model=BalanceOut,
    dependencies=[Depends(require_signer_key)],
)
async def balance(address: str) -> BalanceOut:
    chain: TronSweepService = app.state.chain
    try:
        value, trx_value = await asyncio.gather(
            asyncio.to_thread(chain.balance, address),
            asyncio.to_thread(chain.trx_balance, address),
        )
    except ChainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BalanceOut(
        address=address,
        balance=format(value, "f"),
        asset=os.getenv("SIGNER_ASSET", "USDT").upper(),
        trx_balance=format(trx_value, "f"),
    )


@app.post(
    "/v1/sweeps",
    response_model=SweepOut,
    dependencies=[Depends(require_signer_key)],
)
async def sweep(body: SweepRequest) -> SweepOut:
    chain: TronSweepService = app.state.chain
    registry: SweepRegistry = app.state.registry
    try:
        amount = token_amount(body.amount)
        result = await asyncio.to_thread(
            registry.execute_once,
            sweep_id=body.sweep_id,
            source_address=body.source_address,
            amount=amount,
            operation=lambda: chain.sweep(body.source_address, amount),
        )
    except (InvalidOperation, ValueError, ChainError, SweepRegistryError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Signer state database error: {exc}",
        ) from exc
    return SweepOut(
        sweep_id=body.sweep_id,
        transaction_hash=result.transaction_hash,
        amount=format(result.amount, "f"),
        balance_before=format(result.balance_before, "f"),
        destination_address=result.destination_address or chain.treasury_address,
    )


@app.get(
    "/v1/transactions/{transaction_hash}",
    response_model=TransactionOut,
    dependencies=[Depends(require_signer_key)],
)
async def transaction(
    transaction_hash: str,
    source_address: str = Query(min_length=34, max_length=64),
) -> TransactionOut:
    chain: TronSweepService = app.state.chain
    try:
        result = await asyncio.to_thread(
            chain.transaction_status,
            transaction_hash,
            source_address,
        )
    except ChainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TransactionOut(
        status=result.status,
        balance_after=(
            format(result.balance_after, "f")
            if result.balance_after is not None
            else None
        ),
        network_fee=(
            format(result.network_fee, "f")
            if result.network_fee is not None
            else None
        ),
        error_message=result.error_message,
    )
