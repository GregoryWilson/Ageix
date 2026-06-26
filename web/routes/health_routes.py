from __future__ import annotations

from fastapi import APIRouter, Depends

from models.auth_identity import AuthIdentity
from web.auth import get_auth_identity

router = APIRouter()


@router.get("/health")
def health(identity: AuthIdentity = Depends(get_auth_identity)) -> dict[str, object]:
    metadata: dict[str, object] = {"auth_enabled": identity.auth_enabled}
    if identity.auth_enabled:
        metadata.update({"client_id": identity.client_id, "authentication_method": identity.authentication_method})
    return {"success": True, "result": {"status": "ok", "system": "ageix", "web_service": "available"}, "metadata": metadata}
