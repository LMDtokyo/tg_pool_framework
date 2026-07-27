"""
src/api/license_gate.py — ASGI middleware that blocks API access once the
local LicenseService reports the subscription is no longer active.

Pure ASGI (not Starlette's BaseHTTPMiddleware) so both "http" and
"websocket" scopes are gated identically -- BaseHTTPMiddleware only sees
HTTP requests, which would leave /ws/events wide open to an unlicensed
caller.
"""

from __future__ import annotations

from typing import Iterable

_UNLICENSED_BODY = b'{"detail":"A valid subscription is required."}'
_WEBSOCKET_CLOSE_CODE = 4402  # 4000-4999 is the app-defined range for websocket close codes


class LicenseGateMiddleware:
    def __init__(self, app, *, allow_prefixes: Iterable[str]) -> None:
        self._app = app
        self._allow_prefixes = tuple(allow_prefixes)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        path = scope.get("path", "")
        state = scope["app"].state
        if (
            path.startswith(self._allow_prefixes)
            or not state.licensing_enabled
            or state.license_service.is_active()
        ):
            await self._app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": _WEBSOCKET_CLOSE_CODE})
            return

        await send(
            {
                "type": "http.response.start",
                "status": 402,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": _UNLICENSED_BODY})
