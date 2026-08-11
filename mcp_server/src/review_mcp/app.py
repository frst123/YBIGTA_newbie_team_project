from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from review_mcp.auth import BearerTokenMiddleware
from review_mcp.config import Settings
from review_mcp.server import mcp


settings = Settings.from_env()
if not settings.mcp_auth_token:
    raise RuntimeError("MCP_AUTH_TOKEN is required for the HTTP server")

security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=list(settings.allowed_hosts),
    allowed_origins=list(settings.allowed_origins),
)
mcp_app = mcp.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    host=settings.mcp_host,
    transport_security=security,
)
protected_mcp_app = BearerTokenMiddleware(mcp_app, settings.mcp_auth_token)


async def health(_: Request) -> Response:
    return JSONResponse({"status": "ok", "service": "ybigta-review-mcp"})


@asynccontextmanager
async def lifespan(_: Starlette) -> AsyncIterator[None]:
    async with mcp.session_manager.run():
        yield


app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Mount("/", app=protected_mcp_app),
    ],
    lifespan=lifespan,
)
