def _profiles(monkeypatch, tmp_path):
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    import mms_provider_profiles

    mms_provider_profiles.load_provider_profiles.cache_clear()
    return mms_provider_profiles


def test_mimo_anthropic_profile_uses_api_key_and_thinking_toggle(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)
    payload = {"model": "mimo-v2.5-pro", "messages": []}

    profile_id = profiles.apply_profile_body_patches(
        payload,
        protocol="anthropic_messages",
        provider_id="mimo-direct",
        base_url="https://api.xiaomimimo.com/anthropic",
        model_name="mimo-v2.5-pro",
        thinking_enabled=True,
        reasoning_effort="xhigh",
    )
    headers = {"Content-Type": "application/json"}
    profiles.apply_profile_auth_headers(
        headers,
        protocol="anthropic_messages",
        api_key="sk-mimo",
        provider_id="mimo-direct",
        base_url="https://api.xiaomimimo.com/anthropic",
        model_name="mimo-v2.5-pro",
    )

    assert profile_id == "mimo"
    assert payload["thinking"] == {"type": "enabled"}
    assert "output_config" not in payload
    assert headers["api-key"] == "sk-mimo"
    assert headers["Authorization"] == "Bearer sk-mimo"


def test_qwen_chat_template_profile_is_explicit_overlay_only(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)
    payload = {"model": "qwen3.5-coder", "messages": []}

    auto_id = profiles.apply_profile_body_patches(
        payload,
        protocol="openai_chat",
        base_url="http://127.0.0.1:8000/v1",
        model_name="qwen3.5-coder",
        thinking_enabled=True,
    )
    assert auto_id == ""
    assert "chat_template_kwargs" not in payload

    explicit_id = profiles.apply_profile_body_patches(
        payload,
        protocol="openai_chat",
        profile_id="qwen-chat-template",
        base_url="http://127.0.0.1:8000/v1",
        model_name="qwen3.5-coder",
        thinking_enabled=False,
    )
    assert explicit_id == "qwen-chat-template"
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}

    payload = {"model": "qwen3.5-coder", "messages": []}
    profiles.apply_profile_body_patches(
        payload,
        protocol="openai_chat",
        profile_id="qwen-chat-template",
        base_url="http://127.0.0.1:8000/v1",
        model_name="qwen3.5-coder",
    )
    assert payload["chat_template_kwargs"] == {"enable_thinking": True}


def test_deepseek_effort_maps_xhigh_to_max_and_disables_cleanly(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)
    payload = {
        "model": "deepseek-v4-pro",
        "messages": [],
        "thinking": {"type": "enabled"},
        "output_config": {"effort": "high", "format": "markdown"},
    }

    profile_id = profiles.apply_profile_body_patches(
        payload,
        protocol="anthropic_messages",
        provider_id="deepseek",
        base_url="https://api.deepseek.com/anthropic",
        model_name="deepseek-v4-pro",
        thinking_enabled=True,
        reasoning_effort="xhigh",
    )
    assert profile_id == "deepseek"
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["output_config"] == {"effort": "max", "format": "markdown"}

    profiles.apply_profile_body_patches(
        payload,
        protocol="anthropic_messages",
        provider_id="deepseek",
        base_url="https://api.deepseek.com/anthropic",
        model_name="deepseek-v4-pro",
        thinking_enabled=False,
        reasoning_effort="xhigh",
    )
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["output_config"] == {"format": "markdown"}


def test_profile_context_window_and_references(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)

    assert profiles.profile_context_window(
        "mimo-v2.5-pro",
        provider_id="mimo",
        base_url="https://api.xiaomimimo.com/anthropic",
    ) == 1_000_000
    assert profiles.profile_model_alias(
        "mimo-v2.5-pro",
        protocol="anthropic_messages",
        provider_id="mimo-direct-anthropic",
        base_url="https://token-plan-cn.xiaomimimo.com/anthropic",
    ) == "mimo-v2.5-pro[1m]"
    assert profiles.profile_model_alias(
        "mimo-v2.5",
        protocol="anthropic_messages",
        provider_id="mimo-direct-anthropic",
        base_url="https://token-plan-cn.xiaomimimo.com/anthropic",
    ) == "mimo-v2.5[1m]"
    assert profiles.profile_model_alias(
        "mimo-v2.5-pro",
        protocol="anthropic_messages",
        provider_id="newapi-personal-tokyo",
        base_url="http://161.33.197.51:4001",
    ) == ""
    refs = profiles.provider_profile_references()
    assert "https://platform.xiaomimimo.com/static/docs/api/chat/anthropic-api.md" in refs["mimo"]


def test_deepseek_context_and_wire_model_are_profile_driven(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)

    assert profiles.profile_context_window(
        "deepseek-v4-pro",
        provider_id="newapi-personal-tokyo",
    ) == 1_000_000
    assert profiles.profile_context_window(
        "deepseek-v4-flash",
        provider_id="newapi-personal-tokyo",
    ) == 1_000_000
    assert profiles.profile_model_alias(
        "deepseek-v4-pro",
        protocol="anthropic_messages",
        provider_id="newapi-personal-tokyo",
        base_url="http://161.33.197.51:4001",
    ) == ""
    assert profiles.profile_model_alias(
        "deepseek-v4-pro",
        protocol="anthropic_messages",
        provider_id="deepseek-direct",
        base_url="https://api.deepseek.com/anthropic",
    ) == "deepseek-v4-pro[1m]"
    assert profiles.profile_model_alias(
        "deepseek-v4-flash",
        protocol="anthropic_messages",
        provider_id="deepseek-direct",
        base_url="https://api.deepseek.com/anthropic",
    ) == ""


def test_kimi_k26_context_aliases_are_profile_driven(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)

    assert profiles.profile_context_window(
        "K2.6-code-preview",
        provider_id="kimi-code",
        base_url="https://api.kimi.com/coding/",
    ) == 262_144
    assert profiles.profile_context_window(
        "kimi-k2.6-code-preview",
        provider_id="kimi-code",
        base_url="https://api.kimi.com/coding/",
    ) == 262_144


def test_glm_capabilities_are_profile_driven(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)

    caps = profiles.profile_thinking_capabilities(
        "glm-4.6",
        provider_id="glm-direct",
        base_url="https://api.z.ai/api/anthropic",
    )
    payload = {"model": "glm-4.6", "messages": []}
    profile_id = profiles.apply_profile_body_patches(
        payload,
        protocol="anthropic_messages",
        provider_id="glm-direct",
        base_url="https://api.z.ai/api/anthropic",
        model_name="glm-4.6",
        thinking_enabled=False,
    )

    assert caps["profile"] == "glm"
    assert caps["thinking_supported"] is True
    assert caps["effort_supported"] is False
    assert profile_id == "glm"
    assert payload["thinking"] == {"type": "disabled"}
