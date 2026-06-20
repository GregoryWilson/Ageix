from __future__ import annotations

from pathlib import Path

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from models.auth_identity import AuthIdentity
from services.auth_service import AuthForbiddenError, AuthRequiredError, AuthService
from services.mcp_context import AgeixExternalRequestContext, AgeixRequestContext
from web.dependencies import get_repo_root

bearer_scheme = HTTPBearer(auto_error=False)


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


def resolve_request_context(identity: AuthIdentity, request_context: AgeixExternalRequestContext, repo_root: Path) -> AgeixRequestContext:
    try:
        return AuthService(repo_root).build_resolved_context(
            identity,
            session_id=request_context.session_id,
            project_id=request_context.project_id,
        )
    except AuthForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def validate_request_context(identity: AuthIdentity, context: AgeixRequestContext, repo_root: Path) -> None:
    try:
        AuthService(repo_root).validate_context(identity, context)
    except AuthForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
