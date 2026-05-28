import os
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
RESET_SCRIPT = ROOT_DIR / "scripts" / "reset_mms_install.sh"


def _run_reset(*args: str, home: Path, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["REAL_HOME"] = ""
    env["MMS_REAL_HOME"] = ""
    env["ORIGINAL_HOME"] = ""
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(RESET_SCRIPT), *args],
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def test_reset_mms_install_dry_run_reports_core_artifacts_without_removing(tmp_path):
    real_home = tmp_path / "real-home"
    (real_home / ".mms" / "bin").mkdir(parents=True)
    (real_home / ".config" / "mms" / "codex-gateway" / "s" / "12345").mkdir(parents=True)
    (real_home / ".local" / "bin").mkdir(parents=True)
    (real_home / ".local" / "bin" / "mms").symlink_to(real_home / ".mms" / "mms")
    (real_home / ".local" / "bin" / "mmf").symlink_to(real_home / ".mms" / "mmf")
    (real_home / ".local" / "bin" / "mmc").symlink_to(real_home / ".mms" / "mmc")
    (real_home / ".local" / "bin" / "ccs").symlink_to(
        real_home / ".config" / "mms" / "codex-gateway" / "s" / "12345" / "ccs"
    )

    completed = _run_reset(home=real_home)

    assert "dry-run" in completed.stdout
    assert str(real_home / ".mms") in completed.stdout
    assert str(real_home / ".config" / "mms") in completed.stdout
    assert str(real_home / ".local" / "bin" / "mms") in completed.stdout
    assert str(real_home / ".local" / "bin" / "mmf") in completed.stdout
    assert str(real_home / ".local" / "bin" / "mmc") in completed.stdout
    assert (real_home / ".mms").exists()
    assert (real_home / ".config" / "mms").exists()
    assert (real_home / ".local" / "bin" / "mms").is_symlink()


def test_reset_mms_install_apply_removes_only_mms_owned_artifacts(tmp_path):
    real_home = tmp_path / "real-home"
    (real_home / ".mms" / "bin").mkdir(parents=True)
    (real_home / ".config" / "mms" / "claude-gateway" / "s" / "67890").mkdir(parents=True)
    (real_home / ".local" / "bin").mkdir(parents=True)
    (real_home / ".local" / "bin" / "mms").symlink_to(real_home / ".mms" / "mms")
    (real_home / ".local" / "bin" / "mmf").symlink_to(real_home / ".mms" / "mmf")
    (real_home / ".local" / "bin" / "mmc").symlink_to(real_home / ".mms" / "mmc")
    (real_home / ".local" / "bin" / "ccs").symlink_to(real_home / ".mms" / "ccs")
    (real_home / ".local" / "bin" / "mmslogs").symlink_to(real_home / ".mms" / "mmslogs")
    healthy_codex = real_home / ".local" / "bin" / "codex"
    healthy_codex.symlink_to("/usr/local/bin/codex")

    completed = _run_reset("--apply", home=real_home)

    assert "reset applied" in completed.stdout
    assert not (real_home / ".mms").exists()
    assert not (real_home / ".config" / "mms").exists()
    assert not (real_home / ".local" / "bin" / "mms").exists()
    assert not (real_home / ".local" / "bin" / "mmf").exists()
    assert not (real_home / ".local" / "bin" / "mmc").exists()
    assert not (real_home / ".local" / "bin" / "ccs").exists()
    assert not (real_home / ".local" / "bin" / "mmslogs").exists()
    assert healthy_codex.is_symlink()


def test_reset_mms_install_include_shell_rc_only_removes_mms_marker_block(tmp_path):
    real_home = tmp_path / "real-home"
    real_home.mkdir(parents=True)
    zshrc = real_home / ".zshrc"
    zshrc.write_text(
        "\n".join(
            [
                'export PATH="/opt/homebrew/bin:$PATH"',
                "# Added by MMS",
                'export PATH="$HOME/.local/bin:$PATH"',
                "alias ll='ls -la'",
                "",
            ]
        ),
        encoding="utf-8",
    )

    completed = _run_reset("--apply", "--include-shell-rc", home=real_home)

    assert "shell rc marker" in completed.stdout
    content = zshrc.read_text(encoding="utf-8")
    assert "# Added by MMS" not in content
    assert 'export PATH="$HOME/.local/bin:$PATH"' not in content
    assert 'export PATH="/opt/homebrew/bin:$PATH"' in content
    assert "alias ll='ls -la'" in content
