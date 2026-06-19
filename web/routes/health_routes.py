from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, object]:
    return {"success": True, "result": {"status": "ok", "system": "ageix", "web_service": "available"}}
