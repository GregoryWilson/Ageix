from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from models.auth_identity import AuthIdentity
from services.mcp_context import AgeixRequestContext
from services.mcp_service import MCPService
from web.auth import get_auth_identity, validate_request_context
from web.dependencies import get_repo_root

router = APIRouter(prefix="/mcp")


class MCPToolPayload(BaseModel):
    context: AgeixRequestContext
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
        "metadata": {"auth_enabled": identity.auth_enabled},
    }


@router.post("/tools/call")
def call_tool(payload: MCPToolPayload, identity: AuthIdentity = Depends(get_auth_identity), repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    validate_request_context(identity, payload.context, repo_root)
    return MCPService(repo_root).execute_tool(payload.tool_name, payload.context, payload.arguments).model_dump()
