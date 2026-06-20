from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from models.auth_identity import AuthIdentity
from services.mcp_context import AgeixExternalRequestContext
from services.mcp_service import MCPService
from web.auth import get_auth_identity, resolve_request_context
from web.dependencies import get_repo_root

router = APIRouter(prefix="/mcp")


class MCPToolPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context: AgeixExternalRequestContext
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("/tools")
def tools(
    identity: AuthIdentity = Depends(get_auth_identity),
    repo_root: Path = Depends(get_repo_root),
    category: str | None = Query(default=None),
    experimental: bool | None = Query(default=None),
    include_placeholders: bool = Query(default=True),
) -> dict[str, Any]:
    service = MCPService(repo_root)
    return {
        "success": True,
        "result": {
            "tools": service.discover_tools(
                category=category,
                experimental=experimental,
                include_placeholders=include_placeholders,
            ),
            "categories": service.discover_categories(include_placeholders=include_placeholders),
        },
        "metadata": {"auth_enabled": identity.auth_enabled, "client_id": identity.client_id if identity.auth_enabled else None},
    }


@router.post("/tools/call")
def call_tool(payload: MCPToolPayload, identity: AuthIdentity = Depends(get_auth_identity), repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    context = resolve_request_context(identity, payload.context, repo_root)
    return MCPService(repo_root).execute_tool(payload.tool_name, context, payload.arguments).model_dump()
