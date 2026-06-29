from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError
from starlette.requests import Request

from services.auth_service import AuthForbiddenError, AuthRequiredError, AuthService
from services.mcp_context import AgeixEnvelope
from services.mcp_service import MCPService


# Headers that could carry credentials/secrets are never surfaced, even for
# descriptive identity diagnostics.
_SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "proxy-authorization"}


def _safe_request_headers(request: Any) -> dict[str, str] | None:
    if request is None:
        return None
    return {key.lower(): value for key, value in request.headers.items() if key.lower() not in _SENSITIVE_HEADERS}


IDENTITY_ARGUMENT_FIELDS = {
    "client_id",
    "agent_id",
    "participant_id",
    "provider",
    "display_name",
    "authentication_method",
    "authorization",
    "token",
    "bearer_token",
}


def build_fastmcp_server(repo_root: str | Path = ".") -> Any:
    """Build the governed Ageix FastMCP transport server.

    FastMCP is transport only. Authentication is derived from the HTTP request
    bearer token, request context is resolved by AuthService, and every tool call
    delegates to MCPService so capability authorization, project authorization,
    Chair governance, and audit behavior remain authoritative in Ageix.
    """
    try:
        from fastmcp import FastMCP  # type: ignore
        from fastmcp.dependencies import CurrentRequest  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional transport package
        raise RuntimeError("fastmcp_not_installed") from exc

    root = Path(repo_root).resolve()
    service = MCPService(root)
    mcp = FastMCP("Ageix")

    for tool in service.tool_registry.list_tools():
        if tool.placeholder:
            continue
        _register_tool(mcp, service, tool.name, root, CurrentRequest, Request)

    return mcp


def _register_tool(mcp: Any, service: MCPService, tool_name: str, repo_root: Path, CurrentRequest: Any, Request: Any) -> None:
    async def invoke(
        session_id: str,
        project_id: str,
        arguments: dict[str, Any] | None = None,
        request: Request = CurrentRequest(),
    ) -> dict[str, Any]:
        if arguments and IDENTITY_ARGUMENT_FIELDS.intersection(arguments.keys()):
            return AgeixEnvelope.denied("identity_fields_not_allowed", tool_name=tool_name).model_dump()

        auth = AuthService(repo_root)
        token = _bearer_token_from_request(request)
        user_agent = request.headers.get("user-agent") if request is not None else None
        headers = _safe_request_headers(request)
        try:
            identity = auth.authenticate_bearer_token(token)
            context = auth.build_resolved_context(
                identity,
                session_id=session_id,
                project_id=project_id,
                client_user_agent=user_agent,
                client_headers=headers,
            )
        except AuthRequiredError as exc:
            return AgeixEnvelope.denied(str(exc), tool_name=tool_name).model_dump()
        except AuthForbiddenError as exc:
            return AgeixEnvelope.denied(str(exc), tool_name=tool_name, security_violation=True).model_dump()
        except ValidationError as exc:
            message = str(exc.errors()[0].get("ctx", {}).get("error") or exc.errors()[0].get("msg") or "request_context_invalid")
            return AgeixEnvelope.denied(message, tool_name=tool_name).model_dump()

        capability_id = service.tool_registry.map_capability(tool_name) or tool_name
        requested_capability_id = str((arguments or {}).get("capability_id") or "")
        if not identity.capability_allowed(capability_id):
            return AgeixEnvelope.denied("capability_not_authorized_for_token", tool_name=tool_name, capability_id=capability_id).model_dump()
        if capability_id == "capabilities.execute" and requested_capability_id and not identity.capability_allowed(requested_capability_id):
            return AgeixEnvelope.denied("capability_not_authorized_for_token", tool_name=tool_name, capability_id=requested_capability_id).model_dump()

        return service.execute_tool(tool_name, context, arguments or {}).model_dump()

    wire_name = tool_name.replace(".", "_")
    invoke.__name__ = wire_name
    invoke.__doc__ = f"Governed Ageix MCP tool adapter for {tool_name}."
    # MCP clients (e.g. claude.ai's frontend) validate tool names against
    # ^[a-zA-Z0-9_-]{1,64}$ -- dots are rejected. Advertise the sanitized name on
    # the wire; tool_name (with dots) keeps driving capability mapping/audit/governance.
    mcp.tool(name=wire_name)(invoke)


def _bearer_token_from_request(request: Any) -> str | None:
    authorization = request.headers.get("authorization") if request is not None else None
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token
