from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from tg_pool.api.datamoll import (
    DatamollDeliveryError,
    download_and_import_deliveries,
    save_order_receipt,
)


pytestmark = pytest.mark.unit


def test_order_receipt_keeps_delivered_items_server_side(tmp_path):
    order = {
        "order_id": 4012,
        "external_order_id": "tgpool-order-1",
        "items": ["sensitive-account-data"],
    }

    path = save_order_receipt(order, str(tmp_path))

    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    assert saved["items"] == ["sensitive-account-data"]
    assert "tgpool-order-1-4012.json" in path


def _account_archive(*, unsafe_name: str | None = None) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        if unsafe_name is not None:
            archive.writestr(unsafe_name, b"unsafe")
        else:
            root = "CA_+1_1pcs_2026-07-26_03-04"
            archive.writestr(
                f"{root}/sessions_2040/12499460883.session",
                b"sqlite-session",
            )
            archive.writestr(
                f"{root}/sessions_2040/12499460883.json",
                json.dumps(
                    {
                        "app_id": 2040,
                        "app_hash": "hash",
                        "phone": "+12499460883",
                    }
                ),
            )
            archive.writestr(
                f"{root}/tdatas/12499460883/2FA.txt",
                "secret",
            )
            archive.writestr(
                f"{root}/tdatas/12499460883/tdata/key_datas",
                b"key-data",
            )
            archive.writestr(
                f"{root}/tdatas/12499460883/tdata/D877F783D5D3EF8C/maps",
                b"maps",
            )
    return output.getvalue()


@pytest.mark.asyncio
async def test_delivery_archive_is_imported_into_existing_account_storage(tmp_path):
    archive_bytes = _account_archive()
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, content=archive_bytes)
    )
    accounts_dir = tmp_path / "Accounts"
    tdata_dir = tmp_path / "Tdata"

    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=True,
    ) as client:
        result = await download_and_import_deliveries(
            ["https://dl-cloude.org/files/account"],
            accounts_dir=str(accounts_dir),
            tdata_dir=str(tdata_dir),
            client=client,
        )
        repeated = await download_and_import_deliveries(
            ["https://dl-cloude.org/files/account"],
            accounts_dir=str(accounts_dir),
            tdata_dir=str(tdata_dir),
            client=client,
        )

    assert result.downloaded_files == 1
    assert result.imported_sessions == 1
    assert result.imported_tdata == 1
    assert (accounts_dir / "12499460883.session").read_bytes() == b"sqlite-session"
    assert (accounts_dir / "12499460883.json").is_file()
    assert (tdata_dir / "12499460883" / "2FA.txt").read_text() == "secret"
    assert (tdata_dir / "12499460883" / "tdata" / "key_datas").is_file()
    assert repeated.imported_sessions == 0
    assert repeated.imported_tdata == 0
    assert repeated.skipped_existing == 2


@pytest.mark.asyncio
async def test_delivery_archive_rejects_path_traversal(tmp_path):
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, content=_account_archive(unsafe_name="../escape"))
    )
    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=True,
    ) as client:
        with pytest.raises(DatamollDeliveryError, match="unsafe file path"):
            await download_and_import_deliveries(
                ["https://dl-cloude.org/files/account"],
                accounts_dir=str(tmp_path / "Accounts"),
                tdata_dir=str(tmp_path / "Tdata"),
                client=client,
            )

    assert not (tmp_path / "escape").exists()
