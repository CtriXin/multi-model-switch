from __future__ import annotations

from mms_tui_launcher_flow import (
    confirm_agent_pack,
    last_used_model_info,
    load_balance_slot_provider_ids,
    load_balance_tui_payload,
    normalize_confirm_result,
    provider_browse_options,
    refresh_tui_runtime_state_after_config_change,
    safe_tui_call,
)


def test_provider_browse_options_filters_and_dedupes_candidates() -> None:
    provider = {"id": "current"}
    default_models = ["gpt-5.4"]
    candidates = [
        (
            {
                "id": "p1",
                "name": "Provider One",
                "api_key": "k",
                "role": "primary",
                "priority": 300,
                "supported_clis": ["codex"],
            },
            False,
        ),
        (
            {"id": "p1", "name": "Provider One Duplicate", "api_key": "k", "supported_clis": ["codex"]},
            False,
        ),
        (
            {
                "id": "disabled",
                "name": "Disabled",
                "api_key": "k",
                "enabled": False,
                "supported_clis": ["codex"],
            },
            False,
        ),
        ({"id": "no-key", "name": "No Key", "supported_clis": ["codex"]}, False),
        (
            {"id": "claude-only", "name": "Claude Only", "api_key": "k", "supported_clis": ["claude"]},
            False,
        ),
        ({"name": "Default Provider", "api_key": "k", "supported_clis": ["codex"]}, False),
    ]

    def provider_candidates(cfg, current_provider, models):
        assert cfg == {"cfg": True}
        assert current_provider is provider
        assert models is default_models
        return candidates

    result = provider_browse_options(
        {"cfg": True},
        provider,
        default_models,
        "codex",
        provider_candidates=provider_candidates,
        default_provider_id="default",
        provider_supports_cli_name=lambda item, cli: cli in item.get("supported_clis", []),
        provider_label=lambda item: item.get("name") or item.get("id"),
    )

    assert result == [
        {"id": "p1", "name": "Provider One", "role": "primary", "priority": 300},
        {"id": "default", "name": "Default Provider", "role": "auto", "priority": 100},
    ]


def test_safe_tui_call_normalizes_keyboard_interrupt() -> None:
    def raises_keyboard_interrupt():
        raise KeyboardInterrupt

    assert safe_tui_call(raises_keyboard_interrupt) == "__interrupt__"


def test_safe_tui_call_returns_function_result() -> None:
    assert safe_tui_call(lambda left, right=None: (left, right), "a", right="b") == ("a", "b")


def test_load_balance_tui_payload_preserves_models_and_provider_options() -> None:
    cfg = {"load_balance": True}
    provider = {"id": "p1"}
    default_models = ["gpt-5.4"]
    families_detail = {
        "codex": {
            "GPT": [{"model": "gpt-5.4"}, {"model": "gpt-5.5"}],
            "Qwen": [{"model": "qwen3"}],
        },
        "claude": {"Claude": [{"model": "claude-sonnet-4.5"}]},
    }

    def build_provider_options_map(arg_cfg, cli_name, current_provider, models, all_models):
        assert arg_cfg is cfg
        assert cli_name == "codex"
        assert current_provider is provider
        assert models is default_models
        return {"models": list(all_models)}

    all_models, cli_families, profiles, default_profile, provider_options = load_balance_tui_payload(
        cfg,
        "codex",
        provider,
        default_models,
        families_detail,
        load_balance_profiles=lambda arg_cfg: {"balanced": {} if arg_cfg is cfg else {"wrong": True}},
        default_load_balance_profile_name=lambda arg_cfg: "balanced" if arg_cfg is cfg else "wrong",
        build_provider_options_map=build_provider_options_map,
    )

    assert all_models == ["gpt-5.4", "gpt-5.5", "qwen3"]
    assert cli_families is families_detail["codex"]
    assert profiles == {"balanced": {}}
    assert default_profile == "balanced"
    assert provider_options == {"models": ["gpt-5.4", "gpt-5.5", "qwen3"]}


def test_load_balance_tui_payload_skips_provider_options_without_models() -> None:
    calls = []

    result = load_balance_tui_payload(
        {},
        "codex",
        {},
        [],
        {"codex": {}},
        load_balance_profiles=lambda _cfg: {},
        default_load_balance_profile_name=lambda _cfg: "",
        build_provider_options_map=lambda *_args: calls.append(True),
    )

    assert result == ([], {}, {}, "", None)
    assert calls == []


def test_load_balance_slot_provider_ids_drops_empty_slots() -> None:
    assert load_balance_slot_provider_ids(
        {
            "lb_slot_providers": {
                "heavy": "provider-heavy",
                "medium": "",
                "light": None,
            }
        }
    ) == {"heavy": "provider-heavy"}


def test_last_used_model_info_preserves_dict_model_info() -> None:
    model_info = {"model": "gpt-5.4", "provider": "p1"}
    assert last_used_model_info({"model": "fallback", "model_info": model_info}) is model_info


def test_last_used_model_info_falls_back_to_model_name() -> None:
    assert last_used_model_info({"model": "gpt-5.4", "model_info": "bad"}) == {"model": "gpt-5.4"}


def test_refresh_tui_runtime_state_after_config_change_clears_and_rebuilds() -> None:
    calls = []

    class FakeProbeCache:
        def clear(self):
            calls.append(("clear",))

    def fake_rmtree(path, *, ignore_errors):
        calls.append(("rmtree", path, ignore_errors))

    def fake_ensure_provider_credentials(cfg):
        calls.append(("ensure", cfg))
        return {"id": "provider"}

    def fake_probe_models(provider, *, emit_output):
        calls.append(("probe", provider, emit_output))
        return {"models": ["gpt-5.4"]}

    def fake_resolve_visible_clis(cfg, provider, models):
        calls.append(("visible", cfg, provider, models))
        return ["codex"]

    provider, models, clis = refresh_tui_runtime_state_after_config_change(
        {"cfg": True},
        probe_cache=FakeProbeCache(),
        probe_file_cache_dir="/tmp/probe-cache",
        rmtree=fake_rmtree,
        ensure_provider_credentials=fake_ensure_provider_credentials,
        probe_models=fake_probe_models,
        resolve_visible_clis=fake_resolve_visible_clis,
    )

    assert provider == {"id": "provider"}
    assert models == ["gpt-5.4"]
    assert clis == ["codex"]
    assert calls == [
        ("clear",),
        ("rmtree", "/tmp/probe-cache", True),
        ("ensure", {"cfg": True}),
        ("probe", {"id": "provider"}, False),
        ("visible", {"cfg": True}, {"id": "provider"}, ["gpt-5.4"]),
    ]


def test_confirm_agent_pack_accepts_new_and_legacy_values() -> None:
    assert confirm_agent_pack("OMC") == "omc"
    assert confirm_agent_pack("none") == "none"
    assert confirm_agent_pack(True) == "ecc"
    assert confirm_agent_pack(False) == "none"


def test_normalize_confirm_result_supports_current_tuple_shape() -> None:
    surfaces = {"xmem": True}
    result = normalize_confirm_result(
        ("", True, True, False, "omc", False, "medium", surfaces, True),
        "high",
    )

    assert result == {
        "action": "",
        "bypass": True,
        "claude_1m_enabled": True,
        "caveman_enabled": False,
        "agent_pack": "omc",
        "thinking_enabled": False,
        "reasoning_effort": "medium",
        "disabled_session_surfaces": surfaces,
        "nsr_enabled": True,
        "confirm_returned_surfaces": True,
    }


def test_normalize_confirm_result_supports_legacy_tuple_shapes() -> None:
    assert normalize_confirm_result(("s", True, False, True, True), "high") == {
        "action": "s",
        "bypass": True,
        "claude_1m_enabled": False,
        "caveman_enabled": True,
        "agent_pack": "ecc",
        "thinking_enabled": True,
        "reasoning_effort": "high",
        "disabled_session_surfaces": {},
        "nsr_enabled": False,
        "confirm_returned_surfaces": False,
    }
    assert normalize_confirm_result(("b", False, True), "low")["caveman_enabled"] is False
    assert normalize_confirm_result("q", "medium")["action"] == "q"
