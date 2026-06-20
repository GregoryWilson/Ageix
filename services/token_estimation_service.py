from __future__ import annotations

import math
from typing import Any

from models.consultation import CostEstimate, TokenEstimate


class TokenEstimationService:
    """Deterministic token and spend estimates for pre-consultation approval."""

    DEFAULT_MODEL_PRICING = {
        "generic": {
            "input_cost_per_million": 0.0,
            "output_cost_per_million": 0.0,
        },
        "anthropic/claude-sonnet-4.6": {
            "input_cost_per_million": 3.00,
            "output_cost_per_million": 15.00,
        },
        "anthropic/claude-opus-4.6": {
            "input_cost_per_million": 5.00,
            "output_cost_per_million": 25.00,
        },
        "anthropic/claude-haiku-4.5": {
            "input_cost_per_million": 1.00,
            "output_cost_per_million": 5.00,
        },
    }

    def estimate_text_tokens(self, text: str | None) -> int:
        if not text:
            return 0
        return max(1, math.ceil(len(text) / 4))

    def estimate_payload_tokens(self, payload: Any) -> int:
        if payload is None:
            return 0
        if isinstance(payload, str):
            return self.estimate_text_tokens(payload)
        return self.estimate_text_tokens(str(payload))

    def build_estimate(
        self,
        *,
        sections: dict[str, Any],
        max_output_tokens: int,
        cached_prefix_sections: set[str] | None = None,
    ) -> TokenEstimate:
        cached_prefix_sections = cached_prefix_sections or set()
        section_tokens = {
            name: self.estimate_payload_tokens(value)
            for name, value in sections.items()
        }
        cached_prefix_tokens = sum(
            tokens for name, tokens in section_tokens.items()
            if name in cached_prefix_sections
        )
        input_tokens = sum(section_tokens.values())
        fresh_input_tokens = max(0, input_tokens - cached_prefix_tokens)
        return TokenEstimate(
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=max_output_tokens,
            estimated_total_tokens=input_tokens + max_output_tokens,
            cached_prefix_tokens=cached_prefix_tokens,
            fresh_input_tokens=fresh_input_tokens,
            estimation_method="chars_div_4",
        )

    def estimate_cost(
        self,
        *,
        model: str,
        token_estimate: TokenEstimate,
        pricing: dict[str, dict[str, float]] | None = None,
    ) -> CostEstimate:
        pricing_table = pricing or self.DEFAULT_MODEL_PRICING
        model_pricing = pricing_table.get(model, pricing_table["generic"])
        input_cost = (
            token_estimate.fresh_input_tokens
            * float(model_pricing.get("input_cost_per_million", 0.0))
            / 1_000_000
        )
        output_cost = (
            token_estimate.estimated_output_tokens
            * float(model_pricing.get("output_cost_per_million", 0.0))
            / 1_000_000
        )
        return CostEstimate(
            model=model,
            estimated_input_cost=round(input_cost, 6),
            estimated_output_cost=round(output_cost, 6),
            estimated_total_cost=round(input_cost + output_cost, 6),
        )
