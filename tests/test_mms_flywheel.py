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


def _seed_flywheel_tier_routes(root):
    router = {
        "version": 1,
        "routes": {
            "qwen3.7-max": {
                "primary": {
                    "provider_id": "direct-qwen",
                    "model_id": "qwen3.7-max",
                    "anthropic_base_url": "https://qwen.example/v1",
                    "openai_base_url": "https://qwen.example/v1",
                    "api_key": "secret-qwen",
                    "max_context_tokens": 1000000,
                },
                "fallbacks": [
                    {
                        "provider_id": "newapi-personal-tokyo",
                        "model_id": "qwen3.7-max",
                        "anthropic_base_url": "https://tokyo.example/v1",
                        "openai_base_url": "https://tokyo.example/v1",
                        "api_key": "secret-tokyo",
                    },
                    {
                        "provider_id": "newapi-tencent",
                        "model_id": "qwen3.7-max",
                        "anthropic_base_url": "https://tencent.example/v1",
                        "openai_base_url": "https://tencent.example/v1",
                        "api_key": "secret-tencent",
                    },
                ],
            },
            "glm-5.2": {
                "primary": {
                    "provider_id": "direct-zai",
                    "model_id": "glm-5.2",
                    "anthropic_base_url": "https://glm.example/v1",
                    "openai_base_url": "https://glm.example/v1",
                    "api_key": "secret-glm",
                },
                "fallbacks": [
                    {
                        "provider_id": "newapi-personal-tokyo",
                        "model_id": "glm-5.2",
                        "anthropic_base_url": "https://tokyo.example/v1",
                        "openai_base_url": "https://tokyo.example/v1",
                        "api_key": "secret-tokyo",
                    },
                    {
                        "provider_id": "newapi-tencent",
                        "model_id": "glm-5.2",
                        "anthropic_base_url": "https://tencent.example/v1",
                        "openai_base_url": "https://tencent.example/v1",
                        "api_key": "secret-tencent",
                    },
                ],
            },
            "MiniMax-M3": {
                "primary": {
                    "provider_id": "direct-minimax",
                    "model_id": "MiniMax-M3",
                    "anthropic_base_url": "https://minimax.example/anthropic",
                    "openai_base_url": "https://minimax.example/v1",
                    "api_key": "secret-minimax",
                    "max_context_tokens": 1000000,
                },
                "fallbacks": [
                    {
                        "provider_id": "newapi-personal-tokyo",
                        "model_id": "MiniMax-M3",
                        "anthropic_base_url": "https://tokyo.example/v1",
                        "openai_base_url": "https://tokyo.example/v1",
                        "api_key": "secret-tokyo",
                    },
                    {
                        "provider_id": "newapi-tencent",
                        "model_id": "MiniMax-M3",
                        "anthropic_base_url": "https://tencent.example/v1",
                        "openai_base_url": "https://tencent.example/v1",
                        "api_key": "secret-tencent",
                    },
                ],
            },
            "gpt-5.5": {
                "primary": {
                    "provider_id": "uscrsopenai",
                    "model_id": "gpt-5.5",
                    "openai_base_url": "https://openai.example/v1",
                    "api_key": "secret-openai",
                },
                "fallbacks": [
                    {
                        "provider_id": "us-cpa-local-codex",
                        "model_id": "gpt-5.5",
                        "openai_base_url": "https://cpa.example/v1",
                        "anthropic_base_url": "https://cpa-anthropic.example/v1",
                        "api_key": "secret-cpa",
                    },
                    {
                        "provider_id": "newapi-company",
                        "model_id": "gpt-5.5",
                        "openai_base_url": "https://company.example/v1",
                        "anthropic_base_url": "https://company-anthropic.example/v1",
                        "api_key": "secret-company",
                    },
                    {
                        "provider_id": "newapi-tencent",
                        "model_id": "gpt-5.5",
                        "openai_base_url": "https://tencent.example/v1",
                        "api_key": "secret-tencent",
                    },
                ],
            },
        },
    }
    lineup = {"version": 1, "routes": router["routes"]}
    _write_json(root / "model-routes.json", router)
    _write_json(root / "model-routes.lineup.json", lineup)
    (root / "config.toml").write_text(
        """
[[providers]]
id = "newapi-personal-tokyo"
enabled = true
api_key = "secret-tokyo"
openai_base_url = "https://tokyo.example/v1"
anthropic_base_url = "https://tokyo.example/v1"
protocols = ["anthropic_messages", "openai_chat_completions"]
fallback_models = ["gpt-5.5", "qwen3.7-max", "glm-5.2", "MiniMax-M3"]
supported_clis = ["codex"]
""".strip(),
        encoding="utf-8",
    )


def _write_qwen_worker_config(root: Path, *, effort: str = "high", runtime: str = "claude"):
    (root / "config.toml").write_text(
        """
[flywheel.lanes.worker]
"AI-P3" = "flywheel.worker.p3"

[flywheel.profiles."flywheel.worker.p3"]
runtime = "{runtime}"
model = "qwen3.7-max"
provider = "direct-qwen"
reasoning_effort = "{effort}"
thinking_mode = "enable"
""".strip().format(effort=effort, runtime=runtime),
        encoding="utf-8",
    )


def test_default_worker_and_fixer_tiers_use_domestic_models_and_ordered_fallbacks(tmp_path):
    root = tmp_path / "mms-next"
    root.mkdir()
    _seed_flywheel_tier_routes(root)

    worker_p3 = mms_flywheel.resolve_flywheel_profile(lane="worker", priority="AI-P3", config_root=str(root))
    worker_p4 = mms_flywheel.resolve_flywheel_profile(lane="worker", priority="AI-P4", config_root=str(root))
    fixer_p4 = mms_flywheel.resolve_flywheel_profile(lane="fixer", priority="AI-P4", config_root=str(root))
    worker_p2 = mms_flywheel.resolve_flywheel_profile(lane="worker", priority="AI-P2", config_root=str(root))
    worker_p0 = mms_flywheel.resolve_flywheel_profile(lane="worker", priority="AI-P0", config_root=str(root))

    assert worker_p3["profile_id"] == "flywheel.worker.cn-qwen"
    assert worker_p3["runtime_kind"] == "claude"
    assert worker_p3["model"] == "qwen3.7-max"
    assert worker_p3["provider_id"] == "direct-qwen"
    assert worker_p4["runtime_kind"] == "claude"
    assert worker_p4["profile_id"] == "flywheel.worker.cn-minimax"
    assert worker_p4["model"] == "MiniMax-M3"
    assert worker_p4["provider_id"] == "direct-minimax"
    assert fixer_p4["profile_id"] == "flywheel.fixer.cn-minimax"
    assert fixer_p4["runtime_kind"] == "claude"
    assert fixer_p4["model"] == "MiniMax-M3"
    assert worker_p2["profile_id"] == "flywheel.worker.cn-glm"
    assert worker_p2["runtime_kind"] == "claude"
    assert worker_p2["model"] == "glm-5.2"
    assert worker_p0["runtime_kind"] == "codex"
    assert [item["provider_id"] for item in worker_p3["fallback_routes"]] == [
        "newapi-personal-tokyo",
        "newapi-tencent",
        "us-cpa-local-codex",
        "newapi-company",
    ]
    assert [item["provider_id"] for item in worker_p0["fallback_routes"]] == [
        "newapi-personal-tokyo",
        "newapi-tencent",
        "us-cpa-local-codex",
        "newapi-company",
    ]
    assert [item["model_id"] for item in worker_p3["fallback_routes"]] == [
        "qwen3.7-max",
        "qwen3.7-max",
        "gpt-5.5",
        "gpt-5.5",
    ]
    assert worker_p3["fallback_routes"][2]["allow_model_switch"] is True
    serialized = json.dumps(worker_p3, ensure_ascii=False)
    assert "secret-" not in serialized
    assert "https://" not in serialized


def test_flywheel_runtime_passes_ordered_native_fallback_routes_without_artifact_leak(tmp_path, monkeypatch):
    root = tmp_path / "mms-next"
    workdir = tmp_path / "work"
    artifact_dir = tmp_path / "artifacts"
    root.mkdir()
    workdir.mkdir()
    _seed_flywheel_tier_routes(root)
    captured = {}

    def fake_run_claude_headless(*, runtime, model, prompt, cwd, sandbox):
        captured["runtime"] = runtime
        captured["model"] = model
        return (0, "agent text", "")

    monkeypatch.setattr(mms_flywheel, "_run_claude_headless", fake_run_claude_headless)

    result = mms_flywheel.run_flywheel_lane(
        lane="worker",
        priority="AI-P3",
        config_root=str(root),
        cwd=str(workdir),
        artifact_dir=str(artifact_dir),
        runner_args=["exec", "ship it"],
    )

    assert result["ok"] is True
    assert result["runtime_kind"] == "claude"
    assert captured["model"] == "qwen3.7-max"
    assert [item["provider_id"] for item in captured["runtime"]["native_fallback_routes"]] == [
        "newapi-personal-tokyo",
        "newapi-tencent",
        "us-cpa-local-codex",
        "newapi-company",
    ]
    assert [item["model"] for item in captured["runtime"]["native_fallback_routes"]] == [
        "qwen3.7-max",
        "qwen3.7-max",
        "gpt-5.5",
        "gpt-5.5",
    ]
    assert captured["runtime"]["native_fallback_routes"][2]["gateway_url"] == "https://cpa.example/v1"
    assert captured["runtime"]["native_fallback_routes"][3]["gateway_url"] == "https://company.example/v1"
    assert captured["runtime"]["native_fallback_routes"][2]["allow_model_switch"] is True
    artifact = json.loads(Path(result["resolved_route_path"]).read_text(encoding="utf-8"))
    serialized = json.dumps(artifact, ensure_ascii=False)
    assert "secret-" not in serialized
    assert "gateway_key" not in serialized
    assert "native_fallback_routes" not in serialized


def test_flywheel_run_preserves_explicit_config_for_native_fallback_routes(tmp_path, monkeypatch):
    root = tmp_path / "mms-next"
    workdir = tmp_path / "work"
    artifact_dir = tmp_path / "artifacts"
    root.mkdir()
    workdir.mkdir()
    _seed_flywheel_tier_routes(root)
    explicit_config = tmp_path / "custom-flywheel.toml"
    explicit_config.write_text(
        """
[lanes.worker]
"AI-P3" = "flywheel.worker.custom"

[profiles."flywheel.worker.custom"]
runtime = "claude"
model = "qwen3.7-max"
provider = "direct-qwen"
fallback_providers = ["us-cpa-local-codex"]

[profiles."flywheel.worker.custom".fallback_model_by_provider]
us-cpa-local-codex = "gpt-5.5"
""".strip(),
        encoding="utf-8",
    )
    captured = {}

    def fake_run_claude_headless(*, runtime, model, prompt, cwd, sandbox):
        captured["runtime"] = runtime
        captured["model"] = model
        return (0, "agent text", "")

    monkeypatch.setattr(mms_flywheel, "_run_claude_headless", fake_run_claude_headless)

    result = mms_flywheel.run_flywheel_lane(
        lane="worker",
        priority="AI-P3",
        config_root=str(root),
        config_path=str(explicit_config),
        cwd=str(workdir),
        artifact_dir=str(artifact_dir),
        runner_args=["exec", "ship it"],
    )

    assert result["ok"] is True
    assert result["runtime_kind"] == "claude"
    assert captured["model"] == "qwen3.7-max"
    assert [item["provider_id"] for item in captured["runtime"]["native_fallback_routes"]] == [
        "us-cpa-local-codex",
    ]
    assert captured["runtime"]["native_fallback_routes"][0]["model"] == "gpt-5.5"
    artifact = json.loads(Path(result["resolved_route_path"]).read_text(encoding="utf-8"))
    assert artifact["resolved"]["profile_id"] == "flywheel.worker.custom"
    assert artifact["resolved"]["config"]["config_path"] == str(explicit_config.resolve())
    assert "native_fallback_routes" not in json.dumps(artifact, ensure_ascii=False)


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


@pytest.mark.parametrize("model_name", ["minimax-m3", "kimi-for-coding", "step-fun3.7"])
def test_resolve_claude_runtime_accepts_future_domestic_model_name_alias(tmp_path, model_name):
    root = tmp_path / "mms-next"
    root.mkdir()
    _write_json(
        root / "model-routes.json",
        {
            "version": 1,
            "routes": {
                model_name: {
                    "primary": {
                        "provider_id": "direct-cn",
                        "model_id": model_name,
                        "anthropic_base_url": "https://cn.example/v1",
                        "openai_base_url": "https://cn.example/v1",
                        "api_key": "secret-cn",
                    }
                }
            },
        },
    )
    _write_json(
        root / "model-routes.lineup.json",
        {
            "version": 1,
            "routes": {
                model_name: {
                    "primary": {
                        "provider_id": "direct-cn",
                        "model_id": model_name,
                        "reasoning_effort": "high",
                        "thinking_mode": "disable",
                        "max_context_tokens": 600000,
                    }
                }
            },
        },
    )
    (root / "flywheel.toml").write_text(
        f"""
[lanes.worker]
"AI-P4" = "flywheel.worker.future-cn"

[profiles."flywheel.worker.future-cn"]
runtime_kind = "claude"
model_name = "{model_name}"
provider = "direct-cn"
""".strip(),
        encoding="utf-8",
    )

    resolved = mms_flywheel.resolve_flywheel_profile(lane="worker", priority="AI-P4", config_root=str(root))

    assert resolved["runtime_kind"] == "claude"
    assert resolved["model"] == model_name
    assert resolved["provider_id"] == "direct-cn"
    assert resolved["thinking_mode"] == "disable"
    assert resolved["reasoning_effort"] == "high"
    assert resolved["max_context_tokens"] == 600000


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
    assert result["command_preview"]["cli"] == "claude"
    assert payload["runtime"]["reasoning_effort"] == "xhigh"
    assert payload["runtime"]["thinking_mode"] == "enable"
    assert payload["runtime"]["max_context_tokens"] == 1000000
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
runtime = "claude"
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
    _seed_flywheel_tier_routes(root)
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


def test_run_invokes_claude_runner_with_raw_runtime_but_json_output_is_safe(tmp_path, monkeypatch, capsys):
    root = tmp_path / "mms-next"
    workdir = tmp_path / "work"
    root.mkdir()
    workdir.mkdir()
    _seed_flywheel_tier_routes(root)
    _write_qwen_worker_config(root)
    captured = {}

    def fake_run_claude_headless(*, runtime, model, prompt, cwd, sandbox):
        captured["runtime"] = runtime
        captured["model"] = model
        captured["prompt"] = prompt
        captured["cwd"] = cwd
        captured["sandbox"] = sandbox
        return (0, "agent text", "")

    monkeypatch.setattr(mms_flywheel, "_run_claude_headless", fake_run_claude_headless)

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
    assert payload["result"]["runtime_kind"] == "claude"
    assert payload["result"]["agent_text"] == "agent text"
    assert captured["runtime"]["api_key"] == "secret-qwen"
    assert captured["runtime"]["openai_base_url"] == "https://qwen.example/v1"
    assert captured["runtime"]["anthropic_base_url"] == "https://qwen.example/v1"
    assert captured["runtime"]["thinking_mode"] == "enable"
    assert captured["runtime"]["reasoning_effort"] == "high"
    assert captured["runtime"]["max_context_tokens"] == 1000000
    assert captured["model"] == "qwen3.7-max"
    assert captured["prompt"] == "fix this"
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "secret-qwen" not in serialized
    assert "https://qwen.example" not in serialized


def test_run_invokes_claude_runner_with_anthropic_transport_for_dual_protocol_route(tmp_path, monkeypatch):
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
runtime = "claude"
model = "qwen3.7-max"
provider = "dual-qwen"
""".strip(),
        encoding="utf-8",
    )
    captured = {}

    def fake_run_claude_headless(*, runtime, model, prompt, cwd, sandbox):
        captured["runtime"] = runtime
        captured["model"] = model
        return (0, "agent text", "")

    monkeypatch.setattr(mms_flywheel, "_run_claude_headless", fake_run_claude_headless)

    result = mms_flywheel.run_flywheel_lane(
        lane="worker",
        priority="AI-P3",
        config_root=str(root),
        cwd=str(workdir),
        runner_args=["exec", "fix this"],
    )

    assert result["ok"] is True
    assert result["runtime_kind"] == "claude"
    assert captured["runtime"]["preferred_transport"] == "anthropic_messages"
    assert captured["runtime"]["transport_request_path"] == "/v1/messages"
    assert captured["runtime"]["cache_transport_evidence"]["protocol"] == "anthropic_messages"
    assert captured["runtime"]["api_key"] == "secret-qwen"
    assert captured["model"] == "qwen3.7-max"


def test_run_uses_legacy_secret_route_when_generated_route_is_sanitized(tmp_path, monkeypatch):
    root = tmp_path / "mms-next"
    workdir = tmp_path / "work"
    root.mkdir()
    workdir.mkdir()
    _seed_flywheel_tier_routes(root)
    _write_qwen_worker_config(root)
    generated = root / "generated"
    generated.mkdir()
    routes_payload = json.loads((root / "model-routes.json").read_text(encoding="utf-8"))
    generated_primary = routes_payload["routes"]["qwen3.7-max"]["primary"]
    generated_primary["api_key"] = ""
    _write_json(generated / "model-routes.json", routes_payload)
    _write_json(generated / "model-routes.lineup.json", json.loads((root / "model-routes.lineup.json").read_text(encoding="utf-8")))
    captured = {}

    def fake_run_claude_headless(*, runtime, model, prompt, cwd, sandbox):
        captured["runtime"] = runtime
        captured["model"] = model
        return (0, "agent text", "")

    monkeypatch.setattr(mms_flywheel, "_run_claude_headless", fake_run_claude_headless)

    result = mms_flywheel.run_flywheel_lane(
        lane="worker",
        priority="AI-P3",
        config_root=str(root),
        cwd=str(workdir),
        runner_args=["exec", "fix this"],
    )

    assert result["ok"] is True
    assert captured["runtime"]["api_key"] == "secret-qwen"
    artifact = json.loads(Path(result["resolved_route_path"]).read_text(encoding="utf-8"))
    assert artifact["resolved"]["config"]["route_path"].endswith("generated/model-routes.json")
    serialized = json.dumps(artifact, ensure_ascii=False)
    assert "secret-qwen" not in serialized


def test_run_invokes_codex_runner_for_gpt_worker(tmp_path, monkeypatch):
    root = tmp_path / "mms-next"
    workdir = tmp_path / "work"
    root.mkdir()
    workdir.mkdir()
    _seed_flywheel_tier_routes(root)
    captured = {}

    def fake_run_codex_headless(*, runtime, model, prompt, cwd, sandbox):
        captured["runtime"] = runtime
        captured["model"] = model
        captured["prompt"] = prompt
        return (
            0,
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "codex text"}}),
            "",
        )

    monkeypatch.setattr(mms_flywheel, "_run_codex_headless", fake_run_codex_headless)

    result = mms_flywheel.run_flywheel_lane(
        lane="worker",
        priority="AI-P0",
        config_root=str(root),
        cwd=str(workdir),
        runner_args=["exec", "fix this"],
    )

    assert result["ok"] is True
    assert result["runtime_kind"] == "codex"
    assert result["agent_text"] == "codex text"
    assert captured["model"] == "gpt-5.5"
    assert captured["runtime"]["preferred_transport"] == "openai_responses"
    assert captured["prompt"] == "fix this"


def test_claude_headless_uses_bridge_with_thinking_effort_and_context(tmp_path, monkeypatch):
    import mms_launchers

    captured = {}
    runtime = {
        "id": "direct-qwen",
        "api_key": "secret-qwen",
        "openai_api_key": "secret-qwen",
        "openai_base_url": "https://qwen.example/v1",
        "anthropic_base_url": "https://qwen.example/v1",
        "protocols": ["anthropic_messages", "openai_chat_completions"],
        "preferred_transport": "anthropic_messages",
        "thinking_mode": "disable",
        "reasoning_effort": "xhigh",
        "max_context_tokens": 777000,
        "native_fallback_routes": [
            {"provider_id": "newapi-personal-tokyo", "gateway_url": "https://tokyo.example/v1", "gateway_key": "secret-tokyo"}
        ],
    }

    @contextmanager
    def fake_bridge(gateway_url, api_key, **kwargs):
        captured["bridge_gateway_url"] = gateway_url
        captured["bridge_api_key"] = api_key
        captured["bridge_kwargs"] = kwargs
        yield {"base_url": "http://127.0.0.1:9999", "api_key": "bridge-token"}

    def fake_claude_env(_runtime, **kwargs):
        captured["env_kwargs"] = kwargs
        return {"HOME": str(tmp_path / "home"), "ANTHROPIC_MODEL": "claude-sonnet-4-6"}

    def fake_prepare_cli_command(cmd, env):
        captured["cmd"] = cmd
        captured["env"] = env
        return cmd, env, "claude"

    def fake_subprocess_run(cmd, **kwargs):
        captured["run_cmd"] = cmd
        captured["run_kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="claude text", stderr="")

    monkeypatch.setattr(mms_launchers, "_ensure_bridge_helpers", lambda: None)
    monkeypatch.setattr(mms_launchers, "_ensure_speed_stats", lambda: None)
    monkeypatch.setattr(mms_launchers, "gateway_health_check", lambda _runtime: None)
    monkeypatch.setattr(mms_launchers, "_probe_models", lambda _runtime, emit_output=False: {"models": ["qwen3.7-max"]})
    monkeypatch.setattr(mms_launchers, "build_provider_speed_scope", lambda _runtime: {"provider": "direct-qwen"})
    monkeypatch.setattr(mms_launchers, "_is_claude_family_model_name", lambda _model: False)
    monkeypatch.setattr(mms_launchers, "_resolve_anthropic_base_url", lambda _runtime, probe_model="": ("https://qwen.example", "normalized"))
    monkeypatch.setattr(mms_launchers, "_anthropic_base_url", lambda _runtime: _runtime["anthropic_base_url"])
    monkeypatch.setattr(mms_launchers, "_openai_base_url", lambda _runtime: _runtime["openai_base_url"])
    monkeypatch.setattr(mms_launchers, "_runtime_thinking_enabled", lambda _runtime: False)
    monkeypatch.setattr(mms_launchers, "_runtime_reasoning_effort", lambda _runtime, default="high": _runtime["reasoning_effort"])
    monkeypatch.setattr(mms_launchers, "_runtime_supports_claude_1m", lambda _runtime: False)
    monkeypatch.setattr(mms_launchers, "_runtime_model_capabilities", lambda _runtime, _model: {})
    monkeypatch.setattr(mms_launchers, "_runtime_vision_sidecar", lambda _runtime: {})
    monkeypatch.setattr(mms_launchers, "_model_capabilities_support_vision", lambda _capabilities, _model: False)
    monkeypatch.setattr(mms_launchers, "_context_windows_for_models", lambda *_models, **_kwargs: {"qwen3.7-max": 777000})
    monkeypatch.setattr(mms_launchers, "_claude_route_status_paths", lambda: [str(tmp_path / "route-status.json")])
    monkeypatch.setattr(mms_launchers, "_runtime_is_sensitive_claude_provider", lambda _runtime: False)
    monkeypatch.setattr(mms_launchers, "_rescue_bridge_kwargs", lambda: {})
    monkeypatch.setattr(mms_launchers, "_gateway_claude_bridge_context", fake_bridge)
    monkeypatch.setattr(mms_launchers, "_claude_gateway_env", fake_claude_env)
    monkeypatch.setattr(mms_launchers, "_claude_code_effort_env_value", lambda _model, _runtime: "max")
    monkeypatch.setattr(mms_launchers, "_apply_claude_shell_context_slots", lambda env, **kwargs: captured.setdefault("context_kwargs", kwargs))
    monkeypatch.setattr(mms_launchers, "_resolve_real_home_command_path", lambda _name, _env: "claude")
    monkeypatch.setattr(mms_launchers, "prepare_cli_command", fake_prepare_cli_command)
    monkeypatch.setattr(mms_flywheel.subprocess, "run", fake_subprocess_run)

    rc, stdout, stderr = mms_flywheel._run_claude_headless(
        runtime=runtime,
        model="qwen3.7-max",
        prompt="do it",
        cwd=tmp_path,
        sandbox="danger-full-access",
    )

    assert rc == 0
    assert stdout == "claude text"
    assert stderr == ""
    assert captured["bridge_gateway_url"] == "https://qwen.example/v1"
    assert captured["bridge_api_key"] == "secret-qwen"
    assert captured["bridge_kwargs"]["heavy_model"] == "qwen3.7-max"
    assert captured["bridge_kwargs"]["reasoning_enabled"] is False
    assert captured["bridge_kwargs"]["reasoning_effort"] == "xhigh"
    assert captured["bridge_kwargs"]["native_fallback_routes"] == runtime["native_fallback_routes"]
    assert captured["env_kwargs"]["selected_model"] == "claude-sonnet-4-6"
    assert captured["env_kwargs"]["display_model"] == "qwen3.7-max"
    assert captured["env"]["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == "777000"
    assert captured["env"]["CLAUDE_CODE_EFFORT_LEVEL"] == "max"
    assert captured["context_kwargs"]["context_window"] == 777000
    assert captured["run_kwargs"]["cwd"] == str(tmp_path)
    assert "--dangerously-skip-permissions" in captured["cmd"]
    assert captured["cmd"][-2:] == ["-p", "do it"]


def test_codex_headless_initializes_lazy_speed_stats(tmp_path, monkeypatch):
    import mms_launchers

    captured = {}
    runtime = {
        "id": "direct-qwen",
        "api_key": "secret-qwen",
        "openai_api_key": "secret-qwen",
        "openai_base_url": "https://qwen.example/v1",
        "protocols": ["openai_chat_completions"],
        "preferred_transport": "openai_chat_completions",
    }

    @contextmanager
    def fake_bridge(gateway_url, api_key, **kwargs):
        captured["speed_scope"] = kwargs.get("speed_scope")
        yield {"base_url": "http://127.0.0.1:9999", "api_key": "bridge-token"}

    def fake_ensure_speed_stats():
        mms_launchers.build_provider_speed_scope = lambda _runtime: {"provider": "direct-qwen"}

    monkeypatch.setattr(mms_launchers, "_ensure_bridge_helpers", lambda: None)
    monkeypatch.setattr(mms_launchers, "build_provider_speed_scope", None)
    monkeypatch.setattr(mms_launchers, "_ensure_speed_stats", fake_ensure_speed_stats)
    monkeypatch.setattr(mms_launchers, "gateway_health_check", lambda _runtime: None)
    monkeypatch.setattr(mms_launchers, "_openai_base_url", lambda _runtime: _runtime["openai_base_url"])
    monkeypatch.setattr(mms_launchers, "_probe_models", lambda _runtime, emit_output=False: {"models": ["qwen3.7-max"]})
    monkeypatch.setattr(mms_launchers, "_is_gpt_model", lambda _model: False)
    monkeypatch.setattr(mms_launchers, "_runtime_thinking_enabled", lambda _runtime: False)
    monkeypatch.setattr(mms_launchers, "_runtime_reasoning_effort", lambda _runtime, default="medium": default)
    monkeypatch.setattr(mms_launchers, "_rescue_bridge_kwargs", lambda: {})
    monkeypatch.setattr(mms_launchers, "codex_chatcompletions_bridge", fake_bridge)
    monkeypatch.setattr(mms_launchers, "_codex_provider_base_url", lambda base_url: f"{base_url}/v1")
    monkeypatch.setattr(mms_launchers, "_codex_gateway_env", lambda _runtime, _base_url, model_info=None: {})

    def fake_prepare_cli_command(cmd, env):
        captured["cmd"] = cmd
        return cmd, env, "codex"

    monkeypatch.setattr(mms_launchers, "prepare_cli_command", fake_prepare_cli_command)
    monkeypatch.setattr(
        mms_flywheel.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}),
            stderr="",
        ),
    )

    rc, _stdout, stderr = mms_flywheel._run_codex_headless(
        runtime=runtime,
        model="qwen3.7-max",
        prompt="do it",
        cwd=tmp_path,
        sandbox="danger-full-access",
    )

    assert rc == 0
    assert stderr == ""
    assert captured["speed_scope"] == {"provider": "direct-qwen"}
    assert "--ignore-user-config" in captured["cmd"]
    assert 'model_providers.custom.name="custom"' in captured["cmd"]
    assert 'model_providers.custom.wire_api="responses"' in captured["cmd"]
    assert "model_providers.custom.requires_openai_auth=true" in captured["cmd"]


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
        "native_fallback_routes": [
            {"provider_id": "newapi-personal-tokyo", "gateway_url": "https://tokyo.example/v1", "gateway_key": "secret-tokyo"}
        ],
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
    assert captured["kwargs"]["native_fallback_routes"] == runtime["native_fallback_routes"]


def test_run_rejects_committee_profile_for_headless_worker_runner(tmp_path):
    root = tmp_path / "mms-next"
    root.mkdir()

    with pytest.raises(mms_flywheel.FlywheelConfigError, match="codex/claude runtime only"):
        mms_flywheel.run_flywheel_lane(
            lane="committee",
            priority="AI-P0",
            config_root=str(root),
            prompt="review",
        )


def test_run_rejects_non_gpt_codex_runtime(tmp_path):
    root = tmp_path / "mms-next"
    workdir = tmp_path / "work"
    root.mkdir()
    workdir.mkdir()
    _seed_routes(root)
    _write_qwen_worker_config(root, runtime="codex")

    with pytest.raises(mms_flywheel.FlywheelConfigError, match="GPT/OpenAI-family"):
        mms_flywheel.run_flywheel_lane(
            lane="worker",
            priority="AI-P3",
            config_root=str(root),
            cwd=str(workdir),
            prompt="do it",
        )
