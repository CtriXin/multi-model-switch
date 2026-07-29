from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

import mms_pi_committee
import mms_pi_watchdog


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
        "provider_id": "direct-kimi-test-provider",
        "anthropic_base_url": "https://direct-kimi.example.test",
        "openai_base_url": "",
        "api_key": "sk-kimi-test-secret-123456",
        "model_id": "kimi-for-coding",
    },
    "kimi-k2.7-code": {
        "provider_id": "direct-kimi-test-provider",
        "anthropic_base_url": "https://direct-kimi.example.test",
        "openai_base_url": "",
        "api_key": "sk-kimi-test-secret-123456",
        "model_id": "kimi-k2.7-code",
    },
    "kimi-k2.8-code": {
        "provider_id": "direct-kimi-test-provider",
        "anthropic_base_url": "https://direct-kimi.example.test",
        "openai_base_url": "",
        "api_key": "sk-kimi-test-secret-123456",
        "model_id": "kimi-k2.8-code",
    },
    "k3": {
        "provider_id": "direct-kimi-test-provider",
        "anthropic_base_url": "https://direct-kimi.example.test",
        "openai_base_url": "",
        "api_key": "sk-kimi-test-secret-123456",
        "model_id": "k3",
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


def _write_bundle(
    root: Path,
    *,
    hidden_models: tuple[str, ...] = (),
    bundle_revision: str = "bundle_pi_committee_test",
    generated_at: str = "",
) -> Path:
    generated = root / "generated"
    routes = {model: {"primary": dict(route), "fallbacks": []} for model, route in MODELS.items()}
    for model in ("kimi-for-coding", "kimi-k2.7-code", "kimi-k2.8-code", "k3"):
        if model in routes:
            routes[model] = {
                "primary": dict(MODELS[model]),
                "fallbacks": [
                    {
                        "provider_id": "newapi-tokyo-test-provider",
                        "anthropic_base_url": "https://tokyo-kimi.example.test",
                        "openai_base_url": "",
                        "api_key": "sk-kimi-tokyo-test-secret-123456",
                        "model_id": model,
                    },
                    {
                        "provider_id": "newapi-tokyo-secondary-test-provider",
                        "anthropic_base_url": "https://tokyo-secondary-kimi.example.test",
                        "openai_base_url": "",
                        "api_key": "sk-kimi-tokyo-secondary-test-secret-123456",
                        "model_id": model,
                    },
                    {
                        "provider_id": "newapi-tencent-test-provider",
                        "anthropic_base_url": "https://tencent-kimi.example.test",
                        "openai_base_url": "",
                        "api_key": "sk-kimi-tencent-test-secret-123456",
                        "model_id": model,
                    },
                ],
            }
    # The committee policy fails closed unless every non-GPT member has a Tokyo route.
    for model, route_group in routes.items():
        if model.lower().startswith(("gpt-", "o1", "o3", "o4", "codex-")):
            continue
        route_rows = [route_group["primary"], *route_group.get("fallbacks", [])]
        if any("tokyo" in str(row.get("provider_id") or "").lower() for row in route_rows):
            continue
        primary = dict(route_group["primary"])
        primary["provider_id"] = "newapi-tokyo-test-provider"
        primary["anthropic_base_url"] = "https://tokyo.example.test"
        primary["openai_base_url"] = ""
        primary["api_key"] = "sk-tokyo-test-secret-123456"
        route_group["fallbacks"] = [primary, *route_group.get("fallbacks", [])]
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
    manifest_payload = {
        "schema": "mms.model_registry.latest_approved.v1",
        "bundle_revision": bundle_revision,
        "model_registry_revision": bundle_revision,
        "capability_revision": "cap_pi_committee_test",
        "route_revision": "route_pi_committee_test",
        "policy_revision": "policy_pi_committee_test",
        "profile_revision": "profile_pi_committee_test",
        "files": files,
    }
    if generated_at:
        manifest_payload["generated_at"] = generated_at
    _write_json(manifest, manifest_payload)
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
    assert result["watchdog"]["member_wall_timeout_seconds"] == 900
    assert result["watchdog"]["kimi_attempt_timeout_seconds"] == 300
    assert result["watchdog"]["idle_timeout_seconds"] == 300
    assert result["watchdog"]["committee_timeout_seconds"] == 960
    assert result["watchdog"]["quorum_successes"] == 0
    assert result["plan"]["bundle"]["config_root"] == str(root)
    assert result["plan"]["bundle"]["freshness"]["status"] == "unknown"
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
        "k3",
        "gemini-3-flash-agent(high)",
        "qwen3.7-max",
        "deepseek-v4-flash",
        "glm-5.2",
    ]
    kimi_member = plan["members"][2]
    assert kimi_member["family"] == "Kimi"
    assert [route["provider_id"] for route in kimi_member["route_chain"]] == [
        "newapi-tokyo-test-provider",
        "newapi-tokyo-secondary-test-provider",
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


@pytest.mark.parametrize("generated_at", ["", "2026-05-29T00:14:32Z"])
def test_stale_timestamped_bundle_fails_closed_before_model_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    generated_at: str,
) -> None:
    root = _write_bundle(
        tmp_path / "config",
        bundle_revision="bundle_20260529001432_deadbeef",
        generated_at=generated_at,
    )
    monkeypatch.setattr(
        mms_pi_committee,
        "_utc_now",
        lambda: datetime(2026, 7, 17, 0, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(mms_pi_committee.CommitteeError, match="latest-approved bundle is stale"):
        mms_pi_committee.plan_committee(config_root=root, task="must fail before selecting kimi-k2.6")


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


def test_prepared_attempt_uses_highest_source_backed_thinking_level(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "config")

    _plan, members, _bundle = mms_pi_committee.plan_committee(
        config_root=root,
        task="Inspect",
        count=1,
        explicit_models=["gpt-5.5"],
    )
    gpt_attempt = mms_pi_committee._prepare_members(members, config_root=root)["member-01"][0]

    _plan, members, _bundle = mms_pi_committee.plan_committee(
        config_root=root,
        task="Inspect",
        count=1,
        explicit_models=["k3"],
    )
    k3_attempt = mms_pi_committee._prepare_members(members, config_root=root)["member-01"][0]

    assert gpt_attempt.thinking_level == "xhigh"
    assert k3_attempt.thinking_level == "max"
    assert mms_pi_committee._highest_thinking_level({"models": [{"id": "unknown"}]}, "unknown", "unknown") == ""


def test_worker_launch_is_isolated_read_only_and_emits_transport_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _write_bundle(tmp_path / "config")
    captured: dict = {}
    monkeypatch.setenv("OPENAI_API_KEY", "sk-global-should-not-leak-123456")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-global-should-not-leak-abcdef")
    monkeypatch.setenv("MMS_CONFIG_ROOT", "/sentinel/original-root")

    def fake_run(cmd, *, cwd, env, policy, cancellation):
        captured.update({"cmd": cmd, "cwd": cwd, "env": env, "policy": policy})
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
        return mms_pi_watchdog.ProcessOutcome(
            terminal_reason="completed",
            returncode=0,
            stdout=json.dumps(message) + "\n",
            stderr="",
            elapsed_ms=25,
            stdout_bytes=100,
            stderr_bytes=0,
            peak_repeated_events=1,
            terminated=False,
            forced_kill=False,
        )

    monkeypatch.setattr(mms_pi_committee.mms_pi_watchdog, "run_process", fake_run)
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
    assert "--thinking" not in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--tools") + 1] == "read,grep,find,ls"
    assert captured["policy"].wall_timeout_seconds == 899
    assert captured["policy"].idle_timeout_seconds == 300
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
    assert result["results"][0]["watchdog"]["terminal_reason"] == "completed"
    assert "sk-global-should-not-leak" not in json.dumps(result)


def test_role_card_is_appended_as_private_system_prompt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _write_bundle(tmp_path / "config")
    _plan, members, _bundle = mms_pi_committee.plan_committee(
        config_root=root,
        task="Inspect",
        count=1,
        explicit_models=["k3"],
    )
    member = replace(
        members[0],
        member_id="testing-contract",
        domain="testing",
        role_id="qa",
        role_card="# qa\n\nGATE\n- inspect contract paths",
        role_card_source="agent-spec:roles/qa.min.md",
        role_card_sha256="a" * 64,
        required_domain=True,
    )
    attempt = mms_pi_committee._prepare_members((member,), config_root=root)[member.member_id][0]
    captured = {}

    def fake_run(cmd, *, cwd, env, policy, cancellation):
        captured["cmd"] = cmd
        prompt_path = Path(cmd[cmd.index("--append-system-prompt") + 1])
        captured["role_prompt"] = prompt_path.read_text(encoding="utf-8")
        message = {
            "type": "turn_end",
            "message": {
                "role": "assistant",
                "stopReason": "stop",
                "usage": {},
                "content": [{"type": "text", "text": '{"verdict":"ok","confidence":0.8,"findings":[],"risks":[],"recommendation":"continue","role_payload":{}}'}],
            },
        }
        return mms_pi_watchdog.ProcessOutcome(
            terminal_reason="completed",
            returncode=0,
            stdout=json.dumps(message) + "\n",
            stderr="",
            elapsed_ms=20,
            stdout_bytes=100,
            stderr_bytes=0,
            peak_repeated_events=1,
            terminated=False,
            forced_kill=False,
        )

    monkeypatch.setattr(mms_pi_committee.mms_pi_watchdog, "run_process", fake_run)
    result = mms_pi_committee._run_attempt(
        member,
        attempt,
        task="Inspect contract",
        cwd=tmp_path,
        timeout_seconds=30,
        idle_timeout_seconds=10,
        max_output_bytes=1024,
        max_repeated_events=8,
        cancellation=mms_pi_watchdog.CancellationController(),
    )

    assert "--append-system-prompt" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--thinking") + 1] == "max"
    assert "Canonical role card (qa)" in captured["role_prompt"]
    assert "committee JSON envelope" in captured["role_prompt"]
    assert result["domain"] == "testing"
    assert result["role_id"] == "qa"
    assert result["required_domain"] is True


def test_exhausted_member_budget_skips_fallback_without_counting_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _write_bundle(tmp_path / "config")
    _plan, members, _bundle = mms_pi_committee.plan_committee(
        config_root=root,
        task="Inspect",
        count=1,
        explicit_models=["kimi-for-coding"],
    )
    primary = mms_pi_committee._prepare_members(members, config_root=root)["member-01"][0]
    fallback = mms_pi_committee._prepare_members(members, config_root=root)["member-01"][1]
    clock = [0.0]
    calls: list[str] = []

    monkeypatch.setattr(mms_pi_committee.time, "monotonic", lambda: clock[0])

    def fake_run_attempt(_member, attempt, **_kwargs):
        calls.append(attempt.binding.provider_id)
        clock[0] = 900.1
        return {
            "status": "wall_timeout",
            "terminal_reason": "wall_timeout",
            "watchdog": {"elapsed_ms": 899_082},
        }

    monkeypatch.setattr(mms_pi_committee, "_run_attempt", fake_run_attempt)
    result = mms_pi_committee._run_member(
        members[0],
        (primary, fallback),
        task="Heavy review",
        cwd=tmp_path,
        timeout_seconds=900,
        idle_timeout_seconds=300,
        max_output_bytes=2 * 1024 * 1024,
        max_repeated_events=32,
        cancellation=mms_pi_watchdog.CancellationController(),
        route_source="test",
        kimi_attempt_timeout_seconds=0,
    )

    assert calls == ["newapi-tokyo-test-provider"]
    assert result["terminal_reason"] == "wall_timeout"
    assert result["fallback_used"] is False
    assert result["fallback_skipped_reason"] == "no_budget_remaining"
    assert result["error"] == "newapi-tokyo-test-provider:wall_timeout"
    assert result["attempts"][0]["started"] is True
    assert result["attempts"][0]["budget_seconds"] == 900
    assert result["attempts"][1] == {
        "provider_id": "newapi-tokyo-secondary-test-provider",
        "fallback_position": 1,
        "started": False,
        "budget_seconds": 0,
        "status": "skipped",
        "terminal_reason": "no_budget_remaining",
        "error": "",
        "watchdog": {},
    }


def test_kimi_attempt_cap_preserves_tokyo_fallback_after_tokyo_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _write_bundle(tmp_path / "config")
    _plan, members, _bundle = mms_pi_committee.plan_committee(
        config_root=root,
        task="Inspect",
        count=1,
        explicit_models=["k3"],
    )
    attempts = mms_pi_committee._prepare_members(members, config_root=root)["member-01"][:2]
    clock = [0.0]
    calls: list[tuple[str, int]] = []

    monkeypatch.setattr(mms_pi_committee.time, "monotonic", lambda: clock[0])

    def fake_run_attempt(member, attempt, *, timeout_seconds, **_kwargs):
        calls.append((attempt.binding.provider_id, timeout_seconds))
        if attempt.binding.provider_id == "newapi-tokyo-test-provider":
            clock[0] += timeout_seconds + 0.1
            return {
                "status": "wall_timeout",
                "terminal_reason": "wall_timeout",
                "watchdog": {"elapsed_ms": timeout_seconds * 1000},
            }
        clock[0] += 1
        return {
            **mms_pi_committee._member_identity(member),
            "status": "success",
            "terminal_reason": "completed",
            "watchdog": {"elapsed_ms": 1000},
            "_usage": {},
        }

    monkeypatch.setattr(mms_pi_committee, "_run_attempt", fake_run_attempt)
    result = mms_pi_committee._run_member(
        members[0],
        attempts,
        task="Heavy review",
        cwd=tmp_path,
        timeout_seconds=900,
        idle_timeout_seconds=300,
        max_output_bytes=2 * 1024 * 1024,
        max_repeated_events=32,
        cancellation=mms_pi_watchdog.CancellationController(),
        route_source="test",
        kimi_attempt_timeout_seconds=300,
    )

    assert calls == [
        ("newapi-tokyo-test-provider", 300),
        ("newapi-tokyo-secondary-test-provider", 300),
    ]
    assert result["status"] == "success"
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "newapi-tokyo-test-provider:wall_timeout"
    assert [attempt["budget_seconds"] for attempt in result["attempts"]] == [300, 300]


def test_committee_deadline_cancels_workers_and_preserves_all_member_results(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _write_bundle(tmp_path / "config")

    monkeypatch.setattr(
        mms_pi_committee,
        "_prepare_members",
        lambda members, **_kwargs: {member.member_id: () for member in members},
    )

    def fake_member(member, _attempts, *, cancellation, **_kwargs):
        while not cancellation.is_cancelled():
            time.sleep(0.01)
        return mms_pi_committee._cancelled_member_result(member, cancellation.reason)

    monkeypatch.setattr(mms_pi_committee, "_run_member", fake_member)
    result = mms_pi_committee.run_committee(
        config_root=root,
        task="Bound the whole committee",
        cwd=tmp_path,
        count=3,
        max_concurrency=2,
        committee_timeout_seconds=0.12,
    )

    assert result["status"] == "failed"
    assert result["watchdog"]["committee_stop_reason"] == "committee_timeout"
    assert len(result["results"]) == 3
    assert {item["terminal_reason"] for item in result["results"]} == {"committee_timeout"}


def test_quorum_is_opt_in_and_cancels_only_after_grace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _write_bundle(tmp_path / "config")
    monkeypatch.setattr(
        mms_pi_committee,
        "_prepare_members",
        lambda members, **_kwargs: {member.member_id: () for member in members},
    )

    def fake_member(member, _attempts, *, cancellation, **_kwargs):
        if member.member_id == "member-01":
            return {
                "member_id": member.member_id,
                "model": member.candidate.model,
                "family": member.candidate.family,
                "lens": member.lens,
                "status": "success",
                "terminal_reason": "completed",
                "response": {"raw_text": "enough"},
                "attempts": [],
            }
        while not cancellation.is_cancelled():
            time.sleep(0.01)
        return mms_pi_committee._cancelled_member_result(member, cancellation.reason)

    monkeypatch.setattr(mms_pi_committee, "_run_member", fake_member)
    result = mms_pi_committee.run_committee(
        config_root=root,
        task="Use explicit quorum",
        cwd=tmp_path,
        count=3,
        max_concurrency=3,
        quorum_successes=1,
        quorum_grace_seconds=0.05,
    )

    assert result["status"] == "partial"
    assert result["watchdog"]["committee_stop_reason"] == "quorum_reached"
    assert result["summary"] == {"members": 3, "succeeded": 1, "failed": 2}


def test_openai_chat_route_records_audited_fallback_reason() -> None:
    protocol, _base_url, reason = mms_pi_committee._select_protocol(
        "glm-test",
        anthropic_url="",
        openai_url="https://glm.example.test/v1",
    )

    assert protocol == "openai_chat_completions"
    assert reason


def test_url_redaction_removes_userinfo_query_and_fragment() -> None:
    value = "https://user:secret@example.test/v1/messages?api_key=hidden#fragment"

    assert mms_pi_committee._redact_url(value) == "https://example.test/v1/messages"


def test_pi_blocked_tokyo_route_fails_closed_without_tencent_fallback() -> None:
    route_group = {
        "primary": {
            "provider_id": "newapi-tencent",
            "anthropic_base_url": "https://primary.example.test",
            "api_key": "sk-primary-test-secret-123456",
            "model_id": "gemini-3.1-pro-low",
        },
        "fallbacks": [
            {
                "provider_id": "newapi-personal-tokyo",
                "anthropic_base_url": "https://blocked.example.test",
                "api_key": "sk-blocked-test-secret-123456",
                "model_id": "gemini-3.1-pro-low",
            }
        ],
    }

    with pytest.raises(mms_pi_committee.CommitteeError, match="Pi route is blocked"):
        mms_pi_committee._build_route_chain("gemini-3.1-pro-low", route_group, {})


def test_non_gpt_without_tokyo_route_is_excluded(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "config")
    router_path = root / "generated" / "model-routes.json"
    router = json.loads(router_path.read_text(encoding="utf-8"))
    router["routes"]["glm-test"]["fallbacks"] = []
    router["routes"]["glm-test"]["primary"]["provider_id"] = "newapi-tencent-test-provider"
    _write_json(router_path, router)
    manifest_path = root / "generated" / "model-registry.latest-approved.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["router"]["sha256"] = _sha256(router_path)
    _write_json(manifest_path, manifest)

    with pytest.raises(mms_pi_committee.CommitteeError, match="requested models are unavailable"):
        mms_pi_committee.plan_committee(
            config_root=root,
            task="Tokyo is required",
            count=1,
            explicit_models=["glm-test"],
        )


def test_frontier_requires_pinned_gpt_5_5(tmp_path: Path) -> None:
    root = _write_bundle(tmp_path / "config", hidden_models=("gpt-5.5",))

    with pytest.raises(mms_pi_committee.CommitteeError, match="frontier GPT model is unavailable: gpt-5.5"):
        mms_pi_committee.plan_committee(config_root=root, task="GPT must be pinned")


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
