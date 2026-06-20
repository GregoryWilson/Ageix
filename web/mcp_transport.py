from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from services.auth_service import AuthForbiddenError, AuthRequiredError, AuthService
from mcp.server import build_fastmcp_server


class MCPTransportAuthMiddleware:
    """Authenticate all mounted MCP transport requests before FastMCP handles them."""

    def __init__(self, app: ASGIApp, repo_root: str | Path = ".") -> None:
        self.app = app
        self.repo_root = Path(repo_root).resolve()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        token = _bearer_token_from_scope(scope)
        try:
            identity = AuthService(self.repo_root).authenticate_bearer_token(token)
        except AuthRequiredError as exc:
            await JSONResponse({"detail": str(exc)}, status_code=401)(scope, receive, send)
            return
        except AuthForbiddenError as exc:
            await JSONResponse({"detail": str(exc)}, status_code=403)(scope, receive, send)
            return
        scope.setdefault("state", {})["ageix_auth_identity"] = identity.model_dump()
        await self.app(scope, receive, send)


def build_mcp_transport_app(repo_root: str | Path = ".") -> ASGIApp:
    """Return an authenticated FastMCP ASGI transport app mounted at /mcp."""
    mcp = build_fastmcp_server(repo_root)
    mcp_app = mcp.http_app(path="/")
    return MCPTransportAuthMiddleware(mcp_app, repo_root)


def build_mcp_transport_lifespan(repo_root: str | Path = ".") -> tuple[ASGIApp | None, Any | None, str | None]:
    """Best-effort helper for web.app.

    Returns the mounted app and its lifespan when FastMCP is installed. When the
    optional transport package is unavailable, return a reason so /mcp can still
    fail explicitly instead of appearing as a missing route.
    """
    try:
        mcp = build_fastmcp_server(repo_root)
        mcp_app = mcp.http_app(path="/")
        return MCPTransportAuthMiddleware(mcp_app, repo_root), getattr(mcp_app, "lifespan", None), None
    except RuntimeError as exc:
        return None, None, str(exc)


def _bearer_token_from_scope(scope: Scope) -> str | None:
    headers = {key.lower(): value for key, value in scope.get("headers") or []}
    raw = headers.get(b"authorization")
    if not raw:
        return None
    authorization = raw.decode("latin1")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token
