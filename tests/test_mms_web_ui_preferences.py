"""Install-level UI flags live in the state root, not only the browser."""
import json
from pathlib import Path
from unittest.mock import patch

from mms_web.server import WebApplication
from mms_web.ui_preferences import UiPreferences

EMPTY = {"tourSeen": False, "whatsNewSeenVersion": ""}


def test_tour_seen_defaults_false_and_persists(tmp_path):
    prefs = UiPreferences(tmp_path / "state")
    assert prefs.read() == EMPTY
    assert prefs.update({"tourSeen": True}) == {**EMPTY, "tourSeen": True}
    # A fresh reader (new port / new browser / restart) sees the same flag.
    assert UiPreferences(tmp_path / "state").read() == {**EMPTY, "tourSeen": True}
    # Only allowlisted keys are stored; junk never flips the flag.
    assert prefs.update({"tourSeen": "yes", "other": 1}) == EMPTY
    assert prefs.update(None) == EMPTY
    assert set(json.loads((tmp_path / "state" / "ui-preferences.json").read_text())) == set(EMPTY)


def test_the_release_notes_marker_is_a_version_not_a_flag(tmp_path):
    """Every upgrade owes its own notes, so the store remembers which were read."""
    prefs = UiPreferences(tmp_path / "state")

    assert prefs.update({"whatsNewSeenVersion": "4.16.0"}) == {**EMPTY, "whatsNewSeenVersion": "4.16.0"}
    # The two keys are independent: neither write clears the other.
    assert prefs.update({"tourSeen": True}) == {"tourSeen": True, "whatsNewSeenVersion": "4.16.0"}
    assert UiPreferences(tmp_path / "state").read() == {"tourSeen": True, "whatsNewSeenVersion": "4.16.0"}
    # Anything a browser could put there is bounded before it is written.
    assert len(prefs.update({"whatsNewSeenVersion": "9" * 500})["whatsNewSeenVersion"]) == 64
    assert prefs.update({"whatsNewSeenVersion": None})["whatsNewSeenVersion"] == ""


def test_ui_preferences_routes(tmp_path):
    with patch("mms_web.server._adapter", return_value=None):
        app = WebApplication(state_root=tmp_path / "state")
    try:
        assert app.get(["ui-preferences"]) == EMPTY
        assert app.post(["ui-preferences"], {"tourSeen": True}) == {**EMPTY, "tourSeen": True}
        assert app.get(["ui-preferences"]) == {**EMPTY, "tourSeen": True}
        assert app.post(["ui-preferences"], {"whatsNewSeenVersion": "4.16.0"}) == {
            "tourSeen": True,
            "whatsNewSeenVersion": "4.16.0",
        }
        assert (Path(tmp_path) / "state" / "ui-preferences.json").is_file()
    finally:
        app.close()
