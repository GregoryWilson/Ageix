from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


PatchOperation = Literal["create", "modify", "delete"]


class PatchFile(BaseModel):
    path: str
    operation: PatchOperation = "modify"
    content: str | None = None


class PatchProposal(BaseModel):
    result_type: Literal["patch_proposal"] = "patch_proposal"
    objective: str
    summary: str
    reasoning: str = ""
    files: list[PatchFile] = Field(default_factory=list)