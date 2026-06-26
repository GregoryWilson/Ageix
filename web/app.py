from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from web.routes.audit_routes import router as audit_router
from web.routes.capability_routes import router as capability_router
from web.routes.consultation_routes import router as consultation_router
from web.routes.health_routes import router as health_router
from web.routes.mcp_routes import router as mcp_router
from web.routes.oauth_discovery_routes import router as oauth_discovery_router
from web.routes.project_routes import router as project_router
from web.routes.proposal_routes import router as proposal_router
from web.mcp_transport import build_mcp_transport_lifespan


def create_app(repo_root: str | Path = ".") -> FastAPI:
    mcp_transport_app, mcp_lifespan, mcp_unavailable_reason = build_mcp_transport_lifespan(repo_root)
    app = FastAPI(title="Ageix Governed Service Boundary", version="16.5", lifespan=mcp_lifespan)
    app.include_router(oauth_discovery_router)
    app.include_router(health_router)
    app.include_router(capability_router)
    app.include_router(project_router)
    app.include_router(proposal_router)
    app.include_router(consultation_router)
    app.include_router(audit_router)
    app.include_router(mcp_router)

    if mcp_transport_app is not None:
        app.mount("/mcp", mcp_transport_app, name="ageix-mcp-transport")
    else:
        @app.get("/mcp")
        def mcp_transport_unavailable() -> dict[str, object]:
            return {
                "success": False,
                "errors": [mcp_unavailable_reason or "mcp_transport_unavailable"],
                "metadata": {"transport": "fastmcp"},
            }

    return app


app = create_app()
