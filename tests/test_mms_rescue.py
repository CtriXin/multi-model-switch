import io
import json
import types
from pathlib import Path


def test_write_file_only_rescue_redacts_and_indexes(tmp_path):
    from mms_rescue import is_secret_safe, write_file_only_rescue

    repo = tmp_path / "repo"
    config_root = tmp_path / "mms-config"
    repo.mkdir()
    event = {
        "registry_revision": "reg_test",
        "failed": {
            "model": "gpt-5.5",
            "provider_id": "private-relay",
            "status_code": 429,
            "error_type": "rate_limit",
            "error_summary": "Authorization: Bearer sk-secret-token-1234567890 hit quota",
        },
        "git": {"status_short": " M mms_bridge.py"},
        "next_action": "Resume from rescue packet.",
    }

    payload = write_file_only_rescue(
        event,
        repo_root=repo,
        config_root=config_root,
        raw_artifacts={
            "upstream-response.json": {
                "Authorization": "Bearer sk-raw-secret-token-1234567890",
                "message": "quota",
            }
        },
        created_at="2026-05-22T01:00:00+00:00",
    )

    latest_json = repo / ".mms" / "rescue" / "latest.json"
    latest_md = repo / ".mms" / "rescue" / "latest.md"
    index_path = config_root / "rescue" / "index.jsonl"
    assert latest_json.exists()
    assert latest_md.exists()
    assert index_path.exists()

    latest_text = latest_json.read_text(encoding="utf-8")
    raw_text = Path(payload["artifacts"]["raw_written"][0]).read_text(encoding="utf-8")
    index_text = index_path.read_text(encoding="utf-8")
    assert "sk-secret" not in latest_text
    assert "sk-raw-secret" not in raw_text
    assert "Authorization" not in index_text
    assert is_secret_safe(latest_text)
    assert is_secret_safe(raw_text)
    assert json.loads(latest_text)["rescue_level"] == "L3_file_only"
    assert json.loads(index_text.splitlines()[0])["schema"] == "mms.rescue_index.v1"


def test_write_file_only_rescue_skips_auth_bearing_raw_files(tmp_path):
    from mms_rescue import write_file_only_rescue

    repo = tmp_path / "repo"
    repo.mkdir()
    payload = write_file_only_rescue(
        {"failed": {"model": "glm-5.1"}},
        repo_root=repo,
        config_root=tmp_path / "mms-config",
        raw_artifacts={
            "~/.codex/auth.json": '{"access_token":"secret"}',
            "safe-log.txt": "plain error",
        },
        created_at="2026-05-22T01:01:00+00:00",
    )

    assert payload["artifacts"]["raw_skipped_auth_bearing"] == ["~/.codex/auth.json"]
    assert len(payload["artifacts"]["raw_written"]) == 1
    assert Path(payload["artifacts"]["raw_written"][0]).name == "safe-log.txt"


def test_list_rescue_events_loads_recent_enriched_payloads(tmp_path):
    from mms_rescue import list_rescue_events, write_file_only_rescue

    repo = tmp_path / "repo"
    config_root = tmp_path / "mms-config"
    repo.mkdir()
    write_file_only_rescue(
        {
            "failed": {
                "model": "older-model",
                "provider_id": "relay-a",
                "status_code": 429,
                "failure_kind": "rate_limit_or_quota",
            },
        },
        repo_root=repo,
        config_root=config_root,
        created_at="2026-05-22T01:00:00+00:00",
    )
    write_file_only_rescue(
        {
            "failed": {
                "model": "newer-model",
                "provider_id": "relay-b",
                "status_code": 413,
                "failure_kind": "context_overflow",
            },
        },
        repo_root=repo,
        config_root=config_root,
        created_at="2026-05-22T02:00:00+00:00",
    )

    events = list_rescue_events(repo_root=repo, config_root=config_root, limit=5)

    assert [event["failed_model"] for event in events] == ["newer-model", "older-model"]
    assert events[0]["failed_provider_id"] == "relay-b"
    assert events[0]["status_code"] == 413
    assert events[0]["artifact_markdown"].endswith("rescue.md")


def test_write_demo_rescue_packet_is_listable_and_marked_demo(tmp_path):
    from mms_rescue import list_rescue_events, write_demo_rescue_packet

    repo = tmp_path / "repo"
    config_root = tmp_path / "mms-config"
    repo.mkdir()

    payload = write_demo_rescue_packet(
        repo_root=repo,
        config_root=config_root,
        created_at="2026-05-22T03:00:00+00:00",
    )
    events = list_rescue_events(repo_root=repo, config_root=config_root, limit=5)

    assert payload["failed"]["model"] == "demo-rescue-model"
    assert events[0]["failed_model"] == "demo-rescue-model"
    assert events[0]["failed_provider_id"] == "demo-provider"
    assert "Demo rescue packet" in events[0]["error_summary"]


def test_write_fallback_handover_is_file_only_and_context_aware(tmp_path):
    from mms_rescue import list_rescue_events, write_fallback_handover, write_file_only_rescue

    repo = tmp_path / "repo"
    config_root = tmp_path / "mms-config"
    repo.mkdir()
    source_payload = write_file_only_rescue(
        {
            "failed": {
                "model": "failed-model",
                "provider_id": "relay",
                "status_code": 413,
                "failure_kind": "context_overflow",
                "error_summary": "context window exceeded",
            },
        },
        repo_root=repo,
        config_root=config_root,
        created_at="2026-05-22T04:00:00+00:00",
    )
    event = list_rescue_events(repo_root=repo, config_root=config_root)[0]

    handover = write_fallback_handover(
        event,
        fallback_model="fallback-model",
        created_at="2026-05-22T04:01:00+00:00",
    )

    assert handover["schema"] == "mms.rescue_fallback_handover.v1"
    assert handover["fallback"]["automatic_model_call"] is False
    assert handover["context_policy"]["mode"] == "compact_first"
    md_path = Path(handover["artifacts"]["markdown"])
    latest_path = repo / ".mms" / "rescue" / "latest-fallback-handover.md"
    assert md_path.exists()
    assert latest_path.exists()
    assert "fallback-model" in md_path.read_text(encoding="utf-8")

    auto_handover = write_fallback_handover(
        source_payload,
        fallback_model="auto-fallback-model",
        mode="auto_default_handover",
        created_at="2026-05-22T04:02:00+00:00",
    )
    assert auto_handover["failed"]["model"] == "failed-model"
    assert auto_handover["fallback"]["mode"] == "auto_default_handover"


def test_rescue_config_root_uses_real_home_not_gateway_session(monkeypatch, tmp_path):
    from mms_rescue import resolve_real_mms_config_dir

    real_home = tmp_path / "home"
    session_home = real_home / ".config" / "mms" / "codex-gateway" / "s" / "12345"
    monkeypatch.delenv("MMS_REAL_HOME", raising=False)
    monkeypatch.delenv("REAL_HOME", raising=False)
    monkeypatch.delenv("ORIGINAL_HOME", raising=False)
    monkeypatch.setenv("HOME", str(session_home))

    assert resolve_real_mms_config_dir() == real_home / ".config" / "mms"


def test_rescue_config_root_prefers_real_home_env(tmp_path):
    from mms_rescue import resolve_real_mms_config_dir

    session_home = tmp_path / ".config" / "mms" / "codex-gateway" / "s" / "12345"
    mms_real = tmp_path / "mms-real"
    real = tmp_path / "real"
    original = tmp_path / "original"

    assert resolve_real_mms_config_dir({
        "HOME": str(session_home),
        "MMS_REAL_HOME": str(mms_real),
        "REAL_HOME": str(real),
        "ORIGINAL_HOME": str(original),
    }) == mms_real / ".config" / "mms"
    assert resolve_real_mms_config_dir({
        "HOME": str(session_home),
        "REAL_HOME": str(real),
        "ORIGINAL_HOME": str(original),
    }) == real / ".config" / "mms"
    assert resolve_real_mms_config_dir({
        "HOME": str(session_home),
        "ORIGINAL_HOME": str(original),
    }) == original / ".config" / "mms"


def test_record_blocking_failure_redacts_secret_upstream_body(tmp_path):
    from mms_rescue import record_blocking_failure

    repo = tmp_path / "repo"
    repo.mkdir()
    payload = record_blocking_failure(
        repo_root=repo,
        config_root=tmp_path / "mms-config",
        model="gpt-5.5",
        provider_id="relay",
        status_code=429,
        body_text='{"error":{"message":"quota","access_token":"secret-token-123","api_key":"sk-live-secret-1234567890"}}',
        request_url="https://relay.example.com/v1/responses?api_key=sk-query-secret-1234567890",
        created_at="2026-05-22T01:02:00+00:00",
    )

    assert payload is not None
    latest_text = (repo / ".mms" / "rescue" / "latest.json").read_text(encoding="utf-8")
    raw_text = Path(payload["artifacts"]["raw_written"][0]).read_text(encoding="utf-8")
    assert "secret-token" not in latest_text
    assert "sk-live-secret" not in latest_text
    assert "sk-query-secret" not in latest_text
    assert "secret-token" not in raw_text
    assert "sk-live-secret" not in raw_text
    assert payload["safety"]["global_oauth_fallback"] == "disabled"
    assert payload["safety"]["automatic_model_call"] is False


def test_bridge_mocked_429_writes_file_only_rescue_without_oauth(monkeypatch, tmp_path):
    import mms_bridge

    repo = tmp_path / "repo"
    config_root = tmp_path / "mms-config"
    repo.mkdir()

    class FakeResponse:
        status_code = 429
        headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return b'{"error":{"message":"quota hit","authorization":"Bearer sk-upstream-secret-1234567890"}}'

    def fail_oauth(*_args, **_kwargs):
        raise AssertionError("global OAuth fallback must not be used")

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=lambda *_args, **_kwargs: FakeResponse()))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)
    monkeypatch.setattr(mms_bridge, "_load_codex_auth", fail_oauth)

    raw_body = json.dumps({"model": "gpt-5.5", "input": "hi"}).encode()
    handler = mms_bridge._ResponsesProxyHandler.__new__(mms_bridge._ResponsesProxyHandler)
    handler.path = "/v1/responses"
    handler.headers = {
        "content-length": str(len(raw_body)),
        "authorization": "Bearer bridge-token",
    }
    handler.rfile = io.BytesIO(raw_body)
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        bridge_token="bridge-token",
        gateway_key="relay-key",
        gateway_url="https://relay.example.com/v1",
        model_name="gpt-5.5",
        advertised_models=["gpt-5.5"],
        speed_scope={},
        route_status_paths=[],
        provider_id="private-relay",
        provider_profile="openai",
        reasoning_enabled=True,
        reasoning_effort="high",
        proxy_url="",
        no_proxy="",
        native_fallback_routes=[],
        rescue_enabled=True,
        rescue_repo_root=str(repo),
        rescue_config_root=str(config_root),
        rescue_fallback_model="fallback-model",
        rescue_fallback_cli="codex",
    )
    captured = {"headers": []}
    handler.send_response = lambda code: captured.setdefault("status", code)
    handler.send_header = lambda *args, **kwargs: captured["headers"].append(args)
    handler.end_headers = lambda: None

    handler.do_POST()

    assert captured["status"] == 429
    latest_json = repo / ".mms" / "rescue" / "latest.json"
    assert latest_json.exists()
    payload = json.loads(latest_json.read_text(encoding="utf-8"))
    assert payload["rescue_level"] == "L3_file_only"
    assert payload["failed"]["status_code"] == 429
    assert payload["failed"]["failure_kind"] == "rate_limit_or_quota"
    assert payload["fallback"]["selected"] is False
    assert payload["safety"]["global_oauth_fallback"] == "disabled"
    assert "sk-upstream-secret" not in latest_json.read_text(encoding="utf-8")
    assert (config_root / "rescue" / "index.jsonl").exists()
    handover_json = repo / ".mms" / "rescue" / "latest-fallback-handover.json"
    assert handover_json.exists()
    handover = json.loads(handover_json.read_text(encoding="utf-8"))
    assert handover["fallback"]["model"] == "fallback-model"
    assert handover["fallback"]["cli"] == "codex"
    assert handover["fallback"]["mode"] == "auto_default_handover"
    assert handover["fallback"]["automatic_model_call"] is False


def test_responses_proxy_hot_fallback_uses_configured_rescue_model(monkeypatch, tmp_path):
    import mms_bridge

    repo = tmp_path / "repo"
    config_root = tmp_path / "mms-config"
    (config_root / "generated").mkdir(parents=True)
    repo.mkdir()
    (config_root / "generated" / "model-routes.json").write_text(
        json.dumps(
            {
                "version": 1,
                "routes": {
                    "deepseek-v4-flash": {
                        "primary": {
                            "provider_id": "newapi-deepseek",
                            "openai_base_url": "https://deepseek.example/v1",
                            "api_key": "sk-deepseek-test",
                            "model_id": "deepseek-v4-flash",
                        },
                        "fallbacks": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    class FakeResponse:
        status_code = 503
        headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return b'{"error":{"message":"auth_unavailable: no auth available"}}'

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=lambda *_args, **_kwargs: FakeResponse()))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)
    emitted_events = []
    monkeypatch.setattr(mms_bridge, "_emit_event", lambda *args, **kwargs: emitted_events.append((args, kwargs)))

    raw_body = json.dumps({"model": "gpt-5.5", "input": "hi"}).encode()
    handler = mms_bridge._ResponsesProxyHandler.__new__(mms_bridge._ResponsesProxyHandler)
    handler.path = "/v1/responses"
    handler.headers = {
        "content-length": str(len(raw_body)),
        "authorization": "Bearer bridge-token",
    }
    handler.rfile = io.BytesIO(raw_body)
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        bridge_token="bridge-token",
        gateway_key="relay-key",
        gateway_url="https://relay.example/v1",
        model_name="gpt-5.5",
        advertised_models=["gpt-5.5"],
        speed_scope={},
        route_status_paths=[],
        provider_id="codex-relay",
        provider_profile="openai",
        reasoning_enabled=True,
        reasoning_effort="high",
        proxy_url="",
        no_proxy="",
        native_fallback_routes=[],
        rescue_enabled=True,
        rescue_repo_root=str(repo),
        rescue_config_root=str(config_root),
        rescue_fallback_model="deepseek-v4-flash",
        rescue_fallback_cli="codex",
        rescue_hot_fallback_enabled=True,
    )
    captured = {}

    def fake_chat_fallback(payload, model_name, gateway_url, gateway_key, _started_ms, route=None):
        captured.update({
            "payload": payload,
            "model_name": model_name,
            "gateway_url": gateway_url,
            "gateway_key": gateway_key,
            "route": route,
        })

    handler._do_chatcompletions_fallback = fake_chat_fallback
    handler.send_response = lambda code: captured.setdefault("status", code)
    handler.send_header = lambda *_args, **_kwargs: None
    handler.end_headers = lambda: None

    handler.do_POST()

    assert captured["model_name"] == "deepseek-v4-flash"
    assert captured["gateway_url"] == "https://deepseek.example/v1"
    assert captured["gateway_key"] == "sk-deepseek-test"
    assert captured["route"]["provider_id"] == "newapi-deepseek"
    latest_json = repo / ".mms" / "rescue" / "latest.json"
    assert latest_json.exists()
    latest = json.loads(latest_json.read_text(encoding="utf-8"))
    assert latest["safety"]["automatic_model_call"] is True
    assert latest["safety"]["global_oauth_fallback"] == "disabled"
    handover = json.loads((repo / ".mms" / "rescue" / "latest-fallback-handover.json").read_text(encoding="utf-8"))
    assert handover["fallback"]["model"] == "deepseek-v4-flash"
    assert handover["fallback"]["mode"] == "hot_fallback_attempt"
    assert handover["fallback"]["automatic_model_call"] is True
    assert handover["safety"]["global_oauth_fallback"] == "disabled"
    assert emitted_events
    assert emitted_events[0][0] == ("fallback", "deepseek-v4-flash")
    assert "rescue_hot_fallback" in emitted_events[0][1]["note"]


def test_responses_proxy_hot_fallback_prefers_anthropic_messages_for_deepseek(monkeypatch, tmp_path):
    import mms_bridge

    repo = tmp_path / "repo"
    config_root = tmp_path / "mms-config"
    (config_root / "generated").mkdir(parents=True)
    repo.mkdir()
    (config_root / "generated" / "model-routes.json").write_text(
        json.dumps(
            {
                "version": 1,
                "routes": {
                    "deepseek-v4-flash": {
                        "primary": {
                            "provider_id": "newapi-deepseek",
                            "anthropic_base_url": "https://deepseek.example",
                            "openai_base_url": "https://deepseek.example",
                            "api_key": "sk-deepseek-test",
                            "model_id": "deepseek-v4-flash",
                        },
                        "fallbacks": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    class FakeResponse:
        status_code = 524
        headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return b"upstream timeout"

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=lambda *_args, **_kwargs: FakeResponse()))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)

    raw_body = json.dumps({"model": "gpt-5.5", "input": "hi"}).encode()
    handler = mms_bridge._ResponsesProxyHandler.__new__(mms_bridge._ResponsesProxyHandler)
    handler.path = "/v1/responses"
    handler.headers = {
        "content-length": str(len(raw_body)),
        "authorization": "Bearer bridge-token",
    }
    handler.rfile = io.BytesIO(raw_body)
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        bridge_token="bridge-token",
        gateway_key="relay-key",
        gateway_url="https://relay.example/v1",
        model_name="gpt-5.5",
        advertised_models=["gpt-5.5"],
        speed_scope={},
        route_status_paths=[],
        provider_id="codex-relay",
        provider_profile="openai",
        reasoning_enabled=True,
        reasoning_effort="high",
        proxy_url="",
        no_proxy="",
        native_fallback_routes=[],
        rescue_enabled=True,
        rescue_repo_root=str(repo),
        rescue_config_root=str(config_root),
        rescue_fallback_model="deepseek-v4-flash",
        rescue_fallback_cli="codex",
        rescue_hot_fallback_enabled=True,
    )
    captured = {}

    def fake_anthropic_fallback(payload, model_name, gateway_url, gateway_key, _started_ms, route=None):
        captured.update({
            "payload": payload,
            "model_name": model_name,
            "gateway_url": gateway_url,
            "gateway_key": gateway_key,
            "route": route,
        })

    handler._do_anthropic_messages_fallback = fake_anthropic_fallback
    handler._do_chatcompletions_fallback = lambda *_args, **_kwargs: captured.setdefault("chat_called", True)
    handler.send_response = lambda code: captured.setdefault("status", code)
    handler.send_header = lambda *_args, **_kwargs: None
    handler.end_headers = lambda: None

    handler.do_POST()

    assert captured["model_name"] == "deepseek-v4-flash"
    assert captured["gateway_url"] == "https://deepseek.example"
    assert captured["gateway_key"] == "sk-deepseek-test"
    assert captured["route"]["provider_id"] == "newapi-deepseek"
    assert captured["route"]["protocol"] == "anthropic_messages"
    assert captured.get("chat_called") is None


def test_anthropic_messages_hot_fallback_posts_messages_endpoint(monkeypatch, tmp_path):
    import mms_bridge

    calls = []

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def iter_lines():
            return iter([
                b"event: message_start",
                b'data: {"type":"message_start","message":{"id":"msg_1","type":"message","role":"assistant","content":[],"model":"deepseek-v4-flash"}}',
                b"",
                b"event: content_block_start",
                b'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
                b"",
                b"event: content_block_delta",
                b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ok"}}',
                b"",
                b"event: content_block_stop",
                b'data: {"type":"content_block_stop","index":0}',
                b"",
                b"event: message_stop",
                b'data: {"type":"message_stop"}',
                b"",
            ])

    def fake_stream(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=fake_stream))
    handler = mms_bridge._ResponsesProxyHandler.__new__(mms_bridge._ResponsesProxyHandler)
    handler.headers = {"authorization": "Bearer bridge-token"}
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        speed_scope={},
        provider_id="codex-relay",
        provider_profile="openai",
        reasoning_enabled=True,
        reasoning_effort="high",
        proxy_url="",
        no_proxy="",
        route_status_paths=[],
        rescue_enabled=True,
        rescue_repo_root=str(tmp_path / "repo"),
        rescue_config_root=str(tmp_path / "config"),
    )
    captured = {"headers": []}
    handler.send_response = lambda code: captured.setdefault("status", code)
    handler.send_header = lambda *args, **_kwargs: captured["headers"].append(args)
    handler.end_headers = lambda: None

    handler._do_anthropic_messages_fallback(
        {"model": "deepseek-v4-flash", "instructions": "sys", "input": "hi", "max_output_tokens": 16},
        "deepseek-v4-flash",
        "https://deepseek.example",
        "sk-test",
        0,
        route={"provider_id": "newapi-deepseek", "protocol": "anthropic_messages"},
    )

    assert captured["status"] == 200
    assert calls[0][0] == "POST"
    assert calls[0][1] == "https://deepseek.example/v1/messages"
    assert calls[0][2]["headers"]["x-api-key"] == "sk-test"
    assert calls[0][2]["json"]["model"] == "deepseek-v4-flash"
    assert b"response.output_text.delta" in handler.wfile.getvalue()
    assert b"ok" in handler.wfile.getvalue()


def test_responses_proxy_hot_fallback_reads_current_rescue_config(monkeypatch, tmp_path):
    import mms_bridge

    repo = tmp_path / "repo"
    config_root = tmp_path / "mms-config"
    (config_root / "generated").mkdir(parents=True)
    repo.mkdir()
    (config_root / "config.toml").write_text(
        """
        [rescue]
        fallback_model = "deepseek-v4-flash"
        fallback_cli = "codex"
        hot_fallback_enabled = true
        """,
        encoding="utf-8",
    )
    (config_root / "generated" / "model-routes.json").write_text(
        json.dumps(
            {
                "version": 1,
                "routes": {
                    "deepseek-v4-flash": {
                        "primary": {
                            "provider_id": "newapi-deepseek",
                            "openai_base_url": "https://deepseek.example/v1",
                            "api_key": "sk-deepseek-test",
                            "model_id": "deepseek-v4-flash",
                        },
                        "fallbacks": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    class FakeResponse:
        status_code = 503
        headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return b'{"error":{"message":"auth_unavailable: no auth available"}}'

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=lambda *_args, **_kwargs: FakeResponse()))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)
    monkeypatch.delenv("MMS_RESCUE_FALLBACK_MODEL", raising=False)
    monkeypatch.delenv("MMS_RESCUE_FALLBACK_CLI", raising=False)

    raw_body = json.dumps({"model": "gpt-5.5", "input": "hi"}).encode()
    handler = mms_bridge._ResponsesProxyHandler.__new__(mms_bridge._ResponsesProxyHandler)
    handler.path = "/v1/responses"
    handler.headers = {
        "content-length": str(len(raw_body)),
        "authorization": "Bearer bridge-token",
    }
    handler.rfile = io.BytesIO(raw_body)
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        bridge_token="bridge-token",
        gateway_key="relay-key",
        gateway_url="https://relay.example/v1",
        model_name="gpt-5.5",
        advertised_models=["gpt-5.5"],
        speed_scope={},
        route_status_paths=[],
        provider_id="codex-relay",
        provider_profile="openai",
        reasoning_enabled=True,
        reasoning_effort="high",
        proxy_url="",
        no_proxy="",
        native_fallback_routes=[],
        rescue_enabled=True,
        rescue_repo_root=str(repo),
        rescue_config_root=str(config_root),
        rescue_fallback_model="",
        rescue_fallback_cli="",
        rescue_hot_fallback_enabled=False,
    )
    captured = {}

    def fake_chat_fallback(payload, model_name, gateway_url, gateway_key, _started_ms, route=None):
        captured.update({
            "payload": payload,
            "model_name": model_name,
            "gateway_url": gateway_url,
            "gateway_key": gateway_key,
            "route": route,
        })

    handler._do_chatcompletions_fallback = fake_chat_fallback
    handler.send_response = lambda code: captured.setdefault("status", code)
    handler.send_header = lambda *_args, **_kwargs: None
    handler.end_headers = lambda: None

    handler.do_POST()

    assert captured["model_name"] == "deepseek-v4-flash"
    assert captured["gateway_url"] == "https://deepseek.example/v1"
    assert captured["route"]["provider_id"] == "newapi-deepseek"
    assert handler.server.rescue_fallback_model == "deepseek-v4-flash"
    assert handler.server.rescue_fallback_cli == "codex"
    handover = json.loads((repo / ".mms" / "rescue" / "latest-fallback-handover.json").read_text(encoding="utf-8"))
    assert handover["fallback"]["automatic_model_call"] is True
    assert handover["safety"]["global_oauth_fallback"] == "disabled"


def test_rescue_global_fallback_without_hot_switch_records_handover_only(tmp_path):
    import mms_bridge

    repo = tmp_path / "repo"
    config_root = tmp_path / "mms-config"
    repo.mkdir()
    config_root.mkdir()
    (config_root / "config.toml").write_text(
        """
        [rescue]
        fallback_model = "deepseek-v4-flash"
        fallback_cli = "codex"
        """,
        encoding="utf-8",
    )
    server = types.SimpleNamespace(
        rescue_enabled=True,
        rescue_repo_root=str(repo),
        rescue_config_root=str(config_root),
        model_name="gpt-5.5",
        provider_id="codex-relay",
        rescue_fallback_model="",
        rescue_fallback_cli="",
        rescue_hot_fallback_enabled=False,
    )

    assert mms_bridge._rescue_hot_fallback_enabled(server) is False

    payload = mms_bridge._record_bridge_blocking_failure(
        server,
        model_name="gpt-5.5",
        provider_id="codex-relay",
        status_code=429,
        body_text='{"error":"rate limit"}',
        request_url="https://relay.example/v1/responses",
        bridge_surface="codex_responses_proxy",
    )

    assert payload is not None
    latest = json.loads((repo / ".mms" / "rescue" / "latest.json").read_text(encoding="utf-8"))
    assert latest["safety"]["automatic_model_call"] is False
    handover = json.loads((repo / ".mms" / "rescue" / "latest-fallback-handover.json").read_text(encoding="utf-8"))
    assert handover["fallback"]["model"] == "deepseek-v4-flash"
    assert handover["fallback"]["automatic_model_call"] is False
    assert handover["fallback"]["mode"] == "auto_default_handover"


def test_configure_bridge_rescue_reads_default_fallback_env(monkeypatch, tmp_path):
    import mms_bridge

    monkeypatch.setenv("MMS_PROJECT_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("MMS_RESCUE_CONFIG_ROOT", str(tmp_path / "config"))
    monkeypatch.setenv("MMS_RESCUE_FALLBACK_MODEL", "fallback-model")
    monkeypatch.setenv("MMS_RESCUE_FALLBACK_CLI", "codex")
    monkeypatch.setenv("MMS_RESCUE_HOT_FALLBACK", "1")

    server = types.SimpleNamespace()
    mms_bridge._configure_bridge_rescue(server)

    assert server.rescue_enabled is True
    assert server.rescue_repo_root == str(tmp_path / "repo")
    assert server.rescue_config_root == str(tmp_path / "config")
    assert server.rescue_fallback_model == "fallback-model"
    assert server.rescue_fallback_cli == "codex"
    assert server.rescue_hot_fallback_enabled is True
