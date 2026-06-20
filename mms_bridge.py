import json
import logging
import copy
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

try:
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib

from mms_speed_stats import record_model_speed
from mms_state_io import atomic_write_json, locked_state_file, mms_config_root_mode, resolve_mms_config_dir
from mms_provider_profiles import apply_profile_auth_headers, apply_profile_body_patches, profile_model_alias
from mms_i18n import get_language as _get_mms_language, normalize_language as _normalize_mms_language

try:
    from mms_events import emit_event as _emit_event
except ImportError:
    def _emit_event(*_a, **_kw): pass


class _SilentHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that silences BrokenPipeError/ConnectionResetError on client disconnect."""

    def handle_error(self, request, client_address):
        import sys
        exc_type = sys.exc_info()[0]
        if exc_type and issubclass(exc_type, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return  # 客户端断开（Ctrl+C / Escape），静默忽略
        super().handle_error(request, client_address)

httpx = None


def _ensure_httpx():
    global httpx
    if httpx is None:
        try:
            import httpx as _httpx
            httpx = _httpx
        except ImportError:
            pass
    return httpx


def _split_no_proxy_values(no_proxy):
    raw = str(no_proxy or "").strip()
    if not raw:
        return []
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _target_matches_no_proxy(target_url, no_proxy):
    target_url = str(target_url or "").strip()
    if not target_url:
        return False
    try:
        host = (urlsplit(target_url).hostname or "").strip().lower()
    except Exception:
        host = ""
    if not host:
        return False
    for token in _split_no_proxy_values(no_proxy):
        normalized = token.lstrip(".")
        if not normalized:
            continue
        if token == "*" or host == normalized or host.endswith("." + normalized):
            return True
    return False


def _bridge_httpx_kwargs(*, target_url="", proxy_url="", no_proxy=""):
    kwargs = {"trust_env": False}
    normalized_proxy = str(proxy_url or "").strip()
    if normalized_proxy and not _target_matches_no_proxy(target_url, no_proxy):
        kwargs["proxy"] = normalized_proxy
    return kwargs


def _server_bridge_httpx_kwargs(server, target_url=""):
    return _bridge_httpx_kwargs(
        target_url=target_url,
        proxy_url=getattr(server, "proxy_url", ""),
        no_proxy=getattr(server, "no_proxy", ""),
    )


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


_CLAUDE_SENSITIVE_HEADER_PASSTHROUGH = (
    "anthropic-version",
    "anthropic-beta",
)


_CLAUDE_HEADER_PREFIX_PASSTHROUGH = (
    "x-stainless-",
)


_ONE_M_CONTEXT_SUFFIX = "[1m]"
_MIMO_1M_CONTEXT_BETA = "context-1m-2025-08-07"
_MIMO_1M_CONTEXT_SELECTORS = {
    f"mimo-v2.5-pro{_ONE_M_CONTEXT_SUFFIX}",
    f"mimo-v2.5{_ONE_M_CONTEXT_SUFFIX}",
}


def _coerce_context_window(value):
    try:
        window = int(value)
    except Exception:
        return None
    return window if window > 0 else None


def _requests_mimo_1m_context(model_name):
    return _normalize_model_name(model_name) in _MIMO_1M_CONTEXT_SELECTORS


def _model_requests_mimo_1m_context(model_name, context_window=None):
    if _requests_mimo_1m_context(model_name):
        return True
    normalized = _selector_base_model_name(model_name)
    if normalized not in {"mimo-v2.5-pro", "mimo-v2.5"}:
        return False
    window = _coerce_context_window(context_window)
    return bool(window and window >= 1_000_000)


def _merge_header_token(headers, header_name, token):
    if not token:
        return
    existing_key = None
    for key in headers:
        if key.lower() == header_name.lower():
            existing_key = key
            break
    if existing_key is None:
        headers[header_name] = token
        return
    parts = [
        part.strip()
        for part in str(headers.get(existing_key) or "").split(",")
        if part.strip()
    ]
    if token not in parts:
        parts.append(token)
    headers[existing_key] = ",".join(parts)


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


def _claude_passthrough_rules(server, model_name=""):
    header_names = _CLAUDE_HEADER_PASSTHROUGH
    header_prefixes = _CLAUDE_HEADER_PREFIX_PASSTHROUGH
    if getattr(server, "minimal_claude_header_passthrough", False):
        header_names = _CLAUDE_SENSITIVE_HEADER_PASSTHROUGH
        header_prefixes = ()
    if getattr(server, "strip_upstream_user_agent", False):
        header_names = tuple(name for name in header_names if name != "User-Agent")
    if _is_domestic_model(model_name):
        header_names = tuple(name for name in header_names if name != "anthropic-beta")
    return header_names, header_prefixes


# ---------------------------------------------------------------------------
# Bridge mode 缓存：记录 (provider, model) 是否需要 chatcompletions fallback
# ---------------------------------------------------------------------------

_BRIDGE_MODE_CACHE_DIR = os.path.join(
    resolve_mms_config_dir(),
    "cache",
)
_BRIDGE_MODE_CACHE_FILE = os.path.join(_BRIDGE_MODE_CACHE_DIR, "bridge_mode_cache.json")
_bridge_mode_cache_memory = {}  # 内存缓存，避免重复读文件
_BRIDGE_MODE_CACHE_TTL = 6 * 3600
_BRIDGE_MODE_CACHE_LOCK = threading.RLock()

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


def _load_bridge_mode_cache_unlocked():
    global _bridge_mode_cache_memory
    if _bridge_mode_cache_memory:
        return _bridge_mode_cache_memory
    try:
        if os.path.exists(_BRIDGE_MODE_CACHE_FILE):
            with open(_BRIDGE_MODE_CACHE_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            _bridge_mode_cache_memory = loaded if isinstance(loaded, dict) else {}
        else:
            _bridge_mode_cache_memory = {}
    except (OSError, json.JSONDecodeError):
        _bridge_mode_cache_memory = {}
    return _bridge_mode_cache_memory


def _load_bridge_mode_cache():
    """加载 bridge mode 缓存。返回 dict: {\"provider:model\": \"chatcompletions\"}"""
    global _bridge_mode_cache_memory
    with _BRIDGE_MODE_CACHE_LOCK:
        with locked_state_file(_BRIDGE_MODE_CACHE_FILE):
            return _load_bridge_mode_cache_unlocked()


def _save_bridge_mode_cache_unlocked(cache):
    global _bridge_mode_cache_memory
    _bridge_mode_cache_memory = dict(cache) if isinstance(cache, dict) else {}
    atomic_write_json(_BRIDGE_MODE_CACHE_FILE, _bridge_mode_cache_memory)


def _save_bridge_mode_cache(cache):
    """持久化 bridge mode 缓存到文件。"""
    try:
        with _BRIDGE_MODE_CACHE_LOCK:
            with locked_state_file(_BRIDGE_MODE_CACHE_FILE):
                _save_bridge_mode_cache_unlocked(cache)
    except OSError:
        pass


def _bridge_fallback_cache_key(provider_id, model_name, gateway_url=None):
    normalized_provider = str(provider_id or "").strip()
    normalized_model = str(model_name or "").strip()
    normalized_url = str(gateway_url or "").strip().rstrip("/")
    return "::".join(part for part in (normalized_provider, normalized_url, normalized_model) if part)


def _record_bridge_fallback(provider_id, model_name, gateway_url=None):
    """记录 (provider, gateway_url, model) 需要走 chatcompletions bridge。"""
    key = _bridge_fallback_cache_key(provider_id, model_name, gateway_url)
    with _BRIDGE_MODE_CACHE_LOCK:
        with locked_state_file(_BRIDGE_MODE_CACHE_FILE):
            cache = _load_bridge_mode_cache_unlocked()
            entry = cache.get(key)
            should_refresh = not isinstance(entry, dict) or entry.get("mode") != "chatcompletions"
            if not should_refresh:
                ts = entry.get("ts")
                should_refresh = not isinstance(ts, (int, float)) or time.time() - ts > _BRIDGE_MODE_CACHE_TTL
            if should_refresh:
                cache[key] = {"mode": "chatcompletions", "ts": time.time()}
                _save_bridge_mode_cache_unlocked(cache)


_NATIVE_FALLBACK_RETRY_STATUSES = {401, 403, 408, 409, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524}
_NATIVE_FALLBACK_RETRY_TOKENS = {"connect_error", "timeout", "invalid_json", "invalid_text"}


def _native_fallback_retry_sets(route):
    raw = route.get("try_next_on") if isinstance(route, dict) else None
    if not raw:
        return set(_NATIVE_FALLBACK_RETRY_STATUSES), set(_NATIVE_FALLBACK_RETRY_TOKENS)
    statuses = set()
    tokens = set()
    for item in raw:
        try:
            statuses.add(int(item))
            continue
        except Exception:
            pass
        token = str(item or "").strip().lower()
        if token:
            tokens.add(token)
    return statuses, tokens


def _native_fallback_failure_for_body(body):
    try:
        data = json.loads((body or b"").decode("utf-8", errors="replace"))
    except Exception:
        return "invalid_json"
    if not isinstance(data, dict):
        return "invalid_json"
    if data.get("type") == "message":
        content = data.get("content")
        if not isinstance(content, list) or not content:
            return "invalid_text"
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                return None
            if block.get("type") == "text" and str(block.get("text") or "").strip():
                return None
        return "invalid_text"
    if "choices" in data:
        choices = data.get("choices") or []
        choice = choices[0] if choices else {}
        message = choice.get("message") if isinstance(choice, dict) else {}
        if isinstance(message, dict):
            if str(message.get("content") or "").strip() or message.get("tool_calls"):
                return None
        return "invalid_text"
    return "invalid_json"


def _native_fallback_error_token(exc):
    name = exc.__class__.__name__.lower()
    module = exc.__class__.__module__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timeout" in text:
        return "timeout"
    transport_markers = (
        "connect",
        "network",
        "proxy",
        "protocol",
        "readerror",
        "writeerror",
        "transport",
    )
    text_markers = (
        "connection refused",
        "connection reset",
        "connection aborted",
        "server disconnected",
        "remote protocol",
        "broken pipe",
    )
    if "httpx" in module and any(marker in name for marker in transport_markers):
        return "connect_error"
    if any(marker in text for marker in text_markers):
        return "connect_error"
    return ""


def _route_httpx_kwargs(server, route, target_url):
    route = route if isinstance(route, dict) else {}
    return _bridge_httpx_kwargs(
        target_url=target_url,
        proxy_url=route.get("proxy_url", getattr(server, "proxy_url", "")),
        no_proxy=route.get("no_proxy", getattr(server, "no_proxy", "")),
    )


def _fallback_safe_url(url):
    try:
        parsed = urlsplit(str(url or ""))
        return parsed.path or "/"
    except Exception:
        return "/"


def _log_native_fallback(*, from_route, to_route, model_name, reason, request_url):
    evidence = {
        "schema": "cache_transport_evidence.v1",
        "model": model_name,
        "provider_id": str((to_route or {}).get("provider_id") or ""),
        "request_path": _fallback_safe_url(request_url),
        "fallback_reason": reason,
        "from_provider_id": str((from_route or {}).get("provider_id") or ""),
    }
    _bridge_error_logger.warning(
        "native fallback triggered: %s",
        json.dumps(evidence, ensure_ascii=False, sort_keys=True),
    )


def _gateway_route_payload(route, *, gateway_url, gateway_key, server):
    route = route if isinstance(route, dict) else {}
    return {
        "provider_id": str(route.get("provider_id") or getattr(server, "provider_id", "") or ""),
        "provider_profile": str(route.get("provider_profile") or getattr(server, "provider_profile", "") or ""),
        "gateway_url": str(route.get("gateway_url") or gateway_url or "").strip(),
        "gateway_key": str(route.get("gateway_key") or gateway_key or ""),
        "openai_url": str(route.get("openai_url") or getattr(server, "openai_url", "") or "").strip(),
        "proxy_url": str(route.get("proxy_url") or getattr(server, "proxy_url", "") or "").strip(),
        "no_proxy": str(route.get("no_proxy") or getattr(server, "no_proxy", "") or "").strip(),
        "model": str(route.get("model") or "").strip(),
        "allow_model_switch": bool(route.get("allow_model_switch")),
        "protocol": str(route.get("protocol") or "").strip(),
        "fallback_reason": str(route.get("fallback_reason") or "primary"),
        "try_next_on": list(route.get("try_next_on") or []),
    }


def _normalized_bridge_protocol(route):
    protocol = str((route or {}).get("protocol") or "").strip()
    aliases = {
        "responses": "openai_responses",
        "openai": "openai_responses",
        "openai_responses": "openai_responses",
        "chat": "openai_chat_completions",
        "chat_completions": "openai_chat_completions",
        "openai_chat": "openai_chat_completions",
        "openai_chat_completions": "openai_chat_completions",
        "anthropic": "anthropic_messages",
        "messages": "anthropic_messages",
        "anthropic_messages": "anthropic_messages",
    }
    return aliases.get(protocol, protocol or "anthropic_messages")


_OPENAI_MODEL_PREFIXES = ("gpt-", "o1-", "o3-", "o4-", "codex-")
_DOMESTIC_MODEL_PREFIXES = ("glm", "kimi", "k2.6", "mimo", "qwen", "minimax", "deepseek")
_DOMESTIC_THINKING_BLOCK_TYPES = {"thinking", "redacted_thinking"}
_DOMESTIC_THINKING_ALLOW_PREFIXES = ("glm", "kimi", "k2.5", "k2.6", "minimax", "deepseek")
_DOMESTIC_THINKING_BLOCK_PREFIXES = ("mimo",)
_QWEN_THINKING_ALLOW_PREFIXES = ("qwen-plus", "qwen3.5-plus", "qwen3.6-plus", "qwen3-max")
_QWEN_THINKING_BLOCK_PREFIXES = ("qwen-coder", "qwen3-coder")
_DOMESTIC_EFFORT_ALLOW_PREFIXES = ("deepseek",)
_DOMESTIC_ANTHROPIC_HISTORY_COALESCE_PREFIXES = ("kimi", "k2.", "mimo")
_DOMESTIC_REASONING_CONTENT_ROUNDTRIP_PREFIXES = ("deepseek", "mimo", "kimi", "k2.")
_ANTHROPIC_CACHE_CONTROL_ALLOW_PREFIXES = ("qwen-plus", "qwen3.5-plus", "qwen3.6-plus", "qwen3-max")
_KNOWN_IMAGE_INPUT_SUPPORTED_MODEL_NAMES = {
    "gpt-5.3-codex",
    "gpt-5.4",
    "gpt-5.5",
    "k2.6",
    "k2.6-code-preview",
    "kimi-k2.5",
    "kimi-k2.6",
    "mimo-v2.5",
    "mimo-v2-omni",
    "qwen3.5-plus",
    "qwen3.6-flash",
    "qwen3.6-plus",
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
}
_KNOWN_IMAGE_INPUT_SUPPORTED_PREFIXES = (
    "claude-",
    "sonnet-",
    "opus-",
    "haiku-",
    "gemini-",
)
_KNOWN_TEXT_ONLY_IMAGE_UNSUPPORTED_PREFIXES = (
    "deepseek-chat",
    "deepseek-reasoner",
    "deepseek-v4-",
    "glm-5",
    "glm-5.1",
    "glm-5-turbo",
    "kimi-for-coding",
    "mimo-v2.5-pro",
    "mimo-v2-pro",
    "mimo-v2-flash",
    "qwen-plus",
    "qwen3-max",
)

_CODEX_CLI_INSTRUCTIONS_PREFIX = (
    "You are Codex, based on GPT-5. You are running as a coding agent"
    " in the Codex CLI on a user's computer."
)


def _is_openai_model(model_name):
    """检测模型是否为 OpenAI 系列（GPT/o1/o3/o4）。"""
    return isinstance(model_name, str) and model_name.lower().startswith(_OPENAI_MODEL_PREFIXES)


def _normalize_model_name(model_name):
    normalized = str(model_name or "").strip().lower()
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def _is_claude_shell_model(model_name):
    normalized = _normalize_model_name(model_name)
    return not normalized or normalized.startswith(("claude-", "sonnet-", "opus-", "haiku-"))


def _is_domestic_model(model_name):
    return _normalize_model_name(model_name).startswith(_DOMESTIC_MODEL_PREFIXES)


def _selector_base_model_name(model_name):
    normalized = _normalize_model_name(model_name)
    if normalized.endswith(_ONE_M_CONTEXT_SUFFIX):
        normalized = normalized[:-len(_ONE_M_CONTEXT_SUFFIX)]
    return normalized


def _model_capability_entry(model_capabilities, model_name):
    if not isinstance(model_capabilities, dict):
        return {}
    target = _selector_base_model_name(model_name)
    if not target:
        return {}
    for key, value in model_capabilities.items():
        if _selector_base_model_name(key) == target and isinstance(value, dict):
            return value
    return {}


def _model_image_input_override(model_name, model_capabilities):
    caps = _model_capability_entry(model_capabilities, model_name)
    nested = caps.get("capabilities") if isinstance(caps.get("capabilities"), dict) else {}
    for source in (caps, nested):
        for key in ("vision", "supports_vision"):
            if isinstance(source.get(key), bool):
                return bool(source[key])
    return None


def _is_image_content_block(value):
    if not isinstance(value, dict):
        return False
    block_type = str(value.get("type") or "").strip().lower()
    return block_type in {"image", "input_image"}


def _count_image_blocks_recursive(value):
    if isinstance(value, dict):
        if _is_image_content_block(value):
            return 1
        return sum(_count_image_blocks_recursive(child) for child in value.values())
    if isinstance(value, list):
        return sum(_count_image_blocks_recursive(item) for item in value)
    return 0


def _payload_has_image_input(value):
    return _count_image_blocks_recursive(value) > 0


def _model_rejects_image_input(model_name, model_capabilities=None):
    normalized = _selector_base_model_name(model_name)
    if not normalized:
        return True
    image_override = _model_image_input_override(normalized, model_capabilities or {})
    if image_override is not None:
        return not image_override
    if normalized in _KNOWN_IMAGE_INPUT_SUPPORTED_MODEL_NAMES:
        return False
    if normalized.startswith(_KNOWN_IMAGE_INPUT_SUPPORTED_PREFIXES):
        return False
    if normalized.startswith(_KNOWN_TEXT_ONLY_IMAGE_UNSUPPORTED_PREFIXES):
        return True
    # New provider models are text-only until the capability registry or a
    # user override explicitly marks them as image-capable.
    return True


def _unsupported_image_input_payload(model_name):
    model = str(model_name or "").strip() or "selected model"
    return {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": (
                "MMS capability guard: model "
                f"{model} does not support image input. "
                "Open a text-only chat, remove image history, or switch to a vision-capable model such as gpt-5.4."
            ),
        },
    }


def _vision_sidecar_enabled(config):
    if not isinstance(config, dict):
        return False
    value = config.get("enabled", True)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() not in {"0", "false", "no", "off", "disable", "disabled"}


def _vision_sidecar_gateway_url(config):
    if not isinstance(config, dict):
        return ""
    return str(
        config.get("anthropic_base_url")
        or config.get("gateway_url")
        or config.get("base_url")
        or ""
    ).strip().rstrip("/")


def _vision_sidecar_target_url(config):
    gateway_url = _vision_sidecar_gateway_url(config)
    if not gateway_url:
        return ""
    return gateway_url + ("/messages" if gateway_url.endswith("/v1") else "/v1/messages")


def _image_block_for_anthropic(block):
    if not isinstance(block, dict):
        return None
    block_type = str(block.get("type") or "").strip().lower()
    if block_type == "image":
        return copy.deepcopy(block)
    if block_type != "input_image":
        return None
    image_url = block.get("image_url") or block.get("url") or ""
    if isinstance(image_url, dict):
        image_url = image_url.get("url") or ""
    image_url = str(image_url or "").strip()
    if image_url.startswith("data:") and ";base64," in image_url:
        header, data = image_url.split(";base64,", 1)
        media_type = header.replace("data:", "", 1) or "image/png"
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": data,
            },
        }
    if image_url:
        return {
            "type": "image",
            "source": {
                "type": "url",
                "url": image_url,
            },
        }
    return None


def _collect_image_blocks(value):
    images = []

    def walk(node):
        if isinstance(node, dict):
            if _is_image_content_block(node):
                image_block = _image_block_for_anthropic(node)
                if image_block is not None:
                    images.append(image_block)
                return
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(value)
    return images


def _strip_image_blocks(value, *, parent_key=""):
    if isinstance(value, dict):
        if _is_image_content_block(value):
            return None, True
        changed = False
        cleaned = {}
        for key, child in value.items():
            next_child, child_changed = _strip_image_blocks(child, parent_key=str(key))
            changed = changed or child_changed
            if child_changed and next_child is None:
                continue
            cleaned[key] = next_child
        return cleaned, changed
    if isinstance(value, list):
        changed = False
        cleaned = []
        for item in value:
            next_item, item_changed = _strip_image_blocks(item, parent_key=parent_key)
            changed = changed or item_changed
            if item_changed and next_item is None:
                continue
            cleaned.append(next_item)
        if changed and parent_key == "content" and not cleaned:
            cleaned.append({
                "type": "text",
                "text": _VISION_SIDECAR_REMOVED_IMAGE_TEXT,
            })
        return cleaned, changed
    return value, False


def _messages_without_images(messages):
    cleaned = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        next_message, _ = _strip_image_blocks(copy.deepcopy(message))
        cleaned.append(next_message)
    return cleaned


_VISION_SIDECAR_REMOVED_IMAGE_TEXT = "[MMS removed image input; see vision sidecar summary appended to this request.]"
_VISION_SIDECAR_NOTE_PREFIX = "[MMS vision sidecar by "


def _strip_vision_sidecar_text(text):
    if not isinstance(text, str):
        return text, False
    cleaned = text
    changed = False
    if _VISION_SIDECAR_REMOVED_IMAGE_TEXT in cleaned:
        cleaned = cleaned.replace(_VISION_SIDECAR_REMOVED_IMAGE_TEXT, "")
        changed = True
    marker = cleaned.find(_VISION_SIDECAR_NOTE_PREFIX)
    if marker != -1:
        cleaned = cleaned[:marker]
        changed = True
    if changed:
        cleaned = cleaned.rstrip()
    return cleaned, changed


def _strip_vision_sidecar_artifacts(value, *, parent_key=""):
    if isinstance(value, dict):
        if value.get("type") == "text":
            cleaned_text, changed = _strip_vision_sidecar_text(str(value.get("text") or ""))
            if changed and not cleaned_text.strip():
                return None, True
            if changed:
                updated = copy.deepcopy(value)
                updated["text"] = cleaned_text
                return updated, True
            return copy.deepcopy(value), False
        changed = False
        cleaned = {}
        for key, child in value.items():
            next_child, child_changed = _strip_vision_sidecar_artifacts(child, parent_key=str(key))
            changed = changed or child_changed
            if child_changed and next_child is None:
                continue
            cleaned[key] = next_child
        if value.get("type") == "tool_result" and "content" not in cleaned:
            return None, True
        return cleaned, changed
    if isinstance(value, list):
        changed = False
        cleaned = []
        for item in value:
            next_item, item_changed = _strip_vision_sidecar_artifacts(item, parent_key=parent_key)
            changed = changed or item_changed
            if item_changed and next_item is None:
                continue
            cleaned.append(next_item)
        if parent_key == "content" and not cleaned:
            return None, True
        return cleaned, changed
    cleaned_text, changed = _strip_vision_sidecar_text(value)
    if changed and isinstance(cleaned_text, str) and not cleaned_text.strip():
        return None, True
    return cleaned_text, changed


def _messages_without_vision_sidecar_artifacts(messages):
    cleaned = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        next_message, changed = _strip_vision_sidecar_artifacts(copy.deepcopy(message))
        if changed and next_message is None:
            continue
        cleaned.append(next_message)
    return cleaned


def _sanitize_historical_multimodal_message(message):
    next_message, _ = _strip_image_blocks(copy.deepcopy(message))
    next_message, changed = _strip_vision_sidecar_artifacts(next_message)
    if changed and next_message is None:
        return None
    if isinstance(next_message, dict):
        role = str(next_message.get("role") or "").strip().lower()
        if role in {"user", "assistant"} and "content" not in next_message:
            return None
    return next_message


def _sanitize_historical_multimodal_messages(messages):
    if not isinstance(messages, list):
        return messages
    last_assistant_index = -1
    for idx, message in enumerate(messages):
        if isinstance(message, dict) and str(message.get("role") or "").strip().lower() == "assistant":
            last_assistant_index = idx
    if last_assistant_index < 0:
        return copy.deepcopy(messages)
    cleaned = []
    for message in messages[: last_assistant_index + 1]:
        next_message = _sanitize_historical_multimodal_message(message)
        if next_message is None:
            continue
        cleaned.append(next_message)
    for message in messages[last_assistant_index + 1 :]:
        cleaned.append(copy.deepcopy(message))
    return cleaned


def _append_vision_sidecar_text(payload, vision_text, sidecar_model):
    messages = payload.setdefault("messages", [])
    if not isinstance(messages, list):
        messages = []
        payload["messages"] = messages
    note = (
        f"[MMS vision sidecar by {sidecar_model or 'vision model'}]\n"
        "当前主模型不支持 image input；MMS 已先用 vision sidecar 读取用户图片。\n"
        "图片内容如下：\n"
        f"{str(vision_text or '').strip()}"
    ).strip()
    block = {"type": "text", "text": "\n\n" + note}
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            message["content"] = [{"type": "text", "text": content}, block]
        elif isinstance(content, list):
            content.append(block)
        else:
            message["content"] = [block]
        return
    messages.append({"role": "user", "content": [block]})


def _extract_anthropic_text(response_payload):
    parts = []
    if not isinstance(response_payload, dict):
        return ""
    for block in response_payload.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text = str(block.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts).strip()


def _build_vision_sidecar_payload(original_payload, sidecar_model, image_blocks):
    user_text = []
    for message in (original_payload.get("messages") or [])[-8:]:
        if isinstance(message, dict) and message.get("role") == "user":
            text = _extract_user_text(message.get("content", ""))
            if text:
                user_text.append(text)
    prompt = (
        "你是 MMS vision sidecar。任务：只读取图片，为后续 text-only LLM 提供可靠文字上下文。\n"
        "请用中文输出：1) 视觉内容概述 2) 关键文字/OCR 3) 与用户问题相关的细节。\n"
        "不要回答用户最终问题，只描述图片事实。\n"
    )
    if user_text:
        prompt += "\n用户文本上下文：\n" + "\n\n".join(user_text[-4:])
    content = [{"type": "text", "text": prompt}]
    content.extend(copy.deepcopy(image_blocks))
    return {
        "model": sidecar_model,
        "max_tokens": int((original_payload.get("max_tokens") or 1500)),
        "stream": False,
        "messages": [{"role": "user", "content": content}],
    }


def _apply_vision_sidecar(payload, sidecar_config, handler):
    if not _vision_sidecar_enabled(sidecar_config):
        return None, "disabled"
    _ensure_httpx()
    if httpx is None:
        return None, "missing_httpx"
    image_blocks = _collect_image_blocks(payload.get("messages"))
    if not image_blocks:
        return None, "no_collectable_image_blocks"
    sidecar_model = str(sidecar_config.get("model") or "K2.6").strip()
    target_url = _vision_sidecar_target_url(sidecar_config)
    api_key = str(
        sidecar_config.get("api_key")
        or sidecar_config.get("gateway_key")
        or sidecar_config.get("anthropic_api_key")
        or ""
    ).strip()
    if not sidecar_model or not target_url or not api_key:
        return None, "missing_config"
    sidecar_payload = _build_vision_sidecar_payload(payload, sidecar_model, image_blocks)
    provider_id = str(sidecar_config.get("provider_id") or "vision-sidecar").strip()
    provider_profile = str(sidecar_config.get("provider_profile") or sidecar_config.get("profile") or "").strip()
    apply_profile_body_patches(
        sidecar_payload,
        protocol="anthropic_messages",
        provider_id=provider_id,
        profile_id=provider_profile,
        base_url=_vision_sidecar_gateway_url(sidecar_config),
        model_name=sidecar_model,
        thinking_enabled=False,
        reasoning_effort="medium",
    )
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    apply_profile_auth_headers(
        headers,
        protocol="anthropic_messages",
        api_key=api_key,
        provider_id=provider_id,
        profile_id=provider_profile,
        base_url=_vision_sidecar_gateway_url(sidecar_config),
        model_name=sidecar_model,
    )
    response = httpx.post(
        target_url,
        headers=headers,
        json=sidecar_payload,
        timeout=int(sidecar_config.get("timeout", 120) or 120),
        **_route_httpx_kwargs(getattr(handler, "server", None), sidecar_config, target_url),
    )
    if response.status_code >= 400:
        body = response.content.decode("utf-8", errors="replace")
        return None, f"http_{response.status_code}:{body[:300]}"
    try:
        vision_text = _extract_anthropic_text(json.loads(response.content.decode("utf-8")))
    except Exception:
        vision_text = ""
    if not vision_text:
        return None, "empty_response"
    rewritten = copy.deepcopy(payload)
    rewritten["messages"] = _messages_without_images(rewritten.get("messages"))
    _append_vision_sidecar_text(rewritten, vision_text, sidecar_model)
    return rewritten, ""


def _model_policy_capability_bool(model_name, *capability_keys):
    try:
        from mms_capability_resolver import load_default_model_policy

        policy = load_default_model_policy()
    except Exception:
        return None
    models = policy.get("models") if isinstance(policy, dict) else {}
    if not isinstance(models, dict):
        return None
    normalized = _normalize_model_name(model_name)
    for key, entry in models.items():
        if _normalize_model_name(key) != normalized or not isinstance(entry, dict):
            continue
        caps = entry.get("capabilities") if isinstance(entry.get("capabilities"), dict) else {}
        for cap_key in capability_keys:
            if isinstance(caps.get(cap_key), bool):
                return bool(caps[cap_key])
    return None


def _domestic_model_supports_thinking(model_name):
    policy_override = _model_policy_capability_bool(model_name, "thinking", "supports_thinking")
    if policy_override is not None:
        return policy_override
    normalized = _normalize_model_name(model_name)
    if not normalized.startswith(_DOMESTIC_MODEL_PREFIXES):
        return False
    if normalized.startswith(_DOMESTIC_THINKING_BLOCK_PREFIXES):
        return False
    if normalized.startswith(_DOMESTIC_THINKING_ALLOW_PREFIXES):
        return True
    if normalized.startswith("qwen"):
        if normalized.startswith(_QWEN_THINKING_BLOCK_PREFIXES):
            return False
        return normalized.startswith(_QWEN_THINKING_ALLOW_PREFIXES)
    return False


def _should_strip_domestic_thinking_signals(model_name):
    return _is_domestic_model(model_name) and not _domestic_model_supports_thinking(model_name)


def _domestic_model_supports_reasoning_effort(model_name):
    normalized = _normalize_model_name(model_name)
    return normalized.startswith(_DOMESTIC_EFFORT_ALLOW_PREFIXES)


def _domestic_model_requires_reasoning_content_roundtrip(model_name):
    normalized = _normalize_model_name(model_name)
    return normalized.startswith(_DOMESTIC_REASONING_CONTENT_ROUNDTRIP_PREFIXES)


def _domestic_model_requires_anthropic_history_coalescing(model_name):
    normalized = _normalize_model_name(model_name)
    return normalized.startswith(_DOMESTIC_ANTHROPIC_HISTORY_COALESCE_PREFIXES)


def _model_supports_anthropic_cache_control(model_name):
    normalized = _normalize_model_name(model_name)
    return normalized.startswith(_ANTHROPIC_CACHE_CONTROL_ALLOW_PREFIXES)


def _normalize_domestic_reasoning_effort(value, default="high"):
    normalized = str(value or "").strip().lower()
    if normalized == "xhigh":
        return "high"
    if normalized in {"low", "medium", "high"}:
        return normalized
    return default if default in {"low", "medium", "high"} else "high"


def _strip_domestic_thinking_signals(payload):
    """未验证/不支持 Anthropic thinking 的国产模型在转发前剥离相关字段。"""
    payload.pop("thinking", None)

    system = payload.get("system")
    if isinstance(system, list):
        payload["system"] = [
            block
            for block in system
            if not (
                isinstance(block, dict)
                and block.get("type") in _DOMESTIC_THINKING_BLOCK_TYPES
            )
        ]

    for message in payload.get("messages", []):
        if not isinstance(message, dict):
            continue
        message.pop("reasoning_content", None)
        content = message.get("content")
        if isinstance(content, list):
            message["content"] = [
                block
                for block in content
                if not (
                    isinstance(block, dict)
                    and block.get("type") in _DOMESTIC_THINKING_BLOCK_TYPES
                )
            ]


def _assistant_reasoning_content_from_blocks(content):
    parts = []
    for block in _normalize_message_content(content):
        if block.get("type") != "thinking":
            continue
        text = block.get("thinking")
        if isinstance(text, str) and text.strip():
            parts.append(text)
    return "\n\n".join(parts).strip()


def _assistant_message_reasoning_content(message):
    if not isinstance(message, dict):
        return ""
    direct = str(message.get("reasoning_content") or "").strip()
    if direct:
        return direct
    return _assistant_reasoning_content_from_blocks(message.get("content"))


def _anthropic_response_reasoning_content(payload):
    if not isinstance(payload, dict):
        return ""
    direct = str(payload.get("reasoning_content") or "").strip()
    if direct:
        return direct
    return _assistant_reasoning_content_from_blocks(payload.get("content"))


def _assistant_has_thinking_block(content):
    for block in _normalize_message_content(content):
        if block.get("type") != "thinking":
            continue
        text = block.get("thinking")
        if isinstance(text, str) and text.strip():
            return True
    return False


def _assistant_messages_with_reasoning_slots(payload):
    messages = []
    for message in payload.get("messages", []):
        if not isinstance(message, dict):
            continue
        if str(message.get("role", "")).strip() != "assistant":
            continue
        messages.append(message)
    return messages


def _assistant_message_has_tool_use(message):
    if not isinstance(message, dict):
        return False
    if isinstance(message.get("tool_calls"), list) and any(isinstance(item, dict) for item in message["tool_calls"]):
        return True
    for block in _normalize_message_content(message.get("content")):
        if block.get("type") == "tool_use":
            return True
    return False


def _message_has_only_tool_result_blocks(message):
    if not isinstance(message, dict):
        return False
    if str(message.get("role", "")).strip() != "user":
        return False
    content = _normalize_message_content(message.get("content"))
    return bool(content) and all(block.get("type") == "tool_result" for block in content)


def _assistant_content_with_reasoning_fallback(message):
    if not isinstance(message, dict):
        return []
    content = _normalize_message_content(message.get("content"))
    reasoning_content = str(message.get("reasoning_content") or "").strip()
    if reasoning_content and not _assistant_has_thinking_block(content):
        return [{"type": "thinking", "thinking": reasoning_content}] + content
    return content


def _merge_assistant_messages(left, right):
    merged = copy.deepcopy(left) if isinstance(left, dict) else {}
    left_content = _assistant_content_with_reasoning_fallback(left)
    right_content = _assistant_content_with_reasoning_fallback(right)
    merged_content = left_content + right_content
    merged["role"] = "assistant"
    merged["content"] = merged_content

    merged_tool_calls = []
    for tool_calls in ((left or {}).get("tool_calls"), (right or {}).get("tool_calls")):
        if isinstance(tool_calls, list):
            merged_tool_calls.extend(item for item in tool_calls if isinstance(item, dict))
    if merged_tool_calls:
        merged["tool_calls"] = merged_tool_calls
    else:
        merged.pop("tool_calls", None)

    reasoning_content = _assistant_reasoning_content_from_blocks(merged_content)
    if reasoning_content:
        merged["reasoning_content"] = reasoning_content
    else:
        merged.pop("reasoning_content", None)
    return merged


def _merge_user_tool_result_messages(left, right):
    merged = copy.deepcopy(left) if isinstance(left, dict) else {}
    merged["role"] = "user"
    merged["content"] = _normalize_message_content((left or {}).get("content")) + _normalize_message_content((right or {}).get("content"))
    return merged


def _coalesce_domestic_anthropic_history(payload, model_name):
    if not _domestic_model_requires_anthropic_history_coalescing(model_name):
        return
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return

    coalesced = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "")).strip()
        if not coalesced:
            coalesced.append(copy.deepcopy(message))
            continue

        previous = coalesced[-1]
        previous_role = str(previous.get("role", "")).strip()
        if role == "assistant" and previous_role == "assistant":
            coalesced[-1] = _merge_assistant_messages(previous, message)
            continue
        if (
            role == "user"
            and previous_role == "user"
            and _message_has_only_tool_result_blocks(previous)
            and _message_has_only_tool_result_blocks(message)
        ):
            coalesced[-1] = _merge_user_tool_result_messages(previous, message)
            continue
        coalesced.append(copy.deepcopy(message))

    payload["messages"] = coalesced


def _canonicalize_domestic_anthropic_history(payload, model_name):
    _coalesce_domestic_anthropic_history(payload, model_name)
    _preserve_domestic_reasoning_roundtrip(payload, model_name)


def _apply_domestic_thinking_toggle(payload, model_name, *, thinking_enabled):
    if not _domestic_model_supports_thinking(model_name):
        return
    thinking_payload = payload.get("thinking")
    next_thinking = dict(thinking_payload) if isinstance(thinking_payload, dict) else {}
    next_thinking["type"] = "enabled" if thinking_enabled else "disabled"
    payload["thinking"] = next_thinking


def _preserve_domestic_reasoning_roundtrip(payload, model_name):
    if not _domestic_model_requires_reasoning_content_roundtrip(model_name):
        return
    assistant_messages = _assistant_messages_with_reasoning_slots(payload)
    last_reasoning_content = ""
    for message in assistant_messages:
        content = _normalize_message_content(message.get("content"))
        reasoning_content = str(message.get("reasoning_content") or "").strip()
        if reasoning_content and not _assistant_has_thinking_block(content):
            message["content"] = [{"type": "thinking", "thinking": reasoning_content}] + content
            content = message["content"]
        reasoning_content = _assistant_reasoning_content_from_blocks(message.get("content"))
        if reasoning_content:
            # Some OpenAI-compatible relays (notably DeepSeek thinking/tool-use paths)
            # require assistant reasoning_content to be echoed back on continuation
            # even when the client talks to us in Anthropic thinking blocks.
            message["reasoning_content"] = reasoning_content
            last_reasoning_content = reasoning_content
            continue
        if last_reasoning_content and _assistant_message_has_tool_use(message):
            if not _assistant_has_thinking_block(content):
                message["content"] = [{"type": "thinking", "thinking": last_reasoning_content}] + content
            message["reasoning_content"] = last_reasoning_content


def _restore_session_domestic_reasoning_roundtrip(payload, model_name, session_reasoning_content):
    """Rehydrate the latest assistant tool-use group from session-level reasoning."""
    if not _domestic_model_requires_reasoning_content_roundtrip(model_name):
        return False
    reasoning_content = str(session_reasoning_content or "").strip()
    if not reasoning_content:
        return False
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return False

    tail_index = len(messages) - 1
    while tail_index >= 0 and str(messages[tail_index].get("role", "")).strip() != "assistant":
        tail_index -= 1
    if tail_index < 0 or tail_index == len(messages) - 1:
        return False

    group_start = tail_index
    while group_start >= 0 and str(messages[group_start].get("role", "")).strip() == "assistant":
        group_start -= 1
    assistant_group = [
        message
        for message in messages[group_start + 1 : tail_index + 1]
        if isinstance(message, dict) and str(message.get("role", "")).strip() == "assistant"
    ]
    if not assistant_group:
        return False
    if not any(_assistant_message_has_tool_use(message) for message in assistant_group):
        return False
    if any(_assistant_message_reasoning_content(message) for message in assistant_group):
        return False

    first_message = assistant_group[0]
    content = _normalize_message_content(first_message.get("content"))
    if not _assistant_has_thinking_block(content):
        first_message["content"] = [{"type": "thinking", "thinking": reasoning_content}] + content
    first_message["reasoning_content"] = reasoning_content
    return True


def _apply_domestic_reasoning_controls(payload, model_name, *, thinking_enabled=True, reasoning_effort="high"):
    if not _is_domestic_model(model_name):
        return
    if not thinking_enabled:
        _apply_domestic_thinking_toggle(payload, model_name, thinking_enabled=False)
        _strip_domestic_thinking_signals(payload)
        output_config = payload.get("output_config")
        if isinstance(output_config, dict) and "effort" in output_config:
            next_config = dict(output_config)
            next_config.pop("effort", None)
            if next_config:
                payload["output_config"] = next_config
            else:
                payload.pop("output_config", None)
        return
    if _should_strip_domestic_thinking_signals(model_name):
        _strip_domestic_thinking_signals(payload)
        output_config = payload.get("output_config")
        if isinstance(output_config, dict) and "effort" in output_config:
            next_config = dict(output_config)
            next_config.pop("effort", None)
            if next_config:
                payload["output_config"] = next_config
            else:
                payload.pop("output_config", None)
        return
    _apply_domestic_thinking_toggle(payload, model_name, thinking_enabled=True)
    if _domestic_model_supports_reasoning_effort(model_name):
        output_config = payload.get("output_config")
        next_config = dict(output_config) if isinstance(output_config, dict) else {}
        next_config["effort"] = _normalize_domestic_reasoning_effort(reasoning_effort, default="high")
        payload["output_config"] = next_config
    _canonicalize_domestic_anthropic_history(payload, model_name)


def _should_retry_gpt_bridge_without_previous_response_id(status_code, responses_payload, error_text):
    """仅在 continuation 可疑失败时，退回到全量 transcript 重试一次。"""
    if not isinstance(responses_payload, dict) or not responses_payload.get("previous_response_id"):
        return False
    lowered = str(error_text or "").lower()
    if "previous_response_id" in lowered:
        return True
    if status_code not in (401, 403):
        return False
    return any(
        marker in lowered
        for marker in (
            "permission denied",
            "please run /login",
            "run /login",
            '"type":"<nil>"',
            '"type": "<nil>"',
        )
    )


def _truncate_upstream_detail(value, limit=480):
    detail = str(value or "").strip().replace("\n", " ")
    if len(detail) > limit:
        return detail[: limit - 3] + "..."
    return detail


def _extract_upstream_error_summary(body_text):
    body_text = str(body_text or "")
    summary = {
        "body": _truncate_upstream_detail(body_text),
        "message": "",
        "type": "",
        "code": "",
        "request_id": "",
    }
    try:
        data = json.loads(body_text)
    except Exception:
        return summary
    if not isinstance(data, dict):
        return summary
    error = data.get("error")
    if isinstance(error, dict):
        summary["message"] = _truncate_upstream_detail(error.get("message"), 240)
        summary["type"] = _truncate_upstream_detail(error.get("type"), 80)
        summary["code"] = _truncate_upstream_detail(error.get("code"), 80)
        summary["request_id"] = _truncate_upstream_detail(
            error.get("request_id") or data.get("request_id"),
            120,
        )
        return summary
    summary["message"] = _truncate_upstream_detail(data.get("message"), 240)
    summary["type"] = _truncate_upstream_detail(data.get("type"), 80)
    summary["code"] = _truncate_upstream_detail(data.get("code"), 80)
    summary["request_id"] = _truncate_upstream_detail(data.get("request_id"), 120)
    return summary


def _mms_bridge_language(value=""):
    return _normalize_mms_language(value) or _get_mms_language()


def _mms_auth_error_category(status_code, language=""):
    language = _mms_bridge_language(language)
    if int(status_code or 0) == 401:
        if language == "en":
            return (
                "provider_authentication",
                "the selected MMS API-key provider/account rejected authentication",
                "check the selected provider API key/account binding, or switch runtime in MMS",
            )
        return (
            "provider_authentication",
            "当前选择的 MMS API-key provider/account 认证被上游拒绝",
            "检查当前 provider 的 API key/account 绑定，或在 MMS 中切换 runtime",
        )
    if language == "en":
        return (
            "provider_or_model_permission",
            "the selected MMS provider/account reached upstream, but upstream denied this model/path",
            "check provider model permission, relay policy, quota, or switch runtime in MMS",
        )
    return (
        "provider_or_model_permission",
        "请求已到达上游，但上游拒绝当前 model/path，通常是 model 权限、relay policy 或 quota 问题",
        "检查 provider 的 model 权限、relay policy、quota，或在 MMS 中切换 runtime",
    )


def _mms_fail_closed_auth_error_payload(
    status_code,
    body_text,
    *,
    model_name="",
    provider_id="",
    request_url="",
    route_count=1,
    language="",
):
    """将 upstream 401/403 改写成可诊断、但不会误导用户去 login 的 fail-closed 错误。"""
    language = _mms_bridge_language(language)
    status_code = int(status_code or 0)
    model_label = str(model_name or "").strip() or "current model"
    provider_label = str(provider_id or "").strip() or "selected-provider"
    request_path = _fallback_safe_url(request_url)
    upstream = _extract_upstream_error_summary(body_text)
    category, meaning, next_step = _mms_auth_error_category(status_code, language)
    route_note = ""
    try:
        if int(route_count or 0) > 1:
            route_note = f" routes_tried={int(route_count)}."
    except Exception:
        route_note = ""
    upstream_hint = upstream.get("message") or upstream.get("body")
    if language == "en":
        message = (
            f"MMS fail-closed: upstream_provider returned HTTP {status_code} "
            f"({category}). model={model_label} provider={provider_label} path={request_path}."
            f"{route_note} Meaning: {meaning}. "
            "MMS stayed inside the current configured runtime; global OAuth or login fallback was not used. "
            f"Next: {next_step}."
        )
        if upstream_hint:
            message += f" Upstream said: {upstream_hint}"
    else:
        message = (
            f"MMS fail-closed：上游 provider 返回 HTTP {status_code} "
            f"（{category}）。model={model_label} provider={provider_label} path={request_path}."
            f"{route_note} 含义：{meaning}。"
            "MMS 仍停留在当前 configured runtime；没有使用 global OAuth 或 login fallback。"
            f"下一步：{next_step}。"
        )
        if upstream_hint:
            message += f" 上游原文：{upstream_hint}"
    return {
        "type": "error",
        "error": {
            "type": "mms_upstream_auth_error",
            "message": message,
            "mms": {
                "source": "upstream_provider",
                "category": category,
                "status_code": status_code,
                "model": model_label,
                "provider_id": provider_label,
                "request_path": request_path,
                "routes_tried": int(route_count or 1) if str(route_count or "").isdigit() else route_count,
                "global_oauth_fallback": "disabled",
                "next": next_step,
            },
            "upstream": {
                key: value
                for key, value in {
                    "status_code": status_code,
                    "type": upstream.get("type"),
                    "code": upstream.get("code"),
                    "message": upstream.get("message"),
                    "request_id": upstream.get("request_id"),
                    "body": upstream.get("body"),
                }.items()
                if value not in (None, "")
            },
        },
    }


def _record_bridge_blocking_failure(
    server,
    *,
    model_name,
    provider_id="",
    status_code=None,
    body_text="",
    request_url="",
    route_count=1,
    bridge_surface="bridge",
    fallback_mode="auto_default_handover",
    automatic_model_call=False,
):
    """Best-effort L3 rescue hook; never switches runtime or OAuth flow."""
    if not bool(getattr(server, "rescue_enabled", False)):
        return None
    try:
        from mms_rescue import record_blocking_failure, write_fallback_handover

        payload = record_blocking_failure(
            repo_root=getattr(server, "rescue_repo_root", None),
            config_root=getattr(server, "rescue_config_root", None),
            model=str(model_name or getattr(server, "model_name", "") or ""),
            provider_id=str(provider_id or getattr(server, "provider_id", "") or ""),
            status_code=status_code,
            body_text=body_text,
            request_url=request_url,
            request_path=_fallback_safe_url(request_url),
            route_count=route_count,
            bridge_surface=bridge_surface,
            automatic_model_call=bool(automatic_model_call),
            raw_artifacts={"upstream-response.txt": body_text} if body_text not in (None, "") else None,
        )
        if payload:
            _bridge_error_logger.warning(
                "rescue file-only packet written: event_id=%s model=%s provider=%s status=%s",
                payload.get("event_id"),
                model_name,
                provider_id or getattr(server, "provider_id", ""),
                status_code,
            )
            fallback = _current_rescue_fallback(server)
            fallback_model = str(fallback.get("model") or "").strip()
            if fallback_model:
                handover = write_fallback_handover(
                    payload,
                    fallback_model=fallback_model,
                    fallback_cli=str(fallback.get("cli") or getattr(server, "rescue_fallback_cli", "") or "").strip(),
                    mode=fallback_mode,
                    automatic_model_call=bool(automatic_model_call),
                )
                _bridge_error_logger.warning(
                    "rescue fallback handover written: source_event_id=%s fallback_model=%s",
                    handover.get("source_event_id"),
                    fallback_model,
                )
        _append_incident_log(
            server=server,
            model=model_name or getattr(server, "model_name", ""),
            provider_id=provider_id or getattr(server, "provider_id", ""),
            status_code=status_code,
            bridge_surface=bridge_surface,
            request_url=request_url,
            event="blocking_failure",
        )
        if payload and fallback_model:
            artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
            rescue_dir = str(artifacts.get("dir") or "").strip()
            _schedule_rescue_summary(
                server, payload,
                fallback_model=fallback_model,
                rescue_dir=rescue_dir,
            )
        return payload
    except Exception as exc:
        _bridge_error_logger.warning("rescue file-only packet failed: %s", exc, exc_info=True)
        return None


def _schedule_rescue_summary(server, payload, *, fallback_model, rescue_dir):
    """Generate rescue summaries off the response path."""
    try:
        payload_copy = copy.deepcopy(payload)
        worker = threading.Thread(
            target=_generate_rescue_summary,
            args=(server, payload_copy),
            kwargs={"fallback_model": fallback_model, "rescue_dir": rescue_dir},
            name="mms-rescue-summary",
            daemon=True,
        )
        worker.start()
    except Exception as exc:
        _bridge_error_logger.warning("rescue summary scheduling failed: %s", exc, exc_info=True)


def _generate_rescue_summary(server, payload, *, fallback_model, rescue_dir):
    """Call fallback model to generate a session summary; write to rescue_dir/summary.md.

    Best-effort: never raises. The bridge schedules this outside the main response path.
    """
    if not fallback_model or not rescue_dir:
        return
    try:
        routes = _load_rescue_hot_fallback_routes(server, fallback_model)
        if not routes:
            return
        route = routes[0]
        protocol = str(route.get("protocol") or "openai_chat_completions").strip()
        gateway_url = str(route.get("gateway_url") or route.get("openai_base_url") or "").strip()
        gateway_key = str(route.get("gateway_key") or route.get("api_key") or "").strip()
        model_id = str(route.get("model") or fallback_model).strip()
        if not gateway_url or not gateway_key:
            return
        failed = payload.get("failed") if isinstance(payload.get("failed"), dict) else {}
        session_meta = payload.get("session_meta") if isinstance(payload.get("session_meta"), dict) else {}
        task_goal = str(session_meta.get("task_goal") or "").strip()
        failed_model = str(failed.get("model") or payload.get("model") or "").strip()
        status_code = failed.get("status_code")
        failure_kind = str(failed.get("failure_kind") or "").strip()
        error_summary = str(failed.get("error_summary") or "")[:500]
        prompt_parts = [
            "A model API call failed during an MMS session. Generate a concise recovery summary.",
            "",
            f"Failed model: {failed_model}",
            f"Status: {status_code}",
            f"Failure type: {failure_kind}",
        ]
        if task_goal:
            prompt_parts.append(f"Session goal: {task_goal}")
        if error_summary:
            prompt_parts.append(f"Error (truncated): {error_summary[:300]}")
        prompt_parts.extend([
            "",
            "Write a recovery summary in markdown with these sections:",
            "1. **What was being worked on** (from session goal if available)",
            "2. **What failed** (model, status, error type)",
            "3. **Suggested next steps** (how to resume or retry)",
            "",
            "Keep it under 300 words. Be concrete, not generic.",
        ])
        user_msg = "\n".join(prompt_parts)
        request_payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": user_msg}],
            "max_tokens": 800,
        }
        auth_protocol = "anthropic_messages" if protocol == "anthropic_messages" else "openai_chat"
        target_url = _build_gateway_url(
            gateway_url,
            "/messages" if protocol == "anthropic_messages" else "/chat/completions",
        )
        headers = {"Content-Type": "application/json"}
        if protocol == "anthropic_messages":
            headers.update({"x-api-key": gateway_key, "anthropic-version": "2023-06-01"})
        else:
            headers["Authorization"] = f"Bearer {gateway_key}"
        apply_profile_auth_headers(
            headers,
            protocol=auth_protocol,
            api_key=gateway_key,
            provider_id=str(route.get("provider_id") or ""),
            profile_id=str(route.get("provider_profile") or route.get("profile") or ""),
            base_url=gateway_url,
            model_name=model_id,
        )
        httpx_mod = _ensure_httpx()
        if httpx_mod is None:
            return
        with httpx_mod.stream(
            "POST",
            target_url,
            headers=headers,
            json=request_payload,
            timeout=30,
            **_route_httpx_kwargs(server, route, target_url),
        ) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")
        if resp.status_code >= 200 and resp.status_code < 300:
            data = json.loads(resp_body)
            if protocol == "anthropic_messages":
                content = data.get("content") if isinstance(data.get("content"), list) else []
                summary_text = "\n".join(
                    str(block.get("text") or "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ).strip()
            else:
                summary_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if summary_text:
                summary_path = os.path.join(str(rescue_dir), "summary.md")
                os.makedirs(os.path.dirname(summary_path), exist_ok=True)
                with open(summary_path, "w", encoding="utf-8") as f:
                    f.write(f"# Rescue Summary\n\n")
                    f.write(f"- generated_at: {int(time.time())}\n")
                    f.write(f"- fallback_model: {fallback_model}\n")
                    f.write(f"- source_model: {failed_model}\n\n")
                    f.write(summary_text)
                _bridge_error_logger.warning(
                    "rescue summary written: model=%s path=%s", fallback_model, summary_path
                )
    except Exception as exc:
        _bridge_error_logger.warning("rescue summary generation failed: %s", exc, exc_info=True)


def _truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def _rescue_hot_fallback_enabled(server):
    # PAUSED: same-session hot fallback is disabled pending redesign.
    # Keep file-first rescue + fallback handover active without switching the live request.
    return False
    raw = str(os.environ.get("MMS_RESCUE_HOT_FALLBACK", "") or "").strip().lower()
    fallback = _current_rescue_fallback(server)
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return bool(getattr(server, "rescue_enabled", False)) and bool(fallback.get("model"))
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return (
        bool(getattr(server, "rescue_enabled", False))
        and bool(fallback.get("model"))
        and bool(fallback.get("hot_fallback_enabled"))
    )


def _rescue_config_root(server):
    config_root = str(getattr(server, "rescue_config_root", "") or "").strip()
    if config_root:
        return config_root
    try:
        return resolve_mms_config_dir()
    except Exception:
        return ""


def _rescue_requires_latest_approved_bundle(config_root):
    try:
        return mms_config_root_mode(config_root) == "preview"
    except Exception:
        return False


def _read_rescue_fallback_config(config_root):
    root = str(config_root or "").strip()
    if not root:
        return {"model": "", "cli": ""}
    path = os.path.join(root, "config.toml")
    try:
        with open(path, "rb") as handle:
            cfg = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError, TypeError):
        return {"model": "", "cli": ""}
    rescue_cfg = cfg.get("rescue") if isinstance(cfg.get("rescue"), dict) else {}
    hot_value = rescue_cfg.get("hot_fallback_enabled", rescue_cfg.get("enable_hot_fallback", False))
    return {
        "model": str(rescue_cfg.get("fallback_model") or rescue_cfg.get("default_fallback_model") or "").strip(),
        "cli": str(rescue_cfg.get("fallback_cli") or rescue_cfg.get("default_fallback_cli") or "").strip(),
        "hot_fallback_enabled": _truthy(hot_value),
    }


def _current_rescue_fallback(server):
    """Resolve the latest explicit fallback choice without using global OAuth."""
    config_fallback = _read_rescue_fallback_config(_rescue_config_root(server))
    if config_fallback.get("model"):
        return config_fallback
    return {
        "model": str(getattr(server, "rescue_fallback_model", "") or os.environ.get("MMS_RESCUE_FALLBACK_MODEL") or "").strip(),
        "cli": str(getattr(server, "rescue_fallback_cli", "") or os.environ.get("MMS_RESCUE_FALLBACK_CLI") or "").strip(),
        "hot_fallback_enabled": bool(getattr(server, "rescue_hot_fallback_enabled", False)),
    }


def _truthy_route_flag(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _route_declares_cache_sensitive_transport(route):
    route = route if isinstance(route, dict) else {}
    protocol_hints = route.get("protocol_hints")
    hint_sensitive = False
    if isinstance(protocol_hints, dict):
        hint_sensitive = _truthy_route_flag(protocol_hints.get("cache_sensitive_transport"))
    return (
        _truthy_route_flag(route.get("cache_sensitive_transport"))
        or _truthy_route_flag(route.get("cache_sensitive"))
        or hint_sensitive
    )


def _route_declares_anthropic_messages(route):
    route = route if isinstance(route, dict) else {}
    protocols = route.get("protocols")
    if isinstance(protocols, str):
        protocols = [protocols]
    if isinstance(protocols, (list, tuple)):
        return "anthropic_messages" in {str(item).strip() for item in protocols}
    protocol_hints = route.get("protocol_hints")
    if isinstance(protocol_hints, dict):
        hint_protocols = protocol_hints.get("protocols")
        if isinstance(hint_protocols, str):
            hint_protocols = [hint_protocols]
        if isinstance(hint_protocols, (list, tuple)):
            return "anthropic_messages" in {str(item).strip() for item in hint_protocols}
    return False


def _route_should_use_messages_transport(route):
    """Return True when chat/completions is unsafe for a fallback route."""
    return _route_declares_cache_sensitive_transport(route) or _route_declares_anthropic_messages(route)


def _rescue_route_from_export(route, fallback_model):
    route = route if isinstance(route, dict) else {}
    model_id = str(route.get("model_id") or route.get("model") or fallback_model or "").strip()
    if not model_id:
        return None
    anthropic_url = str(route.get("anthropic_base_url") or "").strip().rstrip("/")
    openai_url = str(route.get("openai_base_url") or route.get("gateway_url") or route.get("base_url") or "").strip().rstrip("/")
    if not anthropic_url and openai_url and _route_should_use_messages_transport(route):
        # Shared-root gateways often expose /v1/messages under the same base used
        # for OpenAI-compatible calls; cache-sensitive fallbacks must not hit chat.
        anthropic_url = openai_url
    protocol = _rescue_route_protocol(route, model_id, anthropic_url=anthropic_url, openai_url=openai_url)
    selected_url = anthropic_url if protocol == "anthropic_messages" else openai_url
    api_key = str(route.get("api_key") or route.get("gateway_key") or "").strip()
    if not selected_url or not api_key:
        return None
    return {
        "provider_id": str(route.get("provider_id") or "rescue-fallback").strip(),
        "provider_profile": str(route.get("provider_profile") or route.get("profile") or "").strip(),
        "gateway_url": selected_url,
        "gateway_key": api_key,
        "openai_url": openai_url,
        "anthropic_url": anthropic_url,
        "model": model_id,
        "protocol": protocol,
        "fallback_reason": "rescue_hot_fallback",
        "try_next_on": list(_NATIVE_FALLBACK_RETRY_STATUSES),
    }


def _rescue_route_protocol(route, model_id, *, anthropic_url="", openai_url=""):
    if _route_declares_cache_sensitive_transport(route) and (anthropic_url or openai_url):
        return "anthropic_messages"
    explicit = str(route.get("protocol") or route.get("preferred_protocol") or "").strip()
    if explicit in {"anthropic_messages", "openai_chat_completions"}:
        return explicit
    protocols = route.get("protocols")
    if isinstance(protocols, str):
        protocols = [protocols]
    if isinstance(protocols, (list, tuple)):
        normalized = {str(item).strip() for item in protocols}
        if "anthropic_messages" in normalized and (anthropic_url or openai_url) and not _is_openai_model(model_id):
            return "anthropic_messages"
        if "openai_chat_completions" in normalized and openai_url:
            return "openai_chat_completions"
    if anthropic_url and _is_domestic_model(model_id):
        return "anthropic_messages"
    if openai_url:
        return "openai_chat_completions"
    if anthropic_url:
        return "anthropic_messages"
    return "openai_chat_completions"


def _rescue_routes_from_router_payload(payload, fallback_model, seen):
    model_routes = payload.get("routes") if isinstance(payload.get("routes"), dict) else {}
    entry = model_routes.get(fallback_model)
    if not isinstance(entry, dict):
        return []
    routes = []
    leaves = [entry.get("primary")]
    if isinstance(entry.get("fallbacks"), list):
        leaves.extend(entry.get("fallbacks") or [])
    for leaf in leaves:
        normalized = _rescue_route_from_export(leaf, fallback_model)
        if not normalized:
            continue
        key = (normalized.get("provider_id"), normalized.get("gateway_url"), normalized.get("model"))
        if key in seen:
            continue
        seen.add(key)
        routes.append(normalized)
    return routes


def _load_rescue_hot_fallback_routes(server, fallback_model):
    explicit_routes = getattr(server, "rescue_hot_fallback_routes", None)
    if isinstance(explicit_routes, list) and explicit_routes:
        routes = []
        for item in explicit_routes:
            normalized = _rescue_route_from_export(item, fallback_model)
            if normalized:
                routes.append(normalized)
        return routes

    config_root = _rescue_config_root(server)
    manifest_path = os.path.join(config_root, "generated", "model-registry.latest-approved.json")
    if os.path.exists(manifest_path):
        try:
            import mms_registry

            payload = mms_registry.try_load_latest_approved_payload("router", config_dir=config_root, include_secret=True)
        except Exception:
            payload = {}
        if isinstance(payload, dict) and payload:
            return _rescue_routes_from_router_payload(payload, fallback_model, set())
        return []
    if _rescue_requires_latest_approved_bundle(config_root):
        return []

    candidates = [
        os.path.join(config_root, "generated", "model-routes.json"),
        os.path.join(config_root, "model-routes.json"),
    ]
    seen = set()
    routes = []
    for path in candidates:
        try:
            payload = json.loads(open(path, "r", encoding="utf-8").read())
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        routes.extend(_rescue_routes_from_router_payload(payload, fallback_model, seen))
        if routes:
            return routes
    return routes


def _configure_bridge_rescue(server):
    disabled = str(os.environ.get("MMS_RESCUE_ENABLED", "1")).strip().lower() in {"0", "false", "no", "off"}
    server.rescue_enabled = not disabled
    try:
        cwd = os.getcwd()
    except OSError:
        cwd = ""
    server.rescue_repo_root = str(os.environ.get("MMS_PROJECT_ROOT") or os.environ.get("MMS_CWD") or cwd or "").strip() or None
    server.rescue_config_root = str(os.environ.get("MMS_RESCUE_CONFIG_ROOT") or "").strip() or None
    server.rescue_fallback_model = str(os.environ.get("MMS_RESCUE_FALLBACK_MODEL") or "").strip()
    server.rescue_fallback_cli = str(os.environ.get("MMS_RESCUE_FALLBACK_CLI") or "").strip()
    server.rescue_hot_fallback_enabled = _truthy(os.environ.get("MMS_RESCUE_HOT_FALLBACK"))


def _strip_cache_control(payload):
    """剥离不支持 Anthropic prompt cache 的模型 payload 中的 cache_control 字段。"""
    # 顶层 cache_control
    payload.pop("cache_control", None)
    # system 可能是字符串或 content block 列表
    system = payload.get("system")
    if isinstance(system, list):
        for block in system:
            if isinstance(block, dict):
                block.pop("cache_control", None)
    # messages 中的 content blocks
    for msg in payload.get("messages", []):
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    block.pop("cache_control", None)
    # tools
    for tool in payload.get("tools", []):
        if isinstance(tool, dict):
            tool.pop("cache_control", None)


_ANTHROPIC_BILLING_SYSTEM_LINE_RE = re.compile(
    r"(?im)^[^\n]*x-anthropic-billing-header[^\n]*(?:\n|$)"
)


def _strip_anthropic_billing_system_header(payload):
    """Remove Claude Code's randomized billing-header line from bridged prompts.

    MMS also sets CLAUDE_CODE_ATTRIBUTION_HEADER=0, but this bridge-side guard
    protects third-party providers if a future Claude Code version still emits
    the cache-busting system line.
    """
    if not isinstance(payload, dict):
        return False
    changed = False

    def clean_text(value):
        if not isinstance(value, str) or "x-anthropic-billing-header" not in value.lower():
            return value, False
        cleaned = _ANTHROPIC_BILLING_SYSTEM_LINE_RE.sub("", value)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip("\n")
        return cleaned, cleaned != value

    system = payload.get("system")
    if isinstance(system, str):
        cleaned, item_changed = clean_text(system)
        if item_changed:
            payload["system"] = cleaned
            changed = True
    elif isinstance(system, list):
        next_system = []
        for block in system:
            if not isinstance(block, dict):
                next_system.append(block)
                continue
            next_block = dict(block)
            text_key = "text" if isinstance(next_block.get("text"), str) else "content"
            cleaned, item_changed = clean_text(next_block.get(text_key))
            if item_changed:
                next_block[text_key] = cleaned
                changed = True
            if not (
                str(next_block.get("type") or "").strip().lower() == "text"
                and not str(next_block.get(text_key) or "").strip()
            ):
                next_system.append(next_block)
        if changed:
            payload["system"] = next_system
    return changed


def _needs_chatcompletions_bridge(provider_id, model_name, gateway_url=None):
    """检查 (provider, gateway_url, model) 是否已知需要 chatcompletions bridge。"""
    cache = _load_bridge_mode_cache()
    entry = cache.get(_bridge_fallback_cache_key(provider_id, model_name, gateway_url))
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


def _clear_bridge_fallback(provider_id, model_name, gateway_url=None):
    key = _bridge_fallback_cache_key(provider_id, model_name, gateway_url)
    with _BRIDGE_MODE_CACHE_LOCK:
        with locked_state_file(_BRIDGE_MODE_CACHE_FILE):
            cache = _load_bridge_mode_cache_unlocked()
            if key in cache:
                cache.pop(key, None)
                _save_bridge_mode_cache_unlocked(cache)


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


def _retry_after_delay_seconds(value, *, max_delay=2.0):
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    try:
        delay = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if delay <= 0:
        return 0.0
    return min(delay, max_delay)


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


def _chatcompletions_error_requests_messages(body_text):
    lower = str(body_text or "").lower()
    return (
        "prompt-cache sensitive" in lower
        and "/v1/messages" in lower
        and ("/v1/chat/completions" in lower or "chat/completions" in lower)
    )


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
GEMINI_BRIDGE_SCRIPT = os.path.join(ROOT_DIR, "scripts", "gemini_codeassist_bridge.mjs")

def _incident_log_path(server=None):
    config_root = ""
    if server is not None:
        config_root = _rescue_config_root(server)
    if not config_root:
        try:
            config_root = resolve_mms_config_dir()
        except Exception:
            config_root = os.path.join(os.path.expanduser("~"), ".config", "mms")
    return os.path.join(str(config_root), "logs", "incidents.jsonl")


def _redact_incident_value(value):
    try:
        from mms_rescue import assert_secret_safe, redact_text

        text = redact_text(value)
        assert_secret_safe(text)
        return text
    except Exception:
        raw = str(value or "")
        if not raw:
            return ""
        try:
            parsed = urlsplit(raw)
            if parsed.scheme and parsed.netloc:
                return parsed.path or "/"
        except Exception:
            pass
        return "<REDACTED>"


def _append_incident_log(
    *,
    server=None,
    model="",
    provider_id="",
    status_code=None,
    bridge_surface="",
    request_url="",
    event="blocking_failure",
    detail="",
):
    """Append one JSONL line to the resolved MMS config logs dir. Best-effort, never raises."""
    try:
        incident_path = _incident_log_path(server)
        os.makedirs(os.path.dirname(incident_path), exist_ok=True)
        entry = {
            "ts": int(time.time()),
            "model": _redact_incident_value(model),
            "provider_id": _redact_incident_value(provider_id),
            "status_code": status_code,
            "bridge_surface": _redact_incident_value(bridge_surface),
            "request_url": _redact_incident_value(request_url),
            "event": _redact_incident_value(event),
            "detail": _redact_incident_value(detail),
        }
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        try:
            from mms_rescue import assert_secret_safe

            assert_secret_safe(line)
        except Exception:
            return
        with locked_state_file(incident_path):
            with open(incident_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        pass


def _now_ms():
    return time.monotonic() * 1000.0


def _extract_usage(payload):
    """提取 input_tokens 和 output_tokens（兼容 Anthropic 和 OpenAI 格式）。"""
    if not isinstance(payload, dict):
        return 0, 0
    usage_candidates = []
    for container in (payload, payload.get("response", {}), payload.get("message", {})):
        if isinstance(container, dict):
            u = container.get("usage")
            if isinstance(u, dict):
                usage_candidates.append(u)
    inp = out = 0
    for u in usage_candidates:
        for k in ("input_tokens", "prompt_tokens"):
            v = u.get(k)
            if isinstance(v, (int, float)) and v > 0:
                inp = max(inp, int(v))
        for k in ("output_tokens", "completion_tokens"):
            v = u.get(k)
            if isinstance(v, (int, float)) and v > 0:
                out = max(out, int(v))
    # cache_read/creation 也算 input
    for u in usage_candidates:
        for k in ("cache_read_input_tokens", "cache_creation_input_tokens"):
            v = u.get(k)
            if isinstance(v, (int, float)) and v > 0:
                inp = max(inp, inp)  # cache tokens 已包含在 input_tokens 中
    return inp, out


def _accumulate_usage(server, payload):
    """累加到 server 级 session 统计。"""
    inp, out = _extract_usage(payload)
    if hasattr(server, "session_input_tokens"):
        server.session_input_tokens += inp
        server.session_output_tokens += out
        server.session_request_count += 1


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


def _record_bridge_speed(model_name, *, started_ms, first_byte_ms, output_tokens=None, provider_scope=None, server=None, input_tokens=None):
    # ── Session 累加 ──
    if server and hasattr(server, "session_request_count"):
        server.session_request_count += 1
        server.session_output_tokens += (output_tokens or 0)
        server.session_input_tokens += (input_tokens or 0)
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
    return os.path.join(resolve_mms_config_dir(), "route_status.json")


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


def _write_route_status(tier, model, reason, *, status_paths=None, context_window_tokens=None):
    """写路由状态供 statusline 读取，非阻塞，失败静默。"""
    try:
        payload = {"tier": tier, "model": model, "reason": reason, "ts": time.time()}
        context_window = _coerce_context_window(context_window_tokens)
        if context_window:
            payload["context_window_tokens"] = context_window
        data = json.dumps(payload)
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


def _server_model_context_window(server, model_name, *, prefer_session=True):
    if prefer_session:
        session_window = _coerce_context_window(getattr(server, "session_context_window", None))
        if session_window:
            return session_window
    windows = getattr(server, "context_windows", {}) or {}
    if not isinstance(windows, dict):
        return None
    candidates = []
    normalized = _normalize_model_name(model_name)
    base = _selector_base_model_name(model_name)
    raw = str(model_name or "").strip()
    candidates.extend([raw, normalized, base])
    for key, value in windows.items():
        key_text = str(key or "").strip()
        key_norm = _normalize_model_name(key_text)
        if key_text in candidates or key_norm in candidates or _selector_base_model_name(key_text) in candidates:
            window = _coerce_context_window(value)
            if window:
                return window
    return None


def _route_status_context_kwargs(server, model_name):
    window = _server_model_context_window(server, model_name, prefer_session=True)
    return {"context_window_tokens": window} if window else {}


def _wait_local_server_ready(port, attempts=50, delay=0.1):
    for _ in range(max(1, int(attempts))):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(delay)
                if sock.connect_ex(("127.0.0.1", int(port))) == 0:
                    return True
        except Exception:
            pass
        time.sleep(delay)
    return False


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


def _content_block_to_responses(block, role="user"):
    block_type = block.get("type")
    if block_type == "text":
        # Responses API: user → input_text, assistant → output_text
        text_type = "output_text" if role == "assistant" else "input_text"
        return {"type": text_type, "text": str(block.get("text", ""))}
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

        def flush_text_parts(r=role):
            if text_parts:
                items.append({"role": r, "content": list(text_parts)})
                text_parts.clear()

        for block in _normalize_message_content(message.get("content")):
            block_type = block.get("type")
            if block_type in {"text", "image"}:
                converted = _content_block_to_responses(block, role=role)
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


def _build_codex_payload(
    request_payload,
    model_name,
    incremental_messages=None,
    reasoning_effort="medium",
    *,
    reasoning_enabled=True,
    include_max_output_tokens=True,
):
    messages = incremental_messages if incremental_messages is not None else (request_payload.get("messages") or [])
    payload = {
        "model": model_name,
        "instructions": _system_to_instructions(request_payload.get("system")) or "You are a helpful assistant.",
        "input": _anthropic_messages_to_responses_input(messages),
        "store": False,
        "stream": True,
    }
    if reasoning_enabled:
        payload["reasoning"] = {"effort": reasoning_effort}
    tools = _anthropic_tools_to_responses(request_payload.get("tools"))
    if tools:
        payload["tools"] = tools
    if include_max_output_tokens:
        max_output_tokens = request_payload.get("max_output_tokens")
        if max_output_tokens is None:
            max_output_tokens = request_payload.get("max_tokens")
        if isinstance(max_output_tokens, (int, float)) and max_output_tokens > 0:
            payload["max_output_tokens"] = int(max_output_tokens)
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


def _responses_max_output_tokens(payload):
    if not isinstance(payload, dict):
        return None
    value = payload.get("max_output_tokens")
    if value is None:
        value = payload.get("max_tokens")
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return None


class _AnthropicTranslator:
    def __init__(self, model_name):
        self.model_name = model_name
        self.message_id = f"msg_{uuid.uuid4().hex}"
        self.blocks = []
        self.item_to_index = {}
        self.text_item_to_index = {}
        self.seen_tool_use = False
        self.response_id = None  # 从 response.completed 提取，用于 previous_response_id
        self.reasoning_item_to_index = {}  # reasoning item_id → block index

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
            if item.get("type") == "reasoning":
                index = len(self.blocks)
                self.reasoning_item_to_index[item["id"]] = index
                self.blocks.append({"type": "thinking", "thinking": ""})
                outgoing.append(("content_block_start", {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {"type": "thinking", "thinking": ""},
                }))
            elif item.get("type") == "function_call":
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
                # Only surface the thinking prefix when the upstream emitted
                # actual reasoning summary text; a bare reasoning item alone
                # should not render a misleading "[thinking: 0chars]".
                if not self.blocks[index]["text"] and self.reasoning_item_to_index:
                    thinking_chars = sum(len(b["thinking"]) for b in self.blocks if b.get("type") == "thinking")
                    if thinking_chars > 0:
                        delta = f"[thinking: {thinking_chars}chars]\n\n" + delta
                self.blocks[index]["text"] += delta
                outgoing.append(("content_block_delta", {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "text_delta", "text": delta},
                }))
        elif event_type == "response.reasoning_summary_text.delta":
            item_id = payload.get("item_id")
            index = self.reasoning_item_to_index.get(item_id)
            if index is not None:
                delta = payload.get("delta", "")
                self.blocks[index]["thinking"] += delta
                outgoing.append(("content_block_delta", {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "thinking_delta", "thinking": delta},
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
            elif item_type == "reasoning":
                index = self.reasoning_item_to_index.get(item_id)
                if index is not None:
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
            # 提取 response_id 用于 previous_response_id 续接
            resp_obj = payload.get("response") if isinstance(payload, dict) else None
            if isinstance(resp_obj, dict) and resp_obj.get("id"):
                self.response_id = resp_obj["id"]
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
        line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line)
        line = line.rstrip("\r")
        if not line:
            if data_lines:
                payload_text = "\n".join(data_lines)
                try:
                    payload = json.loads(payload_text)
                except json.JSONDecodeError:
                    payload = None
                if payload is not None:
                    yield current_event or "message", payload
            current_event = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            current_event = line[6:].strip() or "message"
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        payload_text = "\n".join(data_lines)
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            payload = None
        if payload is not None:
            yield current_event or "message", payload


class _AnthropicReasoningStreamTracker:
    """Collect thinking deltas from Anthropic SSE streams for next-turn carry-forward."""

    def __init__(self):
        self._thinking_by_index = {}

    def feed_event(self, event_type, payload):
        if not isinstance(payload, dict):
            return
        if event_type == "content_block_start":
            try:
                index = int(payload.get("index"))
            except (TypeError, ValueError):
                return
            block = payload.get("content_block") if isinstance(payload.get("content_block"), dict) else {}
            if block.get("type") != "thinking":
                return
            parts = self._thinking_by_index.setdefault(index, [])
            initial = str(block.get("thinking") or "")
            if initial:
                parts.append(initial)
            return
        if event_type != "content_block_delta":
            return
        try:
            index = int(payload.get("index"))
        except (TypeError, ValueError):
            return
        delta = payload.get("delta") if isinstance(payload.get("delta"), dict) else {}
        if delta.get("type") != "thinking_delta":
            return
        text = str(delta.get("thinking") or "")
        if not text:
            return
        self._thinking_by_index.setdefault(index, []).append(text)

    def reasoning_content(self):
        parts = []
        for index in sorted(self._thinking_by_index):
            text = "".join(self._thinking_by_index[index]).strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()


def _feed_anthropic_reasoning_sse_line(raw_line, tracker, state):
    if tracker is None or state is None:
        return
    line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line)
    stripped = line.strip()
    if not stripped:
        data_lines = state.get("data_lines", [])
        if data_lines:
            payload_text = "\n".join(data_lines)
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                payload = None
            if payload is not None:
                tracker.feed_event(state.get("event") or "message", payload)
        state["event"] = None
        state["data_lines"] = []
        return
    if stripped.startswith(":"):
        return
    if stripped.startswith("event:"):
        state["event"] = stripped[6:].strip() or "message"
        return
    if stripped.startswith("data:"):
        state.setdefault("data_lines", []).append(stripped[5:].lstrip())


def _bridge_request_to_codex(account, model_name, request_payload, stream_response):
    _ensure_httpx()
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
    with httpx.stream(
        "POST",
        url,
        headers=headers,
        json=payload,
        timeout=300,
        **_bridge_httpx_kwargs(
            target_url=url,
            proxy_url=account.get("proxy"),
            no_proxy=account.get("no_proxy"),
        ),
    ) as response:
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
    bridge_token = f"mms-bridge-{uuid.uuid4().hex}"
    server = _SilentHTTPServer(("127.0.0.1", 0), _BridgeHandler)
    port = int(server.server_address[1])
    server.account = account
    server.model_name = model_name
    server.bridge_token = bridge_token
    server.bridge_source_cli = "codex"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if not _wait_local_server_ready(port):
            raise RuntimeError(f"codex_claude_bridge 未能在本地端口 {port} 就绪")
        yield {
            "base_url": f"http://127.0.0.1:{port}",
            "api_key": bridge_token,
        }
    finally:
        try:
            server._BaseServer__shutdown_request = True
            server.server_close()
            thread.join(timeout=2)
        except (KeyboardInterrupt, Exception):
            pass


@contextmanager
def gemini_claude_bridge(account, model_name):
    bridge_token = f"mms-bridge-{uuid.uuid4().hex}"
    server = _SilentHTTPServer(("127.0.0.1", 0), _BridgeHandler)
    port = int(server.server_address[1])
    server.account = account
    server.model_name = model_name
    server.bridge_token = bridge_token
    server.bridge_source_cli = "gemini"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if not _wait_local_server_ready(port):
            raise RuntimeError(f"gemini_claude_bridge 未能在本地端口 {port} 就绪")
        yield {
            "base_url": f"http://127.0.0.1:{port}",
            "api_key": bridge_token,
        }
    finally:
        try:
            server._BaseServer__shutdown_request = True
            server.server_close()
            thread.join(timeout=2)
        except (KeyboardInterrupt, Exception):
            pass


_SYSTEM_TAG_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)


def _json_resp_to_sse(body: bytes) -> bytes:
    """将 upstream 非流式 JSON 响应转换为 Anthropic SSE 事件流。

    支持 Anthropic Messages 格式和 OpenAI Chat Completions 格式。
    Claude Code 期望 SSE 流，但路由模式下 upstream 返回 JSON，需要在此转换。
    """
    try:
        data = json.loads(body)
    except Exception:
        return (
            "event: error\n"
            "data: "
            + json.dumps(
                {
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": "upstream returned non-JSON body",
                    },
                },
                ensure_ascii=False,
            )
            + "\n\n"
        ).encode("utf-8")

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
            if bt == "text":
                cb_start = {"type": "text", "text": ""}
            elif bt == "thinking":
                # 保留 signature 字段，Anthropic API 校验需要
                cb_start = {"type": "thinking", "thinking": ""}
                for _tk in ("signature",):
                    if blk.get(_tk):
                        cb_start[_tk] = blk[_tk]
            elif bt == "tool_use":
                cb_start = {"type": "tool_use", "id": blk.get("id", ""), "name": blk.get("name", ""), "input": {}}
            else:
                cb_start = {"type": bt}
            events.append(f'event: content_block_start\ndata: {json.dumps({"type": "content_block_start", "index": i, "content_block": cb_start})}\n\n')
            if bt == "text":
                events.append(f'event: content_block_delta\ndata: {json.dumps({"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": blk.get("text", "")}})}\n\n')
            elif bt == "thinking":
                events.append(f'event: content_block_delta\ndata: {json.dumps({"type": "content_block_delta", "index": i, "delta": {"type": "thinking_delta", "thinking": blk.get("thinking", "")}})}\n\n')
            elif bt == "tool_use":
                input_json = json.dumps(blk.get("input", {}))
                events.append(f'event: content_block_delta\ndata: {json.dumps({"type": "content_block_delta", "index": i, "delta": {"type": "input_json_delta", "partial_json": input_json}})}\n\n')
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
        idx = 0
        # 文本内容
        if text:
            events.append(f'event: content_block_start\ndata: {json.dumps({"type": "content_block_start", "index": idx, "content_block": {"type": "text", "text": ""}})}\n\n')
            events.append(f'event: content_block_delta\ndata: {json.dumps({"type": "content_block_delta", "index": idx, "delta": {"type": "text_delta", "text": text}})}\n\n')
            events.append(f'event: content_block_stop\ndata: {json.dumps({"type": "content_block_stop", "index": idx})}\n\n')
            idx += 1
        # tool_calls → Anthropic tool_use 块
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            tool_id = tc.get("id", f"toolu_{idx}")
            tool_name = fn.get("name", "")
            try:
                tool_input = json.loads(fn.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                tool_input = {}
            cb = {"type": "tool_use", "id": tool_id, "name": tool_name, "input": {}}
            events.append(f'event: content_block_start\ndata: {json.dumps({"type": "content_block_start", "index": idx, "content_block": cb})}\n\n')
            events.append(f'event: content_block_delta\ndata: {json.dumps({"type": "content_block_delta", "index": idx, "delta": {"type": "input_json_delta", "partial_json": json.dumps(tool_input)}})}\n\n')
            events.append(f'event: content_block_stop\ndata: {json.dumps({"type": "content_block_stop", "index": idx})}\n\n')
            idx += 1
        # 如果既没有文本也没有 tool_calls，仍然输出空文本块
        if idx == 0:
            events.append(f'event: content_block_start\ndata: {json.dumps({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})}\n\n')
            events.append(f'event: content_block_delta\ndata: {json.dumps({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": ""}})}\n\n')
            events.append(f'event: content_block_stop\ndata: {json.dumps({"type": "content_block_stop", "index": 0})}\n\n')
        stop_reason = "tool_use" if msg.get("tool_calls") else "end_turn"
        events.append(f'event: message_delta\ndata: {json.dumps({"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None}, "usage": {"output_tokens": usage.get("completion_tokens", 0)}})}\n\n')
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
            # 兜底只用实际配置的模型，不硬编码可能不存在的模型
            fallback_models = [
                getattr(self.server, "heavy_model", None),
                getattr(self.server, "medium_model", None),
                getattr(self.server, "light_model", None),
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
        _lb_debug_paths = [os.path.join(resolve_mms_config_dir(), "lb_debug.log")]
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
                            from mms_router import log_route
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

        # ── 模型名映射：通常只将 Claude Code 壳模型替换为真实模型名 ──
        # 用户通过 /model 明确选择的非 Claude 模型必须保留；MiMo [1m]
        # 例外需要把 Claude Code 可校验的 base model 重新映射到本地 selector，
        # 后续转发阶段会发 base model + 1M beta。
        heavy_model = getattr(self.server, "heavy_model", None)
        incoming_model = payload.get("model") if isinstance(payload, dict) else ""
        if heavy_model and "model" in payload:
            heavy_base_model = str(heavy_model or "").replace(_ONE_M_CONTEXT_SUFFIX, "").strip()
            if _is_claude_shell_model(incoming_model):
                payload["model"] = heavy_model
            elif (
                _model_requests_mimo_1m_context(
                    heavy_model,
                    _server_model_context_window(self.server, heavy_model, prefer_session=False),
                )
                and _normalize_model_name(incoming_model) == _normalize_model_name(heavy_base_model)
            ):
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
                from mms_router import classify_task, log_route, STICKY_DECAY_TURNS
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
                        provider_id=getattr(self.server, "provider_id", ""),
                        provider_profile=getattr(self.server, "provider_profile", ""),
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
                    **_route_status_context_kwargs(self.server, payload.get("model", "")),
                )
                _emit_event("started", payload.get("model", ""), note=f"tier={level} reason={reason}")
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
                    **_route_status_context_kwargs(self.server, payload.get("model", "")),
                )
                _emit_event("streaming", payload.get("model", ""), note="tool_continue")
                from mms_router import log_route
                log_route(prev_level, "tool_continue", payload.get("model", "?"), "(tool_result)")
            else:
                # 智能路由开启但没有用户消息，沿用上次 tier
                prev_level = getattr(self.server, "_last_level", "medium")
                _write_route_status(
                    prev_level,
                    payload.get("model", ""),
                    "no_user_msg",
                    status_paths=getattr(self.server, "route_status_paths", None),
                    **_route_status_context_kwargs(self.server, payload.get("model", "")),
                )
                _emit_event("streaming", payload.get("model", ""), note="no_user_msg")
                self.server._last_level = prev_level

        # 无论是否路由，都写 status 供 statusline 显示真实 model
        if not has_routing and "/messages" in path.split("?")[0]:
            _write_route_status(
                "-",
                payload.get("model", ""),
                "direct",
                status_paths=getattr(self.server, "route_status_paths", None),
                **_route_status_context_kwargs(self.server, payload.get("model", "")),
            )
            _emit_event("started", payload.get("model", ""), note="direct")

        # 剥离 query string 再匹配路由（Claude Code 会发 /v1/messages?beta=true）
        path_bare = path.split("?")[0]
        should_record_speed = path_bare != "/v1/messages/count_tokens"

        if path_bare not in ("/v1/messages", "/v1/messages/count_tokens"):
            self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": "not found"}})
            return

        resolved_model_for_guard = str(payload.get("model") or "")
        _strip_anthropic_billing_system_header(payload)
        if isinstance(payload.get("messages"), list):
            payload["messages"] = _messages_without_vision_sidecar_artifacts(payload.get("messages"))
            if _model_rejects_image_input(
                resolved_model_for_guard,
                getattr(self.server, "model_capabilities", {}) or {},
            ):
                payload["messages"] = _sanitize_historical_multimodal_messages(payload.get("messages"))

        if _payload_has_image_input(payload.get("messages")) and _model_rejects_image_input(
            resolved_model_for_guard,
            getattr(self.server, "model_capabilities", {}) or {},
        ):
            sidecar_payload, sidecar_error = _apply_vision_sidecar(
                payload,
                getattr(self.server, "vision_sidecar", {}) or {},
                self,
            )
            if sidecar_payload is not None:
                payload = sidecar_payload
            elif sidecar_error and sidecar_error != "disabled":
                error_payload = _unsupported_image_input_payload(resolved_model_for_guard)
                error_payload["error"]["message"] += f" Vision sidecar failed: {sidecar_error}."
                self._json(400, error_payload)
                return
            else:
                self._json(400, _unsupported_image_input_payload(resolved_model_for_guard))
                return

        _ensure_httpx()
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

        # ── GPT-on-Claude 桥接：仅 OpenAI 系列模型走 Responses API ──
        resolved_model = str(payload.get("model") or "")
        openai_url = getattr(self.server, "openai_url", None)
        if openai_url and path_bare == "/v1/messages" and _is_openai_model(resolved_model):
            self._forward_as_responses(payload, resolved_model, openai_url, gateway_key, should_record_speed)
            return
        # 国产模型继续走 Anthropic Messages 路径（gateway 负责格式转换）

        client_wants_stream = bool(payload.get("stream"))
        base_forward_payload = copy.deepcopy(payload)
        primary_route = _gateway_route_payload(
            {},
            gateway_url=gateway_url,
            gateway_key=gateway_key,
            server=self.server,
        )
        fallback_routes = [
            _gateway_route_payload(route, gateway_url="", gateway_key="", server=self.server)
            for route in getattr(self.server, "native_fallback_routes", []) or []
            if isinstance(route, dict)
            and (
                not route.get("model")
                or _normalize_model_name(route.get("model")) == _normalize_model_name(payload.get("model"))
            )
        ]
        forward_routes = [primary_route] + [route for route in fallback_routes if route.get("gateway_url") and route.get("gateway_key")]
        input_tokens = None

        try:
            for route_index, route in enumerate(forward_routes):
                route_payload = copy.deepcopy(base_forward_payload)
                route_gateway_url = route.get("gateway_url") or gateway_url
                route_gateway_key = route.get("gateway_key") or gateway_key
                route_provider_id = route.get("provider_id") or getattr(self.server, "provider_id", "")
                route_provider_profile = route.get("provider_profile") or getattr(self.server, "provider_profile", "")
                resolved_model = str(route_payload.get("model") or "")
                enable_mimo_1m_context = _model_requests_mimo_1m_context(
                    resolved_model,
                    _server_model_context_window(self.server, resolved_model, prefer_session=False),
                )
                wire_model = profile_model_alias(
                    resolved_model,
                    protocol="anthropic_messages",
                    provider_id=route_provider_id,
                    profile_id=route_provider_profile,
                    base_url=route_gateway_url,
                )
                if wire_model:
                    route_payload["model"] = wire_model
                    resolved_model = wire_model
                if enable_mimo_1m_context:
                    # MiMo Token Plan documents the [1m] selector for Claude Code, but
                    # its Messages API currently accepts the base model plus 1M beta.
                    route_payload["model"] = resolved_model.replace(_ONE_M_CONTEXT_SUFFIX, "")
                    resolved_model = str(route_payload["model"] or "")

                _restore_session_domestic_reasoning_roundtrip(
                    route_payload,
                    resolved_model,
                    getattr(self.server, "_last_reasoning_content", ""),
                )

                profile_id = apply_profile_body_patches(
                    route_payload,
                    protocol="anthropic_messages",
                    provider_id=route_provider_id,
                    profile_id=route_provider_profile,
                    base_url=route_gateway_url,
                    model_name=resolved_model,
                    thinking_enabled=bool(getattr(self.server, "reasoning_enabled", True)),
                    reasoning_effort=getattr(self.server, "reasoning_effort", "high"),
                )
                if profile_id:
                    _canonicalize_domestic_anthropic_history(route_payload, resolved_model)
                if not profile_id and _is_domestic_model(resolved_model):
                    _apply_domestic_reasoning_controls(
                        route_payload,
                        resolved_model,
                        thinking_enabled=bool(getattr(self.server, "reasoning_enabled", True)),
                        reasoning_effort=getattr(self.server, "reasoning_effort", "high"),
                    )
                if not resolved_model.startswith("claude-") and not _model_supports_anthropic_cache_control(resolved_model):
                    _strip_cache_control(route_payload)

                _gw = route_gateway_url.rstrip("/")
                if _gw.endswith("/v1"):
                    path_suffix = path[3:]
                else:
                    path_suffix = path
                target_url = _gw + path_suffix

                fwd_headers = {
                    "Content-Type": "application/json",
                    "x-api-key": route_gateway_key,
                }
                apply_profile_auth_headers(
                    fwd_headers,
                    protocol="anthropic_messages",
                    api_key=route_gateway_key,
                    provider_id=route_provider_id,
                    profile_id=route_provider_profile,
                    base_url=route_gateway_url,
                    model_name=resolved_model,
                )
                claude_passthrough, claude_passthrough_prefixes = _claude_passthrough_rules(
                    self.server,
                    resolved_model,
                )
                fwd_headers.update(
                    _copy_passthrough_headers(
                        self.headers,
                        names=claude_passthrough,
                        prefixes=claude_passthrough_prefixes,
                    )
                )
                if "anthropic-version" not in {name.lower() for name in fwd_headers}:
                    fwd_headers["anthropic-version"] = "2023-06-01"
                if enable_mimo_1m_context:
                    _merge_header_token(fwd_headers, "anthropic-beta", _MIMO_1M_CONTEXT_BETA)

                stream = client_wants_stream
                # 智能路由模式下强制非流式（避免各 provider SSE 格式 / 连接行为不一致）
                if has_routing:
                    stream = False
                    route_payload["stream"] = False
                metrics_model = str(route_payload.get("model") or "")
                route_started_ms = _now_ms()
                first_byte_ms = None
                output_tokens = None
                is_last_route = route_index >= len(forward_routes) - 1
                retry_statuses, retry_tokens = _native_fallback_retry_sets(route)
                response_started = False

                try:
                    if stream:
                        reasoning_tracker = _AnthropicReasoningStreamTracker()
                        reasoning_sse_state = {"event": None, "data_lines": []}
                        with httpx.stream(
                            "POST",
                            target_url,
                            headers=fwd_headers,
                            json=route_payload,
                            timeout=300,
                            **_route_httpx_kwargs(self.server, route, target_url),
                        ) as response:
                            if response.status_code in retry_statuses and not is_last_route:
                                body = response.read().decode("utf-8", errors="replace")
                                next_route = forward_routes[route_index + 1]
                                reason = f"http_{response.status_code}"
                                _log_native_fallback(
                                    from_route=route,
                                    to_route=next_route,
                                    model_name=metrics_model,
                                    reason=reason,
                                    request_url=target_url,
                                )
                                _write_route_status(
                                    "fallback",
                                    metrics_model,
                                    reason,
                                    status_paths=getattr(self.server, "route_status_paths", None),
                                    **_route_status_context_kwargs(self.server, metrics_model),
                                )
                                continue
                            if response.status_code in (401, 403):
                                body = response.read().decode("utf-8", errors="replace")
                                _record_bridge_blocking_failure(
                                    self.server,
                                    model_name=metrics_model,
                                    provider_id=route_provider_id,
                                    status_code=response.status_code,
                                    body_text=body,
                                    request_url=target_url,
                                    route_count=len(forward_routes),
                                    bridge_surface="gateway_messages_stream",
                                )
                                self._json(
                                    502,
                                    _mms_fail_closed_auth_error_payload(
                                        response.status_code,
                                        body,
                                        model_name=metrics_model,
                                        provider_id=route_provider_id,
                                        request_url=target_url,
                                        route_count=len(forward_routes),
                                    ),
                                )
                                return
                            if response.status_code >= 400:
                                _record_bridge_blocking_failure(
                                    self.server,
                                    model_name=metrics_model,
                                    provider_id=route_provider_id,
                                    status_code=response.status_code,
                                    body_text="",
                                    request_url=target_url,
                                    route_count=len(forward_routes),
                                    bridge_surface="gateway_messages_stream",
                                )
                            self.send_response(response.status_code)
                            self.send_header("Content-Type", response.headers.get("content-type", "text/event-stream"))
                            self.send_header("Cache-Control", "no-cache")
                            self.send_header("Connection", "close")
                            self.end_headers()
                            response_started = True
                            for raw_line in response.iter_lines():
                                if first_byte_ms is None:
                                    first_byte_ms = _now_ms()
                                _feed_anthropic_reasoning_sse_line(raw_line, reasoning_tracker, reasoning_sse_state)
                                current_reasoning = reasoning_tracker.reasoning_content()
                                if current_reasoning:
                                    # Tool-result continuations can race ahead of message_stop.
                                    # Publish reasoning as soon as it is visible in the stream.
                                    self.server._last_reasoning_content = current_reasoning
                                stripped = raw_line.strip()
                                if stripped.startswith("data:"):
                                    data_str = stripped[5:].strip()
                                    if data_str and data_str != "[DONE]":
                                        try:
                                            event_payload = json.loads(data_str)
                                        except json.JSONDecodeError:
                                            event_payload = None
                                        if event_payload:
                                            extracted = _extract_output_tokens(event_payload)
                                            if extracted is not None:
                                                output_tokens = extracted
                                            inp, _ = _extract_usage(event_payload)
                                            if inp > 0:
                                                input_tokens = inp
                                self.wfile.write(raw_line.encode("utf-8") + b"\n")
                                if raw_line == "":
                                    self.wfile.flush()
                            _feed_anthropic_reasoning_sse_line("", reasoning_tracker, reasoning_sse_state)
                            self.server._last_reasoning_content = reasoning_tracker.reasoning_content()
                            self.close_connection = True
                        if should_record_speed and response.status_code < 400:
                            _record_bridge_speed(
                                metrics_model,
                                started_ms=route_started_ms,
                                first_byte_ms=first_byte_ms,
                                output_tokens=output_tokens,
                                input_tokens=input_tokens,
                                provider_scope=getattr(self.server, "speed_scope", None),
                                server=self.server,
                            )
                        return

                    response = httpx.post(
                        target_url,
                        headers=fwd_headers,
                        json=route_payload,
                        timeout=300,
                        **_route_httpx_kwargs(self.server, route, target_url),
                    )
                    first_byte_ms = _now_ms()
                    body_out = response.content
                    if response.status_code in retry_statuses and not is_last_route:
                        next_route = forward_routes[route_index + 1]
                        reason = f"http_{response.status_code}"
                        _log_native_fallback(
                            from_route=route,
                            to_route=next_route,
                            model_name=metrics_model,
                            reason=reason,
                            request_url=target_url,
                        )
                        _write_route_status(
                            "fallback",
                            metrics_model,
                            reason,
                            status_paths=getattr(self.server, "route_status_paths", None),
                            **_route_status_context_kwargs(self.server, metrics_model),
                        )
                        continue
                    if response.status_code in (401, 403):
                        body = body_out.decode("utf-8", errors="replace")
                        _record_bridge_blocking_failure(
                            self.server,
                            model_name=metrics_model,
                            provider_id=route_provider_id,
                            status_code=response.status_code,
                            body_text=body,
                            request_url=target_url,
                            route_count=len(forward_routes),
                            bridge_surface="gateway_messages_post",
                        )
                        self._json(
                            502,
                            _mms_fail_closed_auth_error_payload(
                                response.status_code,
                                body,
                                model_name=metrics_model,
                                provider_id=route_provider_id,
                                request_url=target_url,
                                route_count=len(forward_routes),
                            ),
                        )
                        return
                    if response.status_code >= 400:
                        _record_bridge_blocking_failure(
                            self.server,
                            model_name=metrics_model,
                            provider_id=route_provider_id,
                            status_code=response.status_code,
                            body_text=body_out.decode("utf-8", errors="replace"),
                            request_url=target_url,
                            route_count=len(forward_routes),
                            bridge_surface="gateway_messages_post",
                        )
                    if response.status_code == 200 and path_bare == "/v1/messages" and not is_last_route:
                        failure = _native_fallback_failure_for_body(body_out)
                        if failure in retry_tokens:
                            next_route = forward_routes[route_index + 1]
                            _log_native_fallback(
                                from_route=route,
                                to_route=next_route,
                                model_name=metrics_model,
                                reason=failure,
                                request_url=target_url,
                            )
                            _write_route_status(
                                "fallback",
                                metrics_model,
                                failure,
                                status_paths=getattr(self.server, "route_status_paths", None),
                                **_route_status_context_kwargs(self.server, metrics_model),
                            )
                            continue
                    if response.status_code == 200:
                        try:
                            response_payload = json.loads(body_out.decode("utf-8"))
                        except Exception:
                            response_payload = None
                        self.server._last_reasoning_content = _anthropic_response_reasoning_content(response_payload)
                    if body_out:
                        try:
                            output_tokens = _extract_output_tokens(json.loads(body_out.decode("utf-8")))
                        except Exception:
                            output_tokens = None
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
                            started_ms=route_started_ms,
                            first_byte_ms=first_byte_ms,
                            output_tokens=output_tokens,
                            provider_scope=getattr(self.server, "speed_scope", None),
                            server=self.server,
                        )
                    return
                except BrokenPipeError:
                    raise
                except Exception as exc:
                    token = _native_fallback_error_token(exc)
                    if not response_started and token in retry_tokens and not is_last_route:
                        next_route = forward_routes[route_index + 1]
                        _log_native_fallback(
                            from_route=route,
                            to_route=next_route,
                            model_name=str(route_payload.get("model") or ""),
                            reason=token,
                            request_url=target_url,
                        )
                        _write_route_status(
                            "fallback",
                            str(route_payload.get("model") or ""),
                            token,
                            status_paths=getattr(self.server, "route_status_paths", None),
                            **_route_status_context_kwargs(self.server, str(route_payload.get("model") or "")),
                        )
                        continue
                    if response_started:
                        return
                    raise
        except BrokenPipeError:
            return  # 客户端已断开（Ctrl+C），静默忽略
        except Exception as exc:
            try:
                self._json(502, {"type": "error", "error": {"type": "api_error", "message": str(exc)}})
            except BrokenPipeError:
                return


    def _forward_as_responses(self, anthropic_payload, model_name, openai_url, api_key, should_record_speed):
        """GPT-on-Claude: 将 Anthropic Messages 转为 Responses 格式发到 OpenAI 端点。

        流程:
        1. 检查 server._gpt_last_response_id → 有则用 previous_response_id + 增量 input
        2. Anthropic Messages payload → Responses payload
        3. 伪装 Codex CLI 头通过 CRS 验证
        4. 发到 openai_url/v1/responses（强制 stream=true）
        5. 收到 Responses SSE → _AnthropicTranslator 转回 Anthropic SSE → 返回 Claude Code
        6. 从 response.completed 提取 response_id → 存入 server._gpt_last_response_id
        """
        # previous_response_id 续接：只在纯文本对话轮中使用（tool call 轮跳过，避免上游配对失败）
        last_response_id = getattr(self.server, "_gpt_last_response_id", None)
        messages = anthropic_payload.get("messages") or []
        has_tool_result = any(
            any(b.get("type") == "tool_result" for b in _normalize_message_content(m.get("content")))
            for m in messages if m.get("role") == "user"
        )
        reasoning_effort = getattr(self.server, "reasoning_effort", "medium")
        reasoning_enabled = bool(getattr(self.server, "reasoning_enabled", True))
        provider_id = getattr(self.server, "provider_id", "")
        provider_profile = getattr(self.server, "provider_profile", "")
        full_responses_payload = _build_codex_payload(
            anthropic_payload,
            model_name,
            reasoning_effort=reasoning_effort,
            reasoning_enabled=reasoning_enabled,
            include_max_output_tokens=False,
        )
        if last_response_id and not has_tool_result:
            # 取最后一个 assistant 消息之后的所有消息作为增量 input
            last_assistant_idx = -1
            for i, m in enumerate(messages):
                if m.get("role") == "assistant":
                    last_assistant_idx = i
            incremental = messages[last_assistant_idx + 1:] if last_assistant_idx >= 0 else messages
            responses_payload = _build_codex_payload(
                anthropic_payload,
                model_name,
                incremental_messages=incremental,
                reasoning_effort=reasoning_effort,
                reasoning_enabled=reasoning_enabled,
                include_max_output_tokens=False,
            )
            responses_payload["previous_response_id"] = last_response_id
        else:
            responses_payload = dict(full_responses_payload)
        # 确保 instructions 以 Codex 前缀开头（CRS 验证要求）
        for payload in (full_responses_payload, responses_payload):
            orig_instructions = payload.get("instructions", "")
            if not orig_instructions.startswith(_CODEX_CLI_INSTRUCTIONS_PREFIX):
                payload["instructions"] = _CODEX_CLI_INSTRUCTIONS_PREFIX + "\n\n" + orig_instructions
            payload["stream"] = True
            apply_profile_body_patches(
                payload,
                protocol="responses",
                provider_id=provider_id,
                profile_id=provider_profile,
                base_url=openai_url,
                model_name=model_name,
                thinking_enabled=reasoning_enabled,
                reasoning_effort=reasoning_effort,
            )

        # 构造 target URL
        _oai = openai_url.rstrip("/")
        if _oai.endswith("/v1"):
            target_url = _oai + "/responses"
        else:
            target_url = _oai + "/v1/responses"

        # 稳定 session_id 用于 prompt_cache_key 命中缓存
        bridge_token = getattr(self.server, "bridge_token", "")
        session_id = f"mms-gpt-bridge-{bridge_token[-16:]}" if len(bridge_token) > 16 else f"mms-gpt-bridge-{uuid.uuid4().hex}"

        fwd_headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "codex_cli_rs/0.38.0 (Mac OS 26.2.0; arm64) xterm-256color",
            "originator": "codex_cli_rs",
            "session_id": session_id,
        }
        apply_profile_auth_headers(
            fwd_headers,
            protocol="responses",
            api_key=api_key,
            provider_id=provider_id,
            profile_id=provider_profile,
            base_url=openai_url,
            model_name=model_name,
        )

        client_wants_stream = bool(anthropic_payload.get("stream"))
        metrics_model = model_name
        started_ms = _now_ms()
        first_byte_ms = None
        output_tokens = None
        translator = _AnthropicTranslator(model_name)

        try:
            retried_without_previous_response_id = False
            while True:
                with httpx.stream(
                    "POST",
                    target_url,
                    headers=fwd_headers,
                    json=responses_payload,
                    timeout=300,
                    **_server_bridge_httpx_kwargs(self.server, target_url),
                ) as response:
                    if response.status_code >= 400:
                        body = response.read().decode("utf-8", errors="replace")
                        try:
                            err = json.loads(body)
                        except (json.JSONDecodeError, ValueError):
                            err = {"type": "error", "error": {"type": "api_error", "message": body or f"GPT bridge upstream: {response.status_code}"}}
                        error_text = " ".join(
                            part.lower()
                            for part in (
                                body,
                                json.dumps(err, ensure_ascii=False) if isinstance(err, dict) else "",
                            )
                            if part
                        )
                        if (
                            not retried_without_previous_response_id
                            and _should_retry_gpt_bridge_without_previous_response_id(
                                response.status_code,
                                responses_payload,
                                error_text,
                            )
                        ):
                            self.server._gpt_last_response_id = None
                            _bridge_error_logger.warning(
                                "gpt bridge continuation rejected; retrying without previous_response_id: "
                                "status=%s model=%s url=%s",
                                response.status_code,
                                model_name,
                                target_url,
                            )
                            responses_payload = dict(full_responses_payload)
                            retried_without_previous_response_id = True
                            continue
                        if response.status_code in (401, 403):
                            _record_bridge_blocking_failure(
                                self.server,
                                model_name=model_name,
                                provider_id=provider_id,
                                status_code=response.status_code,
                                body_text=body,
                                request_url=target_url,
                                route_count=1,
                                bridge_surface="gpt_on_claude_responses",
                            )
                            self._json(
                                502,
                                _mms_fail_closed_auth_error_payload(
                                    response.status_code,
                                    body,
                                    model_name=model_name,
                                    provider_id=provider_id,
                                    request_url=target_url,
                                ),
                            )
                            return
                        _record_bridge_blocking_failure(
                            self.server,
                            model_name=model_name,
                            provider_id=provider_id,
                            status_code=response.status_code,
                            body_text=body,
                            request_url=target_url,
                            route_count=1,
                            bridge_surface="gpt_on_claude_responses",
                        )
                        self._json(response.status_code, err)
                        return

                    if client_wants_stream:
                        # 流式：Responses SSE → Anthropic SSE → Claude Code
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.send_header("Cache-Control", "no-cache")
                        self.send_header("Connection", "close")
                        self.end_headers()
                        for event_type, event_data in _iter_sse_lines(response):
                            if first_byte_ms is None:
                                first_byte_ms = _now_ms()
                            for ant_event_name, ant_event_payload in translator.process(event_type, event_data):
                                line = f"event: {ant_event_name}\ndata: {json.dumps(ant_event_payload, ensure_ascii=False)}\n\n"
                                self.wfile.write(line.encode("utf-8"))
                                self.wfile.flush()
                        self.close_connection = True
                    else:
                        # 非流式：收集完整 Responses SSE → 合成 Anthropic JSON
                        for event_type, event_data in _iter_sse_lines(response):
                            if first_byte_ms is None:
                                first_byte_ms = _now_ms()
                            translator.process(event_type, event_data)
                        final = translator.final_message()
                        body_out = json.dumps(final, ensure_ascii=False).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(body_out)))
                        self.end_headers()
                        self.wfile.write(body_out)
                break

            # 存回 response_id 供下轮续接
            if translator.response_id:
                self.server._gpt_last_response_id = translator.response_id
            if should_record_speed and first_byte_ms:
                _record_bridge_speed(
                    metrics_model,
                    started_ms=started_ms,
                    first_byte_ms=first_byte_ms,
                    output_tokens=output_tokens,
                    provider_scope=getattr(self.server, "speed_scope", None),
                    server=self.server,
                )
        except BrokenPipeError:
            return
        except Exception as exc:
            # 续接失败时清除 response_id，下轮重新全量发送
            self.server._gpt_last_response_id = None
            try:
                self._json(502, {"type": "error", "error": {"type": "api_error", "message": f"GPT bridge error: {exc}"}})
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


def _responses_reasoning_item_text(item):
    if not isinstance(item, dict):
        return ""

    parts = []

    def _append_text(value):
        if isinstance(value, str):
            text = value.strip()
            if text:
                parts.append(text)

    def _append_part_list(values):
        if isinstance(values, str):
            _append_text(values)
            return
        if not isinstance(values, list):
            return
        for value in values:
            if isinstance(value, str):
                _append_text(value)
                continue
            if not isinstance(value, dict):
                continue
            _append_text(value.get("text"))
            summary_text = value.get("summary_text")
            if isinstance(summary_text, dict):
                _append_text(summary_text.get("text"))
            else:
                _append_text(summary_text)

    _append_text(item.get("text"))
    _append_text(item.get("summary_text"))
    _append_part_list(item.get("summary"))
    _append_part_list(item.get("content"))
    return "\n\n".join(parts).strip()


def _responses_input_to_messages(instructions, input_items, model_name="", *, session_reasoning_content=""):
    """Convert Responses API 'input' array to Chat Completions 'messages'."""
    messages = []
    if instructions:
        messages.append({"role": "system", "content": instructions})

    pending_tool_calls = []
    pending_reasoning_content = ""
    requires_roundtrip = _domestic_model_requires_reasoning_content_roundtrip(model_name)

    def _assistant_message(message):
        if (
            requires_roundtrip
            and pending_reasoning_content
            and isinstance(message, dict)
            and str(message.get("role") or "") == "assistant"
        ):
            message["reasoning_content"] = pending_reasoning_content
        return message

    for item in input_items or []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        role = item.get("role")
        item_reasoning_content = ""
        if requires_roundtrip:
            value = item.get("reasoning_content")
            if isinstance(value, str) and value.strip():
                item_reasoning_content = value.strip()

        if item_type == "reasoning":
            reasoning_text = _responses_reasoning_item_text(item)
            if reasoning_text:
                pending_reasoning_content = (
                    f"{pending_reasoning_content}\n\n{reasoning_text}".strip()
                    if pending_reasoning_content
                    else reasoning_text
                )
            continue

        if item_type == "function_call":
            if item_reasoning_content:
                pending_reasoning_content = item_reasoning_content
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
                messages.append(_assistant_message({"role": "assistant", "tool_calls": list(pending_tool_calls)}))
                pending_tool_calls = []
            messages.append({
                "role": "tool",
                "tool_call_id": item.get("call_id", ""),
                "content": str(item.get("output", "")),
            })
            pending_reasoning_content = ""
            continue

        if role in ("user", "assistant", "system"):
            # Flush pending tool_calls before a new message
            if pending_tool_calls:
                messages.append(_assistant_message({"role": "assistant", "tool_calls": list(pending_tool_calls)}))
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
                if item_reasoning_content:
                    pending_reasoning_content = item_reasoning_content
                # Check if this message also has tool_calls embedded
                messages.append(_assistant_message({"role": "assistant", "content": content}))
            else:
                messages.append({"role": role, "content": content})
                if role != "assistant":
                    pending_reasoning_content = ""
            continue

    # Flush remaining pending tool_calls
    if pending_tool_calls:
        messages.append(_assistant_message({"role": "assistant", "tool_calls": list(pending_tool_calls)}))

    if requires_roundtrip:
        last_reasoning_content = str(session_reasoning_content or "").strip()
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "")
            reasoning_content = str(message.get("reasoning_content") or "").strip()
            if role == "assistant":
                if reasoning_content:
                    last_reasoning_content = reasoning_content
                    continue
                if last_reasoning_content and isinstance(message.get("tool_calls"), list) and message["tool_calls"]:
                    message["reasoning_content"] = last_reasoning_content
                    continue

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


def _chat_messages_to_anthropic_payload(chat_messages, model_name, *, stream=True, max_tokens=None):
    system_parts = []
    messages = []
    for message in chat_messages or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user")
        content = message.get("content")
        if role == "system":
            if content:
                system_parts.append(str(content))
            continue
        if role == "tool":
            messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": str(message.get("tool_call_id") or ""),
                    "content": str(content or ""),
                }],
            })
            continue
        blocks = []
        reasoning_content = ""
        if role == "assistant":
            reasoning_content = str(message.get("reasoning_content") or "").strip()
        if reasoning_content:
            blocks.append({"type": "thinking", "thinking": reasoning_content})
        if content:
            blocks.append({"type": "text", "text": str(content)})
        for tool_call in message.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
            arguments = function.get("arguments") or "{}"
            try:
                parsed_arguments = json.loads(arguments)
            except (TypeError, json.JSONDecodeError):
                parsed_arguments = {}
            blocks.append({
                "type": "tool_use",
                "id": str(tool_call.get("id") or f"toolu_{uuid.uuid4().hex[:24]}"),
                "name": str(function.get("name") or ""),
                "input": parsed_arguments,
            })
        if not blocks:
            blocks.append({"type": "text", "text": ""})
        messages.append({"role": "assistant" if role == "assistant" else "user", "content": blocks})
    payload = {
        "model": model_name,
        "messages": messages or [{"role": "user", "content": [{"type": "text", "text": ""}]}],
        "stream": bool(stream),
        "max_tokens": int(max_tokens) if isinstance(max_tokens, (int, float)) and max_tokens > 0 else 1024,
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    return payload


def _responses_tools_to_anthropic(tools):
    converted = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") != "function":
            continue
        converted.append({
            "name": str(tool.get("name") or ""),
            "description": str(tool.get("description") or ""),
            "input_schema": tool.get("parameters") or {"type": "object", "properties": {}},
        })
    return converted


def _responses_payload_to_anthropic_messages_payload(payload, model_name):
    chat_messages = _responses_input_to_messages(
        payload.get("instructions", ""),
        payload.get("input", []),
        model_name,
    )
    anthropic_payload = _chat_messages_to_anthropic_payload(
        chat_messages,
        model_name,
        stream=True,
        max_tokens=_responses_max_output_tokens(payload),
    )
    tools = _responses_tools_to_anthropic(payload.get("tools"))
    if tools:
        anthropic_payload["tools"] = tools
    return anthropic_payload


def _chat_delta_reasoning_content(delta):
    if not isinstance(delta, dict):
        return ""
    value = delta.get("reasoning_content")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        text = value.get("text")
        return text if isinstance(text, str) else ""
    if not isinstance(value, list):
        return ""
    parts = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


class _ChatCompletionsToResponsesTranslator:
    """Translate Chat Completions streaming chunks to Responses API SSE events.
    Matches the real OpenAI Responses API format that Codex expects."""

    def __init__(self, model_name, response_id=None):
        self.model_name = model_name
        self.response_id = response_id or f"resp_{uuid.uuid4().hex[:24]}"
        self.msg_item_id = f"msg_{uuid.uuid4().hex[:24]}"
        self.reasoning_item_id = f"rs_{uuid.uuid4().hex[:24]}"
        self.text_content = ""
        self.reasoning_content = ""
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

    def _normalized_reasoning_content(self):
        return self.reasoning_content.strip()

    def _reasoning_output_item(self):
        reasoning_content = self._normalized_reasoning_content()
        if not reasoning_content:
            return None
        return {
            "type": "reasoning",
            "id": self.reasoning_item_id,
            "summary": [{"type": "summary_text", "text": reasoning_content}],
            "status": "completed",
        }

    def _message_output_item(self, *, status="completed"):
        item = {
            "type": "message",
            "id": self.msg_item_id,
            "role": "assistant",
            "status": status,
            "content": [{"type": "output_text", "annotations": [], "text": self.text_content}],
        }
        reasoning_content = self._normalized_reasoning_content()
        if reasoning_content:
            item["reasoning_content"] = reasoning_content
        return item

    def _tool_call_output_item(self, tc_info, *, status="completed"):
        item = {
            "type": "function_call",
            "id": tc_info["item_id"],
            "call_id": tc_info["id"],
            "name": tc_info["name"],
            "arguments": tc_info["arguments"],
            "status": status,
        }
        reasoning_content = self._normalized_reasoning_content()
        if reasoning_content:
            item["reasoning_content"] = reasoning_content
        return item

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
        reasoning_delta = _chat_delta_reasoning_content(delta)
        if reasoning_delta:
            self.reasoning_content += reasoning_delta

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
                    "item": self._tool_call_output_item(tc_info),
                    "sequence_number": self._seq_num(),
                }))

            # Build output for completed response
            output_items = []
            reasoning_item = self._reasoning_output_item()
            if reasoning_item:
                output_items.append(reasoning_item)
            if self.text_content or not self.tool_calls:
                output_items.append(self._message_output_item())
            for idx, tc_info in sorted(self.tool_calls.items()):
                output_items.append(self._tool_call_output_item(tc_info))

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
            "item": self._message_output_item(),
            "sequence_number": self._seq_num(),
        }))
        return events


class _AnthropicMessagesToResponsesTranslator:
    """Translate Anthropic Messages SSE chunks to Responses API SSE events."""

    def __init__(self, model_name):
        self.model_name = model_name
        self.response_id = f"resp_{uuid.uuid4().hex[:24]}"
        self.message_item_id = f"msg_{uuid.uuid4().hex[:24]}"
        self.started = False
        self.text_part_added = False
        self.text_content = ""
        self.block_to_tool = {}
        self.tool_arguments = {}
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

    def _ensure_started(self):
        if self.started:
            return []
        self.started = True
        return [
            ("response.created", {
                "type": "response.created",
                "response": self._response_obj("in_progress"),
            }),
            ("response.in_progress", {
                "type": "response.in_progress",
                "response": self._response_obj("in_progress"),
            }),
            ("response.output_item.added", {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {
                    "type": "message",
                    "id": self.message_item_id,
                    "role": "assistant",
                    "status": "in_progress",
                    "content": [],
                },
                "sequence_number": self._seq_num(),
            }),
        ]

    def _ensure_text_part(self):
        if self.text_part_added:
            return []
        self.text_part_added = True
        return [("response.content_part.added", {
            "type": "response.content_part.added",
            "item_id": self.message_item_id,
            "output_index": 0,
            "content_index": 0,
            "part": {"type": "output_text", "annotations": [], "text": ""},
            "sequence_number": self._seq_num(),
        })]

    def process(self, event_type, payload):
        outgoing = []
        if event_type in {"message_start", "content_block_start", "content_block_delta", "message_delta", "message_stop"}:
            outgoing.extend(self._ensure_started())
        if event_type == "content_block_start":
            index = int(payload.get("index") or 0)
            block = payload.get("content_block") if isinstance(payload.get("content_block"), dict) else {}
            if block.get("type") == "text":
                outgoing.extend(self._ensure_text_part())
            elif block.get("type") == "tool_use":
                item_id = f"fc_{uuid.uuid4().hex[:24]}"
                self.block_to_tool[index] = {
                    "item_id": item_id,
                    "call_id": str(block.get("id") or item_id),
                    "name": str(block.get("name") or ""),
                }
                self.tool_arguments[index] = ""
                outgoing.append(("response.output_item.added", {
                    "type": "response.output_item.added",
                    "output_index": index + 1,
                    "item": {
                        "type": "function_call",
                        "id": item_id,
                        "call_id": self.block_to_tool[index]["call_id"],
                        "name": self.block_to_tool[index]["name"],
                        "arguments": "",
                        "status": "in_progress",
                    },
                    "sequence_number": self._seq_num(),
                }))
        elif event_type == "content_block_delta":
            index = int(payload.get("index") or 0)
            delta = payload.get("delta") if isinstance(payload.get("delta"), dict) else {}
            if delta.get("type") == "text_delta":
                text = str(delta.get("text") or "")
                outgoing.extend(self._ensure_text_part())
                self.text_content += text
                outgoing.append(("response.output_text.delta", {
                    "type": "response.output_text.delta",
                    "item_id": self.message_item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "delta": text,
                    "sequence_number": self._seq_num(),
                }))
            elif delta.get("type") == "input_json_delta" and index in self.block_to_tool:
                partial = str(delta.get("partial_json") or "")
                self.tool_arguments[index] = self.tool_arguments.get(index, "") + partial
                outgoing.append(("response.function_call_arguments.delta", {
                    "type": "response.function_call_arguments.delta",
                    "item_id": self.block_to_tool[index]["item_id"],
                    "output_index": index + 1,
                    "delta": partial,
                    "sequence_number": self._seq_num(),
                }))
        elif event_type == "content_block_stop":
            index = int(payload.get("index") or 0)
            if index in self.block_to_tool:
                tool = self.block_to_tool[index]
                arguments = self.tool_arguments.get(index, "")
                outgoing.append(("response.function_call_arguments.done", {
                    "type": "response.function_call_arguments.done",
                    "item_id": tool["item_id"],
                    "output_index": index + 1,
                    "arguments": arguments,
                    "sequence_number": self._seq_num(),
                }))
                outgoing.append(("response.output_item.done", {
                    "type": "response.output_item.done",
                    "output_index": index + 1,
                    "item": {
                        "type": "function_call",
                        "id": tool["item_id"],
                        "call_id": tool["call_id"],
                        "name": tool["name"],
                        "arguments": arguments,
                        "status": "completed",
                    },
                    "sequence_number": self._seq_num(),
                }))
        elif event_type == "message_stop":
            output = [{
                "type": "message",
                "id": self.message_item_id,
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "annotations": [], "text": self.text_content}],
            }]
            outgoing.append(("response.output_text.done", {
                "type": "response.output_text.done",
                "item_id": self.message_item_id,
                "output_index": 0,
                "content_index": 0,
                "text": self.text_content,
                "sequence_number": self._seq_num(),
            }))
            outgoing.append(("response.content_part.done", {
                "type": "response.content_part.done",
                "item_id": self.message_item_id,
                "output_index": 0,
                "content_index": 0,
                "part": {"type": "output_text", "annotations": [], "text": self.text_content},
                "sequence_number": self._seq_num(),
            }))
            outgoing.append(("response.output_item.done", {
                "type": "response.output_item.done",
                "output_index": 0,
                "item": output[0],
                "sequence_number": self._seq_num(),
            }))
            outgoing.append(("response.completed", {
                "type": "response.completed",
                "response": self._response_obj("completed", output),
            }))
        return outgoing


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

    def _json_with_headers(self, status, payload, extra_headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if isinstance(extra_headers, dict):
            for header_name, value in extra_headers.items():
                if value is None or value == "":
                    continue
                self.send_header(str(header_name), str(value))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _try_rescue_hot_fallback(
        self,
        payload,
        *,
        failed_model,
        failed_provider_id,
        status_code,
        body_text,
        request_url,
        route_count=1,
    ):
        if not _rescue_hot_fallback_enabled(self.server):
            return False
        fallback = _current_rescue_fallback(self.server)
        fallback_model = str(fallback.get("model") or "").strip()
        if not fallback_model or _normalize_model_name(fallback_model) == _normalize_model_name(failed_model):
            return False
        self.server.rescue_fallback_model = fallback_model
        self.server.rescue_fallback_cli = str(fallback.get("cli") or getattr(self.server, "rescue_fallback_cli", "") or "").strip()
        routes = _load_rescue_hot_fallback_routes(self.server, fallback_model)
        if not routes:
            return False
        route = routes[0]
        rescue_payload = _record_bridge_blocking_failure(
            self.server,
            model_name=failed_model,
            provider_id=failed_provider_id,
            status_code=status_code,
            body_text=body_text,
            request_url=request_url,
            route_count=route_count,
            bridge_surface="codex_responses_proxy",
            fallback_mode="hot_fallback_attempt",
            automatic_model_call=True,
        )
        if not rescue_payload:
            return False
        try:
            _emit_event(
                "fallback",
                fallback_model,
                note=f"rescue_hot_fallback from={failed_model} status={status_code} provider={route.get('provider_id') or '-'}",
            )
        except Exception:
            pass
        _bridge_error_logger.warning(
            "rescue hot fallback attempting: failed_model=%s status=%s fallback_model=%s provider=%s",
            failed_model,
            status_code,
            fallback_model,
            route.get("provider_id"),
        )
        fallback_payload = copy.deepcopy(payload)
        fallback_payload["model"] = route.get("model") or fallback_model
        if route.get("protocol") == "anthropic_messages":
            self._do_anthropic_messages_fallback(
                fallback_payload,
                route.get("model") or fallback_model,
                route.get("gateway_url") or route.get("anthropic_url") or "",
                route.get("gateway_key") or "",
                _now_ms(),
                route=route,
            )
        else:
            self._do_chatcompletions_fallback(
                fallback_payload,
                route.get("model") or fallback_model,
                route.get("gateway_url") or route.get("openai_url") or "",
                route.get("gateway_key") or "",
                _now_ms(),
                route=route,
            )
        return True

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
        if not self._authorized():
            self._json(401, {"error": {"message": "invalid token"}})
            return
        if self.path.split("?", 1)[0] == "/v1/models":
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

        _ensure_httpx()
        if httpx is None:
            self._json(502, {"error": {"message": "缺少 httpx"}})
            return

        gateway_url = getattr(self.server, "gateway_url")
        gateway_key = getattr(self.server, "gateway_key")
        requested_model_name = payload.get("model") or getattr(self.server, "model_name", "unknown")
        started_ms = _now_ms()
        first_byte_ms = None
        output_tokens = None
        base_forward_payload = copy.deepcopy(payload)
        primary_route = _gateway_route_payload(
            {},
            gateway_url=gateway_url,
            gateway_key=gateway_key,
            server=self.server,
        )
        fallback_routes = [
            _gateway_route_payload(route, gateway_url="", gateway_key="", server=self.server)
            for route in getattr(self.server, "native_fallback_routes", []) or []
            if isinstance(route, dict)
            and (
                not route.get("model")
                or _normalize_model_name(route.get("model")) == _normalize_model_name(requested_model_name)
            )
        ]
        forward_routes = [primary_route] + [route for route in fallback_routes if route.get("gateway_url") and route.get("gateway_key")]

        try:
            for route_index, route in enumerate(forward_routes):
                payload = copy.deepcopy(base_forward_payload)
                route_gateway_url = route.get("gateway_url") or gateway_url
                route_gateway_key = route.get("gateway_key") or gateway_key
                provider_id = route.get("provider_id") or getattr(self.server, "provider_id", "")
                provider_profile = route.get("provider_profile") or getattr(self.server, "provider_profile", "")
                model_name = payload.get("model") or getattr(self.server, "model_name", "unknown")
                reasoning_enabled = bool(getattr(self.server, "reasoning_enabled", True))
                reasoning_effort = getattr(self.server, "reasoning_effort", "high")
                profile_id = apply_profile_body_patches(
                    payload,
                    protocol="responses",
                    provider_id=provider_id,
                    profile_id=provider_profile,
                    base_url=route_gateway_url,
                    model_name=model_name,
                    thinking_enabled=reasoning_enabled,
                    reasoning_effort=reasoning_effort,
                )
                if not profile_id and reasoning_enabled:
                    reasoning_payload = payload.get("reasoning")
                    next_reasoning = dict(reasoning_payload) if isinstance(reasoning_payload, dict) else {}
                    next_reasoning["effort"] = reasoning_effort
                    payload["reasoning"] = next_reasoning
                elif not profile_id:
                    payload.pop("reasoning", None)
                target_url = _build_gateway_url(route_gateway_url, "/responses")
                fwd_headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {route_gateway_key}",
                }
                apply_profile_auth_headers(
                    fwd_headers,
                    protocol="responses",
                    api_key=route_gateway_key,
                    provider_id=provider_id,
                    profile_id=provider_profile,
                    base_url=route_gateway_url,
                    model_name=model_name,
                )
                fwd_headers.update(_copy_passthrough_headers(self.headers))
                is_last_route = route_index >= len(forward_routes) - 1
                retry_statuses, _retry_tokens = _native_fallback_retry_sets(route)

                # 检查是否已知需要 chatcompletions fallback
                if provider_id and _needs_chatcompletions_bridge(provider_id, model_name, route_gateway_url):
                    self._do_chatcompletions_fallback(
                        payload,
                        model_name,
                        route_gateway_url,
                        route_gateway_key,
                        started_ms,
                        route=route,
                    )
                    return

                with httpx.stream(
                    "POST",
                    target_url,
                    headers=fwd_headers,
                    json=payload,
                    timeout=300,
                    **_route_httpx_kwargs(self.server, route, target_url),
                ) as response:
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
                    try:
                        content_length = int(cl_header) if cl_header else None
                    except (TypeError, ValueError):
                        content_length = None
                    if response.status_code >= 400:
                        body_out = response.read()
                        body_text = body_out.decode("utf-8", errors="replace")
                        if response.status_code in retry_statuses and not is_last_route:
                            next_route = forward_routes[route_index + 1]
                            reason = f"http_{response.status_code}"
                            _log_native_fallback(
                                from_route=route,
                                to_route=next_route,
                                model_name=model_name,
                                reason=reason,
                                request_url=target_url,
                            )
                            _write_route_status(
                                "fallback",
                                model_name,
                                reason,
                                status_paths=getattr(self.server, "route_status_paths", None),
                                **_route_status_context_kwargs(self.server, model_name),
                            )
                            continue
                        if _should_try_chatcompletions_fallback(response.status_code, body_text):
                            response.close()
                            if provider_id:
                                _record_bridge_fallback(provider_id, model_name, route_gateway_url)
                            self._do_chatcompletions_fallback(
                                payload,
                                model_name,
                                route_gateway_url,
                                route_gateway_key,
                                _now_ms(),
                                route=route,
                            )
                            return
                        if response.status_code in (401, 403):
                            if self._try_rescue_hot_fallback(
                                payload,
                                failed_model=model_name,
                                failed_provider_id=provider_id,
                                status_code=response.status_code,
                                body_text=body_text,
                                request_url=target_url,
                                route_count=len(forward_routes),
                            ):
                                return
                            _record_bridge_blocking_failure(
                                self.server,
                                model_name=model_name,
                                provider_id=provider_id,
                                status_code=response.status_code,
                                body_text=body_text,
                                request_url=target_url,
                                route_count=len(forward_routes),
                                bridge_surface="codex_responses_proxy",
                            )
                            self._json(
                                502,
                                _mms_fail_closed_auth_error_payload(
                                    response.status_code,
                                    body_text,
                                    model_name=model_name,
                                    provider_id=provider_id,
                                    request_url=target_url,
                                    route_count=len(forward_routes),
                                ),
                            )
                            return
                        if self._try_rescue_hot_fallback(
                            payload,
                            failed_model=model_name,
                            failed_provider_id=provider_id,
                            status_code=response.status_code,
                            body_text=body_text,
                            request_url=target_url,
                            route_count=len(forward_routes),
                        ):
                            return
                        _record_bridge_blocking_failure(
                            self.server,
                            model_name=model_name,
                            provider_id=provider_id,
                            status_code=response.status_code,
                            body_text=body_text,
                            request_url=target_url,
                            route_count=len(forward_routes),
                            bridge_surface="codex_responses_proxy",
                        )
                        self.send_response(response.status_code)
                        self.send_header("Content-Type", content_type)
                        self.send_header("Content-Length", str(len(body_out)))
                        self.end_headers()
                        self.wfile.write(body_out)
                        return
                    if content_length == 0:
                        response.close()
                        self._do_chatcompletions_fallback(
                            payload,
                            model_name,
                            route_gateway_url,
                            route_gateway_key,
                            _now_ms(),
                            route=route,
                        )
                        return

                    if is_stream:
                        lines = response.iter_lines()
                        first_line = next(lines, None)
                        if first_line is None:
                            response.close()
                            self._do_chatcompletions_fallback(
                                payload,
                                model_name,
                                route_gateway_url,
                                route_gateway_key,
                                _now_ms(),
                                route=route,
                            )
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
                            _clear_bridge_fallback(provider_id, model_name, route_gateway_url)
                    else:
                        body_out = response.read()
                        if not body_out:
                            response.close()
                            self._do_chatcompletions_fallback(
                                payload,
                                model_name,
                                route_gateway_url,
                                route_gateway_key,
                                _now_ms(),
                                route=route,
                            )
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
                            _clear_bridge_fallback(provider_id, model_name, route_gateway_url)
                    if response.status_code < 400:
                        _record_bridge_speed(
                            model_name,
                            started_ms=started_ms,
                            first_byte_ms=first_byte_ms,
                            output_tokens=output_tokens,
                            provider_scope=getattr(self.server, "speed_scope", None),
                            server=self.server,
                        )
                    return
        except Exception as exc:
            _bridge_error_logger.error("do_POST responses proxy error: %s", exc, exc_info=True)
            self._json(502, {"error": {"message": str(exc)}})

    def _do_chatcompletions_fallback(self, payload, model_name, gateway_url, gateway_key, started_ms, route=None, return_result=False):
        """Responses API 不可用时，内部翻译为 Chat Completions 请求并转发。"""
        route = route if isinstance(route, dict) else {}
        provider_id = route.get("provider_id") or getattr(self.server, "provider_id", "")
        provider_profile = route.get("provider_profile") or getattr(self.server, "provider_profile", "")
        reasoning_enabled = bool(getattr(self.server, "reasoning_enabled", True))
        reasoning_effort = getattr(self.server, "reasoning_effort", "high")
        chat_messages = _responses_input_to_messages(
            payload.get("instructions", ""),
            payload.get("input", []),
            model_name,
            session_reasoning_content=getattr(self.server, "_last_reasoning_content", ""),
        )
        chat_payload = {
            "model": model_name,
            "messages": chat_messages,
            "stream": True,
        }
        max_output_tokens = _responses_max_output_tokens(payload)
        if max_output_tokens is not None:
            chat_payload["max_tokens"] = max_output_tokens
        chat_tools = _responses_tools_to_chat(payload.get("tools"))
        if chat_tools:
            chat_payload["tools"] = chat_tools
        apply_profile_body_patches(
            chat_payload,
            protocol="openai_chat",
            provider_id=provider_id,
            profile_id=provider_profile,
            base_url=gateway_url,
            model_name=model_name,
            thinking_enabled=reasoning_enabled,
            reasoning_effort=reasoning_effort,
        )

        fwd_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {gateway_key}",
        }
        apply_profile_auth_headers(
            fwd_headers,
            protocol="openai_chat",
            api_key=gateway_key,
            provider_id=provider_id,
            profile_id=provider_profile,
            base_url=gateway_url,
            model_name=model_name,
        )
        fwd_headers.update(_copy_passthrough_headers(self.headers))

        translator = _ChatCompletionsToResponsesTranslator(model_name)
        first_byte_ms = None
        output_tokens = None
        try:
            last_body = None
            last_status = 404
            for target_url in _build_gateway_candidate_urls(gateway_url, "/chat/completions"):
                _bridge_error_logger.info(
                    "FALLBACK to chatcompletions: model=%s url=%s", model_name, target_url
                )
                retry_remaining = 1
                while True:
                    with httpx.stream(
                        "POST",
                        target_url,
                        headers=fwd_headers,
                        json=chat_payload,
                        timeout=300,
                        **_route_httpx_kwargs(self.server, route, target_url),
                    ) as response:
                        if response.status_code == 429:
                            last_status = response.status_code
                            last_body = response.read().decode("utf-8", errors="replace")
                            retry_after = response.headers.get("Retry-After")
                            delay = _retry_after_delay_seconds(retry_after)
                            if retry_remaining > 0 and delay > 0:
                                retry_remaining -= 1
                                _bridge_error_logger.warning(
                                    "chatcompletions fallback rate limited: model=%s url=%s retry_after=%s",
                                    model_name,
                                    target_url,
                                    retry_after,
                                )
                                time.sleep(delay)
                                continue
                            if return_result:
                                return {
                                    "sent": False,
                                    "status": response.status_code,
                                    "body": last_body or "chat completions fallback rate limited",
                                    "url": target_url,
                                }
                            _record_bridge_blocking_failure(
                                self.server,
                                model_name=model_name,
                                provider_id=provider_id,
                                status_code=response.status_code,
                                body_text=last_body,
                                request_url=target_url,
                                bridge_surface="codex_chatcompletions_fallback",
                            )
                            self._json_with_headers(
                                429,
                                {"error": {"message": last_body or "chat completions fallback rate limited"}},
                                extra_headers={"Retry-After": retry_after} if retry_after else None,
                            )
                            return
                        if response.status_code >= 400:
                            last_status = response.status_code
                            last_body = response.read().decode("utf-8", errors="replace")
                            break

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
                                    current_reasoning = translator._normalized_reasoning_content()
                                    if current_reasoning:
                                        self.server._last_reasoning_content = current_reasoning
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
                            server=self.server,
                        )
                        return {"sent": True, "status": 200, "url": target_url}
                    break
            if _chatcompletions_error_requests_messages(last_body) and gateway_url and gateway_key:
                if return_result:
                    return {
                        "sent": False,
                        "status": last_status,
                        "body": last_body or "",
                        "url": target_url if "target_url" in locals() else "",
                        "failure_token": "invalid_text",
                    }
                messages_route = dict(route)
                messages_route["protocol"] = "anthropic_messages"
                messages_route["fallback_reason"] = "cache_sensitive_messages_retry"
                _bridge_error_logger.warning(
                    "chatcompletions fallback rejected for cache-sensitive transport; retrying messages: model=%s",
                    model_name,
                )
                _append_incident_log(
                    server=self.server,
                    model=model_name,
                    provider_id=provider_id,
                    status_code=last_status,
                    bridge_surface="chatcompletions_to_messages_retry",
                    request_url=target_url,
                    event="cache_sensitive_channel_switch",
                    detail="chatcompletions rejected; retrying via anthropic messages",
                )
                self._do_anthropic_messages_fallback(
                    payload,
                    model_name,
                    gateway_url,
                    gateway_key,
                    started_ms,
                    route=messages_route,
                )
                return
            if return_result:
                return {
                    "sent": False,
                    "status": last_status,
                    "body": last_body or "chat completions fallback failed",
                    "url": target_url if "target_url" in locals() else "",
                }
            _record_bridge_blocking_failure(
                self.server,
                model_name=model_name,
                provider_id=provider_id,
                status_code=last_status,
                body_text=last_body or "",
                request_url=target_url if "target_url" in locals() else "",
                bridge_surface="codex_chatcompletions_fallback",
            )
            self._json(last_status, {"error": {"message": last_body or "chat completions fallback failed"}})
        except Exception as exc:
            _bridge_error_logger.error("fallback chatcompletions error: %s", exc, exc_info=True)
            if return_result:
                return {
                    "sent": False,
                    "status": 502,
                    "body": str(exc),
                    "url": target_url if "target_url" in locals() else "",
                    "failure_token": _native_fallback_error_token(exc),
                }
            # fallback 也失败，返回 502
            self._json(502, {"error": {"message": str(exc)}})

    def _do_openai_responses_fallback_route(self, payload, model_name, gateway_url, gateway_key, started_ms, route=None):
        """Forward one mixed-protocol fallback route through OpenAI Responses."""
        route = route if isinstance(route, dict) else {}
        provider_id = route.get("provider_id") or getattr(self.server, "provider_id", "")
        provider_profile = route.get("provider_profile") or getattr(self.server, "provider_profile", "")
        reasoning_enabled = bool(getattr(self.server, "reasoning_enabled", True))
        reasoning_effort = getattr(self.server, "reasoning_effort", "high")
        route_payload = copy.deepcopy(payload)
        route_payload["model"] = model_name
        profile_id = apply_profile_body_patches(
            route_payload,
            protocol="responses",
            provider_id=provider_id,
            profile_id=provider_profile,
            base_url=gateway_url,
            model_name=model_name,
            thinking_enabled=reasoning_enabled,
            reasoning_effort=reasoning_effort,
        )
        if not profile_id and reasoning_enabled:
            reasoning_payload = route_payload.get("reasoning")
            next_reasoning = dict(reasoning_payload) if isinstance(reasoning_payload, dict) else {}
            next_reasoning["effort"] = reasoning_effort
            route_payload["reasoning"] = next_reasoning
        elif not profile_id:
            route_payload.pop("reasoning", None)

        target_url = _build_gateway_url(gateway_url, "/responses")
        fwd_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {gateway_key}",
        }
        apply_profile_auth_headers(
            fwd_headers,
            protocol="responses",
            api_key=gateway_key,
            provider_id=provider_id,
            profile_id=provider_profile,
            base_url=gateway_url,
            model_name=model_name,
        )
        fwd_headers.update(_copy_passthrough_headers(self.headers))

        first_byte_ms = None
        output_tokens = None
        try:
            with httpx.stream(
                "POST",
                target_url,
                headers=fwd_headers,
                json=route_payload,
                timeout=300,
                **_route_httpx_kwargs(self.server, route, target_url),
            ) as response:
                content_type = response.headers.get("content-type", "application/json")
                if response.status_code >= 400:
                    body_text = response.read().decode("utf-8", errors="replace")
                    return {
                        "sent": False,
                        "status": response.status_code,
                        "body": body_text,
                        "url": target_url,
                    }

                if "text/event-stream" in content_type.lower():
                    self.send_response(response.status_code)
                    self.send_header("Content-Type", content_type)
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
                    body_out = response.read()
                    if not body_out:
                        return {
                            "sent": False,
                            "status": 502,
                            "body": "empty responses fallback body",
                            "url": target_url,
                            "failure_token": "invalid_text",
                        }
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

                _record_bridge_speed(
                    model_name,
                    started_ms=started_ms,
                    first_byte_ms=first_byte_ms,
                    output_tokens=output_tokens,
                    provider_scope=getattr(self.server, "speed_scope", None),
                    server=self.server,
                )
                return {"sent": True, "status": response.status_code, "url": target_url}
        except Exception as exc:
            token = _native_fallback_error_token(exc)
            return {
                "sent": False,
                "status": 502,
                "body": str(exc),
                "url": target_url,
                "failure_token": token,
            }

    def _do_anthropic_messages_fallback(self, payload, model_name, gateway_url, gateway_key, started_ms, route=None):
        """Codex Responses hot fallback through Anthropic Messages transport."""
        route = route if isinstance(route, dict) else {}
        reasoning_enabled = bool(getattr(self.server, "reasoning_enabled", True))
        reasoning_effort = getattr(self.server, "reasoning_effort", "high")

        def _forward_routes():
            primary = _gateway_route_payload(route, gateway_url=gateway_url, gateway_key=gateway_key, server=self.server)
            routes = [primary]
            if route.get("include_native_fallbacks"):
                requested_model = _normalize_model_name(model_name)
                for item in getattr(self.server, "native_fallback_routes", []) or []:
                    if not isinstance(item, dict):
                        continue
                    item_model = str(item.get("model") or "").strip()
                    allow_model_switch = bool(item.get("allow_model_switch"))
                    if item_model and not allow_model_switch and _normalize_model_name(item_model) != requested_model:
                        continue
                    next_route = _gateway_route_payload(item, gateway_url="", gateway_key="", server=self.server)
                    if not next_route.get("gateway_url") or not next_route.get("gateway_key"):
                        continue
                    routes.append(next_route)
            return routes

        forward_routes = _forward_routes()
        last_body = None
        last_status = 404
        last_target_url = ""
        try:
            for route_index, active_route in enumerate(forward_routes):
                active_model = str(active_route.get("model") or model_name or "").strip()
                active_gateway_url = active_route.get("gateway_url") or gateway_url
                active_gateway_key = active_route.get("gateway_key") or gateway_key
                provider_id = active_route.get("provider_id") or getattr(self.server, "provider_id", "")
                provider_profile = active_route.get("provider_profile") or getattr(self.server, "provider_profile", "")
                is_last_route = route_index >= len(forward_routes) - 1
                retry_statuses, _retry_tokens = _native_fallback_retry_sets(active_route)
                active_protocol = _normalized_bridge_protocol(active_route)

                if active_protocol == "openai_responses":
                    result = self._do_openai_responses_fallback_route(
                        payload,
                        active_model,
                        active_gateway_url,
                        active_gateway_key,
                        started_ms,
                        route=active_route,
                    )
                    if result.get("sent"):
                        return
                    last_status = int(result.get("status") or 502)
                    last_body = str(result.get("body") or "")
                    last_target_url = str(result.get("url") or "")
                    failure_token = str(result.get("failure_token") or "").strip()
                    can_try_next = (
                        (last_status in retry_statuses)
                        or (failure_token and failure_token in _retry_tokens)
                    )
                    if not is_last_route and can_try_next:
                        next_route = forward_routes[route_index + 1]
                        _log_native_fallback(
                            from_route=active_route,
                            to_route=next_route,
                            model_name=active_model,
                            reason=failure_token or f"http_{last_status}",
                            request_url=last_target_url,
                        )
                        continue
                    break

                if active_protocol == "openai_chat_completions":
                    if is_last_route:
                        self._do_chatcompletions_fallback(
                            payload,
                            active_model,
                            active_gateway_url,
                            active_gateway_key,
                            started_ms,
                            route=active_route,
                        )
                        return
                    result = self._do_chatcompletions_fallback(
                        payload,
                        active_model,
                        active_gateway_url,
                        active_gateway_key,
                        started_ms,
                        route=active_route,
                        return_result=True,
                    )
                    if result and result.get("sent"):
                        return
                    last_status = int((result or {}).get("status") or 502)
                    last_body = str((result or {}).get("body") or "")
                    last_target_url = str((result or {}).get("url") or "")
                    failure_token = str((result or {}).get("failure_token") or "").strip()
                    can_try_next = (
                        (last_status in retry_statuses)
                        or (failure_token and failure_token in _retry_tokens)
                    )
                    if not is_last_route and can_try_next:
                        next_route = forward_routes[route_index + 1]
                        _log_native_fallback(
                            from_route=active_route,
                            to_route=next_route,
                            model_name=active_model,
                            reason=failure_token or f"http_{last_status}",
                            request_url=last_target_url,
                        )
                        continue
                    break

                anthropic_payload = _responses_payload_to_anthropic_messages_payload(payload, active_model)
                profile_id = apply_profile_body_patches(
                    anthropic_payload,
                    protocol="anthropic_messages",
                    provider_id=provider_id,
                    profile_id=provider_profile,
                    base_url=active_gateway_url,
                    model_name=active_model,
                    thinking_enabled=reasoning_enabled,
                    reasoning_effort=reasoning_effort,
                )
                if profile_id:
                    _canonicalize_domestic_anthropic_history(anthropic_payload, active_model)
                if not profile_id and _is_domestic_model(active_model):
                    _apply_domestic_reasoning_controls(
                        anthropic_payload,
                        active_model,
                        thinking_enabled=reasoning_enabled,
                        reasoning_effort=reasoning_effort,
                    )
                if not _normalize_model_name(active_model).startswith("claude-") and not _model_supports_anthropic_cache_control(active_model):
                    _strip_cache_control(anthropic_payload)

                fwd_headers = {
                    "Content-Type": "application/json",
                    "x-api-key": active_gateway_key,
                    "anthropic-version": "2023-06-01",
                }
                apply_profile_auth_headers(
                    fwd_headers,
                    protocol="anthropic_messages",
                    api_key=active_gateway_key,
                    provider_id=provider_id,
                    profile_id=provider_profile,
                    base_url=active_gateway_url,
                    model_name=active_model,
                )
                claude_passthrough, claude_passthrough_prefixes = _claude_passthrough_rules(self.server, active_model)
                fwd_headers.update(
                    _copy_passthrough_headers(
                        self.headers,
                        names=claude_passthrough,
                        prefixes=claude_passthrough_prefixes,
                    )
                )

                translator = _AnthropicMessagesToResponsesTranslator(active_model)
                first_byte_ms = None
                output_tokens = None
                route_exhausted = False
                for target_url in _build_gateway_candidate_urls(active_gateway_url, "/messages"):
                    last_target_url = target_url
                    _bridge_error_logger.info(
                        "FALLBACK to anthropic messages: model=%s url=%s", active_model, target_url
                    )
                    retry_remaining = 1
                    while True:
                        with httpx.stream(
                            "POST",
                            target_url,
                            headers=fwd_headers,
                            json=anthropic_payload,
                            timeout=300,
                            **_route_httpx_kwargs(self.server, active_route, target_url),
                        ) as response:
                            if response.status_code == 429:
                                last_status = response.status_code
                                last_body = response.read().decode("utf-8", errors="replace")
                                retry_after = response.headers.get("Retry-After")
                                delay = _retry_after_delay_seconds(retry_after)
                                if retry_remaining > 0 and delay > 0:
                                    retry_remaining -= 1
                                    _bridge_error_logger.warning(
                                        "anthropic messages fallback rate limited: model=%s url=%s retry_after=%s",
                                        active_model,
                                        target_url,
                                        retry_after,
                                    )
                                    time.sleep(delay)
                                    continue
                                if not is_last_route and response.status_code in retry_statuses:
                                    next_route = forward_routes[route_index + 1]
                                    _log_native_fallback(
                                        from_route=active_route,
                                        to_route=next_route,
                                        model_name=active_model,
                                        reason="http_429",
                                        request_url=target_url,
                                    )
                                    route_exhausted = True
                                    break
                                _record_bridge_blocking_failure(
                                    self.server,
                                    model_name=active_model,
                                    provider_id=provider_id,
                                    status_code=response.status_code,
                                    body_text=last_body,
                                    request_url=target_url,
                                    bridge_surface="codex_anthropic_messages_fallback",
                                )
                                self._json_with_headers(
                                    429,
                                    {"error": {"message": last_body or "anthropic messages fallback rate limited"}},
                                    extra_headers={"Retry-After": retry_after} if retry_after else None,
                                )
                                return
                            if response.status_code >= 400:
                                last_status = response.status_code
                                last_body = response.read().decode("utf-8", errors="replace")
                                if not is_last_route and response.status_code in retry_statuses:
                                    next_route = forward_routes[route_index + 1]
                                    _log_native_fallback(
                                        from_route=active_route,
                                        to_route=next_route,
                                        model_name=active_model,
                                        reason=f"http_{response.status_code}",
                                        request_url=target_url,
                                    )
                                    route_exhausted = True
                                break

                            self.send_response(200)
                            self.send_header("Content-Type", "text/event-stream")
                            self.send_header("Cache-Control", "no-cache")
                            self.send_header("Connection", "close")
                            self.end_headers()

                            for event_type, event_payload in _iter_sse_lines(response):
                                if first_byte_ms is None:
                                    first_byte_ms = _now_ms()
                                for event_name, response_payload in translator.process(event_type, event_payload):
                                    extracted = _extract_output_tokens(response_payload)
                                    if extracted is not None:
                                        output_tokens = extracted
                                    self._sse(event_name, response_payload)
                            self.close_connection = True
                            _record_bridge_speed(
                                active_model,
                                started_ms=started_ms,
                                first_byte_ms=first_byte_ms,
                                output_tokens=output_tokens,
                                provider_scope=getattr(self.server, "speed_scope", None),
                                server=self.server,
                            )
                            return
                    if route_exhausted:
                        break
                if route_exhausted:
                    continue
                break
            _record_bridge_blocking_failure(
                self.server,
                model_name=model_name,
                provider_id=str((forward_routes[-1] if forward_routes else route).get("provider_id") or getattr(self.server, "provider_id", "")),
                status_code=last_status,
                body_text=last_body or "",
                request_url=last_target_url,
                bridge_surface="codex_anthropic_messages_fallback",
            )
            self._json(last_status, {"error": {"message": last_body or "anthropic messages fallback failed"}})
        except Exception as exc:
            _bridge_error_logger.error("fallback anthropic messages error: %s", exc, exc_info=True)
            self._json(502, {"error": {"message": str(exc)}})


class _ResponsesToChatHandler(_ResponsesProxyHandler):
    """Local bridge: accepts Codex's /v1/responses requests,
    translates to the configured upstream transport, and forwards to gateway."""

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
        if not self._authorized():
            self._json(401, {"error": {"message": "invalid token"}})
            return
        if self.path.split("?", 1)[0] == "/v1/models":
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

        _ensure_httpx()
        if httpx is None:
            self._json(502, {"error": {"message": "缺少 httpx"}})
            return

        gateway_url = getattr(self.server, "gateway_url")
        gateway_key = getattr(self.server, "gateway_key")
        model_name = payload.get("model") or getattr(self.server, "model_name", "unknown")
        provider_id = getattr(self.server, "provider_id", "")
        provider_profile = getattr(self.server, "provider_profile", "")
        reasoning_enabled = bool(getattr(self.server, "reasoning_enabled", True))
        reasoning_effort = getattr(self.server, "reasoning_effort", "high")
        started_ms = _now_ms()
        primary_protocol = str(getattr(self.server, "primary_protocol", "openai_chat_completions") or "openai_chat_completions")

        if primary_protocol == "anthropic_messages":
            messages_route = {
                "provider_id": provider_id,
                "provider_profile": provider_profile,
                "protocol": "anthropic_messages",
                "fallback_reason": "",
                "include_native_fallbacks": True,
            }
            self._do_anthropic_messages_fallback(
                payload,
                model_name,
                gateway_url,
                gateway_key,
                started_ms,
                route=messages_route,
            )
            return

        # Translate Responses → Chat Completions request
        chat_messages = _responses_input_to_messages(
            payload.get("instructions", ""),
            payload.get("input", []),
            model_name,
            session_reasoning_content=getattr(self.server, "_last_reasoning_content", ""),
        )
        chat_payload = {
            "model": model_name,
            "messages": chat_messages,
            "stream": True,
        }
        max_output_tokens = _responses_max_output_tokens(payload)
        if max_output_tokens is not None:
            chat_payload["max_tokens"] = max_output_tokens
        chat_tools = _responses_tools_to_chat(payload.get("tools"))
        if chat_tools:
            chat_payload["tools"] = chat_tools
        apply_profile_body_patches(
            chat_payload,
            protocol="openai_chat",
            provider_id=provider_id,
            profile_id=provider_profile,
            base_url=gateway_url,
            model_name=model_name,
            thinking_enabled=reasoning_enabled,
            reasoning_effort=reasoning_effort,
        )

        # Forward to gateway /v1/chat/completions
        target_url = _build_gateway_url(gateway_url, "/chat/completions")
        fwd_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {gateway_key}",
        }
        apply_profile_auth_headers(
            fwd_headers,
            protocol="openai_chat",
            api_key=gateway_key,
            provider_id=provider_id,
            profile_id=provider_profile,
            base_url=gateway_url,
            model_name=model_name,
        )
        fwd_headers.update(_copy_passthrough_headers(self.headers))

        translator = _ChatCompletionsToResponsesTranslator(model_name)
        first_byte_ms = None
        output_tokens = None
        try:
            with httpx.stream(
                "POST",
                target_url,
                headers=fwd_headers,
                json=chat_payload,
                timeout=300,
                **_server_bridge_httpx_kwargs(self.server, target_url),
            ) as response:
                if response.status_code >= 400:
                    body = response.read().decode("utf-8", errors="replace")
                    if _chatcompletions_error_requests_messages(body) and gateway_url and gateway_key:
                        messages_route = {
                            "provider_id": provider_id,
                            "provider_profile": provider_profile,
                            "protocol": "anthropic_messages",
                            "fallback_reason": "cache_sensitive_messages_retry",
                        }
                        _bridge_error_logger.warning(
                            "primary chat bridge rejected for cache-sensitive transport; retrying messages: model=%s",
                            model_name,
                        )
                        _append_incident_log(
                            server=self.server,
                            model=model_name,
                            provider_id=provider_id,
                            status_code=response.status_code,
                            bridge_surface="chat_to_messages_retry",
                            request_url=target_url,
                            event="cache_sensitive_channel_switch",
                            detail="chatcompletions rejected; retrying via anthropic messages",
                        )
                        self._do_anthropic_messages_fallback(
                            payload,
                            model_name,
                            gateway_url,
                            gateway_key,
                            started_ms,
                            route=messages_route,
                        )
                        return
                    _record_bridge_blocking_failure(
                        self.server,
                        model_name=model_name,
                        provider_id=provider_id,
                        status_code=response.status_code,
                        body_text=body,
                        request_url=target_url,
                        bridge_surface="codex_responses_to_chat",
                    )
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
                            current_reasoning = translator._normalized_reasoning_content()
                            if current_reasoning:
                                self.server._last_reasoning_content = current_reasoning
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
                    server=self.server,
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
    provider_id="",
    provider_profile="",
    reasoning_enabled=True,
    reasoning_effort="high",
    proxy_url="",
    no_proxy="",
    primary_protocol="openai_chat_completions",
    native_fallback_routes=None,
    rescue_fallback_model="",
    rescue_fallback_cli="",
    rescue_hot_fallback_enabled=None,
):
    """Local bridge for Codex: translates /v1/responses to chat or messages.

    Use this when the gateway only supports Chat Completions for non-GPT models
    or when a cache-sensitive route must use Anthropic Messages while Codex
    still requires Responses API.
    """
    _ensure_httpx()
    if httpx is None:
        raise RuntimeError("缺少 httpx，无法启动 Codex Chat Completions bridge")
    bridge_token = f"mms-bridge-{uuid.uuid4().hex}"
    server = _SilentHTTPServer(("127.0.0.1", 0), _ResponsesToChatHandler)
    port = int(server.server_address[1])
    server.gateway_url = gateway_url
    server.gateway_key = gateway_key
    server.model_name = model_name
    server.advertised_models = list(advertised_models or [])
    server.speed_scope = dict(speed_scope or {})
    server.route_status_paths = list(route_status_paths or [])
    server.bridge_token = bridge_token
    server.provider_id = str(provider_id or "")
    server.provider_profile = str(provider_profile or "")
    server.reasoning_enabled = bool(reasoning_enabled)
    server.reasoning_effort = reasoning_effort
    server._last_reasoning_content = ""
    server.proxy_url = str(proxy_url or "").strip()
    server.no_proxy = str(no_proxy or "").strip()
    server.primary_protocol = (
        "anthropic_messages"
        if str(primary_protocol or "").strip() == "anthropic_messages"
        else "openai_chat_completions"
    )
    server.native_fallback_routes = list(native_fallback_routes or [])
    _configure_bridge_rescue(server)
    if rescue_fallback_model:
        server.rescue_fallback_model = str(rescue_fallback_model or "").strip()
    if rescue_fallback_cli:
        server.rescue_fallback_cli = str(rescue_fallback_cli or "").strip()
    if rescue_hot_fallback_enabled is not None:
        server.rescue_hot_fallback_enabled = bool(rescue_hot_fallback_enabled)
    server.session_input_tokens = 0
    server.session_output_tokens = 0
    server.session_request_count = 0
    server.session_start_time = time.time()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if not _wait_local_server_ready(port):
            raise RuntimeError(f"codex_chatcompletions_bridge 未能在本地端口 {port} 就绪")
        yield {
            "base_url": f"http://127.0.0.1:{port}",
            "api_key": bridge_token,
        }
    finally:
        try:
            server._BaseServer__shutdown_request = True
            server.server_close()
            thread.join(timeout=2)
        except (KeyboardInterrupt, Exception):
            pass


@contextmanager
def codex_responses_bridge(
    gateway_url,
    gateway_key,
    model_name="unknown",
    advertised_models=None,
    speed_scope=None,
    route_status_paths=None,
    provider_id="",
    provider_profile="",
    reasoning_enabled=True,
    reasoning_effort="medium",
    proxy_url="",
    no_proxy="",
    native_fallback_routes=None,
    rescue_fallback_model="",
    rescue_fallback_cli="",
    rescue_hot_fallback_enabled=None,
):
    _ensure_httpx()
    if httpx is None:
        raise RuntimeError("缺少 httpx，无法启动 Codex responses bridge")
    bridge_token = f"mms-bridge-{uuid.uuid4().hex}"
    server = _SilentHTTPServer(("127.0.0.1", 0), _ResponsesProxyHandler)
    port = int(server.server_address[1])
    server.gateway_url = gateway_url
    server.gateway_key = gateway_key
    server.model_name = model_name
    server.advertised_models = list(advertised_models or [])
    server.speed_scope = dict(speed_scope or {})
    server.route_status_paths = list(route_status_paths or [])
    server.bridge_token = bridge_token
    server.provider_id = provider_id
    server.provider_profile = str(provider_profile or "")
    server.reasoning_enabled = bool(reasoning_enabled)
    server.reasoning_effort = reasoning_effort
    server._last_reasoning_content = ""
    server.proxy_url = str(proxy_url or "").strip()
    server.no_proxy = str(no_proxy or "").strip()
    server.native_fallback_routes = list(native_fallback_routes or [])
    _configure_bridge_rescue(server)
    if rescue_fallback_model:
        server.rescue_fallback_model = str(rescue_fallback_model or "").strip()
    if rescue_fallback_cli:
        server.rescue_fallback_cli = str(rescue_fallback_cli or "").strip()
    if rescue_hot_fallback_enabled is not None:
        server.rescue_hot_fallback_enabled = bool(rescue_hot_fallback_enabled)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if not _wait_local_server_ready(port):
            raise RuntimeError(f"codex_responses_bridge 未能在本地端口 {port} 就绪")
        yield {
            "base_url": f"http://127.0.0.1:{port}",
            "api_key": bridge_token,
        }
    finally:
        try:
            server._BaseServer__shutdown_request = True
            server.server_close()
            thread.join(timeout=2)
        except (KeyboardInterrupt, Exception):
            pass


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
    provider_id="",
    provider_profile="",
    openai_url=None,
    strip_upstream_user_agent=False,
    minimal_claude_header_passthrough=False,
    reasoning_enabled=True,
    reasoning_effort="medium",
    proxy_url="",
    no_proxy="",
    native_fallback_routes=None,
    vision_sidecar=None,
    model_capabilities=None,
    rescue_fallback_model="",
    rescue_fallback_cli="",
    rescue_hot_fallback_enabled=None,
    context_windows=None,
    session_context_window=None,
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
    _ensure_httpx()
    if httpx is None:
        raise RuntimeError("缺少 httpx，无法启动 gateway bridge")
    bridge_token = f"mms-bridge-{uuid.uuid4().hex}"
    server = _SilentHTTPServer(("127.0.0.1", 0), _GatewayBridgeHandler)
    port = int(server.server_address[1])
    server.gateway_url = gateway_url
    server.gateway_key = gateway_key
    server.bridge_token = bridge_token
    server.heavy_model = heavy_model
    server.medium_model = medium_model
    server.light_model = light_model
    server.advertised_models = list(advertised_models or [])
    server.speed_scope = dict(speed_scope or {})
    server.route_status_paths = list(route_status_paths or [])
    server.context_windows = dict(context_windows or {})
    server.session_context_window = _coerce_context_window(session_context_window)
    # 止血：暂时禁用 bridge 层跨 provider slot 切换，避免实际 provider/account 漂移。
    server.slot_configs = {}
    server.provider_id = str(provider_id or "")
    server.provider_profile = str(provider_profile or "")
    server.openai_url = openai_url
    server.strip_upstream_user_agent = bool(strip_upstream_user_agent)
    server.minimal_claude_header_passthrough = bool(minimal_claude_header_passthrough)
    server.reasoning_enabled = bool(reasoning_enabled)
    server.reasoning_effort = reasoning_effort
    server.proxy_url = str(proxy_url or "").strip()
    server.no_proxy = str(no_proxy or "").strip()
    server.native_fallback_routes = list(native_fallback_routes or [])
    server.vision_sidecar = dict(vision_sidecar or {})
    server.model_capabilities = dict(model_capabilities or {})
    _configure_bridge_rescue(server)
    if rescue_fallback_model:
        server.rescue_fallback_model = str(rescue_fallback_model or "").strip()
    if rescue_fallback_cli:
        server.rescue_fallback_cli = str(rescue_fallback_cli or "").strip()
    if rescue_hot_fallback_enabled is not None:
        server.rescue_hot_fallback_enabled = bool(rescue_hot_fallback_enabled)
    server._sticky_floor = None
    server._sticky_remaining = 0
    server._last_level = "heavy"  # 默认 tier
    server._last_reasoning_content = ""
    # ── Session 统计 ──
    server.session_input_tokens = 0
    server.session_output_tokens = 0
    server.session_request_count = 0
    server.session_start_time = time.time()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if not _wait_local_server_ready(port):
            raise RuntimeError(f"gateway_claude_bridge 未能在本地端口 {port} 就绪")
        yield {
            "base_url": f"http://127.0.0.1:{port}",
            "api_key": bridge_token,
            "_server": server,  # launcher 退出时读取 session 统计
        }
    finally:
        try:
            server._BaseServer__shutdown_request = True
            server.server_close()
            thread.join(timeout=2)
        except (KeyboardInterrupt, Exception):
            pass
