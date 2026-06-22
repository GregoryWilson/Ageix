from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request

from services.oauth_discovery_service import OAuthDiscoveryService
from web.dependencies import get_repo_root

router = APIRouter()


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _mcp_resource_url(request: Request) -> str:
    return f"{_base_url(request)}/mcp"


@router.get("/.well-known/oauth-protected-resource/mcp")
@router.get("/mcp/.well-known/oauth-protected-resource")
def oauth_protected_resource_metadata(request: Request, repo_root: Path = Depends(get_repo_root)) -> dict[str, object]:
    return OAuthDiscoveryService(repo_root).protected_resource_metadata(_mcp_resource_url(request))


@router.get("/.well-known/oauth-authorization-server/mcp")
@router.get("/mcp/.well-known/oauth-authorization-server")
def oauth_authorization_server_metadata(request: Request, repo_root: Path = Depends(get_repo_root)) -> dict[str, object]:
    return OAuthDiscoveryService(repo_root).authorization_server_metadata(_base_url(request))


@router.get("/.well-known/openid-configuration")
@router.get("/mcp/.well-known/openid-configuration")
def openid_configuration(request: Request, repo_root: Path = Depends(get_repo_root)) -> dict[str, object]:
    return OAuthDiscoveryService(repo_root).openid_configuration(_base_url(request))
