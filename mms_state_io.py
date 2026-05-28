from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None


_STATE_FILE_PROCESS_LOCK = threading.RLock()
_GATEWAY_SESSION_MARKERS = (
    os.path.join(".config", "mms", "codex-gateway", "s") + os.sep,
    os.path.join(".config", "mms", "claude-gateway", "s") + os.sep,
    os.path.join(".config", "mms", "accounts") + os.sep,
)


def resolve_real_user_home(env=None):
    env = env or os.environ
    for key in ("MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME"):
        raw = str(env.get(key) or "").strip()
        if raw:
            return os.path.abspath(os.path.expanduser(raw))

    home = os.path.abspath(os.path.expanduser(str(env.get("HOME") or "~")))
    normalized_home = os.path.normpath(home)
    for marker in _GATEWAY_SESSION_MARKERS:
        idx = normalized_home.find(marker)
        if idx == -1:
            continue
        base_home = normalized_home[:idx]
        if base_home:
            return base_home
    return home


def _path_from_env_value(raw):
    raw = str(raw or "").strip()
    if not raw:
        return ""
    expanded = os.path.expanduser(raw)
    if os.path.isabs(expanded):
        return os.path.normpath(expanded)
    try:
        return os.path.abspath(expanded)
    except OSError:
        return os.path.normpath(expanded)


def resolve_current_workdir(env=None, fallback=None):
    """Resolve project/workspace cwd without silently trusting real HOME."""
    env = env or os.environ
    try:
        cwd = os.getcwd()
        if cwd:
            return os.path.abspath(cwd)
    except FileNotFoundError:
        pass
    except OSError:
        pass

    for key in ("MMS_WORKSPACE", "PWD", "MMS_PROJECT_ROOT", "MMS_CWD", "MMS_HOST_CWD", "OLDPWD"):
        candidate = _path_from_env_value(env.get(key))
        if candidate:
            return candidate

    raw_fallback = _path_from_env_value(fallback)
    if raw_fallback:
        return raw_fallback

    # Last safe choice for deleted-cwd sessions is the isolated session home,
    # not the real user HOME. Real HOME is exposed separately via MMS_REAL_HOME.
    for key in ("MMS_SESSION_HOME", "CODEX_HOME", "GEMINI_CLI_HOME"):
        candidate = _path_from_env_value(env.get(key))
        if candidate:
            return candidate

    raise RuntimeError("unable to resolve current workdir after cwd disappeared")


def resolve_mms_config_dir(env=None):
    env = env or os.environ
    explicit_root = str(env.get("MMS_CONFIG_ROOT") or "").strip()
    if explicit_root:
        return _path_from_env_value(explicit_root)

    explicit = str(env.get("MMS_CONFIG_DIR") or "").strip()
    if explicit:
        return _path_from_env_value(explicit)

    xdg_config_home = str(env.get("XDG_CONFIG_HOME") or "").strip()
    if xdg_config_home:
        normalized_xdg = _path_from_env_value(xdg_config_home)
        for marker in _GATEWAY_SESSION_MARKERS:
            idx = normalized_xdg.find(marker)
            if idx == -1:
                continue
            base_home = normalized_xdg[:idx]
            if base_home:
                return os.path.join(base_home, ".config", "mms")
        return os.path.join(normalized_xdg, "mms")

    return os.path.join(resolve_real_user_home(env), ".config", "mms")


def mms_config_root_source(env=None):
    env = env or os.environ
    if str(env.get("MMS_CONFIG_ROOT") or "").strip():
        return "MMS_CONFIG_ROOT"
    if str(env.get("MMS_CONFIG_DIR") or "").strip():
        return "MMS_CONFIG_DIR"
    if str(env.get("XDG_CONFIG_HOME") or "").strip():
        return "XDG_CONFIG_HOME"
    return "real_home"


def mms_config_root_is_explicit(env=None):
    env = env or os.environ
    return bool(str(env.get("MMS_CONFIG_ROOT") or env.get("MMS_CONFIG_DIR") or "").strip())


def mms_config_root_mode(config_dir=None, env=None):
    env = env or os.environ
    marker = str(env.get("MMS_PREVIEW_MODE") or env.get("MMS_COMMAND_NAME") or "").strip().lower()
    root = os.path.normpath(str(config_dir or resolve_mms_config_dir(env)))
    if marker == "mmf" or os.path.basename(root) == "mms-next":
        return "preview"
    if mms_config_root_is_explicit(env):
        return "preview"
    return "stable"


def mms_config_root_status(command=None, config_dir=None, env=None):
    env = env or os.environ
    root = os.path.normpath(str(config_dir or resolve_mms_config_dir(env)))
    real_home = resolve_real_user_home(env)
    return {
        "command": str(command or env.get("MMS_COMMAND_NAME") or "mms"),
        "mode": mms_config_root_mode(root, env),
        "root_source": mms_config_root_source(env),
        "config_root": root,
        "config_path": os.path.join(root, "config.toml"),
        "credentials_path": os.path.join(root, "credentials.sh"),
        "usage_path": os.path.join(root, "usage.json"),
        "stable_root": os.path.join(real_home, ".config", "mms"),
        "preview_root": os.path.join(real_home, ".config", "mms-next"),
        "explicit_root": mms_config_root_is_explicit(env),
    }



@contextmanager
def locked_state_file(path):
    normalized_path = os.path.abspath(str(path or ""))
    if not normalized_path:
        raise ValueError("path is required")
    lock_path = normalized_path + ".lock"
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with _STATE_FILE_PROCESS_LOCK:
        with open(lock_path, "a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def atomic_write_text(path, text, *, mode=None):
    normalized_path = os.path.abspath(str(path or ""))
    if not normalized_path:
        raise ValueError("path is required")
    os.makedirs(os.path.dirname(normalized_path), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=os.path.basename(normalized_path) + ".",
        suffix=".tmp",
        dir=os.path.dirname(normalized_path),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(text))
        os.replace(temp_path, normalized_path)
        if mode is not None:
            os.chmod(normalized_path, mode)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def atomic_write_json(path, payload, *, mode=None, indent=2):
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=indent) + "\n",
        mode=mode,
    )
