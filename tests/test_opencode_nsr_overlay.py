from __future__ import annotations

from pathlib import Path
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
