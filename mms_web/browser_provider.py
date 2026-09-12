"""Common browser capability contract used by MMS Bots.

Providers own browser sessions, profiles and permissions. MMS only consumes
semantic actions and evidence returned by the selected provider.
"""
from __future__ import annotations

from typing import Any, Protocol


class BrowserProvider(Protocol):
    provider_id: str

    def available(self) -> bool:
        """Whether this provider is installed and authorized."""

    def capture(self, task_id: str, url: str | None = None) -> dict[str, Any]:
        """Capture a screenshot from the task's persistent browser page."""

    def interact(self, task_id: str, operation: str, target: str | None = None,
                 value: str | None = None) -> dict[str, Any]:
        """Run a bounded semantic browser action."""

    def capabilities(self) -> dict[str, Any]:
        """Return provider name and supported operations for the UI."""
