from __future__ import annotations

import asyncio
import io
import json
import os
import types
from datetime import datetime
from pathlib import Path

import pytest


def test_build_claude_session_settings_only_inherits_allowlisted_keys(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_load_mms_claude_settings_template", lambda: {})
    monkeypatch.setattr(mms_launchers, "_load_global_claude_settings_template", lambda: {})
    monkeypatch.setattr(mms_launchers, "_default_session_mcp_servers", lambda: {})

    result = mms_launchers._build_claude_session_settings(
        {
            "theme": "dark",
            "hooks": {"preToolUse": [{"matcher": "*"}]},
            "statusLine": {"type": "command", "command": "/tmp/status.sh"},
            "permissions": {"allow": ["Read"]},
            "env": {"HTTP_PROXY": "http://127.0.0.1:7890"},
        },
        required_env={"HTTP_PROXY": "http://127.0.0.1:7890"},
        default_env={"CLAUDE_CODE_ATTRIBUTION_HEADER": "0"},
    )

    assert result["theme"] == "dark"
    assert result["hooks"]["preToolUse"][0]["matcher"] == "*"
    assert result["statusLine"]["type"] == "command"
    assert "statusline-command.sh" in result["statusLine"]["command"]
    assert "Read" in result["permissions"]["allow"]
    assert result["env"]["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert result["env"]["CLAUDE_CODE_ATTRIBUTION_HEADER"] == "0"


def test_build_claude_session_settings_injects_only_hive_and_mindkeeper_mcp_servers(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_load_mms_claude_settings_template", lambda: {})
    monkeypatch.setattr(mms_launchers, "_load_global_claude_settings_template", lambda: {})
    monkeypatch.setattr(mms_launchers, "_default_session_mcp_servers", lambda: {})
    monkeypatch.setattr(
        mms_launchers,
        "_default_hive_session_mcp_server",
        lambda: {
            "command": "/tmp/hive-session-only.sh",
            "args": [],
            "env": {"HOME": "/tmp/real-home"},
            "type": "stdio",
        },
    )

    result = mms_launchers._build_claude_session_settings(
        {
            "mcpServers": {
                "demo": {"command": "demo"},
                "hive": {"command": "/tmp/hive-mcp.sh", "args": [], "type": "stdio"},
                "mindkeeper": {"command": "node", "args": ["/tmp/mindkeeper.js"], "type": "stdio"},
            },
        }
    )

    assert result["mcpServers"] == {
        "mindkeeper": {"command": "node", "args": ["/tmp/mindkeeper.js"], "type": "stdio"},
        "hive": {
            "command": "/tmp/hive-session-only.sh",
            "args": [],
            "env": {"HOME": "/tmp/real-home"},
            "type": "stdio",
        },
    }


def test_build_claude_session_settings_falls_back_to_local_hive_and_mindkeeper_mcp_servers(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_load_mms_claude_settings_template", lambda: {})
    monkeypatch.setattr(mms_launchers, "_load_global_claude_settings_template", lambda: {})
    monkeypatch.setattr(
        mms_launchers,
        "_default_session_mcp_servers",
        lambda: {
            "mindkeeper": {
                "command": "node",
                "args": ["/tmp/mindkeeper/dist/server.js"],
                "type": "stdio",
            },
        },
    )
    monkeypatch.setattr(
        mms_launchers,
        "_default_hive_session_mcp_server",
        lambda: {
            "command": "/tmp/hive/bin/mcp-server.sh",
            "args": [],
            "env": {"HOME": "/tmp/real-home"},
            "type": "stdio",
        },
    )

    result = mms_launchers._build_claude_session_settings({})

    assert result["mcpServers"]["hive"]["command"] == "/tmp/hive/bin/mcp-server.sh"
    assert result["mcpServers"]["hive"]["env"]["HOME"] == "/tmp/real-home"
    assert result["mcpServers"]["mindkeeper"]["args"] == ["/tmp/mindkeeper/dist/server.js"]


def test_resolve_hive_root_prefers_installed_hive_home_for_installed_mms(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    hive_root = real_home / ".hive-orchestrator"
    (hive_root / "bin").mkdir(parents=True)
    (hive_root / "bin" / "mcp-server.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.delenv("MMS_HIVE_ROOT", raising=False)
    monkeypatch.delenv("HIVE_HOME", raising=False)
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )

    resolved = mms_launchers._resolve_hive_root(module_path=str(real_home / ".mms" / "mms_launchers.py"))

    assert resolved == str(hive_root)


def test_resolve_hive_root_prefers_local_repo_for_source_checkout(monkeypatch, tmp_path):
    import mms_launchers

    source_root = tmp_path / "repo"
    module_path = source_root / "multi-model-switch" / "mms_launchers.py"
    local_hive_root = source_root / "hive"
    installed_hive_root = tmp_path / "real-home" / ".hive-orchestrator"
    (local_hive_root / "bin").mkdir(parents=True)
    (local_hive_root / "bin" / "mcp-server.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (installed_hive_root / "bin").mkdir(parents=True)
    (installed_hive_root / "bin" / "mcp-server.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.delenv("MMS_HIVE_ROOT", raising=False)
    monkeypatch.delenv("HIVE_HOME", raising=False)
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str((tmp_path / "real-home").joinpath(*parts)),
    )

    resolved = mms_launchers._resolve_hive_root(module_path=str(module_path))

    assert resolved == str(local_hive_root)


def test_append_codex_mcp_servers_from_claude_json_injects_hive_fallback(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_home.mkdir(parents=True)
    (real_home / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo": {
                        "command": "node",
                        "args": ["/tmp/demo.js"],
                        "type": "stdio",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )
    monkeypatch.setattr(
        mms_launchers,
        "_default_hive_session_mcp_server",
        lambda: {
            "command": "/tmp/hive/bin/mcp-server.sh",
            "args": [],
            "env": {"HOME": "/tmp/real-home"},
            "type": "stdio",
        },
    )

    rendered = mms_launchers._append_codex_mcp_servers_from_claude_json('base_url = "https://example.test"\n')

    assert '[mcp_servers.demo]' in rendered
    assert '[mcp_servers.hive]' in rendered
    assert 'command = "/tmp/hive/bin/mcp-server.sh"' in rendered
    assert 'HOME = "/tmp/real-home"' in rendered


def test_inject_managed_mcp_servers_into_claude_state_adds_hive_fallback(monkeypatch):
    import mms_launchers

    monkeypatch.setattr(mms_launchers, "_load_real_claude_settings", lambda: {})
    monkeypatch.setattr(mms_launchers, "_default_session_mcp_servers", lambda: {})
    monkeypatch.setattr(
        mms_launchers,
        "_default_hive_session_mcp_server",
        lambda: {
            "command": "/tmp/hive/bin/mcp-server.sh",
            "args": [],
            "env": {"HOME": "/tmp/real-home"},
            "type": "stdio",
        },
    )

    result = mms_launchers._inject_managed_mcp_servers_into_claude_state({})

    assert result["mcpServers"]["hive"]["command"] == "/tmp/hive/bin/mcp-server.sh"
    assert result["mcpServers"]["hive"]["env"]["HOME"] == "/tmp/real-home"


def test_build_claude_session_settings_strips_execution_surfaces_for_oauth_claude(monkeypatch):
    import mms_launchers

    hive_compact = os.path.join(mms_launchers._LOCAL_HOOKS_DIR, "hive-compact-hook.sh")
    monkeypatch.setattr(
        mms_launchers,
        "_load_mms_claude_settings_template",
        lambda: {
            "hooks": {
                "PreCompact": [
                    {
                        "matcher": "",
                        "hooks": [
                            {"type": "command", "command": f"bash {hive_compact}"},
                        ],
                    }
                ],
                "PostCompact": [
                    {
                        "matcher": "",
                        "hooks": [
                            {"type": "command", "command": f"bash {hive_compact}"},
                        ],
                    }
                ],
            }
        },
    )
    monkeypatch.setattr(
        mms_launchers,
        "_load_global_claude_settings_template",
        lambda: {
            "statusLine": {"type": "command", "command": "/tmp/status.sh"},
            "permissions": {"allow": ["Read"]},
        },
    )
    monkeypatch.setattr(
        mms_launchers,
        "_default_session_mcp_servers",
        lambda: {
            "hive": {"command": "/tmp/hive/bin/mcp-server.sh", "args": [], "type": "stdio"},
            "mindkeeper": {"command": "node", "args": ["/tmp/mindkeeper.js"], "type": "stdio"},
        },
    )

    result = mms_launchers._build_claude_session_settings(
        {
            "theme": "dark",
            "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "/tmp/demo.sh"}]}]},
            "statusLine": {"type": "command", "command": "/tmp/account-status.sh"},
            "permissions": {"allow": ["Bash(*)"]},
            "mcpServers": {"demo": {"command": "demo"}},
        },
        allow_execution_surfaces=False,
    )

    assert result["theme"] == "dark"
    assert "hooks" not in result
    assert "statusLine" not in result
    assert "permissions" not in result
    assert "mcpServers" not in result


def test_build_claude_session_settings_rewrites_caveman_hooks_per_session(monkeypatch, tmp_path):
    import mms_launchers

    caveman_root = tmp_path / "caveman"
    hooks_dir = caveman_root / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "caveman-activate.js").write_text("// activate\n", encoding="utf-8")
    (hooks_dir / "caveman-mode-tracker.js").write_text("// tracker\n", encoding="utf-8")

    monkeypatch.setenv("MMS_CAVEMAN_ROOT", str(caveman_root))
    monkeypatch.setattr(mms_launchers, "_load_mms_claude_settings_template", lambda: {})
    monkeypatch.setattr(mms_launchers, "_load_global_claude_settings_template", lambda: {})
    monkeypatch.setattr(mms_launchers, "_default_session_mcp_servers", lambda: {})

    base_settings = {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {"type": "command", "command": 'node "/global/caveman-activate.js"'},
                        {"type": "command", "command": "/tmp/keep-session-start.sh"},
                    ]
                }
            ],
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {"type": "command", "command": 'node "/global/caveman-mode-tracker.js"'},
                    ]
                }
            ],
        }
    }

    disabled = mms_launchers._build_claude_session_settings(
        base_settings,
        enable_caveman=False,
    )
    disabled_session_start = [
        item["command"]
        for group in disabled["hooks"]["SessionStart"]
        for item in group["hooks"]
    ]
    disabled_user_prompt = [
        item["command"]
        for group in disabled["hooks"]["UserPromptSubmit"]
        for item in group["hooks"]
    ]
    disabled_stop = [
        item["command"]
        for group in disabled["hooks"]["Stop"]
        for item in group["hooks"]
    ]
    assert "/tmp/keep-session-start.sh" in disabled_session_start
    assert mms_launchers._CLAUDE_MINDKEEPER_SESSION_START_HOOK in disabled_session_start
    assert disabled_user_prompt == [mms_launchers._CLAUDE_MINDKEEPER_TOKEN_MONITOR_HOOK]
    assert disabled_stop == [mms_launchers._CLAUDE_MINDKEEPER_SESSION_END_HOOK]

    enabled = mms_launchers._build_claude_session_settings(
        base_settings,
        enable_caveman=True,
    )
    session_start_commands = [
        item["command"]
        for group in enabled["hooks"]["SessionStart"]
        for item in group["hooks"]
    ]
    user_prompt_commands = [
        item["command"]
        for group in enabled["hooks"]["UserPromptSubmit"]
        for item in group["hooks"]
    ]
    assert "/tmp/keep-session-start.sh" in session_start_commands
    assert f'node "{caveman_root / "hooks" / "caveman-activate.js"}"' in session_start_commands
    assert f'node "{caveman_root / "hooks" / "caveman-mode-tracker.js"}"' in user_prompt_commands


def test_resolve_caveman_root_prefers_bundled_vendor_before_legacy_home(monkeypatch, tmp_path):
    import mms_launchers

    bundled_root = tmp_path / "mms-install" / "vendor" / "caveman"
    legacy_root = tmp_path / "real-home" / "caveman"
    for root in (bundled_root, legacy_root):
        hooks_dir = root / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "caveman-activate.js").write_text("// activate\n", encoding="utf-8")
        (hooks_dir / "caveman-mode-tracker.js").write_text("// tracker\n", encoding="utf-8")

    monkeypatch.delenv("MMS_CAVEMAN_ROOT", raising=False)
    monkeypatch.setattr(mms_launchers, "__file__", str(tmp_path / "mms-install" / "mms_launchers.py"))
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str((tmp_path / "real-home").joinpath(*parts)),
    )

    assert mms_launchers._resolve_caveman_root() == str(bundled_root)


def test_build_codex_session_hooks_respects_session_caveman_toggle(monkeypatch, tmp_path):
    import mms_launchers

    caveman_root = tmp_path / "caveman"
    hooks_dir = caveman_root / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "caveman-activate.js").write_text("// activate\n", encoding="utf-8")
    (hooks_dir / "caveman-mode-tracker.js").write_text("// tracker\n", encoding="utf-8")
    codex_dir = caveman_root / ".codex"
    codex_dir.mkdir()
    (codex_dir / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup|resume",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "echo 'CAVEMAN MODE ACTIVE. session default'",
                                    "timeout": 5,
                                    "statusMessage": "Loading caveman mode",
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("MMS_CAVEMAN_ROOT", str(caveman_root))
    base_hooks = {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {"type": "command", "command": "/tmp/notify.sh"},
                    ]
                },
                {
                    "matcher": "startup|resume",
                    "hooks": [
                        {"type": "command", "command": "echo 'CAVEMAN MODE ACTIVE. global default'"},
                    ],
                },
            ]
        }
    }

    disabled = mms_launchers._build_codex_session_hooks(
        base_hooks,
        enable_caveman=False,
    )
    disabled_groups = disabled["hooks"]["SessionStart"]
    assert disabled_groups == [
        {
            "hooks": [
                {"type": "command", "command": "/tmp/notify.sh"},
            ]
        }
    ]

    enabled = mms_launchers._build_codex_session_hooks(
        base_hooks,
        enable_caveman=True,
    )
    enabled_groups = enabled["hooks"]["SessionStart"]
    enabled_commands = [
        item["command"]
        for group in enabled_groups
        for item in group["hooks"]
    ]
    assert "/tmp/notify.sh" in enabled_commands
    assert "echo 'CAVEMAN MODE ACTIVE. session default'" in enabled_commands
    assert enabled_commands.count("echo 'CAVEMAN MODE ACTIVE. session default'") == 1


def test_overlay_caveman_session_entries_merges_session_and_caveman_assets(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "session"
    parent_dir = session_home / ".claude"
    parent_dir.mkdir(parents=True)
    global_assets = tmp_path / "global-assets"
    (global_assets / "commands").mkdir(parents=True)
    (global_assets / "skills").mkdir()
    (global_assets / "commands" / "keep.toml").write_text("keep = true\n", encoding="utf-8")
    (global_assets / "skills" / "keep-skill").mkdir()
    os.symlink(global_assets / "commands", parent_dir / "commands")
    os.symlink(global_assets / "skills", parent_dir / "skills")

    caveman_root = tmp_path / "caveman"
    (caveman_root / "commands").mkdir(parents=True)
    (caveman_root / "skills" / "caveman").mkdir(parents=True)
    (caveman_root / "commands" / "caveman.toml").write_text("name = 'caveman'\n", encoding="utf-8")
    (caveman_root / "skills" / "caveman" / "SKILL.md").write_text("# caveman\n", encoding="utf-8")
    (caveman_root / "hooks").mkdir()
    (caveman_root / "hooks" / "caveman-activate.js").write_text("// activate\n", encoding="utf-8")
    (caveman_root / "hooks" / "caveman-mode-tracker.js").write_text("// tracker\n", encoding="utf-8")

    monkeypatch.setenv("MMS_CAVEMAN_ROOT", str(caveman_root))

    mms_launchers._overlay_caveman_session_entries(
        str(parent_dir),
        str(session_home),
        enable_caveman=True,
    )

    assert os.path.islink(parent_dir / "commands")
    assert os.path.islink(parent_dir / "skills")
    assert os.path.islink(parent_dir / "commands" / "keep.toml")
    assert os.path.islink(parent_dir / "commands" / "caveman.toml")
    assert os.path.islink(parent_dir / "skills" / "keep-skill")
    assert os.path.islink(parent_dir / "skills" / "caveman")


def test_overlay_web_access_session_entries_merges_session_and_web_access_skill(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "session"
    parent_dir = session_home / ".claude"
    parent_dir.mkdir(parents=True)
    global_assets = tmp_path / "global-assets"
    (global_assets / "skills").mkdir(parents=True)
    (global_assets / "skills" / "keep-skill").mkdir()
    os.symlink(global_assets / "skills", parent_dir / "skills")

    web_access_root = tmp_path / "web-access"
    (web_access_root / "references").mkdir(parents=True)
    (web_access_root / "SKILL.md").write_text("# web-access\n", encoding="utf-8")
    (web_access_root / "README.md").write_text("# readme\n", encoding="utf-8")

    monkeypatch.setenv("MMS_WEB_ACCESS_ROOT", str(web_access_root))

    mms_launchers._overlay_web_access_session_entries(
        str(parent_dir),
        str(session_home),
    )

    assert os.path.islink(parent_dir / "skills")
    assert os.path.islink(parent_dir / "skills" / "keep-skill")
    assert os.path.islink(parent_dir / "skills" / "web-access")
    assert (parent_dir / "skills" / "web-access" / "SKILL.md").read_text(encoding="utf-8") == "# web-access\n"


def test_overlay_agent_browser_session_entries_merges_session_and_agent_browser_skill(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "session"
    parent_dir = session_home / ".codex"
    parent_dir.mkdir(parents=True)
    global_assets = tmp_path / "global-assets"
    (global_assets / "skills").mkdir(parents=True)
    (global_assets / "skills" / "keep-skill").mkdir()
    os.symlink(global_assets / "skills", parent_dir / "skills")

    agent_browser_root = tmp_path / "agent-browser"
    agent_browser_root.mkdir()
    (agent_browser_root / "SKILL.md").write_text("# agent-browser\n", encoding="utf-8")
    (agent_browser_root / "_meta.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setenv("MMS_AGENT_BROWSER_ROOT", str(agent_browser_root))

    mms_launchers._overlay_agent_browser_session_entries(
        str(parent_dir),
        str(session_home),
    )

    assert os.path.islink(parent_dir / "skills")
    assert os.path.islink(parent_dir / "skills" / "keep-skill")
    assert os.path.islink(parent_dir / "skills" / "agent-browser")
    assert (parent_dir / "skills" / "agent-browser" / "SKILL.md").read_text(encoding="utf-8") == "# agent-browser\n"


def test_codex_gateway_env_materializes_session_caveman_hooks_and_assets(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_codex = real_home / ".codex"
    real_codex.mkdir(parents=True)
    (real_codex / "config.toml").write_text('base_url = "https://api.example.com"\n', encoding="utf-8")
    (real_codex / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {"type": "command", "command": "/tmp/notify.sh"},
                            ]
                        },
                        {
                            "matcher": "startup|resume",
                            "hooks": [
                                {"type": "command", "command": "echo 'CAVEMAN MODE ACTIVE. global default'"},
                            ],
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (real_codex / "commands").mkdir()
    (real_codex / "commands" / "keep.toml").write_text("keep = true\n", encoding="utf-8")
    (real_codex / "skills").mkdir()
    (real_codex / "skills" / "keep-skill").mkdir()

    caveman_root = tmp_path / "caveman"
    (caveman_root / "hooks").mkdir(parents=True)
    (caveman_root / "hooks" / "caveman-activate.js").write_text("// activate\n", encoding="utf-8")
    (caveman_root / "hooks" / "caveman-mode-tracker.js").write_text("// tracker\n", encoding="utf-8")
    (caveman_root / ".codex").mkdir()
    (caveman_root / ".codex" / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup|resume",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "echo 'CAVEMAN MODE ACTIVE. session default'",
                                    "timeout": 5,
                                    "statusMessage": "Loading caveman mode",
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (caveman_root / "commands").mkdir()
    (caveman_root / "commands" / "caveman.toml").write_text("name = 'caveman'\n", encoding="utf-8")
    (caveman_root / "skills" / "caveman").mkdir(parents=True)
    (caveman_root / "skills" / "caveman" / "SKILL.md").write_text("# caveman\n", encoding="utf-8")

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)
    monkeypatch.setenv("MMS_CAVEMAN_ROOT", str(caveman_root))
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_sync_codex_session_claude_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=False: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )

    env = mms_launchers._codex_gateway_env(
        {"id": "relay-a", "api_key": "sk-runtime", "caveman_mode": "enable"},
        "https://relay.example.com",
        model_info={"model": "gpt-5.4"},
    )

    session_codex = Path(env["HOME"]) / ".codex"
    hooks_payload = json.loads((session_codex / "hooks.json").read_text(encoding="utf-8"))
    commands = [
        item["command"]
        for group in hooks_payload["hooks"]["SessionStart"]
        for item in group["hooks"]
    ]
    assert "/tmp/notify.sh" in commands
    assert "echo 'CAVEMAN MODE ACTIVE. session default'" in commands
    assert os.path.islink(session_codex / "commands")
    assert os.path.islink(session_codex / "skills")
    assert os.path.islink(session_codex / "commands" / "keep.toml")
    assert os.path.islink(session_codex / "commands" / "caveman.toml")
    assert os.path.islink(session_codex / "skills" / "keep-skill")
    assert os.path.islink(session_codex / "skills" / "caveman")
    packet = json.loads(Path(env["MMS_SESSION_PACKET_JSON"]).read_text(encoding="utf-8"))
    assert packet["cli"] == "codex"
    assert packet["model"]["primary"] == "gpt-5.4"
    assert env["MMS_SESSION_PACKET_FORMAT"] == "toon"


def test_codex_gateway_env_materializes_session_web_access_skill(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_codex = real_home / ".codex"
    (real_codex / "skills" / "keep-skill").mkdir(parents=True)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    web_access_root = tmp_path / "web-access"
    (web_access_root / "references").mkdir(parents=True)
    (web_access_root / "SKILL.md").write_text("# web-access\n", encoding="utf-8")

    monkeypatch.chdir(repo_dir)
    monkeypatch.setenv("MMS_WEB_ACCESS_ROOT", str(web_access_root))
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_sync_codex_session_claude_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=False: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )

    env = mms_launchers._codex_gateway_env(
        {"id": "relay-a", "api_key": "sk-runtime"},
        "https://relay.example.com",
    )

    session_codex = Path(env["HOME"]) / ".codex"
    assert os.path.islink(session_codex / "skills" / "keep-skill")
    assert os.path.islink(session_codex / "skills" / "web-access")
    assert (session_codex / "skills" / "web-access" / "SKILL.md").read_text(encoding="utf-8") == "# web-access\n"


def test_codex_gateway_env_materializes_session_agent_browser_skill(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_codex = real_home / ".codex"
    (real_codex / "skills" / "keep-skill").mkdir(parents=True)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    agent_browser_root = tmp_path / "agent-browser"
    agent_browser_root.mkdir()
    (agent_browser_root / "SKILL.md").write_text("# agent-browser\n", encoding="utf-8")
    (agent_browser_root / "_meta.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.chdir(repo_dir)
    monkeypatch.setenv("MMS_AGENT_BROWSER_ROOT", str(agent_browser_root))
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_sync_codex_session_claude_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=False: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )

    env = mms_launchers._codex_gateway_env(
        {"id": "relay-a", "api_key": "sk-runtime"},
        "https://relay.example.com",
    )

    session_codex = Path(env["HOME"]) / ".codex"
    assert os.path.islink(session_codex / "skills" / "keep-skill")
    assert os.path.islink(session_codex / "skills" / "agent-browser")
    assert (session_codex / "skills" / "agent-browser" / "SKILL.md").read_text(encoding="utf-8") == "# agent-browser\n"


def test_overlay_toon_session_entries_merges_existing_session_skills(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "session-home"
    parent_dir = session_home / ".codex"
    existing_skills = tmp_path / "existing-skills"
    toon_root = tmp_path / "toon"
    parent_dir.mkdir(parents=True)
    (existing_skills / "keep-skill").mkdir(parents=True)
    toon_root.mkdir()
    (toon_root / "SKILL.md").write_text("# toon\n", encoding="utf-8")
    os.symlink(existing_skills, parent_dir / "skills")

    monkeypatch.setenv("MMS_TOON_ROOT", str(toon_root))

    mms_launchers._overlay_toon_session_entries(str(parent_dir), str(session_home))

    assert os.path.islink(parent_dir / "skills")
    assert os.path.islink(parent_dir / "skills" / "keep-skill")
    assert os.path.islink(parent_dir / "skills" / "toon")
    assert (parent_dir / "skills" / "toon" / "SKILL.md").read_text(encoding="utf-8") == "# toon\n"


def test_codex_gateway_env_materializes_session_toon_skill_and_wrapper(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    real_codex = real_home / ".codex"
    (real_codex / "skills" / "keep-skill").mkdir(parents=True)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toon_root = tmp_path / "toon"
    toon_root.mkdir()
    (toon_root / "SKILL.md").write_text("# toon\n", encoding="utf-8")
    toon_script = tmp_path / "mms-toon"
    toon_script.write_text("#!/bin/sh\nprintf 'TOON:\\n'\n", encoding="utf-8")
    toon_script.chmod(0o755)

    monkeypatch.chdir(repo_dir)
    monkeypatch.setenv("HOME", str(tmp_path / "isolated-home"))
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")
    monkeypatch.setenv("MMS_TOON_ROOT", str(toon_root))
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_sync_codex_session_claude_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=False: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: str(real_home))
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(mms_launchers, "_mms_toon_script_path", lambda: str(toon_script))
    monkeypatch.setattr(mms_launchers, "_SESSION_REAL_HOME_WRAPPER_COMMANDS", ())

    env = mms_launchers._codex_gateway_env(
        {"id": "relay-a", "api_key": "sk-runtime"},
        "https://relay.example.com",
    )

    session_codex = Path(env["HOME"]) / ".codex"
    toon_wrapper = Path(env["MMS_TOON_BIN"])
    assert os.path.islink(session_codex / "skills" / "keep-skill")
    assert os.path.islink(session_codex / "skills" / "toon")
    assert (session_codex / "skills" / "toon" / "SKILL.md").read_text(encoding="utf-8") == "# toon\n"
    assert toon_wrapper == Path(env["HOME"]) / ".mms" / "bin" / "mms-toon"
    assert toon_wrapper.exists()
    assert f'exec "{toon_script}" "$@"' in toon_wrapper.read_text(encoding="utf-8")
    assert env["PATH"].startswith(str(toon_wrapper.parent) + os.pathsep)


def test_build_claude_session_settings_rewrites_ecc_hooks_and_env_per_session(monkeypatch, tmp_path):
    import mms_launchers

    ecc_root = tmp_path / "everything-claude-code"
    (ecc_root / "hooks").mkdir(parents=True)
    (ecc_root / "commands").mkdir()
    (ecc_root / "skills").mkdir()
    (ecc_root / "hooks" / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {"type": "command", "command": "node scripts/hooks/session-start-bootstrap.js"},
                            ],
                        }
                    ],
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": "node scripts/hooks/pre-bash-dispatcher.js"},
                            ],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("MMS_ECC_ROOT", str(ecc_root))
    monkeypatch.setattr(mms_launchers, "_load_mms_claude_settings_template", lambda: {})
    monkeypatch.setattr(mms_launchers, "_load_global_claude_settings_template", lambda: {})
    monkeypatch.setattr(mms_launchers, "_default_session_mcp_servers", lambda: {})

    base_settings = {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {"type": "command", "command": "node /tmp/everything-claude-code/scripts/hooks/session-start-bootstrap.js"},
                        {"type": "command", "command": "/tmp/keep-session-start.sh"},
                    ]
                }
            ],
        },
        "env": {
            "CLAUDE_PLUGIN_ROOT": "/tmp/old-ecc",
            "ECC_PLUGIN_ROOT": "/tmp/old-ecc",
            "ECC_HOOK_PROFILE": "strict",
        },
    }

    disabled = mms_launchers._build_claude_session_settings(
        base_settings,
        enable_ecc=False,
        default_env={"KEEP_ME": "1"},
    )
    disabled_commands = [
        item["command"]
        for group in disabled["hooks"]["SessionStart"]
        for item in group["hooks"]
    ]
    assert "/tmp/keep-session-start.sh" in disabled_commands
    assert mms_launchers._CLAUDE_MINDKEEPER_SESSION_START_HOOK in disabled_commands
    assert "CLAUDE_PLUGIN_ROOT" not in disabled["env"]
    assert "ECC_PLUGIN_ROOT" not in disabled["env"]
    assert "ECC_HOOK_PROFILE" not in disabled["env"]
    assert disabled["env"]["KEEP_ME"] == "1"

    enabled = mms_launchers._build_claude_session_settings(
        base_settings,
        enable_ecc=True,
        default_env={"KEEP_ME": "1"},
    )
    enabled_session_start = [
        item["command"]
        for group in enabled["hooks"]["SessionStart"]
        for item in group["hooks"]
    ]
    enabled_pretool = [
        item["command"]
        for group in enabled["hooks"]["PreToolUse"]
        for item in group["hooks"]
    ]
    assert "/tmp/keep-session-start.sh" in enabled_session_start
    assert "node scripts/hooks/session-start-bootstrap.js" in enabled_session_start
    assert "node scripts/hooks/pre-bash-dispatcher.js" in enabled_pretool
    assert enabled["env"]["CLAUDE_PLUGIN_ROOT"] == str(ecc_root)
    assert enabled["env"]["ECC_PLUGIN_ROOT"] == str(ecc_root)
    assert enabled["env"]["ECC_HOOK_PROFILE"] == "standard"
    assert enabled["env"]["KEEP_ME"] == "1"


def test_sanitize_global_snapshot_strips_session_only_hooks_and_hive_server():
    import mms_launchers

    snapshot = {
        "env": {"HTTP_PROXY": "http://127.0.0.1:7890"},
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "",
                    "commands": [
                        "/tmp/keep-session-start.sh",
                        mms_launchers._CLAUDE_MINDKEEPER_SESSION_START_HOOK,
                    ],
                }
            ],
            "Stop": [
                {
                    "matcher": "",
                    "commands": [mms_launchers._CLAUDE_MINDKEEPER_SESSION_END_HOOK],
                }
            ],
            "UserPromptSubmit": [
                {
                    "matcher": "",
                    "commands": [mms_launchers._CLAUDE_MINDKEEPER_TOKEN_MONITOR_HOOK],
                }
            ],
            "PreToolUse": [
                {
                    "matcher": "WebFetch",
                    "commands": [
                        "/tmp/keep-webfetch.sh",
                        mms_launchers._CLAUDE_FEISHU_WEBFETCH_GUARD_HOOK,
                    ],
                }
            ],
        },
        "mcpServers": {
            "hive": {"command": "/tmp/hive/bin/mcp-server.sh", "args": [], "type": "stdio"},
            "mindkeeper": {"command": "node", "args": ["/tmp/mindkeeper/dist/server.js"], "type": "stdio"},
        },
    }

    sanitized = mms_launchers._sanitize_global_snapshot(snapshot)

    assert "env" not in sanitized
    assert sanitized["hooks"]["SessionStart"] == [
        {"matcher": "", "commands": ["/tmp/keep-session-start.sh"]}
    ]
    assert sanitized["hooks"]["PreToolUse"] == [
        {"matcher": "WebFetch", "commands": ["/tmp/keep-webfetch.sh"]}
    ]
    assert "Stop" not in sanitized["hooks"]
    assert "UserPromptSubmit" not in sanitized["hooks"]
    assert "hive" not in sanitized["mcpServers"]
    assert sanitized["mcpServers"]["mindkeeper"]["args"] == ["/tmp/mindkeeper/dist/server.js"]


def test_overlay_ecc_session_entries_merges_session_and_ecc_assets(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "session"
    parent_dir = session_home / ".claude"
    parent_dir.mkdir(parents=True)
    global_assets = tmp_path / "global-assets"
    (global_assets / "commands").mkdir(parents=True)
    (global_assets / "skills").mkdir()
    (global_assets / "commands" / "keep.md").write_text("keep\n", encoding="utf-8")
    (global_assets / "skills" / "keep-skill").mkdir()
    os.symlink(global_assets / "commands", parent_dir / "commands")
    os.symlink(global_assets / "skills", parent_dir / "skills")

    ecc_root = tmp_path / "everything-claude-code"
    (ecc_root / "hooks").mkdir(parents=True)
    (ecc_root / "hooks" / "hooks.json").write_text('{"hooks":{}}', encoding="utf-8")
    (ecc_root / "commands").mkdir()
    (ecc_root / "commands" / "feature-development.md").write_text("# feature\n", encoding="utf-8")
    (ecc_root / "skills" / "core-skill").mkdir(parents=True)
    (ecc_root / "skills" / "core-skill" / "SKILL.md").write_text("# core\n", encoding="utf-8")
    (ecc_root / ".agents" / "skills" / "agent-skill").mkdir(parents=True)
    (ecc_root / ".agents" / "skills" / "agent-skill" / "SKILL.md").write_text("# agent\n", encoding="utf-8")
    (ecc_root / ".claude" / "skills" / "ecc-meta").mkdir(parents=True)
    (ecc_root / ".claude" / "skills" / "ecc-meta" / "SKILL.md").write_text("# meta\n", encoding="utf-8")
    (ecc_root / ".claude" / "commands").mkdir(parents=True)
    (ecc_root / ".claude" / "commands" / "feature-development.md").write_text("# claude cmd\n", encoding="utf-8")
    (ecc_root / "rules" / "common").mkdir(parents=True)
    (ecc_root / "rules" / "common" / "hooks.md").write_text("# hooks\n", encoding="utf-8")
    (ecc_root / ".claude" / "rules").mkdir(parents=True)
    (ecc_root / ".claude" / "rules" / "everything-claude-code-guardrails.md").write_text("# guardrails\n", encoding="utf-8")

    monkeypatch.setenv("MMS_ECC_ROOT", str(ecc_root))

    mms_launchers._overlay_ecc_session_entries(
        str(parent_dir),
        str(session_home),
        enable_ecc=True,
    )

    assert os.path.islink(parent_dir / "commands")
    assert os.path.islink(parent_dir / "skills")
    assert os.path.islink(parent_dir / "rules")
    assert os.path.islink(parent_dir / "commands" / "keep.md")
    assert os.path.islink(parent_dir / "commands" / "feature-development.md")
    assert os.path.islink(parent_dir / "skills" / "keep-skill")
    assert os.path.islink(parent_dir / "skills" / "core-skill")
    assert os.path.islink(parent_dir / "skills" / "agent-skill")
    assert os.path.islink(parent_dir / "skills" / "ecc-meta")
    assert os.path.islink(parent_dir / "rules" / "common")
    assert os.path.islink(parent_dir / "rules" / "everything-claude-code-guardrails.md")


def test_claude_gateway_env_materializes_session_ecc_assets_and_env(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "gateway-session"
    session_home.mkdir()
    real_home = tmp_path / "real-home"
    (real_home / ".local").mkdir(parents=True)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)

    ecc_root = tmp_path / "everything-claude-code"
    (ecc_root / "hooks").mkdir(parents=True)
    (ecc_root / "hooks" / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {"type": "command", "command": "node scripts/hooks/session-start-bootstrap.js"},
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (ecc_root / "commands").mkdir()
    (ecc_root / "commands" / "feature-development.md").write_text("# feature\n", encoding="utf-8")
    (ecc_root / "skills" / "core-skill").mkdir(parents=True)
    (ecc_root / "skills" / "core-skill" / "SKILL.md").write_text("# core\n", encoding="utf-8")
    (ecc_root / "rules" / "common").mkdir(parents=True)
    (ecc_root / "rules" / "common" / "hooks.md").write_text("# hooks\n", encoding="utf-8")

    monkeypatch.setenv("MMS_ECC_ROOT", str(ecc_root))
    monkeypatch.setattr(
        mms_launchers,
        "_reserve_session_home",
        lambda *args, **kwargs: (str(session_home), 0, 1),
    )
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_claude_library_entries", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_prepare_claude_session_tree",
        lambda _home, claude_dir, **_kwargs: os.makedirs(claude_dir, exist_ok=True),
    )
    monkeypatch.setattr(mms_launchers, "_pick_gateway_model", lambda *args, **kwargs: "kimi-for-coding")
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(mms_launchers, "_claude_route_status_paths", lambda: [str(tmp_path / "route-status.json")])
    monkeypatch.setattr(mms_launchers, "list_indexed_sessions", lambda _cli="claude": [])

    env = mms_launchers._claude_gateway_env(
        {"id": "relay-a", "api_key": "sk-runtime", "ecc_mode": "enable"},
        base_url="https://relay.example.com",
        auth_token="bridge-token",
        selected_model="kimi-for-coding",
        display_model="kimi-for-coding",
    )

    assert env["CLAUDE_PLUGIN_ROOT"] == str(ecc_root)
    assert env["ECC_PLUGIN_ROOT"] == str(ecc_root)
    assert env["ECC_HOOK_PROFILE"] == "standard"
    settings = json.loads((session_home / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings["env"]["CLAUDE_PLUGIN_ROOT"] == str(ecc_root)
    assert settings["env"]["ECC_PLUGIN_ROOT"] == str(ecc_root)
    session_start_commands = [
        item["command"]
        for group in settings["hooks"]["SessionStart"]
        for item in group["hooks"]
    ]
    assert "node scripts/hooks/session-start-bootstrap.js" in session_start_commands
    assert os.path.islink(session_home / ".claude" / "commands" / "feature-development.md")
    assert os.path.islink(session_home / ".claude" / "skills" / "core-skill")
    assert os.path.islink(session_home / ".claude" / "rules" / "common")


def test_claude_gateway_env_materializes_session_web_access_skill(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "gateway-session"
    session_home.mkdir()
    real_home = tmp_path / "real-home"
    (real_home / ".local").mkdir(parents=True)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    web_access_root = tmp_path / "web-access"
    (web_access_root / "references").mkdir(parents=True)
    (web_access_root / "SKILL.md").write_text("# web-access\n", encoding="utf-8")

    monkeypatch.chdir(repo_dir)
    monkeypatch.setenv("MMS_WEB_ACCESS_ROOT", str(web_access_root))
    monkeypatch.setattr(
        mms_launchers,
        "_reserve_session_home",
        lambda *args, **kwargs: (str(session_home), 0, 1),
    )
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_claude_library_entries", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_prepare_claude_session_tree",
        lambda _home, claude_dir, **_kwargs: os.makedirs(claude_dir, exist_ok=True),
    )
    monkeypatch.setattr(mms_launchers, "_pick_gateway_model", lambda *args, **kwargs: "kimi-for-coding")
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(mms_launchers, "_claude_route_status_paths", lambda: [str(tmp_path / "route-status.json")])
    monkeypatch.setattr(mms_launchers, "list_indexed_sessions", lambda _cli="claude": [])

    env = mms_launchers._claude_gateway_env(
        {"id": "relay-a", "api_key": "sk-runtime"},
        base_url="https://relay.example.com",
        auth_token="bridge-token",
        selected_model="kimi-for-coding",
        display_model="kimi-for-coding",
    )

    assert env["HOME"] == str(session_home)
    assert os.path.islink(session_home / ".claude" / "skills" / "web-access")
    assert (session_home / ".claude" / "skills" / "web-access" / "SKILL.md").read_text(encoding="utf-8") == "# web-access\n"
    packet = json.loads(Path(env["MMS_SESSION_PACKET_JSON"]).read_text(encoding="utf-8"))
    settings = json.loads((session_home / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert packet["cli"] == "claude"
    assert packet["model"]["primary"] == "kimi-for-coding"
    assert settings["env"]["MMS_SESSION_PACKET_JSON"] == env["MMS_SESSION_PACKET_JSON"]
    assert env["MMS_SESSION_PACKET_FORMAT"] == "toon"


def test_claude_gateway_env_materializes_session_toon_skill_and_export(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "gateway-session"
    session_home.mkdir()
    real_home = tmp_path / "real-home"
    (real_home / ".local").mkdir(parents=True)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    toon_root = tmp_path / "toon"
    toon_root.mkdir()
    (toon_root / "SKILL.md").write_text("# toon\n", encoding="utf-8")
    toon_script = tmp_path / "mms-toon"
    toon_script.write_text("#!/bin/sh\nprintf 'TOON:\\n'\n", encoding="utf-8")
    toon_script.chmod(0o755)

    monkeypatch.chdir(repo_dir)
    monkeypatch.setenv("HOME", str(tmp_path / "isolated-home"))
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")
    monkeypatch.setenv("MMS_TOON_ROOT", str(toon_root))
    monkeypatch.setattr(
        mms_launchers,
        "_reserve_session_home",
        lambda *args, **kwargs: (str(session_home), 0, 1),
    )
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_claude_library_entries", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_prepare_claude_session_tree",
        lambda _home, claude_dir, **_kwargs: os.makedirs(claude_dir, exist_ok=True),
    )
    monkeypatch.setattr(mms_launchers, "_pick_gateway_model", lambda *args, **kwargs: "kimi-for-coding")
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: str(real_home))
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(mms_launchers, "_mms_toon_script_path", lambda: str(toon_script))
    monkeypatch.setattr(mms_launchers, "_SESSION_REAL_HOME_WRAPPER_COMMANDS", ())
    monkeypatch.setattr(mms_launchers, "_claude_route_status_paths", lambda: [str(tmp_path / "route-status.json")])
    monkeypatch.setattr(mms_launchers, "list_indexed_sessions", lambda _cli="claude": [])

    env = mms_launchers._claude_gateway_env(
        {"id": "relay-a", "api_key": "sk-runtime"},
        base_url="https://relay.example.com",
        auth_token="bridge-token",
        selected_model="kimi-for-coding",
        display_model="kimi-for-coding",
    )

    toon_wrapper = Path(env["MMS_TOON_BIN"])
    assert env["HOME"] == str(session_home)
    assert os.path.islink(session_home / ".claude" / "skills" / "toon")
    assert (session_home / ".claude" / "skills" / "toon" / "SKILL.md").read_text(encoding="utf-8") == "# toon\n"
    assert toon_wrapper == session_home / ".mms" / "bin" / "mms-toon"
    assert toon_wrapper.exists()
    assert f'exec "{toon_script}" "$@"' in toon_wrapper.read_text(encoding="utf-8")
    assert env["PATH"].startswith(str(toon_wrapper.parent) + os.pathsep)


def test_prepare_claude_session_tree_keeps_static_tooling_allowlist(monkeypatch, tmp_path):
    import mms_launchers

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)

    raw_root = tmp_path / "project-store"
    raw_root.mkdir()
    for entry in mms_launchers.CLAUDE_PERSISTENT_ENTRIES:
        (raw_root / entry).mkdir(exist_ok=True)

    monkeypatch.setattr(
        mms_launchers,
        "ensure_claude_project_store",
        lambda cwd, account_id="": {"project_key": "project-key"},
    )
    monkeypatch.setattr(
        mms_launchers,
        "claude_raw_entry_path",
        lambda entry, cwd, account_id="": raw_root / entry,
    )
    monkeypatch.setattr(mms_launchers, "record_claude_session_start", lambda **kwargs: None)
    monkeypatch.setattr(mms_launchers, "write_slot_marker", lambda *args, **kwargs: None)

    source_claude_dir = tmp_path / "source-claude"
    source_claude_dir.mkdir()
    (source_claude_dir / ".mcp.json").write_text('{"mcpServers":{"demo":{}}}\n', encoding="utf-8")
    (source_claude_dir / "CLAUDE.md").write_text("# Claude\n", encoding="utf-8")
    (source_claude_dir / "RTK.md").write_text("# RTK\n", encoding="utf-8")
    (source_claude_dir / "commands").mkdir()
    (source_claude_dir / "hooks").mkdir()
    (source_claude_dir / "skills").mkdir()
    (source_claude_dir / "agents").mkdir()

    session_claude_dir = tmp_path / "session" / ".claude"
    session_claude_dir.mkdir(parents=True)
    os.symlink(source_claude_dir / "agents", session_claude_dir / "agents")

    mms_launchers._prepare_claude_session_tree(
        str(tmp_path / "session"),
        str(session_claude_dir),
        account_id="claude-a",
        source_claude_dir=str(source_claude_dir),
    )

    assert not (session_claude_dir / "agents").exists()
    assert not os.path.islink(session_claude_dir / "agents")
    for entry in mms_launchers._CLAUDE_SESSION_SOURCE_ENTRY_ALLOWLIST:
        assert os.path.islink(session_claude_dir / entry)
    for entry in mms_launchers.CLAUDE_PERSISTENT_ENTRIES:
        assert os.path.islink(session_claude_dir / entry)


def test_prepare_claude_session_tree_persists_claude_projects_for_resume(monkeypatch, tmp_path):
    import mms_launchers

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)

    raw_root = tmp_path / "project-store"
    for entry in mms_launchers.CLAUDE_PERSISTENT_ENTRIES:
        target = raw_root / entry
        if entry.endswith(".jsonl"):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
        else:
            target.mkdir(parents=True, exist_ok=True)

    slots_root = tmp_path / "slots"
    old_slot = slots_root / "111"
    old_projects = old_slot / ".claude" / "projects" / "-tmp-repo"
    old_projects.mkdir(parents=True)
    (old_slot / ".mms_slot.json").write_text(
        json.dumps(
            {
                "cwd": str(repo_dir.resolve()),
                "project_key": "project-key",
                "account_id": "relay-a",
            }
        ),
        encoding="utf-8",
    )
    old_resume_file = old_projects / "old-session.jsonl"
    old_resume_file.write_text('{"type":"summary","summary":"old"}\n', encoding="utf-8")

    real_home = tmp_path / "real-home"
    real_project_name = mms_launchers._claude_project_resume_dir_names(str(repo_dir.resolve()))[0]
    real_projects = real_home / ".claude" / "projects" / real_project_name
    real_projects.mkdir(parents=True)
    real_resume_file = real_projects / "native-session.jsonl"
    real_resume_file.write_text('{"type":"summary","summary":"native"}\n', encoding="utf-8")

    monkeypatch.setattr(
        mms_launchers,
        "ensure_claude_project_store",
        lambda cwd, account_id="": {"project_key": "project-key"},
    )
    monkeypatch.setattr(
        mms_launchers,
        "claude_raw_entry_path",
        lambda entry, cwd, account_id="": raw_root / entry,
    )
    monkeypatch.setattr(
        mms_launchers,
        "_claude_slot_roots_for_resume_backfill",
        lambda _account_id: [str(slots_root)],
    )
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(mms_launchers, "record_claude_session_start", lambda **kwargs: None)
    monkeypatch.setattr(mms_launchers, "write_slot_marker", lambda *args, **kwargs: None)

    session_home = tmp_path / "session"
    session_claude_dir = session_home / ".claude"
    local_projects = session_claude_dir / "projects" / "-tmp-repo"
    local_projects.mkdir(parents=True)
    local_resume_file = local_projects / "current-session.jsonl"
    local_resume_file.write_text('{"type":"summary","summary":"current"}\n', encoding="utf-8")

    mms_launchers._prepare_claude_session_tree(
        str(session_home),
        str(session_claude_dir),
        account_id="relay-a",
    )

    assert os.path.islink(session_claude_dir / "projects")
    assert os.path.realpath(session_claude_dir / "projects") == str((raw_root / "projects").resolve())
    assert (raw_root / "projects" / "-tmp-repo" / "old-session.jsonl").read_text(encoding="utf-8") == old_resume_file.read_text(encoding="utf-8")
    assert (raw_root / "projects" / "-tmp-repo" / "current-session.jsonl").read_text(encoding="utf-8") == local_resume_file.read_text(encoding="utf-8")
    assert (raw_root / "projects" / real_project_name / "native-session.jsonl").read_text(encoding="utf-8") == real_resume_file.read_text(encoding="utf-8")


def test_link_claude_library_entries_replaces_broad_library_symlink(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    keychains = real_home / "Library" / "Keychains"
    keychains.mkdir(parents=True)
    (real_home / "Library" / "Preferences").mkdir()

    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )

    session_home = tmp_path / "session"
    session_home.mkdir()
    os.symlink(real_home / "Library", session_home / "Library")

    mms_launchers._link_claude_library_entries(str(session_home))

    session_library = session_home / "Library"
    assert session_library.is_dir()
    assert not session_library.is_symlink()
    assert os.path.islink(session_library / "Keychains")
    assert not (session_library / "Preferences").exists()


def test_finalize_claude_slot_stale_cleanup_skips_sync(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "slot" / "1234"
    session_home.mkdir(parents=True)

    sync_calls = []
    monkeypatch.setattr(
        mms_launchers,
        "read_slot_marker",
        lambda _path: {"cwd": str(tmp_path), "account_id": "claude-a", "account_home": str(tmp_path / "account")},
    )
    monkeypatch.setattr(
        mms_launchers,
        "_sync_claude_session_state_to_account_home",
        lambda *args, **kwargs: sync_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(mms_launchers, "finalize_claude_session", lambda **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_record_account_guard_finalize", lambda *args, **kwargs: None)

    mms_launchers._finalize_claude_slot(str(session_home), stale_cleanup=True)

    assert sync_calls == []


def test_claude_guard_runtime_uses_gateway_home_for_api_key(monkeypatch, tmp_path):
    import mms_launchers

    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )

    result = mms_launchers._claude_guard_runtime({"id": "relay-a", "auth_mode": "api_key"})

    assert result["home_dir"] == str(tmp_path / ".config" / "mms" / "claude-gateway")


def test_launch_cli_enforces_network_guard_for_sensitive_claude_api_key_bypass(monkeypatch):
    import mms_launchers

    guard_calls = []
    account_guard_calls = []

    monkeypatch.setattr(mms_launchers, "validate_provider_for_cli", lambda cli, runtime: None)
    monkeypatch.setattr(
        mms_launchers,
        "_build_account_guard_report",
        lambda runtime: account_guard_calls.append(runtime) or {"status": "stable", "profile": {}, "active_sessions_after": 1, "score": 100, "drift_fields": []},
    )
    monkeypatch.setattr(
        mms_launchers,
        "_enforce_claude_network_guard_or_exit",
        lambda runtime, require_proxy=False: guard_calls.append((runtime.get("id"), require_proxy)),
    )
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["claude-sonnet-4-6"], "base_source": "remote"},
    )
    monkeypatch.setitem(mms_launchers.LAUNCHERS, "claude", lambda model_info, runtime, once=False: None)

    mms_launchers.launch_cli(
        "claude",
        {"model": "claude-sonnet-4-6"},
        {
            "id": "relay-a",
            "name": "relay-a",
            "auth_mode": "api_key",
            "api_key": "sk-test",
            "base_url": "https://relay.example.com",
            "skip_anthropic_probe": True,
            "bypass": True,
        },
        once=True,
    )

    assert guard_calls == [("relay-a", True)]
    assert account_guard_calls == []


def test_launch_cli_does_not_require_proxy_for_regular_api_key_bypass(monkeypatch):
    import mms_launchers

    guard_calls = []
    account_guard_calls = []

    monkeypatch.setattr(mms_launchers, "validate_provider_for_cli", lambda cli, runtime: None)
    monkeypatch.setattr(
        mms_launchers,
        "_build_account_guard_report",
        lambda runtime: account_guard_calls.append(runtime) or {"status": "stable", "profile": {}, "active_sessions_after": 1, "score": 100, "drift_fields": []},
    )
    monkeypatch.setattr(
        mms_launchers,
        "_enforce_claude_network_guard_or_exit",
        lambda runtime, require_proxy=False: guard_calls.append((runtime.get("id"), require_proxy)),
    )
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda runtime, emit_output=False: {"models": ["claude-sonnet-4-6"], "base_source": "remote"},
    )
    monkeypatch.setitem(mms_launchers.LAUNCHERS, "claude", lambda model_info, runtime, once=False: None)

    mms_launchers.launch_cli(
        "claude",
        {"model": "claude-sonnet-4-6"},
        {
            "id": "newapi-personal-tokyo",
            "name": "newapi-personal-tokyo",
            "auth_mode": "api_key",
            "api_key": "sk-test",
            "base_url": "https://relay.example.com",
            "bypass": True,
        },
        once=True,
    )

    assert guard_calls == [("newapi-personal-tokyo", False)]
    assert account_guard_calls == []


def test_claude_bypass_requires_proxy_only_for_claude_account_or_sensitive_provider():
    import mms_launchers

    assert mms_launchers._claude_bypass_requires_proxy({"auth_mode": "oauth", "cli": "claude"}) is True
    assert mms_launchers._claude_bypass_requires_proxy({"auth_mode": "oauth", "cli": "gemini"}) is False
    assert mms_launchers._claude_bypass_requires_proxy({"auth_mode": "oauth", "cli": "codex"}) is False
    assert mms_launchers._claude_bypass_requires_proxy({"auth_mode": "api_key", "skip_anthropic_probe": True}) is True
    assert mms_launchers._claude_bypass_requires_proxy({"auth_mode": "api_key"}) is False


def test_resolve_anthropic_base_url_cache_is_scoped_by_configured_url(monkeypatch):
    import mms_launchers

    old_cache_key = mms_launchers._anthropic_cache_key("relay-a", "https://old.example.com")
    now_iso = datetime.now().isoformat()
    saved_cache = {}

    monkeypatch.setattr(
        mms_launchers,
        "_load_anthropic_url_file_cache",
        lambda: {old_cache_key: {"url": "https://old.example.com", "ts": now_iso}},
    )
    monkeypatch.setattr(mms_launchers, "_save_anthropic_url_file_cache", lambda payload: saved_cache.update(payload))
    mms_launchers._ANTHROPIC_URL_CACHE.clear()

    resolved, method = mms_launchers._resolve_anthropic_base_url(
        {
            "id": "relay-a",
            "api_key": "sk-test",
            "anthropic_base_url": "https://new.example.com",
            "skip_anthropic_probe": True,
        }
    )

    assert resolved == "https://new.example.com"
    assert method == "config_bypass"
    assert mms_launchers._anthropic_cache_key("relay-a", "https://new.example.com") in saved_cache


def test_load_probe_file_cache_marks_stale_and_preserves_error(monkeypatch, tmp_path):
    import mms_core

    monkeypatch.setattr(mms_core, "_PROBE_FILE_CACHE_DIR", str(tmp_path))
    cache_path = Path(mms_core._probe_file_cache_path("provider-a"))
    cache_path.write_text(
        json.dumps(
            {
                "raw_models": [],
                "working_url": "https://relay.example.com/v1",
                "base_source": "remote",
                "error": "probe failed",
                "error_kind": "http_error",
            }
        ),
        encoding="utf-8",
    )
    stale_ts = datetime.now().timestamp() - (mms_core._PROBE_FILE_CACHE_NEGATIVE_TTL + 10)
    os.utime(cache_path, (stale_ts, stale_ts))

    cached = mms_core._load_probe_file_cache("provider-a", allow_stale=True)
    base_result = mms_core._base_probe_result_from_cache("provider-a", cached)

    assert cached["is_stale"] is True
    assert base_result["error"] == "probe failed"
    assert base_result["error_kind"] == "http_error"
    assert base_result["is_stale"] is True


def test_provider_candidates_ignore_stale_probe_cache(monkeypatch):
    import mms_core

    monkeypatch.setattr(
        mms_core,
        "_load_probe_file_cache",
        lambda provider_id, allow_stale=False: (
            {"raw_models": ["fresh-model"], "is_stale": False}
            if provider_id == "fresh"
            else {"raw_models": ["stale-model"], "is_stale": True}
        ),
    )
    monkeypatch.setattr(mms_core, "resolve_provider_context", lambda cfg, provider_id: {"id": provider_id})

    candidates = mms_core._provider_candidates(
        {"providers": [{"id": "fresh"}, {"id": "stale"}]},
        {"id": "default"},
        ["default-model"],
    )

    assert candidates[1] == ({"id": "fresh"}, ["fresh-model"])
    assert candidates[2] == ({"id": "stale"}, None)


def test_provider_options_for_model_accepts_openai_base_url_only(monkeypatch):
    import mms_core

    provider = {
        "id": "relay-openai-only",
        "enabled": True,
        "openai_base_url": "https://relay.example.com/v1",
        "api_key": "sk-test",
        "protocols": ["responses", "openai_chat_completions"],
        "supported_clis": ["codex"],
        "models_endpoint": "manual",
        "fallback_models": ["gpt-5.4"],
    }
    monkeypatch.setattr(
        mms_core,
        "_provider_candidates",
        lambda cfg, default_provider, default_models: [(provider, ["gpt-5.4"])],
    )

    options = mms_core._provider_options_for_model(
        {},
        "codex",
        {"id": "default"},
        ["gpt-5.4"],
        model_info={"model": "gpt-5.4"},
    )

    assert options
    assert options[0]["id"] == "relay-openai-only"


def test_bridge_fallback_cache_is_scoped_by_gateway_url(monkeypatch):
    import mms_bridge

    monkeypatch.setattr(
        mms_bridge,
        "_save_bridge_mode_cache",
        lambda cache: setattr(mms_bridge, "_bridge_mode_cache_memory", dict(cache)),
    )
    mms_bridge._bridge_mode_cache_memory = {}

    mms_bridge._record_bridge_fallback("relay-a", "gpt-5.4", "https://gw-a.example.com/v1")

    assert mms_bridge._needs_chatcompletions_bridge("relay-a", "gpt-5.4", "https://gw-a.example.com/v1") is True
    assert mms_bridge._needs_chatcompletions_bridge("relay-a", "gpt-5.4", "https://gw-b.example.com/v1") is False


def test_claude_passthrough_rules_use_minimal_headers_for_sensitive_provider():
    import mms_bridge

    header_names, header_prefixes = mms_bridge._claude_passthrough_rules(
        types.SimpleNamespace(
            minimal_claude_header_passthrough=True,
            strip_upstream_user_agent=False,
        )
    )

    assert header_names == mms_bridge._CLAUDE_SENSITIVE_HEADER_PASSTHROUGH
    assert header_prefixes == ()


def test_claude_passthrough_rules_drop_anthropic_beta_for_domestic_models():
    import mms_bridge

    header_names, header_prefixes = mms_bridge._claude_passthrough_rules(
        types.SimpleNamespace(
            minimal_claude_header_passthrough=False,
            strip_upstream_user_agent=False,
        ),
        "kimi-for-coding",
    )

    assert "anthropic-version" in header_names
    assert "anthropic-beta" not in header_names
    assert header_prefixes == mms_bridge._CLAUDE_HEADER_PREFIX_PASSTHROUGH


@pytest.mark.parametrize(
    ("model_name", "expected"),
    [
        ("deepseek-v4-pro", True),
        ("kimi-for-coding", True),
        ("glm-5.1", True),
        ("MiniMax-M2.7", True),
        ("qwen3.5-plus", True),
        ("qwen3-max-2026-01-23", True),
        ("qwen3-coder-plus", False),
        ("mimo-v2-pro", False),
    ],
)
def test_domestic_model_supports_thinking_capability_allowlist(model_name, expected):
    import mms_bridge

    assert mms_bridge._domestic_model_supports_thinking(model_name) is expected
    assert mms_bridge._should_strip_domestic_thinking_signals(model_name) is (not expected)


def test_strip_domestic_thinking_signals_removes_thinking_payload_fields():
    import mms_bridge

    payload = {
        "thinking": {"type": "enabled", "budget_tokens": 2048},
        "output_config": {"effort": "high"},
        "system": [
            {"type": "text", "text": "system"},
            {"type": "thinking", "thinking": "hidden"},
        ],
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "abc", "signature": "sig"},
                    {"type": "text", "text": "keep"},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "redacted_thinking", "data": "secret"},
                    {"type": "text", "text": "still here"},
                ],
            },
        ],
    }

    mms_bridge._strip_domestic_thinking_signals(payload)

    assert "thinking" not in payload
    assert payload["output_config"] == {"effort": "high"}
    assert payload["system"] == [{"type": "text", "text": "system"}]
    assert payload["messages"][0]["content"] == [{"type": "text", "text": "keep"}]
    assert payload["messages"][1]["content"] == [{"type": "text", "text": "still here"}]


def test_apply_domestic_reasoning_controls_preserves_supported_thinking_and_sets_deepseek_effort():
    import mms_bridge

    payload = {
        "thinking": {"type": "enabled", "budget_tokens": 2048},
        "messages": [{"role": "assistant", "content": [{"type": "thinking", "thinking": "abc"}]}],
    }

    mms_bridge._apply_domestic_reasoning_controls(
        payload,
        "deepseek-v4-pro",
        thinking_enabled=True,
        reasoning_effort="xhigh",
    )

    assert payload["thinking"]["budget_tokens"] == 2048
    assert payload["messages"][0]["content"][0]["type"] == "thinking"
    assert payload["output_config"] == {"effort": "high"}


def test_apply_domestic_reasoning_controls_disables_thinking_and_removes_effort():
    import mms_bridge

    payload = {
        "thinking": {"type": "enabled", "budget_tokens": 2048},
        "output_config": {"effort": "high", "format": "markdown"},
        "messages": [{"role": "assistant", "content": [{"type": "thinking", "thinking": "abc"}]}],
    }

    mms_bridge._apply_domestic_reasoning_controls(
        payload,
        "deepseek-v4-pro",
        thinking_enabled=False,
        reasoning_effort="high",
    )

    assert "thinking" not in payload
    assert payload["output_config"] == {"format": "markdown"}
    assert payload["messages"][0]["content"] == []


def test_responses_proxy_empty_body_fallback_does_not_cache(monkeypatch):
    import mms_bridge

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def read():
            return b""

        @staticmethod
        def close():
            return None

    recorded = []
    fallback_calls = []

    mms_bridge.httpx = types.SimpleNamespace(stream=lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)
    monkeypatch.setattr(mms_bridge, "_needs_chatcompletions_bridge", lambda *args, **kwargs: False)
    monkeypatch.setattr(mms_bridge, "_record_bridge_fallback", lambda *args, **kwargs: recorded.append((args, kwargs)))

    raw_body = json.dumps({"model": "gpt-5.4"}).encode("utf-8")
    handler = mms_bridge._ResponsesProxyHandler.__new__(mms_bridge._ResponsesProxyHandler)
    handler.path = "/v1/responses"
    handler.headers = {
        "content-length": str(len(raw_body)),
        "authorization": "Bearer bridge-token",
    }
    handler.rfile = io.BytesIO(raw_body)
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        bridge_token="bridge-token",
        gateway_key="gateway-key",
        gateway_url="https://gw-a.example.com/v1",
        model_name="gpt-5.4",
        provider_id="relay-a",
    )
    handler.send_response = lambda *args, **kwargs: None
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda *args, **kwargs: None
    handler._do_chatcompletions_fallback = lambda *args, **kwargs: fallback_calls.append((args, kwargs))

    handler.do_POST()

    assert fallback_calls
    assert recorded == []


def test_copy_claude_state_json_oauth_mode_allowlists_auth_state(tmp_path):
    import mms_launchers

    src = tmp_path / "src.json"
    dst = tmp_path / "nested" / "dst.json"
    src.write_text(
        json.dumps(
            {
                "userID": "user-1",
                "firstStartTime": "2026-04-15T10:00:00Z",
                "numStartups": 7,
                "bypassPermissionsModeAccepted": True,
                "alwaysThinkingEnabled": True,
                "hasCompletedOnboarding": True,
                "lastOnboardingVersion": "1.2.3",
                "lastReleaseNotesSeen": "2.1.110",
                "installMethod": "native",
                "effortCalloutV2Dismissed": True,
                "migrationVersion": 11,
                "officialMarketplaceAutoInstallAttempted": True,
                "officialMarketplaceAutoInstalled": True,
                "tipsHistory": {
                    "theme-command": 2,
                    "terminal-setup": 1,
                },
                "oauthAccount": {
                    "accountUuid": "acct-1",
                    "emailAddress": "u@example.com",
                    "organizationUuid": "org-1",
                    "displayName": "User",
                    "workspaceRole": "owner",
                    "unexpected": "drop-me",
                },
                "claudeAiOauth": {
                    "accessToken": "tok-1",
                    "refreshToken": "refresh-1",
                    "expiresAt": "2026-04-16T10:00:00Z",
                    "emailAddress": "u@example.com",
                    "extra": "drop-me",
                },
                "provider": "gateway",
                "api_key": "sk-test",
                "projects": {
                    "/tmp/repo": {
                        "hasCompletedProjectOnboarding": True,
                        "hasClaudeMdExternalIncludesApproved": True,
                        "hasClaudeMdExternalIncludesWarningShown": True,
                        "projectOnboardingSeenCount": 2,
                        "lastSessionId": "abc",
                    }
                },
                "customApiKeyResponses": {"demo": "x"},
                "anonymousId": "anon-1",
            }
        ),
        encoding="utf-8",
    )

    mms_launchers._copy_claude_state_json(str(src), str(dst), mode="oauth")

    result = json.loads(dst.read_text(encoding="utf-8"))
    assert result == {
        "userID": "user-1",
        "firstStartTime": "2026-04-15T10:00:00Z",
        "numStartups": 7,
        "bypassPermissionsModeAccepted": True,
        "alwaysThinkingEnabled": True,
        "hasCompletedOnboarding": True,
        "lastOnboardingVersion": "1.2.3",
        "lastReleaseNotesSeen": "2.1.110",
        "installMethod": "native",
        "effortCalloutV2Dismissed": True,
        "migrationVersion": 11,
        "officialMarketplaceAutoInstallAttempted": True,
        "officialMarketplaceAutoInstalled": True,
        "tipsHistory": {
            "theme-command": 2,
            "terminal-setup": 1,
        },
        "oauthAccount": {
            "accountUuid": "acct-1",
            "emailAddress": "u@example.com",
            "organizationUuid": "org-1",
            "displayName": "User",
            "workspaceRole": "owner",
        },
        "claudeAiOauth": {
            "accessToken": "tok-1",
            "refreshToken": "refresh-1",
            "expiresAt": "2026-04-16T10:00:00Z",
            "emailAddress": "u@example.com",
        },
        "projects": {
            str(Path("/tmp/repo").resolve()): {
                "hasCompletedProjectOnboarding": True,
                "hasClaudeMdExternalIncludesApproved": True,
                "hasClaudeMdExternalIncludesWarningShown": True,
                "projectOnboardingSeenCount": 2,
            }
        },
    }


def test_account_env_scrubs_claude_oauth_parent_env(monkeypatch, tmp_path):
    import mms_launchers

    account_home = tmp_path / "account-home"
    real_home = tmp_path / "real-home"
    real_home.mkdir()

    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-parent")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://relay.example.com")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("CLAUDE_CODE_SUBAGENT_MODEL", "claude-haiku-4-5")
    monkeypatch.setenv("CLAUDE_CODE_ATTRIBUTION_HEADER", "1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7890")

    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_claude_library_entries", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_prepare_claude_session_tree", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_persist_account_guard_launch", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    env = mms_launchers._account_env(
        {"id": "claude-a", "cli": "claude", "home_dir": str(account_home)},
        validate_proxy=False,
    )

    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert "ANTHROPIC_BASE_URL" not in env
    assert "ANTHROPIC_MODEL" not in env
    assert "CLAUDE_CODE_SUBAGENT_MODEL" not in env
    assert "CLAUDE_CODE_ATTRIBUTION_HEADER" not in env
    assert "HTTP_PROXY" not in env
    assert env["HOME"].startswith(str(account_home / "s"))


def test_account_env_seeds_current_project_trust_and_ui_state(monkeypatch, tmp_path):
    import mms_launchers

    account_home = tmp_path / "account-home"
    account_home.mkdir()
    session_home = account_home / "s" / "1234"
    session_home.mkdir(parents=True)
    real_home = tmp_path / "real-home"
    (real_home / ".local").mkdir(parents=True)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)

    (account_home / ".claude.json").write_text(
        json.dumps(
            {
                "bypassPermissionsModeAccepted": True,
                "projects": {
                    str(repo_dir.resolve()): {
                        "hasClaudeMdExternalIncludesApproved": False,
                        "projectOnboardingSeenCount": 0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (real_home / ".claude.json").write_text(
        json.dumps(
            {
                "firstStartTime": "2026-04-15T10:00:00Z",
                "numStartups": 9,
                "hasCompletedOnboarding": True,
                "lastOnboardingVersion": "1.2.3",
                "lastReleaseNotesSeen": "2.1.110",
                "installMethod": "native",
                "migrationVersion": 11,
                "tipsHistory": {
                    "theme-command": 508,
                    "terminal-setup": 515,
                },
                "mcpServers": {
                    "mindkeeper": {
                        "command": "mindkeeper",
                        "args": ["stdio"],
                    }
                },
                "projects": {
                    str(repo_dir.resolve()): {
                        "hasCompletedProjectOnboarding": False,
                        "hasClaudeMdExternalIncludesApproved": False,
                        "hasClaudeMdExternalIncludesWarningShown": False,
                        "projectOnboardingSeenCount": 0,
                        "lastSessionId": "session-abc",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(mms_launchers, "seed_claude_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_reserve_session_home",
        lambda *args, **kwargs: (str(session_home), 0, 1),
    )
    monkeypatch.setattr(mms_launchers, "_link_claude_library_entries", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_prepare_claude_session_tree", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_persist_account_guard_launch", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    env = mms_launchers._account_env(
        {"id": "claude-a", "cli": "claude", "home_dir": str(account_home)},
        validate_proxy=False,
    )

    session_state = json.loads((Path(env["HOME"]) / ".claude.json").read_text(encoding="utf-8"))
    assert "bypassPermissionsModeAccepted" not in session_state
    assert session_state["lastReleaseNotesSeen"] == "2.1.110"
    assert session_state["migrationVersion"] == 11
    assert session_state["numStartups"] == 9
    assert session_state["tipsHistory"]["theme-command"] == 508
    assert session_state["tipsHistory"]["terminal-setup"] == 515
    assert "mcpServers" not in session_state
    project_state = session_state["projects"][str(repo_dir.resolve())]
    assert project_state["hasTrustDialogAccepted"] is True
    assert project_state["hasCompletedProjectOnboarding"] is True
    assert project_state["hasClaudeMdExternalIncludesApproved"] is True
    assert project_state["hasClaudeMdExternalIncludesWarningShown"] is True
    assert project_state["projectOnboardingSeenCount"] == 1
    assert project_state["enabledMcpjsonServers"] == []
    assert project_state["disabledMcpjsonServers"] == []
    assert "lastSessionId" not in project_state


def test_account_env_fail_closed_when_guarded_limit_reached(monkeypatch, tmp_path):
    import mms_launchers

    account_home = tmp_path / "account-home"
    real_home = tmp_path / "real-home"
    real_home.mkdir()

    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_count_live_session_dirs", lambda _path: 4)
    monkeypatch.setattr(mms_launchers, "_session_home_is_active", lambda _path: False)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    try:
        mms_launchers._account_env(
            {"id": "claude-a", "cli": "claude", "home_dir": str(account_home)},
            validate_proxy=False,
        )
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected _account_env to fail-closed at guard limit")


def test_account_env_scrubs_claude_oauth_parent_env_for_codex(monkeypatch, tmp_path):
    import mms_launchers

    account_home = tmp_path / "account-home"
    real_home = tmp_path / "real-home"
    real_home.mkdir()

    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-parent")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://relay.example.com")
    monkeypatch.setenv("CLAUDE_CODE_SUBAGENT_MODEL", "claude-haiku-4-5")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_overlay_codex_shared_resume", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_sync_codex_session_claude_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    env = mms_launchers._account_env(
        {"id": "codex-a", "cli": "codex", "home_dir": str(account_home)},
        validate_proxy=False,
    )

    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert "ANTHROPIC_BASE_URL" not in env
    assert "CLAUDE_CODE_SUBAGENT_MODEL" not in env
    assert "OPENAI_API_KEY" not in env
    assert env["HOME"].startswith(str(account_home / "s"))


def test_account_env_materializes_web_access_skill_for_codex(monkeypatch, tmp_path):
    import mms_launchers

    account_home = tmp_path / "account-home"
    (account_home / ".codex" / "skills" / "keep-skill").mkdir(parents=True)
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    web_access_root = tmp_path / "web-access"
    (web_access_root / "references").mkdir(parents=True)
    (web_access_root / "SKILL.md").write_text("# web-access\n", encoding="utf-8")

    monkeypatch.setenv("MMS_WEB_ACCESS_ROOT", str(web_access_root))
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_sync_codex_session_claude_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    env = mms_launchers._account_env(
        {"id": "codex-a", "cli": "codex", "home_dir": str(account_home)},
        validate_proxy=False,
    )

    session_codex = Path(env["HOME"]) / ".codex"
    assert os.path.islink(session_codex / "skills" / "keep-skill")
    assert os.path.islink(session_codex / "skills" / "web-access")
    assert (session_codex / "skills" / "web-access" / "SKILL.md").read_text(encoding="utf-8") == "# web-access\n"


def test_account_env_materializes_agent_browser_skill_for_codex(monkeypatch, tmp_path):
    import mms_launchers

    account_home = tmp_path / "account-home"
    (account_home / ".codex" / "skills" / "keep-skill").mkdir(parents=True)
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    agent_browser_root = tmp_path / "agent-browser"
    agent_browser_root.mkdir()
    (agent_browser_root / "SKILL.md").write_text("# agent-browser\n", encoding="utf-8")
    (agent_browser_root / "_meta.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setenv("MMS_AGENT_BROWSER_ROOT", str(agent_browser_root))
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_sync_codex_session_claude_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    env = mms_launchers._account_env(
        {"id": "codex-a", "cli": "codex", "home_dir": str(account_home)},
        validate_proxy=False,
    )

    session_codex = Path(env["HOME"]) / ".codex"
    assert os.path.islink(session_codex / "skills" / "keep-skill")
    assert os.path.islink(session_codex / "skills" / "agent-browser")
    assert (session_codex / "skills" / "agent-browser" / "SKILL.md").read_text(encoding="utf-8") == "# agent-browser\n"


def test_account_env_scrubs_inherited_openai_and_proxy_parent_env_for_gemini(monkeypatch, tmp_path):
    import mms_launchers

    account_home = tmp_path / "account-home"
    real_home = tmp_path / "real-home"
    real_home.mkdir()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:15721/v1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:15721")

    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    env = mms_launchers._account_env(
        {"id": "gemini-a", "cli": "gemini", "home_dir": str(account_home)},
        validate_proxy=False,
    )

    assert "OPENAI_API_KEY" not in env
    assert "OPENAI_BASE_URL" not in env
    assert "HTTP_PROXY" not in env
    assert env["GEMINI_CLI_HOME"] == str(account_home)


def test_core_account_env_scrubs_inherited_ai_and_proxy_env(monkeypatch, tmp_path):
    import mms_core

    account_home = tmp_path / "account-home"
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-parent")
    monkeypatch.setenv("CLAUDE_CODE_ATTRIBUTION_HEADER", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("NODE_EXTRA_CA_CERTS", "/tmp/test-ca.pem")
    monkeypatch.setattr(mms_core, "seed_claude_state", lambda *_args, **_kwargs: None)

    env = mms_core._account_env(
        {"id": "claude-a", "cli": "claude", "home_dir": str(account_home)}
    )

    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert "CLAUDE_CODE_ATTRIBUTION_HEADER" not in env
    assert "OPENAI_API_KEY" not in env
    assert "HTTP_PROXY" not in env
    assert "NODE_EXTRA_CA_CERTS" not in env
    assert env["HOME"] == str(account_home)


def test_count_live_session_dirs_keeps_child_pid_backed_session_alive(monkeypatch, tmp_path):
    import mms_launchers

    sessions_dir = tmp_path / "sessions"
    session_home = sessions_dir / "1234"
    session_home.mkdir(parents=True)
    marker_path = session_home / mms_launchers._SESSION_GUARD_MARKER_NAME
    marker_path.write_text(
        json.dumps(
            {
                "launcher_pid": 1234,
                "launcher_identity": "python old",
                "child_pid": 5678,
                "child_identity": "claude child",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        mms_launchers,
        "_session_guard_pid_alive",
        lambda pid, identity="": int(pid or 0) == 5678 and identity == "claude child",
    )

    assert mms_launchers._count_live_session_dirs(str(sessions_dir)) == 1


def test_launch_qwen_scrubs_inherited_openai_and_proxy_parent_env(monkeypatch):
    import mms_launchers

    captured = {}
    monkeypatch.setenv("OPENAI_API_KEY", "sk-parent")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:15721/v1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:15721")
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, runtime=None: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, runtime: env)
    monkeypatch.setattr(
        mms_launchers,
        "_exec_or_run",
        lambda cmd, env, once=False, **kwargs: captured.update({"cmd": list(cmd), "env": dict(env)}),
    )

    mms_launchers.launch_qwen(
        "qwen3.5-plus",
        {"id": "qwen-a", "api_key": "sk-runtime", "openai_base_url": "https://api.example.com/v1"},
        once=True,
    )

    assert captured["cmd"][:3] == ["qwen", "--openai-base-url", "https://api.example.com/v1"]
    assert "OPENAI_API_KEY" not in captured["env"]
    assert "OPENAI_BASE_URL" not in captured["env"]
    assert "HTTP_PROXY" not in captured["env"]


def test_launch_claude_oauth_is_manual_only(monkeypatch, tmp_path, capsys):
    import mms_launchers

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)

    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-parent")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-parent")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9999")
    monkeypatch.setenv("PYTHONPATH", "/tmp/python")
    monkeypatch.setattr(mms_launchers, "_ensure_bridge_helpers", lambda: None)
    monkeypatch.setattr(mms_launchers, "_ensure_speed_stats", lambda: None)
    monkeypatch.setattr(mms_launchers, "_runtime_supports_claude_1m", lambda runtime: False)
    with pytest.raises(SystemExit) as exc:
        mms_launchers.launch_claude(
            {"model": "claude-sonnet-4-6"},
            {"auth_mode": "oauth", "cli": "claude", "home_dir": str(tmp_path / "account-home"), "bypass": True},
            once=True,
        )

    assert exc.value.code == mms_launchers._CLAUDE_OAUTH_MANUAL_ONLY_EXIT_CODE
    captured = capsys.readouterr()
    assert "manual-only" in captured.out
    assert "不能自动启动它" in captured.out


def test_launch_claude_oauth_delegate_blocks_force_ipv4(monkeypatch, tmp_path):
    import mms_launchers

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(mms_launchers, "_ensure_bridge_helpers", lambda: None)
    monkeypatch.setattr(mms_launchers, "_ensure_speed_stats", lambda: None)
    monkeypatch.setattr(mms_launchers, "_runtime_supports_claude_1m", lambda runtime: False)

    with pytest.raises(SystemExit) as exc:
        mms_launchers.launch_claude(
            {"model": "claude-sonnet-4-6"},
            {"auth_mode": "oauth", "cli": "claude", "home_dir": str(tmp_path / "account-home"), "force_ipv4": True},
            once=True,
        )
    assert exc.value.code == mms_launchers._CLAUDE_OAUTH_MANUAL_ONLY_EXIT_CODE

def test_anthropic_usage_ignores_ambient_env_and_respects_account_proxy(monkeypatch):
    import mms_usage

    captured = {}

    class FakeTransport:
        def __init__(self, **kwargs):
            captured["transport_kwargs"] = dict(kwargs)

    class FakeClient:
        def __init__(self, *, transport=None, timeout=None):
            captured["transport"] = transport
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            captured["url"] = url
            captured["headers"] = dict(headers or {})
            return types.SimpleNamespace(status_code=200, json=lambda: {"ok": True})

    monkeypatch.setattr(
        mms_usage,
        "_httpx",
        types.SimpleNamespace(AsyncHTTPTransport=FakeTransport, AsyncClient=FakeClient),
    )

    result = asyncio.run(
        mms_usage._anthropic_usage(
            "tok-test",
            {"proxy": "http://127.0.0.1:7890", "force_ipv4": True},
        )
    )

    assert result == {"ok": True}
    assert captured["url"] == "https://api.anthropic.com/api/oauth/usage"
    assert captured["headers"]["Authorization"] == "Bearer tok-test"
    assert captured["transport_kwargs"]["trust_env"] is False
    assert captured["transport_kwargs"]["proxy"] == "http://127.0.0.1:7890"
    assert captured["transport_kwargs"]["local_address"] == "0.0.0.0"


def test_install_session_command_wrappers_covers_global_mutating_commands(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    isolated_home = tmp_path / "isolated-home"
    real_home.mkdir()
    isolated_home.mkdir()

    monkeypatch.setenv(
        "PATH",
        os.pathsep.join(
            [
                str(isolated_home / ".mms" / "bin"),
                str(isolated_home / ".local" / "bin"),
                "/usr/local/bin",
                "/usr/bin",
            ]
        ),
    )
    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: str(real_home))
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    env = {"PATH": "/usr/local/bin:/usr/bin"}
    session_home = tmp_path / "session-home"
    mms_launchers._install_session_command_wrappers(str(session_home), env)

    wrapper_dir = session_home / ".mms" / "bin"
    for command_name in ("pm2", "npm", "pnpm", "npx", "yarn", "corepack"):
        wrapper_path = wrapper_dir / command_name
        assert wrapper_path.exists()
        script = wrapper_path.read_text(encoding="utf-8")
        assert f'command -v "{command_name}"' in script
        assert str(isolated_home / ".mms" / "bin") not in script
        assert str(isolated_home / ".local" / "bin") not in script
        assert f'export HOME="{real_home}"' in script
        assert f'export XDG_CONFIG_HOME="{real_home / ".config"}"' in script
        assert 'ANTHROPIC_*|CLAUDE_CODE_*|OPENAI_*|HTTP_PROXY|HTTPS_PROXY|ALL_PROXY|NO_PROXY' in script
        assert 'unset "$_mms_var"' in script
    assert f'export PM2_HOME="{real_home / ".pm2"}"' in (wrapper_dir / "pm2").read_text(encoding="utf-8")
    assert not (wrapper_dir / "claude").exists()
    assert env["PATH"].startswith(str(wrapper_dir) + os.pathsep)


def test_get_export_env_exposes_toon_bin_for_export_only_launch(monkeypatch, tmp_path):
    import mms_launchers

    toon_script = tmp_path / "mms-toon"
    toon_script.write_text("#!/bin/sh\nprintf 'TOON:\\n'\n", encoding="utf-8")
    toon_script.chmod(0o755)

    monkeypatch.setattr(mms_launchers, "_mms_toon_script_path", lambda: str(toon_script))
    monkeypatch.setattr(mms_launchers, "validate_provider_for_cli", lambda *_args, **_kwargs: None)

    runtime = {
        "id": "relay-a",
        "api_key": "sk-runtime",
        "base_url": "https://relay.example.com",
        "anthropic_base_url": "https://anthropic.example.com",
        "openai_base_url": "https://openai.example.com/v1",
    }

    claude_exports = mms_launchers.get_export_env("claude", runtime)
    codex_exports = mms_launchers.get_export_env("codex", runtime)

    assert claude_exports["MMS_TOON_BIN"] == str(toon_script)
    assert codex_exports["MMS_TOON_BIN"] == str(toon_script)
    assert claude_exports["PATH"] == f"{toon_script.parent}:$PATH"
    assert codex_exports["PATH"] == f"{toon_script.parent}:$PATH"
    assert claude_exports["ANTHROPIC_AUTH_TOKEN"] == "sk-runtime"
    assert codex_exports["OPENAI_API_KEY"] == "sk-runtime"


def test_account_env_oauth_claude_fail_closes_execution_surfaces(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    account_home = tmp_path / "account-home"
    session_home = tmp_path / "session-home"
    repo_dir = tmp_path / "repo"
    isolated_home = tmp_path / "isolated-home"
    real_home.mkdir()
    account_home.mkdir()
    session_home.mkdir()
    repo_dir.mkdir()
    isolated_home.mkdir()
    (real_home / ".local").mkdir(parents=True)

    monkeypatch.chdir(repo_dir)
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")
    monkeypatch.setenv("HOME", str(isolated_home))
    captured = {}
    monkeypatch.setattr(mms_launchers, "seed_claude_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_reserve_session_home",
        lambda *args, **kwargs: (str(session_home), 0, 1),
    )
    monkeypatch.setattr(mms_launchers, "_link_claude_library_entries", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_prepare_claude_session_tree",
        lambda _session_home, session_claude_dir, **kwargs: (
            captured.update({"allowed_source_entries": tuple(kwargs.get("allowed_source_entries") or ())}),
            Path(session_claude_dir).mkdir(parents=True, exist_ok=True),
        )[-1],
    )
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_persist_account_guard_launch", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: str(real_home))
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(
        mms_launchers,
        "_install_session_command_wrappers",
        lambda *args, **kwargs: captured.setdefault("wrapper_called", True),
    )

    env = mms_launchers._account_env(
        {"id": "claude-a", "cli": "claude", "home_dir": str(account_home)},
        validate_proxy=False,
    )

    session_state = json.loads((session_home / ".claude.json").read_text(encoding="utf-8"))
    assert "mcpServers" not in session_state
    project_state = session_state["projects"][str(repo_dir.resolve())]
    assert project_state["enabledMcpjsonServers"] == []
    assert project_state["disabledMcpjsonServers"] == []
    assert project_state["mcpServers"] == {}
    assert captured["allowed_source_entries"] == mms_launchers._CLAUDE_OAUTH_SESSION_SOURCE_ENTRY_ALLOWLIST
    assert "wrapper_called" not in captured
    assert not (session_home / ".claude" / "settings.json").exists()
    assert env["HOME"] == str(session_home)


def test_account_env_materializes_web_access_skill_for_oauth_claude(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    account_home = tmp_path / "account-home"
    session_home = tmp_path / "session-home"
    repo_dir = tmp_path / "repo"
    real_home.mkdir()
    account_home.mkdir()
    session_home.mkdir()
    repo_dir.mkdir()
    (real_home / ".local").mkdir(parents=True)
    web_access_root = tmp_path / "web-access"
    (web_access_root / "references").mkdir(parents=True)
    (web_access_root / "SKILL.md").write_text("# web-access\n", encoding="utf-8")

    monkeypatch.chdir(repo_dir)
    monkeypatch.setenv("MMS_WEB_ACCESS_ROOT", str(web_access_root))
    monkeypatch.setattr(mms_launchers, "seed_claude_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_reserve_session_home",
        lambda *args, **kwargs: (str(session_home), 0, 1),
    )
    monkeypatch.setattr(mms_launchers, "_link_claude_library_entries", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mms_launchers,
        "_prepare_claude_session_tree",
        lambda _session_home, session_claude_dir, **kwargs: Path(session_claude_dir).mkdir(parents=True, exist_ok=True),
    )
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_persist_account_guard_launch", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_real_user_home", lambda: str(real_home))
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)

    env = mms_launchers._account_env(
        {"id": "claude-a", "cli": "claude", "home_dir": str(account_home)},
        validate_proxy=False,
    )

    assert env["HOME"] == str(session_home)
    assert os.path.islink(session_home / ".claude" / "skills" / "web-access")
    assert (session_home / ".claude" / "skills" / "web-access" / "SKILL.md").read_text(encoding="utf-8") == "# web-access\n"


def test_sync_codex_session_claude_json_allowlists_non_sensitive_fields(monkeypatch, tmp_path):
    import mms_launchers

    real_home = tmp_path / "real-home"
    session_home = tmp_path / "session-home"
    real_home.mkdir()
    session_home.mkdir()

    (real_home / ".claude.json").write_text(
        json.dumps(
            {
                "firstStartTime": "2026-04-15T10:00:00Z",
                "numStartups": 7,
                "bypassPermissionsModeAccepted": True,
                "alwaysThinkingEnabled": True,
                "userID": "device-1",
                "oauthAccount": {"accountUuid": "acct-1"},
                "claudeAiOauth": {"accessToken": "tok-1"},
                "provider": "gateway",
                "api_key": "sk-test",
                "mcpServers": {"demo": {"command": "demo"}},
            }
        ),
        encoding="utf-8",
    )
    (session_home / ".claude.json").write_text(
        json.dumps({"firstStartTime": "keep-me", "bypassPermissionsModeAccepted": False}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        mms_launchers,
        "_real_user_path",
        lambda *parts: str(real_home.joinpath(*parts)),
    )

    mms_launchers._sync_codex_session_claude_json(str(session_home))

    result = json.loads((session_home / ".claude.json").read_text(encoding="utf-8"))
    assert result == {
        "firstStartTime": "keep-me",
        "numStartups": 7,
        "bypassPermissionsModeAccepted": False,
        "alwaysThinkingEnabled": True,
    }


def test_claude_gateway_env_scrubs_inherited_claude_auth_env(monkeypatch, tmp_path):
    import mms_launchers

    gateway_home = tmp_path / "gateway-home"
    real_home = tmp_path / "real-home"
    gateway_home.mkdir()
    real_home.mkdir()

    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-parent")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-parent")
    monkeypatch.setenv("CLAUDE_CODE_SUBAGENT_MODEL", "claude-haiku-4-5")

    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_claude_library_entries", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_prepare_claude_session_tree", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_write_claude_session_settings", lambda *args, **kwargs: ({}, "settings.json"))
    monkeypatch.setattr(mms_launchers, "_pick_gateway_model", lambda *args, **kwargs: "claude-sonnet-4-6")
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(mms_launchers, "_claude_gateway_home", lambda: str(gateway_home))
    monkeypatch.setattr(mms_launchers, "_claude_route_status_paths", lambda: [str(tmp_path / "route-status.json")])
    monkeypatch.setattr(mms_launchers, "list_indexed_sessions", lambda _cli="claude": [])

    env = mms_launchers._claude_gateway_env(
        {"id": "relay-a", "api_key": "sk-runtime"},
        base_url="https://relay.example.com",
        auth_token="bridge-token",
        selected_model="claude-sonnet-4-6",
    )

    assert env["ANTHROPIC_AUTH_TOKEN"] == "bridge-token"
    assert env["ANTHROPIC_BASE_URL"] == "https://relay.example.com"
    assert "ANTHROPIC_API_KEY" not in env
    assert env["CLAUDE_CODE_SUBAGENT_MODEL"] != "claude-haiku-4-5"


def test_claude_gateway_env_seeds_ui_state_and_sanitized_project_trust(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "gateway-session"
    session_home.mkdir()
    real_home = tmp_path / "real-home"
    (real_home / ".local").mkdir(parents=True)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)

    (real_home / ".claude.json").write_text(
        json.dumps(
            {
                "firstStartTime": "2026-04-15T10:00:00Z",
                "numStartups": 9,
                "hasCompletedOnboarding": True,
                "lastOnboardingVersion": "1.2.3",
                "lastReleaseNotesSeen": "2.1.110",
                "migrationVersion": 11,
                "tipsHistory": {
                    "theme-command": 508,
                    "terminal-setup": 515,
                },
                "projects": {
                    str(repo_dir.resolve()): {
                        "hasCompletedProjectOnboarding": False,
                        "hasClaudeMdExternalIncludesApproved": False,
                        "hasClaudeMdExternalIncludesWarningShown": False,
                        "projectOnboardingSeenCount": 0,
                        "lastSessionId": "session-abc",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (session_home / ".claude.json").write_text(
        json.dumps(
            {
                "numStartups": 2,
                "tipsHistory": {"theme-command": 3},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        mms_launchers,
        "_reserve_session_home",
        lambda *args, **kwargs: (str(session_home), 0, 1),
    )
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_claude_library_entries", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_prepare_claude_session_tree", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_write_claude_session_settings", lambda *args, **kwargs: ({}, "settings.json"))
    monkeypatch.setattr(mms_launchers, "_pick_gateway_model", lambda *args, **kwargs: "claude-sonnet-4-6")
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(mms_launchers, "_claude_route_status_paths", lambda: [str(tmp_path / "route-status.json")])
    monkeypatch.setattr(
        mms_launchers,
        "_session_managed_mcp_servers",
        lambda _settings=None, **_kwargs: {
            "hive": {"command": "/tmp/hive/bin/mcp-server.sh", "args": [], "type": "stdio"},
            "mindkeeper": {"command": "node", "args": ["/tmp/mindkeeper/dist/server.js"], "type": "stdio"},
        },
    )
    monkeypatch.setattr(mms_launchers, "list_indexed_sessions", lambda _cli="claude": [])

    mms_launchers._claude_gateway_env(
        {"id": "relay-a", "api_key": "sk-runtime"},
        base_url="https://relay.example.com",
        auth_token="bridge-token",
        selected_model="kimi-for-coding",
        display_model="kimi-for-coding",
    )

    session_state = json.loads((session_home / ".claude.json").read_text(encoding="utf-8"))
    assert session_state["lastReleaseNotesSeen"] == "2.1.110"
    assert session_state["migrationVersion"] == 11
    assert session_state["alwaysThinkingEnabled"] is True
    assert session_state["numStartups"] == 9
    assert session_state["tipsHistory"]["theme-command"] == 508
    assert session_state["tipsHistory"]["terminal-setup"] == 515
    assert session_state["mcpServers"]["hive"]["command"] == "/tmp/hive/bin/mcp-server.sh"
    assert session_state["mcpServers"]["mindkeeper"]["args"] == ["/tmp/mindkeeper/dist/server.js"]
    project_state = session_state["projects"][str(repo_dir.resolve())]
    assert project_state["hasTrustDialogAccepted"] is True
    assert project_state["hasCompletedProjectOnboarding"] is True
    assert project_state["hasClaudeMdExternalIncludesApproved"] is True
    assert project_state["hasClaudeMdExternalIncludesWarningShown"] is True
    assert project_state["projectOnboardingSeenCount"] == 1
    assert "lastSessionId" not in project_state


def test_claude_gateway_env_restores_project_scoped_resume_pointer(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "gateway-session"
    session_home.mkdir()
    real_home = tmp_path / "real-home"
    (real_home / ".local").mkdir(parents=True)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    other_repo = tmp_path / "other-repo"
    other_repo.mkdir()
    monkeypatch.chdir(repo_dir)

    (real_home / ".claude.json").write_text(
        json.dumps(
            {
                "projects": {
                    str(repo_dir.resolve()): {
                        "hasCompletedProjectOnboarding": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        mms_launchers,
        "_reserve_session_home",
        lambda *args, **kwargs: (str(session_home), 0, 1),
    )
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_claude_library_entries", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_prepare_claude_session_tree", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_write_claude_session_settings", lambda *args, **kwargs: ({}, "settings.json"))
    monkeypatch.setattr(mms_launchers, "_pick_gateway_model", lambda *args, **kwargs: "claude-sonnet-4-6")
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(mms_launchers, "_claude_route_status_paths", lambda: [str(tmp_path / "route-status.json")])
    monkeypatch.setattr(
        mms_launchers,
        "list_indexed_sessions",
        lambda _cli="claude": [
            {
                "project_path": str(other_repo.resolve()),
                "account_id": "relay-a",
                "runtime_kind": "api_key",
                "session_id": "session-other-project",
                "last_active_at": "2026-04-16T16:00:00+00:00",
            },
            {
                "project_path": str(repo_dir.resolve()),
                "account_id": "relay-b",
                "runtime_kind": "api_key",
                "session_id": "session-other-account",
                "last_active_at": "2026-04-16T17:00:00+00:00",
            },
            {
                "project_path": str(repo_dir.resolve()),
                "account_id": "relay-a",
                "runtime_kind": "oauth",
                "session_id": "session-other-runtime",
                "last_active_at": "2026-04-16T18:00:00+00:00",
            },
            {
                "project_path": str(repo_dir.resolve()),
                "account_id": "relay-a",
                "runtime_kind": "api_key",
                "resume_model": "claude-sonnet-4-6",
                "session_id": "session-match",
                "last_active_at": "2026-04-16T19:00:00+00:00",
            },
        ],
    )

    mms_launchers._claude_gateway_env(
        {"id": "relay-a", "api_key": "sk-runtime"},
        base_url="https://relay.example.com",
        auth_token="bridge-token",
        selected_model="claude-sonnet-4-6",
    )

    session_state = json.loads((session_home / ".claude.json").read_text(encoding="utf-8"))
    project_state = session_state["projects"][str(repo_dir.resolve())]
    assert project_state["lastSessionId"] == "session-match"


def test_claude_gateway_env_does_not_restore_cross_model_resume_pointer(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "gateway-session"
    session_home.mkdir()
    real_home = tmp_path / "real-home"
    (real_home / ".local").mkdir(parents=True)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)

    (real_home / ".claude.json").write_text(
        json.dumps(
            {
                "projects": {
                    str(repo_dir.resolve()): {
                        "hasCompletedProjectOnboarding": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        mms_launchers,
        "_reserve_session_home",
        lambda *args, **kwargs: (str(session_home), 0, 1),
    )
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_claude_library_entries", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_prepare_claude_session_tree", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_write_claude_session_settings", lambda *args, **kwargs: ({}, "settings.json"))
    monkeypatch.setattr(mms_launchers, "_pick_gateway_model", lambda *args, **kwargs: "claude-sonnet-4-6")
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))
    monkeypatch.setattr(mms_launchers, "_claude_route_status_paths", lambda: [str(tmp_path / "route-status.json")])
    monkeypatch.setattr(
        mms_launchers,
        "list_indexed_sessions",
        lambda _cli="claude": [
            {
                "project_path": str(repo_dir.resolve()),
                "account_id": "relay-a",
                "runtime_kind": "api_key",
                "resume_model": "qwen3-coder-plus",
                "session_id": "session-qwen",
                "last_active_at": "2026-04-16T19:00:00+00:00",
            },
        ],
    )

    mms_launchers._claude_gateway_env(
        {"id": "relay-a", "api_key": "sk-runtime"},
        base_url="https://relay.example.com",
        auth_token="bridge-token",
        selected_model="claude-sonnet-4-6",
        display_model="gpt-5.4",
    )

    session_state = json.loads((session_home / ".claude.json").read_text(encoding="utf-8"))
    project_state = session_state["projects"][str(repo_dir.resolve())]
    assert "lastSessionId" not in project_state


def test_build_broker_env_scrubs_inherited_claude_auth_env(monkeypatch):
    import mms_broker

    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-parent")
    monkeypatch.setenv("CLAUDE_CODE_SUBAGENT_MODEL", "claude-haiku-4-5")

    env = mms_broker._build_broker_env(
        {"id": "broker-a", "broker_base_url": "https://broker.example.com"},
        workspace_root="/tmp/workspace",
    )

    assert env["CC_BROKER_BASE_URL"] == "https://broker.example.com"
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert "CLAUDE_CODE_SUBAGENT_MODEL" not in env


def test_resolve_anthropic_base_url_probe_metadata_is_neutral(monkeypatch):
    import mms_launchers

    captured = {}

    def fake_detect(url, endpoint, headers, body=None, timeout=0, runtime=None):
        captured["url"] = url
        captured["endpoint"] = endpoint
        captured["body"] = body
        return url

    monkeypatch.setattr(mms_launchers, "detect_working_base_url", fake_detect)
    monkeypatch.setattr(mms_launchers, "_remember_anthropic_url", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_load_anthropic_url_file_cache", lambda: {})
    monkeypatch.setattr(mms_launchers, "_save_anthropic_url_file_cache", lambda payload: None)
    mms_launchers._ANTHROPIC_URL_CACHE.clear()

    resolved, method = mms_launchers._resolve_anthropic_base_url(
        {
            "id": "relay-a",
            "api_key": "sk-test",
            "anthropic_base_url": "https://relay.example.com",
        }
    )

    body = json.loads(captured["body"].decode("utf-8"))
    metadata_user_id = json.loads(body["metadata"]["user_id"])

    assert resolved == "https://relay.example.com"
    assert method == "probed"
    assert metadata_user_id["device_id"].startswith("device-")
    assert metadata_user_id["session_id"].startswith("session-")
    assert "account_uuid" not in metadata_user_id
    assert "mms-probe-" not in metadata_user_id["device_id"]
    assert "mms-probe-" not in metadata_user_id["session_id"]


def test_gateway_health_check_cache_is_scoped_per_provider(monkeypatch, tmp_path):
    import mms_launchers

    health_path = tmp_path / "health_check.json"
    monkeypatch.setattr(mms_launchers, "HEALTH_CHECK_PATH", str(health_path))
    monkeypatch.setattr(mms_launchers, "_gateway_ping", lambda *args, **kwargs: True)
    monkeypatch.setattr(mms_launchers, "_openai_base_url", lambda provider: provider.get("base_url"))
    monkeypatch.setattr(mms_launchers, "_anthropic_base_url", lambda provider: "")

    provider_a = {"id": "relay-a", "base_url": "https://relay-a.example.com", "api_key": "sk-a"}
    provider_b = {"id": "relay-b", "base_url": "https://relay-b.example.com", "api_key": "sk-b"}

    mms_launchers.gateway_health_check(provider_a)
    mms_launchers.gateway_health_check(provider_b)

    assert mms_launchers._health_check_due("relay-a") is False
    assert mms_launchers._health_check_due("relay-b") is False

    saved = json.loads(health_path.read_text(encoding="utf-8"))
    assert set(saved["providers"].keys()) == {"relay-a", "relay-b"}


def test_gateway_ping_uses_x_api_key_for_anthropic_endpoint(monkeypatch):
    import mms_launchers

    captured = {}

    class FakeResponse:
        status_code = 200

    monkeypatch.setattr(mms_launchers, "_ensure_bridge_helpers", lambda: None)
    monkeypatch.setattr(mms_launchers, "_build_gateway_url", lambda base_url, endpoint: base_url.rstrip("/") + endpoint)
    monkeypatch.setattr(mms_launchers, "_anthropic_base_url", lambda runtime: runtime.get("anthropic_base_url", ""))
    monkeypatch.setattr(
        mms_launchers,
        "_runtime_httpx_request",
        lambda method, url, runtime=None, headers=None, timeout=None: captured.update(
            {"method": method, "url": url, "headers": dict(headers or {})}
        ) or FakeResponse(),
    )

    ok = mms_launchers._gateway_ping(
        "https://relay.example.com",
        "sk-test",
        runtime={"anthropic_base_url": "https://relay.example.com"},
    )

    assert ok is True
    assert captured["headers"] == {
        "x-api-key": "sk-test",
        "anthropic-version": "2023-06-01",
    }


def test_gateway_claude_bridge_binds_ephemeral_port_and_waits_ready(monkeypatch):
    import mms_bridge

    calls = {"wait": [], "closed": 0}

    class FakeServer:
        def __init__(self, addr, handler):
            calls["addr"] = addr
            calls["handler"] = handler
            self.server_address = ("127.0.0.1", 54321)

        def serve_forever(self):
            return None

        def server_close(self):
            calls["closed"] += 1

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            self.target = target
            self.daemon = daemon

        def start(self):
            calls["started"] = True

        def join(self, timeout=None):
            calls["joined"] = timeout

    monkeypatch.setattr(mms_bridge, "_SilentHTTPServer", FakeServer)
    monkeypatch.setattr(mms_bridge.threading, "Thread", FakeThread)
    monkeypatch.setattr(
        mms_bridge,
        "_wait_local_server_ready",
        lambda port, attempts=50, delay=0.1: calls["wait"].append((port, attempts, delay)) or True,
    )

    with mms_bridge.gateway_claude_bridge("https://relay.example.com/v1", "sk-test") as bridge_cfg:
        assert bridge_cfg["base_url"] == "http://127.0.0.1:54321"
        assert bridge_cfg["api_key"].startswith("mms-bridge-")

    assert calls["addr"] == ("127.0.0.1", 0)
    assert calls["wait"] == [(54321, 50, 0.1)]
    assert calls["closed"] == 1


def test_bridge_httpx_kwargs_disable_ambient_proxy_by_default():
    import mms_bridge

    kwargs = mms_bridge._bridge_httpx_kwargs(target_url="https://relay.example.com/v1/messages")

    assert kwargs == {"trust_env": False}


def test_gateway_bridge_post_disables_trust_env_and_respects_runtime_proxy(monkeypatch):
    import mms_bridge

    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        content = b'{"ok": true}'

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = dict(kwargs)
        return FakeResponse()

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(post=fake_post))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)

    raw_body = json.dumps(
        {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        }
    ).encode("utf-8")

    handler = mms_bridge._GatewayBridgeHandler.__new__(mms_bridge._GatewayBridgeHandler)
    handler.path = "/v1/messages"
    handler.headers = {
        "content-length": str(len(raw_body)),
        "x-api-key": "bridge-token",
    }
    handler.rfile = io.BytesIO(raw_body)
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        bridge_token="bridge-token",
        gateway_key="gateway-key",
        gateway_url="https://relay.example.com/v1",
        route_status_paths=[],
        advertised_models=["claude-sonnet-4-6"],
        heavy_model="claude-sonnet-4-6",
        medium_model=None,
        light_model=None,
        slot_configs={},
        openai_url=None,
        speed_scope=None,
        proxy_url="http://127.0.0.1:15721",
        no_proxy="",
    )
    handler.send_response = lambda code: captured.setdefault("status", code)
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda: None

    handler.do_POST()

    assert captured["status"] == 200
    assert captured["url"] == "https://relay.example.com/v1/messages"
    assert captured["kwargs"]["trust_env"] is False
    assert captured["kwargs"]["proxy"] == "http://127.0.0.1:15721"


def test_chatcompletions_fallback_429_respects_retry_after_without_fanout(monkeypatch):
    import mms_bridge

    class FakeResponse:
        def __init__(self, status_code, body, headers=None):
            self.status_code = status_code
            self._body = body.encode("utf-8")
            self.headers = headers or {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return self._body

        @staticmethod
        def iter_lines():
            return iter(())

    calls = []
    sleep_calls = []
    response = FakeResponse(429, "rate limited", {"Retry-After": "3"})

    def fake_stream(method, url, **kwargs):
        calls.append(url)
        return response

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=fake_stream))
    monkeypatch.setattr(
        mms_bridge,
        "_build_gateway_candidate_urls",
        lambda *args, **kwargs: [
            "https://gw-a.example.com/chat/completions",
            "https://gw-b.example.com/chat/completions",
        ],
    )
    monkeypatch.setattr(mms_bridge.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    handler = mms_bridge._ResponsesProxyHandler.__new__(mms_bridge._ResponsesProxyHandler)
    handler.headers = {}
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(speed_scope=None)
    status = {}
    sent_headers = {}
    handler.send_response = lambda code: status.setdefault("code", code)
    handler.send_header = lambda name, value: sent_headers.setdefault(name, value)
    handler.end_headers = lambda: None

    handler._do_chatcompletions_fallback(
        {"input": [], "instructions": ""},
        "gpt-5.4",
        "https://gw-root.example.com",
        "gateway-key",
        0,
    )

    assert calls == [
        "https://gw-a.example.com/chat/completions",
        "https://gw-a.example.com/chat/completions",
    ]
    assert sleep_calls == [2.0]
    assert status["code"] == 429
    assert sent_headers["Retry-After"] == "3"


def test_build_codex_payload_maps_output_limit():
    import mms_bridge

    payload = mms_bridge._build_codex_payload(
        {
            "system": "You are helpful.",
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
            "max_tokens": 256,
        },
        "gpt-5.4",
    )

    assert payload["max_output_tokens"] == 256


def test_build_codex_payload_can_skip_output_limit_mapping():
    import mms_bridge

    payload = mms_bridge._build_codex_payload(
        {
            "system": "You are helpful.",
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
            "max_tokens": 256,
        },
        "gpt-5.4",
        include_max_output_tokens=False,
    )

    assert "max_output_tokens" not in payload


def test_build_codex_payload_can_disable_reasoning():
    import mms_bridge

    payload = mms_bridge._build_codex_payload(
        {
            "system": "You are helpful.",
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        },
        "gpt-5.4",
        reasoning_effort="high",
        reasoning_enabled=False,
        include_max_output_tokens=False,
    )

    assert "reasoning" not in payload


def test_gpt_on_claude_forward_as_responses_skips_output_limit_for_strict_upstream(monkeypatch):
    import mms_bridge

    captured = {}

    def fake_build_codex_payload(
        request_payload,
        model_name,
        incremental_messages=None,
        reasoning_effort="medium",
        *,
        reasoning_enabled=True,
        include_max_output_tokens=True,
    ):
        captured["include_max_output_tokens"] = include_max_output_tokens
        payload = {
            "model": model_name,
            "input": [],
            "stream": True,
        }
        if reasoning_enabled:
            payload["reasoning"] = {"effort": reasoning_effort}
        if include_max_output_tokens:
            payload["max_output_tokens"] = 256
        return payload

    class FakeResponse:
        status_code = 400
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def read():
            return b'{"detail":"Unsupported parameter: max_output_tokens"}'

    def fake_stream(method, url, **kwargs):
        captured["url"] = url
        captured["json"] = dict(kwargs.get("json") or {})
        return FakeResponse()

    monkeypatch.setattr(mms_bridge, "_build_codex_payload", fake_build_codex_payload)
    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=fake_stream))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)

    handler = mms_bridge._GatewayBridgeHandler.__new__(mms_bridge._GatewayBridgeHandler)
    handler.server = types.SimpleNamespace(
        _gpt_last_response_id=None,
        reasoning_effort="high",
        bridge_token="bridge-token",
        proxy_url="",
        no_proxy="",
    )
    status = {}
    handler._json = lambda code, payload: status.update({"code": code, "payload": payload})

    handler._forward_as_responses(
        {
            "model": "gpt-5.4",
            "stream": False,
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
            "max_tokens": 256,
        },
        "gpt-5.4",
        "https://crs.example.com/v1",
        "sk-test",
        False,
    )

    assert captured["include_max_output_tokens"] is False
    assert "max_output_tokens" not in captured["json"]
    assert captured["url"] == "https://crs.example.com/v1/responses"
    assert status["code"] == 400


def test_iter_sse_lines_defaults_event_name_and_skips_bad_json():
    import mms_bridge

    class FakeResponse:
        @staticmethod
        def iter_lines():
            return iter(
                [
                    'data: {"type":"response.started"}',
                    "",
                    "event: response.output_text.delta",
                    'data: {"type":"response.output_text.delta","delta":"ok"}',
                    "",
                    'data: {"broken"',
                    "",
                ]
            )

    events = list(mms_bridge._iter_sse_lines(FakeResponse()))

    assert events == [
        ("message", {"type": "response.started"}),
        ("response.output_text.delta", {"type": "response.output_text.delta", "delta": "ok"}),
    ]


def test_forward_as_responses_retries_without_previous_response_id(monkeypatch):
    import mms_bridge

    calls = []

    def fake_build_codex_payload(*_args, incremental_messages=None, **_kwargs):
        return {
            "model": "gpt-5.4",
            "input": list(incremental_messages or []),
            "instructions": "hello",
            "stream": True,
        }

    class FakeResponse:
        headers = {}

        def __init__(self, status_code, body=""):
            self.status_code = status_code
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return self._body.encode("utf-8")

    responses = [
        FakeResponse(400, '{"detail":"Unsupported parameter: previous_response_id"}'),
        FakeResponse(200),
    ]

    def fake_stream(method, url, **kwargs):
        calls.append({"url": url, "json": dict(kwargs.get("json") or {})})
        return responses.pop(0)

    class FakeTranslator:
        def __init__(self, _model_name):
            self.response_id = "resp-new"

        def process(self, event_type, event_data):
            return []

        def final_message(self):
            return {"type": "message", "content": []}

    monkeypatch.setattr(mms_bridge, "_build_codex_payload", fake_build_codex_payload)
    monkeypatch.setattr(mms_bridge, "_AnthropicTranslator", FakeTranslator)
    monkeypatch.setattr(
        mms_bridge,
        "_iter_sse_lines",
        lambda _response: [("response.completed", {"id": "resp-new"})],
    )
    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=fake_stream))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)

    handler = mms_bridge._GatewayBridgeHandler.__new__(mms_bridge._GatewayBridgeHandler)
    handler.server = types.SimpleNamespace(
        _gpt_last_response_id="resp-old",
        reasoning_effort="high",
        bridge_token="bridge-token",
        proxy_url="",
        no_proxy="",
    )
    handler.wfile = io.BytesIO()
    handler.send_response = lambda _code: None
    handler.send_header = lambda *_args, **_kwargs: None
    handler.end_headers = lambda: None
    handler._json = lambda code, payload: (_ for _ in ()).throw(AssertionError((code, payload)))

    handler._forward_as_responses(
        {
            "model": "gpt-5.4",
            "stream": False,
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        },
        "gpt-5.4",
        "https://crs.example.com/v1",
        "sk-test",
        False,
    )

    assert len(calls) == 2
    assert calls[0]["json"]["previous_response_id"] == "resp-old"
    assert "previous_response_id" not in calls[1]["json"]
    assert handler.server._gpt_last_response_id == "resp-new"


def test_forward_as_responses_retries_on_generic_403_permission_denied(monkeypatch):
    import mms_bridge

    calls = []

    def fake_build_codex_payload(*_args, incremental_messages=None, **_kwargs):
        return {
            "model": "gpt-5.4",
            "input": list(incremental_messages or []),
            "instructions": "hello",
            "stream": True,
        }

    class FakeResponse:
        headers = {}

        def __init__(self, status_code, body=""):
            self.status_code = status_code
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return self._body.encode("utf-8")

    responses = [
        FakeResponse(
            403,
            '{"error":{"type":"<nil>","message":"Permission denied","request_id":"req-1"}}',
        ),
        FakeResponse(200),
    ]

    def fake_stream(method, url, **kwargs):
        calls.append({"url": url, "json": dict(kwargs.get("json") or {})})
        return responses.pop(0)

    class FakeTranslator:
        def __init__(self, _model_name):
            self.response_id = "resp-new"

        def process(self, event_type, event_data):
            return []

        def final_message(self):
            return {"type": "message", "content": []}

    monkeypatch.setattr(mms_bridge, "_build_codex_payload", fake_build_codex_payload)
    monkeypatch.setattr(mms_bridge, "_AnthropicTranslator", FakeTranslator)
    monkeypatch.setattr(
        mms_bridge,
        "_iter_sse_lines",
        lambda _response: [("response.completed", {"id": "resp-new"})],
    )
    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=fake_stream))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)

    handler = mms_bridge._GatewayBridgeHandler.__new__(mms_bridge._GatewayBridgeHandler)
    handler.server = types.SimpleNamespace(
        _gpt_last_response_id="resp-old",
        reasoning_effort="high",
        bridge_token="bridge-token",
        proxy_url="",
        no_proxy="",
    )
    handler.wfile = io.BytesIO()
    handler.send_response = lambda _code: None
    handler.send_header = lambda *_args, **_kwargs: None
    handler.end_headers = lambda: None
    handler._json = lambda code, payload: (_ for _ in ()).throw(AssertionError((code, payload)))

    handler._forward_as_responses(
        {
            "model": "gpt-5.4",
            "stream": False,
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        },
        "gpt-5.4",
        "https://crs.example.com/v1",
        "sk-test",
        False,
    )

    assert len(calls) == 2
    assert calls[0]["json"]["previous_response_id"] == "resp-old"
    assert "previous_response_id" not in calls[1]["json"]
    assert handler.server._gpt_last_response_id == "resp-new"


def test_forward_as_responses_fail_closes_final_403_without_login_hint(monkeypatch):
    import mms_bridge

    def fake_build_codex_payload(*_args, incremental_messages=None, **_kwargs):
        return {
            "model": "gpt-5.4",
            "input": list(incremental_messages or []),
            "instructions": "hello",
            "stream": True,
        }

    class FakeResponse:
        headers = {}

        def __init__(self, status_code, body=""):
            self.status_code = status_code
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return self._body.encode("utf-8")

    monkeypatch.setattr(mms_bridge, "_build_codex_payload", fake_build_codex_payload)
    monkeypatch.setattr(
        mms_bridge,
        "httpx",
        types.SimpleNamespace(
            stream=lambda *_args, **_kwargs: FakeResponse(
                403,
                '{"error":{"type":"<nil>","message":"Permission denied","request_id":"req-2"}}',
            )
        ),
    )
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)

    handler = mms_bridge._GatewayBridgeHandler.__new__(mms_bridge._GatewayBridgeHandler)
    handler.server = types.SimpleNamespace(
        _gpt_last_response_id=None,
        reasoning_effort="high",
        bridge_token="bridge-token",
        proxy_url="",
        no_proxy="",
    )
    captured = {}
    handler._json = lambda code, payload: captured.update({"code": code, "payload": payload})

    handler._forward_as_responses(
        {
            "model": "gpt-5.4",
            "stream": False,
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        },
        "gpt-5.4",
        "https://crs.example.com/v1",
        "sk-test",
        False,
    )

    assert captured["code"] == 502
    message = captured["payload"]["error"]["message"]
    assert "Claude OAuth login is disabled here" in message
    assert "/login" not in message
    assert "HTTP 403" in message


def test_responses_proxy_handler_strips_reasoning_when_disabled(monkeypatch):
    import mms_bridge

    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def iter_lines():
            return iter([])

    def fake_stream(method, url, **kwargs):
        captured["url"] = url
        captured["json"] = dict(kwargs.get("json") or {})
        return FakeResponse()

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=fake_stream))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)
    monkeypatch.setattr(mms_bridge, "_needs_chatcompletions_bridge", lambda *args, **kwargs: False)

    handler = mms_bridge._ResponsesProxyHandler.__new__(mms_bridge._ResponsesProxyHandler)
    body = json.dumps({"model": "gpt-5.4", "reasoning": {"effort": "xhigh"}, "stream": True}).encode("utf-8")
    handler.server = types.SimpleNamespace(
        gateway_url="https://gw.example.com/v1",
        gateway_key="sk-test",
        model_name="gpt-5.4",
        provider_id="relay-a",
        bridge_token="bridge-token",
        reasoning_enabled=False,
        reasoning_effort="medium",
        proxy_url="",
        no_proxy="",
        advertised_models=[],
        speed_scope={},
        route_status_paths=[],
    )
    handler.headers = {"authorization": "Bearer bridge-token", "content-length": str(len(body))}
    handler.path = "/v1/responses"
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.send_response = lambda _code: None
    handler.send_header = lambda *_args, **_kwargs: None
    handler.end_headers = lambda: None

    handler.do_POST()

    assert captured["url"] == "https://gw.example.com/v1/responses"
    assert "reasoning" not in captured["json"]


def test_responses_proxy_handler_overrides_reasoning_effort_when_enabled(monkeypatch):
    import mms_bridge

    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def iter_lines():
            return iter([])

    def fake_stream(method, url, **kwargs):
        captured["json"] = dict(kwargs.get("json") or {})
        return FakeResponse()

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=fake_stream))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)
    monkeypatch.setattr(mms_bridge, "_needs_chatcompletions_bridge", lambda *args, **kwargs: False)

    handler = mms_bridge._ResponsesProxyHandler.__new__(mms_bridge._ResponsesProxyHandler)
    body = json.dumps({"model": "gpt-5.4", "reasoning": {"effort": "low"}, "stream": True}).encode("utf-8")
    handler.server = types.SimpleNamespace(
        gateway_url="https://gw.example.com/v1",
        gateway_key="sk-test",
        model_name="gpt-5.4",
        provider_id="relay-a",
        bridge_token="bridge-token",
        reasoning_enabled=True,
        reasoning_effort="high",
        proxy_url="",
        no_proxy="",
        advertised_models=[],
        speed_scope={},
        route_status_paths=[],
    )
    handler.headers = {"authorization": "Bearer bridge-token", "content-length": str(len(body))}
    handler.path = "/v1/responses"
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.send_response = lambda _code: None
    handler.send_header = lambda *_args, **_kwargs: None
    handler.end_headers = lambda: None

    handler.do_POST()

    assert captured["json"]["reasoning"] == {"effort": "high"}


def test_gateway_bridge_post_fail_closes_upstream_403_without_login_hint(monkeypatch):
    import mms_bridge

    class FakeResponse:
        status_code = 403
        headers = {"content-type": "application/json"}
        content = b'{"error":{"type":"<nil>","message":"Permission denied","request_id":"req-3"}}'

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(post=lambda *_args, **_kwargs: FakeResponse()))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)

    raw_body = json.dumps(
        {
            "model": "K2.6-code-preview",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        }
    ).encode("utf-8")

    handler = mms_bridge._GatewayBridgeHandler.__new__(mms_bridge._GatewayBridgeHandler)
    handler.path = "/v1/messages"
    handler.headers = {
        "content-length": str(len(raw_body)),
        "x-api-key": "bridge-token",
    }
    handler.rfile = io.BytesIO(raw_body)
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        bridge_token="bridge-token",
        gateway_key="gateway-key",
        gateway_url="https://relay.example.com/v1",
        route_status_paths=[],
        advertised_models=["K2.6-code-preview"],
        heavy_model="K2.6-code-preview",
        medium_model=None,
        light_model=None,
        slot_configs={},
        openai_url=None,
        speed_scope=None,
        proxy_url="",
        no_proxy="",
    )
    captured = {}
    handler._json = lambda code, payload: captured.update({"code": code, "payload": payload})
    handler.send_response = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("send_response should not be called"))
    handler.send_header = lambda *_args, **_kwargs: None
    handler.end_headers = lambda: None

    handler.do_POST()

    assert captured["code"] == 502
    message = captured["payload"]["error"]["message"]
    assert "Claude OAuth login is disabled here" in message
    assert "/login" not in message
    assert "HTTP 403" in message


def test_json_resp_to_sse_invalid_body_returns_error_event():
    import mms_bridge

    body = mms_bridge._json_resp_to_sse(b"not-json")
    text = body.decode("utf-8")

    assert text.startswith("event: error\n")
    assert "upstream returned non-JSON body" in text


def test_responses_bridge_models_endpoint_requires_auth_and_supports_query():
    import mms_bridge

    handler_classes = (
        mms_bridge._ResponsesProxyHandler,
        mms_bridge._ResponsesToChatHandler,
    )

    for handler_cls in handler_classes:
        handler = handler_cls.__new__(handler_cls)
        handler.headers = {}
        handler.path = "/v1/models?view=full"
        handler.wfile = io.BytesIO()
        handler.server = types.SimpleNamespace(
            bridge_token="bridge-token",
            gateway_key="gateway-key",
            advertised_models=["gpt-5.4"],
            model_name="gpt-5.4",
        )

        unauthorized = {}
        handler.send_response = lambda code, store=unauthorized: store.setdefault("code", code)
        handler.send_header = lambda *args, **kwargs: None
        handler.end_headers = lambda: None
        handler.do_GET()
        assert unauthorized["code"] == 401

        handler.headers = {"authorization": "Bearer bridge-token"}
        authorized = {}
        handler.send_response = lambda code, store=authorized: store.setdefault("code", code)
        handler.wfile = io.BytesIO()
        handler.do_GET()
        assert authorized["code"] == 200


def test_llm_classify_retries_retry_after_on_429(monkeypatch):
    import mms_router

    class FakeResponse:
        def __init__(self, status_code, payload=None, text="", headers=None, url="https://relay.example.com/v1/messages"):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = text
            self.headers = headers or {}
            self.url = url

        def json(self):
            return self._payload

    calls = []
    sleep_calls = []
    responses = iter(
        [
            FakeResponse(429, text="rate limited", headers={"Retry-After": "1"}),
            FakeResponse(
                200,
                payload={
                    "content": [{"type": "text", "text": "LIGHT HIGH"}],
                    "usage": {"input_tokens": 8, "output_tokens": 2},
                },
            ),
        ]
    )

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(url)
        return next(responses)

    monkeypatch.setattr(mms_router, "_httpx", types.SimpleNamespace(post=fake_post))
    monkeypatch.setattr(mms_router.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    result = mms_router._llm_classify(
        "fix typo in docs",
        "https://relay.example.com",
        "sk-test",
        "claude-sonnet-4-6",
    )

    assert result == ("light", "high")
    assert calls == [
        "https://relay.example.com/v1/messages",
        "https://relay.example.com/v1/messages",
    ]
    assert sleep_calls == [1.0]
