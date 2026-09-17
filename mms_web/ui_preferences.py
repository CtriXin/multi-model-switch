"""Small per-install UI flags kept in the Pilot state root, outside the browser.

Browser localStorage is per origin, so a port or browser change would replay
first-run behaviour. These flags survive that; localStorage stays a fast cache.
"""
from __future__ import annotations
import json
from pathlib import Path

from .runtime import private_json

_BOOL_KEYS = ("tourSeen",)
# The version whose release notes this install has already shown. A version
# string rather than a flag, so every upgrade surfaces its own notes once.
# webHarness is this Pilot instance's default execution tool for new sessions.
_STRING_KEYS = ("whatsNewSeenVersion", "webHarness")
_MAX_STRING = 64
_HARNESS_VALUES = ("", "pi", "grok")


class UiPreferences:
    def __init__(self, state_root: Path):
        self.path = Path(state_root) / "ui-preferences.json"

    def read(self, *, seed_version: str = "") -> dict:
        """Read the flags, seeding a state root that has never been used.

        ``seed_version`` stamps the running version on an install with no
        preferences file at all, so its first visit is not greeted by a
        changelog it did not miss. Deciding this in the browser instead would
        race the guided tour, which writes this same file on first run.
        """
        exists = self.path.exists()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            value = {}
        if not exists and str(seed_version or "").strip():
            return self.update({"whatsNewSeenVersion": str(seed_version).strip()})
        if not isinstance(value, dict):
            value = {}
        result = {key: value.get(key) is True for key in _BOOL_KEYS}
        for key in _STRING_KEYS:
            text = str(value.get(key) or "")[:_MAX_STRING]
            if key == "webHarness" and text not in _HARNESS_VALUES:
                text = ""
            result[key] = text
        return result

    def update(self, payload) -> dict:
        current = self.read()
        if isinstance(payload, dict):
            for key in _BOOL_KEYS:
                if key in payload:
                    current[key] = payload.get(key) is True
            for key in _STRING_KEYS:
                if key in payload:
                    text = str(payload.get(key) or "")[:_MAX_STRING]
                    if key == "webHarness" and text not in _HARNESS_VALUES:
                        continue
                    current[key] = text
        private_json(self.path, current)
        return current
