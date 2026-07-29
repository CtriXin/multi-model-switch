import io
import json
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def test_responses_json_parse_error_uses_chatcompletions_fallback():
    import mms_bridge

    assert mms_bridge._should_try_chatcompletions_fallback(
        400,
        '{"error":{"message":"Request body must be valid JSON"}}',
    ) is True
    assert mms_bridge._should_try_chatcompletions_fallback(
        400,
        '{"error":{"message":"input is required"}}',
    ) is False
    assert mms_bridge._should_try_chatcompletions_fallback(
        422,
        '{"error":{"message":"Request body must be valid JSON"}}',
    ) is False


def test_chatcompletions_projection_keeps_codex_additional_tools():
    import mms_bridge

    tools, custom_tool_names = mms_bridge._responses_additional_tools_to_chat(
        [
            {
                "type": "additional_tools",
                "tools": [
                    {
                        "type": "custom",
                        "name": "exec",
                        "description": "Execute the host tool script.",
                    },
                    {
                        "type": "function",
                        "name": "wait",
                        "description": "Wait for a running command.",
                        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}},
                    },
                ],
            }
        ]
    )

    assert custom_tool_names == {"exec"}
    assert [tool["function"]["name"] for tool in tools] == ["exec", "wait"]
    assert tools[0]["function"]["parameters"] == {
        "type": "object",
        "properties": {"input": {"type": "string"}},
        "required": ["input"],
        "additionalProperties": False,
    }


def test_chatcompletions_translator_returns_codex_custom_tool_events():
    import mms_bridge

    translator = mms_bridge._ChatCompletionsToResponsesTranslator(
        "gpt-5.6-terra",
        custom_tool_names={"exec"},
    )
    events = translator.process_chunk(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_exec",
                                "function": {"name": "exec", "arguments": '{"input":"await tools.exec_command({cmd: \\"pwd\\"})"}'},
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
    )

    assert any(
        event_name == "response.custom_tool_call_input.delta"
        and payload["delta"] == 'await tools.exec_command({cmd: "pwd"})'
        for event_name, payload in events
    )
    assert any(
        event_name == "response.custom_tool_call_input.done"
        and payload["input"] == 'await tools.exec_command({cmd: "pwd"})'
        for event_name, payload in events
    )
    assert any(
        event_name == "response.output_item.done"
        and payload["item"]["type"] == "custom_tool_call"
        and payload["item"]["name"] == "exec"
        for event_name, payload in events
    )


def test_chatcompletions_translator_streams_decoded_custom_tool_input_chunks():
    import mms_bridge

    translator = mms_bridge._ChatCompletionsToResponsesTranslator(
        "gpt-5.6-terra",
        custom_tool_names={"exec"},
    )
    first_events = translator.process_chunk(
        {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": "call_exec",
                        "function": {"name": "exec", "arguments": '{"input":"printf \\u4f60'},
                    }],
                },
                "finish_reason": None,
            }]
        }
    )
    second_events = translator.process_chunk(
        {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "function": {"arguments": '\\u597d\\n\\"quoted\\""}'},
                    }],
                },
                "finish_reason": "tool_calls",
            }]
        }
    )

    events = first_events + second_events
    deltas = [payload["delta"] for event_name, payload in events if event_name == "response.custom_tool_call_input.delta"]
    assert "".join(deltas) == 'printf 你好\n"quoted"'
    assert any(
        event_name == "response.custom_tool_call_input.done"
        and payload["input"] == 'printf 你好\n"quoted"'
        for event_name, payload in events
    )


def test_responses_input_maps_custom_tool_history_to_chat_tool_messages():
    import mms_bridge

    messages = mms_bridge._responses_input_to_messages(
        "",
        [
            {"type": "custom_tool_call", "call_id": "call_exec", "name": "exec", "input": "await tools.exec_command({cmd: 'pwd'})"},
            {
                "type": "custom_tool_call_output",
                "call_id": "call_exec",
                "output": [{"type": "input_text", "text": "/tmp"}],
            },
        ],
    )

    assert messages == [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_exec",
                    "type": "function",
                    "function": {
                        "name": "exec",
                        "arguments": '{"input": "await tools.exec_command({cmd: \'pwd\'})"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_exec", "content": "/tmp"},
    ]


def test_resolve_native_fallback_routes_finds_same_vendor_direct():
    from mms_native_fallback import resolve_native_fallback_routes

    runtime = {
        "id": "newapi-personal-tokyo",
        "auth_mode": "api_key",
        "anthropic_base_url": "https://relay.example.com/anthropic",
        "api_key": "relay-key",
    }
    cfg = {
        "providers": [
            {
                "id": "newapi-personal-tokyo",
                "enabled": True,
                "protocols": ["anthropic_messages"],
                "default_anthropic_base_url": "https://relay.example.com/anthropic",
                "api_key": "relay-key",
                "extra_models": ["deepseek-v4-pro"],
            },
            {
                "id": "deepseek-direct",
                "enabled": True,
                "role": "fallback",
                "protocols": ["anthropic_messages", "openai_chat_completions"],
                "default_anthropic_base_url": "https://api.deepseek.com/anthropic",
                "default_openai_base_url": "https://api.deepseek.com",
                "api_key": "native-key",
                "extra_models": ["deepseek-v4-pro"],
            },
        ]
    }

    routes = resolve_native_fallback_routes(runtime, "deepseek-v4-pro", cfg=cfg)

    assert [route["provider_id"] for route in routes] == ["deepseek-direct"]
    assert routes[0]["gateway_url"] == "https://api.deepseek.com/anthropic/v1"
    assert routes[0]["gateway_key"] == "native-key"
    assert 403 in routes[0]["try_next_on"]
    assert 524 in routes[0]["try_next_on"]
    assert "invalid_text" in routes[0]["try_next_on"]


def test_native_fallback_skips_legacy_config_for_preview_root(monkeypatch, tmp_path):
    import mms_core
    from mms_native_fallback import resolve_native_fallback_routes

    monkeypatch.setenv("MMS_CONFIG_ROOT", str(tmp_path / "mms-next"))
    load_called = {"value": False}

    def fake_load_config():
        load_called["value"] = True
        return {
            "providers": [
                {
                    "id": "deepseek-direct",
                    "enabled": True,
                    "role": "fallback",
                    "protocols": ["anthropic_messages"],
                    "default_anthropic_base_url": "https://api.deepseek.com/anthropic",
                    "api_key": "native-key",
                    "extra_models": ["deepseek-v4-pro"],
                }
            ]
        }

    monkeypatch.setattr(mms_core, "load_config", fake_load_config)
    runtime = {
        "id": "newapi-personal-tokyo",
        "auth_mode": "api_key",
        "anthropic_base_url": "https://relay.example.com/anthropic",
        "api_key": "relay-key",
    }

    routes = resolve_native_fallback_routes(runtime, "deepseek-v4-pro")

    assert routes == []
    assert load_called["value"] is False


def test_resolve_native_fallback_routes_uses_anthropic_profile_for_mimo_relays(monkeypatch):
    import mms_native_fallback

    monkeypatch.setattr(
        mms_native_fallback,
        "_provider_context",
        lambda _cfg, provider_def: dict(provider_def),
    )

    runtime = {
        "id": "xin",
        "auth_mode": "api_key",
        "anthropic_base_url": "https://apple.clawopen.online",
        "openai_base_url": "https://apple.clawopen.online",
        "api_key": "relay-key",
    }
    cfg = {
        "providers": [
            {
                "id": "xin",
                "enabled": True,
                "protocols": ["anthropic_messages", "openai_chat_completions"],
                "default_anthropic_base_url": "https://apple.clawopen.online",
                "default_openai_base_url": "https://apple.clawopen.online",
                "api_key": "relay-key",
                "extra_models": ["mimo-v2.5", "mimo-v2.5-pro"],
            },
            {
                "id": "mimo-direct-anthropic",
                "enabled": True,
                "role": "fallback",
                "protocols": ["anthropic_messages"],
                "default_anthropic_base_url": "https://token-plan-cn.xiaomimimo.com/anthropic",
                "api_key": "native-key",
                "extra_models": ["mimo-v2.5", "mimo-v2.5-pro"],
            },
        ]
    }

    routes = mms_native_fallback.resolve_native_fallback_routes(runtime, "mimo-v2.5[1m]", cfg=cfg)

    assert [route["provider_id"] for route in routes] == ["mimo-direct-anthropic"]
    assert routes[0]["provider_profile"] == "mimo"
    assert routes[0]["gateway_url"] == "https://token-plan-cn.xiaomimimo.com/anthropic/v1"


def test_resolve_codex_responses_fallback_routes_finds_codex_provider(monkeypatch):
    import mms_native_fallback

    monkeypatch.setattr(
        mms_native_fallback,
        "_provider_context",
        lambda _cfg, provider_def: dict(provider_def),
    )

    runtime = {
        "id": "uscrsopenai",
        "auth_mode": "api_key",
        "openai_base_url": "https://openai.example.com/openai",
        "api_key": "relay-key",
    }
    cfg = {
        "providers": [
            {
                "id": "uscrsopenai",
                "enabled": True,
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["codex"],
                "default_openai_base_url": "https://openai.example.com/openai",
                "api_key": "relay-key",
                "extra_models": ["gpt-5.5"],
            },
            {
                "id": "us-cpa-local-codex",
                "enabled": True,
                "role": "fallback",
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["codex"],
                "default_openai_base_url": "https://codex.example.com/v1",
                "api_key": "native-key",
                "extra_models": ["gpt-5.5"],
            },
        ]
    }

    routes = mms_native_fallback.resolve_codex_responses_fallback_routes(runtime, "gpt-5.5", cfg=cfg)

    assert [route["provider_id"] for route in routes] == ["us-cpa-local-codex"]
    assert routes[0]["gateway_url"] == "https://codex.example.com/v1"
    assert routes[0]["gateway_key"] == "native-key"
    assert routes[0]["protocol"] == "responses"
    assert 403 in routes[0]["try_next_on"]
    assert 524 in routes[0]["try_next_on"]


def test_responses_proxy_retries_native_fallback_on_403(monkeypatch):
    import mms_bridge

    calls = []

    class FakeResponse:
        def __init__(self, status_code, body=b"", headers=None, lines=None):
            self.status_code = status_code
            self._body = body
            self.headers = headers or {"content-type": "application/json"}
            self._lines = lines or []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self._body

        def iter_lines(self):
            return iter(self._lines)

    def fake_stream(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if len(calls) == 1:
            return FakeResponse(403, b'{"error":{"message":"Permission denied"}}')
        return FakeResponse(
            200,
            headers={"content-type": "text/event-stream"},
            lines=[
                'event: response.created',
                'data: {"type":"response.created","response":{"id":"resp_1"}}',
                "",
            ],
        )

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=fake_stream))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)
    monkeypatch.setattr(mms_bridge, "_write_route_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_bridge, "_record_bridge_speed", lambda *args, **kwargs: None)

    raw_body = json.dumps({"model": "gpt-5.5", "input": "hi", "stream": True}).encode()
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
        gateway_url="https://openai.example.com/openai",
        model_name="gpt-5.5",
        advertised_models=["gpt-5.5"],
        speed_scope={},
        route_status_paths=[],
        provider_id="uscrsopenai",
        provider_profile="openai",
        reasoning_enabled=True,
        reasoning_effort="xhigh",
        proxy_url="",
        no_proxy="",
        native_fallback_routes=[{
            "provider_id": "us-cpa-local-codex",
            "provider_profile": "openai",
            "gateway_url": "https://codex.example.com/v1",
            "gateway_key": "native-key",
            "model": "gpt-5.5",
            "protocol": "responses",
            "proxy_url": "http://proxy.example:8080",
            "try_next_on": [403],
        }],
    )
    captured = {"statuses": []}
    handler.send_response = lambda code: captured["statuses"].append(code)
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda: None

    handler.do_POST()

    assert captured["statuses"] == [200]
    assert [item[1] for item in calls] == [
        "https://openai.example.com/openai/responses",
        "https://codex.example.com/v1/responses",
    ]
    assert calls[1][2]["headers"]["Authorization"] == "Bearer native-key"
    assert calls[1][2]["proxy"] == "http://proxy.example:8080"
    assert b"response.created" in handler.wfile.getvalue()


def test_responses_proxy_retries_native_fallback_on_cloudflare_524(monkeypatch):
    import mms_bridge

    calls = []

    class FakeResponse:
        def __init__(self, status_code, body=b"", headers=None, lines=None):
            self.status_code = status_code
            self._body = body
            self.headers = headers or {"content-type": "text/html"}
            self._lines = lines or []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self._body

        def iter_lines(self):
            return iter(self._lines)

    def fake_stream(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if len(calls) == 1:
            return FakeResponse(524, b"<title>524: A timeout occurred</title>")
        return FakeResponse(
            200,
            headers={"content-type": "text/event-stream"},
            lines=[
                'event: response.created',
                'data: {"type":"response.created","response":{"id":"resp_1"}}',
                "",
            ],
        )

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=fake_stream))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)
    monkeypatch.setattr(mms_bridge, "_write_route_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_bridge, "_record_bridge_speed", lambda *args, **kwargs: None)

    raw_body = json.dumps({"model": "gpt-5.5", "input": "hi", "stream": True}).encode()
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
        gateway_url="https://openai.example.com/openai",
        model_name="gpt-5.5",
        advertised_models=["gpt-5.5"],
        speed_scope={},
        route_status_paths=[],
        provider_id="uscrsopenai",
        provider_profile="openai",
        reasoning_enabled=True,
        reasoning_effort="xhigh",
        proxy_url="",
        no_proxy="",
        native_fallback_routes=[{
            "provider_id": "us-cpa-local-codex",
            "provider_profile": "openai",
            "gateway_url": "https://codex.example.com/v1",
            "gateway_key": "native-key",
            "model": "gpt-5.5",
            "protocol": "responses",
        }],
    )
    captured = {"statuses": []}
    handler.send_response = lambda code: captured["statuses"].append(code)
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda: None

    handler.do_POST()

    assert captured["statuses"] == [200]
    assert [item[1] for item in calls] == [
        "https://openai.example.com/openai/responses",
        "https://codex.example.com/v1/responses",
    ]
    assert b"response.created" in handler.wfile.getvalue()


def test_anthropic_bridge_mixed_protocol_fallback_uses_openai_responses(monkeypatch):
    import mms_bridge

    calls = []

    class FakeResponse:
        def __init__(self, status_code, body=b"", headers=None, lines=None):
            self.status_code = status_code
            self._body = body
            self.headers = headers or {"content-type": "application/json"}
            self._lines = lines or []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self._body

        def iter_lines(self):
            return iter(self._lines)

    def fake_stream(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if len(calls) == 1:
            return FakeResponse(403, b'{"error":{"message":"blocked"}}')
        return FakeResponse(
            200,
            headers={"content-type": "text/event-stream"},
            lines=[
                'event: response.created',
                'data: {"type":"response.created","response":{"id":"resp_gpt"}}',
                "",
            ],
        )

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=fake_stream))
    monkeypatch.setattr(mms_bridge, "_record_bridge_speed", lambda *args, **kwargs: None)

    handler = mms_bridge._ResponsesProxyHandler.__new__(mms_bridge._ResponsesProxyHandler)
    handler.headers = {}
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        provider_id="direct-qwen",
        provider_profile="",
        gateway_key="qwen-key",
        gateway_url="https://qwen.example/v1",
        speed_scope={},
        proxy_url="",
        no_proxy="",
        reasoning_enabled=True,
        reasoning_effort="medium",
        native_fallback_routes=[{
            "provider_id": "us-cpa-local-codex",
            "provider_profile": "openai",
            "gateway_url": "https://cpa.example/v1",
            "gateway_key": "gpt-key",
            "model": "gpt-5.5",
            "protocol": "openai_responses",
            "allow_model_switch": True,
            "try_next_on": [403],
        }],
    )
    captured = {"statuses": []}
    handler.send_response = lambda code: captured["statuses"].append(code)
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda: None

    handler._do_anthropic_messages_fallback(
        {"model": "qwen3.7-max", "input": "hi", "stream": True},
        "qwen3.7-max",
        "https://qwen.example/v1",
        "qwen-key",
        0,
        route={
            "provider_id": "direct-qwen",
            "provider_profile": "",
            "protocol": "anthropic_messages",
            "include_native_fallbacks": True,
            "try_next_on": [403],
        },
    )

    assert captured["statuses"] == [200]
    assert [item[1] for item in calls] == [
        "https://qwen.example/v1/messages",
        "https://cpa.example/v1/responses",
    ]
    assert calls[1][2]["json"]["model"] == "gpt-5.5"
    assert calls[1][2]["headers"]["Authorization"] == "Bearer gpt-key"
    assert b"response.created" in handler.wfile.getvalue()


def test_anthropic_bridge_chat_fallback_honors_try_next_on(monkeypatch):
    import mms_bridge

    calls = []

    class FakeResponse:
        def __init__(self, status_code, body=b"", headers=None, lines=None):
            self.status_code = status_code
            self._body = body
            self.headers = headers or {"content-type": "application/json"}
            self._lines = lines or []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self._body

        def iter_lines(self):
            return iter(self._lines)

    def fake_stream(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if len(calls) == 1:
            return FakeResponse(403, b'{"error":{"message":"primary blocked"}}')
        if len(calls) == 2:
            return FakeResponse(503, b'{"error":{"message":"chat unavailable"}}')
        return FakeResponse(
            200,
            headers={"content-type": "text/event-stream"},
            lines=[
                'event: response.created',
                'data: {"type":"response.created","response":{"id":"resp_after_chat"}}',
                "",
            ],
        )

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=fake_stream))
    monkeypatch.setattr(mms_bridge, "_record_bridge_speed", lambda *args, **kwargs: None)

    handler = mms_bridge._ResponsesProxyHandler.__new__(mms_bridge._ResponsesProxyHandler)
    handler.headers = {}
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        provider_id="direct-qwen",
        provider_profile="",
        gateway_key="qwen-key",
        gateway_url="https://qwen.example/v1",
        speed_scope={},
        proxy_url="",
        no_proxy="",
        reasoning_enabled=True,
        reasoning_effort="medium",
        native_fallback_routes=[
            {
                "provider_id": "newapi-chat",
                "provider_profile": "",
                "gateway_url": "https://chat.example/v1",
                "gateway_key": "chat-key",
                "model": "gpt-5.5",
                "protocol": "openai_chat_completions",
                "allow_model_switch": True,
                "try_next_on": [503],
            },
            {
                "provider_id": "us-cpa-local-codex",
                "provider_profile": "openai",
                "gateway_url": "https://responses.example/v1",
                "gateway_key": "responses-key",
                "model": "gpt-5.5",
                "protocol": "openai_responses",
                "allow_model_switch": True,
                "try_next_on": [503],
            },
        ],
    )
    captured = {"statuses": []}
    handler.send_response = lambda code: captured["statuses"].append(code)
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda: None

    handler._do_anthropic_messages_fallback(
        {"model": "qwen3.7-max", "input": "hi", "stream": True},
        "qwen3.7-max",
        "https://qwen.example/v1",
        "qwen-key",
        0,
        route={
            "provider_id": "direct-qwen",
            "provider_profile": "",
            "protocol": "anthropic_messages",
            "include_native_fallbacks": True,
            "try_next_on": [403],
        },
    )

    assert captured["statuses"] == [200]
    assert [item[1] for item in calls] == [
        "https://qwen.example/v1/messages",
        "https://chat.example/v1/chat/completions",
        "https://responses.example/v1/responses",
    ]
    assert calls[1][2]["json"]["model"] == "gpt-5.5"
    assert calls[1][2]["headers"]["Authorization"] == "Bearer chat-key"
    assert calls[2][2]["headers"]["Authorization"] == "Bearer responses-key"
    assert b"resp_after_chat" in handler.wfile.getvalue()


def test_anthropic_bridge_terminal_chat_fallback_retries_messages(monkeypatch):
    import mms_bridge

    calls = []

    class FakeResponse:
        def __init__(self, status_code, body=b"", headers=None, lines=None):
            self.status_code = status_code
            self._body = body
            self.headers = headers or {"content-type": "application/json"}
            self._lines = lines or []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self._body

        def iter_lines(self):
            return iter(self._lines)

    def fake_stream(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if len(calls) == 1:
            return FakeResponse(403, b'{"error":{"message":"primary blocked"}}')
        if len(calls) == 2:
            return FakeResponse(
                400,
                b'{"error":{"message":"prompt-cache sensitive route requires /v1/messages instead of /v1/chat/completions"}}',
            )
        return FakeResponse(
            200,
            headers={"content-type": "text/event-stream"},
            lines=[
                "event: message_start",
                'data: {"type":"message_start","message":{"id":"msg_1","type":"message","role":"assistant","content":[],"model":"gpt-5.5","stop_reason":null,"stop_sequence":null,"usage":{"input_tokens":1,"output_tokens":1}}}',
                "",
                "event: content_block_start",
                'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
                "",
                "event: content_block_delta",
                'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"resp_messages_retry"}}',
                "",
                "event: content_block_stop",
                'data: {"type":"content_block_stop","index":0}',
                "",
                "event: message_stop",
                'data: {"type":"message_stop"}',
                "",
            ],
        )

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=fake_stream))
    monkeypatch.setattr(mms_bridge, "_record_bridge_speed", lambda *args, **kwargs: None)

    handler = mms_bridge._ResponsesProxyHandler.__new__(mms_bridge._ResponsesProxyHandler)
    handler.headers = {}
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        provider_id="direct-qwen",
        provider_profile="",
        gateway_key="qwen-key",
        gateway_url="https://qwen.example/v1",
        speed_scope={},
        proxy_url="",
        no_proxy="",
        reasoning_enabled=True,
        reasoning_effort="medium",
        native_fallback_routes=[{
            "provider_id": "newapi-chat",
            "provider_profile": "",
            "gateway_url": "https://chat.example/v1",
            "gateway_key": "chat-key",
            "model": "gpt-5.5",
            "protocol": "openai_chat_completions",
            "allow_model_switch": True,
            "try_next_on": [503],
        }],
    )
    captured = {"statuses": []}
    handler.send_response = lambda code: captured["statuses"].append(code)
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda: None

    handler._do_anthropic_messages_fallback(
        {"model": "qwen3.7-max", "input": "hi", "stream": True},
        "qwen3.7-max",
        "https://qwen.example/v1",
        "qwen-key",
        0,
        route={
            "provider_id": "direct-qwen",
            "provider_profile": "",
            "protocol": "anthropic_messages",
            "include_native_fallbacks": True,
            "try_next_on": [403],
        },
    )

    assert captured["statuses"] == [200]
    assert [item[1] for item in calls] == [
        "https://qwen.example/v1/messages",
        "https://chat.example/v1/chat/completions",
        "https://chat.example/v1/messages",
    ]
    assert calls[1][2]["headers"]["Authorization"] == "Bearer chat-key"
    assert calls[2][2]["headers"]["x-api-key"] == "chat-key"
    assert b"resp_messages_retry" in handler.wfile.getvalue()


def test_responses_proxy_converts_terminal_403_to_fail_closed(monkeypatch):
    import mms_bridge

    monkeypatch.setenv("MMS_LANG", "zh")

    class FakeResponse:
        status_code = 403
        headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return b'{"error":{"message":"Permission denied"}}'

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
        gateway_url="https://openai.example.com/openai",
        model_name="gpt-5.5",
        advertised_models=["gpt-5.5"],
        speed_scope={},
        route_status_paths=[],
        provider_id="uscrsopenai",
        provider_profile="openai",
        reasoning_enabled=True,
        reasoning_effort="xhigh",
        proxy_url="",
        no_proxy="",
        native_fallback_routes=[],
    )
    captured = {}
    handler.send_response = lambda code: captured.setdefault("status", code)
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda: None

    handler.do_POST()

    assert captured["status"] == 502
    payload = json.loads(handler.wfile.getvalue().decode())
    assert "MMS fail-closed" in payload["error"]["message"]
    assert "HTTP 403" in payload["error"]["message"]
    assert "provider_or_model_permission" in payload["error"]["message"]
    assert payload["error"]["mms"]["source"] == "upstream_provider"
    assert payload["error"]["mms"]["provider_id"] == "uscrsopenai"
    assert payload["error"]["mms"]["model"] == "gpt-5.5"
    assert payload["error"]["mms"]["request_path"] == "/openai/responses"
    assert payload["error"]["upstream"]["message"] == "Permission denied"


def test_fail_closed_auth_error_payload_keeps_diagnosis_and_upstream_detail(monkeypatch):
    import mms_bridge

    monkeypatch.setenv("MMS_LANG", "zh")

    payload = mms_bridge._mms_fail_closed_auth_error_payload(
        401,
        '{"error":{"type":"invalid_api_key","message":"bad key","request_id":"req-auth"}}',
        model_name="gpt-5.5",
        provider_id="codex-relay",
        request_url="https://relay.example.com/v1/responses",
        route_count=2,
    )

    message = payload["error"]["message"]
    assert "provider_authentication" in message
    assert "provider=codex-relay" in message
    assert "routes_tried=2" in message
    assert "没有使用 global OAuth 或 login fallback" in message
    assert payload["error"]["type"] == "mms_upstream_auth_error"
    assert payload["error"]["mms"] == {
        "source": "upstream_provider",
        "category": "provider_authentication",
        "status_code": 401,
        "model": "gpt-5.5",
        "provider_id": "codex-relay",
        "request_path": "/v1/responses",
        "routes_tried": 2,
        "global_oauth_fallback": "disabled",
        "next": "检查当前 provider 的 API key/account 绑定，或在 MMS 中切换 runtime",
    }
    assert payload["error"]["upstream"]["type"] == "invalid_api_key"
    assert payload["error"]["upstream"]["message"] == "bad key"
    assert payload["error"]["upstream"]["request_id"] == "req-auth"


def test_fail_closed_auth_error_payload_uses_english_when_mms_lang_en(monkeypatch):
    import mms_i18n
    import mms_bridge

    monkeypatch.delenv("MMS_LANG", raising=False)
    mms_i18n.set_language("en")

    try:
        payload = mms_bridge._mms_fail_closed_auth_error_payload(
            403,
            '{"error":{"message":"Permission denied","request_id":"req-en"}}',
            model_name="gpt-5.5",
            provider_id="codex-relay",
            request_url="https://relay.example.com/v1/responses",
        )
    finally:
        mms_i18n.set_language("zh")

    message = payload["error"]["message"]
    assert "upstream_provider returned HTTP 403" in message
    assert "Meaning: the selected MMS provider/account reached upstream" in message
    assert "global OAuth or login fallback was not used" in message
    assert "Upstream said: Permission denied" in message
    assert "上游 provider 返回" not in message
    assert payload["error"]["mms"]["category"] == "provider_or_model_permission"
    assert payload["error"]["mms"]["next"] == (
        "check provider model permission, relay policy, quota, or switch runtime in MMS"
    )
    assert payload["error"]["upstream"]["request_id"] == "req-en"


def test_chatcompletions_fallback_uses_native_route_profile_and_proxy(monkeypatch):
    import mms_bridge

    class FakeResponse:
        status_code = 429
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return b"rate limited"

        @staticmethod
        def iter_lines():
            return iter(())

    calls = []
    profile_calls = []

    def fake_stream(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse()

    def fake_body_patch(_payload, **kwargs):
        profile_calls.append(("body", kwargs))
        return kwargs.get("profile_id")

    def fake_auth_headers(_headers, **kwargs):
        profile_calls.append(("auth", kwargs))

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=fake_stream))
    monkeypatch.setattr(
        mms_bridge,
        "_build_gateway_candidate_urls",
        lambda *_args, **_kwargs: ["https://codex.example.com/v1/chat/completions"],
    )
    monkeypatch.setattr(mms_bridge, "apply_profile_body_patches", fake_body_patch)
    monkeypatch.setattr(mms_bridge, "apply_profile_auth_headers", fake_auth_headers)

    handler = mms_bridge._ResponsesProxyHandler.__new__(mms_bridge._ResponsesProxyHandler)
    handler.headers = {}
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        provider_id="primary-provider",
        provider_profile="primary-profile",
        proxy_url="",
        no_proxy="",
        speed_scope=None,
    )
    captured = {}
    handler.send_response = lambda code: captured.setdefault("status", code)
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda: None

    route = {
        "provider_id": "fallback-provider",
        "provider_profile": "fallback-profile",
        "proxy_url": "http://proxy.example:8080",
        "no_proxy": "",
    }
    handler._do_chatcompletions_fallback(
        {"input": [], "instructions": ""},
        "gpt-5.5",
        "https://codex.example.com/v1",
        "native-key",
        0,
        route=route,
    )

    assert captured["status"] == 429
    assert calls[0][1] == "https://codex.example.com/v1/chat/completions"
    assert calls[0][2]["proxy"] == "http://proxy.example:8080"
    assert {item[0] for item in profile_calls} == {"body", "auth"}
    assert all(call[1]["provider_id"] == "fallback-provider" for call in profile_calls)
    assert all(call[1]["profile_id"] == "fallback-profile" for call in profile_calls)


def test_gateway_bridge_retries_native_fallback_before_responding(monkeypatch):
    import mms_bridge

    calls = []

    class FakeResponse:
        def __init__(self, status_code, content):
            self.status_code = status_code
            self.content = content
            self.headers = {"content-type": "application/json"}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if len(calls) == 1:
            return FakeResponse(403, b"<html>forbidden</html>")
        return FakeResponse(
            200,
            json.dumps({
                "id": "msg_ok",
                "type": "message",
                "role": "assistant",
                "model": "deepseek-v4-pro[1m]",
                "content": [{"type": "text", "text": "pong"}],
                "stop_reason": "end_turn",
            }).encode(),
        )

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(post=fake_post))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)
    monkeypatch.setattr(mms_bridge, "_write_route_status", lambda *args, **kwargs: None)

    raw_body = json.dumps({
        "model": "deepseek-v4-pro",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
    }).encode()

    handler = mms_bridge._GatewayBridgeHandler.__new__(mms_bridge._GatewayBridgeHandler)
    handler.path = "/v1/messages"
    handler.headers = {
        "content-length": str(len(raw_body)),
        "x-api-key": "bridge-token",
    }
    handler.rfile = io.BytesIO(raw_body)
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        bridge_token="bridge-token",
        gateway_key="relay-key",
        gateway_url="https://relay.example.com/anthropic/v1",
        route_status_paths=[],
        advertised_models=["deepseek-v4-pro"],
        heavy_model="deepseek-v4-pro",
        medium_model=None,
        light_model=None,
        slot_configs={},
        openai_url=None,
        speed_scope=None,
        provider_id="newapi-personal-tokyo",
        provider_profile="",
        proxy_url="",
        no_proxy="",
        reasoning_enabled=True,
        reasoning_effort="xhigh",
        native_fallback_routes=[{
            "provider_id": "deepseek-direct",
            "provider_profile": "deepseek",
            "gateway_url": "https://api.deepseek.com/anthropic/v1",
            "gateway_key": "native-key",
            "model": "deepseek-v4-pro",
            "fallback_reason": "same_vendor_native_direct",
            "try_next_on": [403, "invalid_json", "invalid_text"],
        }],
    )
    captured = {}
    handler.send_response = lambda code: captured.setdefault("status", code)
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda: None

    handler.do_POST()

    assert captured["status"] == 200
    assert [item[0] for item in calls] == [
        "https://relay.example.com/anthropic/v1/messages",
        "https://api.deepseek.com/anthropic/v1/messages",
    ]
    assert calls[1][1]["headers"]["x-api-key"] == "native-key"
    assert calls[1][1]["json"]["model"] == "deepseek-v4-pro[1m]"
    assert b"pong" in handler.wfile.getvalue()


def test_gateway_bridge_does_not_fallback_after_stream_response_started(monkeypatch):
    import mms_bridge

    calls = []

    class FakeStreamResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def iter_lines(self):
            yield 'data: {"type":"message_start"}'
            raise RuntimeError("connection reset by peer")

    def fake_stream(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeStreamResponse()

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(stream=fake_stream))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)
    monkeypatch.setattr(mms_bridge, "_write_route_status", lambda *args, **kwargs: None)

    raw_body = json.dumps({
        "model": "deepseek-v4-pro",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }).encode()

    handler = mms_bridge._GatewayBridgeHandler.__new__(mms_bridge._GatewayBridgeHandler)
    handler.path = "/v1/messages"
    handler.headers = {
        "content-length": str(len(raw_body)),
        "x-api-key": "bridge-token",
    }
    handler.rfile = io.BytesIO(raw_body)
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        bridge_token="bridge-token",
        gateway_key="relay-key",
        gateway_url="https://relay.example.com/anthropic/v1",
        route_status_paths=[],
        advertised_models=["deepseek-v4-pro"],
        heavy_model="deepseek-v4-pro",
        medium_model=None,
        light_model=None,
        slot_configs={},
        openai_url=None,
        speed_scope=None,
        provider_id="newapi-personal-tokyo",
        provider_profile="",
        proxy_url="",
        no_proxy="",
        reasoning_enabled=True,
        reasoning_effort="xhigh",
        native_fallback_routes=[{
            "provider_id": "deepseek-direct",
            "provider_profile": "deepseek",
            "gateway_url": "https://api.deepseek.com/anthropic/v1",
            "gateway_key": "native-key",
            "model": "deepseek-v4-pro",
            "fallback_reason": "same_vendor_native_direct",
            "try_next_on": ["connect_error"],
        }],
    )
    captured = {"statuses": []}
    handler.send_response = lambda code: captured["statuses"].append(code)
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda: None

    handler.do_POST()

    assert captured["statuses"] == [200]
    assert [item[1] for item in calls] == ["https://relay.example.com/anthropic/v1/messages"]
    assert b"message_start" in handler.wfile.getvalue()


def test_gateway_bridge_does_not_fallback_on_local_programming_error(monkeypatch):
    import mms_bridge

    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        raise RuntimeError("local patch bug")

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(post=fake_post))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)
    monkeypatch.setattr(mms_bridge, "_write_route_status", lambda *args, **kwargs: None)

    raw_body = json.dumps({
        "model": "deepseek-v4-pro",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
    }).encode()

    handler = mms_bridge._GatewayBridgeHandler.__new__(mms_bridge._GatewayBridgeHandler)
    handler.path = "/v1/messages"
    handler.headers = {
        "content-length": str(len(raw_body)),
        "x-api-key": "bridge-token",
    }
    handler.rfile = io.BytesIO(raw_body)
    handler.wfile = io.BytesIO()
    handler.server = types.SimpleNamespace(
        bridge_token="bridge-token",
        gateway_key="relay-key",
        gateway_url="https://relay.example.com/anthropic/v1",
        route_status_paths=[],
        advertised_models=["deepseek-v4-pro"],
        heavy_model="deepseek-v4-pro",
        medium_model=None,
        light_model=None,
        slot_configs={},
        openai_url=None,
        speed_scope=None,
        provider_id="newapi-personal-tokyo",
        provider_profile="",
        proxy_url="",
        no_proxy="",
        reasoning_enabled=True,
        reasoning_effort="xhigh",
        native_fallback_routes=[{
            "provider_id": "deepseek-direct",
            "provider_profile": "deepseek",
            "gateway_url": "https://api.deepseek.com/anthropic/v1",
            "gateway_key": "native-key",
            "model": "deepseek-v4-pro",
            "fallback_reason": "same_vendor_native_direct",
            "try_next_on": ["connect_error"],
        }],
    )
    captured = {}
    handler.send_response = lambda code: captured.setdefault("status", code)
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda: None

    handler.do_POST()

    assert captured["status"] == 502
    assert [item[0] for item in calls] == ["https://relay.example.com/anthropic/v1/messages"]
    assert b"local patch bug" in handler.wfile.getvalue()


def test_gateway_claude_bridge_stores_native_fallback_routes(monkeypatch):
    import mms_bridge

    calls = {"closed": 0}

    class FakeServer:
        def __init__(self, addr, handler):
            self.server_address = ("127.0.0.1", 54322)

        def serve_forever(self):
            return None

        def server_close(self):
            calls["closed"] += 1

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            self.target = target
            self.daemon = daemon

        def start(self):
            return None

        def join(self, timeout=None):
            return None

    monkeypatch.setattr(mms_bridge, "_SilentHTTPServer", FakeServer)
    monkeypatch.setattr(mms_bridge.threading, "Thread", FakeThread)
    monkeypatch.setattr(mms_bridge, "_wait_local_server_ready", lambda *_args, **_kwargs: True)

    routes = [{"provider_id": "deepseek-direct", "gateway_url": "https://api.deepseek.com/anthropic/v1"}]
    with mms_bridge.gateway_claude_bridge(
        "https://relay.example.com/v1",
        "relay-key",
        native_fallback_routes=routes,
    ) as bridge_cfg:
        assert bridge_cfg["_server"].native_fallback_routes == routes

    assert calls["closed"] == 1
