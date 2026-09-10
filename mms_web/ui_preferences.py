"""Small per-install UI flags kept in the Pilot state root, outside the browser.

Browser localStorage is per origin, so a port or browser change would replay
first-run behaviour. These flags survive that; localStorage stays a fast cache.
"""
from __future__ import annotations
import json
from pathlib import Path

from .runtime import private_json

_BOOL_KEYS = ("tourSeen",)


class UiPreferences:
    def __init__(self, state_root: Path):
        self.path = Path(state_root) / "ui-preferences.json"

    def read(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            value = {}
        if not isinstance(value, dict):
            value = {}
        return {key: value.get(key) is True for key in _BOOL_KEYS}

    def update(self, payload) -> dict:
        current = self.read()
        if isinstance(payload, dict):
            for key in _BOOL_KEYS:
                if key in payload:
                    current[key] = payload.get(key) is True
        private_json(self.path, current)
        return current
