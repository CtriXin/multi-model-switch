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
