from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import mms_flywheel


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_routes(root):
    router = {
        "version": 1,
        "routes": {
            "qwen3.7-max": {
                "primary": {
                    "provider_id": "direct-qwen",
                    "model_id": "qwen3.7-max",
                    "openai_base_url": "https://qwen.example/v1",
                    "api_key": "secret-qwen",
                },
                "fallbacks": [
                    {
                        "provider_id": "newapi-personal-tokyo",
                        "model_id": "qwen3.7-max",
                        "openai_base_url": "https://tokyo.example/v1",
                        "api_key": "secret-tokyo",
                    },
                    {
                        "provider_id": "newapi-tencent",
                        "model_id": "qwen3.7-max",
                        "openai_base_url": "https://tencent.example/v1",
                        "api_key": "secret-tencent",
                    },
                ],
            }
        },
    }
    lineup = {
        "version": 1,
        "routes": {
            "qwen3.7-max": {
                "primary": {
                    "provider_id": "direct-qwen",
                    "model_id": "qwen3.7-max",
                    "max_context_tokens": 1000000,
                    "reasoning_effort": "medium",
                    "thinking_mode": "enable",
                },
                "fallbacks": [
                    {"provider_id": "newapi-personal-tokyo", "model_id": "qwen3.7-max", "max_context_tokens": 800000},
                    {"provider_id": "newapi-tencent", "model_id": "qwen3.7-max", "max_context_tokens": 500000},
                ],
            }
        },
    }
    _write_json(root / "model-routes.json", router)
    _write_json(root / "model-routes.lineup.json", lineup)


def test_resolve_worker_profile_from_mms_config(tmp_path):
    root = tmp_path / "mms-next"
    root.mkdir()
    _seed_routes(root)
    (root / "config.toml").write_text(
        """
[flywheel.lanes.worker]
"AI-P3" = "flywheel.worker.p3"

[flywheel.profiles."flywheel.worker.p3"]
runtime = "opencode"
model = "qwen3.7-max"
provider = "direct-qwen"
reasoning_effort = "high"
thinking_mode = "disable"
""".strip(),
        encoding="utf-8",
    )

    resolved = mms_flywheel.resolve_flywheel_profile(
        lane="worker",
        priority="p3",
        config_root=str(root),
    )

    assert resolved["profile_id"] == "flywheel.worker.p3"
    assert resolved["runtime_kind"] == "opencode"
    assert resolved["model"] == "qwen3.7-max"
    assert resolved["provider_id"] == "direct-qwen"
    assert resolved["thinking_mode"] == "disable"
    assert resolved["reasoning_effort"] == "high"
    assert resolved["max_context_tokens"] == 1000000
    assert resolved["selected_route"]["slot"] == "primary"
    assert "api_key" not in resolved["selected_route"]
    assert [item["provider_id"] for item in resolved["fallback_routes"]] == [
        "newapi-personal-tokyo",
        "newapi-tencent",
    ]


def test_resolve_committee_default_without_model_route(tmp_path):
    root = tmp_path / "mms-next"
    root.mkdir()

    resolved = mms_flywheel.resolve_flywheel_profile(
        lane="committee",
        priority="AI-P0",
        config_root=str(root),
    )

    assert resolved["profile_id"] == "opencode-committee-heavy"
    assert resolved["runtime_kind"] == "opencode_profile"
    assert resolved["model"] == "opencode-committee-heavy"
    assert resolved["route_status"] == "not_applicable"


def test_resolve_fails_closed_for_unknown_provider(tmp_path):
    root = tmp_path / "mms-next"
    root.mkdir()
    _seed_routes(root)
    (root / "flywheel.toml").write_text(
        """
[lanes.worker]
"AI-P2" = "flywheel.worker.p2"

[profiles."flywheel.worker.p2"]
model = "qwen3.7-max"
provider = "missing-provider"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(mms_flywheel.FlywheelConfigError, match="missing-provider"):
        mms_flywheel.resolve_flywheel_profile(lane="worker", priority="AI-P2", config_root=str(root))


def test_handle_flywheel_resolve_json(tmp_path, capsys):
    root = tmp_path / "mms-next"
    root.mkdir()
    rc = mms_flywheel.handle_flywheel_command(
        ["resolve", "--lane", "committee", "--priority", "AI-P3", "--config-root", str(root), "--json"],
        command_name="mmf flywheel",
    )

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["ok"] is True
    assert out["result"]["profile_id"] == "opencode-committee-fast"


def test_mms_core_dispatches_flywheel_command(tmp_path, capsys, monkeypatch):
    import mms_core

    root = tmp_path / "mms-next"
    root.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        ["mmf", "flywheel", "resolve", "--lane", "committee", "--priority", "AI-P4", "--config-root", str(root), "--json"],
    )

    with pytest.raises(SystemExit) as exc:
        mms_core.main()

    out = json.loads(capsys.readouterr().out)
    assert exc.value.code == 0
    assert out["result"]["profile_id"] == "opencode-committee-fast"
