import mms_session_assets


class _FakeCore:
    def __init__(self, home):
        self.home = str(home)

    def resolve_real_user_home(self):
        return self.home

    def load_user_preferences(self):
        return {
            "launch": {"defaults": {"bypass": True, "caveman_mode": "enable", "nsr_mode": "disable", "agent_pack": "none"}},
            "session_surfaces": {"disabled": {"skills": ["agent-browser"], "mcp": ["pilot"], "hooks": []}},
        }

    def _caveman_available_for_cli(self, _cli):
        return True

    def _nsr_available_for_cli(self, cli):
        return cli in {"claude", "codex"}

    def _ecc_available_for_claude(self):
        return True

    def _omc_available_for_claude(self):
        return False

    def _build_confirm_preview_catalog(self, cli, _runtime, *, has_caveman=False, has_nsr=False, has_ecc=False, has_omc=False):
        return {
            "allow_execution_surfaces": True,
            "skills": {
                "always": [{"title": "web-access", "summary": "Session skill", "details": [("Path", f"{self.home}/.mms/vendor/web-access/SKILL.md")], "disable_key": "web-access"}],
                "caveman": [{"title": "caveman", "summary": "compact mode", "details": [("Path", f"{self.home}/.mms/vendor/caveman/SKILL.md")]}] if has_caveman else [],
                "ecc": [{"title": "ECC 能力包", "summary": "3 skills", "details": [("Path", f"{self.home}/.mms/agent-packs/ecc")]}] if has_ecc else [],
            },
            "mcp": {"always": [{"title": "global-demo", "summary": "stdio · ~/.local/bin/demo", "details": [("Path", f"{self.home}/.local/bin/demo")]}]},
            "hooks": {"always": [{"title": "RTK OpenCode plugin", "summary": "OpenCode plugin", "details": [("Path", f"{self.home}/.mms/vendor/rtk/plugin.js")]}] if cli == "opencode" else []},
        }


def _patch_core(monkeypatch, tmp_path):
    fake = _FakeCore(tmp_path)
    monkeypatch.setattr(mms_session_assets, "_load_mms_core", lambda: fake)
    return fake


def test_session_assets_snapshot_is_read_only_inventory(monkeypatch, tmp_path):
    _patch_core(monkeypatch, tmp_path)
    snapshot = mms_session_assets.build_session_assets_snapshot(
        {},
        config_path="/tmp/mms/config.toml",
        preferences_path="/tmp/mms/preferences.toml",
        command_name="mms",
    )

    assert snapshot["schema"] == "mms.session_assets.snapshot.v1"
    assert snapshot["mode"] == "read_only_inventory"
    assert {tab["id"] for tab in snapshot["tabs"]} == {"mms_dynamic", "global", "other"}
    assert {cli["id"] for cli in snapshot["clis"]} == {"claude", "codex", "opencode", "agy"}
    assert "preferences.toml" in snapshot["configuration_contract"]["persistent_path"]
    assert "[session_surfaces.disabled]" in snapshot["preference_snippet"]
    assert snapshot["launch_defaults"]["bypass"] is True
    assert snapshot["disabled_defaults"]["skills"] == ["agent-browser"]
    assert snapshot["disabled_defaults"]["mcp"] == ["pilot"]
    assert isinstance(snapshot["rows"], list)
    assert isinstance(snapshot["global_roots"], list)


def test_session_asset_rows_have_user_facing_fields(monkeypatch, tmp_path):
    _patch_core(monkeypatch, tmp_path)
    snapshot = mms_session_assets.build_session_assets_snapshot({})
    rows = snapshot["rows"]

    assert rows
    sample = rows[0]
    assert {"cli", "kind", "title", "summary", "group", "origin", "disable_key"} <= set(sample)
    assert sample["kind"] in {"skills", "mcp", "hooks"}
    assert sample["group"] in {"mms_dynamic", "global", "other"}
