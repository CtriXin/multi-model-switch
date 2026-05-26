import os
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = ROOT_DIR / "install.sh"


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
    for entrypoint in ("mms", "mmslogs"):
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


def test_install_check_reports_mmslogs_and_warns_retired_mmc_link(tmp_path):
    home = tmp_path / "home"
    mms_home = home / ".mms"
    bin_dir = home / ".local" / "bin"
    mms_home.mkdir(parents=True)
    bin_dir.mkdir(parents=True)
    for name in ("mms", "mmc", "mmslogs"):
        target = mms_home / name
        target.write_text("#!/bin/sh\n", encoding="utf-8")
        (bin_dir / name).symlink_to(target)

    output = _run_install_check(home=home)

    assert str(bin_dir / "mms") in output
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
    assert "$SOURCE_DIR/vendor/handover" in text
    assert 'HOME="$REAL_HOME" "$(_python_bin)" "$installer_script"' in text
    assert "/Users/xin/auto-skills/shared-skills/handover" not in text
    assert (ROOT_DIR / "vendor" / "handover" / "scripts" / "install_global_commands.py").exists()
