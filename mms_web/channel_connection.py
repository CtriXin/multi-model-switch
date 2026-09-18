"""Small, explicit connection edits for the existing MMF provider writer."""
from urllib.parse import urlsplit

from .errors import WebError


FIELDS = {"openaiBaseUrl": "openai_base_url", "anthropicBaseUrl": "anthropic_base_url"}


def safe_url(value):
    try:
        p = urlsplit(value)
        return bool(p.scheme in {"http", "https"} and p.hostname and p.port != 0
                    and not p.username and not p.password and not p.query and not p.fragment
                    and not any(c.isspace() or ord(c) < 32 for c in value))
    except ValueError:
        return False


def public_connection(provider, runtime=None):
    connection = {}
    for name, field in FIELDS.items():
        value = str(provider.get(field) or "")
        connection[name] = value if safe_url(value) else ""
    connection["hasApiKey"] = bool(provider.get("has_api_key") or (runtime or {}).get("api_key"))
    connection["protocols"] = provider.get("protocols", [])
    return connection


def edit_connection(provider, payload):
    if payload is None:
        return {}, []
    if not isinstance(payload, dict) or set(payload) - {*FIELDS, "apiKey"}:
        raise WebError("INVALID_CONNECTION", "连接设置格式无效。", 400)
    edit, changes = {}, []
    for name, field in FIELDS.items():
        if name not in payload:
            continue
        value = payload[name]
        if not isinstance(value, str) or len(value) > 2048 or not safe_url(value):
            raise WebError("INVALID_URL", "请填写完整的 HTTP(S) 服务地址，不要在地址中填写 Key 或查询参数。", 400)
        value = value.rstrip("/")
        previous = str(provider.get(field) or "").rstrip("/")
        if previous != value:
            edit[field] = value
            edit[field + "_source"] = "config"
            changes.append({"kind": "connection", "model": "OpenAI 地址" if name == "openaiBaseUrl" else "Anthropic 地址",
                            "before": previous if safe_url(previous) else "未设置", "after": value})
    if "apiKey" in payload:
        key = payload["apiKey"]
        if not isinstance(key, str) or not key.strip() or key != key.strip() or len(key) > 8192 or any(c.isspace() or ord(c) < 32 for c in key):
            raise WebError("INVALID_KEY", "新的 API Key 不能为空，也不能包含空白字符。", 400)
        edit.update(api_key=key, update_credentials=True)
        changes.append({"kind": "connection", "model": "API Key", "before": "已配置" if provider.get("has_api_key") else "未配置", "after": "替换为新 Key（不回显）"})
    return edit, changes
