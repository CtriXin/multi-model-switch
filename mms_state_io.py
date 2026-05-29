from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None


_STATE_FILE_PROCESS_LOCK = threading.RLock()
_GATEWAY_SESSION_MARKERS = (
    os.path.join(".config", "mms", "codex-gateway", "s") + os.sep,
    os.path.join(".config", "mms", "claude-gateway", "s") + os.sep,
)


def utc_now_z(*, now_fn=None):
    now = (now_fn or datetime.now)(timezone.utc)
    return now.replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    explicit = str(env.get("MMS_CONFIG_DIR") or "").strip()
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))

    xdg_config_home = str(env.get("XDG_CONFIG_HOME") or "").strip()
    if xdg_config_home:
        normalized_xdg = os.path.abspath(os.path.expanduser(xdg_config_home))
        for marker in _GATEWAY_SESSION_MARKERS:
            idx = normalized_xdg.find(marker)
            if idx == -1:
                continue
            base_home = normalized_xdg[:idx]
            if base_home:
                return os.path.join(base_home, ".config", "mms")
        return os.path.join(normalized_xdg, "mms")

    return os.path.join(resolve_real_user_home(env), ".config", "mms")



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


def load_json_dict_unlocked(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
