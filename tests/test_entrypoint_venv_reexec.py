import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def _write_fake_venv_python(path: Path, marker: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env sh",
                f"printf '%s\\n' \"$MMS_VENV_REEXECED\" > {marker}",
                "printf '%s\\n' \"$@\" >> " + str(marker),
                "exit 123",
                "",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_mms_entrypoint_reexecs_into_managed_venv(tmp_path):
    real_home = tmp_path / "real-home"
    marker = tmp_path / "reexec.log"
    _write_fake_venv_python(real_home / ".mms" / ".venv" / "bin" / "python", marker)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "session-home" / ".config" / "mms" / "codex-gateway" / "s" / "12345"),
            "MMS_REAL_HOME": str(real_home),
            "REAL_HOME": "",
            "ORIGINAL_HOME": "",
        }
    )
    env.pop("MMS_SKIP_VENV_REEXEC", None)
    env.pop("MMS_VENV_REEXECED", None)

    completed = subprocess.run(
        [sys.executable, str(ROOT_DIR / "mms"), "config", "web"],
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 123
    lines = marker.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "1"
    assert lines[1:] == [str((ROOT_DIR / "mms").resolve()), "config", "web"]


def test_mmf_entrypoint_reexecs_into_managed_venv(tmp_path):
    real_home = tmp_path / "real-home"
    marker = tmp_path / "reexec.log"
    _write_fake_venv_python(real_home / ".mms" / ".venv" / "bin" / "python", marker)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "session-home" / ".config" / "mms-next" / "codex-gateway" / "s" / "12345"),
            "MMS_REAL_HOME": str(real_home),
            "REAL_HOME": "",
            "ORIGINAL_HOME": "",
        }
    )
    env.pop("MMS_SKIP_VENV_REEXEC", None)
    env.pop("MMS_VENV_REEXECED", None)

    completed = subprocess.run(
        [sys.executable, str(ROOT_DIR / "mmf"), "preview", "check", "--json"],
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 123
    lines = marker.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "1"
    assert lines[1:] == [str((ROOT_DIR / "mmf").resolve()), "preview", "check", "--json"]
