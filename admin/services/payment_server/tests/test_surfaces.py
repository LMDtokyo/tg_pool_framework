from payment_server.admin_app import app as admin_app
from payment_server.public_app import app as public_app
from payment_server.webhook_app import app as webhook_app


def _paths(app):
    return {getattr(route, "path", "") for route in app.routes}


def test_public_surface_has_only_customer_routes():
    paths = _paths(public_app)
    assert "/v1/balance" in paths
    assert not any(path.startswith("/admin/") for path in paths)
    assert not any(path.startswith("/webhooks/") for path in paths)


def test_admin_surface_has_only_admin_routes():
    paths = _paths(admin_app)
    assert "/admin/users" in paths
    assert not any(path.startswith("/v1/") for path in paths)
    assert not any(path.startswith("/webhooks/") for path in paths)


def test_webhook_surface_has_only_webhook_routes():
    paths = _paths(webhook_app)
    assert "/webhooks/tron/deposits" in paths
    assert not any(path.startswith("/v1/") for path in paths)
    assert not any(path.startswith("/admin/") for path in paths)
