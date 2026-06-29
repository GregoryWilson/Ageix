from __future__ import annotations

from pathlib import Path

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from models.auth_identity import AuthIdentity
from services.auth_service import AuthForbiddenError, AuthRequiredError, AuthService
from services.mcp_context import AgeixExternalRequestContext, AgeixRequestContext
from web.dependencies import get_repo_root

bearer_scheme = HTTPBearer(auto_error=False)

# Headers that could carry credentials/secrets are never surfaced, even for
# descriptive identity diagnostics.
_SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "proxy-authorization"}


def safe_request_headers(request: Request) -> dict[str, str]:
    """Capture caller-supplied headers for descriptive identity diagnostics only.

    Excludes credential-bearing headers. Never used for authorization decisions --
    callers can set arbitrary header values, so this is purely observational.
    """
    return {key.lower(): value for key, value in request.headers.items() if key.lower() not in _SENSITIVE_HEADERS}


def get_auth_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    repo_root: Path = Depends(get_repo_root),
) -> AuthIdentity:
    token = credentials.credentials if credentials else None
    try:
        return AuthService(repo_root).authenticate_bearer_token(token)
    except AuthRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except AuthForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def resolve_request_context(
    identity: AuthIdentity,
    request_context: AgeixExternalRequestContext,
    repo_root: Path,
    client_user_agent: str | None = None,
    client_headers: dict[str, str] | None = None,
) -> AgeixRequestContext:
    try:
        return AuthService(repo_root).build_resolved_context(
            identity,
            session_id=request_context.session_id,
            project_id=request_context.project_id,
            client_user_agent=client_user_agent,
            client_headers=client_headers,
        )
    except AuthForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def validate_request_context(identity: AuthIdentity, context: AgeixRequestContext, repo_root: Path) -> None:
    try:
        AuthService(repo_root).validate_context(identity, context)
    except AuthForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
