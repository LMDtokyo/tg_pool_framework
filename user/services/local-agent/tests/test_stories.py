from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from telethon.errors import FloodWaitError, UserDeactivatedBanError
from telethon.tl.functions.stories import ReadStoriesRequest, SendReactionRequest as SendStoryReactionRequest, SendStoryRequest
from telethon.tl.types import InputMediaUploadedDocument, InputMediaUploadedPhoto, InputPrivacyValueAllowContacts

from tg_pool.accounts.proxy_safety import UnprotectedAccountsError
from tg_pool.api.stories import StoriesAlreadyRunningError, StoriesManager
from tg_pool.api.pool_guard import PoolAccessGuard
from tg_pool.config import AccountConfig, ProxyConfig

pytestmark = pytest.mark.unit


def make_account(phone: str, proxy: ProxyConfig | None = None) -> AccountConfig:
    return AccountConfig(api_id=1, api_hash="hash", phone=phone, session_dir="sessions", proxy=proxy)


def make_client() -> MagicMock:
    client = AsyncMock()
    client.connect = AsyncMock()
    client.is_user_authorized = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    client.is_connected = MagicMock(return_value=True)
    client.get_input_entity = AsyncMock(return_value=MagicMock(name="peer"))
    client.upload_file = AsyncMock(return_value=MagicMock(name="file_handle"))
    return client


def test_start_rejects_unknown_action_type() -> None:
    manager = StoriesManager([make_account("+100")], PoolAccessGuard())
    with pytest.raises(ValueError, match="Unknown action_type"):
        manager.start(require_proxy=False, action_type="super_boost")


def test_start_requires_target_for_view_action() -> None:
    manager = StoriesManager([make_account("+100")], PoolAccessGuard())
    with pytest.raises(ValueError, match="target_chat"):
        manager.start(require_proxy=False, action_type="view")


def test_start_requires_reaction_emoji_for_reaction_action() -> None:
    manager = StoriesManager([make_account("+100")], PoolAccessGuard())
    with pytest.raises(ValueError, match="reaction_emoji"):
        manager.start(require_proxy=False, action_type="reaction", target_chat="@chan", target_story_id=1)


def test_start_requires_existing_media_for_post_action(tmp_path: Path) -> None:
    manager = StoriesManager([make_account("+100")], PoolAccessGuard())
    with pytest.raises(ValueError, match="media_path"):
        manager.start(require_proxy=False, action_type="post")
    with pytest.raises(ValueError, match="not found"):
        manager.start(require_proxy=False, action_type="post", media_path=str(tmp_path / "missing.jpg"))


def test_start_rejects_unknown_privacy(tmp_path: Path) -> None:
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake-jpeg")
    manager = StoriesManager([make_account("+100")], PoolAccessGuard())
    with pytest.raises(ValueError, match="privacy"):
        manager.start(require_proxy=False, action_type="post", media_path=str(photo), privacy="everyone-but-my-boss")


async def test_second_start_while_running_raises(monkeypatch) -> None:
    client = make_client()
    monkeypatch.setattr("tg_pool.api.stories.ClientFactory.build", lambda _account: client)
    manager = StoriesManager([make_account("+100")], PoolAccessGuard())

    manager.start(require_proxy=False, action_type="view", target_chat="@chan", target_story_id=1, delay_min_sec=0, delay_max_sec=0)

    with pytest.raises(StoriesAlreadyRunningError):
        manager.start(require_proxy=False, action_type="view", target_chat="@chan", target_story_id=1)

    await manager._run.task


async def test_view_job_sends_read_stories_request(monkeypatch, tmp_path: Path) -> None:
    client = make_client()
    monkeypatch.setattr("tg_pool.api.stories.ClientFactory.build", lambda _account: client)
    pool_guard = PoolAccessGuard()
    manager = StoriesManager([make_account("+100")], pool_guard)

    job_id = manager.start(require_proxy=False,
        action_type="view",
        target_chat="@chan",
        target_story_id=42,
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    status = manager.status()
    assert status["job_id"] == job_id
    assert status["succeeded"] == 1
    assert status["finished"] is True
    assert Path(status["export_path"]).is_file()
    assert pool_guard.current_holder is None

    sent_request = client.await_args.args[0]
    assert isinstance(sent_request, ReadStoriesRequest)
    assert sent_request.max_id == 42


async def test_reaction_job_sends_story_reaction_request(monkeypatch, tmp_path: Path) -> None:
    client = make_client()
    monkeypatch.setattr("tg_pool.api.stories.ClientFactory.build", lambda _account: client)
    manager = StoriesManager([make_account("+100")], PoolAccessGuard())

    manager.start(require_proxy=False,
        action_type="reaction",
        target_chat="@chan",
        target_story_id=7,
        reaction_emoji="🔥",
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    sent_request = client.await_args.args[0]
    assert isinstance(sent_request, SendStoryReactionRequest)
    assert sent_request.story_id == 7
    assert sent_request.reaction.emoticon == "🔥"


async def test_post_job_uploads_photo_and_sends_story(monkeypatch, tmp_path: Path) -> None:
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake-jpeg")
    client = make_client()
    monkeypatch.setattr("tg_pool.api.stories.ClientFactory.build", lambda _account: client)
    manager = StoriesManager([make_account("+100")], PoolAccessGuard())

    manager.start(require_proxy=False,
        action_type="post",
        media_path=str(photo),
        caption="hello",
        privacy="contacts",
        period_hours=12,
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    client.upload_file.assert_awaited_once_with(str(photo))
    sent_request = client.await_args.args[0]
    assert isinstance(sent_request, SendStoryRequest)
    assert isinstance(sent_request.media, InputMediaUploadedPhoto)
    assert sent_request.peer == "me"
    assert sent_request.caption == "hello"
    assert sent_request.period == 12 * 3600
    assert isinstance(sent_request.privacy_rules[0], InputPrivacyValueAllowContacts)
    assert manager.status()["succeeded"] == 1


async def test_post_job_uploads_video_as_document(monkeypatch, tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake-mp4")
    client = make_client()
    monkeypatch.setattr("tg_pool.api.stories.ClientFactory.build", lambda _account: client)
    manager = StoriesManager([make_account("+100")], PoolAccessGuard())

    manager.start(require_proxy=False,
        action_type="post",
        media_path=str(video),
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    sent_request = client.await_args.args[0]
    assert isinstance(sent_request.media, InputMediaUploadedDocument)
    assert sent_request.media.mime_type == "video/mp4"


def test_start_with_require_proxy_rejects_unproxied_senders() -> None:
    manager = StoriesManager([make_account("+100")], PoolAccessGuard())
    with pytest.raises(UnprotectedAccountsError, match=r"\+100"):
        manager.start(action_type="view", target_chat="@chan", target_story_id=1, require_proxy=True)


async def test_daily_cap_skip_is_recorded_and_does_not_connect(monkeypatch, tmp_path: Path) -> None:
    client = make_client()
    monkeypatch.setattr("tg_pool.api.stories.ClientFactory.build", lambda _account: client)
    manager = StoriesManager([make_account("+100")], PoolAccessGuard(), redis_client=object())
    monkeypatch.setattr(manager, "_check_daily_cap", AsyncMock(return_value=False))

    manager.start(require_proxy=False,
        action_type="view",
        target_chat="@chan",
        target_story_id=1,
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    status = manager.status()
    assert status["skipped_daily_cap"] == 1
    client.connect.assert_not_awaited()


async def test_ban_signal_is_recorded_against_the_sender_proxy(monkeypatch, tmp_path: Path) -> None:
    client = make_client()
    client.side_effect = UserDeactivatedBanError(request=None)
    monkeypatch.setattr("tg_pool.api.stories.ClientFactory.build", lambda _account: client)
    proxy = ProxyConfig(host="1.2.3.4", port=1080, proxy_type="socks5")
    proxy_repository = AsyncMock()
    proxy_repository.record_ban_signal = AsyncMock(return_value=True)
    manager = StoriesManager(
        [make_account("+100", proxy=proxy)], PoolAccessGuard(), proxy_repository=proxy_repository
    )

    manager.start(require_proxy=False,
        action_type="view",
        target_chat="@chan",
        target_story_id=1,
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    proxy_repository.record_ban_signal.assert_awaited_once_with(
        proxy_type="socks5", host="1.2.3.4", port=1080, username=""
    )


async def test_flood_wait_beyond_cap_fails_without_retrying(monkeypatch, tmp_path: Path) -> None:
    client = make_client()
    client.side_effect = FloodWaitError(request=None, capture=999)
    monkeypatch.setattr("tg_pool.api.stories.ClientFactory.build", lambda _account: client)
    manager = StoriesManager([make_account("+100")], PoolAccessGuard())

    manager.start(require_proxy=False,
        action_type="view",
        target_chat="@chan",
        target_story_id=1,
        max_flood_wait_sec=1,
        delay_min_sec=0,
        delay_max_sec=0,
        results_dir=str(tmp_path / "results"),
    )
    await manager._run.task

    status = manager.status()
    assert status["floodwait_count"] == 1
    assert status["failed"] == 1
    assert "exceeds maximum timeout" in status["results"][0]["message"]
