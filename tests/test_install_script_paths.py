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


def test_installer_hook_cleanup_only_plans_and_preserves_read_once(tmp_path):
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")
    body = _extract_shell_function_body(script, "cleanup_legacy_global_session_hooks")
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

    before = {path: path.read_bytes() for path in (claude_settings, codex_hooks)}
    env = dict(os.environ, REAL_HOME=str(tmp_path), SOURCE_DIR=str(ROOT_DIR))
    completed = subprocess.run(
        ["bash", "-c", '_python_bin() { command -v python3; }\nrun_cleanup() {\n' + body + '\n}\nrun_cleanup'],
        text=True, capture_output=True, check=True, env=env,
    )
    report = json.loads(completed.stdout)
    assert sum(len(item["removed"]) for item in report["files"]) == 2
    assert all(path.read_bytes() == content for path, content in before.items())

    # An optional read-only plan must not become an installer prerequisite.
    claude_settings.write_text("invalid JSON")
    failed_plan = subprocess.run(
        ["bash", "-ec", '_python_bin() { command -v python3; }\nrun_cleanup() {\n' + body + '\n}\nrun_cleanup'],
        text=True, capture_output=True, env=env,
    )
    assert failed_plan.returncode == 0
    assert "settings left unchanged" in failed_plan.stderr
    assert claude_settings.read_text() == "invalid JSON"
    assert codex_hooks.read_bytes() == before[codex_hooks]


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
    assert "Install channel: pinned-ref" in completed.stdout
    assert "local-source" not in completed.stdout
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
    assert "Version track: 3.x Stable (3.x-stable)" in stable.stdout
    assert "Dev ref: dev" in dev.stdout
    assert "Planned install ref: dev" in dev.stdout
    assert "Install channel: dev" in dev.stdout
    assert "Version track: 4.0 Dev Preview (4.0.0-dev)" in dev.stdout
    assert "Canary ref: canary" in canary.stdout
    assert "Planned install ref: canary" in canary.stdout
    assert "Install channel: canary" in canary.stdout
    assert "Version track: 4.0 Canary Preview (4.0.0-canary)" in canary.stdout


def test_dev_channel_defaults_to_dev_branch():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert 'DEV_CHANNEL_REF="${MMS_INSTALL_DEV_REF:-dev}"' in text


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


def test_install_script_copies_config_web_static_assets():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert 'copy_dir_safely "$SOURCE_DIR/mms_config_web_static" "$MMS_HOME/mms_config_web_static"' in text


def test_install_script_copies_bundled_session_assets():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert 'copy_dir_safely "$SOURCE_DIR/assets" "$MMS_HOME/assets"' in text
    assert "$MMS_HOME/assets/session-assets" in text


def test_install_script_copies_bundled_provider_profiles():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    profile_path = ROOT_DIR / "config" / "provider-profiles.json"
    profile_text = profile_path.read_text(encoding="utf-8")

    assert 'copy_dir_safely "$SOURCE_DIR/config" "$MMS_HOME/config"' in text
    assert profile_path.exists()
    assert "glm-5.2" in profile_text
    assert "openrouter-moonshot-kimi-k3" in profile_text
    assert "kimi-k3" in profile_text
    assert "kimi-k2.7-code" in profile_text
    assert "minimax-m3" in profile_text


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


def test_install_script_describes_built_in_tools_in_plain_language():
    """The install screen must not spell out internal pack names at the user."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "xmem" not in text.lower()
    assert "Built-in tools" in text
    assert "web access, browser automation, token-saving tools" in text
    assert "only apply inside sessions MMS starts" in text
    # the jargon inventory is gone from the install screen
    assert "weber router + web-access logged-in Chrome + agent-browser headless" not in text
    assert "Bundled session assets" in text  # still fine in --check, which is for operators


def test_install_script_user_facing_lines_stay_short():
    """No line the installer prints at a newcomer should be a wall of text."""
    import re

    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    too_long = [
        zh
        for zh in re.findall(r't "([^"]{2,})" "', text)
        if any("\u4e00" <= c <= "\u9fff" for c in zh) and len(zh) > 90
    ]
    assert too_long == [], too_long

def test_install_check_reports_all_bundled_session_assets(tmp_path):
    home = tmp_path / "home"
    mms_home = home / ".mms"
    session_assets = mms_home / "assets" / "session-assets"
    hooks = mms_home / "hooks"
    for path in (
        session_assets / "packs" / "caveman" / "skills" / "caveman",
        session_assets / "packs" / "caveman" / "hooks",
        session_assets / "skills" / "token-saver",
        session_assets / "skills" / "toon",
        session_assets / "skills" / "web-access",
        session_assets / "skills" / "weber",
        session_assets / "skills" / "agent-browser",
        hooks,
    ):
        path.mkdir(parents=True, exist_ok=True)
    for path in (
        session_assets / "packs" / "caveman" / "skills" / "caveman" / "SKILL.md",
        session_assets / "skills" / "token-saver" / "SKILL.md",
        session_assets / "skills" / "toon" / "SKILL.md",
        session_assets / "skills" / "web-access" / "SKILL.md",
        session_assets / "skills" / "weber" / "SKILL.md",
        session_assets / "skills" / "agent-browser" / "SKILL.md",
    ):
        path.write_text("# asset\n", encoding="utf-8")
    (session_assets / "packs" / "caveman" / "hooks" / "caveman-activate.js").write_text("// activate\n", encoding="utf-8")
    (session_assets / "packs" / "caveman" / "hooks" / "caveman-mode-tracker.js").write_text("// tracker\n", encoding="utf-8")
    for name in (
        "nsr-builtin-hook.py",
        "nsr-loop-hook.py",
        "nsr-stop-wrapper.py",
        "nsr-commit-gate.py",
        "nsrctl.py",
        "nsr-claude-hook.sh",
        "nsr-codex-hook.sh",
    ):
        (hooks / name).write_text("#!/bin/sh\n", encoding="utf-8")

    output = _run_install_check(home=home)

    assert ("Bundled session assets" in output) or ("内建 session assets" in output)
    for label in ("Caveman", "token-saver", "TOON", "web-access", "weber", "agent-browser", "NSR"):
        assert f"✓ {label}:" in output


def test_install_script_installs_llm_operation_guide():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    guide_text = (ROOT_DIR / "docs" / "LLM_OPERATION_GUIDE.md").read_text(encoding="utf-8")

    assert 'docs/LLM_OPERATION_GUIDE.md' in text
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


def test_install_script_asks_nothing_that_changes_the_install():
    """No question may influence what gets installed."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "confirm_from_tty" not in text
    assert "read_from_tty" not in text
    assert "can_prompt_interactively" not in text
    assert "prompt_optional_install_choices" not in text
    assert "prompt_install_language" not in text
    assert "resolve_default_cli_installs" in text
    # the only terminal read is the closing MMS Web offer
    assert text.count("read -r answer < /dev/tty") == 1
    assert "confirm_open_web" in text


def test_install_script_defaults_are_newcomer_ready():
    """A bare `curl | bash` must land on the stable channel with a usable PATH."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    lines = text.splitlines()
    assert 'INSTALL_CHANNEL="stable"' in lines
    assert "WRITE_SHELL_RC=1" in lines
    assert 'LAUNCH_WEB_MODE="ask"' in lines
    assert "--no-shell-rc" in text
    assert "--launch-web" in text
    assert "--no-launch-web" in text


def test_install_script_launches_web_detached_and_configured():
    """MMS Web must outlive the installer and start with a real config root."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "start_mms_web_detached" in text
    assert 'nohup "$BIN_DIR/mms-web"' in text
    assert '--config-root "$config_root"' in text
    assert 'config_root="$REAL_HOME/.config/mms"' in text
    # a fixed port would crash the last install step when it is taken
    assert "find_free_web_port" in text
    assert "running_mms_web_port" in text
    assert "wait_for_mms_web" in text


def test_install_script_requires_pi_cli():
    """pi is mandatory: the pilot web app depends on it."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "PI_CLI_PACKAGE_SPEC" in text
    assert "@earendil-works/pi-coding-agent" in text
    assert "warm_pi_runtime_cache" in text
    assert "pi-cli-wrapper.sh" in text
    # pi is resolved first and is never skipped by an explicit --install-cli list
    assert "for cli_name in pi claude codex opencode; do" in text
    assert '[ "$cli_name" != "pi" ] && [ "$INSTALL_CLI_EXPLICIT" -eq 1 ]' in text


def test_install_script_ignores_removed_pack_flags():
    """Old --install-* flags must be ignored with a notice, not crash old scripts."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    for flag in (
        "--install-rtk",
        "--install-brainkeeper-context",
        "--install-map",
        "--install-codegraph",
        "--install-token-saver",
        "--install-toon",
        "--install-ops-env-safe",
        "--install-ecc",
        "--install-omc",
        "--install-agent-packs",
    ):
        assert flag in text, flag
    assert "该可选包已从安装器移除，本次忽略" in text
    assert "该可选包参数已从安装器移除，本次忽略" in text

def test_install_script_no_longer_installs_codegraph():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    hook_text = (ROOT_DIR / "hooks" / "claude-codegraph-auto-index.sh").read_text(encoding="utf-8")

    assert "install_optional_codegraph" not in text
    assert "CODEGRAPH_PACKAGE_SPEC" not in text
    assert "INSTALL_CODEGRAPH" not in text
    # the retired auto-index hook stays a no-op
    assert "exit 0" in hook_text
    assert "CODEGRAPH_BIN" not in hook_text

def test_install_script_removes_brainkeeper_pack():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "BRAINKEEPER_DEFAULT_REF" not in text
    assert "MINDKEEPER" not in text
    assert "install_brainkeeper_from_archive" not in text
    assert "write_brainkeeper_bin_wrapper" not in text
    assert "install_optional_brainkeeper_context" not in text
    assert "$BIN_DIR/bk" not in text

def test_install_script_removes_global_token_saver_and_toon_packs():
    """Global token-saver/TOON installs are gone; they remain bundled session assets."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "install_optional_token_saver" not in text
    assert "install_optional_toon" not in text
    assert "write_mms_script_wrapper" not in text
    assert "INSTALL_TOKEN_SAVER" not in text
    assert "INSTALL_TOON" not in text
    # still shipped as bundled session assets
    assert "$assets_root/skills/token-saver/SKILL.md" in text
    assert "$assets_root/skills/toon/SKILL.md" in text

def test_install_script_removes_optional_xmem_pack():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    readme_text = (ROOT_DIR / "README.zh-CN.md").read_text(encoding="utf-8")

    assert "--dry-run" in text
    assert "print_dry_run_plan" in text
    assert "--install-xmem" not in text
    assert "--xmem-ref" not in text
    assert "INSTALL_XMEM" not in text
    assert "XMEM_REPO_URL" not in text
    assert "optional_xmem_installed" not in text
    assert "install_optional_xmem" not in text
    assert "run_xmem_setup_onboarding" not in text
    assert "bash install.sh --install-xmem" not in readme_text


def test_install_script_dry_run_does_not_write_home(tmp_path):
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

    assert "DRY RUN: no files will be written" in completed.stdout
    assert "would install xmem CLI/skill" not in completed.stdout
    assert "xmem setup --root" not in completed.stdout
    assert not (tmp_path / ".mms").exists()
    assert not (tmp_path / ".xmem").exists()
    assert not (tmp_path / ".local" / "share" / "xmem").exists()


def test_install_script_removes_claude_agent_packs():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "install_optional_ecc" not in text
    assert "install_optional_omc" not in text
    assert "install_agent_pack_from_git" not in text
    assert "ECC_REPO_URL" not in text
    assert "OMC_REPO_URL" not in text
    # the pack names survive only in the cleanup path
    assert 'remove_retired_mms_dir "$MMS_HOME/agent-packs/everything-claude-code"' in text
    assert 'remove_retired_mms_dir "$MMS_HOME/agent-packs/oh-my-claudecode"' in text

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


def test_install_completion_points_at_the_web_app_and_v2_preview_gate():
    """Stable installs finish at MMS Web; preview installs still route through mmf."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    # stable path: the web app is the configuration surface
    assert "offer_mms_web" in text
    assert "在 MMS Web 里添加 provider 和 API Key" in text
    assert "bash install.sh --check" in text

    # preview path is unchanged
    assert "下一步（首次 preview/mmf 只做这两行）" in text
    assert "$NEXT_MMF_CMD preview prepare" in text
    assert "$NEXT_MMF_CMD config web" in text
    assert "$NEXT_MMF_CMD config doctor" in text

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


def test_published_v4_tag_has_v4_installer_track(tmp_path):
    env = os.environ.copy()
    env.update(_version_env_overrides(stable_ref="v4.0.0", latest_tag_ref="v4.0.0"))
    env["HOME"] = str(tmp_path)
    completed = subprocess.run(
        ["bash", "-s", "--", "--lang", "en", "--ref", "v4.0.0", "--version"],
        cwd=ROOT_DIR, env=env, input=INSTALL_SCRIPT.read_text(),
        capture_output=True, text=True, check=True,
    )
    assert "Planned install ref: v4.0.0" in completed.stdout
    assert "Version track: 4.x Stable (4.0.0)" in completed.stdout


def _plant_retired_pack_artifacts(home: Path) -> None:
    """Recreate what the removed optional packs used to write."""
    mms_marker = "Managed by MMS optional script wrapper"
    bk_marker = "Managed by MMS BrainKeeper context pack"
    ops_marker = "Managed by MMS optional ops-env-safe pack"

    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name in ("token-saver", "mms-context", "token-gain", "mms-gain", "mms-toon"):
        (bin_dir / name).write_text(f"#!/bin/sh\n# {mms_marker}\n", encoding="utf-8")
    for name in ("bk", "brainkeeper"):
        (bin_dir / name).write_text(f"#!/bin/sh\n# {bk_marker}\n", encoding="utf-8")

    commands = home / ".claude" / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    for name in ("distill", "contextzip", "cz", "cr"):
        (commands / f"{name}.md").write_text(f"<!-- {bk_marker} -->\n", encoding="utf-8")
    (commands / "ops-env-safe.md").write_text(f"<!-- {ops_marker} -->\n", encoding="utf-8")

    hooks = home / ".claude" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    for name in (
        "rtk-rewrite.sh",
        "token-monitor-hook.sh",
        "claude-context-restore-hint.sh",
    ):
        (hooks / name).write_text("#!/bin/sh\n", encoding="utf-8")

    vendor = home / ".mms" / "vendor"
    (vendor / "token-saver").mkdir(parents=True, exist_ok=True)
    (vendor / "toon").mkdir(parents=True, exist_ok=True)
    for cli in (".codex", ".claude"):
        skills = home / cli / "skills"
        skills.mkdir(parents=True, exist_ok=True)
        (skills / "token-saver").symlink_to(vendor / "token-saver")
        (skills / "toon").symlink_to(vendor / "toon")
    ops_skill = home / ".codex" / "skills" / "ops-env-safe"
    ops_skill.mkdir(parents=True, exist_ok=True)
    (ops_skill / "SKILL.md").write_text("---\nname: ops-env-safe\n---\n", encoding="utf-8")

    config_dir = home / ".config" / "mms"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "ops-env-safe.toml").write_text(
        f"# {ops_marker}\nmode = \"path-only\"\n", encoding="utf-8"
    )

    for pack in ("everything-claude-code", "oh-my-claudecode"):
        pack_dir = home / ".mms" / "agent-packs" / pack
        pack_dir.mkdir(parents=True, exist_ok=True)
        (pack_dir / "marker").write_text("pack\n", encoding="utf-8")

    settings = home / ".claude" / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": f"/bin/bash {hooks / 'rtk-rewrite.sh'}",
                                },
                                {"type": "command", "command": "/usr/local/bin/mine.sh"},
                            ],
                        }
                    ],
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "/x/claude-map-auto-index.sh",
                                }
                            ]
                        }
                    ],
                },
                "mcpServers": {
                    "codegraph": {"command": "/opt/homebrew/bin/codegraph"},
                    "brainkeeper": {"command": "node"},
                    "figma": {"command": "figma-mcp"},
                },
                "statusLine": {"type": "command", "command": "mine"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _run_retired_cleanup(home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.update(_version_env_overrides())
    return subprocess.run(
        ["bash", str(INSTALL_SCRIPT), "--cleanup-retired-packs"],
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def test_cleanup_removes_retired_pack_artifacts(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _plant_retired_pack_artifacts(home)

    _run_retired_cleanup(home)

    for name in (
        "token-saver",
        "mms-context",
        "token-gain",
        "mms-gain",
        "mms-toon",
        "bk",
        "brainkeeper",
    ):
        assert not (home / ".local" / "bin" / name).exists(), name
    for name in ("distill", "contextzip", "cz", "cr", "ops-env-safe"):
        assert not (home / ".claude" / "commands" / f"{name}.md").exists(), name
    for name in (
        "rtk-rewrite.sh",
        "token-monitor-hook.sh",
        "claude-context-restore-hint.sh",
    ):
        assert (home / ".claude" / "hooks" / name).exists(), name
    for cli in (".codex", ".claude"):
        assert not (home / cli / "skills" / "token-saver").is_symlink()
        assert not (home / cli / "skills" / "toon").is_symlink()
    assert (home / ".codex" / "skills" / "ops-env-safe").exists()
    assert (home / ".config" / "mms" / "ops-env-safe.toml").exists()
    assert not (home / ".mms" / "agent-packs").exists()


def test_cleanup_preserves_global_settings_and_archives_managed_entries(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _plant_retired_pack_artifacts(home)
    settings = home / ".claude" / "settings.json"
    before = settings.read_bytes()
    _run_retired_cleanup(home)
    assert settings.read_bytes() == before
    backups = list((home / ".mms").glob("retired-backup.*"))
    assert len(backups) == 1
    assert (backups[0] / ".local/bin/mms-toon").exists()
    assert (backups[0] / ".claude/commands/cz.md").exists()


def test_cleanup_preserves_user_owned_files(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _plant_retired_pack_artifacts(home)

    # user-owned lookalikes must survive
    bin_dir = home / ".local" / "bin"
    (bin_dir / "brainkeeper").write_text(
        "#!/bin/sh\n# User-local BrainKeeper launcher restored by hand.\n", encoding="utf-8"
    )
    (home / ".claude" / "commands" / "cz.md").write_text("my own command\n", encoding="utf-8")
    custom_skill = home / ".claude" / "skills" / "toon"
    custom_skill.unlink()
    custom_skill.mkdir(parents=True)
    (custom_skill / "SKILL.md").write_text("---\nname: toon\n---\n", encoding="utf-8")
    outside = home / "elsewhere" / "vendor" / "toon"
    outside.mkdir(parents=True)
    foreign_link = home / ".codex" / "skills" / "toon"
    foreign_link.unlink()
    foreign_link.symlink_to(outside)

    _run_retired_cleanup(home)

    assert (bin_dir / "brainkeeper").exists()
    assert (home / ".claude" / "commands" / "cz.md").read_text(encoding="utf-8") == "my own command\n"
    assert (custom_skill / "SKILL.md").exists()
    assert foreign_link.is_symlink()


def test_cleanup_is_idempotent_and_quiet_on_a_clean_machine(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    completed = _run_retired_cleanup(home)

    assert "没有需要清理的旧可选包" in completed.stdout or "No retired optional packs" in completed.stdout


FAKE_MMS_WEB = """#!/usr/bin/env python3
import hashlib
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

argv = sys.argv[1:]
port = int(argv[argv.index("--port") + 1])
log = Path(sys.argv[0]).parent / "mms-web-argv.json"
log.write_text(json.dumps(argv), encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "MMSWeb/1"

    def log_message(self, *_args):
        return

    def do_HEAD(self):
        self.send_response(200)
        home = Path(sys.argv[0]).parent.parent.parent
        identity = hashlib.sha256(f"{home / '.mms'}|{home / '.config/mms'}|".encode()).hexdigest()
        self.send_header("X-MMS-Web-Identity", identity)
        self.end_headers()

    do_GET = do_HEAD


ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""


def _installer_function_source() -> str:
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    return text[: text.index("while [[ $# -gt 0 ]]; do")]


def _run_installer_function(
    home: Path, snippet: str, *, port_base: int = 18765
) -> subprocess.CompletedProcess[str]:
    driver = home / "driver.sh"
    driver.write_text(_installer_function_source() + "\n" + snippet + "\n", encoding="utf-8")
    env = os.environ.copy()
    env["HOME"] = str(home)
    # keep the test off any MMS Web instance actually running on this machine
    env["MMS_WEB_PORT_BASE"] = str(port_base)
    for name in ("REAL_HOME", "MMS_REAL_HOME", "ORIGINAL_HOME", "MMS_CONFIG_ROOT"):
        env.pop(name, None)
    return subprocess.run(
        ["bash", str(driver)],
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


def _install_fake_mms_web(home: Path) -> Path:
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "mms-web"
    fake.write_text(FAKE_MMS_WEB, encoding="utf-8")
    fake.chmod(0o755)
    return fake


def _stop_fake_mms_web(home: Path) -> None:
    subprocess.run(
        ["pkill", "-f", str(home / ".local" / "bin" / "mms-web")],
        capture_output=True,
        check=False,
    )


def test_web_launch_starts_detached_with_a_real_config_root(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _install_fake_mms_web(home)
    try:
        completed = _run_installer_function(home, "start_mms_web_detached")
        assert completed.returncode == 0, completed.stderr

        argv = json.loads(
            (home / ".local" / "bin" / "mms-web-argv.json").read_text(encoding="utf-8")
        )
        assert "--open" in argv
        assert argv[argv.index("--config-root") + 1] == str(home / ".config" / "mms")
        # the address printed is the port the server actually got
        port = argv[argv.index("--port") + 1]
        assert f"http://127.0.0.1:{port}" in completed.stdout
    finally:
        _stop_fake_mms_web(home)


def test_web_launch_falls_back_when_the_default_port_is_taken(tmp_path):
    import socket

    home = tmp_path / "home"
    home.mkdir()
    _install_fake_mms_web(home)
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 18900))
    blocker.listen(1)
    try:
        completed = _run_installer_function(
            home, "start_mms_web_detached", port_base=18900
        )
        assert completed.returncode == 0, completed.stderr
        assert "http://127.0.0.1:18900" not in completed.stdout
        assert "http://127.0.0.1:1890" in completed.stdout
    finally:
        blocker.close()
        _stop_fake_mms_web(home)


def test_web_launch_reuses_an_already_running_instance(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _install_fake_mms_web(home)
    try:
        first = _run_installer_function(home, "start_mms_web_detached")
        assert first.returncode == 0, first.stderr
        (home / ".local" / "bin" / "mms-web-argv.json").unlink()

        second = _run_installer_function(home, "start_mms_web_detached")
        assert second.returncode == 0, second.stderr
        assert "已在运行" in second.stdout or "already running" in second.stdout
        assert not (home / ".local" / "bin" / "mms-web-argv.json").exists()
    finally:
        _stop_fake_mms_web(home)


def test_web_offer_without_a_terminal_prints_the_command_instead_of_asking(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _install_fake_mms_web(home)
    try:
        completed = _run_installer_function(
            home, 'LAUNCH_WEB_MODE="ask"\noffer_mms_web < /dev/null'
        )
        assert completed.returncode == 0, completed.stderr
        assert "mms-web --open" in completed.stdout
        assert not (home / ".local" / "bin" / "mms-web-argv.json").exists()
    finally:
        _stop_fake_mms_web(home)


def test_web_offer_respects_no_launch_web(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _install_fake_mms_web(home)
    try:
        completed = _run_installer_function(
            home, 'LAUNCH_WEB_MODE="never"\noffer_mms_web'
        )
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == ""
        assert not (home / ".local" / "bin" / "mms-web-argv.json").exists()
    finally:
        _stop_fake_mms_web(home)
