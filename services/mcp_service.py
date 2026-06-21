from __future__ import annotations

from pathlib import Path

from ageix_mcp.facade_service import MCPFacadeService


class MCPService(MCPFacadeService):
    """Backward-compatible alias for the Sprint 15 MCP facade service."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        super().__init__(repo_root)
