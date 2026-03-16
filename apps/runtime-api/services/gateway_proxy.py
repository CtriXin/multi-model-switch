from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any, AsyncIterator
from uuid import uuid4

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from services.gateway_config import GatewayContext, GatewayProvider, GatewayUpstreamKey, model_matches
from services.gateway_state import count_today_requests, log_gateway_request

_RETRYABLE_STATUSES = {401, 408, 409, 429, 500, 502, 503, 504}
_HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "content-encoding",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
_PROVIDER_CURSOR: dict[str, int] = defaultdict(int)


def ensure_quota(context: GatewayContext) -> None:
    limit = context.token.dailyRequestLimit
    if not limit:
        return

    used = count_today_requests(context.token.id, "/v1/chat/completions")
    if used >= limit:
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "message": "内部 token 今日请求额度已用完",
                    "code": "gateway_quota_exceeded",
                }
            },
        )


def ensure_model_allowed(context: GatewayContext, model_id: str) -> None:
    token_ok = model_matches(context.token.allowedModels, model_id)
    provider_ok = model_matches(context.provider.modelAllowlist, model_id)
    if token_ok and provider_ok:
        return

    raise HTTPException(
        status_code=403,
        detail={
            "error": {
                "message": f"当前 token 不允许访问模型：{model_id}",
                "code": "model_forbidden",
            }
        },
    )


async def proxy_models(request: Request, context: GatewayContext) -> Response:
    path = _build_upstream_url(context.provider, "/models", request.url.query)
    response = await _send_with_failover(
        method="GET",
        path=path,
        context=context,
        endpoint="/v1/models",
    )
    payload = _filter_models_payload(response["json"], context)
    return JSONResponse(
        status_code=response["status_code"],
        content=payload,
        headers=response["headers"],
    )


async def proxy_chat_completions(request: Request, context: GatewayContext) -> Response:
    payload = await request.json()
    model_id = str(payload.get("model") or "").strip()
    if not model_id:
        raise HTTPException(status_code=400, detail={"error": {"message": "缺少 model 字段", "code": "model_required"}})

    ensure_quota(context)
    ensure_model_allowed(context, model_id)

    request_id = uuid4().hex
    stream = bool(payload.get("stream"))
    if stream:
        return await _proxy_streaming_chat(payload, context, model_id, request_id)
    return await _proxy_non_stream_chat(payload, context, model_id, request_id)


async def _proxy_non_stream_chat(
    payload: dict[str, Any],
    context: GatewayContext,
    model_id: str,
    request_id: str,
) -> Response:
    response = await _send_with_failover(
        method="POST",
        path=_build_upstream_url(context.provider, "/chat/completions"),
        context=context,
        endpoint="/v1/chat/completions",
        json_body=payload,
        model_id=model_id,
        request_id=request_id,
    )
    return Response(
        content=response["content"],
        status_code=response["status_code"],
        media_type=response["media_type"],
        headers=response["headers"],
    )


async def _proxy_streaming_chat(
    payload: dict[str, Any],
    context: GatewayContext,
    model_id: str,
    request_id: str,
) -> Response:
    last_error: Response | None = None

    for key in _ordered_upstream_keys(context.provider, context.token.upstreamKeyIds):
        started_at = time.perf_counter()
        client = _create_client(context.provider.timeoutSeconds)

        try:
            upstream = await client.send(
                client.build_request(
                    "POST",
                    _build_upstream_url(context.provider, "/chat/completions"),
                    headers=_build_upstream_headers(context.provider, key),
                    json=payload,
                ),
                stream=True,
            )
        except httpx.HTTPError as exc:
            await client.aclose()
            _log_attempt(context, key, "/v1/chat/completions", model_id, 502, started_at, request_id, "gateway", str(exc))
            last_error = _error_response(502, "上游连接失败", "gateway_upstream_unreachable")
            continue

        if upstream.status_code in _RETRYABLE_STATUSES:
            body = await upstream.aread()
            headers = _response_headers(upstream.headers, key.id, upstream.status_code, request_id)
            await upstream.aclose()
            await client.aclose()
            _log_attempt(context, key, "/v1/chat/completions", model_id, upstream.status_code, started_at, request_id, "upstream", _trim_error(body))
            last_error = Response(
                content=body,
                status_code=upstream.status_code,
                media_type=upstream.headers.get("content-type", "application/json"),
                headers=headers,
            )
            continue

        headers = _response_headers(upstream.headers, key.id, upstream.status_code, request_id)
        _log_attempt(context, key, "/v1/chat/completions", model_id, upstream.status_code, started_at, request_id)
        return StreamingResponse(
            _stream_bytes(upstream, client),
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "text/event-stream"),
            headers=headers,
        )

    return last_error or _error_response(502, "没有可用的上游 key", "gateway_no_upstream_keys")


async def _send_with_failover(
    *,
    method: str,
    path: str,
    context: GatewayContext,
    endpoint: str,
    json_body: dict[str, Any] | None = None,
    model_id: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    last_error: dict[str, Any] | None = None

    for key in _ordered_upstream_keys(context.provider, context.token.upstreamKeyIds):
        started_at = time.perf_counter()
        try:
            async with _create_client(context.provider.timeoutSeconds) as client:
                response = await client.request(
                    method,
                    path,
                    headers=_build_upstream_headers(context.provider, key),
                    json=json_body,
                )
        except httpx.HTTPError as exc:
            _log_attempt(context, key, endpoint, model_id, 502, started_at, request_id, "gateway", str(exc))
            last_error = {
                "status_code": 502,
                "content": json.dumps({"error": {"message": "上游连接失败", "code": "gateway_upstream_unreachable"}}).encode("utf-8"),
                "media_type": "application/json",
                "headers": {"X-MMS-Error-Source": "gateway", "X-MMS-Upstream-Key": key.id, "X-MMS-Request-Id": request_id or ""},
                "json": {"error": {"message": "上游连接失败", "code": "gateway_upstream_unreachable"}},
            }
            continue

        body = response.content
        if response.status_code in _RETRYABLE_STATUSES:
            _log_attempt(context, key, endpoint, model_id, response.status_code, started_at, request_id, "upstream", _trim_error(body))
            last_error = {
                "status_code": response.status_code,
                "content": body,
                "media_type": response.headers.get("content-type", "application/json"),
                "headers": _response_headers(response.headers, key.id, response.status_code, request_id),
                "json": _safe_json(body),
            }
            continue

        _log_attempt(context, key, endpoint, model_id, response.status_code, started_at, request_id)
        return {
            "status_code": response.status_code,
            "content": body,
            "media_type": response.headers.get("content-type", "application/json"),
            "headers": _response_headers(response.headers, key.id, response.status_code, request_id),
            "json": _safe_json(body),
        }

    if last_error:
        return last_error
    raise HTTPException(status_code=503, detail={"error": {"message": "没有可用的上游 key", "code": "gateway_no_upstream_keys"}})


def _ordered_upstream_keys(provider: GatewayProvider, allowed_ids: list[str]) -> list[GatewayUpstreamKey]:
    keys = [item for item in provider.apiKeys if item.enabled]
    if allowed_ids:
        allowed = set(allowed_ids)
        keys = [item for item in keys if item.id in allowed]
    if not keys:
        return []

    cursor = _PROVIDER_CURSOR[provider.id] % len(keys)
    _PROVIDER_CURSOR[provider.id] += 1
    return keys[cursor:] + keys[:cursor]


def _build_upstream_headers(provider: GatewayProvider, key: GatewayUpstreamKey) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {key.apiKey}",
        "Content-Type": "application/json",
    }
    if provider.apiType == "openrouter":
        if provider.httpReferer:
            headers["HTTP-Referer"] = provider.httpReferer
        if provider.xTitle:
            headers["X-Title"] = provider.xTitle
    return headers


def _build_upstream_url(provider: GatewayProvider, suffix: str, query: str | None = None) -> str:
    base = provider.baseUrl.rstrip("/")
    url = f"{base}{suffix}"
    if query:
        return f"{url}?{query}"
    return url


def _filter_models_payload(payload: Any, context: GatewayContext) -> Any:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return payload

    payload["data"] = [
        item for item in payload["data"]
        if isinstance(item, dict)
        and model_matches(context.token.allowedModels, str(item.get("id", "")))
        and model_matches(context.provider.modelAllowlist, str(item.get("id", "")))
    ]
    return payload


def _response_headers(
    headers: httpx.Headers,
    key_id: str,
    status_code: int,
    request_id: str | None,
) -> dict[str, str]:
    next_headers = {
        name: value
        for name, value in headers.items()
        if name.lower() not in _HOP_BY_HOP_HEADERS
    }
    next_headers["X-MMS-Upstream-Key"] = key_id
    if request_id:
        next_headers["X-MMS-Request-Id"] = request_id
    if status_code >= 400:
        next_headers["X-MMS-Error-Source"] = "upstream"
    return next_headers


async def _stream_bytes(upstream: httpx.Response, client: httpx.AsyncClient) -> AsyncIterator[bytes]:
    try:
        async for chunk in upstream.aiter_raw():
            yield chunk
    finally:
        await upstream.aclose()
        await client.aclose()


def _create_client(timeout_seconds: float) -> httpx.AsyncClient:
    timeout = httpx.Timeout(timeout_seconds, connect=10.0)
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True)


def _safe_json(body: bytes) -> Any:
    if not body:
        return {}
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return {"raw": body.decode("utf-8", errors="replace")}


def _trim_error(body: bytes) -> str:
    if not body:
        return ""
    return body.decode("utf-8", errors="replace")[:500]


def _error_response(status_code: int, message: str, code: str) -> Response:
    body = json.dumps({"error": {"message": message, "code": code}})
    return Response(
        content=body,
        status_code=status_code,
        media_type="application/json",
        headers={"X-MMS-Error-Source": "gateway"},
    )


def _log_attempt(
    context: GatewayContext,
    key: GatewayUpstreamKey,
    endpoint: str,
    model_id: str | None,
    status_code: int,
    started_at: float,
    request_id: str | None,
    error_source: str | None = None,
    error_detail: str | None = None,
) -> None:
    log_gateway_request(
        request_id=request_id or "",
        endpoint=endpoint,
        token_id=context.token.id,
        token_name=context.token.name,
        provider_id=context.provider.id,
        model=model_id,
        upstream_key_id=key.id,
        status_code=status_code,
        latency_ms=int((time.perf_counter() - started_at) * 1000),
        error_source=error_source,
        error_detail=error_detail,
    )
