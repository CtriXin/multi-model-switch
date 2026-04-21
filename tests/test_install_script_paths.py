import os
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = ROOT_DIR / "install.sh"


def _run_install_check(*, home: Path, extra_env: dict[str, str] | None = None) -> str:
    env = os.environ.copy()
    env["HOME"] = str(home)
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
