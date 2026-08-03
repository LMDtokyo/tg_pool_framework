"""Minimal Telegram onboarding bot for issuing payment API keys.

Run separately from the API:
    python -m payment_server.telegram_bot
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from payment_server.telegram import send_telegram_message, telegram_client

logger = logging.getLogger("payment_server.telegram_bot")

BALANCE_BUTTON = "💰 Balance"
REISSUE_KEY_BUTTON = "🔑 Reissue Key"
BALANCE_CALLBACK = "balance"
REISSUE_KEY_CALLBACK = "reissue_key"
MAIN_MENU = {
    "inline_keyboard": [
        [
            {"text": BALANCE_BUTTON, "callback_data": BALANCE_CALLBACK},
            {"text": REISSUE_KEY_BUTTON, "callback_data": REISSUE_KEY_CALLBACK},
        ]
    ],
}


async def _issue_account(
    payment_client: httpx.AsyncClient,
    *,
    user_id: int,
    display_name: str,
    admin_key: str,
    username: str = "",
) -> dict[str, Any]:
    response = await payment_client.post(
        "/admin/users",
        headers={"X-Admin-Key": admin_key},
        json={
            "telegram_user_id": str(user_id),
            "telegram_username": username.strip().lstrip("@") or None,
            "display_name": display_name,
        },
    )
    if response.status_code == 409:
        existing = await payment_client.get(
            f"/admin/telegram-users/{user_id}",
            headers={"X-Admin-Key": admin_key},
        )
        existing.raise_for_status()
        payload = existing.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Payment service returned an invalid response")
        payload["existing"] = True
        return payload
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Payment service returned an invalid response")
    return payload


async def _fetch_balance(
    payment_client: httpx.AsyncClient,
    *,
    user_id: int,
    admin_key: str,
) -> dict[str, Any]:
    response = await payment_client.get(
        f"/admin/telegram-users/{user_id}/balance",
        headers={"X-Admin-Key": admin_key},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Payment service returned an invalid response")
    return payload


async def _reissue_key(
    payment_client: httpx.AsyncClient,
    *,
    user_id: int,
    admin_key: str,
) -> dict[str, Any]:
    response = await payment_client.post(
        f"/admin/telegram-users/{user_id}/regenerate-key",
        headers={"X-Admin-Key": admin_key},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Payment service returned an invalid response")
    return payload


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return "No payment account found. Send /start to create one."
    return "Unable to complete the request. Please try again later."


async def run() -> None:
    load_dotenv(Path(__file__).resolve().parent / ".env")
    bot_token = os.getenv("PAYMENT_TELEGRAM_BOT_TOKEN", "").strip()
    payment_url = os.getenv("PAYMENT_PUBLIC_URL", "http://127.0.0.1:8200").rstrip("/")
    admin_key = os.getenv("PAYMENT_ADMIN_API_KEY", "").strip()
    if not bot_token or not admin_key:
        raise RuntimeError(
            "PAYMENT_TELEGRAM_BOT_TOKEN and PAYMENT_ADMIN_API_KEY must be set"
        )

    offset = 0
    async with (
        telegram_client(timeout=40.0) as telegram,
        httpx.AsyncClient(base_url=payment_url, timeout=20.0) as payment,
    ):
        while True:
            try:
                response = await telegram.get(
                    "/getUpdates",
                    params={
                        "timeout": 30,
                        "offset": offset,
                        "allowed_updates": '["message","callback_query"]',
                    },
                )
                response.raise_for_status()
                for update in response.json().get("result", []):
                    offset = max(offset, int(update["update_id"]) + 1)
                    callback = update.get("callback_query") or {}
                    if callback:
                        message = callback.get("message") or {}
                        callback_data = str(callback.get("data") or "")
                        text = {
                            BALANCE_CALLBACK: BALANCE_BUTTON,
                            REISSUE_KEY_CALLBACK: REISSUE_KEY_BUTTON,
                        }.get(callback_data, "")
                        sender = callback.get("from") or {}
                    else:
                        message = update.get("message") or {}
                        text = str(message.get("text") or "").strip()
                        text = {
                            "/balance": BALANCE_BUTTON,
                            "/reissue_key": REISSUE_KEY_BUTTON,
                        }.get(text.split("@", 1)[0].lower(), text)
                        sender = message.get("from") or {}
                    if (
                        not text.startswith("/start")
                        and text not in {BALANCE_BUTTON, REISSUE_KEY_BUTTON}
                    ):
                        continue
                    chat = message.get("chat") or {}
                    if "id" not in sender or "id" not in chat:
                        continue
                    chat_id = int(chat["id"])
                    user_id = int(sender["id"])
                    username = str(sender.get("username") or "").strip()
                    name = " ".join(
                        part
                        for part in (
                            str(sender.get("first_name") or "").strip(),
                            str(sender.get("last_name") or "").strip(),
                        )
                        if part
                    )
                    try:
                        if text.startswith("/start"):
                            issued = await _issue_account(
                                payment,
                                user_id=user_id,
                                display_name=name,
                                admin_key=admin_key,
                                username=username,
                            )
                            if issued.get("existing"):
                                message_text = (
                                    "Your payment account already exists.\n\n"
                                    f"Deposit ({issued['network']} {issued['asset']}):\n"
                                    f"{issued['deposit_address']}\n\n"
                                    "The original API key cannot be shown again. "
                                    "Use Reissue Key if you need a replacement."
                                )
                            else:
                                message_text = (
                                    "Your payment account is ready.\n\n"
                                    f"API key:\n{issued['api_key']}\n\n"
                                    f"Deposit ({issued['network']} {issued['asset']}):\n"
                                    f"{issued['deposit_address']}\n\n"
                                    "Keep the API key private. It is shown only once."
                                )
                        elif text == BALANCE_BUTTON:
                            balance = await _fetch_balance(
                                payment,
                                user_id=user_id,
                                admin_key=admin_key,
                            )
                            message_text = (
                                "Your purchasing balance:\n"
                                f"{balance['available_balance']} {balance['currency']}"
                            )
                        else:
                            regenerated = await _reissue_key(
                                payment,
                                user_id=user_id,
                                admin_key=admin_key,
                            )
                            message_text = (
                                "Your new API key:\n"
                                f"{regenerated['api_key']}\n\n"
                                "Keep it private. All previous API keys are now revoked."
                            )
                        await send_telegram_message(
                            chat_id,
                            message_text,
                            reply_markup=MAIN_MENU,
                        )
                        if callback.get("id"):
                            callback_response = await telegram.post(
                                "/answerCallbackQuery",
                                json={"callback_query_id": callback["id"]},
                            )
                            callback_response.raise_for_status()
                    except Exception as exc:
                        logger.warning(
                            "Unable to handle Telegram request for user %s: %s",
                            sender.get("id"),
                            exc,
                        )
                        await send_telegram_message(
                            chat_id,
                            _friendly_error(exc),
                            reply_markup=MAIN_MENU,
                        )
                        if callback.get("id"):
                            await telegram.post(
                                "/answerCallbackQuery",
                                json={"callback_query_id": callback["id"]},
                            )
            except Exception:
                logger.exception("Telegram polling failed")
                await asyncio.sleep(3)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
