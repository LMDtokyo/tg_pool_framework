"""
license_server/app.py — The license authority.

A small, standalone FastAPI service, independent from the main
tg_pool_framework backend (src/api/app.py). It is the single source of
truth for which license keys exist, which device each is bound to, and when
each expires. Every customer's local backend calls POST /license/activate
periodically to re-confirm it's still allowed to run.

Run: uvicorn license_server.app:app --host 0.0.0.0 --port 8100
Env: LICENSE_DATABASE_URL, LICENSE_ADMIN_API_KEY (see .env.example)
"""

from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query

from license_server.db.engine import build_session_factory_from_env
from license_server.db.repository import ActivationOutcome, LicenseKeyRepository, ensure_license_tables
from license_server.profile_names import FIRST_NAMES, LAST_NAMES
from license_server.schemas import (
    ActivateRequest,
    ActivateResponse,
    GenerateKeysRequest,
    GenerateKeysResponse,
    IssuedKeyOut,
    LicenseKeySummaryOut,
    ListKeysResponse,
    ProfileNamesOut,
    VersionOut,
)
from license_server.hashing import hash_secret
from license_server.signing import load_private_key_from_env, sign_activation

logger = logging.getLogger("license_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-8s] %(name)s %(message)s")

    if not os.getenv("LICENSE_ADMIN_API_KEY"):
        raise RuntimeError("LICENSE_ADMIN_API_KEY must be set -- refusing to start without admin auth")

    app.state.signing_key = load_private_key_from_env()

    session_factory = build_session_factory_from_env()
    await ensure_license_tables(session_factory)

    app.state.repository = LicenseKeyRepository(session_factory)
    logger.info("License server ready.")
    try:
        yield
    finally:
        engine = session_factory.kw["bind"]
        await engine.dispose()


app = FastAPI(title="tg_pool_framework license authority", lifespan=lifespan)


def require_admin(x_admin_key: str = Header(default="")) -> None:
    expected = os.getenv("LICENSE_ADMIN_API_KEY", "")
    if not expected or not secrets.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing admin key")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/version", response_model=VersionOut)
async def version() -> VersionOut:
    """Lets the console activator show the customer 'installed vs latest' --
    bump LATEST_LAUNCHER_VERSION whenever a new build ships, no redeploy of
    the launcher itself required for the check to reflect it."""
    return VersionOut(
        latest_version=os.getenv("LATEST_LAUNCHER_VERSION", "0.0.0"),
        notes=os.getenv("LATEST_LAUNCHER_NOTES", ""),
    )


@app.get("/profile-names", response_model=ProfileNamesOut)
async def profile_names() -> ProfileNamesOut:
    """
    Public, no license/admin auth needed -- same trust level as /version.
    Lets every deployed backend draw registration display names from one
    shared, centrally-updatable pool instead of a name list frozen into
    that install's build (see license_server/profile_names.py).
    """
    return ProfileNamesOut(first_names=list(FIRST_NAMES), last_names=list(LAST_NAMES))


@app.post("/admin/keys", response_model=GenerateKeysResponse, dependencies=[Depends(require_admin)])
async def generate_keys(request: GenerateKeysRequest) -> GenerateKeysResponse:
    repository: LicenseKeyRepository = app.state.repository
    issued = await repository.create_keys(request.tier, request.count, request.note)
    return GenerateKeysResponse(
        keys=[IssuedKeyOut(id=item.id, key_code=item.key_code, tier=item.tier) for item in issued]
    )


@app.get("/admin/keys", response_model=ListKeysResponse, dependencies=[Depends(require_admin)])
async def list_keys(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)) -> ListKeysResponse:
    repository: LicenseKeyRepository = app.state.repository
    items, total = await repository.list_keys(limit=limit, offset=offset, now=datetime.now(timezone.utc))
    return ListKeysResponse(items=[LicenseKeySummaryOut(**item.__dict__) for item in items], total=total)


@app.post("/admin/keys/{key_id}/revoke", dependencies=[Depends(require_admin)])
async def revoke_key(key_id: int) -> dict:
    repository: LicenseKeyRepository = app.state.repository
    found = await repository.revoke(key_id)
    if not found:
        raise HTTPException(status_code=404, detail="License key not found")
    return {"status": "revoked"}


@app.post("/admin/keys/{key_id}/reset-device", dependencies=[Depends(require_admin)])
async def reset_device(key_id: int) -> dict:
    repository: LicenseKeyRepository = app.state.repository
    found = await repository.reset_device(key_id)
    if not found:
        raise HTTPException(status_code=404, detail="License key not found")
    return {"status": "device_reset"}


@app.post("/license/activate", response_model=ActivateResponse)
async def activate(request: ActivateRequest) -> ActivateResponse:
    repository: LicenseKeyRepository = app.state.repository
    result = await repository.activate(
        request.license_key, hash_secret(request.hwid), now=datetime.now(timezone.utc)
    )

    if result.outcome is ActivationOutcome.NOT_FOUND:
        raise HTTPException(
            status_code=404, detail={"reason": "not_found", "message": "Unknown license key"}
        )
    if result.outcome is ActivationOutcome.REVOKED:
        raise HTTPException(
            status_code=403, detail={"reason": "revoked", "message": "This license key has been revoked"}
        )
    if result.outcome is ActivationOutcome.EXPIRED:
        raise HTTPException(
            status_code=403, detail={"reason": "expired", "message": "This license key has expired"}
        )
    if result.outcome is ActivationOutcome.DEVICE_MISMATCH:
        raise HTTPException(
            status_code=409,
            detail={
                "reason": "device_mismatch",
                "message": "This license key is already active on another device",
            },
        )

    assert result.tier is not None and result.activated_at is not None and result.expires_at is not None
    signature = sign_activation(
        app.state.signing_key,
        license_key=request.license_key,
        hwid=request.hwid,
        tier=result.tier,
        expires_at=result.expires_at.isoformat(),
    )
    return ActivateResponse(
        tier=result.tier, activated_at=result.activated_at, expires_at=result.expires_at, signature=signature
    )
