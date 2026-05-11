from __future__ import annotations

import io
import json
import types


def _run_gateway_bridge_once(monkeypatch, incoming_model: str, *, heavy_model: str = "mimo-v2.5") -> dict:
    import mms_bridge

    captured: dict = {}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        content = b'{"type":"message","role":"assistant","model":"ok","content":[],"stop_reason":"end_turn"}'

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        captured["headers"] = kwargs.get("headers", {})
        return FakeResponse()

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(post=fake_post))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)
    monkeypatch.setattr(mms_bridge, "_record_bridge_speed", lambda *args, **kwargs: None)

    raw_body = json.dumps(
        {
            "model": incoming_model,
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
        }
    ).encode("utf-8")

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
        gateway_key="gateway-key",
        gateway_url="https://relay.example.com/v1",
        route_status_paths=[],
        advertised_models=[incoming_model],
        heavy_model=heavy_model,
        medium_model=None,
        light_model=None,
        slot_configs={},
        openai_url=None,
        speed_scope=None,
        proxy_url="",
        no_proxy="",
        provider_id="mimo-direct-anthropic",
        provider_profile="",
        reasoning_enabled=True,
        reasoning_effort="high",
        minimal_claude_header_passthrough=False,
        strip_upstream_user_agent=False,
    )
    handler.send_response = lambda code: captured.setdefault("status", code)
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda: None

    handler.do_POST()
    return captured


def test_gateway_bridge_rewrites_only_claude_shell_model(monkeypatch):
    captured = _run_gateway_bridge_once(monkeypatch, "claude-sonnet-4-6")

    assert captured["status"] == 200
    assert captured["json"]["model"] == "mimo-v2.5"


def test_gateway_bridge_preserves_explicit_non_claude_model_selection(monkeypatch):
    captured = _run_gateway_bridge_once(monkeypatch, "mimo-v2.5-pro")

    assert captured["status"] == 200
    assert captured["json"]["model"] == "mimo-v2.5-pro"


def test_gateway_bridge_maps_mimo_1m_selector_to_wire_model_and_beta(monkeypatch):
    captured = _run_gateway_bridge_once(monkeypatch, "mimo-v2.5-pro[1m]")

    assert captured["status"] == 200
    assert captured["json"]["model"] == "mimo-v2.5-pro"
    assert "context-1m-2025-08-07" in captured["headers"]["anthropic-beta"]


def test_gateway_bridge_maps_mimo_base_request_to_1m_selector_when_heavy_is_1m(monkeypatch):
    captured = _run_gateway_bridge_once(
        monkeypatch,
        "mimo-v2.5-pro",
        heavy_model="mimo-v2.5-pro[1m]",
    )

    assert captured["status"] == 200
    assert captured["json"]["model"] == "mimo-v2.5-pro"
    assert "context-1m-2025-08-07" in captured["headers"]["anthropic-beta"]
