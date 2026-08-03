"""Export deterministic OpenAPI contracts for each deployable API surface."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

SERVICES_DIR = Path(__file__).resolve().parents[1] / "services"
sys.path.insert(0, str(SERVICES_DIR))

from license_server.admin_app import app as license_admin
from license_server.public_app import app as license_public
from payment_server.admin_app import app as payment_admin
from payment_server.public_app import app as payment_public
from payment_server.webhook_app import app as payment_webhook


OUTPUTS = {
    "public-license.openapi.json": license_public,
    "admin-license.openapi.json": license_admin,
    "public-payment.openapi.json": payment_public,
    "admin-payment.openapi.json": payment_admin,
    "payment-webhook.openapi.json": payment_webhook,
}


def main() -> None:
    output_dir = Path(os.getenv("OPENAPI_OUTPUT_DIR", Path(__file__).resolve().parent))
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, app in OUTPUTS.items():
        target = output_dir / filename
        target.write_text(
            json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
