from __future__ import annotations

from datetime import datetime, timedelta

from mms_display.model import (
    ModelAsset,
    ModelDisplayState,
    TuiRegistryAction,
    fold_long_tail_models,
    get_registry_tui_actions,
    search_model_assets,
    sort_models_for_family,
)
from mms_registry.tui_adapter import InMemoryRegistryTuiAdapter, build_registry_display_state


def test_recency_beats_high_historical_use_count_inside_family() -> None:
    now = datetime(2026, 5, 22, 12, 0, 0)
    models = [
        ModelAsset(
            model_id="gpt-5.4",
            family="GPT",
            last_used_at=now - timedelta(days=90),
            use_count=900,
        ),
        ModelAsset(
            model_id="gpt-5.5",
            family="GPT",
            last_used_at=now - timedelta(hours=18),
            use_count=2,
        ),
        ModelAsset(
            model_id="gpt-never-used",
            family="GPT",
            use_count=1200,
        ),
    ]

    sorted_ids = [asset.model_id for asset in sort_models_for_family(models, now)]

    assert sorted_ids[0] == "gpt-5.5"
    assert sorted_ids.index("gpt-never-used") > sorted_ids.index("gpt-5.4")


def test_qwen_long_tail_folds_but_search_finds_folded_item() -> None:
    now = datetime(2026, 5, 22, 12, 0, 0)
    active = ModelAsset(
        model_id="qwen3.6-plus",
        family="Qwen",
        last_used_at=now - timedelta(days=1),
        use_count=3,
    )
    folded = ModelAsset(
        model_id="qwen-legacy-long-tail",
        family="Qwen",
        registry_state="dormant",
        aliases=("legacy qwen",),
    )

    folded_set = fold_long_tail_models([folded, active], now)
    search_results = search_model_assets("legacy", [folded, active])
    state = InMemoryRegistryTuiAdapter((folded, active)).build_display_state(
        now=now,
        query="legacy",
        preferred_family="Qwen",
    )

    assert [asset.model_id for asset in folded_set.visible] == ["qwen3.6-plus"]
    assert [asset.model_id for asset in folded_set.folded] == ["qwen-legacy-long-tail"]
    assert folded.display_state(now) is ModelDisplayState.DORMANT
    assert [asset.model_id for asset in search_results] == ["qwen-legacy-long-tail"]
    assert state.sections[0].folded_count == 1
    assert [asset.model_id for asset in state.search_results] == ["qwen-legacy-long-tail"]


def test_recoverable_tombstoned_item_is_searchable_and_not_default_launch() -> None:
    now = datetime(2026, 5, 22, 12, 0, 0)
    recoverable = ModelAsset(
        model_id="claude-sonnet-4-6-old-route",
        family="Claude",
        registry_state="tombstoned",
        tombstoned=True,
        restore_available=True,
        tags=("restore",),
    )
    active = ModelAsset(
        model_id="claude-sonnet-4-6",
        family="Claude",
        last_used_at=now - timedelta(days=2),
    )

    state = build_registry_display_state(
        [recoverable, active],
        now=now,
        query="restore",
    )

    assert recoverable.display_state(now) is ModelDisplayState.RECOVERABLE
    assert [asset.model_id for asset in state.search_results] == [
        "claude-sonnet-4-6-old-route"
    ]
    assert recoverable in state.recoverable_assets
    assert recoverable not in state.default_launch_assets


def test_candidate_item_excluded_from_default_launch_until_opted_or_validated() -> None:
    now = datetime(2026, 5, 22, 12, 0, 0)
    candidate = ModelAsset(
        model_id="glm-5.2-candidate",
        family="GLM",
        registry_state="candidate",
        candidate=True,
    )
    opted_candidate = ModelAsset(
        model_id="glm-5.2-opted",
        family="GLM",
        registry_state="candidate",
        candidate=True,
        opted_in=True,
    )
    lazy_validated = ModelAsset(
        model_id="glm-5.2-lazy-validated",
        family="GLM",
        registry_state="candidate",
        candidate=True,
        lazy_validated=True,
    )

    state = build_registry_display_state(
        [candidate, opted_candidate, lazy_validated],
        now=now,
    )
    default_ids = {asset.model_id for asset in state.default_launch_assets}

    assert candidate.display_state(now) is ModelDisplayState.CANDIDATE
    assert candidate in state.candidate_assets
    assert "glm-5.2-candidate" not in default_ids
    assert "glm-5.2-opted" in default_ids
    assert "glm-5.2-lazy-validated" in default_ids


def test_health_degraded_asset_is_displayed_not_removed() -> None:
    now = datetime(2026, 5, 22, 12, 0, 0)
    degraded = ModelAsset(
        model_id="mimo-v2.5-pro",
        family="MiMo",
        health_state="degraded",
        last_used_at=now - timedelta(hours=4),
    )
    broken = ModelAsset(
        model_id="mimo-v2.5-broken-route",
        family="MiMo",
        health_state="broken",
        last_used_at=now - timedelta(hours=2),
    )

    state = build_registry_display_state([degraded, broken], now=now)

    assert degraded.display_state(now) is ModelDisplayState.DEGRADED
    assert broken.display_state(now) is ModelDisplayState.BROKEN
    assert degraded in state.all_assets
    assert broken in state.all_assets
    assert broken not in state.default_launch_assets


def test_action_descriptors_exist_with_stable_labels() -> None:
    actions = {descriptor.action: descriptor.label for descriptor in get_registry_tui_actions()}

    assert actions == {
        TuiRegistryAction.REFRESH_SOURCES: "Refresh Sources",
        TuiRegistryAction.PROBE_SELECTED: "Probe Selected",
        TuiRegistryAction.REGISTRY_DOCTOR: "Registry Doctor",
        TuiRegistryAction.RECENTLY_CHANGED: "Recently Changed",
        TuiRegistryAction.RECOVERABLE: "Recoverable",
        TuiRegistryAction.INTERRUPTED_SESSIONS: "Interrupted Sessions",
    }
