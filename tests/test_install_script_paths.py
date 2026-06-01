import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = ROOT_DIR / "install.sh"
HANDOVER_INSTALLER = ROOT_DIR / "vendor" / "handover" / "scripts" / "install_global_commands.py"


def _version_env_overrides(
    *,
    stable_ref: str = "v1.16.5",
    latest_tag_ref: str = "v1.16.6",
) -> dict[str, str]:
    return {
        "REAL_HOME": "",
        "MMS_REAL_HOME": "",
        "ORIGINAL_HOME": "",
        "MMS_INSTALL_LATEST_RELEASE_OVERRIDE": stable_ref,
        "MMS_INSTALL_LATEST_TAG_OVERRIDE": latest_tag_ref,
    }


def _run_install_check(*, home: Path, extra_env: dict[str, str] | None = None) -> str:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.update(_version_env_overrides())
    if extra_env:
        env.update(extra_env)
    completed = subprocess.run(
        ["bash", str(INSTALL_SCRIPT), "--check"],
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def _extract_shell_function_body(script_text: str, function_name: str) -> str:
    marker = f"{function_name}() {{"
    start = script_text.find(marker)
    assert start != -1, f"Could not find {function_name} function definition"

    body_start = start + len(marker)
    depth = 1
    i = body_start
    while i < len(script_text):
        char = script_text[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return script_text[body_start:i]
        i += 1

    raise AssertionError(f"Could not find closing brace for {function_name}")


def _extract_python_heredoc_after(script_text: str, marker: str) -> str:
    start = script_text.find(marker)
    assert start != -1, f"Could not find marker {marker!r}"
    heredoc_start = script_text.find("<<'PY'", start)
    assert heredoc_start != -1, f"Could not find Python heredoc after {marker!r}"
    body_start = script_text.find("\n", heredoc_start) + 1
    body_end = script_text.find("\nPY\n", body_start)
    assert body_end != -1, f"Could not find Python heredoc end after {marker!r}"
    return script_text[body_start:body_end]


def _run_handover_installer(home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        ["python3", str(HANDOVER_INSTALLER)],
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _install_handover_vendor_fixture(home: Path) -> Path:
    handover_target = home / ".mms" / "vendor" / "handover"
    handover_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT_DIR / "vendor" / "handover", handover_target, symlinks=True)
    return handover_target


def test_cleanup_legacy_global_session_hooks_removes_stale_nsr_and_read_once_dupes(tmp_path):
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")
    cleanup_py = _extract_python_heredoc_after(script, "cleanup_legacy_global_session_hooks()")
    claude_settings = tmp_path / ".claude" / "settings.json"
    codex_hooks = tmp_path / ".codex" / "hooks.json"
    claude_settings.parent.mkdir(parents=True)
    codex_hooks.parent.mkdir(parents=True)
    claude_settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Read",
                            "hooks": [
                                {"type": "command", "command": f"READ_ONCE_DIFF=1 {tmp_path}/.claude/read-once/hook.sh"},
                                {"type": "command", "command": f"READ_ONCE_DIFF=1 /bin/bash {tmp_path}/.claude/read-once/hook.sh"},
                            ],
                        },
                        {
                            "matcher": "*",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "/Users/me/auto-skills/CtriXin-repo/multi-model-switch/.worktrees/old/hooks/nsr-claude-hook.sh",
                                },
                                {"type": "command", "command": "node /external/openpets hook"},
                            ],
                        },
                    ],
                    "PostCompact": [
                        {
                            "matcher": "",
                            "hooks": [
                                {"type": "command", "command": f"{tmp_path}/.claude/read-once/compact.sh"},
                                {"type": "command", "command": f"/bin/bash {tmp_path}/.claude/read-once/compact.sh"},
                            ],
                        }
                    ],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    codex_hooks.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "/bin/bash /Users/me/auto-skills/CtriXin-repo/multi-model-switch/hooks/nsr-codex-hook.sh",
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["python3", "-", str(claude_settings), str(codex_hooks)],
        input=cleanup_py,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "CLEANED:" in completed.stdout
    cleaned_claude = json.loads(claude_settings.read_text(encoding="utf-8"))
    cleaned_codex = json.loads(codex_hooks.read_text(encoding="utf-8"))
    claude_commands = [
        hook["command"]
        for groups in cleaned_claude["hooks"].values()
        for group in groups
        for hook in group.get("hooks", [])
    ]
    codex_commands = [
        hook["command"]
        for groups in cleaned_codex.get("hooks", {}).values()
        for group in groups
        for hook in group.get("hooks", [])
    ]
    assert all("nsr-" not in command for command in claude_commands + codex_commands)
    assert "node /external/openpets hook" in claude_commands
    assert claude_commands.count(f"READ_ONCE_DIFF=1 /bin/bash {tmp_path}/.claude/read-once/hook.sh") == 1
    assert claude_commands.count(f"/bin/bash {tmp_path}/.claude/read-once/compact.sh") == 1
    assert not any(command == f"READ_ONCE_DIFF=1 {tmp_path}/.claude/read-once/hook.sh" for command in claude_commands)
    assert not any(command == f"{tmp_path}/.claude/read-once/compact.sh" for command in claude_commands)


def test_install_check_prefers_explicit_real_home(tmp_path):
    real_home = tmp_path / "real-home"
    session_home = tmp_path / "session-home" / ".config" / "mms" / "codex-gateway" / "s" / "12345"
    real_home.mkdir(parents=True)
    session_home.mkdir(parents=True)

    output = _run_install_check(
        home=session_home,
        extra_env={
            "REAL_HOME": str(real_home),
            "MMS_REAL_HOME": str(real_home),
            "ORIGINAL_HOME": str(real_home),
        },
    )

    assert str(real_home / ".mms" / ".venv") in output
    assert str(real_home / ".local" / "bin" / "mms") in output
    assert str(session_home / ".mms" / ".venv") not in output


def test_install_check_derives_real_home_from_session_home(tmp_path):
    real_home = tmp_path / "real-home"
    session_home = real_home / ".config" / "mms" / "codex-gateway" / "s" / "67890"
    real_home.mkdir(parents=True)
    session_home.mkdir(parents=True)

    output = _run_install_check(
        home=session_home,
        extra_env={
            "REAL_HOME": "",
            "MMS_REAL_HOME": "",
            "ORIGINAL_HOME": "",
        },
    )

    assert str(real_home / ".mms" / ".venv") in output
    assert str(real_home / ".local" / "bin" / "mms") in output
    assert str(session_home / ".mms" / ".venv") not in output


def test_piped_version_check_does_not_misclassify_repo_cwd_as_local_source():
    env = os.environ.copy()
    env.update(_version_env_overrides(stable_ref="v1.16.4", latest_tag_ref="v1.16.4"))
    completed = subprocess.run(
        ["bash", "-s", "--", "--lang", "en", "--ref", "v1.16.4", "--version"],
        cwd=ROOT_DIR,
        env=env,
        input=INSTALL_SCRIPT.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Planned install ref: v1.16.4" in completed.stdout
    assert "Install channel: latest-tag" in completed.stdout
    assert "local-source" not in completed.stdout


def test_piped_version_check_normalizes_git_deref_ref_suffix():
    env = os.environ.copy()
    env.update(_version_env_overrides(stable_ref="v1.16.4", latest_tag_ref="refs/tags/v2.10.3^{}"))
    completed = subprocess.run(
        ["bash", "-s", "--", "--lang", "en", "--latest-tag", "--version"],
        cwd=ROOT_DIR,
        env=env,
        input=INSTALL_SCRIPT.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Latest upstream tag (latest tag): v2.10.3" in completed.stdout
    assert "Planned install ref: v2.10.3" in completed.stdout
    assert "^{}" not in completed.stdout


def test_piped_explicit_ref_normalizes_git_ref_prefix_and_deref_suffix():
    env = os.environ.copy()
    env.update(_version_env_overrides())
    completed = subprocess.run(
        ["bash", "-s", "--", "--lang", "en", "--ref", "refs/tags/v2.10.3^{}", "--version"],
        cwd=ROOT_DIR,
        env=env,
        input=INSTALL_SCRIPT.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Planned install ref: v2.10.3" in completed.stdout
    assert "^{}" not in completed.stdout


def test_local_install_version_check_reports_local_source_channel():
    env = os.environ.copy()
    env.update(_version_env_overrides())
    completed = subprocess.run(
        ["bash", str(INSTALL_SCRIPT), "--lang", "en", "--version"],
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Install channel: local-source" in completed.stdout


def test_version_output_shows_current_stable_and_latest(tmp_path):
    home = tmp_path / "home"
    version_meta = home / ".config" / "mms" / "version.json"
    version_meta.parent.mkdir(parents=True)
    version_meta.write_text(
        (
            "{\n"
            '  "installed_ref": "v1.16.3",\n'
            '  "installed_version": "v1.16.3",\n'
            '  "install_channel": "latest-tag",\n'
            '  "preferred_language": "en"\n'
            "}\n"
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["HOME"] = str(home)
    env.update(_version_env_overrides(stable_ref="v1.16.5", latest_tag_ref="v1.16.6"))

    completed = subprocess.run(
        ["bash", "-s", "--", "--lang", "en", "--ref", "v1.16.6", "--version"],
        cwd=ROOT_DIR,
        env=env,
        input=INSTALL_SCRIPT.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Currently installed: v1.16.3" in completed.stdout
    assert "Stable release (latest release): v1.16.5" in completed.stdout
    assert "Latest upstream tag (latest tag): v1.16.6" in completed.stdout
    assert "Planned install ref: v1.16.6" in completed.stdout


def test_piped_channel_flags_resolve_stable_dev_and_canary_refs():
    env = os.environ.copy()
    env.update(_version_env_overrides(stable_ref="v1.16.5", latest_tag_ref="v1.16.6"))
    env["MMS_INSTALL_DEV_REF"] = "dev"
    env["MMS_INSTALL_CANARY_REF"] = "canary"

    stable = subprocess.run(
        ["bash", "-s", "--", "--lang", "en", "--channel", "stable", "--version"],
        cwd=ROOT_DIR,
        env=env,
        input=INSTALL_SCRIPT.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=True,
    )
    dev = subprocess.run(
        ["bash", "-s", "--", "--lang", "en", "--dev", "--version"],
        cwd=ROOT_DIR,
        env=env,
        input=INSTALL_SCRIPT.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=True,
    )
    canary = subprocess.run(
        ["bash", "-s", "--", "--lang", "en", "--canary", "--version"],
        cwd=ROOT_DIR,
        env=env,
        input=INSTALL_SCRIPT.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Planned install ref: v1.16.5" in stable.stdout
    assert "Install channel: stable" in stable.stdout
    assert "Dev ref: dev" in dev.stdout
    assert "Planned install ref: dev" in dev.stdout
    assert "Install channel: dev" in dev.stdout
    assert "Canary ref: canary" in canary.stdout
    assert "Planned install ref: canary" in canary.stdout
    assert "Install channel: canary" in canary.stdout


def test_dev_channel_defaults_to_dev_branch():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert 'DEV_CHANNEL_REF="${MMS_INSTALL_DEV_REF:-dev}"' in text


def test_dev_and_canary_channels_use_preview_db_root_for_primary_entrypoint():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "install_channel_uses_preview_root()" in text
    assert "dev|canary) return 0" in text
    assert 'export MMS_CONFIG_ROOT="\\${MMS_CONFIG_ROOT:-$PREVIEW_CONFIG_DIR}"' in text
    assert 'export MMS_PREVIEW_MODE="\\${MMS_PREVIEW_MODE:-mms-$INSTALL_CHANNEL}"' in text
    assert "install_primary_mms_entrypoint" in text
    assert 'ln -sf "$MMS_HOME/mms" "$target"' in text


def test_dev_channel_dry_run_reports_preview_config_root(tmp_path):
    home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.update(_version_env_overrides(stable_ref="v1.16.5", latest_tag_ref="v1.16.6"))

    completed = subprocess.run(
        ["bash", "-s", "--", "--lang", "en", "--dev", "--dry-run"],
        cwd=ROOT_DIR,
        env=env,
        input=INSTALL_SCRIPT.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=True,
    )

    assert f"config dir: {home}/.config/mms-next" in completed.stdout
    assert f"mms -> preview DB root ({home}/.config/mms-next)" in completed.stdout

    canary = subprocess.run(
        ["bash", "-s", "--", "--lang", "en", "--canary", "--dry-run"],
        cwd=ROOT_DIR,
        env=env,
        input=INSTALL_SCRIPT.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=True,
    )

    assert f"config dir: {home}/.config/mms-next" in canary.stdout
    assert f"mms -> preview DB root ({home}/.config/mms-next)" in canary.stdout


def test_stable_channel_dry_run_reports_stable_config_root(tmp_path):
    home = tmp_path / "home"
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.update(_version_env_overrides(stable_ref="v1.16.5", latest_tag_ref="v1.16.6"))

    completed = subprocess.run(
        ["bash", "-s", "--", "--lang", "en", "--channel", "stable", "--dry-run"],
        cwd=ROOT_DIR,
        env=env,
        input=INSTALL_SCRIPT.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=True,
    )

    assert f"config dir: {home}/.config/mms" in completed.stdout
    assert f"mms -> stable root ({home}/.config/mms)" in completed.stdout


def test_install_script_uses_npm_first_cli_installs():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    installer_text = (ROOT_DIR / "mms_installer.py").read_text(encoding="utf-8")

    assert "install_named_cli()" in text
    assert "npm_global_install_with_nvm_fallback" in text
    assert 'CLAUDE_CLI_PACKAGE_SPEC="${CLAUDE_CLI_PACKAGE_SPEC:-@anthropic-ai/claude-code@latest}"' in text
    assert 'CODEX_CLI_PACKAGE_SPEC="${CODEX_CLI_PACKAGE_SPEC:-@openai/codex@latest}"' in text
    assert 'OPENCODE_CLI_PACKAGE_SPEC="${OPENCODE_CLI_PACKAGE_SPEC:-opencode-ai@latest}"' in text
    assert "claude|codex|opencode" in text
    assert "npm install -g @openai/codex@latest" in installer_text


def test_repo_entrypoints_use_env_python():
    for entrypoint in ("mms", "mmf", "mmslogs"):
        first_line = (ROOT_DIR / entrypoint).read_text(encoding="utf-8").splitlines()[0]
        assert first_line == "#!/usr/bin/env python3"


def test_node22_setup_does_not_override_nvm_default():
    install_text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    installer_text = (ROOT_DIR / "mms_installer.py").read_text(encoding="utf-8")

    assert "nvm alias default" not in install_text
    assert "nvm alias default" not in installer_text
    assert "@qwen-code/qwen-code" not in installer_text


def test_install_script_selects_supported_python_for_venv():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "find_supported_python()" in text
    assert "python3.13" in text
    assert "bootstrap_managed_python()" in text
    assert "https://astral.sh/uv/install.sh" in text
    assert 'UV_NO_MODIFY_PATH=1' in text
    assert 'if ! "$(_python_bin)" -m venv "$VENV_DIR"; then' in text
    assert 'PYTHON_CMD="$resolved_python"' in text


def test_install_script_supports_fish_and_non_mutating_nvm_bootstrap():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "write_fish_path_rc()" in text
    assert "fish_add_path -g" in text
    assert "Ghostty/iTerm/Terminal" in text
    assert "PROFILE=/dev/null" in text
    assert "METHOD=script" in text
    assert "nvm alias default" not in text


def test_install_script_copies_vendor_directory():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert 'copy_dir_safely "$SOURCE_DIR/vendor" "$MMS_HOME/vendor"' in text


def test_install_script_copies_session_tool_scripts_directory():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert 'copy_dir_safely "$SOURCE_DIR/scripts" "$MMS_HOME/scripts"' in text
    assert '[ -d "$MMS_HOME/scripts" ] && find "$MMS_HOME/scripts" -type f -exec chmod +x {} +' in text


def test_install_script_copies_launcher_package_directories():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "for package_dir in mms_opencode mms_codex mms_claude mms_agy mms_pi mms_session mms_launcher mms_runtime mms_display mms_registry; do" in text
    assert 'copy_dir_safely "$SOURCE_DIR/$package_dir" "$MMS_HOME/$package_dir"' in text
    assert 'for stale_module in "$MMS_HOME"/mms_opencode_*.py "$MMS_HOME"/mms_codex_*.py "$MMS_HOME"/mms_claude_*.py "$MMS_HOME"/mms_agy_*.py "$MMS_HOME"/mms_pi_*.py "$MMS_HOME"/mms_session_*.py "$MMS_HOME"/mms_hook_commands.py "$MMS_HOME"/mms_mmc_launch.py "$MMS_HOME"/mms_tui_settings_actions.py "$MMS_HOME"/mms_tui_launcher_entry.py "$MMS_HOME"/mms_launcher_*.py "$MMS_HOME"/mms_runtime.py "$MMS_HOME"/mms_runtime_*.py "$MMS_HOME"/mms_launch_display.py "$MMS_HOME"/mms_model_display.py "$MMS_HOME"/mms_confirm_preview.py "$MMS_HOME"/mms_registry.py "$MMS_HOME"/mms_registry_*.py; do' in text


def test_local_channel_worktree_update_reminder_is_non_blocking():
    text = (ROOT_DIR / "scripts" / "link_local_channel_commands.sh").read_text(encoding="utf-8")

    assert 'MMS_LOCAL_UPDATE_FOREGROUND:-0' in text
    assert 'cached-remind --command "$MMS_COMMAND_NAME" --kind worktree' in text
    assert 'remind --command "$MMS_COMMAND_NAME" --kind worktree' in text
    assert '>/dev/null 2>&1 &' in text


def test_install_script_retires_mmc_entrypoint():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert '[ -f "$SOURCE_DIR/mmc" ] && cp "$SOURCE_DIR"/mmc "$MMS_HOME/"' not in text
    assert 'for f in "$SOURCE_DIR"/mmc*.py; do' not in text
    assert '[ -f "$MMS_HOME/mmc" ] && chmod +x "$MMS_HOME/mmc"' not in text
    assert '[ -f "$MMS_HOME/mmc" ] && rewrite_shebang "$MMS_HOME/mmc" "$PYTHON_PATH"' not in text
    assert 'ln -sf "$MMS_HOME/mmc" "$BIN_DIR/mmc"' not in text
    assert 'rm -f "$MMS_HOME/mmc"' in text
    assert '已移除 retired mmc 命令链接' in text


def test_install_script_copies_mmslogs_entrypoint_before_linking():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert '[ -f "$SOURCE_DIR/mmf" ] && cp "$SOURCE_DIR"/mmf "$MMS_HOME/"' in text
    assert '[ -f "$MMS_HOME/mmf" ] && chmod +x "$MMS_HOME/mmf"' in text
    assert '[ -f "$MMS_HOME/mmf" ] && rewrite_shebang "$MMS_HOME/mmf" "$PYTHON_PATH"' in text
    assert '[ -f "$MMS_HOME/mmf" ] && ln -sf "$MMS_HOME/mmf" "$BIN_DIR/mmf"' in text
    assert '[ -f "$SOURCE_DIR/mmslogs" ] && cp "$SOURCE_DIR"/mmslogs "$MMS_HOME/"' in text
    assert '[ -f "$MMS_HOME/mmslogs" ] && chmod +x "$MMS_HOME/mmslogs"' in text
    assert '[ -f "$MMS_HOME/mmslogs" ] && rewrite_shebang "$MMS_HOME/mmslogs" "$PYTHON_PATH"' in text
    assert 'ln -sf "$MMS_HOME/mmslogs" "$BIN_DIR/mmslogs"' in text


def test_install_script_mentions_bundled_session_assets():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "Bundled session assets" in text
    assert "xmem" in text
    assert "NSR is built in and enabled by default" in text
    assert "Web automation bundle (weber router + web-access logged-in Chrome + agent-browser headless)" in text


def test_install_check_reports_all_bundled_session_assets(tmp_path):
    home = tmp_path / "home"
    mms_home = home / ".mms"
    vendor = mms_home / "vendor"
    hooks = mms_home / "hooks"
    for path in (
        vendor / "caveman" / "skills" / "caveman",
        vendor / "caveman" / "hooks",
        vendor / "token-saver",
        vendor / "toon",
        vendor / "xmem",
        vendor / "web-access",
        vendor / "weber",
        vendor / "agent-browser",
        hooks,
    ):
        path.mkdir(parents=True, exist_ok=True)
    for path in (
        vendor / "caveman" / "skills" / "caveman" / "SKILL.md",
        vendor / "token-saver" / "SKILL.md",
        vendor / "toon" / "SKILL.md",
        vendor / "xmem" / "SKILL.md",
        vendor / "web-access" / "SKILL.md",
        vendor / "weber" / "SKILL.md",
        vendor / "agent-browser" / "SKILL.md",
    ):
        path.write_text("# asset\n", encoding="utf-8")
    (vendor / "caveman" / "hooks" / "caveman-activate.js").write_text("// activate\n", encoding="utf-8")
    (vendor / "caveman" / "hooks" / "caveman-mode-tracker.js").write_text("// tracker\n", encoding="utf-8")
    for name in ("nsr-builtin-hook.py", "nsr-claude-hook.sh", "nsr-codex-hook.sh"):
        (hooks / name).write_text("#!/bin/sh\n", encoding="utf-8")

    output = _run_install_check(home=home)

    assert ("Bundled session assets" in output) or ("内建 session assets" in output)
    for label in ("Caveman", "token-saver", "TOON", "xmem", "web-access", "weber", "agent-browser", "NSR"):
        assert f"✓ {label}:" in output


def test_install_script_installs_llm_operation_guide():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    guide_text = (ROOT_DIR / "docs" / "LLM_OPERATION_GUIDE.md").read_text(encoding="utf-8")

    assert 'docs/LLM_OPERATION_GUIDE.md' in text
    assert "LLM editing guide" in text
    assert "Human Gate" in guide_text
    assert "~/.config/mms/**" in guide_text


def test_install_script_retires_ccs_entrypoint():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert not (ROOT_DIR / "ccs").exists()
    assert "INSTALL_LEGACY_CCS" not in text
    assert "--install-legacy-ccs" not in text
    assert 'cp "$SOURCE_DIR"/ccs "$MMS_HOME/ccs"' not in text
    assert 'ln -sf "$MMS_HOME/ccs" "$BIN_DIR/ccs"' not in text
    assert 'rm -f "$MMS_HOME/ccs"' in text
    assert "Removed retired legacy ccs command link" in text


def test_install_check_omits_retired_ccs_status(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    output = _run_install_check(home=home)

    assert "ccs" not in output.lower()


def test_install_check_reports_mmf_mmslogs_and_warns_retired_mmc_link(tmp_path):
    home = tmp_path / "home"
    mms_home = home / ".mms"
    bin_dir = home / ".local" / "bin"
    mms_home.mkdir(parents=True)
    bin_dir.mkdir(parents=True)
    for name in ("mms", "mmf", "mmc", "mmslogs"):
        target = mms_home / name
        target.write_text("#!/bin/sh\n", encoding="utf-8")
        (bin_dir / name).symlink_to(target)

    output = _run_install_check(home=home)

    assert str(bin_dir / "mms") in output
    assert str(bin_dir / "mmf") in output
    assert "retired mmc" in output
    assert str(bin_dir / "mmslogs") in output


def test_install_script_updates_chinese_optional_copy():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "BrainKeeper 全量 context pack" in text
    assert "--install-brainkeeper-context" in text
    assert "--install-mindkeeper-context" in text
    assert "--brainkeeper-ref" in text
    assert "--mindkeeper-ref" in text
    assert "Web automation bundle = weber 路由器 + web-access 登录态 Chrome + agent-browser headless CLI。" in text
    assert "Caveman、TOON、token-saver、xmem" in text
    assert "NSR 也已内建" in text


def test_install_script_codegraph_auto_registers_missing_index():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    hook_text = (ROOT_DIR / "hooks" / "claude-codegraph-auto-index.sh").read_text(encoding="utf-8")
    readme_text = (ROOT_DIR / "README.zh-CN.md").read_text(encoding="utf-8")

    assert "自动 init/index" in text
    assert "codegraph init -i" in readme_text
    assert '"$CODEGRAPH_BIN" init "$repo_root"' in hook_text
    assert '"$CODEGRAPH_BIN" index "$repo_root"' in hook_text
    assert '"$CODEGRAPH_BIN" sync' in hook_text


def test_install_script_installs_brainkeeper_shortcuts_and_archive_fallback():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert 'BRAINKEEPER_DEFAULT_REF="${BRAINKEEPER_DEFAULT_REF:-${MINDKEEPER_DEFAULT_REF:-v2.4.1}}"' in text
    assert "ensure_node18_npm_for_optional_pack" in text
    assert "brainkeeper_node_command" in text
    assert "install_brainkeeper_from_archive" in text
    assert "BrainKeeper archive fallback" in text
    assert '"command": node_command' in text
    assert 'write_brainkeeper_bin_wrapper "bk"' in text
    assert 'write_brainkeeper_bin_wrapper "brainkeeper"' in text
    assert "find_brainkeeper_node" in text
    assert "Number(process.versions.node.split" in text
    assert "[ -x \"$BIN_DIR/bk\" ]" in text
    assert "[ -x \"$BIN_DIR/brainkeeper\" ]" in text


def test_install_script_has_optional_token_saver_pack():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "--install-token-saver" in text
    assert "INSTALL_TOKEN_SAVER" in text
    assert "optional_token_saver_installed" in text
    assert "install_optional_token_saver" in text
    assert "~/.codex/skills/token-saver" in text
    assert "~/.claude/skills/token-saver" in text
    assert 'write_mms_script_wrapper "token-saver"' in text
    assert 'write_mms_script_wrapper "mms-context"' in text
    assert 'write_mms_script_wrapper "token-gain"' in text
    assert 'write_mms_script_wrapper "mms-gain"' in text
    assert 'write_mms_script_wrapper "mms-toon"' in text


def test_install_script_has_optional_xmem_pack():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    readme_text = (ROOT_DIR / "README.zh-CN.md").read_text(encoding="utf-8")

    assert "--dry-run" in text
    assert "print_dry_run_plan" in text
    assert "--install-xmem" in text
    assert "--xmem-ref" in text
    assert "INSTALL_XMEM" in text
    assert "XMEM_REPO_URL" in text
    assert "optional_xmem_installed" in text
    assert "install_optional_xmem" in text
    assert "run_xmem_setup_onboarding" in text
    assert "~/.codex/skills/xmem" in text
    assert "~/.claude/skills/xmem" in text
    assert 'XMEM_HOME="$REAL_HOME/.xmem"' in text
    assert 'XMEM_HOST_HOME="$REAL_HOME"' in text
    assert '"$xmem_cmd" setup --root "$REAL_HOME" --scan-depth 2 --register-only --yes --no-sync' in text
    assert "bash install.sh --install-xmem" in readme_text


def test_install_script_dry_run_does_not_write_home(tmp_path):
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env.update(_version_env_overrides())

    completed = subprocess.run(
        ["bash", str(INSTALL_SCRIPT), "--lang", "en", "--install-xmem", "--dry-run"],
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "DRY RUN: no files will be written" in completed.stdout
    assert "would install xmem CLI/skill" in completed.stdout
    assert "xmem setup --root" in completed.stdout
    assert not (tmp_path / ".mms").exists()
    assert not (tmp_path / ".xmem").exists()
    assert not (tmp_path / ".local" / "share" / "xmem").exists()


def test_install_script_has_optional_claude_agent_packs():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "--install-ecc" in text
    assert "--install-omc" in text
    assert "--install-agent-packs" in text
    assert "INSTALL_ECC" in text
    assert "INSTALL_OMC" in text
    assert "install_optional_ecc" in text
    assert "install_optional_omc" in text
    assert "$MMS_HOME/agent-packs/everything-claude-code" in text
    assert "$MMS_HOME/agent-packs/oh-my-claudecode" in text


def test_install_script_uses_bundled_handover_continuity_pack():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "install_builtin_handover_continuity" in text
    assert "$MMS_HOME/vendor/handover" in text
    assert 'HOME="$REAL_HOME" "$(_python_bin)" "$installer_script"' in text
    assert "$SOURCE_DIR/vendor/handover" not in text
    assert "$REAL_HOME/auto-skills/shared-skills/handover" not in text
    assert (ROOT_DIR / "vendor" / "handover" / "scripts" / "install_global_commands.py").exists()


# ─── M29: Builtin handover continuity (offduty/onduty) tests ───

def test_install_script_defines_install_builtin_handover_continuity():
    """install.sh defines install_builtin_handover_continuity function."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "install_builtin_handover_continuity()" in text


def test_install_builtin_handover_calls_shared_installer_via_python_bin():
    """The builtin function calls shared install_global_commands.py via _python_bin."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    # Must reference the shared installer script
    assert "install_global_commands.py" in text
    # Must invoke it via _python_bin
    assert '"$(_python_bin)" "$installer_script"' in text or '"$(_python_bin)" "$installer_script"' in text


def test_install_builtin_handover_not_gated_by_brainkeeper_context():
    """The call to install_builtin_handover_continuity in main flow is NOT gated by --install-brainkeeper-context."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    # Find the main-flow call
    assert "install_builtin_handover_continuity" in text

    # In the main install flow, the call should be unconditional (not inside a
    # BRAINKEEPER_CONTEXT if-block).
    # The main flow call appears right after prepare_source_dir and before chmod.
    # We verify it's not wrapped by INSTALL_BRAINKEEPER_CONTEXT:
    # Pattern: the function call should appear outside any brainkeeper conditional.
    lines = text.splitlines()
    found_call = False
    for i, line in enumerate(lines):
        # The main-flow call (not the function definition itself)
        stripped = line.strip()
        if "install_builtin_handover_continuity" in stripped and "()" not in stripped:
            found_call = True
            # Walk back ~10 lines to ensure no open brainkeeper if
            context_start = max(0, i - 10)
            context = "\n".join(lines[context_start:i + 1])
            assert "INSTALL_BRAINKEEPER_CONTEXT" not in context, (
                f"install_builtin_handover_continuity call at line {i+1} is gated by INSTALL_BRAINKEEPER_CONTEXT"
            )
    assert found_call, "Did not find a main-flow call to install_builtin_handover_continuity"


def test_install_builtin_handover_does_not_reference_brainkeeper():
    """The builtin handover function body does not reference BRAINKEEPER or INSTALL_BRAINKEEPER_CONTEXT."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    body = _extract_shell_function_body(text, "install_builtin_handover_continuity")

    assert "BRAINKEEPER" not in body, (
        "install_builtin_handover_continuity body references BRAINKEEPER"
    )
    assert "INSTALL_BRAINKEEPER_CONTEXT" not in body, (
        "install_builtin_handover_continuity body references INSTALL_BRAINKEEPER_CONTEXT"
    )


def test_install_script_brainkeeper_context_flag_remains_optional():
    """--install-brainkeeper-context is still an optional gated flag, not default."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    # The flag should be parsed but not force-installed
    assert "--install-brainkeeper-context" in text
    # Default value should be 0
    assert "INSTALL_BRAINKEEPER_CONTEXT=0" in text


def test_handover_installer_installs_skill_surfaces_without_commands(tmp_path):
    completed = _run_handover_installer(tmp_path)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True

    skill_roots = [
        tmp_path / ".agents" / "skills",
        tmp_path / ".claude" / "skills",
        tmp_path / ".codex" / "skills",
        tmp_path / ".config" / "opencode" / "skills",
        tmp_path / ".opencode" / "skills",
    ]
    command_roots = [
        tmp_path / ".agents" / "commands",
        tmp_path / ".claude" / "commands",
        tmp_path / ".codex" / "commands",
        tmp_path / ".config" / "opencode" / "commands",
        tmp_path / ".opencode" / "commands",
    ]

    for skill_root in skill_roots:
        assert (skill_root / "handover").is_symlink()
        assert (skill_root / "offduty").is_symlink()
        assert (skill_root / "onduty").is_symlink()

    for command_root in command_roots:
        assert not (command_root / "offduty.md").exists()
        assert not (command_root / "onduty.md").exists()


def test_handover_public_docs_do_not_hardcode_developer_handover_path():
    """Public handover docs must not tell agents to run a developer checkout path."""
    root = ROOT_DIR / "vendor" / "handover"
    offenders = []
    for path in root.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if "/Users/xin/auto-skills/shared-skills/handover" in text:
            offenders.append(str(path.relative_to(ROOT_DIR)))

    assert offenders == []


def test_handover_alias_wrappers_resolve_from_public_skill_symlink(tmp_path):
    """Alias wrapper scripts must work when installed under an arbitrary HOME."""
    home = tmp_path / "home"
    skill_root = home / ".codex" / "skills"
    skill_root.mkdir(parents=True)
    (skill_root / "offduty").symlink_to(ROOT_DIR / "vendor" / "handover" / "aliases" / "offduty")
    (skill_root / "onduty").symlink_to(ROOT_DIR / "vendor" / "handover" / "aliases" / "onduty")

    env = os.environ.copy()
    env["HOME"] = str(home)
    for name in ("offduty", "onduty"):
        wrapper = skill_root / name / name
        completed = subprocess.run(
            [str(wrapper), "--help"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        output = completed.stdout + completed.stderr
        assert completed.returncode == 0, output
        assert f"continuity.py {name}" in output


def test_handover_installer_is_idempotent_on_repeat_runs(tmp_path):
    first = _run_handover_installer(tmp_path)
    second = _run_handover_installer(tmp_path)

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr

    second_payload = json.loads(second.stdout)
    statuses = {item["status"] for item in second_payload["results"]}
    assert statuses == {"ok", "ok_absent"}


def test_handover_installer_removes_legacy_command_symlinks(tmp_path):
    command_roots = [
        tmp_path / ".agents" / "commands",
        tmp_path / ".claude" / "commands",
        tmp_path / ".codex" / "commands",
        tmp_path / ".config" / "opencode" / "commands",
        tmp_path / ".opencode" / "commands",
    ]
    legacy_targets = {
        "offduty.md": ROOT_DIR / "vendor" / "handover" / "commands" / "offduty.md",
        "onduty.md": ROOT_DIR / "vendor" / "handover" / "commands" / "onduty.md",
    }

    for command_root in command_roots:
        command_root.mkdir(parents=True)
        for name, target in legacy_targets.items():
            (command_root / name).symlink_to(target)

    completed = _run_handover_installer(tmp_path)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    statuses = {item["status"] for item in payload["results"]}
    assert "removed_legacy_command_symlink" in statuses
    for command_root in command_roots:
        assert not (command_root / "offduty.md").exists()
        assert not (command_root / "onduty.md").exists()


def test_handover_installer_preserves_unmanaged_command_symlink(tmp_path):
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    unmanaged_target = tmp_path / "user-offduty.md"
    unmanaged_target.write_text("# user symlink target\n", encoding="utf-8")
    unmanaged = commands_dir / "offduty.md"
    unmanaged.symlink_to(unmanaged_target)

    completed = _run_handover_installer(tmp_path)

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    skipped = [item for item in payload["results"] if item["path"].endswith(".claude/commands/offduty.md")]
    assert skipped and skipped[0]["status"] == "skipped_existing_unmanaged"
    assert unmanaged.is_symlink()
    assert unmanaged.resolve(strict=False) == unmanaged_target


def test_handover_installer_preserves_unmanaged_command_files(tmp_path):
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    unmanaged = commands_dir / "offduty.md"
    unmanaged.write_text("# user owned\n", encoding="utf-8")

    completed = _run_handover_installer(tmp_path)

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    skipped = [item for item in payload["results"] if item["path"].endswith(".claude/commands/offduty.md")]
    assert skipped and skipped[0]["status"] == "skipped_existing_unmanaged"
    assert unmanaged.read_text(encoding="utf-8") == "# user owned\n"
    assert not unmanaged.is_symlink()


def test_install_check_reports_handover_installed_when_all_skill_symlinks_present(tmp_path):
    """--check reports installed only when all managed skill surfaces point to bundled vendor."""
    home = tmp_path / "home"
    skill_roots = [
        home / ".agents" / "skills",
        home / ".claude" / "skills",
        home / ".codex" / "skills",
        home / ".config" / "opencode" / "skills",
        home / ".opencode" / "skills",
    ]
    handover_target = _install_handover_vendor_fixture(home)
    offduty_target = handover_target / "aliases" / "offduty"
    onduty_target = handover_target / "aliases" / "onduty"

    for skill_dir in skill_roots:
        skill_dir.mkdir(parents=True)
        (skill_dir / "handover").symlink_to(handover_target)
        (skill_dir / "offduty").symlink_to(offduty_target)
        (skill_dir / "onduty").symlink_to(onduty_target)

    output = _run_install_check(
        home=home,
        extra_env={
            "REAL_HOME": str(home),
            "MMS_REAL_HOME": str(home),
            "ORIGINAL_HOME": str(home),
        },
    )

    assert ("offduty/onduty skill 已安装" in output) or ("offduty/onduty skills installed" in output)


def test_install_check_reports_handover_missing_when_skill_symlinks_target_old_source(tmp_path):
    """--check rejects stale handover symlinks even when all names exist."""
    home = tmp_path / "home"
    skill_roots = [
        home / ".agents" / "skills",
        home / ".claude" / "skills",
        home / ".codex" / "skills",
        home / ".config" / "opencode" / "skills",
        home / ".opencode" / "skills",
    ]
    stale_root = tmp_path / "old-shared-skills" / "handover"
    stale_offduty = stale_root / "aliases" / "offduty"
    stale_onduty = stale_root / "aliases" / "onduty"
    for target in (stale_root, stale_offduty, stale_onduty):
        target.mkdir(parents=True, exist_ok=True)

    for skill_dir in skill_roots:
        skill_dir.mkdir(parents=True)
        (skill_dir / "handover").symlink_to(stale_root)
        (skill_dir / "offduty").symlink_to(stale_offduty)
        (skill_dir / "onduty").symlink_to(stale_onduty)

    output = _run_install_check(
        home=home,
        extra_env={
            "REAL_HOME": str(home),
            "MMS_REAL_HOME": str(home),
            "ORIGINAL_HOME": str(home),
        },
    )

    assert ("offduty/onduty skill 未安装" in output) or ("offduty/onduty skills not installed" in output)


def test_install_check_reports_handover_missing_when_legacy_commands_exist(tmp_path):
    """--check rejects duplicate legacy command surfaces next to skill aliases."""
    home = tmp_path / "home"
    skill_roots = [
        home / ".agents" / "skills",
        home / ".claude" / "skills",
        home / ".codex" / "skills",
        home / ".config" / "opencode" / "skills",
        home / ".opencode" / "skills",
    ]
    handover_target = _install_handover_vendor_fixture(home)
    for skill_dir in skill_roots:
        skill_dir.mkdir(parents=True)
        (skill_dir / "handover").symlink_to(handover_target)
        (skill_dir / "offduty").symlink_to(handover_target / "aliases" / "offduty")
        (skill_dir / "onduty").symlink_to(handover_target / "aliases" / "onduty")

    commands_dir = home / ".codex" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "offduty.md").symlink_to(handover_target / "commands" / "offduty.md")

    output = _run_install_check(
        home=home,
        extra_env={
            "REAL_HOME": str(home),
            "MMS_REAL_HOME": str(home),
            "ORIGINAL_HOME": str(home),
        },
    )

    assert ("offduty/onduty skill 未安装" in output) or ("offduty/onduty skills not installed" in output)


def test_install_check_reports_handover_missing_when_opencode_skill_symlinks_absent(tmp_path):
    """--check stays missing when only Claude/Codex skill symlinks exist."""
    home = tmp_path / "home"
    claude_skills = home / ".claude" / "skills"
    codex_skills = home / ".codex" / "skills"
    claude_skills.mkdir(parents=True)
    codex_skills.mkdir(parents=True)
    handover_target = _install_handover_vendor_fixture(home)
    offduty_target = handover_target / "aliases" / "offduty"
    onduty_target = handover_target / "aliases" / "onduty"

    for skill_dir in (claude_skills, codex_skills):
        (skill_dir / "handover").symlink_to(handover_target)
        (skill_dir / "offduty").symlink_to(offduty_target)
        (skill_dir / "onduty").symlink_to(onduty_target)

    output = _run_install_check(
        home=home,
        extra_env={
            "REAL_HOME": str(home),
            "MMS_REAL_HOME": str(home),
            "ORIGINAL_HOME": str(home),
        },
    )

    assert ("offduty/onduty skill 未安装" in output) or ("offduty/onduty skills not installed" in output)


def test_install_check_reports_handover_missing_when_symlinks_absent(tmp_path):
    """--check reports offduty/onduty missing when symlinks do not exist."""
    home = tmp_path / "home"
    home.mkdir()

    output = _run_install_check(home=home)

    assert ("offduty/onduty skill 未安装" in output) or ("offduty/onduty skills not installed" in output)


def test_install_script_dry_run_mentions_offduty_onduty(tmp_path):
    """--dry-run output mentions would install/repair offduty/onduty."""
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env.update(_version_env_overrides())

    completed = subprocess.run(
        ["bash", str(INSTALL_SCRIPT), "--lang", "en", "--dry-run"],
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    stdout = completed.stdout
    assert ("offduty/onduty" in stdout), (
        f"--dry-run output should mention offduty/onduty; got: {stdout[:500]}"
    )
    assert ("would install" in stdout.lower() or "would install/repair" in stdout or "would install" in stdout), (
        f"--dry-run output should include 'would install'; got: {stdout[:500]}"
    )


def test_install_completion_hints_include_config_web_and_v2_preview_gate():
    """Install completion guide should point users at config UI and v2 preview gate."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "mms config web" in text
    assert "$BIN_DIR/mms config web" in text
    assert "打开浏览器配置中心" in text
    assert "mmf preview doctor --json" in text
    assert "mms migrate config-v2 --json" in text
    assert "stable promotion human gate" in text


def test_install_script_dry_run_does_not_create_home_dirs(tmp_path):
    """--dry-run does not create .claude/, .codex/, or .config/opencode under temp HOME."""
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env.update(_version_env_overrides())

    subprocess.run(
        ["bash", str(INSTALL_SCRIPT), "--lang", "en", "--dry-run"],
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert not (tmp_path / ".claude").exists(), ".claude/ should not be created by --dry-run"
    assert not (tmp_path / ".codex").exists(), ".codex/ should not be created by --dry-run"
    # .config/opencode might not exist, if it does it must be pre-existing
    assert not (tmp_path / ".config" / "opencode").exists(), (
        ".config/opencode should not be created by --dry-run"
    )
