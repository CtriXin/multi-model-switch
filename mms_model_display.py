"""Pure display logic for the MMS registry model asset manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from math import pow
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple


class ModelDisplayState(str, Enum):
    ACTIVE = "active"
    CANDIDATE = "candidate"
    RECOVERABLE = "recoverable"
    DEGRADED = "degraded"
    BROKEN = "broken"
    DORMANT = "dormant"


class TuiRegistryAction(str, Enum):
    REFRESH_SOURCES = "refresh_sources"
    PROBE_SELECTED = "probe_selected"
    REGISTRY_DOCTOR = "registry_doctor"
    RECENTLY_CHANGED = "recently_changed"
    RECOVERABLE = "recoverable"
    INTERRUPTED_SESSIONS = "interrupted_sessions"


@dataclass(frozen=True)
class TuiActionDescriptor:
    action: TuiRegistryAction
    label: str
    description: str
    panel: str = "registry"


REGISTRY_TUI_ACTIONS: Tuple[TuiActionDescriptor, ...] = (
    TuiActionDescriptor(
        TuiRegistryAction.REFRESH_SOURCES,
        "Refresh Sources",
        "Fetch or import registry source evidence into candidate state.",
    ),
    TuiActionDescriptor(
        TuiRegistryAction.PROBE_SELECTED,
        "Probe Selected",
        "Validate the selected model asset without changing runtime defaults.",
    ),
    TuiActionDescriptor(
        TuiRegistryAction.REGISTRY_DOCTOR,
        "Registry Doctor",
        "Inspect registry health, contracts, and display/runtime drift.",
    ),
    TuiActionDescriptor(
        TuiRegistryAction.RECENTLY_CHANGED,
        "Recently Changed",
        "Show source, policy, and health changes since the last review.",
    ),
    TuiActionDescriptor(
        TuiRegistryAction.RECOVERABLE,
        "Recoverable",
        "Show tombstoned or recoverable model assets that can be restored.",
    ),
    TuiActionDescriptor(
        TuiRegistryAction.INTERRUPTED_SESSIONS,
        "Interrupted Sessions",
        "Show launch/session recovery items produced by MMS rescue flows.",
    ),
)


@dataclass(frozen=True)
class ModelAsset:
    model_id: str
    family: str
    display_name: str = ""
    provider_id: str = ""
    route_id: str = ""
    registry_state: str = "approved"
    health_state: str = "usable"
    last_used_at: Any = None
    use_count: int = 0
    favorite: bool = False
    pinned: bool = False
    recommended: bool = False
    candidate: bool = False
    recoverable: bool = False
    tombstoned: bool = False
    restore_available: bool = False
    opted_in: bool = False
    lazy_validated: bool = False
    changed_at: Any = None
    aliases: Tuple[str, ...] = ()
    tags: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.display_name or self.model_id

    def display_state(
        self,
        now: Optional[datetime] = None,
        dormant_after_days: int = 30,
    ) -> ModelDisplayState:
        return resolve_model_display_state(self, now, dormant_after_days)

    @property
    def default_launch_eligible(self) -> bool:
        return is_default_launch_asset(self)


@dataclass(frozen=True)
class FoldedModelSet:
    visible: Tuple[ModelAsset, ...]
    folded: Tuple[ModelAsset, ...]


@dataclass(frozen=True)
class FamilySection:
    family: str
    models: Tuple[ModelAsset, ...]
    folded_models: Tuple[ModelAsset, ...] = ()

    @property
    def folded_count(self) -> int:
        return len(self.folded_models)

    @property
    def all_models(self) -> Tuple[ModelAsset, ...]:
        return self.models + self.folded_models


@dataclass(frozen=True)
class RegistryDisplayState:
    sections: Tuple[FamilySection, ...]
    query: str = ""
    search_results: Tuple[ModelAsset, ...] = ()
    recoverable_assets: Tuple[ModelAsset, ...] = ()
    candidate_assets: Tuple[ModelAsset, ...] = ()
    default_launch_assets: Tuple[ModelAsset, ...] = ()
    actions: Tuple[TuiActionDescriptor, ...] = REGISTRY_TUI_ACTIONS

    @property
    def all_assets(self) -> Tuple[ModelAsset, ...]:
        assets = []
        for section in self.sections:
            assets.extend(section.all_models)
        return tuple(assets)


def get_registry_tui_actions() -> Tuple[TuiActionDescriptor, ...]:
    return REGISTRY_TUI_ACTIONS


def compute_recency_score(
    last_used_at: Any,
    now: datetime,
    half_life_days: int = 14,
) -> float:
    last_used = _coerce_datetime(last_used_at)
    current = _coerce_datetime(now)
    if last_used is None or current is None:
        return 0.0
    if half_life_days <= 0:
        return 1.0

    age_seconds = max(0.0, (current - last_used).total_seconds())
    age_days = age_seconds / 86400.0
    return pow(0.5, age_days / float(half_life_days))


def sort_models_for_family(
    models: Sequence[ModelAsset],
    now: datetime,
) -> Tuple[ModelAsset, ...]:
    def key(asset: ModelAsset) -> Tuple[int, float, int, int, str]:
        return (
            -_priority_rank(asset),
            -compute_recency_score(asset.last_used_at, now),
            -_health_rank(asset),
            -int(asset.use_count or 0),
            asset.name.lower(),
        )

    return tuple(sorted(models, key=key))


def fold_long_tail_models(
    models: Sequence[ModelAsset],
    now: datetime,
    dormant_after_days: int = 30,
) -> FoldedModelSet:
    visible = []
    folded = []
    for asset in sort_models_for_family(models, now):
        if _is_foldable_long_tail(asset, now, dormant_after_days):
            folded.append(asset)
        else:
            visible.append(asset)
    return FoldedModelSet(tuple(visible), tuple(folded))


def search_model_assets(
    query: str,
    assets: Iterable[ModelAsset],
) -> Tuple[ModelAsset, ...]:
    terms = [term for term in _normalise(query).split() if term]
    if not terms:
        return tuple(assets)

    matches = []
    for index, asset in enumerate(assets):
        haystack = _asset_search_text(asset)
        if all(term in haystack for term in terms):
            matches.append((_search_rank(asset, terms), index, asset))

    matches.sort(key=lambda item: (-item[0], item[1], item[2].name.lower()))
    return tuple(item[2] for item in matches)


def build_family_sections(
    assets: Sequence[ModelAsset],
    now: datetime,
    preferred_family: Optional[str] = None,
) -> Tuple[FamilySection, ...]:
    by_family = {}
    for asset in assets:
        family = asset.family or "Other"
        by_family.setdefault(family, []).append(asset)

    preferred = _normalise(preferred_family)

    def family_key(item: Tuple[str, Sequence[ModelAsset]]) -> Tuple[int, float, str]:
        family, family_assets = item
        best_recency = max(
            (compute_recency_score(asset.last_used_at, now) for asset in family_assets),
            default=0.0,
        )
        return (0 if _normalise(family) == preferred else 1, -best_recency, family.lower())

    sections = []
    for family, family_assets in sorted(by_family.items(), key=family_key):
        folded = fold_long_tail_models(family_assets, now)
        sections.append(FamilySection(family, folded.visible, folded.folded))
    return tuple(sections)


def resolve_model_display_state(
    asset: ModelAsset,
    now: Optional[datetime] = None,
    dormant_after_days: int = 30,
) -> ModelDisplayState:
    if _is_recoverable(asset):
        return ModelDisplayState.RECOVERABLE
    if _is_candidate(asset):
        return ModelDisplayState.CANDIDATE
    if _normalise(asset.health_state) in {"broken", "failed", "unusable"}:
        return ModelDisplayState.BROKEN
    if _normalise(asset.health_state) in {"degraded", "warning", "limited"}:
        return ModelDisplayState.DEGRADED
    if _normalise(asset.registry_state) == "dormant":
        return ModelDisplayState.DORMANT
    if now is not None and _is_age_dormant(asset, now, dormant_after_days):
        return ModelDisplayState.DORMANT
    return ModelDisplayState.ACTIVE


def is_default_launch_asset(asset: ModelAsset) -> bool:
    if _is_recoverable(asset):
        return False
    if _normalise(asset.health_state) in {"broken", "failed", "unusable"}:
        return False
    if _is_candidate(asset) and not (asset.opted_in or asset.lazy_validated):
        return False
    return _normalise(asset.registry_state) not in {"deleted", "tombstoned", "purged"}


def _priority_rank(asset: ModelAsset) -> int:
    return int(asset.pinned) * 4 + int(asset.favorite) * 3 + int(asset.recommended) * 2


def _health_rank(asset: ModelAsset) -> int:
    state = _normalise(asset.health_state)
    if state in {"usable", "ok", "healthy", "validated"}:
        return 3
    if state in {"degraded", "warning", "limited"}:
        return 2
    if state in {"", "unknown", "untested"}:
        return 1
    return 0


def _is_foldable_long_tail(
    asset: ModelAsset,
    now: datetime,
    dormant_after_days: int,
) -> bool:
    if _priority_rank(asset):
        return False
    if _is_recoverable(asset) or _is_candidate(asset):
        return False
    if _normalise(asset.registry_state) == "dormant":
        return True
    if _is_age_dormant(asset, now, dormant_after_days):
        return True
    return asset.last_used_at is None and int(asset.use_count or 0) == 0


def _is_age_dormant(
    asset: ModelAsset,
    now: datetime,
    dormant_after_days: int,
) -> bool:
    last_used = _coerce_datetime(asset.last_used_at)
    current = _coerce_datetime(now)
    if last_used is None or current is None:
        return False
    age_seconds = max(0.0, (current - last_used).total_seconds())
    return age_seconds >= dormant_after_days * 86400


def _is_candidate(asset: ModelAsset) -> bool:
    return bool(asset.candidate) or _normalise(asset.registry_state) in {
        "candidate",
        "candidate_truth",
        "pending",
        "unapproved",
    }


def _is_recoverable(asset: ModelAsset) -> bool:
    return (
        bool(asset.recoverable)
        or bool(asset.tombstoned)
        or bool(asset.restore_available)
        or _normalise(asset.registry_state) in {"recoverable", "tombstoned", "deleted"}
    )


def _asset_search_text(asset: ModelAsset) -> str:
    parts = [
        asset.model_id,
        asset.display_name,
        asset.family,
        asset.provider_id,
        asset.route_id,
        asset.registry_state,
        asset.health_state,
        asset.display_state().value,
    ]
    parts.extend(asset.aliases)
    parts.extend(asset.tags)
    for key, value in asset.metadata.items():
        parts.append(str(key))
        parts.append(str(value))
    return _normalise(" ".join(str(part) for part in parts if part))


def _search_rank(asset: ModelAsset, terms: Sequence[str]) -> int:
    name = _normalise(asset.name)
    model_id = _normalise(asset.model_id)
    rank = 0
    for term in terms:
        if model_id == term:
            rank += 6
        elif model_id.startswith(term):
            rank += 4
        elif name.startswith(term):
            rank += 3
        else:
            rank += 1
    if _priority_rank(asset):
        rank += 1
    if is_default_launch_asset(asset):
        rank += 1
    return rank


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _strip_timezone(value)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            return _strip_timezone(datetime.fromisoformat(raw))
        except ValueError:
            return None
    return None


def _strip_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _normalise(value: Any) -> str:
    return str(value or "").strip().lower()
