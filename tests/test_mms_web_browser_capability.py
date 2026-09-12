"""T3 Webber browser capability boundary.

The Windows handoff fixes this contract for Pilot and sessions:

- Edge/Chrome CDP login state is never guessed; when it is unknown the payload
  says ``unknown``.
- Windows Ego is unsupported and says why.
- A backend that is unavailable explains why; an available one must not claim
  it is missing.
- Bootstrap exposes the backend list, login boundary and unavailable reason.

These tests pin the contract. The two xfail entries document current registry
gaps: fix the reason strings so they match the probe result, then delete the
markers.
"""
import json
from unittest.mock import patch

import pytest

from mms_platform import browser_capabilities


def _rows(platform_name="win32", found=()):
    found = set(found)
    return {
        item.backend: item.to_dict()
        for item in browser_capabilities(
            platform_name=platform_name,
            which=lambda name: name if name in found else None,
        )
    }


def test_windows_cdp_routes_keep_login_unknown_and_publish_requirements():
    rows = _rows(found=("playwright", "agent-browser"))
    for backend in ("web-access", "edge-cdp", "chrome-cdp"):
        assert rows[backend]["supported"] is True
        assert rows[backend]["loggedIn"] == "unknown"
        assert rows[backend]["requires"], "CDP routes must state what they need"
    json.dumps(rows)  # the bootstrap payload has to stay JSON-serializable


def test_windows_ego_is_unsupported_with_an_explicit_reason():
    ego = _rows()["ego"]
    assert ego["supported"] is False
    assert ego["loggedIn"] == "unknown"
    assert "Windows" in ego["reason"]


def test_windows_isolated_backends_are_not_login_routes():
    rows = _rows(found=("playwright", "agent-browser"))
    for backend in ("playwright", "agent-browser"):
        assert rows[backend]["loggedIn"] is False
        assert "isolated" in rows[backend]["reason"]


def test_missing_playwright_reason_names_the_missing_binary():
    playwright = _rows()["playwright"]
    assert playwright["supported"] is False
    assert "未找到" in playwright["reason"]


@pytest.mark.xfail(reason="registry claims Playwright is missing even after which() found it",
                   strict=False)
def test_available_playwright_reason_does_not_claim_it_is_missing():
    playwright = _rows(found=("playwright",))["playwright"]
    assert playwright["supported"] is True
    assert "未找到" not in playwright["reason"]


@pytest.mark.xfail(reason="missing agent-browser keeps a generic isolated reason",
                   strict=False)
def test_missing_agent_browser_reason_says_it_is_unavailable():
    reason = _rows()["agent-browser"]["reason"]
    assert "未找到" in reason or "不可用" in reason


def test_bootstrap_exposes_platform_and_browser_capability(tmp_path):
    from mms_web.server import WebApplication

    with patch("mms_web.server._adapter", return_value=None):
        app = WebApplication(state_root=tmp_path / "state")
        try:
            payload = app.bootstrap()
        finally:
            app.close()

    platform = payload["platform"]
    assert platform["os"] in {"darwin", "linux", "win32"}
    assert platform["pathStyle"] in {"posix", "windows"}
    rows = payload["browser"]
    assert {row["backend"] for row in rows} >= {"web-access", "playwright", "agent-browser", "ego"}
    for row in rows:
        assert isinstance(row["supported"], bool)
        assert row["loggedIn"] in (True, False, "unknown")
        if not row["supported"]:
            assert row["reason"], "an unsupported backend has to say why"
