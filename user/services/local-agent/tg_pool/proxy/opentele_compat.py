"""Compatibility fixes for tdata records added after opentele 1.15.1."""

from __future__ import annotations

import logging
from typing import Callable

from PyQt5.QtCore import QByteArray, QDataStream
from opentele import exception as ote_exc
from opentele.td import account as account_module


logger = logging.getLogger(__name__)

_PATCH_MARKER = "_tgpool_new_map_records"


def _consume_uint64(stream: QDataStream, count: int = 1) -> None:
    for _ in range(count):
        stream.readUInt64()


def _consume_map(stream: QDataStream) -> None:
    """Consume Telegram Desktop's encrypted map without loading cache indexes."""
    single_key_records = {
        0x04,  # locations
        0x07,  # recent stickers (legacy)
        0x08,  # background (legacy)
        0x09,  # user settings
        0x0A,  # recent hashtags and bots
        0x0B,  # stickers (legacy)
        0x0C,  # saved peers (legacy)
        0x0D,  # report spam statuses (legacy)
        0x0E,  # saved GIFs (legacy)
        0x0F,  # saved GIFs
        0x11,  # trusted peers
        0x12,  # favorite stickers
        0x13,  # export settings
        0x18,  # search suggestions
        0x1A,  # round placeholder
        0x1B,  # inline bot downloads
        0x1C,  # media playback positions
        0x1E,  # preferences
    }

    while not stream.atEnd():
        record = stream.readUInt32()

        if record in (0x01, 0x02, 0x1D):
            # Drafts, draft cursors, and bot storages: count + (key, peer) pairs.
            count = stream.readUInt32()
            _consume_uint64(stream, count * 2)
        elif record in (0x03, 0x05, 0x06):
            count = stream.readUInt32()
            for _ in range(count):
                _consume_uint64(stream, 3)
                stream.readInt32()
        elif record in single_key_records:
            _consume_uint64(stream)
        elif record == 0x10:
            _consume_uint64(stream, 4)
        elif record == 0x14:
            _consume_uint64(stream, 2)
        elif record == 0x15:
            stream >> QByteArray()
        elif record in (0x16, 0x17):
            # Mask keys and custom-emoji keys each contain three file keys.
            _consume_uint64(stream, 3)
        elif record == 0x19:
            # Webview storage tokens for bots and other webviews.
            stream >> QByteArray() >> QByteArray()
        else:
            raise ote_exc.TDataReadMapDataFailed(
                f"Unsupported key type in encrypted map: {record}"
            )

        account_module.ExpectStreamStatus(
            stream, "Could not stream data from the Telegram Desktop map"
        )


def _read_new_map_records(self, local_key, legacy_passcode: QByteArray) -> None:
    storage = account_module.td.Storage
    map_data = storage.ReadFile("map", self.basePath)

    legacy_salt = QByteArray()
    legacy_key_encrypted = QByteArray()
    map_encrypted = QByteArray()
    map_data.stream >> legacy_salt >> legacy_key_encrypted >> map_encrypted
    account_module.ExpectStreamStatus(map_data.stream, "Could not stream map data")

    if not local_key:
        if legacy_salt.size() != 32:
            raise ote_exc.TDataReadMapDataFailed(
                f"Bad salt in map file, size: {legacy_salt.size()}"
            )
        passcode_key = storage.CreateLegacyLocalKey(legacy_salt, legacy_passcode)
        key_data = storage.DecryptLocal(legacy_key_encrypted, passcode_key)
        local_key = account_module.td.AuthKey.FromStream(key_data.stream)

    decrypted = storage.DecryptLocal(map_encrypted, local_key)
    _consume_map(decrypted.stream)

    # These are the only values needed after a read when converting to Telethon.
    self._MapData__localKey = local_key
    self._oldMapVersion = map_data.version


def install_opentele_compat() -> None:
    """Install a fallback reader for map records unsupported by opentele 1.15.1."""
    current: Callable = account_module.MapData.read
    if getattr(current, _PATCH_MARKER, False):
        return

    def read_with_new_records(self, local_key, legacy_passcode=QByteArray()):
        try:
            return current(self, local_key, legacy_passcode)
        except ote_exc.TDataReadMapDataFailed as exc:
            if "Unknown key type in encrypted map" not in str(exc):
                raise
            logger.info("Retrying tdata map with support for newer record types")
            return _read_new_map_records(self, local_key, legacy_passcode)

    setattr(read_with_new_records, _PATCH_MARKER, True)
    account_module.MapData.read = read_with_new_records

