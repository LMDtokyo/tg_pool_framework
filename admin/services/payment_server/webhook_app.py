"""Dedicated machine-to-machine deposit webhook surface."""

from payment_server.surfaces import build_surface


app = build_surface(
    "webhook",
    "TG Pool payment webhook API",
    lambda path: path == "/health" or path.startswith("/webhooks/"),
)
