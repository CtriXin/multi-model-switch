"""Streaming process watchdog for isolated Pi committee workers."""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


STREAM_QUEUE_MAX_CHUNKS = 64


@dataclass(frozen=True)
class WatchdogPolicy:
    wall_timeout_seconds: float
    idle_timeout_seconds: float
    max_output_bytes: int
    max_repeated_events: int
    terminate_grace_seconds: float = 3.0
    poll_interval_seconds: float = 0.05

    def validate(self) -> None:
        if self.wall_timeout_seconds <= 0:
            raise ValueError("wall timeout must be greater than zero")
        if self.idle_timeout_seconds <= 0:
            raise ValueError("idle timeout must be greater than zero")
        if self.max_output_bytes < 1:
            raise ValueError("max output bytes must be at least 1")
        if self.max_repeated_events < 2:
            raise ValueError("max repeated events must be at least 2")
        if self.terminate_grace_seconds < 0:
            raise ValueError("terminate grace must not be negative")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll interval must be greater than zero")

    def public(self) -> dict[str, int | float]:
        return {
            "wall_timeout_seconds": self.wall_timeout_seconds,
            "idle_timeout_seconds": self.idle_timeout_seconds,
            "max_output_bytes": self.max_output_bytes,
            "max_repeated_events": self.max_repeated_events,
            "terminate_grace_seconds": self.terminate_grace_seconds,
        }


class CancellationController:
    """Thread-safe cooperative cancellation shared by committee workers."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._reason = ""

    def cancel(self, reason: str) -> bool:
        normalized = str(reason or "cancelled").strip() or "cancelled"
        with self._lock:
            if self._event.is_set():
                return False
            self._reason = normalized
            self._event.set()
            return True

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

    def is_cancelled(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True)
class ProcessOutcome:
    terminal_reason: str
    returncode: int | None
    stdout: str
    stderr: str
    elapsed_ms: int
    stdout_bytes: int
    stderr_bytes: int
    peak_repeated_events: int
    terminated: bool
    forced_kill: bool

    def public(self) -> dict[str, int | bool | str | None]:
        return {
            "terminal_reason": self.terminal_reason,
            "returncode": self.returncode,
            "elapsed_ms": self.elapsed_ms,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "peak_repeated_events": self.peak_repeated_events,
            "terminated": self.terminated,
            "forced_kill": self.forced_kill,
        }


def run_process(
    command: Sequence[str],
    *,
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    policy: WatchdogPolicy,
    cancellation: CancellationController | None = None,
) -> ProcessOutcome:
    """Run a command with streaming bounded capture and group termination."""
    policy.validate()
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            list(command),
            cwd=Path(cwd),
            env=dict(env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=(os.name == "posix"),
        )
    except OSError as exc:
        return ProcessOutcome(
            terminal_reason="launch_error",
            returncode=None,
            stdout="",
            stderr=str(exc),
            elapsed_ms=int((time.monotonic() - started) * 1000),
            stdout_bytes=0,
            stderr_bytes=0,
            peak_repeated_events=0,
            terminated=False,
            forced_kill=False,
        )

    chunks: queue.Queue[tuple[str, bytes | None]] = queue.Queue(maxsize=STREAM_QUEUE_MAX_CHUNKS)
    readers = [
        threading.Thread(target=_read_stream, args=("stdout", process.stdout, chunks), daemon=True),
        threading.Thread(target=_read_stream, args=("stderr", process.stderr, chunks), daemon=True),
    ]
    for reader in readers:
        reader.start()

    captured = {"stdout": bytearray(), "stderr": bytearray()}
    line_buffers = {"stdout": bytearray(), "stderr": bytearray()}
    total_bytes = {"stdout": 0, "stderr": 0}
    repeat_state: dict[str, tuple[bytes, int]] = {"stdout": (b"", 0), "stderr": (b"", 0)}
    peak_repeated = 0
    eof_streams: set[str] = set()
    last_activity = started
    terminal_reason = "completed"
    terminated = False
    forced_kill = False

    while True:
        now = time.monotonic()
        if process.poll() is None:
            if cancellation is not None and cancellation.is_cancelled():
                terminal_reason = cancellation.reason or "cancelled"
            elif now - started >= policy.wall_timeout_seconds:
                terminal_reason = "wall_timeout"
            elif now - last_activity >= policy.idle_timeout_seconds:
                terminal_reason = "idle_timeout"
            if terminal_reason != "completed":
                terminated, forced_kill = _terminate_process_group(process, policy.terminate_grace_seconds)

        wait_for = min(policy.poll_interval_seconds, max(0.001, policy.idle_timeout_seconds))
        try:
            stream_name, chunk = chunks.get(timeout=wait_for)
        except queue.Empty:
            if process.poll() is not None and len(eof_streams) == 2:
                break
            continue

        if chunk is None:
            eof_streams.add(stream_name)
        else:
            last_activity = time.monotonic()
            total_bytes[stream_name] += len(chunk)
            captured[stream_name].extend(chunk)
            if len(captured[stream_name]) > policy.max_output_bytes:
                del captured[stream_name][: len(captured[stream_name]) - policy.max_output_bytes]
            line_buffers[stream_name].extend(chunk)
            repeat_state[stream_name], stream_peak, largest_event = _consume_lines(
                line_buffers[stream_name], repeat_state[stream_name]
            )
            peak_repeated = max(peak_repeated, stream_peak)
            if process.poll() is None and max(largest_event, len(line_buffers[stream_name])) > policy.max_output_bytes:
                terminal_reason = "output_limit"
                terminated, forced_kill = _terminate_process_group(process, policy.terminate_grace_seconds)
            elif process.poll() is None and peak_repeated >= policy.max_repeated_events:
                terminal_reason = "repetition_limit"
                terminated, forced_kill = _terminate_process_group(process, policy.terminate_grace_seconds)

        if process.poll() is not None and len(eof_streams) == 2:
            break

    for reader in readers:
        reader.join(timeout=0.2)
    returncode = process.poll()
    return ProcessOutcome(
        terminal_reason=terminal_reason,
        returncode=returncode,
        stdout=bytes(captured["stdout"]).decode("utf-8", errors="replace"),
        stderr=bytes(captured["stderr"]).decode("utf-8", errors="replace"),
        elapsed_ms=int((time.monotonic() - started) * 1000),
        stdout_bytes=total_bytes["stdout"],
        stderr_bytes=total_bytes["stderr"],
        peak_repeated_events=peak_repeated,
        terminated=terminated,
        forced_kill=forced_kill,
    )


def _read_stream(name: str, stream, chunks: queue.Queue[tuple[str, bytes | None]]) -> None:
    if stream is None:
        chunks.put((name, None))
        return
    try:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            chunks.put((name, chunk))
    finally:
        chunks.put((name, None))


def _consume_lines(buffer: bytearray, state: tuple[bytes, int]) -> tuple[tuple[bytes, int], int, int]:
    last_line, repeated = state
    peak = repeated
    largest_event = 0
    while True:
        newline = buffer.find(b"\n")
        if newline < 0:
            break
        line = bytes(buffer[:newline]).strip()
        del buffer[: newline + 1]
        if not line:
            continue
        largest_event = max(largest_event, len(line))
        if line == last_line:
            repeated += 1
        else:
            last_line = line
            repeated = 1
        peak = max(peak, repeated)
    return (last_line, repeated), peak, largest_event


def _terminate_process_group(process: subprocess.Popen[bytes], grace_seconds: float) -> tuple[bool, bool]:
    if process.poll() is not None:
        return False, False
    terminated = True
    if os.name == "posix":
        process_group_id = process.pid
        try:
            os.killpg(process_group_id, signal.SIGTERM)
        except ProcessLookupError:
            return terminated, False
        except OSError:
            process.terminate()
            try:
                process.wait(timeout=max(1.0, grace_seconds))
                return terminated, False
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=max(1.0, grace_seconds))
                return terminated, True
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            process.poll()
            if not _process_group_exists(process_group_id):
                return terminated, False
            time.sleep(0.01)
        if _process_group_exists(process_group_id):
            try:
                os.killpg(process_group_id, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=max(1.0, grace_seconds))
            return terminated, True
        return terminated, False
    else:
        process.terminate()
    try:
        process.wait(timeout=grace_seconds)
        return terminated, False
    except subprocess.TimeoutExpired:
        pass
    process.kill()
    process.wait(timeout=max(1.0, grace_seconds))
    return terminated, True


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
