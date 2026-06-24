from __future__ import annotations

import io
import json
import types


def _run_gateway_bridge_once(
    monkeypatch,
    incoming_model: str,
    *,
    heavy_model: str = "mimo-v2.5",
    context_windows: dict[str, int] | None = None,
    session_context_window: int | None = None,
    messages: list[dict] | None = None,
    system: str | list[dict] | None = None,
    vision_sidecar: dict | None = None,
    model_capabilities: dict | None = None,
    force_heavy_model: bool = False,
) -> dict:
    import mms_bridge

    captured: dict = {}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        content = b'{"type":"message","role":"assistant","model":"ok","content":[],"stop_reason":"end_turn"}'

    def fake_post(url, **kwargs):
        captured.setdefault("post_calls", []).append({"url": url, **kwargs})
        captured["post_called"] = True
        if "vision.example.com" in url:
            class VisionResponse:
                status_code = 200
                headers = {"content-type": "application/json"}
                content = b'{"type":"message","role":"assistant","content":[{"type":"text","text":"red square"}],"stop_reason":"end_turn"}'

            return VisionResponse()
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        captured["headers"] = kwargs.get("headers", {})
        return FakeResponse()

    monkeypatch.setattr(mms_bridge, "httpx", types.SimpleNamespace(post=fake_post))
    monkeypatch.setattr(mms_bridge, "_ensure_httpx", lambda: mms_bridge.httpx)
    monkeypatch.setattr(mms_bridge, "_record_bridge_speed", lambda *args, **kwargs: None)

    payload = {
        "model": incoming_model,
        "messages": messages or [{"role": "user", "content": "ping"}],
        "stream": False,
    }
    if system is not None:
        payload["system"] = system
    raw_body = json.dumps(payload).encode("utf-8")

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
        context_windows=context_windows or {},
        session_context_window=session_context_window,
        reasoning_enabled=True,
        reasoning_effort="high",
        minimal_claude_header_passthrough=False,
        strip_upstream_user_agent=False,
        vision_sidecar=vision_sidecar or {},
        model_capabilities=model_capabilities or {},
        force_heavy_model=force_heavy_model,
    )
    handler.send_response = lambda code: captured.setdefault("status", code)
    handler.send_header = lambda *args, **kwargs: None
    handler.end_headers = lambda: None

    handler.do_POST()
    captured["body"] = handler.wfile.getvalue()
    return captured


def test_gateway_bridge_rewrites_only_claude_shell_model(monkeypatch):
    captured = _run_gateway_bridge_once(monkeypatch, "claude-sonnet-4-6")

    assert captured["status"] == 200
    assert captured["json"]["model"] == "mimo-v2.5"


def test_gateway_bridge_preserves_explicit_non_claude_model_selection(monkeypatch):
    captured = _run_gateway_bridge_once(monkeypatch, "mimo-v2.5-pro")

    assert captured["status"] == 200
    assert captured["json"]["model"] == "mimo-v2.5-pro"


def test_gateway_bridge_force_heavy_model_overrides_any_incoming_model(monkeypatch):
    captured = _run_gateway_bridge_once(
        monkeypatch,
        "mimo-v2.5-pro",
        heavy_model="qwen3.7-max",
        force_heavy_model=True,
    )

    assert captured["status"] == 200
    assert captured["json"]["model"] == "qwen3.7-max"


def test_gateway_bridge_strips_claude_code_billing_system_cache_buster(monkeypatch):
    captured = _run_gateway_bridge_once(
        monkeypatch,
        "mimo-v2.5-pro",
        system=(
            "x-anthropic-billing-header: cch=abc12\n"
            "You are Claude Code.\n"
            "Keep this instruction."
        ),
    )

    assert captured["status"] == 200
    assert "x-anthropic-billing-header" not in captured["json"]["system"].lower()
    assert "Keep this instruction." in captured["json"]["system"]


def test_gateway_bridge_maps_mimo_1m_selector_to_wire_model_and_beta(monkeypatch):
    captured = _run_gateway_bridge_once(monkeypatch, "mimo-v2.5-pro[1m]")

    assert captured["status"] == 200
    assert captured["json"]["model"] == "mimo-v2.5-pro"
    assert "context-1m-2025-08-07" in captured["headers"]["anthropic-beta"]


def test_gateway_bridge_maps_mimo_non_pro_1m_selector_to_wire_model_and_beta(monkeypatch):
    captured = _run_gateway_bridge_once(monkeypatch, "mimo-v2.5[1m]")

    assert captured["status"] == 200
    assert captured["json"]["model"] == "mimo-v2.5"
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


def test_gateway_bridge_maps_mimo_non_pro_base_request_to_1m_selector_when_heavy_is_1m(monkeypatch):
    captured = _run_gateway_bridge_once(
        monkeypatch,
        "mimo-v2.5",
        heavy_model="mimo-v2.5[1m]",
    )

    assert captured["status"] == 200
    assert captured["json"]["model"] == "mimo-v2.5"
    assert "context-1m-2025-08-07" in captured["headers"]["anthropic-beta"]


def test_gateway_bridge_uses_configured_mimo_context_for_beta(monkeypatch):
    captured = _run_gateway_bridge_once(
        monkeypatch,
        "claude-sonnet-4-6",
        heavy_model="mimo-v2.5",
        context_windows={"mimo-v2.5": 1_000_000},
        session_context_window=1_000_000,
    )

    assert captured["status"] == 200
    assert captured["json"]["model"] == "mimo-v2.5"
    assert "context-1m-2025-08-07" in captured["headers"]["anthropic-beta"]


def test_gateway_bridge_rejects_known_text_only_model_image_input_before_upstream(monkeypatch):
    image_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what color"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "iVBORw0KGgo=",
                    },
                },
            ],
        }
    ]

    captured = _run_gateway_bridge_once(
        monkeypatch,
        "claude-sonnet-4-6",
        heavy_model="mimo-v2.5-pro[1m]",
        messages=image_messages,
    )
    body = json.loads(captured["body"].decode("utf-8"))

    assert captured["status"] == 400
    assert captured.get("post_called") is not True
    assert "does not support image input" in body["error"]["message"]
    assert "gpt-5.4" in body["error"]["message"]


def test_gateway_bridge_allows_mimo_v25_image_input(monkeypatch):
    image_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what color"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "iVBORw0KGgo=",
                    },
                },
            ],
        }
    ]

    captured = _run_gateway_bridge_once(
        monkeypatch,
        "claude-sonnet-4-6",
        heavy_model="mimo-v2.5",
        messages=image_messages,
    )

    assert captured["status"] == 200
    assert captured["json"]["model"] == "mimo-v2.5"
    assert captured.get("post_called") is True


def test_gateway_bridge_allows_known_qwen_vision_model_image_input(monkeypatch):
    image_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what color"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "iVBORw0KGgo=",
                    },
                },
            ],
        }
    ]

    captured = _run_gateway_bridge_once(
        monkeypatch,
        "claude-sonnet-4-6",
        heavy_model="qwen3.6-flash",
        messages=image_messages,
    )

    assert captured["status"] == 200
    assert captured["json"]["model"] == "qwen3.6-flash"
    assert captured.get("post_called") is True


def test_gateway_bridge_treats_new_unknown_model_as_text_only(monkeypatch):
    image_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what color"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "iVBORw0KGgo=",
                    },
                },
            ],
        }
    ]

    captured = _run_gateway_bridge_once(
        monkeypatch,
        "claude-sonnet-4-6",
        heavy_model="qwen3.7-max",
        messages=image_messages,
    )
    body = json.loads(captured["body"].decode("utf-8"))

    assert captured["status"] == 400
    assert captured.get("post_called") is not True
    assert "qwen3.7-max does not support image input" in body["error"]["message"]


def test_gateway_bridge_uses_vision_sidecar_for_text_only_model_image_input(monkeypatch):
    image_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what color"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "iVBORw0KGgo=",
                    },
                },
            ],
        }
    ]

    captured = _run_gateway_bridge_once(
        monkeypatch,
        "claude-sonnet-4-6",
        heavy_model="mimo-v2.5-pro[1m]",
        messages=image_messages,
        vision_sidecar={
            "enabled": True,
            "provider_id": "direct-kimi",
            "provider_profile": "kimi-code",
            "model": "K2.6",
            "anthropic_base_url": "https://vision.example.com",
            "api_key": "sk-vision",
        },
    )

    assert captured["status"] == 200
    assert len(captured["post_calls"]) == 2
    assert captured["post_calls"][0]["json"]["model"] == "K2.6"
    assert captured["json"]["model"] == "mimo-v2.5-pro"
    assert "red square" in json.dumps(captured["json"], ensure_ascii=False)
    assert not any(
        isinstance(block, dict) and block.get("type") == "image"
        for message in captured["json"]["messages"]
        for block in (message.get("content") if isinstance(message.get("content"), list) else [])
    )


def test_gateway_bridge_strips_stale_vision_sidecar_history_from_follow_up_turn(monkeypatch):
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "请描述图片"},
                {"type": "text", "text": "[MMS removed image input; see vision sidecar summary appended to this request.]"},
                {
                    "type": "text",
                    "text": (
                        "\n\n[MMS vision sidecar by K2.6]\n"
                        "当前主模型不支持 image input；MMS 已先用 vision sidecar 读取用户图片。\n"
                        "图片内容如下：\n"
                        "一只红色方块"
                    ),
                },
            ],
        },
        {"role": "assistant", "content": [{"type": "text", "text": "这是一个红色方块。"}]},
        {"role": "user", "content": [{"type": "text", "text": "它大概是什么材质？"}]},
    ]

    captured = _run_gateway_bridge_once(
        monkeypatch,
        "claude-sonnet-4-6",
        heavy_model="mimo-v2.5-pro[1m]",
        messages=messages,
    )

    assert captured["status"] == 200
    forwarded_messages = captured["json"]["messages"]
    assert forwarded_messages[0]["content"] == [{"type": "text", "text": "请描述图片"}]
    forwarded_dump = json.dumps(forwarded_messages, ensure_ascii=False)
    assert "[MMS vision sidecar by" not in forwarded_dump
    assert "MMS removed image input" not in forwarded_dump
    assert "一只红色方块" not in forwarded_dump


def test_gateway_bridge_does_not_reprocess_historical_image_on_follow_up_no_image_turn(monkeypatch):
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "请描述这张图"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "iVBORw0KGgo=",
                    },
                },
            ],
        },
        {"role": "assistant", "content": [{"type": "text", "text": "这是一个红色方块。"}]},
        {"role": "user", "content": [{"type": "text", "text": "顺便帮我写个标题"}]},
    ]

    captured = _run_gateway_bridge_once(
        monkeypatch,
        "claude-sonnet-4-6",
        heavy_model="mimo-v2.5-pro[1m]",
        messages=messages,
        vision_sidecar={
            "enabled": True,
            "provider_id": "direct-kimi",
            "provider_profile": "kimi-code",
            "model": "K2.6",
            "anthropic_base_url": "https://vision.example.com",
            "api_key": "sk-vision",
        },
    )

    assert captured["status"] == 200
    assert len(captured["post_calls"]) == 1
    forwarded_dump = json.dumps(captured["json"]["messages"], ensure_ascii=False)
    assert "[MMS vision sidecar by" not in forwarded_dump
    assert "MMS removed image input" not in forwarded_dump
    assert '"type": "image"' not in forwarded_dump
    assert "请描述这张图" in forwarded_dump
    assert "顺便帮我写个标题" in forwarded_dump


def test_gateway_bridge_honors_ui_vision_capability_without_sidecar(monkeypatch):
    image_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what color"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "iVBORw0KGgo=",
                    },
                },
            ],
        }
    ]

    captured = _run_gateway_bridge_once(
        monkeypatch,
        "claude-sonnet-4-6",
        heavy_model="MiniMax-M3",
        messages=image_messages,
        vision_sidecar={
            "enabled": True,
            "provider_id": "direct-kimi",
            "provider_profile": "kimi-code",
            "model": "K2.6",
            "anthropic_base_url": "https://vision.example.com",
            "api_key": "sk-vision",
        },
        model_capabilities={"MiniMax-M3": {"vision": True}},
    )

    assert captured["status"] == 200
    assert len(captured["post_calls"]) == 1
    assert captured["json"]["model"] == "MiniMax-M3"
    assert any(
        isinstance(block, dict) and block.get("type") == "image"
        for message in captured["json"]["messages"]
        for block in (message.get("content") if isinstance(message.get("content"), list) else [])
    )


def test_gateway_bridge_uses_vision_sidecar_for_nested_tool_result_image(monkeypatch):
    image_messages = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "screenshot",
                    "input": {},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": "iVBORw0KGgo=",
                            },
                        }
                    ],
                },
                {"type": "text", "text": "what changed?"},
            ],
        },
    ]

    captured = _run_gateway_bridge_once(
        monkeypatch,
        "claude-sonnet-4-6",
        heavy_model="mimo-v2.5-pro[1m]",
        messages=image_messages,
        vision_sidecar={
            "enabled": True,
            "provider_id": "direct-kimi",
            "provider_profile": "kimi-code",
            "model": "K2.6",
            "anthropic_base_url": "https://vision.example.com",
            "api_key": "sk-vision",
        },
    )

    assert captured["status"] == 200
    assert len(captured["post_calls"]) == 2
    sidecar_json = captured["post_calls"][0]["json"]
    assert any(block.get("type") == "image" for block in sidecar_json["messages"][0]["content"])
    forwarded = json.dumps(captured["json"]["messages"], ensure_ascii=False)
    assert '"type": "image"' not in forwarded
    assert "red square" in forwarded
