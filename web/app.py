from __future__ import annotations

from fastapi import FastAPI

from web.routes.audit_routes import router as audit_router
from web.routes.capability_routes import router as capability_router
from web.routes.consultation_routes import router as consultation_router
from web.routes.health_routes import router as health_router
from web.routes.mcp_routes import router as mcp_router
from web.routes.project_routes import router as project_router
from web.routes.proposal_routes import router as proposal_router


def create_app() -> FastAPI:
    app = FastAPI(title="Ageix Governed Service Boundary", version="14.0")
    app.include_router(health_router)
    app.include_router(capability_router)
    app.include_router(project_router)
    app.include_router(proposal_router)
    app.include_router(consultation_router)
    app.include_router(audit_router)
    app.include_router(mcp_router)
    return app


app = create_app()
