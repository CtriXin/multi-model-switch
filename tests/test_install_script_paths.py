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


def test_install_script_uses_native_claude_and_official_codex_installs():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    installer_text = (ROOT_DIR / "mms_installer.py").read_text(encoding="utf-8")

    assert "https://claude.ai/install.sh" in text
    assert "npm_global_install_with_nvm_fallback" in text
    assert "@anthropic-ai/claude-code" in text
    assert "@openai/codex@latest" in text
    assert "npm install -g @openai/codex@latest" in installer_text


def test_repo_entrypoints_use_env_python():
    for entrypoint in ("mms", "ccs", "mmc", "mmslogs"):
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
    assert "nvm alias default" not in text


def test_install_script_copies_vendor_directory():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert 'copy_dir_safely "$SOURCE_DIR/vendor" "$MMS_HOME/vendor"' in text


def test_install_script_copies_session_tool_scripts_directory():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert 'copy_dir_safely "$SOURCE_DIR/scripts" "$MMS_HOME/scripts"' in text
    assert '[ -d "$MMS_HOME/scripts" ] && find "$MMS_HOME/scripts" -type f -exec chmod +x {} +' in text


def test_install_script_mentions_bundled_session_assets():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "Bundled session assets" in text
    assert "Caveman, weber, web-access, agent-browser, TOON, and token-saver" in text


def test_install_script_keeps_ccs_as_legacy_opt_in():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "INSTALL_LEGACY_CCS=0" in text
    assert "--install-legacy-ccs" in text
    assert 'ln -sf "$MMS_HOME/mms" "$BIN_DIR/mms"' in text
    assert 'if [ "$INSTALL_LEGACY_CCS" -eq 1 ]; then' in text
    assert 'ln -sf "$MMS_HOME/ccs" "$BIN_DIR/ccs"' in text
    assert "Legacy ccs symlink is no longer created by default" in text


def test_install_check_reports_legacy_ccs_as_disabled_by_default(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    output = _run_install_check(home=home)

    assert "legacy ccs 命令链接未启用（默认不再创建）" in output


def test_install_script_updates_chinese_optional_copy():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "BrainKeeper 上下文包会为 Claude 安装 /distill、/cz 和 token 监控 hook。" in text
    assert "--install-brainkeeper-context" in text
    assert "--install-mindkeeper-context" in text
    assert "--brainkeeper-ref" in text
    assert "--mindkeeper-ref" in text
    assert "Caveman、weber、web-access、agent-browser、TOON、token-saver 会随 MMS 一起作为内建 session 资产提供。" in text


def test_install_script_has_optional_token_saver_pack():
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "--install-token-saver" in text
    assert "INSTALL_TOKEN_SAVER" in text
    assert "optional_token_saver_installed" in text
    assert "install_optional_token_saver" in text
    assert "~/.codex/skills/token-saver" in text
    assert "~/.claude/skills/token-saver" in text
    assert 'write_token_saver_bin_wrapper "token-saver"' in text
    assert 'write_token_saver_bin_wrapper "mms-context"' in text
    assert 'write_token_saver_bin_wrapper "mms-toon"' in text


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
