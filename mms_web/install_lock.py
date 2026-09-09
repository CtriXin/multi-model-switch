"""Prevent an in-place installer from replacing a live Pilot's source/deps."""
import fcntl
import hashlib
import os
import tempfile
from pathlib import Path
from .runtime import require_private_root


def acquire_runtime_lease(source):
    root = Path(os.environ.get('MMS_WEB_INSTALL_ROOT') or source).resolve()
    directory = require_private_root(Path(tempfile.gettempdir()) / f'mms-pilot-locks-{os.getuid()}')
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
        raise RuntimeError('Pilot 安装锁目录权限不安全。')
    name = hashlib.sha256(str(root).encode()).hexdigest() + '.lock'
    fd = os.open(directory / name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise RuntimeError('MMS 安装正在进行，请完成后再打开 Pilot。') from None
    return fd
