"""Private administrator license API. Deploy only on the operations network."""

from license_server.surfaces import build_surface


app = build_surface(
    "admin",
    "TG Pool administrator license API",
    lambda path: path == "/health" or path.startswith("/admin/"),
)
