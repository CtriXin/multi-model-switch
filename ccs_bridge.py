import json
import os
import socket
import subprocess
import threading
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import httpx
except ImportError:
    httpx = None


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
GEMINI_BRIDGE_SCRIPT = os.path.join(ROOT_DIR, "scripts", "gemini_codeassist_bridge.mjs")


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock.getsockname()[1]


def _load_codex_auth(account):
    home_dir = os.path.expanduser(str(account.get("home_dir", "")).strip())
    auth_path = os.path.join(home_dir, ".codex", "auth.json")
    with open(auth_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def _load_codex_client_version(account):
    home_dir = os.path.expanduser(str(account.get("home_dir", "")).strip())
    cache_path = os.path.join(home_dir, ".codex", "models_cache.json")
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("client_version") or "0.114.0")
    except Exception:
        return "0.114.0"


def _system_to_instructions(system_value):
    if isinstance(system_value, str):
        return system_value.strip()
    if isinstance(system_value, list):
        parts = []
        for item in system_value:
            if isinstance(item, str):
                parts.append(item.strip())
                continue
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"].strip())
        return "\n\n".join(part for part in parts if part)
    return ""


def _normalize_message_content(content):
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [item for item in content if isinstance(item, dict)]
    return []


def _tool_result_text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return json.dumps(content, ensure_ascii=False)
    parts = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts)


def _content_block_to_responses(block):
    block_type = block.get("type")
    if block_type == "text":
        return {"type": "input_text", "text": str(block.get("text", ""))}
    if block_type == "image":
        source = block.get("source", {})
        if source.get("type") == "base64":
            media_type = source.get("media_type", "image/png")
            data = source.get("data", "")
            return {"type": "input_image", "image_url": f"data:{media_type};base64,{data}"}
    return None


def _anthropic_messages_to_responses_input(messages):
    items = []
    for message in messages:
        role = str(message.get("role", "user"))
        text_parts = []

        def flush_text_parts():
            if text_parts:
                items.append({"role": role, "content": list(text_parts)})
                text_parts.clear()

        for block in _normalize_message_content(message.get("content")):
            block_type = block.get("type")
            if block_type in {"text", "image"}:
                converted = _content_block_to_responses(block)
                if converted is not None:
                    text_parts.append(converted)
                continue
            if block_type == "tool_use":
                flush_text_parts()
                items.append({
                    "type": "function_call",
                    "call_id": str(block.get("id", "")),
                    "name": str(block.get("name", "")),
                    "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                })
                continue
            if block_type == "tool_result":
                flush_text_parts()
                items.append({
                    "type": "function_call_output",
                    "call_id": str(block.get("tool_use_id", "")),
                    "output": _tool_result_text(block.get("content")),
                })
        flush_text_parts()
    return items


def _anthropic_tools_to_responses(tools):
    converted = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        converted.append({
            "type": "function",
            "name": str(tool.get("name", "")),
            "description": str(tool.get("description", "")),
            "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
        })
    return converted


def _json_schema_to_gemini_schema(schema):
    if not isinstance(schema, dict):
        return {"type": "OBJECT", "properties": {}}
    converted = {}
    for key, value in schema.items():
        if key == "type" and isinstance(value, str):
            converted[key] = value.upper()
            continue
        if key in {"properties", "$defs", "definitions"} and isinstance(value, dict):
            converted[key] = {name: _json_schema_to_gemini_schema(item) for name, item in value.items()}
            continue
        if key == "items":
            converted[key] = _json_schema_to_gemini_schema(value)
            continue
        if isinstance(value, dict):
            converted[key] = _json_schema_to_gemini_schema(value)
            continue
        if isinstance(value, list):
            converted[key] = [
                item.upper() if key == "type" and isinstance(item, str) else (
                    _json_schema_to_gemini_schema(item) if isinstance(item, dict) else item
                )
                for item in value
            ]
            continue
        converted[key] = value
    return converted


def _tool_result_payload(content):
    if isinstance(content, str):
        return {"content": content}
    if isinstance(content, list):
        text = _tool_result_text(content)
        return {"content": text}
    if isinstance(content, dict):
        return content
    return {"content": json.dumps(content, ensure_ascii=False)}


def _anthropic_messages_to_gemini_contents(messages):
    contents = []
    tool_names_by_id = {}

    for message in messages or []:
        role = "model" if str(message.get("role", "user")) == "assistant" else "user"
        parts = []
        for block in _normalize_message_content(message.get("content")):
            block_type = block.get("type")
            if block_type == "text":
                parts.append({"text": str(block.get("text", ""))})
                continue
            if block_type == "tool_use":
                tool_id = str(block.get("id", ""))
                tool_name = str(block.get("name", ""))
                if tool_id:
                    tool_names_by_id[tool_id] = tool_name
                parts.append({
                    "functionCall": {
                        "name": tool_name,
                        "args": block.get("input", {}) or {},
                    }
                })
                continue
            if block_type == "tool_result":
                tool_id = str(block.get("tool_use_id", ""))
                tool_name = tool_names_by_id.get(tool_id, tool_id or "tool_result")
                parts.append({
                    "functionResponse": {
                        "name": tool_name,
                        "response": _tool_result_payload(block.get("content")),
                    }
                })
                continue
        if parts:
            contents.append({"role": role, "parts": parts})
    return contents


def _anthropic_tools_to_gemini_tools(tools):
    converted = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        converted.append({
            "functionDeclarations": [{
                "name": str(tool.get("name", "")),
                "description": str(tool.get("description", "")),
                "parameters": _json_schema_to_gemini_schema(
                    tool.get("input_schema", {"type": "object", "properties": {}})
                ),
            }]
        })
    return converted


def _system_to_gemini_content(system_value):
    text = _system_to_instructions(system_value)
    if not text:
        return None
    return {"parts": [{"text": text}]}


def _build_gemini_payload(request_payload, model_name):
    config = {}
    system_instruction = _system_to_gemini_content(request_payload.get("system"))
    if system_instruction:
        config["systemInstruction"] = system_instruction
    max_tokens = request_payload.get("max_tokens")
    if max_tokens:
        config["maxOutputTokens"] = max_tokens
    tools = _anthropic_tools_to_gemini_tools(request_payload.get("tools"))
    if tools:
        config["tools"] = tools
    return {
        "model": model_name,
        "contents": _anthropic_messages_to_gemini_contents(request_payload.get("messages") or []),
        "config": config,
    }


def _build_codex_payload(request_payload, model_name):
    payload = {
        "model": model_name,
        "instructions": _system_to_instructions(request_payload.get("system")) or "You are a helpful assistant.",
        "input": _anthropic_messages_to_responses_input(request_payload.get("messages") or []),
        "store": False,
        "stream": True,
    }
    tools = _anthropic_tools_to_responses(request_payload.get("tools"))
    if tools:
        payload["tools"] = tools
    return payload


def _count_tokens_approx(payload):
    total_text = []
    total_text.append(_system_to_instructions(payload.get("system")))
    for message in payload.get("messages") or []:
        for block in _normalize_message_content(message.get("content")):
            if block.get("type") == "text":
                total_text.append(str(block.get("text", "")))
            elif block.get("type") == "tool_use":
                total_text.append(json.dumps(block.get("input", {}), ensure_ascii=False))
            elif block.get("type") == "tool_result":
                total_text.append(_tool_result_text(block.get("content")))
    text = "\n".join(part for part in total_text if part)
    return max(1, len(text) // 4)


class _AnthropicTranslator:
    def __init__(self, model_name):
        self.model_name = model_name
        self.message_id = f"msg_{uuid.uuid4().hex}"
        self.blocks = []
        self.item_to_index = {}
        self.text_item_to_index = {}
        self.seen_tool_use = False

    def _message_start(self):
        return ("message_start", {
            "type": "message_start",
            "message": {
                "id": self.message_id,
                "type": "message",
                "role": "assistant",
                "model": self.model_name,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        })

    def process(self, event_type, payload):
        outgoing = []
        if event_type == "response.created":
            outgoing.append(self._message_start())
        elif event_type == "response.output_item.added":
            item = payload.get("item", {})
            if item.get("type") == "function_call":
                index = len(self.blocks)
                self.item_to_index[item["id"]] = index
                self.blocks.append({
                    "type": "tool_use",
                    "id": item.get("call_id", item["id"]),
                    "name": item.get("name", ""),
                    "input": {},
                    "_partial_json": "",
                })
                self.seen_tool_use = True
                outgoing.append(("content_block_start", {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {
                        "type": "tool_use",
                        "id": item.get("call_id", item["id"]),
                        "name": item.get("name", ""),
                        "input": {},
                    },
                }))
        elif event_type == "response.content_part.added":
            item_id = payload.get("item_id")
            part = payload.get("part", {})
            if part.get("type") == "output_text" and item_id not in self.text_item_to_index:
                index = len(self.blocks)
                self.text_item_to_index[item_id] = index
                self.blocks.append({"type": "text", "text": ""})
                outgoing.append(("content_block_start", {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {"type": "text", "text": ""},
                }))
        elif event_type == "response.output_text.delta":
            item_id = payload.get("item_id")
            index = self.text_item_to_index.get(item_id)
            if index is not None:
                delta = payload.get("delta", "")
                self.blocks[index]["text"] += delta
                outgoing.append(("content_block_delta", {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "text_delta", "text": delta},
                }))
        elif event_type == "response.function_call_arguments.delta":
            item_id = payload.get("item_id")
            index = self.item_to_index.get(item_id)
            if index is not None:
                delta = payload.get("delta", "")
                self.blocks[index]["_partial_json"] += delta
                outgoing.append(("content_block_delta", {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "input_json_delta", "partial_json": delta},
                }))
        elif event_type == "response.output_item.done":
            item = payload.get("item", {})
            item_type = item.get("type")
            item_id = item.get("id")
            if item_type == "function_call":
                index = self.item_to_index.get(item_id)
                if index is not None:
                    args_text = item.get("arguments") or self.blocks[index].get("_partial_json", "")
                    try:
                        parsed = json.loads(args_text) if args_text else {}
                    except json.JSONDecodeError:
                        parsed = {}
                    self.blocks[index]["input"] = parsed
                    self.blocks[index].pop("_partial_json", None)
                    outgoing.append(("content_block_stop", {
                        "type": "content_block_stop",
                        "index": index,
                    }))
            elif item_type == "message":
                index = self.text_item_to_index.get(item_id)
                if index is not None:
                    outgoing.append(("content_block_stop", {
                        "type": "content_block_stop",
                        "index": index,
                    }))
        elif event_type == "response.completed":
            stop_reason = "tool_use" if self.seen_tool_use else "end_turn"
            outgoing.append(("message_delta", {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": 0},
            }))
            outgoing.append(("message_stop", {"type": "message_stop"}))
        return outgoing

    def final_message(self):
        cleaned = []
        for block in self.blocks:
            item = dict(block)
            item.pop("_partial_json", None)
            cleaned.append(item)
        stop_reason = "tool_use" if self.seen_tool_use else "end_turn"
        return {
            "id": self.message_id,
            "type": "message",
            "role": "assistant",
            "model": self.model_name,
            "content": cleaned,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }


class _GeminiAnthropicTranslator:
    def __init__(self, model_name):
        self.model_name = model_name
        self.message_id = f"msg_{uuid.uuid4().hex}"

    def _content_blocks(self, gemini_response):
        blocks = []
        candidates = gemini_response.get("candidates") or []
        if not candidates:
            return blocks
        content = (candidates[0].get("content") or {})
        for part in content.get("parts") or []:
            if not isinstance(part, dict):
                continue
            if isinstance(part.get("text"), str) and part.get("text"):
                blocks.append({"type": "text", "text": part["text"]})
                continue
            function_call = part.get("functionCall")
            if isinstance(function_call, dict):
                blocks.append({
                    "type": "tool_use",
                    "id": f"toolu_{uuid.uuid4().hex}",
                    "name": str(function_call.get("name", "")),
                    "input": function_call.get("args", {}) or {},
                })
        return blocks

    def final_message(self, gemini_response):
        blocks = self._content_blocks(gemini_response)
        stop_reason = "tool_use" if any(block.get("type") == "tool_use" for block in blocks) else "end_turn"
        return {
            "id": self.message_id,
            "type": "message",
            "role": "assistant",
            "model": self.model_name,
            "content": blocks,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }

    def stream_events(self, gemini_response):
        final_message = self.final_message(gemini_response)
        yield ("message_start", {
            "type": "message_start",
            "message": {
                "id": self.message_id,
                "type": "message",
                "role": "assistant",
                "model": self.model_name,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        })
        for index, block in enumerate(final_message["content"]):
            yield ("content_block_start", {
                "type": "content_block_start",
                "index": index,
                "content_block": {
                    "type": "tool_use",
                    "id": block["id"],
                    "name": block["name"],
                    "input": {},
                } if block["type"] == "tool_use" else {
                    "type": "text",
                    "text": "",
                },
            })
            if block["type"] == "tool_use":
                partial_json = json.dumps(block.get("input", {}), ensure_ascii=False)
                if partial_json:
                    yield ("content_block_delta", {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": {"type": "input_json_delta", "partial_json": partial_json},
                    })
            else:
                text = block.get("text", "")
                if text:
                    yield ("content_block_delta", {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": {"type": "text_delta", "text": text},
                    })
            yield ("content_block_stop", {
                "type": "content_block_stop",
                "index": index,
            })
        yield ("message_delta", {
            "type": "message_delta",
            "delta": {
                "stop_reason": final_message["stop_reason"],
                "stop_sequence": None,
            },
            "usage": {"output_tokens": 0},
        })
        yield ("message_stop", {"type": "message_stop"})


def _iter_sse_lines(response):
    current_event = None
    data_lines = []
    for raw_line in response.iter_lines():
        line = raw_line.strip()
        if not line:
            if current_event and data_lines:
                payload_text = "\n".join(data_lines)
                yield current_event, json.loads(payload_text)
            current_event = None
            data_lines = []
            continue
        if line.startswith("event:"):
            current_event = line[6:].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())


def _bridge_request_to_codex(account, model_name, request_payload, stream_response):
    if httpx is None:
        raise RuntimeError("缺少 httpx，无法启动 Codex bridge")
    auth = _load_codex_auth(account)
    token = auth.get("tokens", {}).get("access_token")
    if not token:
        raise RuntimeError("Codex 账号缺少 access_token，请重新登录")
    client_version = _load_codex_client_version(account)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = _build_codex_payload(request_payload, model_name)
    url = f"https://chatgpt.com/backend-api/codex/responses?client_version={client_version}"
    translator = _AnthropicTranslator(model_name)
    with httpx.stream("POST", url, headers=headers, json=payload, timeout=300) as response:
        if response.status_code >= 400:
            body = response.read().decode("utf-8", errors="replace")
            raise RuntimeError(body or f"Codex bridge upstream failed: {response.status_code}")
        if stream_response:
            for event_type, payload in _iter_sse_lines(response):
                for event_name, event_payload in translator.process(event_type, payload):
                    yield event_name, event_payload
            return
        for event_type, payload in _iter_sse_lines(response):
            translator.process(event_type, payload)
        yield None, translator.final_message()


def _bridge_request_to_gemini(account, model_name, request_payload, stream_response):
    home_dir = os.path.expanduser(str(account.get("home_dir", "")).strip())
    if not home_dir:
        raise RuntimeError("Gemini 账号缺少 home_dir，请重新登录")
    payload = _build_gemini_payload(request_payload, model_name)
    result = subprocess.run(
        ["node", "--no-warnings", GEMINI_BRIDGE_SCRIPT, home_dir],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip() or "Gemini bridge 调用失败"
        raise RuntimeError(message)
    gemini_response = json.loads(result.stdout or "{}")
    translator = _GeminiAnthropicTranslator(model_name)
    if stream_response:
        yield from translator.stream_events(gemini_response)
        return
    yield None, translator.final_message(gemini_response)


class _BridgeHandler(BaseHTTPRequestHandler):
    server_version = "MMSCodexClaudeBridge/0.1"

    def log_message(self, *_args):
        return

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, event_name, payload):
        body = (
            f"event: {event_name}\n"
            f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        ).encode("utf-8")
        self.wfile.write(body)
        self.wfile.flush()

    def _authorized(self):
        expected = getattr(self.server, "bridge_token")
        key = self.headers.get("x-api-key", "").strip()
        auth = self.headers.get("authorization", "").strip()
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        return expected and expected in {key, bearer}

    def do_POST(self):
        if not self._authorized():
            self._json(401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid bridge token"}})
            return

        length = int(self.headers.get("content-length") or 0)
        raw_body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._json(400, {"type": "error", "error": {"type": "invalid_request_error", "message": "invalid json"}})
            return

        if self.path == "/v1/messages/count_tokens":
            self._json(200, {"input_tokens": _count_tokens_approx(payload)})
            return

        if self.path != "/v1/messages":
            self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": "not found"}})
            return

        stream_response = bool(payload.get("stream"))
        try:
            bridge_source_cli = getattr(self.server, "bridge_source_cli", "codex")
            if bridge_source_cli == "gemini":
                iterator = _bridge_request_to_gemini(
                    self.server.account,
                    self.server.model_name,
                    payload,
                    stream_response=stream_response,
                )
            else:
                iterator = _bridge_request_to_codex(
                    self.server.account,
                    self.server.model_name,
                    payload,
                    stream_response=stream_response,
                )
            if stream_response:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                for event_name, event_payload in iterator:
                    self._sse(event_name, event_payload)
                return
            _, final_message = next(iterator)
            self._json(200, final_message)
        except Exception as exc:
            self._json(502, {
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": str(exc),
                },
            })


@contextmanager
def codex_claude_bridge(account, model_name):
    port = _find_free_port()
    bridge_token = f"mms-bridge-{uuid.uuid4().hex}"
    server = ThreadingHTTPServer(("127.0.0.1", port), _BridgeHandler)
    server.account = account
    server.model_name = model_name
    server.bridge_token = bridge_token
    server.bridge_source_cli = "codex"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "base_url": f"http://127.0.0.1:{port}",
            "api_key": bridge_token,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@contextmanager
def gemini_claude_bridge(account, model_name):
    port = _find_free_port()
    bridge_token = f"mms-bridge-{uuid.uuid4().hex}"
    server = ThreadingHTTPServer(("127.0.0.1", port), _BridgeHandler)
    server.account = account
    server.model_name = model_name
    server.bridge_token = bridge_token
    server.bridge_source_cli = "gemini"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "base_url": f"http://127.0.0.1:{port}",
            "api_key": bridge_token,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class _GatewayBridgeHandler(BaseHTTPRequestHandler):
    """Proxy bridge: accepts /v1/messages and /v1/responses from Claude Code,
    translates /v1/responses → /v1/messages, then forwards to the real gateway."""

    server_version = "MMSGatewayBridge/0.1"

    def log_message(self, *_args):
        return

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        expected = getattr(self.server, "bridge_token")
        key = self.headers.get("x-api-key", "").strip()
        auth = self.headers.get("authorization", "").strip()
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        return expected and expected in {key, bearer}

    def do_POST(self):
        if not self._authorized():
            self._json(401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid bridge token"}})
            return

        length = int(self.headers.get("content-length") or 0)
        raw_body = self.rfile.read(length) if length else b"{}"

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._json(400, {"type": "error", "error": {"type": "invalid_request_error", "message": "invalid json"}})
            return

        path = self.path
        # Translate /v1/responses → /v1/messages so gateway only sees Messages API
        if path == "/v1/responses":
            path = "/v1/messages"

        if path not in ("/v1/messages", "/v1/messages/count_tokens"):
            self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": "not found"}})
            return

        if httpx is None:
            self._json(502, {"type": "error", "error": {"type": "api_error", "message": "缺少 httpx，无法代理请求"}})
            return

        # gateway_url already ends with /v1; strip /v1 prefix from path to avoid double /v1
        gateway_url = getattr(self.server, "gateway_url")
        gateway_key = getattr(self.server, "gateway_key")
        path_suffix = path[3:]  # /v1/messages → /messages
        target_url = gateway_url.rstrip("/") + path_suffix

        fwd_headers = {
            "Content-Type": "application/json",
            "x-api-key": gateway_key,
            "Authorization": f"Bearer {gateway_key}",
            "anthropic-version": "2023-06-01",
        }
        # Forward anthropic-beta if present
        beta = self.headers.get("anthropic-beta", "")
        if beta:
            fwd_headers["anthropic-beta"] = beta

        stream = bool(payload.get("stream"))
        try:
            if stream:
                with httpx.stream("POST", target_url, headers=fwd_headers, json=payload, timeout=300) as response:
                    self.send_response(response.status_code)
                    self.send_header("Content-Type", response.headers.get("content-type", "text/event-stream"))
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.end_headers()
                    for chunk in response.iter_bytes():
                        self.wfile.write(chunk)
                        self.wfile.flush()
            else:
                response = httpx.post(target_url, headers=fwd_headers, json=payload, timeout=60)
                body_out = response.content
                self.send_response(response.status_code)
                self.send_header("Content-Type", response.headers.get("content-type", "application/json"))
                self.send_header("Content-Length", str(len(body_out)))
                self.end_headers()
                self.wfile.write(body_out)
        except Exception as exc:
            self._json(502, {"type": "error", "error": {"type": "api_error", "message": str(exc)}})


@contextmanager
def gateway_claude_bridge(gateway_url, gateway_key):
    """Local proxy for gateway mode: translates /v1/responses → /v1/messages,
    then forwards to the real gateway so gateways that only support Messages API work correctly."""
    if httpx is None:
        raise RuntimeError("缺少 httpx，无法启动 gateway bridge")
    port = _find_free_port()
    bridge_token = f"mms-bridge-{uuid.uuid4().hex}"
    server = ThreadingHTTPServer(("127.0.0.1", port), _GatewayBridgeHandler)
    server.gateway_url = gateway_url
    server.gateway_key = gateway_key
    server.bridge_token = bridge_token
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "base_url": f"http://127.0.0.1:{port}",
            "api_key": bridge_token,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
