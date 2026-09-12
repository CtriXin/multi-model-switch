"""Small cross-platform advisory lock shim.

Windows has no ``fcntl`` module. ``msvcrt`` provides byte-range locking; this
shim keeps the fail-closed contract of the one-byte lock files used by MMS.

Deliberate semantic choices on Windows (all fail-closed):

* ``msvcrt`` has no shared mode, so ``LOCK_SH`` becomes an exclusive lock.
  Multiple Pilot processes sharing one install lease therefore serialize; the
  installer's exclusive probe still conflicts as intended.
* ``msvcrt.LK_LOCK`` gives up after about ten seconds and raises. ``fcntl``
  waits indefinitely, so a blocking acquisition here retries ``LK_NBLCK``
  forever instead of surfacing a spurious failure to callers.
* ``msvcrt.locking`` cannot lock a zero-length file portably, so an empty
  lock file is grown by one byte before locking. The byte is never user data:
  every caller locks a dedicated ``*.lock`` file.
"""
from __future__ import annotations

import os
import time

# Bit values only need to agree with this module's own constants; the POSIX
# branch below rebinds them to the real fcntl values.
LOCK_EX = 0x1
LOCK_SH = 0x2
LOCK_NB = 0x4
LOCK_UN = 0x8


def _windows_flock(msvcrt, handle, operation: int, *, sleep=time.sleep) -> None:
    """flock-equivalent on top of msvcrt; ``msvcrt`` is injected for tests."""
    fd = handle if isinstance(handle, int) else handle.fileno()
    os.lseek(fd, 0, os.SEEK_SET)
    if operation & LOCK_UN:
        # Unlock must name the exact locked region: offset 0, one byte.
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return
    if os.fstat(fd).st_size == 0:
        os.write(fd, b"\0")
        os.lseek(fd, 0, os.SEEK_SET)
    if operation & LOCK_NB:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return
    while True:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            sleep(0.05)


if os.name == "nt":  # pragma: no cover - exercised by the Windows CI job
    import msvcrt

    def flock(handle, operation: int) -> None:
        _windows_flock(msvcrt, handle, operation)
else:
    import fcntl as _fcntl

    LOCK_EX = _fcntl.LOCK_EX
    LOCK_SH = _fcntl.LOCK_SH
    LOCK_NB = _fcntl.LOCK_NB
    LOCK_UN = _fcntl.LOCK_UN

    def flock(handle, operation: int) -> None:
        _fcntl.flock(handle, operation)
