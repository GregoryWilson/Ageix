from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from models.auth_identity import AuthIdentity
from services.mcp_context import AgeixEnvelope, AgeixExternalRequestContext
from services.mcp_service import MCPService
from web.auth import get_auth_identity, resolve_request_context, safe_request_headers
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
    tools = service.discover_tools(
        category=category,
        experimental=experimental,
        include_placeholders=include_placeholders,
    )
    if identity.auth_enabled:
        tools = [tool for tool in tools if identity.capability_allowed(str(tool.get("capability_id") or ""))]
    return {
        "success": True,
        "result": {
            "tools": tools,
            "categories": service.discover_categories(include_placeholders=include_placeholders),
        },
        "metadata": {"auth_enabled": identity.auth_enabled, "client_id": identity.client_id if identity.auth_enabled else None},
    }


@router.post("/tools/call")
def call_tool(
    payload: MCPToolPayload,
    request: Request,
    identity: AuthIdentity = Depends(get_auth_identity),
    repo_root: Path = Depends(get_repo_root),
) -> dict[str, Any]:
    service = MCPService(repo_root)
    context = resolve_request_context(
        identity,
        payload.context,
        repo_root,
        client_user_agent=request.headers.get("user-agent"),
        client_headers=safe_request_headers(request),
    )
    capability_id = service.tool_registry.map_capability(payload.tool_name) or payload.tool_name
    requested_capability_id = str((payload.arguments or {}).get("capability_id") or "")
    if not identity.capability_allowed(capability_id):
        return AgeixEnvelope.denied("capability_not_authorized_for_token", tool_name=payload.tool_name, capability_id=capability_id).model_dump()
    if capability_id == "capabilities.execute" and requested_capability_id and not identity.capability_allowed(requested_capability_id):
        return AgeixEnvelope.denied("capability_not_authorized_for_token", tool_name=payload.tool_name, capability_id=requested_capability_id).model_dump()
    return service.execute_tool(payload.tool_name, context, payload.arguments).model_dump()
