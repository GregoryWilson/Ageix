from pydantic import BaseModel, Field
from typing import Literal, Optional


RouteName = Literal[
    "local_fast",
    "local_coding",
    "local_reasoning",
    "cloud_fast",
    "cloud_balanced",
    "cloud_deep",
    "web_research",
]


class RouteSignals(BaseModel):
    needs_current_info: bool = False
    needs_large_context: bool = False
    needs_precision: bool = False
    needs_code: bool = False
    simple_chat: bool = False
    sensitive_data: bool = False
    token_estimate: int = 0


class RouteDecision(BaseModel):
    route: RouteName
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    requires_rag: bool = False
    requires_web: bool = False
    expected_difficulty: Literal["simple", "medium", "hard"] = "medium"
    fallback_route: Optional[RouteName] = "cloud_balanced"