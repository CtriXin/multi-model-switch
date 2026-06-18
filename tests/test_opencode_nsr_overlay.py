from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mms_launchers


def test_opencode_nsr_disabled_by_default(monkeypatch, tmp_path):
    # Default OFF: without MMS_OPENCODE_NSR the plugin must not resolve or overlay.
    monkeypatch.delenv("MMS_OPENCODE_NSR", raising=False)
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    assert mms_launchers._opencode_nsr_plugin_enabled({}) is False
    assert mms_launchers._overlay_opencode_nsr_plugin(str(config_dir)) is False
    assert not (config_dir / "plugins" / "mms-nsr.ts").exists()


def test_opencode_nsr_overlays_when_opted_in(monkeypatch, tmp_path):
    monkeypatch.setenv("MMS_OPENCODE_NSR", "1")
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    assert mms_launchers._opencode_nsr_plugin_enabled({}) is True
    assert mms_launchers._overlay_opencode_nsr_plugin(str(config_dir)) is True
    target = config_dir / "plugins" / "mms-nsr.ts"
    assert target.exists()
    assert "NsrOpenCodePlugin" in target.read_text(encoding="utf-8")


def test_opencode_nsr_runtime_can_force_disable(monkeypatch, tmp_path):
    monkeypatch.setenv("MMS_OPENCODE_NSR", "1")
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    # Even opted-in via env, runtime disable wins.
    assert mms_launchers._opencode_nsr_plugin_enabled({"opencode_nsr": False}) is False
    assert mms_launchers._overlay_opencode_nsr_plugin(str(config_dir), {"opencode_nsr": False}) is False
    assert mms_launchers._opencode_nsr_plugin_enabled({"nsr_mode": "disable"}) is False
    assert mms_launchers._overlay_opencode_nsr_plugin(str(config_dir), {"nsr_mode": "disable"}) is False


def test_opencode_nsr_stop_uses_local_budget_not_builtin_repeat_guard(tmp_path):
    session_dir = tmp_path / ".nsr" / "sessions" / "session-a"
    session_dir.mkdir(parents=True)
    state_path = session_dir / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "runtime": {"mode": "active", "schema_version": 1},
                "goal": {"objective": "demo objective"},
                "loop": {
                    "status": "running",
                    "current_slice": "slice-a",
                    "current_slice_id": "slice-a",
                    "next_action": "continue work",
                },
                "quality": {},
                "gate": {},
            }
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["MMS_REAL_HOME"] = str(tmp_path)
    payload = json.dumps({"hook_event_name": "Stop", "session_id": "session-a", "cwd": str(ROOT)})

    first = subprocess.run(
        ["python3", str(ROOT / "hooks" / "nsr-builtin-hook.py"), "opencode"],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    second = subprocess.run(
        ["python3", str(ROOT / "hooks" / "nsr-builtin-hook.py"), "opencode"],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert first.returncode == 0
    assert second.returncode == 0
    assert json.loads(first.stdout)["decision"] == "block"
    assert json.loads(second.stdout)["decision"] == "block"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["loop"]["status"] == "running"
