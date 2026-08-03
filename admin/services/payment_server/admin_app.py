"""Private administrator payment API with no customer or webhook routes."""

from payment_server.surfaces import build_surface


app = build_surface(
    "admin",
    "TG Pool administrator payment API",
    lambda path: path == "/health" or path.startswith("/admin/"),
)
