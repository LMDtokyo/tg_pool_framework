"""Build isolated public, administrator, and webhook payment applications."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from payment_server.app import app as combined_app


def build_surface(name: str, title: str, include_path: Callable[[str], bool]) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        combined_app.state.active_surface = name
        async with combined_app.router.lifespan_context(combined_app):
            yield

    surface = FastAPI(title=title, lifespan=lifespan)
    framework_paths = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    for route in combined_app.router.routes:
        path = getattr(route, "path", "")
        if path not in framework_paths and include_path(path):
            surface.router.routes.append(route)
    return surface
