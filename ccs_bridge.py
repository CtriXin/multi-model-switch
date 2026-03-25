import json
import logging
import os
import re
import socket
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from ccs_speed_stats import record_model_speed


class _SilentHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that silences BrokenPipeError/ConnectionResetError on client disconnect."""

    def handle_error(self, request, client_address):
        import sys
        exc_type = sys.exc_info()[0]
        if exc_type and issubclass(exc_type, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return  # 客户端断开（Ctrl+C / Escape），静默忽略
        super().handle_error(request, client_address)

try:
    import httpx
except ImportError:
    httpx = None


# ---------------------------------------------------------------------------
# 公共 URL 构造：仅对裸域名补 /v1
# ---------------------------------------------------------------------------

def _build_gateway_url(base_url, endpoint):
    """构造网关请求 URL。

    规则：
    - `https://host` -> `https://host/v1/...`
    - `https://host/v1` -> `https://host/v1/...`
    - `https://host/openai` / `https://host/api/paas/v4` -> 直接拼 endpoint

    base_url: 网关地址（可能是裸域名，也可能已带 path prefix）
    endpoint: 端点路径（如 /responses, /chat/completions）
    """
    base = base_url.rstrip("/")
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    path = urlsplit(base).path.rstrip("/")
    if not path:
        return base + "/v1" + endpoint
    return base + endpoint


_CODEX_HEADER_PASSTHROUGH = (
    "User-Agent",
    "originator",
    "session_id",
    "x-session-id",
    "openai-beta",
)


_CLAUDE_HEADER_PASSTHROUGH = (
    "User-Agent",
    "x-app",
    "anthropic-version",
    "anthropic-beta",
    "anthropic-dangerous-direct-browser-access",
)


_CLAUDE_HEADER_PREFIX_PASSTHROUGH = (
    "x-stainless-",
)


def _copy_passthrough_headers(headers, names=_CODEX_HEADER_PASSTHROUGH, prefixes=()):
    """复制需要保留给上游的请求头，避免丢失上游对原始客户端的识别信息。"""
    copied = {}
    normalized_names = {name.lower(): name for name in names}
    normalized_prefixes = tuple(prefix.lower() for prefix in prefixes)
    for header_name, value in headers.items():
        if not value:
            continue
        lower_name = header_name.lower()
        canonical_name = normalized_names.get(lower_name)
        if canonical_name:
            copied[canonical_name] = value
            continue
        if normalized_prefixes and any(lower_name.startswith(prefix) for prefix in normalized_prefixes):
            copied[header_name] = value
    return copied


# ---------------------------------------------------------------------------
# Bridge mode 缓存：记录 (provider, model) 是否需要 chatcompletions fallback
# ---------------------------------------------------------------------------

_BRIDGE_MODE_CACHE_DIR = os.path.join(
    os.environ.get("CCS_CONFIG_DIR", os.path.expanduser("~/.config/ccs")),
    "cache",
)
_BRIDGE_MODE_CACHE_FILE = os.path.join(_BRIDGE_MODE_CACHE_DIR, "bridge_mode_cache.json")
_bridge_mode_cache_memory = {}  # 内存缓存，避免重复读文件
_BRIDGE_MODE_CACHE_TTL = 6 * 3600

_bridge_error_logger = logging.getLogger("bridge_error")
_bridge_error_logger.setLevel(logging.DEBUG)
if not _bridge_error_logger.handlers:
    os.makedirs(_BRIDGE_MODE_CACHE_DIR, exist_ok=True)
    _beh = logging.FileHandler(
        os.path.join(_BRIDGE_MODE_CACHE_DIR, "bridge_error.log"),
        mode="a", encoding="utf-8",
    )
    _beh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    _bridge_error_logger.addHandler(_beh)


def _load_bridge_mode_cache():
    """加载 bridge mode 缓存。返回 dict: {\"provider:model\": \"chatcompletions\"}"""
    global _bridge_mode_cache_memory
    if _bridge_mode_cache_memory:
        return _bridge_mode_cache_memory
    try:
        if os.path.exists(_BRIDGE_MODE_CACHE_FILE):
            with open(_BRIDGE_MODE_CACHE_FILE, "r") as f:
                _bridge_mode_cache_memory = json.load(f)
        else:
            _bridge_mode_cache_memory = {}
    except (OSError, json.JSONDecodeError):
        _bridge_mode_cache_memory = {}
    return _bridge_mode_cache_memory


def _save_bridge_mode_cache(cache):
    """持久化 bridge mode 缓存到文件。"""
    global _bridge_mode_cache_memory
    _bridge_mode_cache_memory = cache
    try:
        os.makedirs(_BRIDGE_MODE_CACHE_DIR, exist_ok=True)
        with open(_BRIDGE_MODE_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def _record_bridge_fallback(provider_id, model_name):
    """记录 (provider, model) 需要走 chatcompletions bridge。"""
    cache = _load_bridge_mode_cache()
    key = f"{provider_id}:{model_name}"
    entry = cache.get(key)
    if not isinstance(entry, dict) or entry.get("mode") != "chatcompletions":
        cache[key] = {"mode": "chatcompletions", "ts": time.time()}
        _save_bridge_mode_cache(cache)


def _needs_chatcompletions_bridge(provider_id, model_name):
    """检查 (provider, model) 是否已知需要 chatcompletions bridge。"""
    cache = _load_bridge_mode_cache()
    entry = cache.get(f"{provider_id}:{model_name}")
    # 兼容旧格式，但不再信任无时间戳的字符串缓存，避免历史错误把 provider 永久锁死。
    if not isinstance(entry, dict):
        return False
    if entry.get("mode") != "chatcompletions":
        return False
    ts = entry.get("ts")
    if not isinstance(ts, (int, float)):
        return False
    if time.time() - ts > _BRIDGE_MODE_CACHE_TTL:
        return False
    return True


def _clear_bridge_fallback(provider_id, model_name):
    cache = _load_bridge_mode_cache()
    key = f"{provider_id}:{model_name}"
    if key in cache:
        cache.pop(key, None)
        _save_bridge_mode_cache(cache)


def _build_gateway_candidate_urls(base_url, endpoint):
    primary = _build_gateway_url(base_url, endpoint)
    candidates = [primary]
    base = (base_url or "").rstrip("/")
    path = urlsplit(base).path.rstrip("/")
    if path and not path.endswith("/v1"):
        alt = f"{base}/v1{endpoint if endpoint.startswith('/') else '/' + endpoint}"
        if alt not in candidates:
            candidates.append(alt)
    return candidates


def _should_try_chatcompletions_fallback(status_code, body_text):
    if status_code in (404, 405, 410, 501):
        return True
    if status_code != 400:
        return False
    lower = (body_text or "").lower()
    unsupported_markers = (
        "messages array is required",
        "field messages is required",
        "unsupported path",
        "route /",
        "not found",
    )
    return any(marker in lower for marker in unsupported_markers)


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
GEMINI_BRIDGE_SCRIPT = os.path.join(ROOT_DIR, "scripts", "gemini_codeassist_bridge.mjs")


def _now_ms():
    return time.monotonic() * 1000.0


def _extract_output_tokens(payload):
    if not isinstance(payload, dict):
        return None

    usage_candidates = []
    for key in ("usage",):
        usage = payload.get(key)
        if isinstance(usage, dict):
            usage_candidates.append(usage)
    response_payload = payload.get("response")
    if isinstance(response_payload, dict):
        usage = response_payload.get("usage")
        if isinstance(usage, dict):
            usage_candidates.append(usage)
    message_payload = payload.get("message")
    if isinstance(message_payload, dict):
        usage = message_payload.get("usage")
        if isinstance(usage, dict):
            usage_candidates.append(usage)

    for usage in usage_candidates:
        for key in ("output_tokens", "completion_tokens"):
            value = usage.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return int(value)
    return None


def _record_bridge_speed(model_name, *, started_ms, first_byte_ms, output_tokens=None, provider_scope=None):
    if first_byte_ms is None:
        return
    total_ms = max(0.0, _now_ms() - started_ms)
    ttfb_ms = max(0.0, first_byte_ms - started_ms)
    if total_ms <= 0 or ttfb_ms <= 0:
        return
    record_model_speed(
        model_name,
        ttfb_ms=ttfb_ms,
        total_ms=total_ms,
        output_tokens=output_tokens,
        provider=provider_scope,
    )


def _current_route_status_path():
    return os.path.join(os.path.expanduser("~/.config/mms"), "route_status.json")


def _dedupe_status_paths(paths):
    normalized = []
    seen = set()
    for path in paths or []:
        value = os.path.abspath(str(path or "").strip())
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _write_route_status(tier, model, reason, *, status_paths=None):
    """写路由状态供 statusline 读取，非阻塞，失败静默。"""
    try:
        data = json.dumps({"tier": tier, "model": model, "reason": reason, "ts": time.time()})
        targets = _dedupe_status_paths(status_paths or [_current_route_status_path()])
        for path in targets:
            try:
                tmp = path + ".tmp"
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(data)
                os.replace(tmp, path)
            except OSError:
                pass
    except Exception:
        pass


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

    def do_GET(self):
        if not self._authorized():
            self._json(401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid bridge token"}})
            return
        if self.path == "/v1/models":
            model = getattr(self.server, "model_name", "")
            data = [{"id": model, "object": "model"}] if model else []
            self._json(200, {"object": "list", "data": data})
            return
        self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": "not found"}})

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

        path_bare = self.path.split("?")[0]

        if path_bare == "/v1/messages/count_tokens":
            self._json(200, {"input_tokens": _count_tokens_approx(payload)})
            return

        if path_bare != "/v1/messages":
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
    server = _SilentHTTPServer(("127.0.0.1", port), _BridgeHandler)
    server.account = account
    server.model_name = model_name
    server.bridge_token = bridge_token
    server.bridge_source_cli = "codex"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.1)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            if result == 0:
                break
        except Exception:
            pass
        time.sleep(0.1)
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
    server = _SilentHTTPServer(("127.0.0.1", port), _BridgeHandler)
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


_SYSTEM_TAG_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)


def _json_resp_to_sse(body: bytes) -> bytes:
    """将 upstream 非流式 JSON 响应转换为 Anthropic SSE 事件流。

    支持 Anthropic Messages 格式和 OpenAI Chat Completions 格式。
    Claude Code 期望 SSE 流，但路由模式下 upstream 返回 JSON，需要在此转换。
    """
    try:
        data = json.loads(body)
    except Exception:
        return body

    events: list[str] = []

    # ── Anthropic Messages 格式 ──
    if data.get("type") == "message":
        content = data.get("content", [])
        usage = data.get("usage", {})
        start = {**data, "content": [], "stop_reason": None, "stop_sequence": None,
                 "usage": {"input_tokens": usage.get("input_tokens", 0), "output_tokens": 0}}
        events.append(f'event: message_start\ndata: {json.dumps({"type": "message_start", "message": start})}\n\n')
        for i, blk in enumerate(content):
            bt = blk.get("type", "text")
            cb_start = {"type": bt, "text": ""} if bt == "text" else {"type": bt, "thinking": ""}
            events.append(f'event: content_block_start\ndata: {json.dumps({"type": "content_block_start", "index": i, "content_block": cb_start})}\n\n')
            if bt == "text":
                events.append(f'event: content_block_delta\ndata: {json.dumps({"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": blk.get("text", "")}})}\n\n')
            elif bt == "thinking":
                events.append(f'event: content_block_delta\ndata: {json.dumps({"type": "content_block_delta", "index": i, "delta": {"type": "thinking_delta", "thinking": blk.get("thinking", "")}})}\n\n')
            events.append(f'event: content_block_stop\ndata: {json.dumps({"type": "content_block_stop", "index": i})}\n\n')
        events.append(f'event: message_delta\ndata: {json.dumps({"type": "message_delta", "delta": {"stop_reason": data.get("stop_reason", "end_turn"), "stop_sequence": None}, "usage": {"output_tokens": usage.get("output_tokens", 0)}})}\n\n')
        events.append(f'event: message_stop\ndata: {json.dumps({"type": "message_stop"})}\n\n')
        return "".join(events).encode()

    # ── OpenAI Chat Completions 格式 ──
    if "choices" in data:
        choice = data["choices"][0] if data.get("choices") else {}
        msg = choice.get("message", {})
        text = msg.get("content", "") or ""
        usage = data.get("usage", {})
        msg_id = data.get("id", f"msg_{id(data)}")
        model = data.get("model", "")
        anthro = {"id": msg_id, "type": "message", "role": "assistant", "content": [],
                  "model": model, "stop_reason": None, "stop_sequence": None,
                  "usage": {"input_tokens": usage.get("prompt_tokens", 0), "output_tokens": 0}}
        events.append(f'event: message_start\ndata: {json.dumps({"type": "message_start", "message": anthro})}\n\n')
        events.append(f'event: content_block_start\ndata: {json.dumps({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})}\n\n')
        events.append(f'event: content_block_delta\ndata: {json.dumps({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}})}\n\n')
        events.append(f'event: content_block_stop\ndata: {json.dumps({"type": "content_block_stop", "index": 0})}\n\n')
        events.append(f'event: message_delta\ndata: {json.dumps({"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": usage.get("completion_tokens", 0)}})}\n\n')
        events.append(f'event: message_stop\ndata: {json.dumps({"type": "message_stop"})}\n\n')
        return "".join(events).encode()

    # ── 未知格式，原样返回 ──
    return body


def _extract_user_text(content):
    """从 Anthropic messages content 中提取纯用户文本（剥离 system-reminder 注入）。"""
    if isinstance(content, str):
        return _SYSTEM_TAG_RE.sub("", content).strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        raw = " ".join(parts)
        return _SYSTEM_TAG_RE.sub("", raw).strip()
    return ""


class _GatewayBridgeHandler(BaseHTTPRequestHandler):
    """Proxy bridge: accepts /v1/messages and /v1/responses from Claude Code,
    translates /v1/responses → /v1/messages, then forwards to the real gateway."""

    server_version = "MMSGatewayBridge/0.1"

    def log_message(self, *_args):
        return

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except BrokenPipeError:
            self.close_connection = True

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

    def do_GET(self):
        """Handle /v1/models — advertise configured models so Claude Code validation passes."""
        if not self._authorized():
            self._json(401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid bridge token"}})
            return
        if self.path == "/v1/models":
            # 动态构建模型列表：优先使用调用方提供的 advertised_models，再补兜底。
            seen = set()
            models = []
            advertised_models = list(getattr(self.server, "advertised_models", []) or [])
            fallback_models = [
                getattr(self.server, "heavy_model", None),
                getattr(self.server, "medium_model", None),
                getattr(self.server, "light_model", None),
                "claude-sonnet-4-6",
                "claude-opus-4-6",
                "claude-haiku-4-5-20251001",
            ]
            for m in advertised_models + fallback_models:
                if m and m not in seen:
                    seen.add(m)
                    models.append({"id": m, "object": "model"})
            self._json(200, {"object": "list", "data": models})
            return
        self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": "not found"}})

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
        path_bare = path.split("?")[0]
        # Translate /v1/responses → /v1/messages so gateway only sees Messages API
        if path_bare == "/v1/responses":
            path = "/v1/messages" + path[len("/v1/responses"):]

        # ── debug: 记录每次 bridge 收到的请求 ──
        _lb_debug_paths = [os.path.expanduser("~/.config/mms/lb_debug.log")]
        _real_home = os.environ.get("HOME", "")
        _gateway_marker = f"{os.sep}.config{os.sep}mms{os.sep}claude-gateway{os.sep}"
        if _gateway_marker in _real_home:
            _user_home = _real_home.split(_gateway_marker, 1)[0]
            if _user_home:
                _lb_debug_paths.append(os.path.join(_user_home, ".config", "mms", "lb_debug.log"))
        elif f"{os.sep}claude-gateway{os.sep}" in _real_home:
            _user_home = _real_home.split(f"{os.sep}claude-gateway{os.sep}", 1)[0]
            if _user_home.endswith(f"{os.sep}.config{os.sep}mms"):
                _user_home = os.path.dirname(os.path.dirname(_user_home))
            if _user_home:
                _lb_debug_paths.append(os.path.join(_user_home, ".config", "mms", "lb_debug.log"))
        try:
            light_model = getattr(self.server, "light_model", None)
            medium_model = getattr(self.server, "medium_model", None)
            heavy_model = getattr(self.server, "heavy_model", None)
            user_msgs = [m for m in payload.get("messages", []) if m.get("role") == "user"]
            log_line = (f"[POST {self.path}→{path}] heavy={heavy_model} medium={medium_model} light={light_model} "
                        f"user_msgs={len(user_msgs)} model={payload.get('model','?')}\n")
            if user_msgs:
                raw = _extract_user_text(user_msgs[-1].get("content", ""))
                log_line += f"  last_user_text({len(raw)}): {raw[:120]}\n"
            for _lb_debug in _lb_debug_paths:
                try:
                    os.makedirs(os.path.dirname(_lb_debug), exist_ok=True)
                    with open(_lb_debug, "a") as _f:
                        _f.write(log_line)
                except OSError:
                    pass
        except Exception:
            pass

        # ── SUGGESTION MODE 拦截（最优先，在路由之前）──
        # 扫描所有 user messages，任何一条包含 SUGGESTION MODE → 直接返回空回复
        path_bare_check = path.split("?")[0]
        if "/messages" in path_bare_check:
            for _msg in payload.get("messages", []):
                if _msg.get("role") != "user":
                    continue
                _raw_content = _msg.get("content", "")
                # content 可能是 str 或 list
                _check_texts = []
                if isinstance(_raw_content, str):
                    _check_texts.append(_raw_content)
                elif isinstance(_raw_content, list):
                    for _item in _raw_content:
                        if isinstance(_item, str):
                            _check_texts.append(_item)
                        elif isinstance(_item, dict) and _item.get("type") == "text":
                            _check_texts.append(_item.get("text", ""))
                for _ct in _check_texts:
                    if _ct.startswith("[SUGGESTION MODE") or _ct.startswith("[SYSTEM"):
                        try:
                            from ccs_router import log_route
                            log_route("light", "blocked:suggestion", "(blocked)", _ct[:60])
                        except Exception:
                            pass
                        _block_resp = {
                            "id": "msg_blocked_suggestion",
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "text", "text": ""}],
                            "model": payload.get("model", ""),
                            "stop_reason": "end_turn",
                            "usage": {"input_tokens": 0, "output_tokens": 0},
                        }
                        if payload.get("stream"):
                            # 客户端期望 SSE 流，返回 SSE 格式
                            _sse_out = _json_resp_to_sse(json.dumps(_block_resp).encode())
                            self.send_response(200)
                            self.send_header("Content-Type", "text/event-stream")
                            self.send_header("Cache-Control", "no-cache")
                            self.end_headers()
                            self.wfile.write(_sse_out)
                        else:
                            self._json(200, _block_resp)
                        return

        # ── 模型名映射：将 Claude Code 发来的 claude-* 替换为真实模型名 ──
        heavy_model = getattr(self.server, "heavy_model", None)
        if heavy_model and "model" in payload:
            payload["model"] = heavy_model

        # ── 智能路由：3-tier (light/medium/heavy) + sticky escalation ──
        light_model = getattr(self.server, "light_model", None)
        medium_model = getattr(self.server, "medium_model", None)
        # 过滤空字符串
        light_model = light_model if light_model and light_model.strip() else None
        medium_model = medium_model if medium_model and medium_model.strip() else None
        path_no_qs = path.split("?")[0]
        has_routing = light_model or medium_model
        if has_routing and "/messages" in path_no_qs and path_no_qs != "/v1/messages/count_tokens":
            user_msgs = [m for m in payload.get("messages", []) if m.get("role") == "user"]
            # 回退查找：从最后一条 user message 往前找有文本的（跳过 tool_result-only）
            last_text = ""
            for _um in reversed(user_msgs):
                _t = _extract_user_text(_um.get("content", ""))
                if _t:
                    last_text = _t
                    break

            if last_text:
                from ccs_router import classify_task, log_route, STICKY_DECAY_TURNS
                import time as _time_mod

                # 短时去重：同一文本 3 秒内不重复分类
                _prev = getattr(self.server, "_last_classify", None)
                _now = _time_mod.time()
                if (_prev and _prev[0] == last_text
                        and _now - _prev[2] < 3):
                    level, reason = _prev[1], f"dedup({_prev[3]})"
                else:
                    gw_url = getattr(self.server, "gateway_url", None)
                    gw_key = getattr(self.server, "gateway_key", None)
                    level, reason = classify_task(
                        last_text, api_url=gw_url, api_key=gw_key,
                        light_model=light_model or medium_model,
                    )
                    self.server._last_classify = (last_text, level, _now, reason)

                # sticky escalation：heavy 后保持，但高置信 LIGHT 可 override
                sticky_floor = getattr(self.server, "_sticky_floor", None)
                sticky_remaining = getattr(self.server, "_sticky_remaining", 0)
                # 高置信 LIGHT 信号：关键词命中或 LLM 高置信
                _is_confident_light = (level == "light" and
                    (reason.startswith("keyword:") or "high_confidence" in reason))
                if sticky_floor == "heavy" and sticky_remaining > 0:
                    if _is_confident_light:
                        # 高置信 LIGHT override sticky，允许降级
                        self.server._sticky_floor = None
                        self.server._sticky_remaining = 0
                        reason = f"sticky_override({reason})"
                    elif level != "heavy":
                        level = "heavy"
                        reason = f"sticky({sticky_remaining})"
                        self.server._sticky_remaining = sticky_remaining - 1
                        if self.server._sticky_remaining <= 0:
                            self.server._sticky_floor = None
                    else:
                        self.server._sticky_remaining = sticky_remaining - 1
                        if self.server._sticky_remaining <= 0:
                            self.server._sticky_floor = None
                elif level == "heavy":
                    self.server._sticky_floor = "heavy"
                    self.server._sticky_remaining = STICKY_DECAY_TURNS

                # 按 tier 选模型
                if level == "light" and light_model:
                    payload["model"] = light_model
                elif level == "medium" and medium_model:
                    payload["model"] = medium_model
                # heavy 保持 payload["model"]（已设为 heavy_model）
                log_route(level, reason, payload.get("model", "?"), last_text)
                # 写状态文件供 statusline 读取
                _write_route_status(
                    level,
                    payload.get("model", ""),
                    reason,
                    status_paths=getattr(self.server, "route_status_paths", None),
                )
                # 保存 level 供后续使用
                self.server._last_level = level
            elif user_msgs:
                # tool_result 续接：沿用上次 tier（不默认 HEAVY）
                prev_level = getattr(self.server, "_last_level", "medium")
                if prev_level == "light" and light_model:
                    payload["model"] = light_model
                elif prev_level == "medium" and medium_model:
                    payload["model"] = medium_model
                _write_route_status(
                    prev_level,
                    payload.get("model", ""),
                    "tool_continue",
                    status_paths=getattr(self.server, "route_status_paths", None),
                )
                from ccs_router import log_route
                log_route(prev_level, "tool_continue", payload.get("model", "?"), "(tool_result)")
            else:
                # 智能路由开启但没有用户消息，沿用上次 tier
                prev_level = getattr(self.server, "_last_level", "medium")
                _write_route_status(
                    prev_level,
                    payload.get("model", ""),
                    "no_user_msg",
                    status_paths=getattr(self.server, "route_status_paths", None),
                )
                self.server._last_level = prev_level

        # 无论是否路由，都写 status 供 statusline 显示真实 model
        if not has_routing and "/messages" in path.split("?")[0]:
            _write_route_status(
                "-",
                payload.get("model", ""),
                "direct",
                status_paths=getattr(self.server, "route_status_paths", None),
            )

        # 剥离 query string 再匹配路由（Claude Code 会发 /v1/messages?beta=true）
        path_bare = path.split("?")[0]
        should_record_speed = path_bare != "/v1/messages/count_tokens"

        if path_bare not in ("/v1/messages", "/v1/messages/count_tokens"):
            self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": "not found"}})
            return

        if httpx is None:
            self._json(502, {"type": "error", "error": {"type": "api_error", "message": "缺少 httpx，无法代理请求"}})
            return

        # gateway_url already ends with /v1; strip /v1 prefix from path to avoid double /v1
        gateway_url = getattr(self.server, "gateway_url")
        gateway_key = getattr(self.server, "gateway_key")

        # 跨 provider 负载：根据当前 tier 选用对应 slot 的 url/key
        slot_configs = getattr(self.server, "slot_configs", {})
        current_level = getattr(self.server, "_last_level", "heavy")
        if current_level in slot_configs:
            slot = slot_configs[current_level]
            if slot.get("url"):
                gateway_url = slot["url"]
            if slot.get("key"):
                gateway_key = slot["key"]

        # gateway_url 可能以 /v1 结尾也可能不以 /v1 结尾，需兼容
        _gw = gateway_url.rstrip("/")
        if _gw.endswith("/v1"):
            path_suffix = path[3:]  # strip /v1 prefix to avoid double /v1
        else:
            path_suffix = path      # keep full path including /v1
        target_url = _gw + path_suffix

        fwd_headers = {
            "Content-Type": "application/json",
            "x-api-key": gateway_key,
            "Authorization": f"Bearer {gateway_key}",
        }
        fwd_headers.update(
            _copy_passthrough_headers(
                self.headers,
                names=_CLAUDE_HEADER_PASSTHROUGH,
                prefixes=_CLAUDE_HEADER_PREFIX_PASSTHROUGH,
            )
        )
        # Anthropic API 需要 version；若客户端没显式带，保守回退到官方默认值。
        if "anthropic-version" not in {name.lower() for name in fwd_headers}:
            fwd_headers["anthropic-version"] = "2023-06-01"

        client_wants_stream = bool(payload.get("stream"))
        stream = client_wants_stream
        # 智能路由模式下强制非流式（避免各 provider SSE 格式 / 连接行为不一致）
        if has_routing:
            stream = False
            payload["stream"] = False  # 确保 upstream 也返回 JSON 而非 SSE
        metrics_model = str(payload.get("model") or "")
        started_ms = _now_ms()
        first_byte_ms = None
        output_tokens = None

        try:
            if stream:
                with httpx.stream("POST", target_url, headers=fwd_headers, json=payload, timeout=300) as response:
                    self.send_response(response.status_code)
                    self.send_header("Content-Type", response.headers.get("content-type", "text/event-stream"))
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    for raw_line in response.iter_lines():
                        if first_byte_ms is None:
                            first_byte_ms = _now_ms()
                        stripped = raw_line.strip()
                        if stripped.startswith("data:"):
                            data_str = stripped[5:].strip()
                            if data_str and data_str != "[DONE]":
                                try:
                                    event_payload = json.loads(data_str)
                                except json.JSONDecodeError:
                                    event_payload = None
                                extracted = _extract_output_tokens(event_payload)
                                if extracted is not None:
                                    output_tokens = extracted
                        self.wfile.write(raw_line.encode("utf-8") + b"\n")
                        if raw_line == "":
                            self.wfile.flush()
                    self.close_connection = True
            else:
                response = httpx.post(target_url, headers=fwd_headers, json=payload, timeout=300)
                first_byte_ms = _now_ms()
                body_out = response.content
                if body_out:
                    try:
                        output_tokens = _extract_output_tokens(json.loads(body_out.decode("utf-8")))
                    except Exception:
                        output_tokens = None
                # 路由模式：upstream 返回 JSON，但 Claude Code 期望 SSE → 转换
                if has_routing and client_wants_stream and response.status_code == 200:
                    body_out = _json_resp_to_sse(body_out)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(body_out)
                else:
                    self.send_response(response.status_code)
                    self.send_header("Content-Type", response.headers.get("content-type", "application/json"))
                    self.send_header("Content-Length", str(len(body_out)))
                    self.end_headers()
                    self.wfile.write(body_out)
                if should_record_speed and response.status_code < 400:
                    _record_bridge_speed(
                        metrics_model,
                        started_ms=started_ms,
                        first_byte_ms=first_byte_ms,
                        output_tokens=output_tokens,
                        provider_scope=getattr(self.server, "speed_scope", None),
                    )
        except BrokenPipeError:
            return  # 客户端已断开（Ctrl+C），静默忽略
        except Exception as exc:
            try:
                self._json(502, {"type": "error", "error": {"type": "api_error", "message": str(exc)}})
            except BrokenPipeError:
                return


########################################################################
# Codex ↔ Chat Completions Bridge
#   Codex CLI 硬绑 Responses API (/v1/responses)，但 gateway 对非 GPT
#   模型只支持 Chat Completions (/v1/chat/completions)。
#   此 bridge 在本地起 HTTP server，接受 Codex 的 Responses 请求，
#   翻译为 Chat Completions 请求转发给 gateway，再把流式响应翻译回
#   Responses SSE 事件。
########################################################################


def _responses_input_to_messages(instructions, input_items):
    """Convert Responses API 'input' array to Chat Completions 'messages'."""
    messages = []
    if instructions:
        messages.append({"role": "system", "content": instructions})

    pending_tool_calls = []

    for item in input_items or []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        role = item.get("role")

        if item_type == "function_call":
            pending_tool_calls.append({
                "id": item.get("call_id", item.get("id", "")),
                "type": "function",
                "function": {
                    "name": item.get("name", ""),
                    "arguments": item.get("arguments", "{}"),
                },
            })
            continue

        if item_type == "function_call_output":
            # Flush any pending tool_calls first
            if pending_tool_calls:
                messages.append({"role": "assistant", "tool_calls": list(pending_tool_calls)})
                pending_tool_calls = []
            messages.append({
                "role": "tool",
                "tool_call_id": item.get("call_id", ""),
                "content": str(item.get("output", "")),
            })
            continue

        if role in ("user", "assistant", "system"):
            # Flush pending tool_calls before a new message
            if pending_tool_calls:
                messages.append({"role": "assistant", "tool_calls": list(pending_tool_calls)})
                pending_tool_calls = []

            content_parts = item.get("content")
            if isinstance(content_parts, list):
                # Extract text from content parts
                texts = []
                for part in content_parts:
                    if isinstance(part, dict):
                        if part.get("type") == "input_text":
                            texts.append(part.get("text", ""))
                        elif part.get("type") == "output_text":
                            texts.append(part.get("text", ""))
                        elif part.get("type") == "text":
                            texts.append(part.get("text", ""))
                    elif isinstance(part, str):
                        texts.append(part)
                content = "\n".join(texts) if texts else ""
            elif isinstance(content_parts, str):
                content = content_parts
            else:
                content = ""

            if role == "assistant" and item_type == "message":
                # Check if this message also has tool_calls embedded
                messages.append({"role": "assistant", "content": content})
            else:
                messages.append({"role": role, "content": content})
            continue

    # Flush remaining pending tool_calls
    if pending_tool_calls:
        messages.append({"role": "assistant", "tool_calls": list(pending_tool_calls)})

    return messages


def _responses_tools_to_chat(tools):
    """Convert Responses API tools to Chat Completions format."""
    converted = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") == "function":
            converted.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                },
            })
    return converted


class _ChatCompletionsToResponsesTranslator:
    """Translate Chat Completions streaming chunks to Responses API SSE events.
    Matches the real OpenAI Responses API format that Codex expects."""

    def __init__(self, model_name, response_id=None):
        self.model_name = model_name
        self.response_id = response_id or f"resp_{uuid.uuid4().hex[:24]}"
        self.msg_item_id = f"msg_{uuid.uuid4().hex[:24]}"
        self.text_content = ""
        self.tool_calls = {}  # index -> {id, name, arguments}
        self.started = False
        self.text_part_added = False
        self.output_index = 0
        self._seq = 0

    def _seq_num(self):
        self._seq += 1
        return self._seq

    def _response_obj(self, status="in_progress", output=None):
        return {
            "id": self.response_id,
            "object": "response",
            "status": status,
            "model": self.model_name,
            "output": output or [],
            "usage": None if status != "completed" else {
                "input_tokens": 0,
                "output_tokens": max(1, len(self.text_content) // 4),
                "total_tokens": max(1, len(self.text_content) // 4),
            },
        }

    def process_chunk(self, chunk):
        """Process a single Chat Completions chunk and yield Responses SSE events."""
        outgoing = []

        if not self.started:
            self.started = True
            outgoing.append(("response.created", {
                "type": "response.created",
                "response": self._response_obj("in_progress"),
            }))
            outgoing.append(("response.in_progress", {
                "type": "response.in_progress",
                "response": self._response_obj("in_progress"),
            }))
            outgoing.append(("response.output_item.added", {
                "type": "response.output_item.added",
                "output_index": self.output_index,
                "item": {
                    "type": "message",
                    "id": self.msg_item_id,
                    "role": "assistant",
                    "status": "in_progress",
                    "content": [],
                },
                "sequence_number": self._seq_num(),
            }))

        choices = chunk.get("choices", [])
        if not choices:
            return outgoing

        choice = choices[0]
        delta = choice.get("delta", {})
        finish_reason = choice.get("finish_reason")

        # Text content delta
        content = delta.get("content")
        if content is not None:
            if not self.text_part_added:
                self.text_part_added = True
                outgoing.append(("response.content_part.added", {
                    "type": "response.content_part.added",
                    "item_id": self.msg_item_id,
                    "output_index": self.output_index,
                    "content_index": 0,
                    "part": {"type": "output_text", "annotations": [], "text": ""},
                    "sequence_number": self._seq_num(),
                }))
            self.text_content += content
            outgoing.append(("response.output_text.delta", {
                "type": "response.output_text.delta",
                "item_id": self.msg_item_id,
                "output_index": self.output_index,
                "content_index": 0,
                "delta": content,
                "sequence_number": self._seq_num(),
            }))

        # Tool call deltas
        tool_calls = delta.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                idx = tc.get("index", 0)
                if idx not in self.tool_calls:
                    tc_id = tc.get("id", f"call_{uuid.uuid4().hex[:24]}")
                    tc_name = tc.get("function", {}).get("name", "")
                    self.tool_calls[idx] = {
                        "id": tc_id,
                        "item_id": f"fc_{uuid.uuid4().hex[:24]}",
                        "name": tc_name,
                        "arguments": "",
                    }
                    # Close text part if open
                    if self.text_part_added:
                        outgoing.extend(self._close_text_part())
                        self.output_index += 1
                        self.text_part_added = False

                    outgoing.append(("response.output_item.added", {
                        "type": "response.output_item.added",
                        "output_index": self.output_index + idx,
                        "item": {
                            "type": "function_call",
                            "id": self.tool_calls[idx]["item_id"],
                            "call_id": tc_id,
                            "name": tc_name,
                            "arguments": "",
                            "status": "in_progress",
                        },
                        "sequence_number": self._seq_num(),
                    }))

                args_delta = tc.get("function", {}).get("arguments", "")
                if args_delta:
                    self.tool_calls[idx]["arguments"] += args_delta
                    outgoing.append(("response.function_call_arguments.delta", {
                        "type": "response.function_call_arguments.delta",
                        "item_id": self.tool_calls[idx]["item_id"],
                        "output_index": self.output_index + idx,
                        "delta": args_delta,
                        "sequence_number": self._seq_num(),
                    }))

        # Finish
        if finish_reason is not None:
            if self.text_part_added and not self.tool_calls:
                outgoing.extend(self._close_text_part())

            # Close open tool calls
            for idx, tc_info in sorted(self.tool_calls.items()):
                outgoing.append(("response.function_call_arguments.done", {
                    "type": "response.function_call_arguments.done",
                    "item_id": tc_info["item_id"],
                    "output_index": self.output_index + idx,
                    "arguments": tc_info["arguments"],
                    "sequence_number": self._seq_num(),
                }))
                outgoing.append(("response.output_item.done", {
                    "type": "response.output_item.done",
                    "output_index": self.output_index + idx,
                    "item": {
                        "type": "function_call",
                        "id": tc_info["item_id"],
                        "call_id": tc_info["id"],
                        "name": tc_info["name"],
                        "arguments": tc_info["arguments"],
                        "status": "completed",
                    },
                    "sequence_number": self._seq_num(),
                }))

            # Build output for completed response
            output_items = []
            if self.text_content or not self.tool_calls:
                output_items.append({
                    "type": "message",
                    "id": self.msg_item_id,
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "annotations": [], "text": self.text_content}],
                })
            for idx, tc_info in sorted(self.tool_calls.items()):
                output_items.append({
                    "type": "function_call",
                    "id": tc_info["item_id"],
                    "call_id": tc_info["id"],
                    "name": tc_info["name"],
                    "arguments": tc_info["arguments"],
                    "status": "completed",
                })

            outgoing.append(("response.completed", {
                "type": "response.completed",
                "response": self._response_obj("completed", output_items),
            }))

        return outgoing

    def _close_text_part(self):
        """Emit output_text.done + content_part.done + output_item.done for text."""
        events = []
        events.append(("response.output_text.done", {
            "type": "response.output_text.done",
            "item_id": self.msg_item_id,
            "output_index": self.output_index,
            "content_index": 0,
            "text": self.text_content,
            "sequence_number": self._seq_num(),
        }))
        events.append(("response.content_part.done", {
            "type": "response.content_part.done",
            "item_id": self.msg_item_id,
            "output_index": self.output_index,
            "content_index": 0,
            "part": {"type": "output_text", "annotations": [], "text": self.text_content},
            "sequence_number": self._seq_num(),
        }))
        events.append(("response.output_item.done", {
            "type": "response.output_item.done",
            "output_index": self.output_index,
            "item": {
                "type": "message",
                "id": self.msg_item_id,
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "annotations": [], "text": self.text_content}],
            },
            "sequence_number": self._seq_num(),
        }))
        return events


class _ResponsesProxyHandler(BaseHTTPRequestHandler):
    """Local proxy for Codex direct Responses traffic with patched /v1/models."""

    server_version = "MMSCodexResponsesProxy/0.1"

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
        gateway_key = getattr(self.server, "gateway_key", "")
        auth = self.headers.get("authorization", "").strip()
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        key = self.headers.get("x-api-key", "").strip()
        token = key or bearer
        return token and token in {expected, gateway_key}

    def _sse(self, event_name, payload):
        body = (
            f"event: {event_name}\n"
            f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        ).encode("utf-8")
        self.wfile.write(body)
        self.wfile.flush()

    def do_GET(self):
        if self.path == "/v1/models":
            advertised_models = list(getattr(self.server, "advertised_models", []) or [])
            model = getattr(self.server, "model_name", "unknown")
            if not advertised_models:
                advertised_models = [model]
            self._json(200, {
                "object": "list",
                "data": [{"id": item, "object": "model", "owned_by": "gateway"} for item in advertised_models if item],
            })
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._authorized():
            self._json(401, {"error": {"message": "invalid token"}})
            return

        length = int(self.headers.get("content-length") or 0)
        raw_body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._json(400, {"error": {"message": "invalid json"}})
            return

        if self.path not in ("/v1/responses", "/responses"):
            self._json(404, {"error": {"message": f"unsupported path: {self.path}"}})
            return

        if httpx is None:
            self._json(502, {"error": {"message": "缺少 httpx"}})
            return

        gateway_url = getattr(self.server, "gateway_url")
        gateway_key = getattr(self.server, "gateway_key")
        model_name = payload.get("model") or getattr(self.server, "model_name", "unknown")
        provider_id = getattr(self.server, "provider_id", "")
        target_url = _build_gateway_url(gateway_url, "/responses")
        fwd_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {gateway_key}",
        }
        fwd_headers.update(_copy_passthrough_headers(self.headers))

        started_ms = _now_ms()
        first_byte_ms = None
        output_tokens = None

        # 检查是否已知需要 chatcompletions fallback
        if provider_id and _needs_chatcompletions_bridge(provider_id, model_name):
            self._do_chatcompletions_fallback(payload, model_name, gateway_url, gateway_key,
                                             started_ms)
            return

        try:
            with httpx.stream("POST", target_url, headers=fwd_headers, json=payload, timeout=300) as response:
                content_type = response.headers.get("content-type", "application/json")
                is_stream = "text/event-stream" in content_type.lower()

                def _forward_sse_line(raw_line):
                    nonlocal output_tokens
                    stripped = raw_line.strip()
                    if stripped.startswith("data:"):
                        data_str = stripped[5:].strip()
                        if data_str and data_str != "[DONE]":
                            try:
                                event_payload = json.loads(data_str)
                            except json.JSONDecodeError:
                                event_payload = None
                            extracted = _extract_output_tokens(event_payload)
                            if extracted is not None:
                                output_tokens = extracted
                    self.wfile.write(raw_line.encode("utf-8") + b"\n")
                    if raw_line == "":
                        self.wfile.flush()

                # 检测上游是否真正支持 Responses API。仅在明确“不支持 Responses”时才 fallback；
                # 普通 4xx 业务错误应原样透传，避免把可用 provider 误判为 chat completions-only。
                cl_header = response.headers.get("content-length", "")
                if response.status_code >= 400:
                    body_out = response.read()
                    body_text = body_out.decode("utf-8", errors="replace")
                    if _should_try_chatcompletions_fallback(response.status_code, body_text):
                        response.close()
                        if provider_id:
                            _record_bridge_fallback(provider_id, model_name)
                        self._do_chatcompletions_fallback(
                            payload, model_name, gateway_url, gateway_key, _now_ms()
                        )
                        return
                    self.send_response(response.status_code)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body_out)))
                    self.end_headers()
                    self.wfile.write(body_out)
                    return
                if cl_header and int(cl_header) == 0:
                    response.close()
                    if provider_id:
                        _record_bridge_fallback(provider_id, model_name)
                    self._do_chatcompletions_fallback(payload, model_name, gateway_url, gateway_key,
                                                     _now_ms())
                    return

                if is_stream:
                    lines = response.iter_lines()
                    first_line = next(lines, None)
                    if first_line is None:
                        response.close()
                        if provider_id:
                            _record_bridge_fallback(provider_id, model_name)
                        self._do_chatcompletions_fallback(payload, model_name, gateway_url, gateway_key, _now_ms())
                        return
                    first_byte_ms = _now_ms()
                    self.send_response(response.status_code)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    _forward_sse_line(first_line)
                    for raw_line in lines:
                        _forward_sse_line(raw_line)
                    self.close_connection = True
                    if provider_id:
                        _clear_bridge_fallback(provider_id, model_name)
                else:
                    body_out = response.read()
                    if not body_out:
                        response.close()
                        if provider_id:
                            _record_bridge_fallback(provider_id, model_name)
                        self._do_chatcompletions_fallback(payload, model_name, gateway_url, gateway_key,
                                                         _now_ms())
                        return
                    first_byte_ms = _now_ms()
                    try:
                        output_tokens = _extract_output_tokens(json.loads(body_out.decode("utf-8")))
                    except Exception:
                        output_tokens = None
                    self.send_response(response.status_code)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body_out)))
                    self.end_headers()
                    self.wfile.write(body_out)
                    if provider_id:
                        _clear_bridge_fallback(provider_id, model_name)
                if response.status_code < 400:
                    _record_bridge_speed(
                        model_name,
                        started_ms=started_ms,
                        first_byte_ms=first_byte_ms,
                        output_tokens=output_tokens,
                        provider_scope=getattr(self.server, "speed_scope", None),
                    )
        except Exception as exc:
            _bridge_error_logger.error("do_POST responses proxy error: %s", exc, exc_info=True)
            self._json(502, {"error": {"message": str(exc)}})

    def _do_chatcompletions_fallback(self, payload, model_name, gateway_url, gateway_key, started_ms):
        """Responses API 不可用时，内部翻译为 Chat Completions 请求并转发。"""
        chat_messages = _responses_input_to_messages(
            payload.get("instructions", ""),
            payload.get("input", []),
        )
        chat_payload = {
            "model": model_name,
            "messages": chat_messages,
            "stream": True,
        }
        chat_tools = _responses_tools_to_chat(payload.get("tools"))
        if chat_tools:
            chat_payload["tools"] = chat_tools

        fwd_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {gateway_key}",
        }
        fwd_headers.update(_copy_passthrough_headers(self.headers))

        translator = _ChatCompletionsToResponsesTranslator(model_name)
        first_byte_ms = None
        output_tokens = None
        try:
            last_body = None
            for target_url in _build_gateway_candidate_urls(gateway_url, "/chat/completions"):
                _bridge_error_logger.info(
                    "FALLBACK to chatcompletions: model=%s url=%s", model_name, target_url
                )
                with httpx.stream(
                    "POST", target_url, headers=fwd_headers, json=chat_payload, timeout=300
                ) as response:
                    if response.status_code >= 400:
                        last_body = response.read().decode("utf-8", errors="replace")
                        continue

                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.end_headers()

                    for raw_line in response.iter_lines():
                        if first_byte_ms is None:
                            first_byte_ms = _now_ms()
                        line = raw_line.strip()
                        if not line:
                            continue
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                continue
                            try:
                                chunk = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                            for event_name, event_payload in translator.process_chunk(chunk):
                                extracted = _extract_output_tokens(event_payload)
                                if extracted is not None:
                                    output_tokens = extracted
                                self._sse(event_name, event_payload)
                    self.close_connection = True
                    _record_bridge_speed(
                        model_name,
                        started_ms=started_ms,
                        first_byte_ms=first_byte_ms,
                        output_tokens=output_tokens,
                        provider_scope=getattr(self.server, "speed_scope", None),
                    )
                    return
            self._json(404, {"error": {"message": last_body or "chat completions fallback failed"}})
        except Exception as exc:
            _bridge_error_logger.error("fallback chatcompletions error: %s", exc, exc_info=True)
            # fallback 也失败，返回 502
            self._json(502, {"error": {"message": str(exc)}})


class _ResponsesToChatHandler(BaseHTTPRequestHandler):
    """Local bridge: accepts Codex's /v1/responses requests,
    translates to /v1/chat/completions, forwards to gateway."""

    server_version = "MMSCodexChatBridge/0.1"

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
        gateway_key = getattr(self.server, "gateway_key", "")
        auth = self.headers.get("authorization", "").strip()
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        key = self.headers.get("x-api-key", "").strip()
        token = key or bearer
        # Accept both bridge token and gateway key (Codex auth.json may use either)
        return token and token in {expected, gateway_key}

    def do_GET(self):
        """Handle /v1/models for Codex model metadata queries."""
        if self.path == "/v1/models":
            advertised_models = list(getattr(self.server, "advertised_models", []) or [])
            model = getattr(self.server, "model_name", "unknown")
            if not advertised_models:
                advertised_models = [model]
            self._json(200, {
                "object": "list",
                "data": [{"id": item, "object": "model", "owned_by": "gateway"} for item in advertised_models if item],
            })
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._authorized():
            self._json(401, {"error": {"message": "invalid token"}})
            return

        length = int(self.headers.get("content-length") or 0)
        raw_body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._json(400, {"error": {"message": "invalid json"}})
            return

        if self.path not in ("/v1/responses", "/responses"):
            self._json(404, {"error": {"message": f"unsupported path: {self.path}"}})
            return

        if httpx is None:
            self._json(502, {"error": {"message": "缺少 httpx"}})
            return

        gateway_url = getattr(self.server, "gateway_url")
        gateway_key = getattr(self.server, "gateway_key")
        model_name = payload.get("model") or getattr(self.server, "model_name", "unknown")

        # Translate Responses → Chat Completions request
        chat_messages = _responses_input_to_messages(
            payload.get("instructions", ""),
            payload.get("input", []),
        )
        chat_payload = {
            "model": model_name,
            "messages": chat_messages,
            "stream": True,
        }
        chat_tools = _responses_tools_to_chat(payload.get("tools"))
        if chat_tools:
            chat_payload["tools"] = chat_tools

        # Forward to gateway /v1/chat/completions
        target_url = _build_gateway_url(gateway_url, "/chat/completions")
        fwd_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {gateway_key}",
        }
        fwd_headers.update(_copy_passthrough_headers(self.headers))

        translator = _ChatCompletionsToResponsesTranslator(model_name)
        started_ms = _now_ms()
        first_byte_ms = None
        output_tokens = None
        try:
            with httpx.stream("POST", target_url, headers=fwd_headers,
                              json=chat_payload, timeout=300) as response:
                if response.status_code >= 400:
                    body = response.read().decode("utf-8", errors="replace")
                    self._json(response.status_code, {"error": {"message": body}})
                    return

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()

                for raw_line in response.iter_lines():
                    if first_byte_ms is None:
                        first_byte_ms = _now_ms()
                    line = raw_line.strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            continue
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        for event_name, event_payload in translator.process_chunk(chunk):
                            extracted = _extract_output_tokens(event_payload)
                            if extracted is not None:
                                output_tokens = extracted
                            self._sse(event_name, event_payload)
                self.close_connection = True
                _record_bridge_speed(
                    model_name,
                    started_ms=started_ms,
                    first_byte_ms=first_byte_ms,
                    output_tokens=output_tokens,
                    provider_scope=getattr(self.server, "speed_scope", None),
                )

        except Exception as exc:
            self._json(502, {"error": {"message": str(exc)}})


@contextmanager
def codex_chatcompletions_bridge(
    gateway_url,
    gateway_key,
    model_name="unknown",
    advertised_models=None,
    speed_scope=None,
    route_status_paths=None,
):
    """Local bridge for Codex: translates /v1/responses → /v1/chat/completions.

    Use this when the gateway only supports Chat Completions for non-GPT models
    but Codex requires Responses API.
    """
    if httpx is None:
        raise RuntimeError("缺少 httpx，无法启动 Codex Chat Completions bridge")
    port = _find_free_port()
    bridge_token = f"mms-bridge-{uuid.uuid4().hex}"
    server = _SilentHTTPServer(("127.0.0.1", port), _ResponsesToChatHandler)
    server.gateway_url = gateway_url
    server.gateway_key = gateway_key
    server.model_name = model_name
    server.advertised_models = list(advertised_models or [])
    server.speed_scope = dict(speed_scope or {})
    server.route_status_paths = list(route_status_paths or [])
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


@contextmanager
def codex_responses_bridge(
    gateway_url,
    gateway_key,
    model_name="unknown",
    advertised_models=None,
    speed_scope=None,
    route_status_paths=None,
    provider_id="",
):
    if httpx is None:
        raise RuntimeError("缺少 httpx，无法启动 Codex responses bridge")
    port = _find_free_port()
    bridge_token = f"mms-bridge-{uuid.uuid4().hex}"
    server = _SilentHTTPServer(("127.0.0.1", port), _ResponsesProxyHandler)
    server.gateway_url = gateway_url
    server.gateway_key = gateway_key
    server.model_name = model_name
    server.advertised_models = list(advertised_models or [])
    server.speed_scope = dict(speed_scope or {})
    server.route_status_paths = list(route_status_paths or [])
    server.bridge_token = bridge_token
    server.provider_id = provider_id
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
def gateway_claude_bridge(
    gateway_url,
    gateway_key,
    light_model=None,
    medium_model=None,
    heavy_model=None,
    advertised_models=None,
    speed_scope=None,
    route_status_paths=None,
    slot_configs=None,
):
    """Local proxy for gateway mode: translates /v1/responses → /v1/messages,
    then forwards to the real gateway so gateways that only support Messages API work correctly.

    heavy_model: 所有请求默认使用的模型名（替换 Claude Code 发来的 claude-* 模型名）。
    medium_model: 智能路由下的中档模型（LLM 分类低置信度时使用）。
    light_model: 智能路由下的轻量模型（明确简单任务时使用）。
    slot_configs: 跨 provider 负载配置。
        {"medium": {"url": str, "key": str}, "light": {"url": str, "key": str}}
        当某个 tier 命中时，使用对应 slot 的 url/key 代替默认 gateway_url/gateway_key。
        未配置的 slot 仍使用默认 gateway。
    """
    if httpx is None:
        raise RuntimeError("缺少 httpx，无法启动 gateway bridge")
    port = _find_free_port()
    bridge_token = f"mms-bridge-{uuid.uuid4().hex}"
    server = _SilentHTTPServer(("127.0.0.1", port), _GatewayBridgeHandler)
    server.gateway_url = gateway_url
    server.gateway_key = gateway_key
    server.bridge_token = bridge_token
    server.heavy_model = heavy_model
    server.medium_model = medium_model
    server.light_model = light_model
    server.advertised_models = list(advertised_models or [])
    server.speed_scope = dict(speed_scope or {})
    server.route_status_paths = list(route_status_paths or [])
    server.slot_configs = slot_configs or {}
    server._sticky_floor = None
    server._sticky_remaining = 0
    server._last_level = "heavy"  # 默认 tier
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
