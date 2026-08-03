"""
tg_pool/api/local_auth.py — ASGI middleware that requires a shared-secret
header on every request once LOCAL_API_TOKEN is set.

This backend has no other authentication (see tg_pool/api/license_gate.py's
docstring for the license check, which authenticates the subscription, not
the caller): it binds to 127.0.0.1 only and trusts whatever reaches it, on
the assumption that the only caller is the WPF launcher spawning it as a
child process. That assumption fails if another local process (malware, a
compromised browser extension, a future misconfiguration that widens the
bind address) reaches the port instead -- this token is the defense-in-depth
layer for that case: the launcher generates a random token per launch and
passes it to both this process and its own HTTP/WebSocket clients, so a
caller that doesn't already share the launcher's process environment can't
authenticate.

Opt-in via LOCAL_API_TOKEN, same pattern as LICENSE_SERVER_URL/REDIS_URL
elsewhere in this app: unset -> no enforcement, so running the backend
directly for local development or tests needs no extra setup.

Pure ASGI (not BaseHTTPMiddleware) for the same reason as LicenseGateMiddleware:
BaseHTTPMiddleware only sees "http" scopes, which would leave /ws/events
open to an unauthenticated caller.
"""

from __future__ import annotations

import secrets
from typing import Iterable

_UNAUTHORIZED_BODY = b'{"detail":"Missing or invalid local API token."}'
_WEBSOCKET_CLOSE_CODE = 4401  # 4000-4999 is the app-defined range for websocket close codes
_HEADER_NAME = b"x-local-token"


class LocalAuthMiddleware:
    """Reads the expected token from app.state (set fresh in lifespan()) on
    every request, rather than capturing it once at add_middleware() time --
    that constructor call happens at module import, long before any env var
    a test or a real run sets is guaranteed to be in place."""

    def __init__(self, app, *, allow_prefixes: Iterable[str] = ("/health",)) -> None:
        self._app = app
        self._allow_prefixes = tuple(allow_prefixes)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        token = getattr(scope["app"].state, "local_api_token", "")
        path = scope.get("path", "")
        if not token or path.startswith(self._allow_prefixes) or self._token_matches(scope, token):
            await self._app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": _WEBSOCKET_CLOSE_CODE})
            return

        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": _UNAUTHORIZED_BODY})

    @staticmethod
    def _token_matches(scope, token: str) -> bool:
        for name, value in scope.get("headers", ()):
            if name == _HEADER_NAME:
                return secrets.compare_digest(value.decode("latin-1"), token)
        return False
