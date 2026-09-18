"""Explicit new-connection model discovery; no config/cache writes or inference probes."""
from __future__ import annotations

import time
from urllib.parse import urlsplit, urlunsplit

from .errors import WebError


def connection_url(base: str, *, allow_query: bool = False) -> str:
    """Keep legacy manual query URLs; discovery must use an unambiguous path."""
    if any(ord(c) < 32 or c.isspace() for c in base):
        raise WebError("INVALID_SERVICE_URL", "API 地址不能包含空白字符。")
    try:
        parsed = urlsplit(base)
        _ = parsed.port
    except ValueError as exc:
        raise WebError("INVALID_SERVICE_URL", "服务地址格式不正确，请检查地址和端口。") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or (parsed.query and not allow_query) or parsed.fragment:
        raise WebError("INVALID_SERVICE_URL", "请填写完整的 http(s) API 地址，密钥放在 API Key 中，不要放入地址。")
    return base.rstrip("/")


def discover_models(payload: dict) -> dict:
    service = payload.get("service")
    if not isinstance(service, dict):
        raise WebError("INVALID_PAYLOAD", "请填写模型服务地址与 API Key。")
    base = str(service.get("baseUrl") or "").strip()
    key = str(service.get("apiKey") or "").strip()
    protocol = service.get("protocol", "openai")
    if protocol not in {"openai", "dual"}:
        raise WebError("MODELS_MANUAL_REQUIRED", "该服务类型请先手动填写模型名；这里不会额外探测 Anthropic 接口。")
    parsed = urlsplit(connection_url(base))
    if not key or len(key) > 8192 or any(ord(c) < 32 for c in key):
        raise WebError("INVALID_SERVICE_KEY", "请填写有效的 API Key。")
    url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/") + "/models", "", ""))
    started = time.monotonic()
    try:
        import httpx
        # The exact URL shown to the user is the only request. No /v1 guessing,
        # redirect credential forwarding, global proxy/account fallback or cache.
        with httpx.Client(follow_redirects=False, trust_env=False, timeout=httpx.Timeout(15, connect=5)) as client:
            with client.stream("GET", url, headers={"Authorization": "Bearer " + key, "Accept": "application/json"}) as response:
                if response.status_code in {401, 403}:
                    raise WebError("SERVICE_AUTH_FAILED", "服务拒绝了这个 Key。检查密钥是否完整，以及是否有读取模型的权限。", 400)
                if response.status_code == 429:
                    raise WebError("SERVICE_RATE_LIMITED", "服务暂时限制了请求，请稍后重试；也可以手动填写模型名。", 400)
                if 300 <= response.status_code < 400:
                    raise WebError("SERVICE_REDIRECT", "服务返回了跳转地址。请核对 API 地址后重试，密钥没有随跳转发送。", 400)
                if response.status_code == 404:
                    raise WebError("MODELS_ENDPOINT_MISSING", "这个地址没有模型列表接口。请核对是否需要 /v1，或手动填写模型名。", 400)
                if response.status_code >= 400:
                    raise WebError("SERVICE_UNAVAILABLE", f"模型服务返回 HTTP {response.status_code}，请稍后重试或手动填写模型名。", 400)
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 2 * 1024 * 1024:
                        raise WebError("MODEL_LIST_TOO_LARGE", "服务返回的列表过大，请手动填写需要的模型名。")
                    chunks.append(chunk)
        import json
        data = json.loads(b"".join(chunks))
    except WebError:
        raise
    except ImportError as exc:
        raise WebError("DISCOVERY_UNAVAILABLE", "本机缺少 MMS 的 HTTP 依赖，请先完成安装；也可以手动填写模型名。", 409) from exc
    except (ValueError, UnicodeError) as exc:
        raise WebError("INVALID_MODEL_LIST", "服务没有返回有效的模型列表，请核对 API 地址。", 400) from exc
    except Exception as exc:
        # Never serialize provider error bodies or exception URLs containing credentials.
        raise WebError("SERVICE_CONNECTION_FAILED", "无法连接模型服务。检查地址、网络或本地代理后重试，也可以手动填写模型名。", 400) from exc
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise WebError("INVALID_MODEL_LIST", "服务返回的数据不含模型列表，请核对 API 地址。", 400)
    models = sorted({row["id"].strip() for row in rows if isinstance(row, dict)
                     and isinstance(row.get("id"), str) and 0 < len(row["id"].strip()) <= 200
                     and not any(ord(c) < 32 for c in row["id"])})
    if not models:
        raise WebError("EMPTY_MODEL_LIST", "这个 Key 没有返回可用模型，请检查服务权限或手动填写模型名。", 400)
    if len(models) > 5000:
        raise WebError("MODEL_LIST_TOO_LARGE", "模型数量超过展示范围，请手动填写需要的模型名。")
    return {"models": models, "requestUrl": url, "latencyMs": round((time.monotonic() - started) * 1000),
            "generationVerified": False}
