"""Install-level UI flags (tour seen) live in the state root, not only the browser."""
from pathlib import Path
from unittest.mock import patch

from mms_web.server import WebApplication
from mms_web.ui_preferences import UiPreferences


def test_tour_seen_defaults_false_and_persists(tmp_path):
    prefs = UiPreferences(tmp_path / "state")
    assert prefs.read() == {"tourSeen": False}
    assert prefs.update({"tourSeen": True}) == {"tourSeen": True}
    # A fresh reader (new port / new browser / restart) sees the same flag.
    assert UiPreferences(tmp_path / "state").read() == {"tourSeen": True}
    # Only allowlisted booleans are stored; junk never flips the flag.
    assert prefs.update({"tourSeen": "yes", "other": 1}) == {"tourSeen": False}
    assert prefs.update(None) == {"tourSeen": False}
    assert set(__import__("json").loads((tmp_path / "state" / "ui-preferences.json").read_text())) == {"tourSeen"}


def test_ui_preferences_routes(tmp_path):
    with patch("mms_web.server._adapter", return_value=None):
        app = WebApplication(state_root=tmp_path / "state")
    try:
        assert app.get(["ui-preferences"]) == {"tourSeen": False}
        assert app.post(["ui-preferences"], {"tourSeen": True}) == {"tourSeen": True}
        assert app.get(["ui-preferences"]) == {"tourSeen": True}
        assert (Path(tmp_path) / "state" / "ui-preferences.json").is_file()
    finally:
        app.close()
