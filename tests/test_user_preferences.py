from __future__ import annotations


def test_load_user_preferences_sanitizes_allowlist(monkeypatch, tmp_path):
    import mms_core

    skill_root = tmp_path / "web-access"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_text("# skill\n", encoding="utf-8")
    xmem_root = tmp_path / "xmem"
    xmem_root.mkdir()
    (xmem_root / "SKILL.md").write_text("# xmem\n", encoding="utf-8")
    pref_path = tmp_path / "preferences.toml"
    pref_path.write_text(
        f"""
[launch.defaults]
thinking_mode = "disable"
reasoning_effort = "xhigh"
caveman_mode = "enable"
nsr_mode = "enable"
bypass = false
api_key = "sk-should-be-ignored"

[launch.cli.codex]
reasoning_effort = "low"
disabled_session_surfaces = {{ skills = ["agent-browser"], mcp = ["pilot"] }}

[session_surfaces.disabled]
skills = ["web-access", "web-access", "claude:frontend-design"]
hooks = ["/tmp/drop.sh"]

[assets]
managed_enabled = true
managed_root = "{tmp_path / 'managed-assets'}"

[assets.roots]
web_access = "{skill_root}"
xmem = "{xmem_root}"
credentials = "/tmp/should-not-load"

[provider]
base_url = "https://should-not-load.example"
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(mms_core, "PREFERENCES_PATHS", [str(pref_path)])

    prefs = mms_core.load_user_preferences()

    assert prefs["launch"]["defaults"] == {
        "thinking_mode": "disable",
        "reasoning_effort": "xhigh",
        "caveman_mode": "enable",
        "nsr_mode": "enable",
        "bypass": False,
    }
    assert prefs["launch"]["cli"]["codex"]["reasoning_effort"] == "low"
    assert prefs["launch"]["cli"]["codex"]["disabled_session_surfaces"] == {
        "skills": ["agent-browser"],
        "mcp": ["pilot"],
    }
    assert prefs["session_surfaces"]["disabled"] == {
        "skills": ["web-access", "claude:frontend-design"],
        "hooks": ["/tmp/drop.sh"],
    }
    assert prefs["assets"]["roots"] == {"web_access": str(skill_root), "xmem": str(xmem_root)}
    assert prefs["assets"]["managed_enabled"] is True
    assert prefs["assets"]["managed_root"] == str(tmp_path / "managed-assets")
    assert "provider" not in prefs
    assert "api_key" not in prefs["launch"]["defaults"]
    assert "credentials" not in prefs["assets"]["roots"]


def test_runtime_preferences_merge_defaults_cli_and_disabled_surfaces():
    import mms_core

    prefs = {
        "launch": {
            "defaults": {
                "thinking_mode": "enable",
                "reasoning_effort": "xhigh",
                "bypass": False,
                "disabled_session_surfaces": {"skills": ["token-saver"]},
            },
            "cli": {
                "codex": {
                    "reasoning_effort": "low",
                    "disabled_session_surfaces": {"mcp": ["pilot"]},
                }
            },
        },
        "session_surfaces": {"disabled": {"skills": ["web-access"], "hooks": ["/tmp/drop.sh"]}},
        "assets": {"roots": {}},
    }
    runtime = {
        "id": "provider-a",
        "runtime_kind": "provider",
        "auth_mode": "api_key",
        "reasoning_effort": "medium",
        "disabled_session_surfaces": {"skills": ["existing"]},
    }

    result = mms_core._runtime_with_launch_preferences({"_mms_preferences": prefs}, runtime, "codex")

    assert result is not runtime
    assert runtime["reasoning_effort"] == "medium"
    assert result["thinking_mode"] == "enable"
    assert result["reasoning_effort"] == "low"
    assert result["bypass"] is False
    assert result["disabled_session_surfaces"] == {
        "skills": ["existing", "web-access", "token-saver"],
        "hooks": ["/tmp/drop.sh"],
        "mcp": ["pilot"],
    }
    assert result["_mms_preferences_applied"] is True


def test_runtime_preferences_do_not_reapply_after_confirm_changes():
    import mms_core

    runtime = {
        "id": "provider-a",
        "_mms_preferences_applied": True,
        "reasoning_effort": "medium",
        "bypass": True,
    }
    prefs = {
        "launch": {"defaults": {"reasoning_effort": "xhigh", "bypass": False}, "cli": {}},
        "session_surfaces": {"disabled": {}},
        "assets": {"roots": {}},
    }

    assert mms_core._runtime_with_launch_preferences({"_mms_preferences": prefs}, runtime, "codex") is runtime
    assert runtime["reasoning_effort"] == "medium"
    assert runtime["bypass"] is True


def test_launch_with_tracking_applies_preferences_safety_net(monkeypatch):
    import mms_core
    import mms_launchers

    captured = {}
    prefs = {
        "launch": {"defaults": {}, "cli": {"agy": {"bypass": False, "caveman_mode": "disable", "nsr_mode": "enable"}}},
        "session_surfaces": {"disabled": {"skills": ["agent-browser"]}},
        "assets": {"roots": {}},
    }

    monkeypatch.setattr(mms_core, "load_user_preferences", lambda: prefs)
    monkeypatch.setattr(mms_core, "_record_usage", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_core, "_trace_enabled", False)
    monkeypatch.setattr(
        mms_launchers,
        "launch_cli",
        lambda cli, model_info, runtime, once=False, extra_args=None: captured.update(
            {"cli": cli, "model_info": model_info, "runtime": runtime, "once": once, "extra_args": extra_args}
        ),
    )

    mms_core._launch_with_tracking(
        "agy",
        {},
        {"id": "agy-main", "cli": "agy", "auth_mode": "oauth"},
        once=True,
    )

    assert captured["cli"] == "agy"
    assert captured["once"] is True
    assert captured["runtime"]["bypass"] is False
    assert captured["runtime"]["caveman_mode"] == "disable"
    assert captured["runtime"]["nsr_mode"] == "enable"
    assert captured["runtime"]["disabled_session_surfaces"] == {"skills": ["agent-browser"]}


def test_asset_root_preference_is_below_env_and_above_defaults(monkeypatch, tmp_path):
    import mms_launchers

    pref_root = tmp_path / "pref-web"
    env_root = tmp_path / "env-web"
    managed_root = tmp_path / "managed-assets" / "skills" / "web-access"
    for root in (pref_root, env_root, managed_root):
        root.mkdir(parents=True)
        (root / "SKILL.md").write_text("# skill\n", encoding="utf-8")

    monkeypatch.delenv("MMS_WEB_ACCESS_ROOT", raising=False)
    monkeypatch.setattr(
        mms_launchers,
        "preference_asset_root",
        lambda asset_name: str(pref_root) if asset_name == "web_access" else "",
    )
    monkeypatch.setattr(mms_launchers, "managed_assets_enabled", lambda: True)
    monkeypatch.setattr(mms_launchers, "managed_assets_root", lambda: str(tmp_path / "managed-assets"))
    assert mms_launchers._resolve_web_access_root() == str(pref_root)

    monkeypatch.setattr(mms_launchers, "preference_asset_root", lambda _asset_name: "")
    assert mms_launchers._resolve_web_access_root() == str(managed_root)

    monkeypatch.setenv("MMS_WEB_ACCESS_ROOT", str(env_root))
    assert mms_launchers._resolve_web_access_root() == str(env_root)


def test_config_preferences_help_and_example_are_discoverable(monkeypatch):
    import mms_core

    class FakeConsole:
        def __init__(self):
            self.lines = []

        def print(self, *args, **kwargs):
            self.lines.append(" ".join(str(arg) for arg in args))

    console = FakeConsole()
    monkeypatch.setattr(mms_core, "console", console)

    mms_core.handle_config({}, ["preferences.example"])
    example = "\n".join(console.lines)
    assert "[launch.defaults]" in example
    assert "reasoning_effort" in example

    console.lines.clear()
    mms_core.handle_config({}, ["preferences.help"])
    help_text = "\n".join(console.lines)
    assert "preferences.toml" in help_text
    assert "Human gate" in help_text
    assert "managed_root" in help_text

    console.lines.clear()
    mms_core.handle_config({}, ["human-gate"])
    gate_text = "\n".join(console.lines)
    assert "human-only" in gate_text
    assert "preferences.toml" in gate_text


def test_preferences_help_commands_are_startup_help_requests():
    import mms_core

    assert mms_core._is_help_request(["config", "preferences.help"]) is True
    assert mms_core._is_help_request(["config", "preferences.example"]) is True
    assert mms_core._is_help_request(["config", "human-gate"]) is True
    assert mms_core._is_help_request(["config", "set", "cache.probe_async_min_interval_sec", "5"]) is False
