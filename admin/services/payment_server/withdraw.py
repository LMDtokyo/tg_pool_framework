"""Administrator CLI for sweeping a user's on-chain deposit wallet."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent / ".env")
    parser = argparse.ArgumentParser(
        description=(
            "Move confirmed on-chain funds from a user's deposit wallet to the "
            "configured treasury without changing the user's database balance."
        )
    )
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument("--amount", help="Token amount; omit to sweep the full chain balance")
    parser.add_argument("--idempotency-key", default="")
    parser.add_argument("--actor", default=os.getenv("PAYMENT_ADMIN_ACTOR", "cli-admin"))
    parser.add_argument(
        "--url",
        default=os.getenv("PAYMENT_ADMIN_URL", "http://127.0.0.1:8200"),
    )
    args = parser.parse_args()

    admin_key = os.getenv("PAYMENT_ADMIN_API_KEY", "").strip()
    if not admin_key:
        raise SystemExit("PAYMENT_ADMIN_API_KEY must be set")
    idempotency_key = args.idempotency_key.strip() or f"cli-{uuid.uuid4()}"
    body = {"amount": args.amount} if args.amount is not None else {}
    response = httpx.post(
        f"{args.url.rstrip('/')}/admin/users/{args.user_id}/withdrawals",
        headers={
            "X-Admin-Key": admin_key,
            "X-Admin-Actor": args.actor,
            "Idempotency-Key": idempotency_key,
        },
        json=body,
        timeout=90.0,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": response.text}
    print(json.dumps(payload, indent=2))
    if not response.is_success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
