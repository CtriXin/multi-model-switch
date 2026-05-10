import asyncio
import json


def _profiles(monkeypatch, tmp_path):
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    import mms_provider_profiles

    mms_provider_profiles.load_provider_profiles.cache_clear()
    return mms_provider_profiles


def test_profile_budget_patch_maps_reasoning_effort(monkeypatch, tmp_path):
    (tmp_path / "provider-profiles.json").write_text(
        json.dumps(
            {
                "profiles": {
                    "gemini-test": {
                        "thinking": {"supported": True, "default_enabled": True},
                        "body_patches": {
                            "anthropic_messages": {
                                "thinking_on": {"thinking.type": "enabled"},
                                "thinking_off": {"thinking.type": "disabled"},
                            }
                        },
                        "budget": {
                            "anthropic_messages": {
                                "path": "thinkingConfig.thinkingBudget",
                                "default": 8192,
                                "map": {"medium": 4096, "high": 8192, "xhigh": 16384},
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    profiles = _profiles(monkeypatch, tmp_path)
    payload = {"model": "gemini-3-flash-preview", "messages": []}

    profile_id = profiles.apply_profile_body_patches(
        payload,
        protocol="anthropic_messages",
        profile_id="gemini-test",
        model_name="gemini-3-flash-preview",
        thinking_enabled=True,
        reasoning_effort="xhigh",
    )

    assert profile_id == "gemini-test"
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["thinkingConfig"]["thinkingBudget"] == 16384

    profiles.apply_profile_body_patches(
        payload,
        protocol="anthropic_messages",
        profile_id="gemini-test",
        model_name="gemini-3-flash-preview",
        thinking_enabled=False,
        reasoning_effort="xhigh",
    )
    assert payload["thinking"] == {"type": "disabled"}
    assert "thinkingBudget" not in payload.get("thinkingConfig", {})


def test_newapi_qwen_relay_uses_qwen_request_shape(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)
    payload = {"model": "qwen3.6-plus", "messages": []}

    profile_id = profiles.apply_profile_body_patches(
        payload,
        protocol="anthropic_messages",
        provider_id="newapi-personal-tokyo",
        base_url="https://newapi.example.test",
        model_name="qwen3.6-plus",
        thinking_enabled=True,
        reasoning_effort="high",
    )

    assert profile_id == "dashscope-openai"
    assert payload["thinking"] == {"type": "enabled"}


def test_review_launch_mimo_1m_adds_context_beta(monkeypatch):
    import httpx
    from mms_review_launch import _call_model_anthropic_messages

    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"content": [{"type": "text", "text": "Verdict: PASS"}]}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["json"] = json or {}
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    asyncio.run(
        _call_model_anthropic_messages(
            provider={
                "id": "mimo-direct-anthropic",
                "protocols": ["anthropic_messages"],
                "anthropic_base_url": "https://token-plan-cn.xiaomimimo.com/anthropic",
                "api_key": "test-key",
            },
            model_name="mimo-v2.5-pro[1m]",
            prompt="review this",
            max_tokens=1234,
        )
    )

    assert captured["url"] == "https://token-plan-cn.xiaomimimo.com/anthropic/v1/messages"
    assert captured["json"]["model"] == "mimo-v2.5-pro"
    assert "context-1m-2025-08-07" in captured["headers"]["anthropic-beta"]
