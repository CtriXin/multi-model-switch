from __future__ import annotations

import sys
import subprocess
import threading
import time
from pathlib import Path

import mms_pi_watchdog


def _policy(**overrides) -> mms_pi_watchdog.WatchdogPolicy:
    values = {
        "wall_timeout_seconds": 1.0,
        "idle_timeout_seconds": 0.4,
        "max_output_bytes": 64 * 1024,
        "max_repeated_events": 8,
        "terminate_grace_seconds": 0.5,
        "poll_interval_seconds": 0.01,
    }
    values.update(overrides)
    return mms_pi_watchdog.WatchdogPolicy(**values)


def _run(script: str, *, policy: mms_pi_watchdog.WatchdogPolicy, tmp_path: Path):
    return mms_pi_watchdog.run_process(
        [sys.executable, "-u", "-c", script],
        cwd=tmp_path,
        env={},
        policy=policy,
    )


def test_slow_but_active_process_completes(tmp_path: Path) -> None:
    outcome = _run(
        "import time; print('started', flush=True); time.sleep(0.12); print('finished', flush=True)",
        policy=_policy(idle_timeout_seconds=0.25),
        tmp_path=tmp_path,
    )

    assert outcome.terminal_reason == "completed"
    assert outcome.returncode == 0
    assert outcome.stdout.splitlines() == ["started", "finished"]


def test_idle_timeout_stops_silent_process(tmp_path: Path) -> None:
    outcome = _run(
        "import time; time.sleep(5)",
        policy=_policy(idle_timeout_seconds=0.1),
        tmp_path=tmp_path,
    )

    assert outcome.terminal_reason == "idle_timeout"
    assert outcome.terminated is True
    assert outcome.elapsed_ms < 1500


def test_wall_timeout_stops_process_that_keeps_emitting_unique_output(tmp_path: Path) -> None:
    outcome = _run(
        "import time\nfor i in range(100):\n print(i, flush=True)\n time.sleep(0.02)",
        policy=_policy(wall_timeout_seconds=0.18, idle_timeout_seconds=0.5),
        tmp_path=tmp_path,
    )

    assert outcome.terminal_reason == "wall_timeout"
    assert outcome.terminated is True


def test_repeated_event_limit_stops_loop(tmp_path: Path) -> None:
    outcome = _run(
        "import time\nfor _ in range(20):\n print('same-event', flush=True)\n time.sleep(0.01)\ntime.sleep(5)",
        policy=_policy(max_repeated_events=5),
        tmp_path=tmp_path,
    )

    assert outcome.terminal_reason == "repetition_limit"
    assert outcome.peak_repeated_events >= 5


def test_output_limit_bounds_capture_and_stops_process(tmp_path: Path) -> None:
    outcome = _run(
        "import sys,time; sys.stdout.write('x' * 8192); sys.stdout.flush(); time.sleep(5)",
        policy=_policy(max_output_bytes=1024),
        tmp_path=tmp_path,
    )

    assert outcome.terminal_reason == "output_limit"
    assert outcome.stdout_bytes > 1024
    assert len(outcome.stdout.encode()) <= 1024


def test_high_cumulative_framed_output_uses_bounded_tail_without_false_kill(tmp_path: Path) -> None:
    outcome = _run(
        "for i in range(80): print(f'{i:03d}-' + 'x' * 96, flush=True)",
        policy=_policy(max_output_bytes=1024),
        tmp_path=tmp_path,
    )

    assert outcome.terminal_reason == "completed"
    assert outcome.stdout_bytes > 1024
    assert len(outcome.stdout.encode()) <= 1024
    assert "079-" in outcome.stdout


def test_external_cancellation_stops_process(tmp_path: Path) -> None:
    controller = mms_pi_watchdog.CancellationController()
    timer = threading.Timer(0.1, lambda: controller.cancel("committee_timeout"))
    timer.start()
    try:
        outcome = mms_pi_watchdog.run_process(
            [sys.executable, "-u", "-c", "import time; time.sleep(5)"],
            cwd=tmp_path,
            env={},
            policy=_policy(),
            cancellation=controller,
        )
    finally:
        timer.cancel()

    assert outcome.terminal_reason == "committee_timeout"
    assert outcome.terminated is True


def test_timeout_signals_descendant_process_group(tmp_path: Path) -> None:
    marker = tmp_path / "child-terminated.txt"
    child = (
        "import signal,time,pathlib; "
        f"p=pathlib.Path({str(marker)!r}); "
        "signal.signal(signal.SIGTERM, lambda *_: (p.write_text('terminated'), exit(0))); "
        "print('child-ready', flush=True); time.sleep(5)"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-u', '-c', {child!r}]); "
        "time.sleep(5)"
    )

    outcome = _run(
        parent,
        policy=_policy(wall_timeout_seconds=0.4, idle_timeout_seconds=0.3),
        tmp_path=tmp_path,
    )
    deadline = time.monotonic() + 1
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.01)

    assert outcome.terminal_reason in {"idle_timeout", "wall_timeout"}
    assert marker.read_text() == "terminated"


def test_stubborn_descendant_forces_group_kill(tmp_path: Path) -> None:
    child = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); time.sleep(5)"
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-u', '-c', {child!r}]); "
        "time.sleep(5)"
    )

    outcome = _run(
        parent,
        policy=_policy(
            wall_timeout_seconds=0.35,
            idle_timeout_seconds=0.25,
            terminate_grace_seconds=0.1,
        ),
        tmp_path=tmp_path,
    )

    assert outcome.terminal_reason in {"idle_timeout", "wall_timeout"}
    assert outcome.forced_kill is True


def test_posix_group_signal_error_falls_back_to_force_kill(monkeypatch) -> None:
    class FakeProcess:
        pid = 12345

        def __init__(self):
            self.terminated = False
            self.killed = False
            self.waits = 0

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

        def wait(self, timeout):
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("fake", timeout)
            return -9

    process = FakeProcess()
    monkeypatch.setattr(mms_pi_watchdog.os, "killpg", lambda *_args: (_ for _ in ()).throw(OSError("no group")))

    terminated, forced = mms_pi_watchdog._terminate_process_group(process, 0.01)

    assert terminated is True
    assert forced is True
    assert process.terminated is True
    assert process.killed is True
