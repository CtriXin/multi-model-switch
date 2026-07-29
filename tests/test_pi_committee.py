from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import mms_pi_committee


ROOT = Path(__file__).resolve().parents[1]


MODELS = {
    "MiniMax-M3": {
        "provider_id": "minimax-test-provider",
        "anthropic_base_url": "https://minimax.example.test",
        "openai_base_url": "",
        "api_key": "sk-minimax-test-secret-123456",
        "model_id": "MiniMax-M3",
    },
    "MiniMax-M2.7": {
        "provider_id": "minimax-test-provider",
        "anthropic_base_url": "https://minimax.example.test",
        "openai_base_url": "",
        "api_key": "sk-minimax-test-secret-123456",
        "model_id": "MiniMax-M2.7",
    },
    "gpt-5.5": {
        "provider_id": "gpt-frontier-test-provider",
        "anthropic_base_url": "",
        "openai_base_url": "https://gpt.example.test/v1",
        "api_key": "sk-gpt-frontier-test-secret-123456",
        "model_id": "gpt-5.5",
    },
    "gpt-5.4": {
        "provider_id": "gpt-frontier-test-provider",
        "anthropic_base_url": "",
        "openai_base_url": "https://gpt.example.test/v1",
        "api_key": "sk-gpt-frontier-test-secret-123456",
        "model_id": "gpt-5.4",
    },
    "kimi-for-coding": {
        "provider_id": "kimi-test-provider",
        "anthropic_base_url": "https://kimi.example.test",
        "openai_base_url": "",
        "api_key": "sk-kimi-test-secret-123456",
        "model_id": "kimi-for-coding",
    },
    "kimi-k2.7-code": {
        "provider_id": "kimi-test-provider",
        "anthropic_base_url": "https://kimi.example.test",
        "openai_base_url": "",
        "api_key": "sk-kimi-test-secret-123456",
        "model_id": "kimi-k2.7-code",
    },
    "gemini-3-flash-agent(high)": {
        "provider_id": "gemini-test-provider",
        "anthropic_base_url": "https://gemini.example.test",
        "openai_base_url": "",
        "api_key": "sk-gemini-test-secret-123456",
        "model_id": "gemini-3-flash-agent(high)",
    },
    "gemini-3.1-pro-low": {
        "provider_id": "gemini-test-provider",
        "anthropic_base_url": "https://gemini.example.test",
        "openai_base_url": "",
        "api_key": "sk-gemini-test-secret-123456",
        "model_id": "gemini-3.1-pro-low",
    },
    "qwen3.7-max": {
        "provider_id": "qwen-frontier-test-provider",
        "anthropic_base_url": "https://qwen-frontier.example.test",
        "openai_base_url": "",
        "api_key": "sk-qwen-frontier-test-secret-123456",
        "model_id": "qwen3.7-max",
    },
    "qwen3.7-plus": {
        "provider_id": "qwen-frontier-test-provider",
        "anthropic_base_url": "https://qwen-frontier.example.test",
        "openai_base_url": "",
        "api_key": "sk-qwen-frontier-test-secret-123456",
        "model_id": "qwen3.7-plus",
    },
    "deepseek-v4-flash": {
        "provider_id": "deepseek-test-provider",
        "anthropic_base_url": "https://deepseek.example.test",
        "openai_base_url": "",
        "api_key": "sk-deepseek-test-secret-123456",
        "model_id": "deepseek-v4-flash",
    },
    "deepseek-v4-pro": {
        "provider_id": "deepseek-test-provider",
        "anthropic_base_url": "https://deepseek.example.test",
        "openai_base_url": "",
        "api_key": "sk-deepseek-test-secret-123456",
        "model_id": "deepseek-v4-pro",
    },
    "glm-5.2": {
        "provider_id": "glm-frontier-test-provider",
        "anthropic_base_url": "https://glm-frontier.example.test",
        "openai_base_url": "",
        "api_key": "sk-glm-frontier-test-secret-123456",
        "model_id": "glm-5.2",
    },
    "glm-5.1": {
        "provider_id": "glm-frontier-test-provider",
        "anthropic_base_url": "https://glm-frontier.example.test",
        "openai_base_url": "",
        "api_key": "sk-glm-frontier-test-secret-123456",
        "model_id": "glm-5.1",
    },
    "mimo-v2.5": {
        "provider_id": "mimo-test-provider",
        "anthropic_base_url": "https://mimo.example.test",
        "openai_base_url": "",
        "api_key": "sk-mimo-test-secret-123456",
        "model_id": "mimo-v2.5",
    },
    "claude-sonnet-test": {
        "provider_id": "claude-test-provider",
        "anthropic_base_url": "https://claude.example.test",
        "openai_base_url": "",
        "api_key": "sk-claude-test-secret-123456",
        "model_id": "claude-sonnet-wire",
    },
    "gpt-test": {
        "provider_id": "gpt-test-provider",
        "anthropic_base_url": "",
        "openai_base_url": "https://openai.example.test/v1",
        "api_key": "sk-gpt-test-secret-123456",
        "model_id": "gpt-test-wire",
    },
    "glm-test": {
        "provider_id": "glm-test-provider",
        "anthropic_base_url": "",
        "openai_base_url": "https://glm.example.test/v1",
        "api_key": "sk-glm-test-secret-123456",
        "model_id": "glm-test-wire",
    },
    "qwen-test": {
        "provider_id": "qwen-test-provider",
        "anthropic_base_url": "https://qwen.example.test/anthropic",
        "openai_base_url": "https://qwen.example.test/v1",
        "api_key": "sk-qwen-test-secret-123456",
        "model_id": "qwen-test-wire",
    },
}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_bundle(root: Path, *, hidden_models: tuple[str, ...] = ()) -> Path:
    generated = root / "generated"
    routes = {model: {"primary": dict(route), "fallbacks": []} for model, route in MODELS.items()}
    lineup_routes = {
        model: {"primary": {"provider_id": row["provider_id"], "model_id": row["model_id"], "max_context_tokens": 200_000}}
        for model, row in MODELS.items()
    }
    policy_models = {
        model: {
            "visible": model not in hidden_models,
            "favorite": model == "qwen-test",
            "tier": "primary" if model == "qwen-test" else "secondary",
            "capabilities": {"text": True, "reasoning": True, "tool_use": True},
        }
        for model in MODELS
    }
    approved_models = [
        {
            "alias": model,
            "model": model,
            "official_context_window_tokens": 200_000,
            "supports_thinking": True,
        }
        for model in MODELS
    ]
    payloads = {
        "router": ("model-routes.json", {"version": 1, "routes": routes}, "secret"),
        "lineup": ("model-routes.lineup.json", {"version": 1, "routes": lineup_routes}, "non-secret"),
        "profile": (
            "provider-profiles.generated.json",
            {"version": 1, "profiles": {row["provider_id"]: {} for row in MODELS.values()}},
            "non-secret",
        ),
        "policy": ("model-policy.effective.json", {"version": 1, "models": policy_models}, "non-secret"),
        "capabilities": (
            "model-capabilities.approved.json",
            {"version": 1, "models": approved_models},
            "non-secret",
        ),
    }
    files = {}
    for name, (filename, payload, sensitivity) in payloads.items():
        path = generated / filename
        _write_json(path, payload)
        files[name] = {
            "canonical_path": f"generated/{filename}",
            "legacy_alias_path": "",
            "sha256": _sha256(path),
            "sensitivity": sensitivity,
        }
    manifest = generated / "model-registry.latest-approved.json"
    _write_json(
        manifest,
        {
            "schema": "mms.model_registry.latest_approved.v1",
            "bundle_revision": "bundle_pi_committee_test",
            "model_registry_revision": "bundle_pi_committee_test",
            "capability_revision": "cap_pi_committee_test",
            "route_revision": "route_pi_committee_test",
            "policy_revision": "policy_pi_committee_test",
            "profile_revision": "profile_pi_committee_test",
            "files": files,
        },
    )
    return root


def test_dry_run_selects_frontier_members_without_secrets(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "config")
    result = mms_pi_committee.run_committee(
        config_root=root,
        task="Inspect the runtime design",
        cwd=tmp_path,
        count=4,
        min_families=3,
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    assert result["plan"]["selection"]["profile"] == "frontier"
    members = result["plan"]["members"]
    assert [member["member_id"] for member in members] == ["member-01", "member-02", "member-03", "member-04"]
    assert len({member["family"] for member in members}) >= 3
    assert all(member["context_window_tokens"] == 200_000 for member in members)
    assert result["plan"]["isolation"] == {
        "global_config_writes": False,
        "global_oauth_fallback": False,
        "opencode_dependency": False,
        "worker_tools": "read,grep,find,ls",
    }
    rendered = json.dumps(result)
    assert "sk-claude-test-secret" not in rendered
    assert "sk-qwen-test-secret" not in rendered


def test_default_frontier_reproduces_current_seven_family_roster(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "config")

    plan, _members, _bundle = mms_pi_committee.plan_committee(
        config_root=root,
        task="Select current family champions",
    )

    assert [item["model"] for item in plan["members"]] == [
        "MiniMax-M3",
        "gpt-5.5",
        "kimi-for-coding",
        "gemini-3-flash-agent(high)",
        "qwen3.7-max",
        "deepseek-v4-flash",
        "glm-5.2",
    ]
    assert plan["selection"]["target_families"] == list(mms_pi_committee.DEFAULT_FRONTIER_FAMILIES)
    assert plan["selection"]["requested_count"] == 7


def test_frontier_can_add_temporary_family_and_model_without_named_agents(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "config")

    plan, _members, _bundle = mms_pi_committee.plan_committee(
        config_root=root,
        task="Expand this mission",
        frontier_families=(*mms_pi_committee.DEFAULT_FRONTIER_FAMILIES, "Claude"),
        additional_models=("qwen3.7-plus",),
    )

    assert [item["member_id"] for item in plan["members"]] == [f"member-{index:02d}" for index in range(1, 10)]
    assert plan["members"][-2]["model"] == "claude-sonnet-test"
    assert plan["members"][-1]["model"] == "qwen3.7-plus"


def test_balanced_profile_preserves_generic_diversity_mode(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "config")

    plan, _members, _bundle = mms_pi_committee.plan_committee(
        config_root=root,
        task="Use generic diversity",
        selection_profile="balanced",
        count=4,
        min_families=3,
    )

    assert plan["selection"]["profile"] == "balanced"
    assert plan["selection"]["target_families"] == []
    assert len({item["family"] for item in plan["members"]}) >= 3


def test_explicit_models_bind_to_generic_members_in_requested_order(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "config")
    plan, _members, _bundle = mms_pi_committee.plan_committee(
        config_root=root,
        task="Compare two models",
        count=2,
        explicit_models=["glm-test", "claude-sonnet-test"],
    )

    assert [(item["member_id"], item["model"]) for item in plan["members"]] == [
        ("member-01", "glm-test"),
        ("member-02", "claude-sonnet-test"),
    ]


def test_invalid_bundle_hash_fails_closed(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "config")
    policy = root / "generated" / "model-policy.effective.json"
    policy.write_text("{}\n", encoding="utf-8")

    with pytest.raises(mms_pi_committee.CommitteeError, match="hash mismatch"):
        mms_pi_committee.plan_committee(config_root=root, task="must fail")


def test_policy_hidden_model_is_not_selectable(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "config", hidden_models=("glm-test",))

    with pytest.raises(mms_pi_committee.CommitteeError, match="requested models are unavailable"):
        mms_pi_committee.plan_committee(
            config_root=root,
            task="must fail",
            count=1,
            explicit_models=["glm-test"],
        )


def test_prepared_pi_payload_uses_env_reference_and_wire_model(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "config")
    _plan, members, _bundle = mms_pi_committee.plan_committee(
        config_root=root,
        task="Inspect",
        count=1,
        explicit_models=["claude-sonnet-test"],
    )
    prepared = mms_pi_committee._prepare_members(members, config_root=root)
    attempt = prepared["member-01"][0]
    provider = attempt.models_payload["providers"][attempt.provider_ref]

    assert provider["apiKey"] == "$MMS_PI_COMMITTEE_KEY_MEMBER_01_0"
    assert attempt.selected_model == "claude-sonnet-wire"
    assert provider["models"][0]["id"] == "claude-sonnet-wire"
    assert MODELS["claude-sonnet-test"]["api_key"] not in json.dumps(attempt.models_payload)


def test_worker_launch_is_isolated_read_only_and_emits_transport_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _write_bundle(tmp_path / "config")
    captured: dict = {}
    monkeypatch.setenv("OPENAI_API_KEY", "sk-global-should-not-leak-123456")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-global-should-not-leak-abcdef")
    monkeypatch.setenv("MMS_CONFIG_ROOT", "/sentinel/original-root")

    def fake_run(cmd, *, cwd, env, capture_output, text, timeout, check):
        captured.update({"cmd": cmd, "cwd": cwd, "env": env, "timeout": timeout})
        models = json.loads((Path(env["PI_CODING_AGENT_DIR"]) / "models.json").read_text(encoding="utf-8"))
        provider = next(iter(models["providers"].values()))
        captured["api_key_ref"] = provider["apiKey"]
        message = {
            "type": "turn_end",
            "message": {
                "role": "assistant",
                "stopReason": "stop",
                "usage": {"input": 11, "output": 7, "cacheRead": 3},
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "verdict": "isolated",
                                "confidence": 0.9,
                                "findings": [],
                                "risks": [],
                                "recommendation": "keep the boundary",
                            }
                        ),
                    }
                ],
            },
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(message) + "\n", stderr="")

    monkeypatch.setattr(mms_pi_committee.subprocess, "run", fake_run)
    result = mms_pi_committee.run_committee(
        config_root=root,
        task="Inspect isolation",
        cwd=tmp_path,
        count=1,
        explicit_models=["claude-sonnet-test"],
        max_concurrency=1,
    )

    assert result["status"] == "success"
    assert "--no-session" in captured["cmd"]
    assert "--no-context-files" in captured["cmd"]
    assert "--no-extensions" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--tools") + 1] == "read,grep,find,ls"
    assert captured["api_key_ref"] == "$MMS_PI_COMMITTEE_KEY_MEMBER_01_0"
    assert "OPENAI_API_KEY" not in captured["env"]
    assert "ANTHROPIC_API_KEY" not in captured["env"]
    assert "MMS_CONFIG_ROOT" not in captured["env"]
    assert os.environ["MMS_CONFIG_ROOT"] == "/sentinel/original-root"
    assert captured["env"]["HOME"] != str(Path.home())
    evidence = result["results"][0]["cache_transport_evidence"]
    assert evidence["schema"] == "cache_transport_evidence.v1"
    assert evidence["protocol"] == "anthropic_messages"
    assert evidence["request_path"] == "/v1/messages"
    assert evidence["usage"]["cache_read_input_tokens"] == 3
    assert "sk-global-should-not-leak" not in json.dumps(result)


def test_openai_chat_route_records_audited_fallback_reason(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "config")
    plan, _members, _bundle = mms_pi_committee.plan_committee(
        config_root=root,
        task="Inspect transport",
        count=1,
        explicit_models=["glm-test"],
    )

    route = plan["members"][0]["route_chain"][0]
    assert route["protocol"] == "openai_chat_completions"
    assert route["protocol_fallback_reason"]


def test_url_redaction_removes_userinfo_query_and_fragment() -> None:
    value = "https://user:secret@example.test/v1/messages?api_key=hidden#fragment"

    assert mms_pi_committee._redact_url(value) == "https://example.test/v1/messages"


def test_pi_blocked_fallback_route_is_removed_from_member_chain() -> None:
    route_group = {
        "primary": {
            "provider_id": "newapi-tencent",
            "anthropic_base_url": "https://primary.example.test",
            "api_key": "sk-primary-test-secret-123456",
            "model_id": "gemini-3-flash-agent(high)",
        },
        "fallbacks": [
            {
                "provider_id": "newapi-personal-tokyo",
                "anthropic_base_url": "https://blocked.example.test",
                "api_key": "sk-blocked-test-secret-123456",
                "model_id": "gemini-3-flash-agent(high)",
            }
        ],
    }

    chain = mms_pi_committee._build_route_chain("gemini-3-flash-agent(high)", route_group, {})

    assert [binding.provider_id for binding in chain] == ["newapi-tencent"]


def test_cli_dry_run_is_json_only_and_does_not_launch_pi(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "config")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "pi_committee.py"),
            "--config-root",
            str(root),
            "--task",
            "CLI dry run",
            "--cwd",
            str(tmp_path),
            "--count",
            "2",
            "--dry-run",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "dry_run"
    assert [item["member_id"] for item in payload["plan"]["members"]] == ["member-01", "member-02"]
