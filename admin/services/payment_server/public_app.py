"""Internet-facing customer payment API with no administrator routes."""

from payment_server.surfaces import build_surface


app = build_surface(
    "public",
    "TG Pool public payment API",
    lambda path: path == "/health" or path.startswith("/v1/"),
)
