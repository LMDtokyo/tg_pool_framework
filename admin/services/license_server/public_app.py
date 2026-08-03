"""Internet-facing license API. This process contains no administrator routes."""

from license_server.surfaces import build_surface


app = build_surface(
    "public",
    "TG Pool public license API",
    lambda path: path == "/health" or not path.startswith("/admin/"),
)
