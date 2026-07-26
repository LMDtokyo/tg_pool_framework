from __future__ import annotations

import asyncio
import json
import os
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import quote, urlparse

import httpx


DATAMOLL_API_URL = "https://datamollcore.com/api/v1/provider"
DATAMOLL_PROVIDER_NAME = "Datamoll"
DATAMOLL_USER_AGENT = "tg-pool-framework/1.0"
DATAMOLL_MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
DATAMOLL_MAX_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024
DATAMOLL_MAX_ARCHIVE_ENTRIES = 100_000


class DatamollApiError(RuntimeError):
    """Raised when Datamoll cannot complete a provider API operation."""


class DatamollDeliveryError(RuntimeError):
    """Raised when paid Datamoll delivery data cannot be imported locally."""


@dataclass(frozen=True)
class DatamollImportResult:
    downloaded_files: int = 0
    imported_sessions: int = 0
    imported_tdata: int = 0
    skipped_existing: int = 0


def _headers(api_key: str, api_secret: str) -> dict[str, str]:
    key = api_key.strip()
    secret = api_secret.strip()
    if not key or not secret:
        raise ValueError("Datamoll API key and API secret are required")
    return {
        "X-Provider-Key": f"{key}:{secret}",
        "User-Agent": DATAMOLL_USER_AGENT,
        "Accept": "application/json",
    }


def _error_message(response: httpx.Response, operation: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "").strip()
            if message:
                return message
    return f"Datamoll {operation} failed with HTTP {response.status_code}"


async def _send(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    api_key: str,
    api_secret: str,
    operation: str,
    params: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
    extra_headers: Optional[dict[str, str]] = None,
    propagate_timeout: bool = False,
) -> httpx.Response:
    headers = _headers(api_key, api_secret)
    if extra_headers:
        headers.update(extra_headers)
    try:
        return await client.request(
            method,
            f"{DATAMOLL_API_URL}{path}",
            headers=headers,
            params=params,
            json=json_body,
        )
    except httpx.TimeoutException as exc:
        if propagate_timeout:
            raise
        raise DatamollApiError(
            f"Datamoll timed out during {operation}"
        ) from exc
    except httpx.HTTPError as exc:
        raise DatamollApiError(f"Unable to reach Datamoll for {operation}") from exc


def _json_object(response: httpx.Response, operation: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise DatamollApiError(
            f"Datamoll returned invalid JSON for {operation}"
        ) from exc
    if not isinstance(payload, dict):
        raise DatamollApiError(
            f"Datamoll returned an unexpected {operation} response"
        )
    return payload


async def fetch_balance(
    api_key: str,
    api_secret: str,
    *,
    client: Optional[httpx.AsyncClient] = None,
) -> dict[str, Any]:
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=20.0)
    try:
        response = await _send(
            client,
            "GET",
            "/balance",
            api_key=api_key,
            api_secret=api_secret,
            operation="balance request",
        )
        if response.status_code != 200:
            raise DatamollApiError(_error_message(response, "balance request"))
        payload = _json_object(response, "balance")
        return {
            "balance": str(payload.get("balance", "0")),
            "credit_limit": str(payload.get("credit_limit", "0")),
            "available_balance": str(payload.get("available_balance", "0")),
            "currency": str(payload.get("currency", "USD")),
        }
    finally:
        if owns_client:
            await client.aclose()


def _is_telegram_product(product: dict[str, Any]) -> bool:
    searchable = " ".join(
        str(product.get(field) or "")
        for field in ("name", "description", "category_name")
    ).lower()
    return "telegram" in searchable


async def fetch_telegram_catalog(
    api_key: str,
    api_secret: str,
    *,
    language: str = "en",
    client: Optional[httpx.AsyncClient] = None,
) -> list[dict[str, Any]]:
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=25.0)
    products: list[dict[str, Any]] = []
    after_id: Optional[int] = None
    try:
        while True:
            params: dict[str, Any] = {
                "limit": 500,
                "only_in_stock": "true",
                "language": language,
            }
            if after_id is not None:
                params["after_id"] = after_id
            response = await _send(
                client,
                "GET",
                "/catalog",
                api_key=api_key,
                api_secret=api_secret,
                operation="catalog request",
                params=params,
            )
            if response.status_code != 200:
                raise DatamollApiError(_error_message(response, "catalog request"))
            payload = _json_object(response, "catalog")
            items = payload.get("items")
            if not isinstance(items, list):
                raise DatamollApiError(
                    "Datamoll returned an unexpected catalog response"
                )
            products.extend(
                item
                for item in items
                if isinstance(item, dict) and _is_telegram_product(item)
            )
            if not payload.get("has_more"):
                break
            next_after_id = payload.get("next_after_id")
            if not isinstance(next_after_id, int) or next_after_id <= 0:
                raise DatamollApiError("Datamoll catalog pagination is invalid")
            after_id = next_after_id
        return products
    finally:
        if owns_client:
            await client.aclose()


async def _recover_order(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    api_secret: str,
    external_order_id: str,
    attempts: int,
    delay_sec: float,
    sleep_func: Callable[[float], Awaitable[None]],
) -> dict[str, Any]:
    encoded_id = quote(external_order_id, safe="")
    last_message = "Datamoll is still processing the order"
    for attempt in range(attempts):
        if attempt:
            await sleep_func(delay_sec)
        try:
            response = await _send(
                client,
                "GET",
                f"/orders/by-external-id/{encoded_id}",
                api_key=api_key,
                api_secret=api_secret,
                operation="order recovery",
            )
        except DatamollApiError as exc:
            last_message = str(exc)
            if attempt + 1 < attempts:
                continue
            raise
        if response.status_code == 200:
            return _json_object(response, "order")
        if response.status_code in (202, 404):
            last_message = _error_message(response, "order recovery")
            continue
        raise DatamollApiError(_error_message(response, "order recovery"))
    raise DatamollApiError(last_message)


async def create_order_with_recovery(
    api_key: str,
    api_secret: str,
    *,
    product_id: int,
    quantity: int,
    external_order_id: str,
    client: Optional[httpx.AsyncClient] = None,
    recovery_attempts: int = 12,
    recovery_delay_sec: float = 2.0,
    sleep_func: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict[str, Any]:
    if product_id < 1:
        raise ValueError("A valid Datamoll product is required")
    if quantity < 1:
        raise ValueError("Datamoll order quantity must be at least 1")
    stable_order_id = external_order_id.strip()
    if not stable_order_id:
        raise ValueError("Datamoll external order ID is required")

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)
    try:
        try:
            response = await _send(
                client,
                "POST",
                "/orders",
                api_key=api_key,
                api_secret=api_secret,
                operation="order creation",
                json_body={
                    "product_id": product_id,
                    "quantity": quantity,
                    "external_order_id": stable_order_id,
                },
                extra_headers={"Idempotency-Key": stable_order_id},
                propagate_timeout=True,
            )
        except httpx.TimeoutException:
            return await _recover_order(
                client,
                api_key=api_key,
                api_secret=api_secret,
                external_order_id=stable_order_id,
                attempts=recovery_attempts,
                delay_sec=recovery_delay_sec,
                sleep_func=sleep_func,
            )

        if response.status_code in (200, 201):
            return _json_object(response, "order")
        if response.status_code == 202:
            retry_after = response.headers.get("Retry-After")
            try:
                delay = min(10.0, max(0.0, float(retry_after or recovery_delay_sec)))
            except ValueError:
                delay = recovery_delay_sec
            if delay:
                await sleep_func(delay)
            return await _recover_order(
                client,
                api_key=api_key,
                api_secret=api_secret,
                external_order_id=stable_order_id,
                attempts=recovery_attempts,
                delay_sec=delay,
                sleep_func=sleep_func,
            )
        raise DatamollApiError(_error_message(response, "order creation"))
    finally:
        if owns_client:
            await client.aclose()


def save_order_receipt(order: dict[str, Any], receipts_dir: str) -> str:
    order_id = order.get("order_id")
    external_order_id = str(order.get("external_order_id") or "order")
    safe_external_id = "".join(
        char if char.isalnum() or char in ("-", "_") else "_"
        for char in external_order_id
    )[:120]
    directory = Path(receipts_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{safe_external_id}-{order_id}.json"
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(order, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_path, path)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return str(path)


def _safe_extract_zip(archive_path: Path, destination: Path) -> None:
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise DatamollDeliveryError(
            "Datamoll delivered an unsupported or invalid account archive"
        ) from exc

    with archive:
        entries = archive.infolist()
        if len(entries) > DATAMOLL_MAX_ARCHIVE_ENTRIES:
            raise DatamollDeliveryError("Datamoll account archive contains too many files")

        extracted_bytes = 0
        destination_root = destination.resolve()
        for entry in entries:
            entry_path = Path(entry.filename.replace("\\", "/"))
            if (
                entry_path.is_absolute()
                or entry_path.drive
                or ".." in entry_path.parts
                or any(":" in part for part in entry_path.parts)
                or not entry_path.parts
            ):
                raise DatamollDeliveryError(
                    "Datamoll account archive contains an unsafe file path"
                )

            unix_mode = entry.external_attr >> 16
            if stat.S_ISLNK(unix_mode):
                raise DatamollDeliveryError(
                    "Datamoll account archive contains an unsupported symbolic link"
                )

            extracted_bytes += entry.file_size
            if extracted_bytes > DATAMOLL_MAX_EXTRACTED_BYTES:
                raise DatamollDeliveryError("Datamoll account archive is too large")

            target = (destination / entry_path).resolve()
            if target != destination_root and destination_root not in target.parents:
                raise DatamollDeliveryError(
                    "Datamoll account archive contains an unsafe file path"
                )

            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _copy_new_file(source: Path, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as output, source.open("rb") as input_file:
            shutil.copyfileobj(input_file, output)
    except FileExistsError:
        return False
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    try:
        shutil.copystat(source, destination)
    except OSError:
        pass
    return True


def _copy_new_directory(source: Path, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(source, destination)
    except FileExistsError:
        return False
    return True


def _import_extracted_accounts(
    extracted_dir: Path,
    *,
    accounts_dir: Path,
    tdata_dir: Path,
) -> DatamollImportResult:
    imported_sessions = 0
    imported_tdata = 0
    skipped_existing = 0

    for session_file in sorted(extracted_dir.rglob("*.session")):
        json_file = session_file.with_suffix(".json")
        if not json_file.is_file():
            continue

        destination_session = accounts_dir / session_file.name
        destination_json = accounts_dir / json_file.name
        if destination_session.exists() or destination_json.exists():
            skipped_existing += 1
            continue

        if not _copy_new_file(session_file, destination_session):
            skipped_existing += 1
            continue
        try:
            if not _copy_new_file(json_file, destination_json):
                destination_session.unlink(missing_ok=True)
                skipped_existing += 1
                continue
        except Exception:
            destination_session.unlink(missing_ok=True)
            raise
        imported_sessions += 1

    tdata_roots = sorted(
        path
        for path in extracted_dir.rglob("*")
        if path.is_dir() and path.name.casefold() == "tdata"
    )
    for tdata_root in tdata_roots:
        account_package = tdata_root.parent
        destination = tdata_dir / account_package.name
        if _copy_new_directory(account_package, destination):
            imported_tdata += 1
        else:
            skipped_existing += 1

    if imported_sessions == 0 and imported_tdata == 0 and skipped_existing == 0:
        raise DatamollDeliveryError(
            "The delivered archive does not contain a .session + .json pair or tdata account"
        )

    return DatamollImportResult(
        imported_sessions=imported_sessions,
        imported_tdata=imported_tdata,
        skipped_existing=skipped_existing,
    )


async def download_and_import_deliveries(
    items: list[Any],
    *,
    accounts_dir: str,
    tdata_dir: str,
    client: Optional[httpx.AsyncClient] = None,
) -> DatamollImportResult:
    urls = [str(item).strip() for item in items if str(item).strip()]
    if not urls:
        raise DatamollDeliveryError("Datamoll returned no account download links")

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=20.0),
            follow_redirects=True,
        )

    total = DatamollImportResult()
    try:
        with tempfile.TemporaryDirectory(prefix="datamoll-delivery-") as temp_name:
            temp_root = Path(temp_name)
            for index, url in enumerate(urls, start=1):
                parsed = urlparse(url)
                if parsed.scheme.casefold() != "https" or not parsed.hostname:
                    raise DatamollDeliveryError(
                        "Datamoll returned an invalid account download link"
                    )

                archive_path = temp_root / f"delivery-{index}.archive"
                extract_path = temp_root / f"delivery-{index}"
                try:
                    async with client.stream("GET", url) as response:
                        response.raise_for_status()
                        if response.url.scheme.casefold() != "https":
                            raise DatamollDeliveryError(
                                "Datamoll redirected an account download to an insecure link"
                            )
                        downloaded_bytes = 0
                        with archive_path.open("wb") as output:
                            async for chunk in response.aiter_bytes():
                                downloaded_bytes += len(chunk)
                                if downloaded_bytes > DATAMOLL_MAX_DOWNLOAD_BYTES:
                                    raise DatamollDeliveryError(
                                        "Datamoll account download is too large"
                                    )
                                output.write(chunk)
                except DatamollDeliveryError:
                    raise
                except (httpx.HTTPError, OSError) as exc:
                    raise DatamollDeliveryError(
                        f"Unable to download Datamoll account package {index}"
                    ) from exc

                extract_path.mkdir(parents=True)
                try:
                    _safe_extract_zip(archive_path, extract_path)
                except DatamollDeliveryError:
                    raise
                except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                    raise DatamollDeliveryError(
                        f"Unable to extract Datamoll account package {index}"
                    ) from exc
                try:
                    imported = _import_extracted_accounts(
                        extract_path,
                        accounts_dir=Path(accounts_dir),
                        tdata_dir=Path(tdata_dir),
                    )
                except DatamollDeliveryError:
                    raise
                except (OSError, shutil.Error) as exc:
                    raise DatamollDeliveryError(
                        f"Unable to save Datamoll account package {index}"
                    ) from exc
                total = DatamollImportResult(
                    downloaded_files=total.downloaded_files + 1,
                    imported_sessions=(
                        total.imported_sessions + imported.imported_sessions
                    ),
                    imported_tdata=total.imported_tdata + imported.imported_tdata,
                    skipped_existing=(
                        total.skipped_existing + imported.skipped_existing
                    ),
                )
        return total
    finally:
        if owns_client:
            await client.aclose()
