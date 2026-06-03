from mms_session import inventory as mms_session_assets
import mms_launchers


class _FakeCore:
    def __init__(self, home):
        self.home = str(home)

    def resolve_real_user_home(self):
        return self.home

    def load_user_preferences(self):
        return {
            "launch": {"defaults": {"bypass": True, "caveman_mode": "enable", "nsr_mode": "disable", "agent_pack": "none"}},
            "session_surfaces": {"disabled": {"skills": ["agent-browser"], "mcp": ["pilot"], "hooks": []}},
            "assets": {"managed_enabled": True, "managed_root": f"{self.home}/.local/share/mms/assets", "roots": {}},
        }

    def managed_assets_enabled(self):
        return True

    def managed_assets_root(self):
        return f"{self.home}/.local/share/mms/assets"

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
    for rel in (
        ".claude/skills/claude-global",
        ".codex/skills/codex-global",
        ".agents/skills/shared-global",
        ".codex/plugins/cache/openai-bundled/browser/1.0/skills/browser",
    ):
        skill_dir = tmp_path / rel
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"---\ndescription: {rel}\n---\n", encoding="utf-8")
    managed_root = tmp_path / "auto-skills" / "installed-skills" / "web-access"
    managed_root.mkdir(parents=True)
    (managed_root / "SKILL.md").write_text("# web-access\n", encoding="utf-8")
    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: str(managed_root))
    snapshot = mms_session_assets.build_session_assets_snapshot(
        {},
        config_path="/tmp/mms/config.toml",
        preferences_path="/tmp/mms/preferences.toml",
        command_name="mms",
    )

    assert snapshot["schema"] == "mms.session_assets.snapshot.v1"
    assert snapshot["mode"] == "read_only_inventory"
    assert {tab["id"] for tab in snapshot["tabs"]} == {"mms_dynamic", "global", "other"}
    assert {cli["id"] for cli in snapshot["clis"]} == {"claude", "codex", "opencode", "pi", "agy"}
    assert "preferences.toml" in snapshot["configuration_contract"]["persistent_path"]
    assert "[session_surfaces.disabled]" in snapshot["preference_snippet"]
    assert "[assets]" in snapshot["preference_snippet"]
    assert "managed_root" in snapshot["preference_snippet"]
    assert snapshot["managed_install"]["root"].endswith(".local/share/mms/assets")
    assert snapshot["configuration_contract"]["managed_assets_root"].endswith(".local/share/mms/assets")
    assert snapshot["bundled_install"]["root"].endswith("assets/session-assets")
    assert snapshot["configuration_contract"]["bundled_assets_root"].endswith("assets/session-assets")
    assert snapshot["launch_defaults"]["bypass"] is True
    assert snapshot["disabled_defaults"]["skills"] == ["agent-browser"]
    assert snapshot["disabled_defaults"]["mcp"] == ["pilot"]
    assert isinstance(snapshot["rows"], list)
    assert isinstance(snapshot["managed_roots"], list)
    managed_web = next(root for root in snapshot["managed_roots"] if root["name"] == "web-access")
    assert managed_web["surface"] == "Skill"
    assert managed_web["exists"] is True
    assert managed_web["root_kind"] == "安装/管理镜像"
    assert managed_web["install_path"].endswith(".local/share/mms/assets/skills/web-access")
    assert managed_web["skill_count"] == 1
    assert isinstance(snapshot["global_roots"], list)
    assert snapshot["confirm_reference"]["title"] == "TUI 确认页对照"
    assert {panel["id"] for panel in snapshot["confirm_reference"]["panels"]} == {"summary", "mcp", "skills", "hooks"}
    assert any(action["key"] == "D / Space" for action in snapshot["confirm_reference"]["actions"])
    assert {view["id"] for view in snapshot["cli_views"]} == {"claude", "codex", "opencode", "pi", "agy"}
    assert all(isinstance(view["controls"], list) for view in snapshot["cli_views"])
    assert all(isinstance(view["global_sources"], list) for view in snapshot["cli_views"])
    global_skill_rows = [row for row in snapshot["rows"] if row.get("inventory_only") and row.get("group") == "global"]
    assert {row["title"] for row in global_skill_rows} >= {"claude-global", "codex-global", "shared-global", "browser"}
    claude_global = next(row for row in global_skill_rows if row["title"] == "claude-global")
    codex_global = next(row for row in global_skill_rows if row["title"] == "codex-global")
    shared_global = next(row for row in global_skill_rows if row["title"] == "shared-global")
    assert claude_global["disable_supported"] is True
    assert claude_global["disable_key"] == "claude:claude-global"
    assert codex_global["disable_supported"] is True
    assert codex_global["disable_key"] == "codex:codex-global"
    assert shared_global["disable_supported"] is False
    claude = next(view for view in snapshot["cli_views"] if view["id"] == "claude")
    codex = next(view for view in snapshot["cli_views"] if view["id"] == "codex")
    pi = next(view for view in snapshot["cli_views"] if view["id"] == "pi")
    assert any(src["label"] == "Claude 全局技能" and src["count"] == 1 for src in claude["global_sources"])
    assert any(src["label"] == "Codex bundled plugin 技能" and src["count"] == 1 for src in codex["global_sources"])
    assert pi["allow_execution_surfaces"] is False
    assert any("Pi 当前" in constraint for constraint in pi["constraints"])
    assert snapshot["cli_visibility"]["preference_key"] == "launch.disabled_clis"


def test_session_asset_rows_have_user_facing_fields(monkeypatch, tmp_path):
    _patch_core(monkeypatch, tmp_path)
    snapshot = mms_session_assets.build_session_assets_snapshot({})
    rows = snapshot["rows"]

    assert rows
    sample = rows[0]
    assert {
        "cli",
        "kind",
        "kind_label",
        "title",
        "summary",
        "technical_summary",
        "group",
        "group_label",
        "origin",
        "origin_label",
        "disable_key",
    } <= set(sample)
    assert sample["kind"] in {"skills", "mcp", "hooks"}
    assert sample["group"] in {"mms_dynamic", "global", "other"}
    assert sample["kind_label"] in {"技能", "MCP 服务", "自动钩子"}
    assert sample["group_label"] in {"MMS 动态注入", "全局继承", "其它检测项"}
    assert "web" in sample["title"]
    assert "联网" in sample["summary"] or "浏览" in sample["summary"]


def test_session_asset_cli_views_mirror_launch_confirm(monkeypatch, tmp_path):
    _patch_core(monkeypatch, tmp_path)
    snapshot = mms_session_assets.build_session_assets_snapshot({})

    claude = next(view for view in snapshot["cli_views"] if view["id"] == "claude")

    assert claude["label"] == "Claude"
    assert claude["row_count"] > 0
    assert claude["allow_execution_surfaces"] is True
    assert {"mms_dynamic", "global", "other", "skills", "mcp", "hooks"} <= set(claude["counts"])
    assert {"skills", "mcp", "hooks"} <= set(claude["scope_counts"])
    assert {panel["id"] for panel in claude["panels"]} == {"summary", "mcp", "skills", "hooks"}
    assert "inactive_by_default" in claude
    assert "disabled_by_preference" in claude
    assert any(control["label"] == "绕过审批" for control in claude["controls"])
    assert any(control["key"] == "Tab" for control in claude["controls"])
    assert any(control["label"] == "MCP/技能/钩子注入" for control in claude["controls"])
    assert any(source["label"] == "Claude 全局技能" for source in claude["global_sources"])
    assert any("只读展示" in constraint for constraint in claude["constraints"])
