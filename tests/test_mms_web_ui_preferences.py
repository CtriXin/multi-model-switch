"""Install-level UI flags live in the state root, not only the browser."""
import json
from pathlib import Path
from unittest.mock import patch

from mms_version import VERSION
from mms_web.server import WebApplication
from mms_web.ui_preferences import UiPreferences

EMPTY = {"tourSeen": False, "whatsNewSeenVersion": "", "webHarness": ""}


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
    assert prefs.update({"tourSeen": True}) == {**EMPTY, "tourSeen": True, "whatsNewSeenVersion": "4.16.0"}
    assert UiPreferences(tmp_path / "state").read() == {**EMPTY, "tourSeen": True, "whatsNewSeenVersion": "4.16.0"}
    # Anything a browser could put there is bounded before it is written.
    assert len(prefs.update({"whatsNewSeenVersion": "9" * 500})["whatsNewSeenVersion"]) == 64
    assert prefs.update({"whatsNewSeenVersion": None})["whatsNewSeenVersion"] == ""


def test_a_never_used_install_is_stamped_before_the_browser_sees_it(tmp_path):
    """A first-ever read decides "this install is new", not the browser.

    The guided tour writes this same file on first run, so a browser-side rule
    would race it and sometimes greet a first-time user with a changelog.
    """
    prefs = UiPreferences(tmp_path / "state")
    assert prefs.read(seed_version="4.17.0") == {**EMPTY, "whatsNewSeenVersion": "4.17.0"}
    # Written, not just returned: the next read agrees without seeding again.
    assert prefs.read() == {**EMPTY, "whatsNewSeenVersion": "4.17.0"}

    # An install that already exists is an upgrade, and keeps its empty value
    # so the notes get shown.
    used = UiPreferences(tmp_path / "used")
    used.update({"tourSeen": True})
    assert used.read(seed_version="4.17.0") == {**EMPTY, "tourSeen": True}


def test_ui_preferences_routes(tmp_path):
    with patch("mms_web.server._adapter", return_value=None):
        app = WebApplication(state_root=tmp_path / "state")
    try:
        # The very first read stamps the running version on a new state root.
        first = app.get(["ui-preferences"])
        assert first["tourSeen"] is False
        assert first["whatsNewSeenVersion"] == VERSION
        assert app.post(["ui-preferences"], {"tourSeen": True})["tourSeen"] is True
        assert app.get(["ui-preferences"])["tourSeen"] is True
        assert app.post(["ui-preferences"], {"whatsNewSeenVersion": "4.16.0"}) == {
            "tourSeen": True,
            "whatsNewSeenVersion": "4.16.0",
            "webHarness": "",
        }
        assert app.post(["ui-preferences"], {"webHarness": "grok"})["webHarness"] == "grok"
        assert app.get(["ui-preferences"])["webHarness"] == "grok"
        assert app.post(["ui-preferences"], {"webHarness": "claude"})["webHarness"] == "grok"
        assert (Path(tmp_path) / "state" / "ui-preferences.json").is_file()
        assert first.get("webHarness") == ""
        assert app.default_web_harness(["pi", "grok"]) == "grok"
        assert app._preset_for_default_harness("web:pi:gw:m") == "web:pi:gw:m"
    finally:
        app.close()
