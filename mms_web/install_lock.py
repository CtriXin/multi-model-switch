"""Prevent an in-place installer from replacing a live Pilot's source/deps."""
from .file_lock import LOCK_EX, LOCK_NB, LOCK_SH, LOCK_UN, flock
import hashlib
import os
import tempfile
from pathlib import Path
from .runtime import require_private_root


def acquire_runtime_lease(source):
    root = Path(os.environ.get('MMS_WEB_INSTALL_ROOT') or source).resolve()
    owner = getattr(os, "getuid", lambda: os.environ.get("USERNAME", "user"))()
    directory = require_private_root(Path(tempfile.gettempdir()) / f'mms-pilot-locks-{owner}')
    directory.mkdir(mode=0o700, exist_ok=True)
    if os.name != "nt" and (directory.stat().st_uid != owner or directory.stat().st_mode & 0o077):
        raise RuntimeError('Pilot 安装锁目录权限不安全。')
    name = hashlib.sha256(str(root).encode()).hexdigest() + '.lock'
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(directory / name, flags, 0o600)
    try:
        flock(fd, LOCK_SH | LOCK_NB)
    except OSError:
        os.close(fd)
        raise RuntimeError('MMS 安装正在进行，请完成后再打开 Pilot。') from None
    return fd
