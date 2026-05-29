from __future__ import annotations

from datetime import datetime, timezone

from mms_tui import _sort_cli_names_by_last_used, _sort_model_entries_for_tui
from mms_core import _sort_family_entries_for_tui
from mms_tui_launcher_flow import TuiFamilyPayloadDeps, build_tui_family_payloads


NOW = datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc)


def test_cli_tabs_start_with_most_recently_used_cli() -> None:
    ordered = _sort_cli_names_by_last_used(
        ["claude", "codex", "opencode"],
        {
            "claude": {"last_used_at": "2026-05-01T00:00:00Z"},
            "codex": {"last_used_at": "2026-05-22T11:55:00Z"},
        },
        now=NOW,
    )

    assert ordered == ["codex", "claude", "opencode"]


def test_cli_tabs_keep_original_order_when_no_recent_usage() -> None:
    assert _sort_cli_names_by_last_used(["claude", "codex", "opencode"], {}, now=NOW) == [
        "claude",
        "codex",
        "opencode",
    ]


def test_model_sort_uses_last_used_only_before_name() -> None:
    models = [
        {"model": "gpt-5.4", "use_count": 900, "last_used_at": "2026-02-22T12:00:00Z"},
        {"model": "gpt-5.5", "use_count": 2, "last_used_at": "2026-05-22T06:00:00Z"},
        {"model": "gpt-never-used", "use_count": 1200},
    ]

    sorted_names = [item["model"] for item in _sort_model_entries_for_tui(models, "GPT", now=NOW)]

    assert sorted_names == ["gpt-5.5", "gpt-5.4", "gpt-never-used"]


def test_model_sort_falls_back_to_name_without_recency() -> None:
    models = [
        {"model": "qwen-b", "use_count": 1},
        {"model": "qwen-a", "use_count": 3},
        {"model": "qwen-c", "use_count": 3},
    ]

    sorted_names = [item["model"] for item in _sort_model_entries_for_tui(models, "Qwen", now=NOW)]

    assert sorted_names == ["qwen-a", "qwen-b", "qwen-c"]


def test_family_sort_uses_last_used_before_default_family() -> None:
    families = [
        {"family": "GPT", "use_count": 900, "last_used_at": "2026-02-22T12:00:00Z"},
        {"family": "Qwen", "use_count": 2, "last_used_at": "2026-05-22T06:00:00Z"},
        {"family": "Claude", "use_count": 1200},
    ]

    sorted_names = [
        item["family"]
        for item in _sort_family_entries_for_tui(
            families,
            preferred_family="GPT",
            now=NOW,
        )
    ]

    assert sorted_names == ["Qwen", "GPT", "Claude"]


def test_family_sort_keeps_cli_default_first_when_no_recency() -> None:
    families = [
        {"family": "Qwen", "use_count": 10},
        {"family": "GPT", "use_count": 1},
        {"family": "Claude", "use_count": 20},
    ]

    sorted_names = [
        item["family"]
        for item in _sort_family_entries_for_tui(
            families,
            preferred_family="GPT",
            now=NOW,
        )
    ]

    assert sorted_names == ["GPT", "Claude", "Qwen"]


def test_build_tui_family_payloads_preserves_family_metadata() -> None:
    provider = {"id": "p1"}
    default_models = ["gpt-5.4"]
    cold_calls = []

    def build_model_families_for_cli(cfg, cli_name, current_provider, models):
        assert cfg == {"cfg": True}
        assert cli_name == "codex"
        assert current_provider is provider
        assert models is default_models
        return [
            {
                "family": "GPT",
                "models": [
                    {"model": "gpt-5.4", "use_count": 2, "last_used_at": "2026-05-20T10:00:00Z"},
                    {"model": "gpt-5.5", "use_count": "3", "last_used_at": "2026-05-21T10:00:00Z"},
                ],
            },
            {
                "family": "Qwen",
                "models": [
                    {"model": "qwen3"},
                    "raw-model-entry",
                ],
            },
        ]

    def family_is_cold_for_tui(family, total_use, last_used_at, *, preferred_family):
        cold_calls.append((family, total_use, last_used_at, preferred_family))
        return family == "Qwen"

    def sort_family_entries_for_tui(families, *, preferred_family):
        assert preferred_family == "GPT"
        return sorted(families, key=lambda item: item["family"])

    def make_provider_options_loader(cfg, cli_name, current_provider, models):
        return lambda model_name: [cfg, cli_name, current_provider, models, model_name]

    families_by_cli, families_detail, provider_options_by_cli, loaders = build_tui_family_payloads(
        {"cfg": True},
        ["codex"],
        provider,
        default_models,
        deps=TuiFamilyPayloadDeps(
            build_model_families_for_cli=build_model_families_for_cli,
            cli_default_family_first={"codex": "GPT"},
            family_is_cold_for_tui=family_is_cold_for_tui,
            sort_family_entries_for_tui=sort_family_entries_for_tui,
            make_provider_options_loader=make_provider_options_loader,
        ),
    )

    assert families_by_cli["codex"] == [
        {
            "family": "GPT",
            "count": 2,
            "use_count": 5,
            "last_used_at": "2026-05-21T10:00:00Z",
            "is_cold": False,
        },
        {
            "family": "Qwen",
            "count": 2,
            "use_count": 0,
            "last_used_at": "",
            "is_cold": True,
        },
    ]
    assert families_detail["codex"]["Qwen"] == [{"model": "qwen3"}, "raw-model-entry"]
    assert provider_options_by_cli == {"codex": {}}
    assert loaders["codex"]("gpt-5.4")[-1] == "gpt-5.4"
    assert cold_calls == [
        ("GPT", 5, "2026-05-21T10:00:00Z", "GPT"),
        ("Qwen", 0, "", "GPT"),
    ]


def test_family_sort_ignores_use_count_when_no_recency_or_default() -> None:
    families = [
        {"family": "Qwen", "use_count": 10},
        {"family": "Claude", "use_count": 20},
        {"family": "DeepSeek", "use_count": 1},
    ]

    sorted_names = [
        item["family"]
        for item in _sort_family_entries_for_tui(
            families,
            preferred_family="",
            now=NOW,
        )
    ]

    assert sorted_names == ["Claude", "DeepSeek", "Qwen"]


def test_build_model_families_uses_current_cli_last_model_for_recency(monkeypatch) -> None:
    import mms_core

    recent_model = "gpt-recent-choice"
    high_count_model = "gpt-high-count"
    middle_count_model = "gpt-middle-count"
    provider = {
        "id": "openai-demo",
        "enabled": True,
        "api_key": "sk-demo",
        "role": "auto",
        "supported_clis": ["claude", "codex"],
        "models_endpoint": "manual",
        "fallback_models": [high_count_model, middle_count_model, recent_model],
    }
    monkeypatch.setattr(mms_core, "_provider_candidates", lambda *_args, **_kwargs: [(provider, None)])
    monkeypatch.setattr(mms_core, "_provider_has_configured_base_url", lambda _provider: True)
    monkeypatch.setattr(mms_core, "_provider_supports_model_for_cli", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(mms_core, "_provider_label", lambda _provider: "OpenAI Demo")
    monkeypatch.setattr(
        mms_core,
        "_load_usage_stats",
        lambda: {
            "sources": {
                "provider:codex:openai-demo": {
                    "cli": "codex",
                    "last_model": recent_model,
                    "last_used_at": "2026-05-22T11:55:00Z",
                    "model_last_used_at": {
                        recent_model: "2026-05-22T11:55:00Z",
                        high_count_model: "2026-05-21T11:55:00Z",
                        middle_count_model: "2026-05-08T11:55:00Z",
                    },
                    "models": {
                        high_count_model: 10,
                        middle_count_model: 20,
                        recent_model: 2,
                    },
                },
                "provider:claude:openai-demo": {
                    "cli": "claude",
                    "last_model": high_count_model,
                    "last_used_at": "2026-05-22T11:59:00Z",
                    "models": {high_count_model: 99},
                },
            }
        },
    )

    families = mms_core._build_model_families_for_cli({}, "codex", {}, [])
    gpt_models = next(item["models"] for item in families if item["family"] == "GPT")
    by_name = {item["model"]: item for item in gpt_models}
    sorted_names = [item["model"] for item in _sort_model_entries_for_tui(gpt_models, "GPT", now=NOW)]

    assert by_name[recent_model]["last_used_at"] == "2026-05-22T11:55:00Z"
    assert by_name[high_count_model]["last_used_at"] == "2026-05-21T11:55:00Z"
    assert by_name[high_count_model]["use_count"] == 10
    assert sorted_names == [recent_model, high_count_model, middle_count_model]


def test_build_model_families_backfills_legacy_source_last_model(monkeypatch) -> None:
    import mms_core

    current_model = "gpt-current-choice"
    older_model = "gpt-older-choice"
    provider = {
        "id": "openai-demo",
        "enabled": True,
        "api_key": "sk-demo",
        "role": "auto",
        "supported_clis": ["codex"],
        "models_endpoint": "manual",
        "fallback_models": [older_model, current_model],
    }
    monkeypatch.setattr(mms_core, "_provider_candidates", lambda *_args, **_kwargs: [(provider, None)])
    monkeypatch.setattr(mms_core, "_provider_has_configured_base_url", lambda _provider: True)
    monkeypatch.setattr(mms_core, "_provider_supports_model_for_cli", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(mms_core, "_provider_label", lambda _provider: "OpenAI Demo")
    monkeypatch.setattr(
        mms_core,
        "_load_usage_stats",
        lambda: {
            "sources": {
                "provider:codex:openai-demo": {
                    "cli": "codex",
                    "last_model": current_model,
                    "last_used_at": "2026-05-22T11:55:00Z",
                    "models": {older_model: 20, current_model: 2},
                },
            }
        },
    )

    families = mms_core._build_model_families_for_cli({}, "codex", {}, [])
    gpt_models = next(item["models"] for item in families if item["family"] == "GPT")
    by_name = {item["model"]: item for item in gpt_models}

    assert by_name[current_model]["last_used_at"] == "2026-05-22T11:55:00Z"
    assert by_name[older_model]["last_used_at"] == ""
