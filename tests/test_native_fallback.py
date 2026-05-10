import io
import json
import types


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
    assert "invalid_text" in routes[0]["try_next_on"]


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
