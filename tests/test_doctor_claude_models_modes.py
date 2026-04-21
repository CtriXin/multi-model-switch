import importlib
import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

doctor_claude_models = importlib.import_module("doctor_claude_models")


def _patch_minimal_doctor_run(monkeypatch):
    captured = []

    monkeypatch.setattr(doctor_claude_models, "load_config", lambda: {"providers": []})
    monkeypatch.setattr(doctor_claude_models, "apply_local_overrides", lambda cfg: cfg)
    monkeypatch.setattr(doctor_claude_models, "_provider_map", lambda cfg: {"demo": {"enabled": True}})
    monkeypatch.setattr(doctor_claude_models, "_account_map", lambda cfg: {})

    def _fake_run_provider_checks(_cfg, _provider_id, _max_models, skip_claude_cli, _route_probe_timeout):
        captured.append(skip_claude_cli)
        return [], [], []

    monkeypatch.setattr(doctor_claude_models, "_run_provider_checks", _fake_run_provider_checks)
    monkeypatch.setattr(doctor_claude_models, "_render_summary_table", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(doctor_claude_models, "_render_table", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(doctor_claude_models.console, "print", lambda *_args, **_kwargs: None)
    return captured


def test_doctor_defaults_to_lite(monkeypatch):
    captured = _patch_minimal_doctor_run(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["doctor_claude_models.py"])

    exit_code = doctor_claude_models.main()

    assert exit_code == 0
    assert captured == [True]


def test_doctor_full_mode_enables_real_claude_cli(monkeypatch):
    captured = _patch_minimal_doctor_run(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["doctor_claude_models.py", "full"])

    exit_code = doctor_claude_models.main()

    assert exit_code == 0
    assert captured == [False]


def test_doctor_full_flag_enables_real_claude_cli(monkeypatch):
    captured = _patch_minimal_doctor_run(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["doctor_claude_models.py", "--full"])

    exit_code = doctor_claude_models.main()

    assert exit_code == 0
    assert captured == [False]


def test_doctor_rejects_conflicting_full_and_skip(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["doctor_claude_models.py", "full", "--skip-claude-cli"])

    with pytest.raises(SystemExit) as exc_info:
        doctor_claude_models.main()

    assert exc_info.value.code == 2
