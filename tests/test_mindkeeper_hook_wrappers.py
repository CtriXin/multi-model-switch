from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_installed_mindkeeper_wrappers_fallback_to_real_home_install(tmp_path):
    real_home = tmp_path / "real-home"
    mms_home = real_home / ".mms"
    hooks_dir = mms_home / "hooks"
    installed_hooks = real_home / ".local" / "share" / "mindkeeper" / "hooks"
    session_home = tmp_path / "session-home"
    marker = tmp_path / "marker.log"

    wrappers = [
        ("mindkeeper-session-start-hook.sh", "session-start.sh"),
        ("mindkeeper-session-end-hook.sh", "session-end.sh"),
        ("mindkeeper-token-monitor-hook.sh", "token-monitor-hook.sh"),
    ]

    for wrapper_name, target_name in wrappers:
        wrapper_src = ROOT_DIR / "hooks" / wrapper_name
        wrapper_dst = hooks_dir / wrapper_name
        wrapper_dst.parent.mkdir(parents=True, exist_ok=True)
        wrapper_dst.write_text(wrapper_src.read_text(encoding="utf-8"), encoding="utf-8")
        wrapper_dst.chmod(wrapper_src.stat().st_mode | stat.S_IXUSR)

        _write_executable(
            installed_hooks / target_name,
            (
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                f"printf '%s\\n' '{target_name}' >> '{marker}'\n"
                "cat >/dev/null || true\n"
            ),
        )

        env = os.environ.copy()
        env["HOME"] = str(session_home)
        env["MMS_REAL_HOME"] = str(real_home)
        env["REAL_HOME"] = str(real_home)
        env["ORIGINAL_HOME"] = str(real_home)

        subprocess.run(
            ["bash", str(wrapper_dst)],
            input="{}",
            text=True,
            env=env,
            check=True,
        )

    assert marker.read_text(encoding="utf-8").splitlines() == [
        "session-start.sh",
        "session-end.sh",
        "token-monitor-hook.sh",
    ]


def test_brainkeeper_wrappers_prefer_brainkeeper_home_over_legacy(tmp_path):
    real_home = tmp_path / "real-home"
    mms_home = real_home / ".mms"
    hooks_dir = mms_home / "hooks"
    brainkeeper_home = tmp_path / "brainkeeper-home"
    legacy_home = tmp_path / "mindkeeper-home"
    session_home = tmp_path / "session-home"
    marker = tmp_path / "marker.log"

    wrapper_src = ROOT_DIR / "hooks" / "brainkeeper-session-start-hook.sh"
    wrapper_dst = hooks_dir / "brainkeeper-session-start-hook.sh"
    wrapper_dst.parent.mkdir(parents=True, exist_ok=True)
    wrapper_dst.write_text(wrapper_src.read_text(encoding="utf-8"), encoding="utf-8")
    wrapper_dst.chmod(wrapper_src.stat().st_mode | stat.S_IXUSR)

    _write_executable(
        legacy_home / "hooks" / "session-start.sh",
        f"#!/usr/bin/env bash\nprintf '%s\\n' legacy >> '{marker}'\ncat >/dev/null || true\n",
    )
    _write_executable(
        brainkeeper_home / "hooks" / "session-start.sh",
        f"#!/usr/bin/env bash\nprintf '%s\\n' brainkeeper >> '{marker}'\ncat >/dev/null || true\n",
    )

    env = os.environ.copy()
    env["HOME"] = str(session_home)
    env["MMS_REAL_HOME"] = str(real_home)
    env["BRAINKEEPER_HOME"] = str(brainkeeper_home)
    env["MINDKEEPER_HOME"] = str(legacy_home)

    subprocess.run(
        ["bash", str(wrapper_dst)],
        input="{}",
        text=True,
        env=env,
        check=True,
    )

    assert marker.read_text(encoding="utf-8").splitlines() == ["brainkeeper"]
