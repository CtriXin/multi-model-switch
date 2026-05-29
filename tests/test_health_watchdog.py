from scripts import mms_health_watchdog as watchdog


def test_model_presence_skips_claude_routes_from_models_endpoint_check():
    routes_payload = {
        "routes": {
            "claude-opus-4-6": {
                "primary": {
                    "provider_id": "tokyo",
                    "anthropic_base_url": "https://tokyo.example/v1",
                    "model_id": "claude-opus-4-6",
                },
                "fallbacks": [],
            }
        }
    }
    providers = {"tokyo": {"models_endpoint": "/models"}}
    model_sets = {("tokyo", "https://tokyo.example/v1/models"): {"not-returned-by-claude-relay"}}

    results = watchdog.model_presence_checks(routes_payload, providers, model_sets, {})

    assert results[0].status == "ok"
    assert "skipped 1 Claude route entries" in results[0].detail


def test_model_presence_still_warns_for_non_claude_missing_models():
    routes_payload = {
        "routes": {
            "qwen3.6-plus": {
                "primary": {
                    "provider_id": "qwen",
                    "openai_base_url": "https://qwen.example/v1",
                    "model_id": "qwen3.6-plus",
                },
                "fallbacks": [],
            }
        }
    }
    providers = {"qwen": {"models_endpoint": "/models"}}
    model_sets = {("qwen", "https://qwen.example/v1/models"): {"qwen3.5-plus"}}

    results = watchdog.model_presence_checks(routes_payload, providers, model_sets, {})

    assert results[0].status == "fail"
    assert "qwen3.6-plus@qwen/primary" in results[0].detail
