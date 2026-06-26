from __future__ import annotations

import os
from pathlib import Path


def test_ageix_mcp_namespace_does_not_shadow_external_mcp_sdk() -> None:
    assert not Path("mcp").exists()
    assert Path("ageix_mcp").is_dir()

    from ageix_mcp.facade_service import MCPFacadeService
    from ageix_mcp.server import build_fastmcp_server

    assert MCPFacadeService is not None
    assert build_fastmcp_server is not None


def test_fastmcp_transport_imports_ageix_namespace() -> None:
    import web.mcp_transport as transport

    assert transport.build_mcp_transport_lifespan is not None
    assert transport.build_mcp_transport_app is not None


def test_clean_archive_scripts_are_present_and_executable() -> None:
    build_script = Path("scripts/build_clean_archive.sh")
    validate_script = Path("scripts/validate_clean_archive.sh")

    assert build_script.is_file()
    assert validate_script.is_file()
    assert os.access(build_script, os.X_OK)
    assert os.access(validate_script, os.X_OK)
