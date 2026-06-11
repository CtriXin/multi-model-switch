from __future__ import annotations

from datetime import datetime, timezone

from mms_tui import (
    _sort_cli_names_by_last_used,
    _sort_model_entries_for_tui,
    _sort_profile_options_for_tui,
)
from mms_core import _sort_family_entries_for_tui


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


def test_profile_sort_uses_last_opencode_profile_id() -> None:
    options = [
        {"id": "agent", "profile_id": "lite_pro_orchestrated"},
        {"id": "review", "profile_id": "review_hub"},
        {"id": "omo", "profile_id": "heavy_omo"},
        {"id": "raw", "profile_id": "raw"},
    ]

    ordered = _sort_profile_options_for_tui(options, {"opencode_profile": "review_hub"})

    assert [item["id"] for item in ordered] == ["review", "agent", "omo", "raw"]


def test_profile_sort_reads_legacy_model_info_profile() -> None:
    options = [
        {"id": "agent", "profile_id": "lite_pro_orchestrated"},
        {"id": "review", "profile_id": "review_hub"},
        {"id": "omo", "profile_id": "heavy_omo"},
    ]

    ordered = _sort_profile_options_for_tui(
        options,
        {"model_info": {"model": "glm-5-turbo", "profile": "review_hub"}},
    )

    assert [item["id"] for item in ordered] == ["review", "agent", "omo"]


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
