"""Runtime bootstrap helpers for MMS entrypoints."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


MIN_PYTHON = (3, 11)
NODE_CLI_NAMES = {"claude", "agy"}


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


def _real_home_from_env(env=None):
    source = env if isinstance(env, dict) else os.environ
    home = (
        source.get("REAL_HOME")
        or source.get("MMS_REAL_HOME")
        or source.get("ORIGINAL_HOME")
        or source.get("HOME")
        or os.path.expanduser("~")
    )
    marker = f"{os.path.sep}.config{os.path.sep}mms{os.path.sep}"
    if marker in home:
        home = home.split(marker, 1)[0]
    return os.path.abspath(os.path.expanduser(str(home)))


def _semver_key(path_value):
    name = os.path.basename(str(path_value or "").rstrip(os.path.sep))
    if name.startswith("v"):
        name = name[1:]
    parts = []
    for item in name.split("."):
        if item.isdigit():
            parts.append(int(item))
        else:
            break
    return tuple(parts)


def _nvm_bin_dirs(real_home):
    root = os.path.join(real_home, ".nvm", "versions", "node")
    if not os.path.isdir(root):
        return []
    versions = [
        os.path.join(root, name)
        for name in os.listdir(root)
        if os.path.isdir(os.path.join(root, name))
    ]
    versions.sort(key=_semver_key, reverse=True)
    return [os.path.join(version, "bin") for version in versions]


def cli_search_dirs(env=None, real_home=None):
    source = env if isinstance(env, dict) else os.environ
    home = os.path.abspath(os.path.expanduser(real_home or _real_home_from_env(source)))
    path_dirs = str(source.get("PATH") or os.defpath).split(os.pathsep)
    preferred = [
        os.path.join(home, ".local", "bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ]
    return _dedupe([*path_dirs, *preferred, *_nvm_bin_dirs(home), "/usr/bin", "/bin"])


def resolve_cli_binary(command_name, env=None, real_home=None):
    name = str(command_name or "").strip()
    if not name:
        return ""
    source = env if isinstance(env, dict) else os.environ
    override = str(source.get(f"MMS_{name.upper()}_BIN") or "").strip()
    candidates = [override] if override else []
    search_path = os.pathsep.join(cli_search_dirs(source, real_home=real_home))
    found = shutil.which(name, path=search_path)
    if found:
        candidates.append(found)
    for candidate in candidates:
        if not candidate:
            continue
        path_value = candidate if os.path.isabs(candidate) else shutil.which(candidate, path=search_path)
        if path_value and os.path.isfile(path_value) and os.access(path_value, os.X_OK):
            return os.path.abspath(path_value)
    return ""


def prepend_binary_dir_to_path(env, binary_path):
    if not isinstance(env, dict):
        env = os.environ.copy()
    # Keep NVM/global-bin symlinks intact so npm CLIs use the matching node in that bin dir.
    binary_dir = os.path.dirname(os.path.abspath(binary_path))
    current = str(env.get("PATH") or os.defpath)
    parts = [item for item in current.split(os.pathsep) if item]
    if binary_dir not in parts:
        env = dict(env)
        env["PATH"] = os.pathsep.join([binary_dir, *parts])
    return env


def prepare_cli_command(cmd, env=None, real_home=None):
    if not cmd:
        return [], env if isinstance(env, dict) else os.environ.copy(), ""
    command_name = str(cmd[0] or "").strip()
    if os.path.isabs(command_name):
        binary = command_name if os.path.exists(command_name) else ""
    else:
        binary = resolve_cli_binary(command_name, env=env, real_home=real_home)
    if not binary:
        return list(cmd), env if isinstance(env, dict) else os.environ.copy(), ""
    prepared_env = prepend_binary_dir_to_path(env if isinstance(env, dict) else os.environ.copy(), binary)
    return [binary, *list(cmd[1:])], prepared_env, binary


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
