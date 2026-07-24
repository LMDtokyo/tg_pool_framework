"""Regression tests for Telegram Desktop map records newer than opentele."""

from PyQt5.QtCore import QByteArray, QDataStream, QIODevice
import pytest

from opentele import exception as ote_exc
from src.proxy.opentele_compat import _consume_map


def _stream_with_records(write_records):
    payload = QByteArray()
    writer = QDataStream(payload, QIODevice.OpenModeFlag.WriteOnly)
    writer.setVersion(QDataStream.Version.Qt_5_1)
    write_records(writer)

    reader = QDataStream(payload)
    reader.setVersion(QDataStream.Version.Qt_5_1)
    return reader


def test_consume_map_accepts_new_telegram_desktop_records():
    def write(stream):
        stream.writeUInt32(0x17)  # custom emoji keys
        for value in (1, 2, 3):
            stream.writeUInt64(value)

        stream.writeUInt32(0x18)  # search suggestions
        stream.writeUInt64(4)

        stream.writeUInt32(0x19)  # webview tokens
        stream << QByteArray(b"bots") << QByteArray(b"other")

        for record in (0x1A, 0x1B, 0x1C, 0x1E):
            stream.writeUInt32(record)
            stream.writeUInt64(record)

        stream.writeUInt32(0x1D)  # bot storage map
        stream.writeUInt32(2)
        for value in (10, 11, 12, 13):
            stream.writeUInt64(value)

    stream = _stream_with_records(write)
    _consume_map(stream)

    assert stream.atEnd()
    assert stream.status() == QDataStream.Status.Ok


def test_consume_map_rejects_unknown_record_without_guessing_its_shape():
    stream = _stream_with_records(lambda output: output.writeUInt32(0x7FFFFFFF))

    with pytest.raises(ote_exc.TDataReadMapDataFailed, match="Unsupported key type"):
        _consume_map(stream)

