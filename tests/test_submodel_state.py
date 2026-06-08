from __future__ import annotations

from mms_display.submodel_state import SubmodelProviderState, format_age, format_ttfb


def _provider(provider_id, name, priority, *, family="GPT"):
    return {
        "provider_id": provider_id,
        "provider_name": name,
        "provider_ctx": {
            "id": provider_id,
            "priority": priority,
            "priority_family": family,
        },
    }


def test_provider_choices_lazy_load_and_skip_duplicate_provider() -> None:
    calls = []
    models = [
        {
            "model": "gpt-5",
            "provider_name": "Base",
            "provider_id": "base",
            "provider_ctx": {"id": "base", "priority": 20, "priority_family": "GPT"},
        }
    ]

    def loader(model_name):
        calls.append(model_name)
        return [
            _provider("fast", "Fast", 40),
            _provider("base", "Duplicate", 99),
        ]

    state = SubmodelProviderState(models, provider_options_loader=loader, get_speed_entry=None)

    choices = state.provider_choices(models[0])

    assert calls == ["gpt-5"]
    assert [choice["provider_id"] for choice in choices] == ["fast", "base"]


def test_record_priority_swap_preserves_explicit_priority_changes() -> None:
    model = {
        "model": "gpt-5",
        "provider_name": "Base",
        "provider_id": "base",
        "provider_ctx": {"id": "base", "priority": 20, "priority_family": "GPT"},
    }
    chosen = _provider("fast", "Fast", 40)
    state = SubmodelProviderState([model], get_speed_entry=None)

    state.adjust_provider_priority(chosen, 10)
    state.record_priority_swap(model, chosen)

    assert state.priority_changes["fast||GPT"] == 50
    assert state.priority_changes["base||GPT"] == 15


def test_family_autosort_applies_speed_rank_and_syncs_cursor() -> None:
    models = [
        {
            "model": "gpt-a",
            "provider_name": "Slow",
            "provider_id": "slow",
            "provider_ctx": {"id": "slow", "priority": 100, "priority_family": "GPT"},
        },
        {
            "model": "gpt-b",
            "provider_name": "Slow",
            "provider_id": "slow",
            "provider_ctx": {"id": "slow", "priority": 100, "priority_family": "GPT"},
        },
    ]
    provider_options = {
        "gpt-a": [_provider("fast", "Fast", 80)],
        "gpt-b": [_provider("fast", "Fast", 80)],
    }

    def get_speed_entry(_model_name, *, provider):
        provider_id = provider.get("id")
        return {
            "ttfb_avg_ms": 100 if provider_id == "fast" else 600,
            "samples": 3,
            "age_seconds": 120,
            "is_stale": False,
        }

    state = SubmodelProviderState(
        models,
        provider_options=provider_options,
        get_speed_entry=get_speed_entry,
    )
    sync_calls = []

    plan = state.apply_family_autosort(
        lambda model_entry, provider_id: sync_calls.append((model_entry["model"], provider_id))
    )

    assert plan["can_apply"] is True
    assert state.priority_changes == {
        "fast||GPT": 100,
        "slow||GPT": 95,
    }
    assert sync_calls == [("gpt-a", "fast"), ("gpt-b", "fast")]


def test_format_speed_stats_values() -> None:
    assert format_ttfb(123.4) == "123ms"
    assert format_ttfb(None) == "-"
    assert format_age(90) == "1m"
    assert format_age(7200) == "2h"
    assert format_age(172800) == "2d"
