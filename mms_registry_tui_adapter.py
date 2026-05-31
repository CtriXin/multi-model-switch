"""Thin adapter contract between registry-like sources and the MMS TUI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol, Sequence, Tuple

from mms_display.model import (
    REGISTRY_TUI_ACTIONS,
    ModelAsset,
    RegistryDisplayState,
    build_family_sections,
    is_default_launch_asset,
    search_model_assets,
)


class RegistryTuiAssetSource(Protocol):
    def list_model_assets(self) -> Sequence[ModelAsset]:
        """Return display-safe model assets without credentials or runtime secrets."""


@dataclass(frozen=True)
class InMemoryRegistryTuiAdapter:
    assets: Tuple[ModelAsset, ...]

    def list_model_assets(self) -> Tuple[ModelAsset, ...]:
        return self.assets

    def build_display_state(
        self,
        now: Optional[datetime] = None,
        query: str = "",
        preferred_family: Optional[str] = None,
    ) -> RegistryDisplayState:
        return build_registry_display_state(
            self.assets,
            now=now,
            query=query,
            preferred_family=preferred_family,
        )


def build_registry_display_state(
    assets: Sequence[ModelAsset],
    now: Optional[datetime] = None,
    query: str = "",
    preferred_family: Optional[str] = None,
) -> RegistryDisplayState:
    current = now or datetime.utcnow()
    asset_tuple = tuple(assets)
    sections = build_family_sections(asset_tuple, current, preferred_family=preferred_family)
    search_results = search_model_assets(query, asset_tuple) if query.strip() else ()

    return RegistryDisplayState(
        sections=sections,
        query=query,
        search_results=search_results,
        recoverable_assets=tuple(
            asset for asset in asset_tuple if asset.display_state(current).value == "recoverable"
        ),
        candidate_assets=tuple(
            asset for asset in asset_tuple if asset.display_state(current).value == "candidate"
        ),
        default_launch_assets=tuple(
            asset for asset in _flatten_sections(sections) if is_default_launch_asset(asset)
        ),
        actions=REGISTRY_TUI_ACTIONS,
    )


def _flatten_sections(sections: Sequence) -> Tuple[ModelAsset, ...]:
    assets = []
    for section in sections:
        assets.extend(section.all_models)
    return tuple(assets)
