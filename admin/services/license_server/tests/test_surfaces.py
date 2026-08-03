from license_server.admin_app import app as admin_app
from license_server.public_app import app as public_app


def _paths(app):
    return {getattr(route, "path", "") for route in app.routes}


def test_public_surface_contains_no_admin_routes():
    paths = _paths(public_app)
    assert "/license/activate" in paths
    assert not any(path.startswith("/admin/") for path in paths)


def test_admin_surface_contains_no_public_routes():
    paths = _paths(admin_app)
    assert "/admin/keys" in paths
    assert "/license/activate" not in paths
