import importlib.util
from pathlib import Path


def _load_smoke_pi_matrix():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "smoke_pi_matrix.py"
    spec = importlib.util.spec_from_file_location("smoke_pi_matrix_test", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_case_models_default_surface_excludes_blocked(monkeypatch):
    smoke_pi_matrix = _load_smoke_pi_matrix()

    monkeypatch.setattr(
        smoke_pi_matrix.mms_launchers,
        "_pi_exposed_model_names",
        lambda runtime: ["gpt-5.4"],
    )

    rows = smoke_pi_matrix.case_models(
        {"id": "relay-a"},
        include_blocked=False,
        blocked_only=False,
    )

    assert rows == [
        {
            "model": "gpt-5.4",
            "surface": "exposed",
            "blocked_reason": "",
        }
    ]


def test_case_models_can_target_blocked_only(monkeypatch):
    smoke_pi_matrix = _load_smoke_pi_matrix()

    monkeypatch.setattr(
        smoke_pi_matrix.mms_launchers,
        "_pi_runtime_model_names",
        lambda runtime: ["gpt-5.4", "gpt-5.5"],
    )
    monkeypatch.setattr(smoke_pi_matrix.mms_launchers, "_pi_model_supported", lambda _model_name: True)
    monkeypatch.setattr(
        smoke_pi_matrix.mms_launchers,
        "_pi_model_block_reason",
        lambda runtime, model_name: "token invalidated" if model_name == "gpt-5.5" else "",
    )

    rows = smoke_pi_matrix.case_models(
        {"id": "relay-a"},
        include_blocked=True,
        blocked_only=True,
    )

    assert rows == [
        {
            "model": "gpt-5.5",
            "surface": "blocked",
            "blocked_reason": "token invalidated",
        }
    ]


def test_aggregate_attempts_marks_flaky_when_pass_and_fail_mix():
    smoke_pi_matrix = _load_smoke_pi_matrix()

    result = smoke_pi_matrix.aggregate_attempts(
        [
            {
                "provider": "relay-a",
                "model": "gpt-5.4",
                "status": "pass",
                "content": "PONG",
                "errorMessage": "",
                "elapsed_sec": 1.2,
            },
            {
                "provider": "relay-a",
                "model": "gpt-5.4",
                "status": "request_fail",
                "content": "",
                "errorMessage": "401 token invalidated",
                "elapsed_sec": 1.4,
            },
        ]
    )

    assert result["status"] == "flaky"
    assert result["pass_count"] == 1
    assert result["attempt_count"] == 2
    assert result["pass_rate"] == 0.5
    assert result["attempt_statuses"] == ["pass", "request_fail"]
    assert result["content"] == "PONG"
    assert result["errorMessage"] == "401 token invalidated"


def test_temporarily_unblock_case_only_lifts_target_pair(monkeypatch):
    smoke_pi_matrix = _load_smoke_pi_matrix()

    def fake_block_reason(runtime, model_name):
        provider_id = str(runtime.get("id") or "").strip().lower()
        if provider_id == "relay-a" and model_name == "gpt-5.5":
            return "token invalidated"
        if provider_id == "relay-a" and model_name == "gpt-5.4":
            return "still blocked"
        return ""

    monkeypatch.setattr(smoke_pi_matrix.mms_launchers, "_pi_model_block_reason", fake_block_reason)

    runtime = {"id": "relay-a"}
    with smoke_pi_matrix.temporarily_unblock_case(runtime, "gpt-5.5", enabled=True):
        assert smoke_pi_matrix.mms_launchers._pi_model_block_reason(runtime, "gpt-5.5") == ""
        assert smoke_pi_matrix.mms_launchers._pi_model_block_reason(runtime, "gpt-5.4") == "still blocked"

    assert smoke_pi_matrix.mms_launchers._pi_model_block_reason(runtime, "gpt-5.5") == "token invalidated"
