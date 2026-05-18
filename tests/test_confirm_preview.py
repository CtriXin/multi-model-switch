from pathlib import Path

import mms_core
import mms_launchers


def _write_skill(root: Path, name: str) -> Path:
    skill_dir = root / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
    return skill_dir


def test_build_confirm_preview_catalog_disables_execution_surfaces_for_claude_oauth():
    preview = mms_core._build_confirm_preview_catalog(
        "claude",
        {"auth_mode": "oauth"},
        has_caveman=True,
        has_ecc=True,
    )

    assert preview["allow_execution_surfaces"] is False
    assert preview["mcp"]["always"] == []
    assert preview["skills"]["always"] == []
    assert preview["hooks"]["always"] == []


def test_build_confirm_preview_catalog_collects_preview_sections(monkeypatch, tmp_path):
    base_hook = tmp_path / "rtk-rewrite.sh"
    base_hook.write_text("#!/bin/sh\n", encoding="utf-8")
    caveman_hook = tmp_path / "caveman-activate.js"
    caveman_hook.write_text("// caveman\n", encoding="utf-8")
    ecc_hook = tmp_path / "ecc-stop.sh"
    ecc_hook.write_text("#!/bin/sh\n", encoding="utf-8")

    caveman_root = tmp_path / "caveman"
    ecc_root = tmp_path / "ecc"
    _write_skill(caveman_root, "caveman")
    _write_skill(caveman_root, "caveman-review")
    for idx in range(15):
        _write_skill(ecc_root, f"ecc-skill-{idx}")
    (ecc_root / "commands").mkdir(parents=True, exist_ok=True)
    (ecc_root / "commands" / "command-a.js").write_text("// command\n", encoding="utf-8")
    (ecc_root / "rules").mkdir(parents=True, exist_ok=True)
    (ecc_root / "rules" / "rule-a.md").write_text("# rule\n", encoding="utf-8")

    monkeypatch.setattr(
        mms_launchers,
        "_load_real_claude_settings",
        lambda: {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": f"bash {base_hook}"},
                        ],
                    }
                ]
            }
        },
    )
    monkeypatch.setattr(
        mms_launchers,
        "_session_managed_mcp_servers",
        lambda settings, allow_execution_surfaces=True: (
            {"brainkeeper": {"type": "stdio", "command": "/tmp/brainkeeper-server.sh"}}
            if allow_execution_surfaces
            else {}
        ),
    )
    monkeypatch.setattr(mms_launchers, "_load_mms_claude_settings_template", lambda: {"hooks": {}})
    monkeypatch.setattr(mms_launchers, "_load_global_claude_settings_template", lambda: {})
    monkeypatch.setattr(
        mms_launchers,
        "_sanitize_claude_inherited_settings_payload",
        lambda settings, allow_execution_surfaces=True: settings if allow_execution_surfaces else {},
    )
    monkeypatch.setattr(mms_launchers, "_merge_claude_settings", lambda base, template: dict(base))
    monkeypatch.setattr(mms_launchers, "_strip_agent_im_hooks", lambda hooks: hooks)
    monkeypatch.setattr(
        mms_launchers,
        "_merge_mms_session_hooks",
        lambda existing, template: existing or template or {},
    )
    monkeypatch.setattr(
        mms_launchers,
        "_filter_claude_session_hooks",
        lambda hooks, allow_execution_surfaces=True: hooks if allow_execution_surfaces else {},
    )
    monkeypatch.setattr(
        mms_launchers,
        "_configure_claude_caveman_hooks",
        lambda hooks, enable_caveman=False: (
            {
                "SessionStart": [
                    {
                        "matcher": "",
                        "hooks": [
                            {"type": "command", "command": f"node {caveman_hook}"},
                        ],
                    }
                ]
            }
            if enable_caveman
            else {}
        ),
    )
    monkeypatch.setattr(
        mms_launchers,
        "_configure_claude_ecc_hooks",
        lambda hooks, enable_ecc=False: (
            {
                "Stop": [
                    {
                        "matcher": "",
                        "hooks": [
                            {"type": "command", "command": f"bash {ecc_hook}"},
                        ],
                    }
                ]
            }
            if enable_ecc
            else {}
        ),
    )
    monkeypatch.setattr(
        mms_launchers,
        "_configure_claude_omc_hooks",
        lambda hooks, enable_omc=False: (
            {
                "UserPromptSubmit": [
                    {
                        "matcher": "",
                        "hooks": [
                            {"type": "command", "command": 'node "$CLAUDE_PLUGIN_ROOT"/scripts/keyword-detector.mjs'},
                        ],
                    }
                ]
            }
            if enable_omc
            else {}
        ),
    )
    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: "/tmp/web-access")
    monkeypatch.setattr(mms_launchers, "_resolve_agent_browser_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_toon_root", lambda: "/tmp/toon")
    monkeypatch.setattr(mms_launchers, "_resolve_token_saver_root", lambda: "/tmp/token-saver")
    monkeypatch.setattr(mms_launchers, "_resolve_auto_github_contributor_root", lambda: "/tmp/auto-github-contributor")
    monkeypatch.setattr(mms_launchers, "_resolve_caveman_root", lambda: str(caveman_root))
    monkeypatch.setattr(mms_launchers, "_resolve_ecc_root", lambda: str(ecc_root))
    monkeypatch.setattr(mms_launchers, "_resolve_omc_root", lambda: "")

    preview = mms_core._build_confirm_preview_catalog(
        "claude",
        {"auth_mode": "provider"},
        has_caveman=True,
        has_ecc=True,
        has_omc=False,
    )

    assert preview["allow_execution_surfaces"] is True
    mcp_titles = {item["title"] for item in preview["mcp"]["always"]}
    skill_titles = {item["title"] for item in preview["skills"]["always"]}
    caveman_skill_titles = {item["title"] for item in preview["skills"]["caveman"]}
    ecc_skill_titles = {item["title"] for item in preview["skills"]["ecc"]}
    hook_titles = {item["title"] for item in preview["hooks"]["always"]}
    caveman_hook_titles = {item["title"] for item in preview["hooks"]["caveman"]}
    ecc_hook_titles = {item["title"] for item in preview["hooks"]["ecc"]}

    assert "brainkeeper" in mcp_titles
    assert skill_titles >= {"web-access", "toon", "token-saver", "auto-github-contributor"}
    assert caveman_skill_titles >= {"caveman", "caveman-review"}
    assert len(preview["skills"]["ecc"]) == 1
    assert next(iter(ecc_skill_titles)).startswith("ECC")
    assert "RTK Bash 改写" in hook_titles
    assert "Caveman 激活" in caveman_hook_titles
    assert "ecc-stop" in ecc_hook_titles or any(title.startswith("ECC") for title in ecc_hook_titles)

    brainkeeper_item = next(item for item in preview["mcp"]["always"] if item["title"] == "brainkeeper")
    assert any(label == "路径" and value for label, value in brainkeeper_item["details"])

    ecc_bundle = preview["skills"]["ecc"][0]
    assert "skill" in ecc_bundle["summary"]
    assert any(label == "路径" and value for label, value in ecc_bundle["details"])
    assert any(label == "命令" and value for label, value in ecc_bundle["details"])
    assert any(label == "规则" and value for label, value in ecc_bundle["details"])
    assert any(label == "说明" and "hooks" in value for label, value in ecc_bundle["details"])

    rtk_hook = next(item for item in preview["hooks"]["always"] if item["title"] == "RTK Bash 改写")
    assert any(label == "触发" and "Bash" in value for label, value in rtk_hook["details"])
    assert any(label == "路径" and value for label, value in rtk_hook["details"])


def test_build_confirm_preview_catalog_collects_omc_bundle(monkeypatch, tmp_path):
    omc_root = tmp_path / "oh-my-claudecode"
    for name in ("team", "ralph", "autopilot"):
        _write_skill(omc_root, name)
    (omc_root / "agents").mkdir(parents=True)
    (omc_root / "agents" / "executor.md").write_text("# executor\n", encoding="utf-8")
    (omc_root / "hooks").mkdir(parents=True)
    (omc_root / "hooks" / "hooks.json").write_text('{"hooks":{}}', encoding="utf-8")
    (omc_root / ".claude-plugin").mkdir(parents=True)
    (omc_root / ".claude-plugin" / "plugin.json").write_text('{"name":"oh-my-claudecode"}', encoding="utf-8")
    (omc_root / ".mcp.json").write_text(
        '{"mcpServers":{"t":{"command":"node","args":["${CLAUDE_PLUGIN_ROOT}/bridge/mcp-server.cjs"]}}}',
        encoding="utf-8",
    )

    monkeypatch.setattr(mms_launchers, "_load_real_claude_settings", lambda: {})
    monkeypatch.setattr(mms_launchers, "_session_managed_mcp_servers", lambda settings, allow_execution_surfaces=True: {})
    monkeypatch.setattr(mms_launchers, "_load_mms_claude_settings_template", lambda: {"hooks": {}})
    monkeypatch.setattr(mms_launchers, "_load_global_claude_settings_template", lambda: {})
    monkeypatch.setattr(mms_launchers, "_sanitize_claude_inherited_settings_payload", lambda settings, allow_execution_surfaces=True: {})
    monkeypatch.setattr(mms_launchers, "_merge_claude_settings", lambda base, template: dict(base))
    monkeypatch.setattr(mms_launchers, "_strip_agent_im_hooks", lambda hooks: hooks)
    monkeypatch.setattr(mms_launchers, "_merge_mms_session_hooks", lambda existing, template: existing or template or {})
    monkeypatch.setattr(mms_launchers, "_filter_claude_session_hooks", lambda hooks, allow_execution_surfaces=True: hooks if allow_execution_surfaces else {})
    monkeypatch.setattr(mms_launchers, "_configure_claude_caveman_hooks", lambda hooks, enable_caveman=False: {})
    monkeypatch.setattr(mms_launchers, "_configure_claude_ecc_hooks", lambda hooks, enable_ecc=False: {})
    monkeypatch.setattr(
        mms_launchers,
        "_configure_claude_omc_hooks",
        lambda hooks, enable_omc=False: {
            "UserPromptSubmit": [
                {
                    "matcher": "",
                    "hooks": [{"type": "command", "command": 'node "$CLAUDE_PLUGIN_ROOT"/scripts/keyword-detector.mjs'}],
                }
            ]
        } if enable_omc else {},
    )
    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_weber_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_agent_browser_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_toon_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_token_saver_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_auto_github_contributor_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_caveman_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_ecc_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_omc_root", lambda: str(omc_root))

    preview = mms_core._build_confirm_preview_catalog(
        "claude",
        {"auth_mode": "provider"},
        has_omc=True,
    )

    assert {item["title"] for item in preview["mcp"]["omc"]} == {"t"}
    omc_skill_titles = {item["title"] for item in preview["skills"]["omc"]}
    assert omc_skill_titles == {"team", "ralph", "autopilot"} or "OMC 能力包" in omc_skill_titles
    assert "OMC 关键词检测" in {item["title"] for item in preview["hooks"]["omc"]}
    mcp_item = preview["mcp"]["omc"][0]
    assert any(label == "路径" and value for label, value in mcp_item["details"])


def test_build_confirm_preview_catalog_collects_opencode_assets(monkeypatch, tmp_path):
    caveman_root = tmp_path / "caveman"
    _write_skill(caveman_root, "caveman")
    web_access = _write_skill(tmp_path / "web-access-root", "web-access")
    weber = _write_skill(tmp_path / "weber-root", "weber")
    toon = _write_skill(tmp_path / "toon-root", "toon")
    token_saver = _write_skill(tmp_path / "token-root", "token-saver")

    monkeypatch.setattr(mms_launchers, "_opencode_rtk_plugin_path", lambda _runtime=None: "/tmp/opencode-rtk.ts")
    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: str(web_access))
    monkeypatch.setattr(mms_launchers, "_resolve_weber_root", lambda: str(weber))
    monkeypatch.setattr(mms_launchers, "_resolve_toon_root", lambda: str(toon))
    monkeypatch.setattr(mms_launchers, "_resolve_token_saver_root", lambda: str(token_saver))
    monkeypatch.setattr(mms_launchers, "_resolve_auto_github_contributor_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_caveman_root", lambda: str(caveman_root))

    preview = mms_core._build_confirm_preview_catalog(
        "opencode",
        {"opencode_profile": "lite_pro"},
        has_caveman=True,
    )

    assert {item["title"] for item in preview["skills"]["always"]} >= {
        "web-access",
        "weber",
        "toon",
        "token-saver",
    }
    assert {item["title"] for item in preview["skills"]["caveman"]} == {"caveman"}
    assert any(item["title"] == "RTK OpenCode plugin" for item in preview["hooks"]["always"])
