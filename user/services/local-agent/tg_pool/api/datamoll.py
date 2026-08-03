from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx


DATAMOLL_MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
DATAMOLL_MAX_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024
DATAMOLL_MAX_ARCHIVE_ENTRIES = 100_000


class DatamollDeliveryError(RuntimeError):
    """Raised when paid Datamoll delivery data cannot be imported locally."""


@dataclass(frozen=True)
class DatamollImportResult:
    downloaded_files: int = 0
    imported_sessions: int = 0
    imported_tdata: int = 0
    skipped_existing: int = 0


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
