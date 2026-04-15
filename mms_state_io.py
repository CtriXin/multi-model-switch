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
