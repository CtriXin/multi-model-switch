from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _write_latest_approved_router_manifest(config_root: Path, *, router_payload: dict, sha_override: str = "") -> None:
    generated = config_root / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    router_path = generated / "model-routes.json"
    router_bytes = json.dumps(router_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    router_path.write_bytes(router_bytes)
    manifest = {
        "schema": "mms.model_registry.latest_approved.v1",
        "bundle_revision": "bundle_review_test",
        "files": {
            "router": {
                "canonical_path": "generated/model-routes.json",
                "sha256": sha_override or hashlib.sha256(router_bytes).hexdigest(),
                "sensitivity": "secret",
            }
        },
    }
    (generated / "model-registry.latest-approved.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def test_review_launch_help_is_real_subcommand(capsys):
    from mms_review_launch import handle_review_launch_command

    with pytest.raises(SystemExit) as exc:
        handle_review_launch_command(["--help"], command_name="mms")

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "review-launch" in out
    assert "multi-review" in out
    assert "reviewer" in out


def test_review_launch_contract_json_has_required_env(capsys):
    from mms_review_launch import handle_review_launch_command

    assert handle_review_launch_command(["--contract-json"], command_name="mms") == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "mms.review_launch_contract.v1"
    assert payload["model_dispatch_implemented"] is True
    assert payload["review_file_write_implemented"] is True
    assert "MOEBIUS_REVIEWER_ID" in payload["required_env"]
    assert "MOEBIUS_REVIEW_EXPECTED_OUTPUT" in payload["required_env"]


def _write_review_launch_fixture(tmp_path: Path, reviewer_id: str = "kimi-for-coding") -> dict[str, str]:
    repo_root = tmp_path / "repo"
    run_dir = tmp_path / "runs" / "p53"
    gate_path = run_dir / "review-dispatch-gate.json"
    prompt_path = repo_root / ".ai" / "plan" / "p53-prompt.md"
    pack_path = repo_root / ".ai" / "plan" / "review-packs" / "p53.json"
    expected_output = repo_root / ".ai" / "reviews" / reviewer_id / "p53-review-20260506.md"
    changed_file = repo_root / "mms_review_launch.py"
    repo_root.mkdir()
    run_dir.mkdir(parents=True)
    gate_path.write_text(json.dumps({"gate_status": "approved"}) + "\n", encoding="utf-8")
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("# P53 Prompt\n\nReview the MMS launch writer.\n", encoding="utf-8")
    changed_file.write_text("print('changed')\n", encoding="utf-8")
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(
        json.dumps(
            {
                "schema": "multi_review.pack.v1",
                "milestone": "p53",
                "commit": "abc123",
                "title": "P53",
                "prompt_path": ".ai/plan/p53-prompt.md",
                "changed_files": ["mms_review_launch.py"],
                "read_only_files": [],
                "paths": {"pack_md": ".ai/plan/review-packs/p53.md"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "MOEBIUS_RUN_ID": "p53",
        "MOEBIUS_RUN_DIR": str(run_dir),
        "MOEBIUS_REPO_ROOT": str(repo_root),
        "MOEBIUS_REVIEW_DISPATCH_ADAPTER_CONFIG": str(run_dir / "adapter.json"),
        "MOEBIUS_REVIEW_DISPATCH_GATE": str(gate_path),
        "MOEBIUS_REVIEW_DISPATCH_PLAN": str(run_dir / "plan.json"),
        "MOEBIUS_REVIEWER_ID": reviewer_id,
        "MOEBIUS_REVIEW_EXPECTED_OUTPUT": str(expected_output),
        "MULTI_REVIEW_REVIEWER": reviewer_id,
        "MOEBIUS_REVIEW_PACK": str(pack_path),
    }


def test_review_launch_validate_env_accepts_moebius_contract(tmp_path, monkeypatch, capsys):
    from mms_review_launch import handle_review_launch_command

    repo_root = tmp_path / "repo"
    run_dir = tmp_path / "runs" / "p50"
    gate_path = run_dir / "review-dispatch-gate.json"
    expected_output = repo_root / ".ai" / "reviews" / "gemini-cli" / "p50-review-20260506.md"
    repo_root.mkdir()
    run_dir.mkdir(parents=True)
    gate_path.write_text(json.dumps({"gate_status": "approved"}) + "\n", encoding="utf-8")
    pack_path = repo_root / ".ai" / "plan" / "review-packs" / "p50.json"
    pack_path.parent.mkdir(parents=True)
    pack_path.write_text(json.dumps({"schema": "multi_review.pack.v1", "milestone": "p50"}) + "\n", encoding="utf-8")

    env = {
        "MOEBIUS_RUN_ID": "p50",
        "MOEBIUS_RUN_DIR": str(run_dir),
        "MOEBIUS_REPO_ROOT": str(repo_root),
        "MOEBIUS_REVIEW_DISPATCH_ADAPTER_CONFIG": str(run_dir / "adapter.json"),
        "MOEBIUS_REVIEW_DISPATCH_GATE": str(gate_path),
        "MOEBIUS_REVIEW_DISPATCH_PLAN": str(run_dir / "plan.json"),
        "MOEBIUS_REVIEWER_ID": "gemini-cli",
        "MOEBIUS_REVIEW_EXPECTED_OUTPUT": str(expected_output),
        "MULTI_REVIEW_REVIEWER": "gemini-cli",
        "MOEBIUS_REVIEW_PACK": str(pack_path),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    assert handle_review_launch_command(["--validate-env"], command_name="mms") == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "mms.review_launch_validation.v1"
    assert payload["ok"] is True
    assert payload["reviewer_id"] == "gemini-cli"
    assert payload["model_calls"] == 0
    assert payload["review_file_writes"] == 0
    assert payload["warnings"]


def test_review_launch_validate_env_rejects_wrapper_only_id(tmp_path, monkeypatch, capsys):
    from mms_review_launch import handle_review_launch_command

    repo_root = tmp_path / "repo"
    run_dir = tmp_path / "runs" / "p50"
    gate_path = run_dir / "review-dispatch-gate.json"
    expected_output = repo_root / ".ai" / "reviews" / "codex" / "p50-review-20260506.md"
    repo_root.mkdir()
    run_dir.mkdir(parents=True)
    gate_path.write_text(json.dumps({"gate_status": "approved"}) + "\n", encoding="utf-8")

    env = {
        "MOEBIUS_RUN_ID": "p50",
        "MOEBIUS_RUN_DIR": str(run_dir),
        "MOEBIUS_REPO_ROOT": str(repo_root),
        "MOEBIUS_REVIEW_DISPATCH_ADAPTER_CONFIG": str(run_dir / "adapter.json"),
        "MOEBIUS_REVIEW_DISPATCH_GATE": str(gate_path),
        "MOEBIUS_REVIEW_DISPATCH_PLAN": str(run_dir / "plan.json"),
        "MOEBIUS_REVIEWER_ID": "codex",
        "MOEBIUS_REVIEW_EXPECTED_OUTPUT": str(expected_output),
        "MULTI_REVIEW_REVIEWER": "codex",
        "MOEBIUS_REVIEW_PACK": str(repo_root / ".ai" / "plan" / "review-packs" / "p50.json"),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    assert handle_review_launch_command(["--validate-env"], command_name="mms") == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert any("wrapper/tool id" in item for item in payload["errors"])


def test_review_launch_fake_dispatch_writes_exact_expected_review_file(tmp_path, monkeypatch, capsys):
    from mms_review_launch import handle_review_launch_command

    env = _write_review_launch_fixture(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv(
        "MMS_REVIEW_LAUNCH_FAKE_RESPONSE",
        "Reviewer: kimi-for-coding\n\nVerdict: PASS\n\nNo blockers found.\n",
    )

    assert handle_review_launch_command([], command_name="mms") == 0
    payload = json.loads(capsys.readouterr().out)
    expected_output = Path(env["MOEBIUS_REVIEW_EXPECTED_OUTPUT"])

    assert payload["schema"] == "mms.review_launch_result.v1"
    assert payload["ok"] is True
    assert payload["status"] == "review_written"
    assert payload["fake_dispatch"] is True
    assert payload["model_calls"] == 1
    assert payload["review_file_writes"] == 1
    assert payload["review_intake_run"] is False
    assert expected_output.exists()
    assert "Reviewer: kimi-for-coding" in expected_output.read_text(encoding="utf-8")
    review_files = sorted((Path(env["MOEBIUS_REPO_ROOT"]) / ".ai" / "reviews").rglob("*.md"))
    assert review_files == [expected_output]


@pytest.mark.parametrize("reviewer_id", ["kimi-for-coding", "minimax-m2.7", "qwen3.5-plus", "glm-5-turbo", "gpt-5.4"])
def test_review_launch_high_context_reviewers_get_larger_output_budget(
    tmp_path,
    monkeypatch,
    capsys,
    reviewer_id,
):
    import mms_review_launch
    from mms_review_launch import (
        ANTHROPIC_MESSAGES_PROTOCOL,
        HIGH_CONTEXT_REVIEW_MAX_TOKENS,
        HIGH_CONTEXT_REVIEW_READ_TIMEOUT_SECONDS,
        handle_review_launch_command,
    )

    env = _write_review_launch_fixture(tmp_path, reviewer_id=reviewer_id)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    provider = {"id": "newapi-personal-tokyo", "protocols": [ANTHROPIC_MESSAGES_PROTOCOL]}
    monkeypatch.setattr(
        mms_review_launch,
        "_resolve_review_launch_candidates",
        lambda _model, _env: (
            [{"provider": provider, "protocol": ANTHROPIC_MESSAGES_PROTOCOL, "model_name": reviewer_id}],
            "",
        ),
    )
    captured = {}

    async def fake_call_model(*, provider, protocol, model_name, prompt, max_tokens, read_timeout_seconds=180):
        captured["max_tokens"] = max_tokens
        captured["read_timeout_seconds"] = read_timeout_seconds
        return "Verdict: PASS\n\nNo blockers found.\n"

    monkeypatch.setattr(mms_review_launch, "_call_model", fake_call_model)

    assert handle_review_launch_command([], command_name="mms") == 0
    payload = json.loads(capsys.readouterr().out)

    assert captured["max_tokens"] == HIGH_CONTEXT_REVIEW_MAX_TOKENS
    assert captured["read_timeout_seconds"] == HIGH_CONTEXT_REVIEW_READ_TIMEOUT_SECONDS
    assert payload["dispatch_trace"]["max_tokens"] == HIGH_CONTEXT_REVIEW_MAX_TOKENS
    assert Path(env["MOEBIUS_REVIEW_EXPECTED_OUTPUT"]).exists()


def test_review_launch_max_tokens_env_override_still_wins_for_high_context_reviewer(
    tmp_path,
    monkeypatch,
    capsys,
):
    import mms_review_launch
    from mms_review_launch import ANTHROPIC_MESSAGES_PROTOCOL, MAX_TOKENS_ENV, handle_review_launch_command

    env = _write_review_launch_fixture(tmp_path, reviewer_id="kimi-for-coding")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv(MAX_TOKENS_ENV, "8192")

    provider = {"id": "newapi-personal-tokyo", "protocols": [ANTHROPIC_MESSAGES_PROTOCOL]}
    monkeypatch.setattr(
        mms_review_launch,
        "_resolve_review_launch_candidates",
        lambda _model, _env: (
            [{"provider": provider, "protocol": ANTHROPIC_MESSAGES_PROTOCOL, "model_name": "kimi-for-coding"}],
            "",
        ),
    )
    captured = {}

    async def fake_call_model(*, provider, protocol, model_name, prompt, max_tokens, read_timeout_seconds=180):
        captured["max_tokens"] = max_tokens
        return "Verdict: PASS\n\nNo blockers found.\n"

    monkeypatch.setattr(mms_review_launch, "_call_model", fake_call_model)

    assert handle_review_launch_command([], command_name="mms") == 0
    payload = json.loads(capsys.readouterr().out)

    assert captured["max_tokens"] == 8192
    assert payload["dispatch_trace"]["max_tokens"] == 8192


def test_review_launch_uses_route_context_window_for_large_review_context(
    tmp_path,
    monkeypatch,
    capsys,
):
    import mms_review_launch
    from mms_review_launch import ANTHROPIC_MESSAGES_PROTOCOL, handle_review_launch_command

    env = _write_review_launch_fixture(tmp_path, reviewer_id="kimi-for-coding")
    repo_root = Path(env["MOEBIUS_REPO_ROOT"])
    large_file = repo_root / "large-context.txt"
    large_file.write_text(("x" * 520_000) + "ROUTE_CONTEXT_TAIL\n", encoding="utf-8")
    pack_path = Path(env["MOEBIUS_REVIEW_PACK"])
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["changed_files"] = ["large-context.txt"]
    pack_path.write_text(json.dumps(pack) + "\n", encoding="utf-8")
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    provider = {"id": "newapi-personal-tokyo", "protocols": [ANTHROPIC_MESSAGES_PROTOCOL]}
    monkeypatch.setattr(
        mms_review_launch,
        "_resolve_review_launch_candidates",
        lambda _model, _env: (
            [{"provider": provider, "protocol": ANTHROPIC_MESSAGES_PROTOCOL, "model_name": "kimi-for-coding"}],
            "",
        ),
    )
    monkeypatch.setattr(mms_review_launch, "_route_context_window_tokens", lambda _model, _candidate: 262_144)
    captured = {}

    async def fake_call_model(*, provider, protocol, model_name, prompt, max_tokens, read_timeout_seconds=180):
        captured["prompt"] = prompt
        return "Verdict: PASS\n\nNo blockers found.\n"

    monkeypatch.setattr(mms_review_launch, "_call_model", fake_call_model)

    assert handle_review_launch_command([], command_name="mms") == 0
    payload = json.loads(capsys.readouterr().out)

    assert "ROUTE_CONTEXT_TAIL" in captured["prompt"]
    assert payload["dispatch_trace"]["context_window_tokens"] == 262_144
    assert payload["dispatch_trace"]["prompt_context_char_budget"] > 500_000


def test_review_launch_requires_explicit_allowed_read_root_for_external_context(tmp_path):
    from mms_review_launch import ALLOWED_READ_ROOTS_ENV, _render_file_context

    repo_root = tmp_path / "repo"
    external_root = tmp_path / "external"
    external_file = external_root / "pilot" / "scripts" / "pilot_ant_export.py"
    repo_file = repo_root / "AGENTS.md"
    repo_root.mkdir()
    external_file.parent.mkdir(parents=True)
    external_file.write_text("external context\n", encoding="utf-8")
    repo_file.write_text("repo context\n", encoding="utf-8")
    pack = {"read_only_files": ["AGENTS.md", str(external_file)]}

    text, entries = _render_file_context(repo_root, pack, {})

    assert "repo context" in text
    assert "external context" not in text
    assert entries[0]["read"] is True
    assert entries[1]["error"] == "path_outside_allowed_read_roots"

    text, entries = _render_file_context(repo_root, pack, {ALLOWED_READ_ROOTS_ENV: str(external_root)})

    assert "repo context" in text
    assert "external context" in text
    assert entries[1]["read"] is True


def test_review_launch_high_context_reviewer_reads_larger_file_context_by_default(tmp_path):
    from mms_review_launch import _render_file_context

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    large_file = repo_root / "large.txt"
    large_file.write_text(("x" * 13000) + "HIGH_CONTEXT_TAIL\n", encoding="utf-8")
    pack = {"changed_files": ["large.txt"]}

    default_text, default_entries = _render_file_context(repo_root, pack, {})
    high_context_text, high_context_entries = _render_file_context(
        repo_root,
        pack,
        {"MOEBIUS_REVIEWER_ID": "kimi-for-coding"},
    )

    assert "HIGH_CONTEXT_TAIL" not in default_text
    assert default_entries[0]["truncated"] is True
    assert "HIGH_CONTEXT_TAIL" in high_context_text
    assert high_context_entries[0]["truncated"] is False


def test_review_launch_resolves_anthropic_only_provider(monkeypatch):
    import mms_core
    from mms_review_launch import ANTHROPIC_MESSAGES_PROTOCOL, _resolve_provider_for_model

    provider = {
        "id": "mimo-direct-anthropic",
        "protocols": [ANTHROPIC_MESSAGES_PROTOCOL],
        "anthropic_base_url": "https://token-plan-cn.xiaomimimo.com/anthropic",
        "api_key": "key",
    }
    monkeypatch.setattr(mms_core, "load_config", lambda: {"provider": {"default": "default"}, "providers": []})
    monkeypatch.setattr(mms_core, "apply_local_overrides", lambda cfg: cfg)
    monkeypatch.setattr(mms_core, "_default_config", lambda: {})
    monkeypatch.setattr(mms_core, "resolve_provider_context", lambda cfg, provider_id: provider)
    monkeypatch.setattr(mms_core, "_load_probe_file_cache", lambda _provider_id, allow_stale=False: {"raw_models": ["mimo-v2.5"]})
    monkeypatch.setattr(mms_core, "_provider_candidates", lambda cfg, default_provider, default_models: [(provider, ["mimo-v2.5"])])
    monkeypatch.setattr(mms_core, "_provider_effective_models", lambda _provider, cached, _cfg=None: list(cached or []))

    resolved, protocol, error = _resolve_provider_for_model("mimo-v2.5", {})

    assert error == ""
    assert resolved["id"] == "mimo-direct-anthropic"
    assert protocol == ANTHROPIC_MESSAGES_PROTOCOL


def test_review_launch_uses_default_provider_cache_and_canonical_model_case(monkeypatch):
    import mms_core
    from mms_review_launch import ANTHROPIC_MESSAGES_PROTOCOL, _resolve_review_launch_candidates

    default_provider = {
        "id": "newapi-personal-tokyo",
        "enabled": True,
        "role": "auto",
        "priority": 120,
        "protocols": ["anthropic_messages", "openai_chat_completions"],
        "anthropic_base_url": "https://tokyo.example.com",
        "openai_base_url": "https://tokyo.example.com",
        "api_key": "key",
    }
    fallback_provider = {
        "id": "xin",
        "enabled": True,
        "role": "fallback",
        "priority": 90,
        "protocols": ["anthropic_messages"],
        "anthropic_base_url": "https://xin.example.com",
        "api_key": "key",
    }
    cfg = {"provider": {"default": "newapi-personal-tokyo"}, "providers": [default_provider, fallback_provider]}

    monkeypatch.setattr(mms_core, "load_config", lambda: cfg)
    monkeypatch.setattr(mms_core, "apply_local_overrides", lambda loaded: loaded)
    monkeypatch.setattr(mms_core, "_default_config", lambda: {})
    monkeypatch.setattr(
        mms_core,
        "resolve_provider_context",
        lambda loaded, provider_id: default_provider if provider_id == "newapi-personal-tokyo" else fallback_provider,
    )
    monkeypatch.setattr(
        mms_core,
        "_load_probe_file_cache",
        lambda provider_id, allow_stale=False: {
            "raw_models": ["MiniMax-M2.7"] if provider_id == "newapi-personal-tokyo" else ["minimax-m2.7"]
        },
    )
    monkeypatch.setattr(
        mms_core,
        "_provider_candidates",
        lambda loaded, default, default_models: [(default, default_models), (fallback_provider, ["minimax-m2.7"])],
    )
    monkeypatch.setattr(mms_core, "_provider_effective_models", lambda _provider, cached, _cfg=None: list(cached or []))

    candidates, error = _resolve_review_launch_candidates("minimax-m2.7", {})

    assert error == ""
    assert candidates[0]["provider"]["id"] == "newapi-personal-tokyo"
    assert candidates[0]["protocol"] == ANTHROPIC_MESSAGES_PROTOCOL
    assert candidates[0]["model_name"] == "MiniMax-M2.7"


def test_review_launch_uses_verified_latest_approved_router_with_explicit_root(tmp_path):
    from mms_review_launch import ANTHROPIC_MESSAGES_PROTOCOL, _resolve_review_launch_candidates

    config_root = tmp_path / "mms-next"
    _write_latest_approved_router_manifest(
        config_root,
        router_payload={
            "version": 1,
            "routes": {
                "review-model": {
                    "primary": {
                        "provider_id": "verified-review-provider",
                        "anthropic_base_url": "https://verified.example",
                        "api_key": "sk-test-verified",
                        "model_id": "Review-Model",
                    },
                    "fallbacks": [],
                }
            },
        },
    )

    candidates, error = _resolve_review_launch_candidates(
        "review-model",
        {"MMS_CONFIG_ROOT": str(config_root)},
    )

    assert error == ""
    assert len(candidates) == 1
    assert candidates[0]["provider"]["id"] == "verified-review-provider"
    assert candidates[0]["provider"]["route_source"] == "mms:latest-approved:bundle_review_test"
    assert candidates[0]["protocol"] == ANTHROPIC_MESSAGES_PROTOCOL
    assert candidates[0]["model_name"] == "Review-Model"


def test_review_launch_latest_approved_router_fails_closed_on_invalid_manifest(monkeypatch, tmp_path):
    import mms_core
    from mms_review_launch import _resolve_review_launch_candidates

    config_root = tmp_path / "mms-next"
    _write_latest_approved_router_manifest(
        config_root,
        router_payload={
            "version": 1,
            "routes": {
                "review-model": {
                    "primary": {
                        "provider_id": "untrusted-review-provider",
                        "anthropic_base_url": "https://untrusted.example",
                        "api_key": "sk-test-untrusted",
                        "model_id": "review-model",
                    },
                    "fallbacks": [],
                }
            },
        },
        sha_override="0" * 64,
    )
    monkeypatch.setattr(mms_core, "load_config", lambda: {"provider": {"default": "legacy"}, "providers": []})

    candidates, error = _resolve_review_launch_candidates(
        "review-model",
        {"MMS_CONFIG_ROOT": str(config_root)},
    )

    assert candidates == []
    assert "latest-approved bundle invalid" in error


def test_review_launch_latest_approved_router_fails_closed_on_missing_manifest(monkeypatch, tmp_path):
    import mms_core
    from mms_review_launch import _resolve_review_launch_candidates

    config_root = tmp_path / "mms-next"
    legacy_provider = {
        "id": "legacy-review-provider",
        "enabled": True,
        "role": "auto",
        "priority": 120,
        "protocols": ["anthropic_messages"],
        "anthropic_base_url": "https://legacy.example",
        "api_key": "legacy-key",
    }
    cfg = {"provider": {"default": "legacy-review-provider"}, "providers": [legacy_provider]}

    monkeypatch.setattr(mms_core, "load_config", lambda: cfg)
    monkeypatch.setattr(mms_core, "apply_local_overrides", lambda loaded: loaded)
    monkeypatch.setattr(mms_core, "_default_config", lambda: {})
    monkeypatch.setattr(
        mms_core,
        "resolve_provider_context",
        lambda _loaded, _provider_id: legacy_provider,
    )
    monkeypatch.setattr(
        mms_core,
        "_load_probe_file_cache",
        lambda _provider_id, allow_stale=False: {"raw_models": ["review-model"]},
    )
    monkeypatch.setattr(
        mms_core,
        "_provider_candidates",
        lambda _loaded, default, default_models: [(default, default_models)],
    )
    monkeypatch.setattr(mms_core, "_provider_effective_models", lambda _provider, cached, _cfg=None: list(cached or []))

    candidates, error = _resolve_review_launch_candidates(
        "review-model",
        {"MMS_CONFIG_ROOT": str(config_root)},
    )

    assert candidates == []
    assert "latest-approved bundle missing" in error
    assert str(config_root / "generated" / "model-registry.latest-approved.json") in error


def test_review_launch_gpt_auto_uses_openai_chat_on_dual_provider(monkeypatch):
    import mms_core
    from mms_review_launch import OPENAI_CHAT_PROTOCOL, _resolve_review_launch_candidates

    provider = {
        "id": "companycrsopenai",
        "enabled": True,
        "role": "auto",
        "priority": 120,
        "protocols": ["anthropic_messages", "openai_chat_completions"],
        "anthropic_base_url": "https://gateway.example.com/openai",
        "openai_base_url": "https://gateway.example.com/openai/v1",
        "api_key": "key",
    }
    cfg = {"provider": {"default": "companycrsopenai"}, "providers": [provider]}

    monkeypatch.setattr(mms_core, "load_config", lambda: cfg)
    monkeypatch.setattr(mms_core, "apply_local_overrides", lambda loaded: loaded)
    monkeypatch.setattr(mms_core, "_default_config", lambda: {})
    monkeypatch.setattr(mms_core, "resolve_provider_context", lambda _loaded, _provider_id: provider)
    monkeypatch.setattr(mms_core, "_load_probe_file_cache", lambda _provider_id, allow_stale=False: {"raw_models": ["gpt-5.4"]})
    monkeypatch.setattr(mms_core, "_provider_candidates", lambda _loaded, default, default_models: [(default, default_models)])
    monkeypatch.setattr(mms_core, "_provider_effective_models", lambda _provider, cached, _cfg=None: list(cached or []))

    candidates, error = _resolve_review_launch_candidates("gpt-5.4", {})

    assert error == ""
    assert [candidate["protocol"] for candidate in candidates] == [OPENAI_CHAT_PROTOCOL]
    assert candidates[0]["provider"]["id"] == "companycrsopenai"
    assert candidates[0]["model_name"] == "gpt-5.4"


def test_review_launch_gpt_dual_provider_never_calls_messages_endpoint(tmp_path, monkeypatch, capsys):
    import mms_core
    import mms_review_launch
    from mms_review_launch import OPENAI_CHAT_PROTOCOL, handle_review_launch_command

    env = _write_review_launch_fixture(tmp_path, reviewer_id="gpt-5.4")
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    provider = {
        "id": "companycrsopenai",
        "enabled": True,
        "role": "auto",
        "priority": 120,
        "protocols": ["anthropic_messages", "openai_chat_completions"],
        "anthropic_base_url": "https://gateway.example.com/openai",
        "openai_base_url": "https://gateway.example.com/openai/v1",
        "api_key": "key",
    }
    cfg = {"provider": {"default": "companycrsopenai"}, "providers": [provider]}

    monkeypatch.setattr(mms_core, "load_config", lambda: cfg)
    monkeypatch.setattr(mms_core, "apply_local_overrides", lambda loaded: loaded)
    monkeypatch.setattr(mms_core, "_default_config", lambda: {})
    monkeypatch.setattr(mms_core, "resolve_provider_context", lambda _loaded, _provider_id: provider)
    monkeypatch.setattr(mms_core, "_load_probe_file_cache", lambda _provider_id, allow_stale=False: {"raw_models": ["gpt-5.4"]})
    monkeypatch.setattr(mms_core, "_provider_candidates", lambda _loaded, default, default_models: [(default, default_models)])
    monkeypatch.setattr(mms_core, "_provider_effective_models", lambda _provider, cached, _cfg=None: list(cached or []))

    calls = []

    async def fake_call_model(*, provider, protocol, model_name, prompt, max_tokens, read_timeout_seconds=180):
        calls.append(protocol)
        return "Verdict: PASS\n\nNo blockers found.\n"

    monkeypatch.setattr(mms_review_launch, "_call_model", fake_call_model)

    assert handle_review_launch_command([], command_name="mms") == 0
    payload = json.loads(capsys.readouterr().out)

    assert calls == [OPENAI_CHAT_PROTOCOL]
    assert payload["provider_protocol"] == OPENAI_CHAT_PROTOCOL
    assert payload["dispatch_attempts"][0]["request_path"] == "/openai/v1/chat/completions"
    assert payload["transport_evidence"][0]["schema"] == "cache_transport_evidence.v1"
    assert payload["transport_evidence"][0]["protocol"] == OPENAI_CHAT_PROTOCOL
    assert payload["transport_evidence"][0]["request_path"] == "/openai/v1/chat/completions"
    assert payload["transport_evidence"][0]["usage"]["cached_tokens"] == 0
    assert Path(env["MOEBIUS_REVIEW_EXPECTED_OUTPUT"]).exists()


def test_review_launch_transport_evidence_uses_model_call_usage(tmp_path, monkeypatch, capsys):
    import mms_review_launch
    from mms_review_launch import ANTHROPIC_MESSAGES_PROTOCOL, ModelCallResult, handle_review_launch_command

    env = _write_review_launch_fixture(tmp_path, reviewer_id="glm-5.1")
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    provider = {"id": "newapi-personal-tokyo", "protocols": [ANTHROPIC_MESSAGES_PROTOCOL]}
    monkeypatch.setattr(
        mms_review_launch,
        "_resolve_review_launch_candidates",
        lambda _model, _env: (
            [{"provider": provider, "protocol": ANTHROPIC_MESSAGES_PROTOCOL, "model_name": "glm-5.1"}],
            "",
        ),
    )

    usage = {
        "input_tokens": 123,
        "output_tokens": 45,
        "cache_read_input_tokens": 67,
        "cache_creation_input_tokens": 8,
        "cached_tokens": 67,
    }

    async def fake_call_model(*, provider, protocol, model_name, prompt, max_tokens, read_timeout_seconds=180):
        return ModelCallResult("Verdict: PASS\n\nNo blockers found.\n", usage)

    monkeypatch.setattr(mms_review_launch, "_call_model", fake_call_model)

    assert handle_review_launch_command([], command_name="mms") == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["transport_evidence"][0]["usage"] == usage
    assert payload["transport_evidence"][0]["route_source"] == "mms:legacy-provider-config"
    assert payload["dispatch_attempts"][0]["usage"] == usage
    assert payload["cache_transport_evidence"] == payload["transport_evidence"]
    assert Path(env["MOEBIUS_REVIEW_EXPECTED_OUTPUT"]).exists()


def test_review_launch_explicit_provider_reports_protocol_specific_base_url(monkeypatch):
    import mms_core
    from mms_review_launch import OPENAI_CHAT_PROTOCOL, _resolve_provider_for_model

    provider = {
        "id": "mimo-direct-anthropic",
        "protocols": ["anthropic_messages"],
        "anthropic_base_url": "https://token-plan-cn.xiaomimimo.com/anthropic",
        "api_key": "key",
    }
    monkeypatch.setattr(mms_core, "load_config", lambda: {"provider": {"default": "default"}, "providers": []})
    monkeypatch.setattr(mms_core, "apply_local_overrides", lambda cfg: cfg)
    monkeypatch.setattr(mms_core, "_default_config", lambda: {})
    monkeypatch.setattr(mms_core, "resolve_provider_context", lambda cfg, provider_id: provider)

    resolved, protocol, error = _resolve_provider_for_model(
        "mimo-v2.5",
        {"MMS_REVIEW_LAUNCH_PROVIDER_ID": "mimo-direct-anthropic", "MMS_REVIEW_LAUNCH_PROTOCOL": OPENAI_CHAT_PROTOCOL},
    )

    assert resolved is None
    assert protocol == ""
    assert "does not declare protocol openai_chat_completions" in error


def test_review_launch_explicit_provider_chain_preserves_order(monkeypatch):
    import mms_core
    from mms_review_launch import ANTHROPIC_MESSAGES_PROTOCOL, OPENAI_CHAT_PROTOCOL, _resolve_review_launch_candidates

    tokyo = {
        "id": "newapi-tokyo-test",
        "enabled": True,
        "role": "auto",
        "priority": 120,
        "protocols": [ANTHROPIC_MESSAGES_PROTOCOL, OPENAI_CHAT_PROTOCOL],
        "anthropic_base_url": "https://tokyo.example.com",
        "openai_base_url": "https://tokyo.example.com/v1",
        "api_key": "key",
        "models": ["qwen3.5-plus"],
    }
    xin = {
        "id": "xin-test",
        "enabled": True,
        "role": "fallback",
        "priority": 90,
        "protocols": [ANTHROPIC_MESSAGES_PROTOCOL, OPENAI_CHAT_PROTOCOL],
        "anthropic_base_url": "https://xin.example.com",
        "openai_base_url": "https://xin.example.com/v1",
        "api_key": "key",
        "models": ["qwen3.5-plus"],
    }
    extra = {**xin, "id": "unlisted-test", "priority": 200}
    cfg = {"provider": {"default": "unlisted-test"}, "providers": [extra, tokyo, xin]}

    monkeypatch.setattr(mms_core, "load_config", lambda: cfg)
    monkeypatch.setattr(mms_core, "apply_local_overrides", lambda loaded: loaded)
    monkeypatch.setattr(mms_core, "_default_config", lambda: {})
    monkeypatch.setattr(
        mms_core,
        "resolve_provider_context",
        lambda _loaded, provider_id: {"newapi-tokyo-test": tokyo, "xin-test": xin, "unlisted-test": extra}[provider_id],
    )
    monkeypatch.setattr(mms_core, "_load_probe_file_cache", lambda provider_id, allow_stale=False: {"raw_models": ["qwen3.5-plus"]})

    def fake_effective_models(provider, cached, _cfg=None):
        if isinstance(cached, dict):
            return list(cached.get("raw_models") or [])
        return list(cached or provider.get("models") or [])

    monkeypatch.setattr(mms_core, "_provider_effective_models", fake_effective_models)

    candidates, error = _resolve_review_launch_candidates(
        "qwen3.5-plus",
        {"MMS_REVIEW_LAUNCH_PROVIDER_IDS": "newapi-tokyo-test,xin-test"},
    )

    assert error == ""
    assert [(item["provider"]["id"], item["protocol"]) for item in candidates] == [
        ("newapi-tokyo-test", ANTHROPIC_MESSAGES_PROTOCOL),
        ("newapi-tokyo-test", OPENAI_CHAT_PROTOCOL),
        ("xin-test", ANTHROPIC_MESSAGES_PROTOCOL),
        ("xin-test", OPENAI_CHAT_PROTOCOL),
    ]


def test_review_launch_falls_back_to_next_protocol_after_failed_attempt(tmp_path, monkeypatch, capsys):
    import mms_review_launch
    from mms_review_launch import ANTHROPIC_MESSAGES_PROTOCOL, OPENAI_CHAT_PROTOCOL, handle_review_launch_command

    env = _write_review_launch_fixture(tmp_path, reviewer_id="gemini-3-flash-preview")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("MMS_REVIEW_LAUNCH_ALLOW_CHAT_FALLBACK", "1")

    provider = {"id": "us-cpa-local-gemini", "protocols": [ANTHROPIC_MESSAGES_PROTOCOL, OPENAI_CHAT_PROTOCOL]}
    monkeypatch.setattr(
        mms_review_launch,
        "_resolve_review_launch_candidates",
        lambda _model, _env: (
            [
                {"provider": provider, "protocol": ANTHROPIC_MESSAGES_PROTOCOL, "model_name": "gemini-3-flash-preview"},
                {"provider": provider, "protocol": OPENAI_CHAT_PROTOCOL, "model_name": "gemini-3-flash-preview"},
            ],
            "",
        ),
    )

    async def fake_call_model(*, provider, protocol, model_name, prompt, max_tokens, read_timeout_seconds=180):
        if protocol == ANTHROPIC_MESSAGES_PROTOCOL:
            raise RuntimeError("model dispatch failed HTTP 404: page not found")
        return "Verdict: PASS\n\nNo blockers found.\n"

    monkeypatch.setattr(mms_review_launch, "_call_model", fake_call_model)

    assert handle_review_launch_command([], command_name="mms") == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert payload["model_calls"] == 2
    assert payload["provider_protocol"] == OPENAI_CHAT_PROTOCOL
    assert payload["dispatch_attempts"][0]["ok"] is False
    assert payload["dispatch_attempts"][1]["ok"] is True
    assert Path(env["MOEBIUS_REVIEW_EXPECTED_OUTPUT"]).exists()


def test_review_launch_falls_back_to_next_provider_without_chat_fallback(tmp_path, monkeypatch, capsys):
    import mms_review_launch
    from mms_review_launch import ANTHROPIC_MESSAGES_PROTOCOL, OPENAI_CHAT_PROTOCOL, handle_review_launch_command

    env = _write_review_launch_fixture(tmp_path, reviewer_id="qwen3.5-plus")
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    tokyo = {
        "id": "newapi-tokyo-test",
        "protocols": [ANTHROPIC_MESSAGES_PROTOCOL, OPENAI_CHAT_PROTOCOL],
        "anthropic_base_url": "https://tokyo.example.com",
        "openai_base_url": "https://tokyo.example.com/v1",
        "api_key": "key",
    }
    xin = {
        "id": "xin-test",
        "protocols": [ANTHROPIC_MESSAGES_PROTOCOL, OPENAI_CHAT_PROTOCOL],
        "anthropic_base_url": "https://xin.example.com",
        "openai_base_url": "https://xin.example.com/v1",
        "api_key": "key",
    }
    monkeypatch.setattr(
        mms_review_launch,
        "_resolve_review_launch_candidates",
        lambda _model, _env: (
            [
                {"provider": tokyo, "protocol": ANTHROPIC_MESSAGES_PROTOCOL, "model_name": "qwen3.5-plus"},
                {"provider": tokyo, "protocol": OPENAI_CHAT_PROTOCOL, "model_name": "qwen3.5-plus"},
                {"provider": xin, "protocol": ANTHROPIC_MESSAGES_PROTOCOL, "model_name": "qwen3.5-plus"},
            ],
            "",
        ),
    )

    calls = []

    async def fake_call_model(*, provider, protocol, model_name, prompt, max_tokens, read_timeout_seconds=180):
        calls.append((provider["id"], protocol))
        if provider["id"] == "newapi-tokyo-test":
            raise RuntimeError("model dispatch failed HTTP 503: tokyo unavailable")
        return "Verdict: PASS\n\nNo blockers found.\n"

    monkeypatch.setattr(mms_review_launch, "_call_model", fake_call_model)

    assert handle_review_launch_command([], command_name="mms") == 0
    payload = json.loads(capsys.readouterr().out)

    assert calls == [
        ("newapi-tokyo-test", ANTHROPIC_MESSAGES_PROTOCOL),
        ("xin-test", ANTHROPIC_MESSAGES_PROTOCOL),
    ]
    assert payload["provider_id"] == "xin-test"
    assert payload["provider_protocol"] == ANTHROPIC_MESSAGES_PROTOCOL
    assert payload["model_calls"] == 2
    assert payload["dispatch_attempts"][1]["skipped"] is True
    assert payload["dispatch_attempts"][1]["request_path"] == "/v1/chat/completions"
    evidence = payload["transport_evidence"][0]
    assert evidence["provider_id"] == "xin-test"
    assert evidence["protocol"] == ANTHROPIC_MESSAGES_PROTOCOL
    assert evidence["request_path"] == "/v1/messages"
    assert evidence["fallback_used"] is True
    assert "tokyo unavailable" in evidence["fallback_reason"]
    assert Path(env["MOEBIUS_REVIEW_EXPECTED_OUTPUT"]).exists()


def test_review_launch_blocks_cache_sensitive_chat_fallback_by_default(tmp_path, monkeypatch, capsys):
    import mms_review_launch
    from mms_review_launch import ANTHROPIC_MESSAGES_PROTOCOL, OPENAI_CHAT_PROTOCOL, handle_review_launch_command

    env = _write_review_launch_fixture(tmp_path, reviewer_id="kimi-for-coding")
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    provider = {
        "id": "newapi-personal-tokyo",
        "protocols": [ANTHROPIC_MESSAGES_PROTOCOL, OPENAI_CHAT_PROTOCOL],
        "anthropic_base_url": "http://tokyo.example.com",
        "openai_base_url": "http://tokyo.example.com/v1",
        "api_key": "key",
    }
    monkeypatch.setattr(
        mms_review_launch,
        "_resolve_review_launch_candidates",
        lambda _model, _env: (
            [
                {"provider": provider, "protocol": ANTHROPIC_MESSAGES_PROTOCOL, "model_name": "kimi-for-coding"},
                {"provider": provider, "protocol": OPENAI_CHAT_PROTOCOL, "model_name": "kimi-for-coding"},
            ],
            "",
        ),
    )

    calls = []

    async def fake_call_model(*, provider, protocol, model_name, prompt, max_tokens, read_timeout_seconds=180):
        calls.append(protocol)
        raise RuntimeError("model response content is empty")

    monkeypatch.setattr(mms_review_launch, "_call_model", fake_call_model)

    assert handle_review_launch_command([], command_name="mms") == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert payload["model_calls"] == 1
    assert payload["provider_protocol"] == ANTHROPIC_MESSAGES_PROTOCOL
    assert payload["dispatch_trace"]["selected_protocol"] == ANTHROPIC_MESSAGES_PROTOCOL
    assert calls == [ANTHROPIC_MESSAGES_PROTOCOL]
    assert payload["dispatch_attempts"][0]["ok"] is False
    assert payload["dispatch_attempts"][1]["ok"] is False
    assert payload["dispatch_attempts"][1]["skipped"] is True
    assert "chat fallback blocked" in payload["dispatch_attempts"][1]["error"]
    assert len(payload["transport_evidence"]) == 1
    evidence = payload["transport_evidence"][0]
    assert evidence["schema"] == "cache_transport_evidence.v1"
    assert evidence["provider_id"] == "newapi-personal-tokyo"
    assert evidence["protocol"] == ANTHROPIC_MESSAGES_PROTOCOL
    assert evidence["request_url"] == "http://tokyo.example.com/v1/messages?beta=true"
    assert evidence["request_path"] == "/v1/messages"
    assert evidence["usage"]["cache_read_input_tokens"] == 0
    assert payload["cache_transport_evidence"] == payload["transport_evidence"]
    assert payload["dispatch_trace"]["chat_fallback_allowed"] is False
    assert not Path(env["MOEBIUS_REVIEW_EXPECTED_OUTPUT"]).exists()


def test_review_launch_compact_error_keeps_blank_exception_class():
    from mms_review_launch import _compact_error

    assert _compact_error(TimeoutError()) == "TimeoutError"


def test_review_launch_anthropic_call_uses_messages_endpoint(monkeypatch):
    import asyncio
    import httpx
    from mms_review_launch import _call_model_anthropic_messages

    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "content": [{"type": "text", "text": "Reviewer: mimo-v2-flash\n\nVerdict: PASS"}],
                "usage": {
                    "input_tokens": 101,
                    "output_tokens": 11,
                    "cache_read_input_tokens": 31,
                    "cache_creation_input_tokens": 7,
                },
            }

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["json"] = json or {}
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    text = asyncio.run(
        _call_model_anthropic_messages(
            provider={
                "id": "mimo-direct-anthropic",
                "protocols": ["anthropic_messages"],
                "anthropic_base_url": "https://token-plan-cn.xiaomimimo.com/anthropic",
                "api_key": "key",
            },
            model_name="mimo-v2-flash",
            prompt="review this",
            max_tokens=1234,
        )
    )

    assert text.startswith("Reviewer: mimo-v2-flash")
    assert text.usage["input_tokens"] == 101
    assert text.usage["output_tokens"] == 11
    assert text.usage["cache_read_input_tokens"] == 31
    assert text.usage["cache_creation_input_tokens"] == 7
    assert text.usage["cached_tokens"] == 31
    assert captured["url"] == "https://token-plan-cn.xiaomimimo.com/anthropic/v1/messages"
    assert captured["headers"]["x-api-key"] == "key"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["json"]["model"] == "mimo-v2-flash"
    assert captured["json"]["max_tokens"] == 1234
    assert captured["json"]["messages"][0]["content"][0]["text"] == "review this"


def test_review_launch_anthropic_call_does_not_force_unsupported_mimo_1m_alias(monkeypatch):
    import asyncio
    import httpx
    from mms_review_launch import _call_model_anthropic_messages

    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"content": [{"type": "text", "text": "Verdict: PASS"}]}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None, timeout=None):
            captured["json"] = json or {}
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    asyncio.run(
        _call_model_anthropic_messages(
            provider={
                "id": "mimo-direct-anthropic",
                "protocols": ["anthropic_messages"],
                "anthropic_base_url": "https://token-plan-cn.xiaomimimo.com/anthropic",
                "api_key": "key",
            },
            model_name="mimo-v2.5-pro",
            prompt="review this",
            max_tokens=1234,
        )
    )

    assert captured["json"]["model"] == "mimo-v2.5-pro"


def test_review_launch_anthropic_call_does_not_double_append_v1(monkeypatch):
    import asyncio
    import httpx
    from mms_review_launch import _call_model_anthropic_messages

    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"content": [{"type": "text", "text": "Verdict: PASS"}]}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None, timeout=None):
            captured["url"] = url
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    asyncio.run(
        _call_model_anthropic_messages(
            provider={
                "id": "us-cpa-local-gemini",
                "protocols": ["anthropic_messages"],
                "anthropic_base_url": "http://127.0.0.1:18417/v1",
                "api_key": "key",
            },
            model_name="gemini-3-flash-preview",
            prompt="review this",
            max_tokens=1234,
        )
    )

    assert captured["url"] == "http://127.0.0.1:18417/v1/messages"


def test_review_launch_anthropic_call_adds_newapi_beta_once(monkeypatch):
    import asyncio
    import httpx
    from mms_review_launch import _call_model_anthropic_messages

    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"content": [{"type": "text", "text": "Verdict: PASS"}]}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["json"] = json or {}
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    asyncio.run(
        _call_model_anthropic_messages(
            provider={
                "id": "newapi-personal-tokyo",
                "name": "newapi-personal-tokyo",
                "protocols": ["anthropic_messages"],
                "anthropic_base_url": "http://161.33.197.51:4001",
                "api_key": "key",
            },
            model_name="deepseek-v4-flash",
            prompt="review this",
            max_tokens=1234,
        )
    )

    assert captured["url"] == "http://161.33.197.51:4001/v1/messages?beta=true"
    assert captured["json"]["stream"] is False

    asyncio.run(
        _call_model_anthropic_messages(
            provider={
                "id": "newapi-personal-tokyo",
                "protocols": ["anthropic_messages"],
                "anthropic_base_url": "http://161.33.197.51:4001/v1/messages?beta=true",
                "api_key": "key",
            },
            model_name="deepseek-v4-flash",
            prompt="review this",
            max_tokens=1234,
        )
    )

    assert captured["url"] == "http://161.33.197.51:4001/v1/messages?beta=true"


@pytest.mark.parametrize("model_name", ["kimi-for-coding", "qwen3.5-plus"])
def test_review_launch_anthropic_high_latency_models_use_streaming(monkeypatch, model_name):
    import asyncio
    import httpx
    from mms_review_launch import _call_model_anthropic_messages

    captured = {}

    class FakeResponse:
        status_code = 200
        text = (
            'data: {"type":"message_start","message":{"usage":{"input_tokens":211,"cache_read_input_tokens":144,"cache_creation_input_tokens":13}}}\n'
            'data: {"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"hidden"}}\n'
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Verdict: "}}\n'
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"PASS"}}\n'
            'data: {"type":"message_delta","usage":{"output_tokens":23}}\n'
            'data: {"type":"message_stop"}\n'
        )

        def json(self):
            raise AssertionError("streaming response should be parsed as SSE")

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["json"] = json or {}
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    text = asyncio.run(
        _call_model_anthropic_messages(
            provider={
                "id": "newapi-personal-tokyo",
                "protocols": ["anthropic_messages"],
                "anthropic_base_url": "http://161.33.197.51:4001",
                "api_key": "key",
            },
            model_name=model_name,
            prompt="review this",
            max_tokens=1234,
        )
    )

    assert captured["url"] == "http://161.33.197.51:4001/v1/messages?beta=true"
    assert captured["json"]["stream"] is True
    assert text == "Verdict: PASS"
    assert text.usage["input_tokens"] == 211
    assert text.usage["output_tokens"] == 23
    assert text.usage["cache_read_input_tokens"] == 144
    assert text.usage["cache_creation_input_tokens"] == 13
    assert text.usage["cached_tokens"] == 144


def test_review_launch_openai_call_does_not_double_append_v1_and_stream_fallback(monkeypatch):
    import asyncio
    import httpx
    from mms_review_launch import _call_model_openai_chat

    captured_urls = []
    captured_stream_values = []

    class FakeResponse:
        def __init__(self, status_code, text="", payload=None):
            self.status_code = status_code
            self.text = text
            self._payload = payload or {}

        def json(self):
            return self._payload

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None, timeout=None):
            captured_urls.append(url)
            captured_stream_values.append((json or {}).get("stream"))
            if len(captured_urls) == 1:
                return FakeResponse(400, '{"detail":"Stream must be set to true"}')
            return FakeResponse(
                200,
                'data: {"choices":[{"delta":{"content":"Verdict: "}}]}\n'
                'data: {"choices":[{"delta":{"content":"PASS"}}]}\n'
                'data: {"choices":[],"usage":{"prompt_tokens":88,"completion_tokens":9,"prompt_tokens_details":{"cached_tokens":55}}}\n'
                "data: [DONE]\n",
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    text = asyncio.run(
        _call_model_openai_chat(
            provider={
                "id": "uscrsopenai",
                "protocols": ["openai_chat_completions"],
                "openai_base_url": "http://127.0.0.1:18317/v1",
                "api_key": "key",
            },
            model_name="gpt-5.3-codex",
            prompt="review this",
            max_tokens=1234,
        )
    )

    assert captured_urls == ["http://127.0.0.1:18317/v1/chat/completions"] * 2
    assert captured_stream_values == [False, True]
    assert text == "Verdict: PASS"
    assert text.usage["input_tokens"] == 88
    assert text.usage["output_tokens"] == 9
    assert text.usage["cache_read_input_tokens"] == 55
    assert text.usage["cached_tokens"] == 55


def test_review_launch_rejects_output_path_escape_before_writing(tmp_path, monkeypatch, capsys):
    from mms_review_launch import handle_review_launch_command

    env = _write_review_launch_fixture(tmp_path)
    escaped = tmp_path / "outside-review.md"
    env["MOEBIUS_REVIEW_EXPECTED_OUTPUT"] = str(escaped)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("MMS_REVIEW_LAUNCH_FAKE_RESPONSE", "Reviewer: kimi-for-coding\n\nVerdict: PASS\n")

    assert handle_review_launch_command([], command_name="mms") == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert payload["review_file_written"] is False
    assert not escaped.exists()
    assert any("MOEBIUS_REVIEW_EXPECTED_OUTPUT must stay under MOEBIUS_REPO_ROOT" in item for item in payload["errors"])


def test_review_launch_rejects_unapproved_gate_before_writing(tmp_path, monkeypatch, capsys):
    from mms_review_launch import handle_review_launch_command

    env = _write_review_launch_fixture(tmp_path)
    Path(env["MOEBIUS_REVIEW_DISPATCH_GATE"]).write_text(json.dumps({"gate_status": "blocked"}) + "\n", encoding="utf-8")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("MMS_REVIEW_LAUNCH_FAKE_RESPONSE", "Reviewer: kimi-for-coding\n\nVerdict: PASS\n")

    assert handle_review_launch_command([], command_name="mms") == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert payload["review_file_written"] is False
    assert not Path(env["MOEBIUS_REVIEW_EXPECTED_OUTPUT"]).exists()
    assert any("review-dispatch gate must be approved" in item for item in payload["errors"])


def test_mms_core_routes_review_launch_help():
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "mms"), "review-launch", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "review-launch" in completed.stdout
    assert "multi-review" in completed.stdout
    assert "reviewer" in completed.stdout
