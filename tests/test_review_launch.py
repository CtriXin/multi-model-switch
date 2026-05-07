from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


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


def test_review_launch_falls_back_to_next_protocol_after_failed_attempt(tmp_path, monkeypatch, capsys):
    import mms_review_launch
    from mms_review_launch import ANTHROPIC_MESSAGES_PROTOCOL, OPENAI_CHAT_PROTOCOL, handle_review_launch_command

    env = _write_review_launch_fixture(tmp_path, reviewer_id="gemini-3-flash-preview")
    for key, value in env.items():
        monkeypatch.setenv(key, value)

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


def test_review_launch_anthropic_call_uses_messages_endpoint(monkeypatch):
    import asyncio
    import httpx
    from mms_review_launch import _call_model_anthropic_messages

    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"content": [{"type": "text", "text": "Reviewer: mimo-v2.5\n\nVerdict: PASS"}]}

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
            model_name="mimo-v2.5",
            prompt="review this",
            max_tokens=1234,
        )
    )

    assert text.startswith("Reviewer: mimo-v2.5")
    assert captured["url"] == "https://token-plan-cn.xiaomimimo.com/anthropic/v1/messages"
    assert captured["headers"]["x-api-key"] == "key"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["json"]["model"] == "mimo-v2.5"
    assert captured["json"]["max_tokens"] == 1234
    assert captured["json"]["messages"][0]["content"][0]["text"] == "review this"


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
