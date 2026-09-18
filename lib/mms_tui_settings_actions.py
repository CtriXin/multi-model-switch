"""Backend descriptors for future MMS TUI Settings/Maintenance actions.

This module is intentionally display-safe: it contains no config writes, no
credential reads, and no launcher side effects. The TUI can render these
descriptors before each action gets a dedicated implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class TuiSettingsActionDescriptor:
    action_id: str
    label: str
    panel: str
    status: str
    replacement_for: Tuple[str, ...] = ()
    description: str = ""
    safety: str = "read-only scaffold"
    requires_confirmation: bool = False
    emergency_access: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "label": self.label,
            "panel": self.panel,
            "status": self.status,
            "replacement_for": list(self.replacement_for),
            "description": self.description,
            "safety": self.safety,
            "requires_confirmation": self.requires_confirmation,
            "emergency_access": self.emergency_access,
        }


SETTINGS_MAINTENANCE_PANEL = "Settings / Maintenance"


TUI_SETTINGS_ACTIONS: Tuple[TuiSettingsActionDescriptor, ...] = (
    TuiSettingsActionDescriptor(
        action_id="refresh-sources",
        label="Refresh Sources",
        panel=SETTINGS_MAINTENANCE_PANEL,
        status="scaffold",
        replacement_for=("mms usage --refresh", "manual registry refresh"),
        description="Refresh provider/model source evidence into candidate state without changing runtime defaults.",
    ),
    TuiSettingsActionDescriptor(
        action_id="probe-selected",
        label="Probe Selected / Small Health Check",
        panel=SETTINGS_MAINTENANCE_PANEL,
        status="scaffold",
        replacement_for=("mms test", "mms smoke", "mms doctor lite"),
        description="Run a bounded selected-model probe or small health check and report evidence only.",
    ),
    TuiSettingsActionDescriptor(
        action_id="registry-doctor",
        label="Registry Doctor",
        panel=SETTINGS_MAINTENANCE_PANEL,
        status="scaffold",
        replacement_for=("mms routes", "manual route audit"),
        description="Inspect registry contract, route/profile/policy drift, and latest-approved bundle health.",
    ),
    TuiSettingsActionDescriptor(
        action_id="recoverable-models",
        label="Recoverable Models",
        panel=SETTINGS_MAINTENANCE_PANEL,
        status="scaffold",
        description="Show tombstoned, dormant, or recoverable model assets without restoring them automatically.",
    ),
    TuiSettingsActionDescriptor(
        action_id="interrupted-sessions",
        label="Interrupted Sessions / Rescue",
        panel=SETTINGS_MAINTENANCE_PANEL,
        status="scaffold",
        replacement_for=("mms session", "repo .mms/rescue artifacts"),
        description="Surface interrupted managed sessions and rescue artifacts for explicit user recovery.",
        emergency_access=True,
    ),
    TuiSettingsActionDescriptor(
        action_id="export-approved-bundle",
        label="Export Approved Bundle",
        panel=SETTINGS_MAINTENANCE_PANEL,
        status="scaffold",
        replacement_for=("model-routes.json export", "manual bundle copy"),
        description="Export the latest approved registry bundle with manifest/hash checks.",
        requires_confirmation=True,
    ),
    TuiSettingsActionDescriptor(
        action_id="legacy-tools-emergency-debug",
        label="Legacy Tools / Emergency Debug",
        panel=SETTINGS_MAINTENANCE_PANEL,
        status="scaffold",
        replacement_for=("mms chat", "mms discuss", "mmc", "emergency debug paths"),
        description="Keep legacy and emergency tools discoverable for recovery, while avoiding them as main product entrypoints.",
        emergency_access=True,
    ),
    TuiSettingsActionDescriptor(
        action_id="usage-health-overlay",
        label="Usage / Last Used / Health overlay view",
        panel=SETTINGS_MAINTENANCE_PANEL,
        status="scaffold",
        replacement_for=("mms usage", "usage.json inspection", "health cache inspection"),
        description="Show usage, last-used metadata, and health overlay state as display data only.",
    ),
)


def list_tui_settings_actions() -> Tuple[TuiSettingsActionDescriptor, ...]:
    return TUI_SETTINGS_ACTIONS


def get_tui_settings_action(action_id: str) -> TuiSettingsActionDescriptor | None:
    normalized = str(action_id or "").strip().lower()
    for descriptor in TUI_SETTINGS_ACTIONS:
        if descriptor.action_id == normalized:
            return descriptor
    return None
