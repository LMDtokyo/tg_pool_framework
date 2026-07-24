"""Fetch HeroSMS activation offers (GET /api/v1/activations/offers).

Docs: https://hero-sms.com/api#tag/activations/GET/activations/offers
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx
from dotenv import load_dotenv

HERO_SMS_OFFERS_URL = "https://hero-sms.com/api/v1/activations/offers"

# HeroSMS / SMS-Activate compatible IDs
DEFAULT_SERVICES = ["tg"]
ROMANIA_COUNTRY_ID = 32
DEFAULT_COUNTRIES = [ROMANIA_COUNTRY_ID]


class HeroSmsOffersError(RuntimeError):
    """Raised when HeroSMS offers cannot be retrieved."""


def fetch_activation_offers(
    api_key: str,
    *,
    services: list[str] | None = None,
    countries: list[int] | None = None,
    api_url: str = HERO_SMS_OFFERS_URL,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Return activation offers grouped by service and country.

    Defaults to Telegram (`tg`) in Romania (country id 32).

    Args:
        api_key: HeroSMS API token (Authorization header).
        services: Optional service codes, e.g. ["tg"]. Defaults to Telegram.
        countries: Optional country IDs, e.g. [32]. Defaults to Romania.
        api_url: Offers endpoint URL.
        timeout: HTTP timeout in seconds.
    """
    key = api_key.strip()
    if not key:
        raise ValueError("HeroSMS API key is required")

    selected_services = services if services is not None else DEFAULT_SERVICES
    selected_countries = countries if countries is not None else DEFAULT_COUNTRIES

    params: dict[str, str] = {}
    if selected_services:
        params["services"] = ",".join(
            code.strip() for code in selected_services if code.strip()
        )
    if selected_countries:
        params["countries"] = ",".join(
            str(country_id) for country_id in selected_countries
        )

    try:
        response = httpx.get(
            api_url,
            params=params or None,
            headers={
                "Accept": "application/json",
                "Authorization": f"ApiKey {key}",
            },
            timeout=timeout,
        )
    except httpx.RequestError as exc:
        raise HeroSmsOffersError("Unable to reach HeroSMS") from exc

    if response.status_code == 401:
        raise HeroSmsOffersError("HeroSMS rejected the API key (401 Unauthorized)")
    if response.status_code == 404:
        raise HeroSmsOffersError("HeroSMS offers endpoint not found (404)")
    if response.status_code == 422:
        raise HeroSmsOffersError(
            f"HeroSMS rejected the offers request (422): {response.text.strip()}"
        )
    if response.status_code == 429:
        raise HeroSmsOffersError("HeroSMS rate limit exceeded (429 Too Many Requests)")
    if response.status_code >= 500:
        raise HeroSmsOffersError(
            f"HeroSMS server error ({response.status_code}): {response.text.strip()}"
        )
    if response.status_code != 200:
        raise HeroSmsOffersError(
            f"HeroSMS returned HTTP {response.status_code}: {response.text.strip()}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise HeroSmsOffersError("HeroSMS returned invalid offers JSON") from exc

    if not isinstance(payload, dict) or "data" not in payload:
        raise HeroSmsOffersError("HeroSMS returned an unexpected offers response")

    return payload


def _parse_csv_strings(value: str | None) -> list[str] | None:
    if value is None or not value.strip():
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def _parse_csv_ints(value: str | None) -> list[int] | None:
    parts = _parse_csv_strings(value)
    if parts is None:
        return None
    try:
        return [int(part) for part in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"countries must be comma-separated integers, got: {value!r}"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Fetch HeroSMS activation offers (GET /activations/offers)"
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("HERO_SMS_API_KEY", ""),
        help="API key (or set HERO_SMS_API_KEY)",
    )
    parser.add_argument(
        "--services",
        default="tg",
        help="Comma-separated service codes (default: tg)",
    )
    parser.add_argument(
        "--countries",
        default=str(ROMANIA_COUNTRY_ID),
        help="Comma-separated country IDs (default: 32 = Romania)",
    )
    args = parser.parse_args(argv)

    if not args.api_key.strip():
        print(
            "Error: provide --api-key or set HERO_SMS_API_KEY in the environment / .env",
            file=sys.stderr,
        )
        return 2

    try:
        offers = fetch_activation_offers(
            args.api_key,
            services=_parse_csv_strings(args.services),
            countries=_parse_csv_ints(args.countries),
        )
    except (ValueError, HeroSmsOffersError, argparse.ArgumentTypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(offers, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
