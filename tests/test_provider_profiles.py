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
    ) == 1_000_000
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
    ) == 262_144
    assert profiles.profile_context_window(
        "mimo-v2.5-pro[1m]",
        provider_id="mimo",
        base_url="https://api.xiaomimimo.com/anthropic",
    ) == 1_000_000
    assert profiles.profile_context_window(
        "mimo-v2.5[1m]",
        provider_id="mimo",
        base_url="https://api.xiaomimimo.com/anthropic",
    ) == 1_000_000
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
    assert caps["effort_supported"] is False
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


def test_stable_root_without_latest_bundle_keeps_legacy_profile_overlay(monkeypatch, tmp_path):
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

    assert mms_provider_profiles.resolve_provider_profile(provider_id="stable-overlay-provider")[0] == "stable-legacy-overlay"
    assert mms_provider_profiles.profile_context_window("any-model", provider_id="stable-overlay-provider") == 54321
