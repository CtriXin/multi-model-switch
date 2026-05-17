"""Runtime bootstrap helpers for MMS entrypoints."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


MIN_PYTHON = (3, 11)


def _dedupe(values):
    seen = set()
    result = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _resolve_python(candidate):
    if os.path.sep in candidate:
        return candidate if os.path.exists(candidate) else ""
    return shutil.which(candidate) or ""


def _supports_min_python(executable):
    try:
        result = subprocess.run(
            [
                executable,
                "-c",
                (
                    "import sys; "
                    f"raise SystemExit(0 if sys.version_info >= {MIN_PYTHON!r} else 1)"
                ),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        return False
    return result.returncode == 0


def _candidate_pythons():
    return _dedupe(
        [
            os.environ.get("MMS_PYTHON", ""),
            "python3.13",
            "python3.12",
            "python3.11",
            "python3",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3",
        ]
    )


def ensure_supported_python(app_name="MMS"):
    """Re-exec through Python 3.11+ without changing user global Python."""
    if sys.version_info >= MIN_PYTHON:
        return

    if os.environ.get("MMS_PYTHON_REEXEC") != "1":
        current = os.path.realpath(sys.executable)
        for candidate in _candidate_pythons():
            executable = _resolve_python(candidate)
            if not executable:
                continue
            if os.path.realpath(executable) == current:
                continue
            if _supports_min_python(executable):
                env = os.environ.copy()
                env["MMS_PYTHON_REEXEC"] = "1"
                os.execve(executable, [executable, *sys.argv], env)

    current_version = ".".join(str(part) for part in sys.version_info[:3])
    required = ".".join(str(part) for part in MIN_PYTHON)
    sys.stderr.write(
        f"{app_name} 需要 Python {required}+；当前是 {current_version} ({sys.executable})。\n"
        "安装 Python 3.11+，或设置 MMS_PYTHON=/path/to/python 后重试。\n"
    )
    raise SystemExit(1)
