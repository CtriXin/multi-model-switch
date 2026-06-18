from __future__ import annotations

from mms_opencode_session import overlay_opencode_session_assets


def test_overlay_opencode_session_assets_accepts_managed_dynamic_skill_overlay(tmp_path):
    calls = []

    def record(name):
        def _inner(*_args, **_kwargs):
            calls.append(name)

        return _inner

    overlay_opencode_session_assets(
        str(tmp_path / "config"),
        str(tmp_path / "session"),
        overlay_opencode_rtk_plugin=record("rtk"),
        overlay_caveman_session_entries=record("caveman"),
        overlay_web_access_session_entries=record("web-access"),
        overlay_weber_session_entries=record("weber"),
        overlay_toon_session_entries=record("toon"),
        overlay_token_saver_session_entries=record("token-saver"),
        overlay_managed_dynamic_skill_entries=record("managed-dynamic-skills"),
        overlay_codegraph_session_entries=record("codegraph"),
    )

    assert "managed-dynamic-skills" in calls
    assert "xmem" not in calls
    assert "opencode-xmem" not in calls
