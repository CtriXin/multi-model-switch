from __future__ import annotations

from datetime import datetime, timezone

from mms_tui import _sort_cli_names_by_last_used, _sort_model_entries_for_tui
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


def test_model_sort_uses_recency_before_historical_count() -> None:
    models = [
        {"model": "gpt-5.4", "use_count": 900, "last_used_at": "2026-02-22T12:00:00Z"},
        {"model": "gpt-5.5", "use_count": 2, "last_used_at": "2026-05-22T06:00:00Z"},
        {"model": "gpt-never-used", "use_count": 1200},
    ]

    sorted_names = [item["model"] for item in _sort_model_entries_for_tui(models, "GPT", now=NOW)]

    assert sorted_names == ["gpt-5.5", "gpt-5.4", "gpt-never-used"]


def test_model_sort_falls_back_to_use_count_then_name_without_recency() -> None:
    models = [
        {"model": "qwen-b", "use_count": 1},
        {"model": "qwen-a", "use_count": 3},
        {"model": "qwen-c", "use_count": 3},
    ]

    sorted_names = [item["model"] for item in _sort_model_entries_for_tui(models, "Qwen", now=NOW)]

    assert sorted_names == ["qwen-a", "qwen-c", "qwen-b"]


def test_family_sort_uses_recency_before_default_family_and_count() -> None:
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
