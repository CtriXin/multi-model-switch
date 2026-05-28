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


def test_run_direct_check_uses_claude_for_anthropic_cases(monkeypatch):
    smoke_pi_matrix = _load_smoke_pi_matrix()

    monkeypatch.setattr(
        smoke_pi_matrix.mms_launchers,
        "_pi_pick_protocol",
        lambda runtime, model_name: ({"protocol": "anthropic_messages"}, {}),
    )

    captured = {"calls": []}

    class _Completed:
        returncode = 2
        stdout = (
            '{"results":[{"provider":"relay-a","cli":"claude","ok":false,'
            '"route":"direct","model":"claude-sonnet-4-6","status":"500",'
            '"detail":"resolved=https://relay.example.com method=file_cached",'
            '"preview":null}]}'
        )
        stderr = ""

    def fake_run(cmd, capture_output, text, timeout):
        captured["calls"].append((list(cmd), timeout))
        return _Completed()

    monkeypatch.setattr(smoke_pi_matrix.subprocess, "run", fake_run)

    result = smoke_pi_matrix.run_direct_check(
        "relay-a",
        {"id": "relay-a"},
        "claude-sonnet-4-6",
        120,
    )

    first_cmd, first_timeout = captured["calls"][0]
    assert first_cmd[0].endswith("/mms")
    assert first_cmd[1:] == [
        "test",
        "--provider",
        "relay-a",
        "--cli",
        "claude",
        "--model",
        "claude-sonnet-4-6",
        "--timeout",
        "120",
        "--json",
    ]
    assert first_timeout == 120
    assert result == {
        "ok": False,
        "any_ok": False,
        "preferred_cli": "claude",
        "cli": "claude",
        "route": "direct",
        "status": "500",
        "detail": "resolved=https://relay.example.com method=file_cached",
        "preview": [],
        "rc": 2,
        "alternate_checks": [
            {
                "ok": False,
                "cli": "claude",
                "route": "direct",
                "status": "500",
                "detail": "resolved=https://relay.example.com method=file_cached",
                "preview": [],
                "rc": 2,
            }
        ],
    }


def test_maybe_attach_direct_check_skips_pass(monkeypatch):
    smoke_pi_matrix = _load_smoke_pi_matrix()
    monkeypatch.setattr(
        smoke_pi_matrix,
        "run_direct_check",
        lambda *args, **kwargs: {"status": "should-not-run"},
    )

    result = smoke_pi_matrix.maybe_attach_direct_check(
        {
            "provider": "relay-a",
            "model": "gpt-5.4",
            "status": "pass",
        },
        provider_id="relay-a",
        runtime={"id": "relay-a"},
        model_name="gpt-5.4",
        timeout_sec=90,
        enabled=True,
    )

    assert result == {
        "provider": "relay-a",
        "model": "gpt-5.4",
        "status": "pass",
    }


def test_direct_cli_for_case_falls_back_to_supported_cli(monkeypatch):
    smoke_pi_matrix = _load_smoke_pi_matrix()

    monkeypatch.setattr(
        smoke_pi_matrix.mms_launchers,
        "_pi_pick_protocol",
        lambda runtime, model_name: ({"protocol": "openai_chat_completions"}, {}),
    )

    cli = smoke_pi_matrix._direct_cli_for_case(
        {"id": "relay-a", "supported_clis": ["claude"]},
        "anthropic/claude-opus-4.7",
    )

    assert cli == "claude"


def test_run_direct_check_tries_alternate_supported_cli(monkeypatch):
    smoke_pi_matrix = _load_smoke_pi_matrix()

    monkeypatch.setattr(
        smoke_pi_matrix.mms_launchers,
        "_pi_pick_protocol",
        lambda runtime, model_name: ({"protocol": "anthropic_messages"}, {}),
    )

    calls = []

    def fake_run_single(provider_id, cli, model_name, timeout_sec):
        calls.append((provider_id, cli, model_name, timeout_sec))
        if cli == "claude":
            return {
                "ok": False,
                "cli": "claude",
                "route": "direct",
                "status": "500",
                "detail": "claude fail",
                "preview": [],
                "rc": 2,
            }
        return {
            "ok": True,
            "cli": "codex",
            "route": "chatcompletions_bridge",
            "status": "200",
            "detail": "codex pass",
            "preview": [],
            "rc": 0,
        }

    monkeypatch.setattr(smoke_pi_matrix, "_run_single_direct_check", fake_run_single)

    result = smoke_pi_matrix.run_direct_check(
        "relay-a",
        {"id": "relay-a", "supported_clis": ["claude", "codex"]},
        "gpt-5.4",
        90,
    )

    assert calls == [
        ("relay-a", "claude", "gpt-5.4", 90),
        ("relay-a", "codex", "gpt-5.4", 90),
    ]
    assert result["preferred_cli"] == "claude"
    assert result["any_ok"] is True
    assert result["alternate_checks"] == [
        {
            "ok": True,
            "cli": "codex",
            "route": "chatcompletions_bridge",
            "status": "200",
            "detail": "codex pass",
            "preview": [],
            "rc": 0,
        }
    ]
