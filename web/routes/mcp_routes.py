from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from services.mcp_context import AgeixRequestContext
from services.mcp_service import MCPService
from web.dependencies import get_repo_root

router = APIRouter(prefix="/mcp")


class MCPToolPayload(BaseModel):
    context: AgeixRequestContext
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("/tools")
def tools(repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    return {"success": True, "result": {"tools": MCPService(repo_root).discover_tools()}}


@router.post("/tools/call")
def call_tool(payload: MCPToolPayload, repo_root: Path = Depends(get_repo_root)) -> dict[str, Any]:
    return MCPService(repo_root).execute_tool(payload.tool_name, payload.context, payload.arguments).model_dump()
