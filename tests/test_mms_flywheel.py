from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

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


def _seed_dual_protocol_routes(root):
    router = {
        "version": 1,
        "routes": {
            "qwen3.7-max": {
                "primary": {
                    "provider_id": "dual-qwen",
                    "model_id": "qwen3.7-max",
                    "openai_base_url": "https://qwen.example/v1",
                    "anthropic_base_url": "https://qwen.example/v1",
                    "api_key": "secret-qwen",
                    "protocols": ["anthropic_messages", "openai_chat_completions"],
                    "cache_sensitive_transport": True,
                },
                "fallbacks": [],
            }
        },
    }
    lineup = {
        "version": 1,
        "routes": {
            "qwen3.7-max": {
                "primary": {
                    "provider_id": "dual-qwen",
                    "model_id": "qwen3.7-max",
                    "max_context_tokens": 1000000,
                },
                "fallbacks": [],
            }
        },
    }
    _write_json(root / "model-routes.json", router)
    _write_json(root / "model-routes.lineup.json", lineup)


def _write_qwen_worker_config(root: Path, *, effort: str = "high"):
    (root / "config.toml").write_text(
        """
[flywheel.lanes.worker]
"AI-P3" = "flywheel.worker.p3"

[flywheel.profiles."flywheel.worker.p3"]
runtime = "codex"
model = "qwen3.7-max"
provider = "direct-qwen"
reasoning_effort = "{effort}"
thinking_mode = "enable"
""".strip().format(effort=effort),
        encoding="utf-8",
    )


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


def test_run_dry_run_writes_sanitized_resolved_route_artifact(tmp_path):
    root = tmp_path / "mms-next"
    workdir = tmp_path / "work"
    artifact_dir = tmp_path / "artifacts"
    root.mkdir()
    workdir.mkdir()
    _seed_routes(root)
    _write_qwen_worker_config(root, effort="max")

    result = mms_flywheel.run_flywheel_lane(
        lane="worker",
        priority="AI-P3",
        config_root=str(root),
        cwd=str(workdir),
        artifact_dir=str(artifact_dir),
        runner_args=["exec", "--model", "ignored-by-mms", "do the task"],
        dry_run=True,
    )

    artifact = Path(result["resolved_route_path"])
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["status"] == "dry_run"
    assert result["model"] == "qwen3.7-max"
    assert result["provider_id"] == "direct-qwen"
    assert payload["runtime"]["reasoning_effort"] == "xhigh"
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "secret-qwen" not in serialized
    assert "https://qwen.example" not in serialized
    assert "api_key" not in payload["runtime"]
    assert "openai_base_url" not in payload["runtime"]


def test_run_dry_run_emits_cache_transport_evidence_for_dual_protocol_route(tmp_path):
    root = tmp_path / "mms-next"
    workdir = tmp_path / "work"
    artifact_dir = tmp_path / "artifacts"
    root.mkdir()
    workdir.mkdir()
    _seed_dual_protocol_routes(root)
    (root / "config.toml").write_text(
        """
[flywheel.lanes.worker]
"AI-P3" = "flywheel.worker.p3"

[flywheel.profiles."flywheel.worker.p3"]
runtime = "codex"
model = "qwen3.7-max"
provider = "dual-qwen"
""".strip(),
        encoding="utf-8",
    )

    result = mms_flywheel.run_flywheel_lane(
        lane="worker",
        priority="AI-P3",
        config_root=str(root),
        cwd=str(workdir),
        artifact_dir=str(artifact_dir),
        runner_args=["exec", "do the task"],
        dry_run=True,
    )

    artifact = json.loads(Path(result["resolved_route_path"]).read_text(encoding="utf-8"))
    run_artifact = json.loads(Path(result["run_result_path"]).read_text(encoding="utf-8"))
    evidence = result["cache_transport_evidence"]
    assert evidence["schema"] == "cache_transport_evidence.v1"
    assert evidence["protocol"] == "anthropic_messages"
    assert evidence["request_path"] == "/v1/messages"
    assert evidence["request_url"] == ""
    assert evidence["fallback_used"] is False
    assert artifact["cache_transport_evidence"] == evidence
    assert run_artifact["result"]["cache_transport_evidence"] == evidence
    assert artifact["runtime"]["preferred_transport"] == "anthropic_messages"
    serialized = json.dumps(artifact, ensure_ascii=False)
    assert "secret-qwen" not in serialized
    assert "https://qwen.example" not in serialized


def test_run_fake_response_emits_raw_looper_marker(tmp_path, monkeypatch, capsys):
    root = tmp_path / "mms-next"
    workdir = tmp_path / "work"
    root.mkdir()
    workdir.mkdir()
    _seed_routes(root)
    _write_qwen_worker_config(root)
    monkeypatch.setenv(
        "MMS_FLYWHEEL_RUN_FAKE_RESPONSE",
        'done\n__LOOPER_RESULT__={"summary":"ok","git_pr_lifecycle":{"prUrl":"https://github.com/CtriXin/EchoMind/pull/1"}}\n',
    )

    rc = mms_flywheel.handle_flywheel_command(
        [
            "run",
            "--lane",
            "worker",
            "--priority",
            "AI-P3",
            "--config-root",
            str(root),
            "--cwd",
            str(workdir),
            "exec",
            "--model",
            "ignored",
            "ship it",
        ],
        command_name="mmf flywheel",
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert 'done\n__LOOPER_RESULT__={"summary":"ok"' in out


def test_run_invokes_codex_runner_with_raw_runtime_but_json_output_is_safe(tmp_path, monkeypatch, capsys):
    root = tmp_path / "mms-next"
    workdir = tmp_path / "work"
    root.mkdir()
    workdir.mkdir()
    _seed_routes(root)
    _write_qwen_worker_config(root)
    captured = {}

    def fake_run_codex_headless(*, runtime, model, prompt, cwd, sandbox):
        captured["runtime"] = runtime
        captured["model"] = model
        captured["prompt"] = prompt
        captured["cwd"] = cwd
        captured["sandbox"] = sandbox
        return (
            0,
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "agent text"}}),
            "",
        )

    monkeypatch.setattr(mms_flywheel, "_run_codex_headless", fake_run_codex_headless)

    rc = mms_flywheel.handle_flywheel_command(
        [
            "run",
            "--lane",
            "worker",
            "--priority",
            "AI-P3",
            "--config-root",
            str(root),
            "--cwd",
            str(workdir),
            "--json",
            "--",
            "fix this",
        ],
        command_name="mmf flywheel",
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    assert payload["result"]["agent_text"] == "agent text"
    assert captured["runtime"]["api_key"] == "secret-qwen"
    assert captured["runtime"]["openai_base_url"] == "https://qwen.example/v1"
    assert captured["model"] == "qwen3.7-max"
    assert captured["prompt"] == "fix this"
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "secret-qwen" not in serialized
    assert "https://qwen.example" not in serialized


def test_run_invokes_codex_runner_with_anthropic_transport_for_dual_protocol_route(tmp_path, monkeypatch):
    root = tmp_path / "mms-next"
    workdir = tmp_path / "work"
    root.mkdir()
    workdir.mkdir()
    _seed_dual_protocol_routes(root)
    (root / "config.toml").write_text(
        """
[flywheel.lanes.worker]
"AI-P3" = "flywheel.worker.p3"

[flywheel.profiles."flywheel.worker.p3"]
runtime = "codex"
model = "qwen3.7-max"
provider = "dual-qwen"
""".strip(),
        encoding="utf-8",
    )
    captured = {}

    def fake_run_codex_headless(*, runtime, model, prompt, cwd, sandbox):
        captured["runtime"] = runtime
        captured["model"] = model
        return (
            0,
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "agent text"}}),
            "",
        )

    monkeypatch.setattr(mms_flywheel, "_run_codex_headless", fake_run_codex_headless)

    result = mms_flywheel.run_flywheel_lane(
        lane="worker",
        priority="AI-P3",
        config_root=str(root),
        cwd=str(workdir),
        runner_args=["exec", "fix this"],
    )

    assert result["ok"] is True
    assert captured["runtime"]["preferred_transport"] == "anthropic_messages"
    assert captured["runtime"]["transport_request_path"] == "/v1/messages"
    assert captured["runtime"]["cache_transport_evidence"]["protocol"] == "anthropic_messages"
    assert captured["runtime"]["api_key"] == "secret-qwen"
    assert captured["model"] == "qwen3.7-max"


def test_codex_headless_passes_primary_anthropic_protocol_to_bridge(tmp_path, monkeypatch):
    import mms_launchers

    captured = {}
    runtime = {
        "id": "dual-qwen",
        "api_key": "secret-qwen",
        "openai_api_key": "secret-qwen",
        "openai_base_url": "https://qwen.example/v1",
        "anthropic_base_url": "https://qwen.example/v1",
        "protocols": ["anthropic_messages", "openai_chat_completions"],
        "preferred_transport": "anthropic_messages",
    }

    @contextmanager
    def fake_bridge(gateway_url, api_key, **kwargs):
        captured["gateway_url"] = gateway_url
        captured["api_key"] = api_key
        captured["kwargs"] = kwargs
        yield {"base_url": "http://127.0.0.1:9999", "api_key": "bridge-token"}

    monkeypatch.setattr(mms_launchers, "_ensure_bridge_helpers", lambda: None)
    monkeypatch.setattr(mms_launchers, "gateway_health_check", lambda _runtime: None)
    monkeypatch.setattr(mms_launchers, "_anthropic_base_url", lambda _runtime: _runtime["anthropic_base_url"])
    monkeypatch.setattr(mms_launchers, "_openai_base_url", lambda _runtime: _runtime["openai_base_url"])
    monkeypatch.setattr(mms_launchers, "build_provider_speed_scope", lambda _runtime: {})
    monkeypatch.setattr(mms_launchers, "_probe_models", lambda _runtime, emit_output=False: {"models": ["qwen3.7-max"]})
    monkeypatch.setattr(mms_launchers, "_is_gpt_model", lambda _model: False)
    monkeypatch.setattr(mms_launchers, "_runtime_thinking_enabled", lambda _runtime: False)
    monkeypatch.setattr(mms_launchers, "_runtime_reasoning_effort", lambda _runtime, default="medium": default)
    monkeypatch.setattr(mms_launchers, "_rescue_bridge_kwargs", lambda: {})
    monkeypatch.setattr(mms_launchers, "codex_chatcompletions_bridge", fake_bridge)
    monkeypatch.setattr(mms_launchers, "_codex_provider_base_url", lambda base_url: f"{base_url}/v1")
    monkeypatch.setattr(mms_launchers, "_codex_gateway_env", lambda _runtime, _base_url, model_info=None: {})
    monkeypatch.setattr(mms_launchers, "prepare_cli_command", lambda cmd, env: (cmd, env, "codex"))
    monkeypatch.setattr(
        mms_flywheel.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}),
            stderr="",
        ),
    )

    rc, stdout, stderr = mms_flywheel._run_codex_headless(
        runtime=runtime,
        model="qwen3.7-max",
        prompt="do it",
        cwd=tmp_path,
        sandbox="danger-full-access",
    )

    assert rc == 0
    assert stderr == ""
    assert "agent_message" in stdout
    assert captured["gateway_url"] == "https://qwen.example/v1"
    assert captured["kwargs"]["primary_protocol"] == "anthropic_messages"


def test_run_rejects_committee_profile_for_headless_worker_runner(tmp_path):
    root = tmp_path / "mms-next"
    root.mkdir()

    with pytest.raises(mms_flywheel.FlywheelConfigError, match="codex runtime only"):
        mms_flywheel.run_flywheel_lane(
            lane="committee",
            priority="AI-P0",
            config_root=str(root),
            prompt="review",
        )
