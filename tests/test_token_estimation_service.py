from services.token_estimation_service import TokenEstimationService


def test_token_estimator_estimates_text_tokens():
    svc = TokenEstimationService()

    assert svc.estimate_text_tokens("abcd") == 1
    assert svc.estimate_text_tokens("abcde") == 2


def test_token_estimator_tracks_cached_prefix_tokens():
    svc = TokenEstimationService()

    estimate = svc.build_estimate(
        sections={"stable": "a" * 400, "fresh": "b" * 200},
        max_output_tokens=100,
        cached_prefix_sections={"stable"},
    )

    assert estimate.estimated_input_tokens == 150
    assert estimate.cached_prefix_tokens == 100
    assert estimate.fresh_input_tokens == 50
    assert estimate.estimated_total_tokens == 250


def test_token_estimator_estimates_model_cost_from_fresh_input_only():
    svc = TokenEstimationService()
    estimate = svc.build_estimate(
        sections={"stable": "a" * 400, "fresh": "b" * 400},
        max_output_tokens=1000,
        cached_prefix_sections={"stable"},
    )

    cost = svc.estimate_cost(model="anthropic/claude-sonnet-4.6", token_estimate=estimate)

    assert cost.estimated_input_cost == 0.0003
    assert cost.estimated_output_cost == 0.015
    assert cost.estimated_total_cost == 0.0153
