from __future__ import annotations

from mms_opencode_session import opencode_rtk_plugin_path, overlay_opencode_session_assets


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


def test_opencode_rtk_plugin_path_defaults_off(tmp_path):
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "opencode-rtk.ts").write_text("export {}\n", encoding="utf-8")

    path = opencode_rtk_plugin_path(
        {},
        module_file=str(tmp_path / "mms_launchers.py"),
        normalize_session_surface_disabled=lambda _value: {"hooks": set()},
        runtime_bool=lambda _runtime, _key, default: default,
        env_bool=lambda _key, default: default,
        which=lambda _name: "/usr/bin/rtk",
    )

    assert path == ""


def test_opencode_rtk_plugin_path_can_opt_in_by_runtime(tmp_path):
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    plugin = hooks_dir / "opencode-rtk.ts"
    plugin.write_text("export {}\n", encoding="utf-8")

    path = opencode_rtk_plugin_path(
        {"opencode_rtk": True},
        module_file=str(tmp_path / "mms_launchers.py"),
        normalize_session_surface_disabled=lambda _value: {"hooks": set()},
        runtime_bool=lambda runtime, key, default: bool(runtime.get(key, default)),
        env_bool=lambda _key, default: default,
        which=lambda _name: "/usr/bin/rtk",
    )

    assert path == str(plugin)


def test_opencode_rtk_plugin_path_can_opt_in_by_env(tmp_path):
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    plugin = hooks_dir / "opencode-rtk.ts"
    plugin.write_text("export {}\n", encoding="utf-8")

    path = opencode_rtk_plugin_path(
        {},
        module_file=str(tmp_path / "mms_launchers.py"),
        normalize_session_surface_disabled=lambda _value: {"hooks": set()},
        runtime_bool=lambda _runtime, _key, default: default,
        env_bool=lambda key, default: True if key == "MMS_OPENCODE_RTK" else default,
        which=lambda _name: "/usr/bin/rtk",
    )

    assert path == str(plugin)
