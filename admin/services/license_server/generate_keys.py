"""
license_server/generate_keys.py — Admin CLI to mint license keys at sale time.

Talks to a running license_server over HTTP (not the DB directly), so it
works the same way whether the server is local or deployed remotely.

Usage:
    python -m license_server.generate_keys --tier month --count 5 --note "order #123"
    python -m license_server.generate_keys --tier year --count 1 --url https://license.example.com

Requires LICENSE_ADMIN_API_KEY in the environment (or --admin-key).
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Generate license keys")
    parser.add_argument("--tier", required=True, choices=["week", "month", "half_year", "year"])
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--note", default="")
    parser.add_argument("--url", default=os.getenv("LICENSE_SERVER_URL", "http://127.0.0.1:8100"))
    parser.add_argument("--admin-key", default=os.getenv("LICENSE_ADMIN_API_KEY", ""))
    args = parser.parse_args()

    if not args.admin_key:
        print("Error: LICENSE_ADMIN_API_KEY is not set (env var or --admin-key).", file=sys.stderr)
        return 1

    response = httpx.post(
        f"{args.url}/admin/keys",
        json={"tier": args.tier, "count": args.count, "note": args.note},
        headers={"X-Admin-Key": args.admin_key},
        timeout=30.0,
    )
    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text}", file=sys.stderr)
        return 1

    for issued in response.json()["keys"]:
        print(issued["key_code"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
