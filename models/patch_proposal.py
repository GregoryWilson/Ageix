from typing import Literal
from pydantic import BaseModel, Field, model_validator



class PatchFileChange(BaseModel):
    path: str
    operation: Literal["replace_file", "create_file"]
    content: str


class PatchProposal(BaseModel):
    result_type: Literal["patch_proposal"] = "patch_proposal"
    summary: str
    changes: list[PatchFileChange] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

class ContextRequestedFile(BaseModel):
    path: str
    reason: str
    required: bool = True


class ContextRequest(BaseModel):
    result_type: Literal["context_request"] = "context_request"
    reason: str
    requested_files: list[ContextRequestedFile]
    blocking: bool = True

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_response_type(cls, data):
        if (
            isinstance(data, dict)
            and data.get("response_type") == "context_request"
            and "result_type" not in data
        ):
            data["result_type"] = "context_request"

        return data