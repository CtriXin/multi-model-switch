from __future__ import annotations

from mms_tui_launcher_flow import (
    load_balance_slot_provider_ids,
    load_balance_tui_payload,
    provider_browse_options,
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
