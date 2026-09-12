def _profiles(monkeypatch, tmp_path):
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    import mms_provider_profiles

    mms_provider_profiles.load_provider_profiles.cache_clear()
    return mms_provider_profiles


def test_mimo_anthropic_profile_uses_api_key_and_thinking_toggle(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)
    payload = {"model": "mimo-v2.5-pro", "messages": [], "max_tokens": 4096}

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
    assert payload["max_tokens"] == 4096
    assert "max_completion_tokens" not in payload
    assert "output_config" not in payload
    assert headers["api-key"] == "sk-mimo"
    assert headers["Authorization"] == "Bearer sk-mimo"
    assert headers["User-Agent"] == profiles.DEFAULT_HTTP_USER_AGENT


def test_auth_headers_preserve_existing_user_agent(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)
    headers = {"User-Agent": "claude-cli/2.1.148"}

    profiles.apply_profile_auth_headers(
        headers,
        protocol="anthropic_messages",
        api_key="sk-test",
        provider_id="newapi-personal-tokyo",
        base_url="https://newapi.example/v1",
        model_name="kimi-k2.6",
    )

    assert headers["User-Agent"] == "claude-cli/2.1.148"


def test_mimo_openai_profile_uses_official_token_parameter(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)
    payload = {"model": "mimo-v2.5-pro", "messages": [], "max_tokens": 4096}

    profile_id = profiles.apply_profile_body_patches(
        payload,
        protocol="openai_chat",
        provider_id="mimo-direct",
        base_url="https://api.xiaomimimo.com/v1",
        model_name="mimo-v2.5-pro",
        thinking_enabled=True,
    )

    assert profile_id == "mimo-openai"
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["max_completion_tokens"] == 4096
    assert "max_tokens" not in payload


def test_mimo_relay_profile_resolution_prefers_protocol_specific_profile(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)

    anthropic_profile, _ = profiles.resolve_provider_profile(
        provider_id="xin",
        base_url="https://apple.clawopen.online",
        model_name="mimo-v2.5[1m]",
        protocol="anthropic_messages",
    )
    openai_profile, _ = profiles.resolve_provider_profile(
        provider_id="xin",
        base_url="https://apple.clawopen.online",
        model_name="mimo-v2.5[1m]",
        protocol="openai_chat",
    )

    assert anthropic_profile == "mimo"
    assert openai_profile == "mimo-openai"
    assert profiles.profile_context_window(
        "mimo-v2.5[1m]",
        provider_id="xin",
        base_url="https://apple.clawopen.online",
        protocol="anthropic_messages",
    ) == 1_048_576
    assert profiles.profile_model_alias(
        "mimo-v2.5[1m]",
        protocol="anthropic_messages",
        provider_id="xin",
        base_url="https://apple.clawopen.online",
    ) == "mimo-v2.5"


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


def test_deepseek_effort_passes_through_and_disables_cleanly(monkeypatch, tmp_path):
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
    assert payload["output_config"] == {"effort": "xhigh", "format": "markdown"}

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


def test_stepfun_effort_profile_patches_openai_and_messages(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)
    chat_payload = {"model": "step-3.7-flash", "messages": []}

    profile_id = profiles.apply_profile_body_patches(
        chat_payload,
        protocol="openai_chat",
        provider_id="stepfun",
        base_url="https://api.stepfun.com/v1",
        model_name="step-3.7-flash",
        thinking_enabled=True,
        reasoning_effort="xhigh",
    )

    assert profile_id == "stepfun"
    assert chat_payload["reasoning_effort"] == "high"

    default_payload = {"model": "step-3.7-flash", "messages": []}
    profiles.apply_profile_body_patches(
        default_payload,
        protocol="openai_chat",
        provider_id="stepfun",
        base_url="https://api.stepfun.com/v1",
        model_name="step-3.7-flash",
        thinking_enabled=True,
    )
    assert default_payload["reasoning_effort"] == "high"

    messages_payload = {
        "model": "step-router-v1",
        "messages": [],
        "output_config": {"format": "markdown"},
    }
    profile_id = profiles.apply_profile_body_patches(
        messages_payload,
        protocol="anthropic_messages",
        provider_id="stepfun",
        base_url="https://api.stepfun.com/step_plan",
        model_name="step-router-v1",
        thinking_enabled=True,
        reasoning_effort="medium",
    )

    assert profile_id == "stepfun"
    assert messages_payload["output_config"] == {
        "format": "markdown",
        "effort": "medium",
    }

    profiles.apply_profile_body_patches(
        messages_payload,
        protocol="anthropic_messages",
        provider_id="stepfun",
        base_url="https://api.stepfun.com/step_plan",
        model_name="step-router-v1",
        thinking_enabled=False,
        reasoning_effort="high",
    )
    assert messages_payload["output_config"] == {"format": "markdown"}

    caps = profiles.profile_thinking_capabilities(
        "step-3.7-flash",
        provider_id="stepfun",
        base_url="https://api.stepfun.com/v1",
    )
    assert caps["profile"] == "stepfun"
    assert caps["thinking_supported"] is True
    assert caps["effort_supported"] is True
    assert set(caps["effort_allowed"]) == {"low", "medium", "high"}
    assert caps["effort_default"] == "high"
    assert caps["effort_official_default"] == "medium"
    assert caps["effort_recommended_default"] == "high"
    assert caps["effort_map"]["xhigh"] == "high"
    assert profiles.profile_context_window(
        "step-3.7-flash",
        provider_id="stepfun",
        base_url="https://api.stepfun.com/v1",
    ) == 262_144

    headers = {"Content-Type": "application/json"}
    profiles.apply_profile_auth_headers(
        headers,
        protocol="anthropic_messages",
        api_key="sk-step",
        provider_id="stepfun",
        base_url="https://api.stepfun.com/step_plan",
        model_name="step-router-v1",
    )
    assert headers["Authorization"] == "Bearer sk-step"


def test_kimi_k27_profile_keeps_thinking_enabled_when_disabled_requested(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)
    payload = {"model": "kimi-k2.7-code", "messages": []}

    profile_id = profiles.apply_profile_body_patches(
        payload,
        protocol="anthropic_messages",
        provider_id="kimi",
        base_url="https://api.kimi.com/coding/",
        model_name="kimi-k2.7-code",
        thinking_enabled=False,
    )

    assert profile_id == "kimi-code"
    assert payload["thinking"] == {"type": "enabled"}


def test_kimi_k3_profile_uses_reasoning_effort_without_k2_thinking_patch(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)
    payload = {"model": "k3", "messages": [], "thinking": {"type": "enabled"}}

    profile_id = profiles.apply_profile_body_patches(
        payload,
        protocol="anthropic_messages",
        provider_id="kimi",
        base_url="https://api.kimi.com/coding/",
        model_name="k3",
        thinking_enabled=True,
        reasoning_effort="high",
    )

    assert profile_id == "kimi-code"
    assert profiles.resolve_provider_profile(provider_id="demo", model_name="k3")[0] == "kimi-code"
    assert payload["reasoning_effort"] == "max"
    assert "thinking" not in payload
    disabled_payload = {"model": "k3", "messages": [], "thinking": {"type": "disabled"}}
    profiles.apply_profile_body_patches(
        disabled_payload,
        protocol="anthropic_messages",
        provider_id="kimi",
        base_url="https://api.kimi.com/coding/",
        model_name="k3",
        thinking_enabled=False,
        reasoning_effort="low",
    )
    assert disabled_payload["reasoning_effort"] == "max"
    assert "thinking" not in disabled_payload
    assert profiles.profile_context_window(
        "k3",
        provider_id="kimi",
        base_url="https://api.kimi.com/coding/",
    ) == 1_048_576
    assert profiles.profile_context_window(
        "k3[1m]",
        provider_id="kimi",
        base_url="https://api.kimi.com/coding/",
    ) == 1_048_576
    assert profiles.profile_context_window(
        "kimi-k3",
        provider_id="kimi",
        base_url="https://api.kimi.com/coding/",
    ) == 1_048_576
    caps = profiles.profile_thinking_capabilities(
        "k3",
        provider_id="kimi",
        base_url="https://api.kimi.com/coding/",
    )
    assert caps["profile"] == "kimi-code"
    assert caps["thinking_supported"] is True
    assert caps["effort_allowed"] == ["max"]
    assert caps["effort_default"] == "max"
    assert caps["effort_map"]["high"] == "max"


def test_openrouter_kimi_k3_profile_aliases_to_moonshot_wire_model(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)
    payload = {"model": "k3", "messages": []}

    profile_id = profiles.apply_profile_body_patches(
        payload,
        protocol="openai_chat",
        provider_id="openrouter",
        base_url="https://openrouter.ai/api/v1",
        model_name="k3",
        thinking_enabled=True,
        reasoning_effort="low",
    )

    assert profile_id == "openrouter-moonshot-kimi-k3"
    assert payload["reasoning_effort"] == "max"
    assert profiles.profile_model_alias(
        "k3",
        protocol="openai_chat",
        provider_id="openrouter",
        base_url="https://openrouter.ai/api/v1",
    ) == "moonshotai/kimi-k3"
    assert profiles.profile_model_alias(
        "k3[1m]",
        protocol="openai_chat",
        provider_id="openrouter",
        base_url="https://openrouter.ai/api/v1",
    ) == "moonshotai/kimi-k3"
    assert profiles.profile_model_alias(
        "moonshotai/kimi-k3",
        protocol="openai_chat",
        provider_id="openrouter",
        base_url="https://openrouter.ai/api/v1",
    ) == "moonshotai/kimi-k3"
    assert profiles.profile_context_window(
        "moonshotai/kimi-k3",
        provider_id="openrouter",
        base_url="https://openrouter.ai/api/v1",
    ) == 1_048_576


def test_profile_context_window_and_references(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)

    # MiMo documents the `[1m]` suffix as what enables extended context on the
    # Anthropic endpoint, so the plain id there is the 256K mode.
    assert profiles.profile_context_window(
        "mimo-v2.5-pro",
        provider_id="mimo",
        base_url="https://api.xiaomimimo.com/anthropic",
    ) == 262_144
    assert profiles.profile_context_window(
        "mimo-v2.5-pro[1m]",
        provider_id="mimo",
        base_url="https://api.xiaomimimo.com/anthropic",
    ) == 1_048_576
    assert profiles.profile_context_window(
        "mimo-v2.5[1m]",
        provider_id="mimo",
        base_url="https://api.xiaomimimo.com/anthropic",
    ) == 1_048_576
    assert profiles.profile_context_window(
        "mimo-v2.5",
        provider_id="mimo-direct-openai",
        base_url="https://api.xiaomimimo.com/v1",
    ) == 1_048_576
    assert profiles.profile_context_window(
        "mimo-v2.5-pro",
        provider_id="openrouter",
        base_url="https://openrouter.ai/api/v1",
    ) == 1_048_576
    assert profiles.profile_model_alias(
        "mimo-v2.5-pro[1m]",
        protocol="anthropic_messages",
        provider_id="mimo-direct-anthropic",
        base_url="https://token-plan-cn.xiaomimimo.com/anthropic",
    ) == "mimo-v2.5-pro"
    assert profiles.profile_model_alias(
        "mimo-v2.5[1m]",
        protocol="anthropic_messages",
        provider_id="mimo-direct-anthropic",
        base_url="https://token-plan-cn.xiaomimimo.com/anthropic",
    ) == "mimo-v2.5"
    assert profiles.profile_model_alias(
        "mimo-v2.5",
        protocol="openai_chat",
        provider_id="openrouter",
        base_url="https://openrouter.ai/api/v1",
    ) == "xiaomi/mimo-v2.5"
    assert profiles.profile_model_alias(
        "mimo-v2.5-pro",
        protocol="anthropic_messages",
        provider_id="mimo-direct-anthropic",
        base_url="https://token-plan-cn.xiaomimimo.com/anthropic",
    ) == ""
    assert profiles.profile_model_alias(
        "mimo-v2.5",
        protocol="anthropic_messages",
        provider_id="mimo-direct-anthropic",
        base_url="https://token-plan-cn.xiaomimimo.com/anthropic",
    ) == ""
    assert profiles.profile_model_alias(
        "mimo-v2.5-pro",
        protocol="anthropic_messages",
        provider_id="newapi-personal-tokyo",
        base_url="http://161.33.197.51:4001",
    ) == ""
    refs = profiles.provider_profile_references()
    assert "https://platform.xiaomimimo.com/static/docs/api/chat/anthropic-api.md" in refs["mimo"]
    assert "https://platform.xiaomimimo.com/static/docs/usage-guide/passing-back-reasoning_content.md" in refs["mimo"]


def test_deepseek_context_and_wire_model_are_profile_driven(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)

    assert profiles.profile_context_window(
        "deepseek-v4-pro",
        provider_id="newapi-personal-tokyo",
    ) == 1_048_576
    assert profiles.profile_context_window(
        "deepseek-v4-flash",
        provider_id="newapi-personal-tokyo",
    ) == 1_048_576
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
        "K2.6",
        provider_id="newapi-personal-tokyo",
        base_url="https://newapi.evilsngx.ccwu.cc",
    ) == 262_144
    assert profiles.profile_context_window(
        "K2.6-code-preview",
        provider_id="newapi-personal-tokyo",
        base_url="https://newapi.evilsngx.ccwu.cc",
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
    assert caps["effort_supported"] is True
    assert profile_id == "glm"
    assert payload["thinking"] == {"type": "disabled"}


def test_empty_generated_provider_profile_does_not_shadow_gpt_capabilities(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)

    monkeypatch.setattr(
        profiles,
        "load_provider_profiles",
        lambda: {
            "profiles": {
                "openai": {
                    "match": {"model_prefixes": ["gpt-"]},
                    "thinking": {"supported": True, "default_enabled": True},
                    "effort": {
                        "responses": {
                            "path": "reasoning.effort",
                            "default": "medium",
                            "allowed": ["low", "medium", "high", "xhigh"],
                        }
                    },
                },
                "uscrsopenai": {
                    "name": "uscrsopenai",
                    "protocols": ["anthropic_messages", "openai_chat_completions"],
                    "supported_clis": ["claude", "codex", "opencode"],
                },
            }
        },
    )

    profile_id, _profile = profiles.resolve_provider_profile(
        provider_id="uscrsopenai",
        base_url="http://relay.example/openai",
        model_name="gpt-5.5",
    )
    caps = profiles.profile_thinking_capabilities(
        "gpt-5.5",
        provider_id="uscrsopenai",
        base_url="http://relay.example/openai",
    )

    assert profile_id == "openai"
    assert caps["profile"] == "openai"
    assert caps["thinking_supported"] is True
    assert caps["effort_supported"] is True


def test_gemini_opencode_policy_uses_shell_search_fallback(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)

    policy = profiles.profile_opencode_policy(
        "gemini-3-flash-agent(high)",
        provider_id="cpa-antigravity",
        base_url="http://161.33.197.51:4001/v1",
        protocol="anthropic_messages",
    )

    assert policy["profile"] == "cpa-antigravity-gemini"
    assert policy["builtin_search_tools"] == "fallback_only"
    assert policy["shell_search_fallback"] is True
    assert policy["strict_json_schema"] == "weak"


def test_generic_gemini_profile_does_not_force_opencode_search_fallback(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)

    policy = profiles.profile_opencode_policy(
        "gemini-3-flash-agent(high)",
        provider_id="gemini-direct",
        base_url="https://generativelanguage.googleapis.com",
        protocol="anthropic_messages",
    )

    assert policy == {}


def test_gemini_profile_keeps_3_level_and_25_numeric_budget(monkeypatch, tmp_path):
    profiles = _profiles(monkeypatch, tmp_path)

    gemini3_payload = {"model": "gemini-3.5-flash-low", "messages": []}
    gemini3_profile = profiles.apply_profile_body_patches(
        gemini3_payload,
        protocol="anthropic_messages",
        provider_id="gemini-direct",
        base_url="https://generativelanguage.googleapis.com",
        model_name="gemini-3.5-flash-low",
        thinking_enabled=True,
        reasoning_effort="low",
    )

    assert gemini3_profile == "gemini"
    assert gemini3_payload["thinkingConfig"]["thinkingLevel"] == "low"
    assert "thinkingBudget" not in gemini3_payload["thinkingConfig"]

    gemini25_payload = {"model": "gemini-2.5-pro", "messages": []}
    gemini25_profile = profiles.apply_profile_body_patches(
        gemini25_payload,
        protocol="anthropic_messages",
        provider_id="gemini-direct",
        base_url="https://generativelanguage.googleapis.com",
        model_name="gemini-2.5-pro",
        thinking_enabled=True,
        reasoning_effort="low",
    )

    assert gemini25_profile == "gemini"
    assert gemini25_payload["thinkingConfig"]["thinkingBudget"] == 2048
    assert isinstance(gemini25_payload["thinkingConfig"]["thinkingBudget"], int)
    assert "thinkingLevel" not in gemini25_payload["thinkingConfig"]


def test_preview_root_missing_latest_bundle_ignores_legacy_profile_overlay(monkeypatch, tmp_path):
    preview_root = tmp_path / "mms-next"
    preview_root.mkdir()
    (preview_root / "provider-profiles.json").write_text(
        """
        {
          "schema_version": 1,
            "profiles": {
              "preview-only-legacy-overlay": {
                "match": {"provider_id_contains": ["preview-only-provider"]},
              "context_windows": {"any": 12345}
              }
            }
          }
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))
    monkeypatch.delenv("MMS_CONFIG_DIR", raising=False)
    import mms_provider_profiles

    mms_provider_profiles.load_provider_profiles.cache_clear()

    assert mms_provider_profiles.resolve_provider_profile(provider_id="preview-only-provider")[0] == ""
    assert mms_provider_profiles.profile_context_window("any-model", provider_id="preview-only-provider") is None


def test_config_dir_root_missing_latest_bundle_ignores_legacy_profile_overlay(monkeypatch, tmp_path):
    selected_root = tmp_path / "selected-root"
    selected_root.mkdir()
    (selected_root / "provider-profiles.json").write_text(
        """
        {
          "schema_version": 1,
            "profiles": {
              "config-dir-legacy-overlay": {
                "match": {"provider_id_contains": ["config-dir-provider"]},
              "context_windows": {"any": 24680}
              }
            }
          }
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("MMS_CONFIG_DIR", str(selected_root))
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    import mms_provider_profiles

    mms_provider_profiles.load_provider_profiles.cache_clear()

    assert mms_provider_profiles.resolve_provider_profile(provider_id="config-dir-provider")[0] == ""
    assert mms_provider_profiles.profile_context_window("any-model", provider_id="config-dir-provider") is None


def test_legacy_root_without_latest_bundle_ignores_legacy_profile_overlay(monkeypatch, tmp_path):
    stable_root = tmp_path / "xdg" / "mms"
    stable_root.mkdir(parents=True)
    (stable_root / "provider-profiles.json").write_text(
        """
        {
          "schema_version": 1,
            "profiles": {
              "stable-legacy-overlay": {
                "match": {"provider_id_contains": ["stable-overlay-provider"]},
              "context_windows": {"any": 54321}
              }
            }
          }
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(stable_root.parent))
    monkeypatch.delenv("MMS_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.delenv("MMS_PREVIEW_MODE", raising=False)
    monkeypatch.delenv("MMS_COMMAND_NAME", raising=False)
    import mms_provider_profiles

    mms_provider_profiles.load_provider_profiles.cache_clear()

    assert mms_provider_profiles.resolve_provider_profile(provider_id="stable-overlay-provider")[0] == ""
    assert mms_provider_profiles.profile_context_window("any-model", provider_id="stable-overlay-provider") is None


def test_kimi_k3_aliases_agree_on_one_million_context(monkeypatch, tmp_path):
    """Every K3 alias must report the same window.

    K3 shipped 1M natively, but the value has been changed back and forth in the
    profile three times, each round leaving one alias behind. Pin the whole
    family so a partial edit fails here instead of downgrading a live channel.
    """
    profiles = _profiles(monkeypatch, tmp_path)

    for alias in ("k3", "k3[1m]", "kimi-k3"):
        assert profiles.profile_context_window(
            alias,
            provider_id="kimi",
            base_url="https://api.kimi.com/coding/",
        ) == 1_048_576, alias

    # The 256K variant is a separate official model, not a downgraded K3.
    assert profiles.profile_context_window(
        "k3-256k",
        provider_id="kimi",
        base_url="https://api.kimi.com/coding/",
    ) == 262_144


def test_profile_max_output_never_exceeds_its_context_window():
    """A max-output larger than the context window is always a data error.

    ``k3`` was raised to a 1M max output with no source behind it; that shape of
    mistake produces requests the upstream rejects, so catch it in the data.
    """
    import json
    from pathlib import Path

    profiles = json.loads(
        (Path(__file__).resolve().parent.parent / "config" / "provider-profiles.json").read_text(
            encoding="utf-8"
        )
    )["profiles"]

    offenders = []
    for profile_id, profile in profiles.items():
        windows = profile.get("context_windows") or {}
        outputs = profile.get("max_output_tokens") or {}
        for model, max_output in outputs.items():
            window = windows.get(model)
            if window is None:
                continue
            if int(max_output) > int(window):
                offenders.append(f"{profile_id}:{model} output={max_output} > context={window}")

    assert not offenders, "max_output_tokens exceeds context_window: " + "; ".join(offenders)


def _profile_declared_vision_models():
    """Every (profile, model) the profile data itself calls image-capable."""
    import json
    from pathlib import Path

    profiles = json.loads(
        (Path(__file__).resolve().parent.parent / "config" / "provider-profiles.json").read_text(
            encoding="utf-8"
        )
    )["profiles"]

    declared = []
    for profile_id, profile in profiles.items():
        names = set()
        for model, flag in (profile.get("supports_vision") or {}).items():
            if flag is True:
                names.add(model)
        for model, modalities in (profile.get("input_modalities") or {}).items():
            if isinstance(modalities, list) and "image" in modalities:
                names.add(model)
        for model in sorted(names):
            declared.append((profile_id, model))
    return declared


def test_vision_name_fallback_agrees_across_1m_aliases(monkeypatch, tmp_path):
    """`k3` and `k3[1m]` are one model, so the name fallback cannot split them.

    #204 dropped `k3[1m]` from `mms_core._VISION_CAPABLE_MODEL_NAMES` while the
    provider profile and Pi's hints kept calling it image-capable, so the
    last-resort name check answered False for one selector and True for the
    other one. The fallback only runs when nothing else declared the model, and
    that is exactly when a split answer becomes a wrong verdict.
    """
    _profiles(monkeypatch, tmp_path)
    import mms_core

    split = []
    for _profile_id, model in _profile_declared_vision_models():
        if not model.endswith("[1m]"):
            continue
        base = model[: -len("[1m]")]
        if mms_core._model_supports_vision(base) != mms_core._model_supports_vision(model):
            split.append(f"{base}={mms_core._model_supports_vision(base)} "
                         f"{model}={mms_core._model_supports_vision(model)}")

    assert not split, "a [1m] selector disagrees with its base model: " + "; ".join(split)

    for alias in ("k3", "k3[1m]", "kimi-k3"):
        assert mms_core._model_supports_vision(alias) is True, alias


def test_profile_vision_models_resolve_to_image_in_the_pi_chain(monkeypatch, tmp_path):
    """A profile that declares vision must survive the whole resolver chain.

    The single truth chain is resolver -> Pi input types; a model the curated
    data calls image-capable must not come out of `_pi_model_input_types` as
    text-only, whichever selector the user picked.
    """
    _profiles(monkeypatch, tmp_path)
    from mms_capability_resolver import resolve_model_capabilities
    import mms_pi_support

    disagreements = []
    for profile_id, model in _profile_declared_vision_models():
        caps = resolve_model_capabilities(
            model,
            profile_id=profile_id,
            approved_facts={},
            model_policy={},
        )
        types = mms_pi_support._pi_model_input_types(model, caps=caps)
        if caps.get("supports_vision") is not True or "image" not in types:
            disagreements.append(
                f"{profile_id}:{model} supports_vision={caps.get('supports_vision')} input={types}"
            )

    assert not disagreements, "profile says vision but the chain disagrees: " + "; ".join(disagreements)
