"""Cross-platform checks for the flock shim, with a fake msvcrt for the Windows path."""
import errno
import os

import pytest

from mms_web import file_lock
from mms_web.file_lock import LOCK_EX, LOCK_NB, LOCK_SH, LOCK_UN, _windows_flock, flock


class FakeMsvcrt:
    LK_UNLCK = "LK_UNLCK"
    LK_NBLCK = "LK_NBLCK"
    LK_LOCK = "LK_LOCK"

    def __init__(self, failures=0):
        self.calls = []
        self.failures = failures

    def locking(self, fd, mode, nbytes):
        self.calls.append((mode, nbytes, os.lseek(fd, 0, os.SEEK_CUR)))
        if self.failures:
            self.failures -= 1
            raise OSError(errno.EACCES, "region locked")


def test_windows_nonblocking_lock_grows_empty_file_once(tmp_path):
    lock = tmp_path / "empty.lock"
    lock.touch()
    fake = FakeMsvcrt()
    with lock.open("r+b") as handle:
        _windows_flock(fake, handle, LOCK_EX | LOCK_NB)
        assert fake.calls == [(FakeMsvcrt.LK_NBLCK, 1, 0)]
        # A second holder sees the grown byte and must not write again.
        _windows_flock(fake, handle, LOCK_SH | LOCK_NB)
    assert lock.stat().st_size == 1
    assert fake.calls[1][0] == FakeMsvcrt.LK_NBLCK


def test_windows_blocking_lock_retries_instead_of_timing_out(tmp_path):
    lock = tmp_path / "wait.lock"
    lock.write_bytes(b"\0")
    fake = FakeMsvcrt(failures=3)
    with lock.open("r+b") as handle:
        _windows_flock(fake, handle, LOCK_EX, sleep=lambda _: None)
    assert [call[0] for call in fake.calls] == [FakeMsvcrt.LK_NBLCK] * 4
    assert lock.stat().st_size == 1  # never rewritten while waiting


def test_windows_unlock_targets_the_same_byte_and_swallows_release_errors(tmp_path):
    lock = tmp_path / "release.lock"
    lock.write_bytes(b"\0")

    class FailingUnlock(FakeMsvcrt):
        def locking(self, fd, mode, nbytes):
            super().locking(fd, mode, nbytes)
            raise OSError(errno.EACCES, "not held")

    fake = FailingUnlock()
    with lock.open("r+b") as handle:
        handle.seek(99, os.SEEK_END)
        _windows_flock(fake, handle, LOCK_UN)  # must not raise
    assert fake.calls == [(FakeMsvcrt.LK_UNLCK, 1, 0)]  # sought back to byte 0


def test_posix_shim_roundtrip_excludes_and_releases(tmp_path):
    if os.name == "nt":
        pytest.skip("posix fcntl semantics")
    lock = tmp_path / "posix.lock"
    first = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    second = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        flock(first, LOCK_EX | LOCK_NB)
        with pytest.raises(OSError):
            flock(second, LOCK_EX | LOCK_NB)
        flock(first, LOCK_UN)
        flock(second, LOCK_EX | LOCK_NB)  # released: acquisition works again
    finally:
        os.close(first)
        os.close(second)
