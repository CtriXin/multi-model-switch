import os
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
CLEANUP_SCRIPT = ROOT_DIR / "scripts" / "cleanup_dirty_install.sh"


def _run_cleanup(*args: str, home: Path, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["REAL_HOME"] = ""
    env["MMS_REAL_HOME"] = ""
    env["ORIGINAL_HOME"] = ""
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(CLEANUP_SCRIPT), *args],
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def test_cleanup_dirty_install_dry_run_reports_artifacts_without_removing(tmp_path):
    real_home = tmp_path / "real-home"
    session_home = real_home / ".config" / "mms" / "codex-gateway" / "s" / "12345"
    (session_home / ".mms" / "bin").mkdir(parents=True)
    (session_home / ".nvm").mkdir(parents=True)
    (session_home / ".config" / "mms").mkdir(parents=True)
    (session_home / ".local" / "bin").mkdir(parents=True)
    (real_home / ".local" / "bin").mkdir(parents=True)

    (session_home / ".local" / "bin" / "mms").symlink_to(session_home / ".mms" / "bin" / "mms")
    (session_home / ".local" / "bin" / "ccs").symlink_to(session_home / ".mms" / "bin" / "ccs")
    (real_home / ".local" / "bin" / "mms").symlink_to(session_home / ".mms" / "bin" / "mms")

    completed = _run_cleanup(home=real_home)

    assert "dry-run" in completed.stdout
    assert str(session_home / ".mms") in completed.stdout
    assert str(real_home / ".local" / "bin" / "mms") in completed.stdout
    assert (session_home / ".mms").exists()
    assert (real_home / ".local" / "bin" / "mms").is_symlink()


def test_cleanup_dirty_install_apply_removes_only_known_leaked_targets(tmp_path):
    real_home = tmp_path / "real-home"
    session_home = real_home / ".config" / "mms" / "claude-gateway" / "s" / "67890"
    leaked_mms = session_home / ".mms" / "bin"
    leaked_mms.mkdir(parents=True)
    (session_home / ".nvm").mkdir(parents=True)
    (session_home / ".config" / "mms").mkdir(parents=True)
    (session_home / ".local" / "bin").mkdir(parents=True)
    (real_home / ".local" / "bin").mkdir(parents=True)

    (session_home / ".local" / "bin" / "mms").symlink_to(leaked_mms / "mms")
    (session_home / ".local" / "bin" / "ccs").symlink_to(leaked_mms / "ccs")
    healthy_claude = session_home / ".local" / "bin" / "claude"
    healthy_claude.symlink_to("/usr/local/bin/claude")
    (real_home / ".local" / "bin" / "mms").symlink_to(leaked_mms / "mms")
    (real_home / ".local" / "bin" / "ccs").symlink_to(leaked_mms / "ccs")

    completed = _run_cleanup("--apply", home=session_home)

    assert "cleanup applied" in completed.stdout
    assert not (session_home / ".mms").exists()
    assert not (session_home / ".nvm").exists()
    assert not (session_home / ".config" / "mms").exists()
    assert not (session_home / ".local" / "bin" / "mms").exists()
    assert not (session_home / ".local" / "bin" / "ccs").exists()
    assert healthy_claude.is_symlink()
    assert not (real_home / ".local" / "bin" / "mms").exists()
    assert not (real_home / ".local" / "bin" / "ccs").exists()
