from __future__ import annotations

from mms_tui_launcher_flow import (
    apply_confirm_bypass_flag,
    apply_confirm_runtime_preferences,
    apply_tui_priority_changes,
    build_confirm_capability_context,
    confirm_agent_pack,
    confirm_tui_options,
    last_used_model_info,
    load_balance_slot_provider_ids,
    load_balance_tui_payload,
    normalize_confirm_result,
    official_account_profile_context,
    opencode_profile_launch_context,
    provider_browse_model_options,
    provider_browse_options,
    refresh_tui_runtime_state_after_config_change,
    resolve_load_balance_launch_context,
    resolve_last_used_launch_context,
    safe_tui_call,
    selected_model_launch_context,
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


def test_provider_browse_model_options_resolves_and_filters_models() -> None:
    cfg = {"cfg": True}
    provider = {"id": "p1"}
    calls = []

    def resolve_provider_context(arg_cfg, provider_id):
        calls.append(("resolve", arg_cfg, provider_id))
        return provider

    def probe_models(arg_provider, *, emit_output):
        calls.append(("probe", arg_provider, emit_output))
        return {"models": ["gpt-5.4", "hidden-model"]}

    def filter_visible_models(models):
        calls.append(("filter", models))
        return [model for model in models if model != "hidden-model"]

    selected_provider, models = provider_browse_model_options(
        cfg,
        "p1",
        resolve_provider_context=resolve_provider_context,
        probe_models=probe_models,
        filter_visible_models=filter_visible_models,
    )

    assert selected_provider is provider
    assert models == ["gpt-5.4"]
    assert calls == [
        ("resolve", cfg, "p1"),
        ("probe", provider, False),
        ("filter", ["gpt-5.4", "hidden-model"]),
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


def test_resolve_load_balance_launch_context_uses_heavy_slot_provider() -> None:
    trace_records = []
    trace_choices = []
    history_calls = []
    runtime = {"id": "heavy-provider"}

    model_info, selected_runtime, cli_name, error = resolve_load_balance_launch_context(
        {},
        "codex",
        {"model": "gpt-5.4", "lb_medium": "qwen3", "lb_light": "gpt-5-mini", "lb_label": "balanced"},
        {"id": "current"},
        ["gpt-5.4"],
        {"heavy": "provider-heavy"},
        trace_record=lambda *args, **kwargs: trace_records.append((args, kwargs)),
        save_lb_history=lambda *args, **kwargs: history_calls.append((args, kwargs)),
        resolve_lb_slot_provider=lambda *_args: (runtime, ""),
        resolve_best_provider=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        choose_runtime_source=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *args, **kwargs: trace_choices.append((args, kwargs)),
    )

    assert model_info["model"] == "gpt-5.4"
    assert selected_runtime is runtime
    assert cli_name == "codex"
    assert error == ""
    assert trace_records == [
        (
            ("load balance",),
            {
                "cli": "codex",
                "model": "gpt-5.4",
                "lb_medium": "qwen3",
                "lb_light": "gpt-5-mini",
                "profile": None,
            },
        )
    ]
    assert history_calls == [
        (
            ("gpt-5.4", "qwen3", "gpt-5-mini"),
            {"slot_providers": {"heavy": "provider-heavy"}, "label": "balanced"},
        )
    ]
    assert trace_choices == [
        (("runtime resolve", runtime), {"launch_cli": "codex", "choice": "profile provider:provider-heavy"})
    ]


def test_resolve_load_balance_launch_context_returns_slot_error() -> None:
    model_info, runtime, cli_name, error = resolve_load_balance_launch_context(
        {},
        "codex",
        {"model": "gpt-5.4"},
        {},
        [],
        {"heavy": "missing"},
        trace_record=lambda *_args, **_kwargs: None,
        save_lb_history=lambda *_args, **_kwargs: None,
        resolve_lb_slot_provider=lambda *_args: (None, "missing provider"),
        resolve_best_provider=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        choose_runtime_source=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert model_info == {"model": "gpt-5.4"}
    assert runtime is None
    assert cli_name == "codex"
    assert error == "missing provider"


def test_resolve_load_balance_launch_context_uses_best_provider_or_picker() -> None:
    best_runtime = {"id": "best"}
    trace_choices = []

    model_info, runtime, cli_name, error = resolve_load_balance_launch_context(
        {"cfg": True},
        "claude",
        {"model": "claude-sonnet-4.5"},
        {"id": "current"},
        ["claude-sonnet-4.5"],
        {},
        trace_record=lambda *_args, **_kwargs: None,
        save_lb_history=lambda *_args, **_kwargs: None,
        resolve_lb_slot_provider=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        resolve_best_provider=lambda *_args, **_kwargs: (best_runtime, None),
        choose_runtime_source=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *args, **kwargs: trace_choices.append((args, kwargs)),
    )

    assert model_info == {"model": "claude-sonnet-4.5"}
    assert runtime is best_runtime
    assert cli_name == "claude"
    assert error == ""
    assert trace_choices == [
        (("runtime resolve", best_runtime), {"launch_cli": "claude", "choice": "best provider"})
    ]

    chosen_runtime = {"id": "chosen"}
    model_info, runtime, cli_name, error = resolve_load_balance_launch_context(
        {},
        "codex",
        {"model": "gpt-5.4"},
        {"id": "current"},
        ["gpt-5.4"],
        {},
        account_id="acct",
        provider_id="prov",
        trace_record=lambda *_args, **_kwargs: None,
        save_lb_history=lambda *_args, **_kwargs: None,
        resolve_lb_slot_provider=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        resolve_best_provider=lambda *_args, **_kwargs: (None, None),
        choose_runtime_source=lambda *_args, **_kwargs: (chosen_runtime, ["gpt-5.4"], "opencode"),
        trace_runtime_choice=lambda *_args, **_kwargs: None,
    )

    assert model_info == {"model": "gpt-5.4"}
    assert runtime is chosen_runtime
    assert cli_name == "opencode"
    assert error == ""


def test_last_used_model_info_preserves_dict_model_info() -> None:
    model_info = {"model": "gpt-5.4", "provider": "p1"}
    assert last_used_model_info({"model": "fallback", "model_info": model_info}) is model_info


def test_last_used_model_info_falls_back_to_model_name() -> None:
    assert last_used_model_info({"model": "gpt-5.4", "model_info": "bad"}) == {"model": "gpt-5.4"}


def test_resolve_last_used_launch_context_uses_restored_runtime() -> None:
    trace_calls = []
    restored_runtime = {"id": "restored"}

    model_info, runtime, cli_name = resolve_last_used_launch_context(
        {"cfg": True},
        "codex",
        {"model": "gpt-5.4"},
        {"id": "current"},
        ["gpt-5.4"],
        resolve_last_used_runtime=lambda *_args: (restored_runtime, ["gpt-5.4"], "last used provider:p1"),
        resolve_best_provider=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        choose_runtime_source=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *args, **kwargs: trace_calls.append((args, kwargs)),
    )

    assert model_info == {"model": "gpt-5.4"}
    assert runtime is restored_runtime
    assert cli_name == "codex"
    assert trace_calls == [
        (("runtime resolve", restored_runtime), {"launch_cli": "codex", "choice": "last used provider:p1"})
    ]


def test_resolve_last_used_launch_context_uses_best_provider_before_picker() -> None:
    trace_calls = []
    best_runtime = {"id": "best"}

    model_info, runtime, cli_name = resolve_last_used_launch_context(
        {},
        "claude",
        {"model": "claude-sonnet-4.5", "model_info": {"model": "claude-sonnet-4.5", "source": "last"}},
        {"id": "current"},
        ["claude-sonnet-4.5"],
        resolve_last_used_runtime=lambda *_args: (None, [], ""),
        resolve_best_provider=lambda *_args, **_kwargs: (best_runtime, None),
        choose_runtime_source=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *args, **kwargs: trace_calls.append((args, kwargs)),
    )

    assert model_info == {"model": "claude-sonnet-4.5", "source": "last"}
    assert runtime is best_runtime
    assert cli_name == "claude"
    assert trace_calls == [
        (("runtime resolve", best_runtime), {"launch_cli": "claude", "choice": "best provider"})
    ]


def test_resolve_last_used_launch_context_falls_back_to_runtime_picker() -> None:
    choose_calls = []

    def choose_runtime_source(*args, **kwargs):
        choose_calls.append((args, kwargs))
        return {"id": "chosen"}, ["gpt-5.4"], "opencode"

    model_info, runtime, cli_name = resolve_last_used_launch_context(
        {"cfg": True},
        "codex",
        {"model": "gpt-5.4"},
        {"id": "current"},
        ["gpt-5.4"],
        account_id="acct",
        provider_id="prov",
        resolve_last_used_runtime=lambda *_args: (None, [], ""),
        resolve_best_provider=lambda *_args, **_kwargs: (None, None),
        choose_runtime_source=choose_runtime_source,
        trace_runtime_choice=lambda *_args, **_kwargs: None,
    )

    assert model_info == {"model": "gpt-5.4"}
    assert runtime == {"id": "chosen"}
    assert cli_name == "opencode"
    assert choose_calls == [
        (
            ({"cfg": True}, "codex", {"id": "current"}, ["gpt-5.4"]),
            {
                "account_id": "acct",
                "provider_id": "prov",
                "model_info": {"model": "gpt-5.4"},
                "allow_selected_model_accounts": True,
            },
        )
    ]


def test_selected_model_launch_context_uses_embedded_provider_context() -> None:
    trace_calls = []
    provider_ctx = {"id": "embedded"}

    model_info, runtime = selected_model_launch_context(
        {},
        "codex",
        {"model": "gpt-5.4", "provider_ctx": provider_ctx},
        {"id": "current"},
        ["gpt-5.4"],
        resolve_best_provider=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *args, **kwargs: trace_calls.append((args, kwargs)),
    )

    assert model_info == {"model": "gpt-5.4"}
    assert runtime is provider_ctx
    assert trace_calls == [
        (("runtime resolve", provider_ctx), {"launch_cli": "codex", "choice": "best provider"})
    ]


def test_selected_model_launch_context_falls_back_to_best_provider() -> None:
    trace_calls = []
    best_provider = {"id": "best"}

    model_info, runtime = selected_model_launch_context(
        {"cfg": True},
        "claude",
        {"model": "claude-sonnet-4.5"},
        {"id": "current"},
        ["claude-sonnet-4.5"],
        resolve_best_provider=lambda *_args, **_kwargs: (best_provider, None),
        trace_runtime_choice=lambda *args, **kwargs: trace_calls.append((args, kwargs)),
    )

    assert model_info == {"model": "claude-sonnet-4.5"}
    assert runtime is best_provider
    assert trace_calls == [
        (("runtime resolve", best_provider), {"launch_cli": "claude", "choice": "best provider"})
    ]


def test_opencode_profile_launch_context_traces_resolved_runtime() -> None:
    trace_records = []
    trace_choices = []
    runtime = {"id": "provider", "opencode_profile": "agent"}

    model_info, selected_runtime = opencode_profile_launch_context(
        {"cfg": True},
        {"id": "current"},
        ["gpt-5.4"],
        "agent",
        resolve_opencode_profile_runtime=lambda *_args: ({"model": "gpt-5.4"}, runtime),
        trace_record=lambda *args, **kwargs: trace_records.append((args, kwargs)),
        trace_runtime_choice=lambda *args, **kwargs: trace_choices.append((args, kwargs)),
    )

    assert model_info == {"model": "gpt-5.4"}
    assert selected_runtime is runtime
    assert trace_records == [
        (
            ("opencode profile",),
            {"cli": "opencode", "profile": "agent", "model": "gpt-5.4", "provider": "provider"},
        )
    ]
    assert trace_choices == [
        (("runtime resolve", runtime), {"launch_cli": "opencode", "choice": "opencode profile"})
    ]


def test_opencode_profile_launch_context_keeps_unresolved_result_untraced() -> None:
    model_info, runtime = opencode_profile_launch_context(
        {},
        {},
        [],
        "raw",
        resolve_opencode_profile_runtime=lambda *_args: (None, None),
        trace_record=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert model_info is None
    assert runtime is None


def test_official_account_profile_context_traces_matching_account() -> None:
    trace_records = []
    trace_choices = []
    runtime = {"id": "agy-main", "cli": "agy"}

    model_info, selected_runtime = official_account_profile_context(
        {},
        "agy",
        "agy-main",
        resolve_account_context=lambda *_args, **_kwargs: runtime,
        trace_record=lambda *args, **kwargs: trace_records.append((args, kwargs)),
        trace_runtime_choice=lambda *args, **kwargs: trace_choices.append((args, kwargs)),
    )

    assert model_info == {}
    assert selected_runtime is runtime
    assert trace_records == [(("official account",), {"cli": "agy", "account": "agy-main"})]
    assert trace_choices == [(("runtime resolve", runtime), {"launch_cli": "agy", "choice": "official account"})]


def test_official_account_profile_context_rejects_wrong_cli() -> None:
    model_info, runtime = official_account_profile_context(
        {},
        "agy",
        "wrong",
        resolve_account_context=lambda *_args, **_kwargs: {"id": "gemini-old", "cli": "gemini"},
        trace_record=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert model_info == {}
    assert runtime is None


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


def test_apply_tui_priority_changes_saves_then_exports() -> None:
    calls = []

    def export_model_routes(cfg, *, force):
        calls.append(("export", cfg, force))

    changed = apply_tui_priority_changes(
        {"cfg": True},
        [{"id": "p1"}],
        apply_runtime_priority_changes=lambda cfg, changes: calls.append(("apply", cfg, changes)) or True,
        save_config=lambda cfg: calls.append(("save", cfg)),
        export_model_routes_loader=lambda: export_model_routes,
    )

    assert changed is True
    assert calls == [
        ("apply", {"cfg": True}, [{"id": "p1"}]),
        ("save", {"cfg": True}),
        ("export", {"cfg": True}, True),
    ]


def test_apply_tui_priority_changes_ignores_export_failure() -> None:
    calls = []

    def load_export_model_routes():
        raise RuntimeError("export unavailable")

    changed = apply_tui_priority_changes(
        {},
        ["change"],
        apply_runtime_priority_changes=lambda *_args: True,
        save_config=lambda cfg: calls.append(("save", cfg)),
        export_model_routes_loader=load_export_model_routes,
    )

    assert changed is True
    assert calls == [("save", {})]


def test_apply_tui_priority_changes_skips_save_without_changes() -> None:
    calls = []

    changed = apply_tui_priority_changes(
        {},
        None,
        apply_runtime_priority_changes=lambda *_args: False,
        save_config=lambda cfg: calls.append(("save", cfg)),
        export_model_routes_loader=lambda: calls.append(("load_export",)),
    )

    assert changed is False
    assert calls == []


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


def test_apply_confirm_runtime_preferences_sets_claude_modes() -> None:
    runtime = {"disabled_session_surfaces": {"old": True}}
    apply_confirm_runtime_preferences(
        runtime,
        "claude",
        claude_1m_enabled=True,
        caveman_enabled=True,
        agent_pack="omc",
        thinking_enabled=False,
        reasoning_effort="LOW",
        disabled_session_surfaces={"xmem": True},
        nsr_enabled=True,
        has_nsr=True,
        confirm_returned_surfaces=True,
        merge_disabled_session_surfaces=lambda *_args: {"unexpected": True},
    )

    assert runtime == {
        "claude_1m_mode": "enable",
        "agent_pack": "omc",
        "ecc_mode": "disable",
        "omc_mode": "enable",
        "caveman_mode": "enable",
        "nsr_mode": "enable",
        "disabled_session_surfaces": {"xmem": True},
        "thinking_mode": "disable",
        "reasoning_effort": "low",
    }


def test_apply_confirm_runtime_preferences_merges_legacy_surfaces() -> None:
    runtime = {"disabled_session_surfaces": {"context": True}}
    merge_calls = []

    def merge_disabled_session_surfaces(existing, incoming):
        merge_calls.append((existing, incoming))
        return {"context": True, "toon": True}

    apply_confirm_runtime_preferences(
        runtime,
        "codex",
        claude_1m_enabled=False,
        caveman_enabled=False,
        agent_pack="ecc",
        thinking_enabled=True,
        reasoning_effort="",
        disabled_session_surfaces={"toon": True},
        nsr_enabled=True,
        has_nsr=False,
        confirm_returned_surfaces=False,
        merge_disabled_session_surfaces=merge_disabled_session_surfaces,
    )

    assert runtime == {
        "disabled_session_surfaces": {"context": True, "toon": True},
        "caveman_mode": "disable",
        "nsr_mode": "disable",
        "thinking_mode": "enable",
        "reasoning_effort": "high",
    }
    assert merge_calls == [({"context": True}, {"toon": True})]


def test_build_confirm_capability_context_enables_domestic_claude_addons() -> None:
    runtime = {"reasoning_effort": "LOW"}
    clean_model_info = {"model": "qwen3-max"}
    preview_calls = []

    def build_preview(cli_name, runtime_arg, **kwargs):
        preview_calls.append((cli_name, runtime_arg, kwargs))
        return {"preview": kwargs}

    context = build_confirm_capability_context(
        "claude",
        runtime,
        clean_model_info,
        confirm_context_lines=lambda cli_name, runtime_arg: [cli_name, runtime_arg["reasoning_effort"]],
        caveman_available_for_cli=lambda cli_name: cli_name == "claude",
        nsr_available_for_cli=lambda cli_name: cli_name == "claude",
        ecc_available_for_claude=lambda: True,
        omc_available_for_claude=lambda: True,
        model_info_looks_domestic=lambda model_info: model_info is clean_model_info,
        default_reasoning_effort_for_model_info=lambda _model_info: "high",
        build_confirm_preview_catalog=build_preview,
    )

    assert context == {
        "context_lines": ["claude", "LOW"],
        "has_caveman": True,
        "has_nsr": True,
        "has_ecc": True,
        "has_omc": True,
        "default_reasoning_effort": "low",
        "preview_catalog": {
            "preview": {
                "has_caveman": True,
                "has_nsr": True,
                "has_ecc": True,
                "has_omc": True,
            }
        },
    }
    assert preview_calls[0][1] is runtime


def test_build_confirm_capability_context_blocks_non_claude_addons() -> None:
    context = build_confirm_capability_context(
        "codex",
        {},
        {"model": "gpt-5.4"},
        confirm_context_lines=lambda *_args: [],
        caveman_available_for_cli=lambda _cli_name: False,
        nsr_available_for_cli=lambda _cli_name: True,
        ecc_available_for_claude=lambda: True,
        omc_available_for_claude=lambda: True,
        model_info_looks_domestic=lambda _model_info: True,
        default_reasoning_effort_for_model_info=lambda _model_info: "medium",
        build_confirm_preview_catalog=lambda *_args, **kwargs: kwargs,
    )

    assert context["has_ecc"] is False
    assert context["has_omc"] is False
    assert context["has_nsr"] is True
    assert context["default_reasoning_effort"] == "medium"


def test_confirm_tui_options_preserves_confirm_defaults() -> None:
    runtime = {
        "caveman_mode": "disable",
        "nsr_mode": "enable",
        "agent_pack": "omc",
        "thinking_mode": "disable",
    }

    assert confirm_tui_options(
        env_vars={"A": "B"},
        once=True,
        context_lines=["ctx"],
        has_caveman=True,
        has_nsr=True,
        has_ecc=False,
        has_omc=True,
        runtime=runtime,
        default_reasoning_effort="medium",
        preview_catalog={"preview": True},
    ) == {
        "env_vars": {"A": "B"},
        "once": True,
        "context_lines": ["ctx"],
        "has_caveman": True,
        "caveman_enabled_default": False,
        "has_nsr": True,
        "nsr_enabled_default": True,
        "has_ecc": False,
        "ecc_enabled_default": False,
        "has_omc": True,
        "agent_pack_default": "omc",
        "thinking_enabled_default": False,
        "reasoning_effort_default": "medium",
        "preview_catalog": {"preview": True},
        "runtime": runtime,
    }


def test_apply_confirm_bypass_flag_only_for_launch_clis() -> None:
    runtime = {}
    apply_confirm_bypass_flag(runtime, "codex", True)
    assert runtime == {"bypass": True}

    runtime = {}
    apply_confirm_bypass_flag(runtime, "chat", True)
    assert runtime == {}
