from __future__ import annotations

from fastapi import FastAPI

from human_interface_adapter import router as human_interface_router


app = FastAPI(title="Ageix Human Interface Adapter")
app.include_router(human_interface_router)
