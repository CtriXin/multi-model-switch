from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_CLAUDE_HEALTH_TARGETS = (
    {"label": "anthropic", "url": "https://api.anthropic.com"},
    {"label": "claude", "url": "https://claude.ai"},
)
_ALLOWED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}
_SUPPORTED_ROUTE_PROXY_SCHEMES = {"http", "https", "socks5h"}
_HTTP_URL_SCHEMES = {"http", "https"}
_SCHEMA_VERSION = 1


def validate_loopback_proxy_url(proxy_url: str) -> dict[str, str | int | bool]:
    raw = str(proxy_url or "").strip()
    if not raw:
        return {
            "ok": False,
            "detail": "未配置 local loopback proxy URL",
            "url": "",
            "scheme": "",
            "host": "",
            "port": 0,
            "proxy_key": "",
        }
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        return {
            "ok": False,
            "detail": f"local proxy URL 非法: {exc}",
            "url": raw,
            "scheme": "",
            "host": "",
            "port": 0,
            "proxy_key": "",
        }

    scheme = str(parsed.scheme or "").strip().lower()
    host = str(parsed.hostname or "").strip()
    try:
        port = int(parsed.port or 0)
    except ValueError as exc:
        return {
            "ok": False,
            "detail": f"local proxy URL 端口非法: {exc}",
            "url": raw,
            "scheme": scheme,
            "host": host,
            "port": 0,
            "proxy_key": "",
        }

    if scheme not in _ALLOWED_PROXY_SCHEMES:
        return {
            "ok": False,
            "detail": f"local proxy scheme 不支持: {scheme or 'missing'}",
            "url": raw,
            "scheme": scheme,
            "host": host,
            "port": port,
            "proxy_key": "",
        }
    if not host or not port:
        return {
            "ok": False,
            "detail": "local proxy URL 缺少 host 或 port",
            "url": raw,
            "scheme": scheme,
            "host": host,
            "port": port,
            "proxy_key": "",
        }
    if parsed.username or parsed.password:
        return {
            "ok": False,
            "detail": "local proxy URL 不允许内嵌 credential",
            "url": raw,
            "scheme": scheme,
            "host": host,
            "port": port,
            "proxy_key": "",
        }
    if (parsed.path and parsed.path not in {"", "/"}) or parsed.query or parsed.fragment:
        return {
            "ok": False,
            "detail": "local proxy URL 不允许 path/query/fragment",
            "url": raw,
            "scheme": scheme,
            "host": host,
            "port": port,
            "proxy_key": "",
        }

    host_key = host.lower()
    is_loopback = host_key == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        return {
            "ok": False,
            "detail": f"local proxy host 必须是 loopback 地址，当前为 {host}",
            "url": raw,
            "scheme": scheme,
            "host": host,
            "port": port,
            "proxy_key": "",
        }

    normalized_url = f"{scheme}://{host}:{port}"
    return {
        "ok": True,
        "detail": "",
        "url": normalized_url,
        "scheme": scheme,
        "host": host,
        "port": port,
        "proxy_key": f"{scheme}://loopback:{port}",
    }


def _normalize_sticky_binding(binding, *, route_id: str) -> dict[str, str]:
    payload = binding if isinstance(binding, dict) else {}
    normalized = {
        "account_uuid": str(payload.get("account_uuid") or "").strip(),
        "email": str(payload.get("email") or "").strip().lower(),
        "user_id": str(payload.get("user_id") or "").strip(),
    }
    if any(normalized.values()):
        return normalized
    raise ValueError(f"route `{route_id}` 缺少 sticky_account_binding")


def _normalize_health_targets(targets, *, route_id: str) -> list[dict[str, str]]:
    raw_targets = targets if isinstance(targets, list) and targets else list(DEFAULT_CLAUDE_HEALTH_TARGETS)
    normalized = []
    for index, item in enumerate(raw_targets, 1):
        if isinstance(item, str):
            label = ""
            url = item
        elif isinstance(item, dict):
            label = str(item.get("label") or "").strip()
            url = str(item.get("url") or "").strip()
        else:
            raise ValueError(f"route `{route_id}` health_targets[{index}] 不是字符串或对象")
        if not url:
            raise ValueError(f"route `{route_id}` health_targets[{index}] 缺少 url")
        parsed = urlsplit(url)
        scheme = str(parsed.scheme or "").strip().lower()
        host = str(parsed.hostname or "").strip()
        if scheme not in _HTTP_URL_SCHEMES or not host:
            raise ValueError(f"route `{route_id}` health_targets[{index}] URL 非法: {url}")
        if parsed.username or parsed.password:
            raise ValueError(f"route `{route_id}` health_targets[{index}] 不允许 credential")
        if not label:
            label = host
        normalized.append({"label": label, "url": url})
    return normalized


def _normalize_route_item(item, *, source_path: str, index: int) -> dict:
    if not isinstance(item, dict):
        raise ValueError(f"routes[{index}] 不是对象")
    route_id = str(item.get("id") or "").strip()
    if not route_id:
        raise ValueError(f"routes[{index}] 缺少 id")
    purpose = str(item.get("purpose") or "oauth_claude").strip() or "oauth_claude"
    endpoint = validate_loopback_proxy_url(str(item.get("local_proxy_url") or ""))
    if not endpoint.get("ok"):
        raise ValueError(f"route `{route_id}` 的 local_proxy_url 非法: {endpoint.get('detail')}")
    if endpoint.get("scheme") not in _SUPPORTED_ROUTE_PROXY_SCHEMES:
        raise ValueError(
            f"route `{route_id}` 的 local_proxy_url scheme 不支持: {endpoint.get('scheme')}；仅允许 http/https/socks5h"
        )
    expected_exit_ip = str(item.get("expected_exit_ip") or "").strip()
    if expected_exit_ip:
        try:
            expected_exit_ip = str(ipaddress.ip_address(expected_exit_ip))
        except ValueError as exc:
            raise ValueError(f"route `{route_id}` 的 expected_exit_ip 非法: {exc}") from exc
    if purpose == "oauth_claude":
        sticky_binding = _normalize_sticky_binding(item.get("sticky_account_binding"), route_id=route_id)
    else:
        sticky_binding = item.get("sticky_account_binding") if isinstance(item.get("sticky_account_binding"), dict) else {}
        sticky_binding = {
            "account_uuid": str(sticky_binding.get("account_uuid") or "").strip(),
            "email": str(sticky_binding.get("email") or "").strip().lower(),
            "user_id": str(sticky_binding.get("user_id") or "").strip(),
        }
    return {
        "id": route_id,
        "purpose": purpose,
        "local_proxy_url": str(endpoint["url"]),
        "proxy_key": str(endpoint["proxy_key"]),
        "expected_exit_ip": expected_exit_ip,
        "sticky_account_binding": sticky_binding,
        "health_targets": _normalize_health_targets(item.get("health_targets"), route_id=route_id),
        "source_path": source_path,
        "endpoint": endpoint,
    }


def _binding_identity_tokens(route: dict) -> list[tuple[str, str]]:
    binding = route.get("sticky_account_binding") if isinstance(route, dict) else {}
    binding = binding if isinstance(binding, dict) else {}
    tokens = []
    for key in ("account_uuid", "email", "user_id"):
        value = str(binding.get(key) or "").strip()
        if value:
            tokens.append((key, value.lower() if key == "email" else value))
    return tokens


def binding_matches_owner(route: dict, owner: dict[str, str] | None) -> tuple[bool, str]:
    route_id = str((route or {}).get("id") or (route or {}).get("local_proxy_url") or "route").strip()
    binding = (route or {}).get("sticky_account_binding")
    binding = binding if isinstance(binding, dict) else {}
    if not any(str(binding.get(key) or "").strip() for key in ("account_uuid", "email", "user_id")):
        return False, f"route `{route_id}` 缺少 sticky_account_binding"

    owner = dict(owner or {})
    checks = (
        ("account_uuid", "owner_account_uuid", "accountUuid"),
        ("email", "owner_email", "email"),
        ("user_id", "owner_user_id", "userID"),
    )
    for binding_key, owner_key, label in checks:
        expected = str(binding.get(binding_key) or "").strip()
        if not expected:
            continue
        current = str(owner.get(owner_key) or "").strip()
        if binding_key == "email":
            expected = expected.lower()
            current = current.lower()
        if not current:
            return False, f"当前 MMC account 缺少 {label}，无法验证 route `{route_id}`"
        if current != expected:
            return False, f"当前 MMC account 与 route `{route_id}` 的 {label} 绑定不一致"
    return True, ""


def find_route_by_id(document: dict, route_id: str) -> dict | None:
    routes_by_id = document.get("routes_by_id") if isinstance(document, dict) else {}
    routes_by_id = routes_by_id if isinstance(routes_by_id, dict) else {}
    return routes_by_id.get(str(route_id or "").strip())


def find_route_by_local_proxy_url(document: dict, proxy_url: str) -> dict | None:
    routes_by_proxy_key = document.get("routes_by_proxy_key") if isinstance(document, dict) else {}
    routes_by_proxy_key = routes_by_proxy_key if isinstance(routes_by_proxy_key, dict) else {}
    endpoint = validate_loopback_proxy_url(proxy_url)
    if not endpoint.get("ok"):
        return None
    return routes_by_proxy_key.get(str(endpoint["proxy_key"]))


def find_routes_for_owner(document: dict, owner: dict[str, str] | None, *, purpose: str = "oauth_claude") -> list[dict]:
    matched = []
    for route in document.get("routes") or []:
        if str(route.get("purpose") or "").strip() != str(purpose or "").strip():
            continue
        if binding_matches_owner(route, owner)[0]:
            matched.append(route)
    return matched


def load_proxy_routes_file(path_value: str) -> dict:
    source_path = os.path.realpath(os.path.abspath(os.path.expanduser(str(path_value or "").strip())))
    if not source_path:
        raise ValueError("缺少 proxy route 文件路径")
    path = Path(source_path)
    if not path.exists():
        raise ValueError(f"proxy route 文件不存在: {source_path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"proxy route JSON 非法: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("proxy route 文件顶层必须是对象")
    schema_version = int(payload.get("schema_version") or _SCHEMA_VERSION)
    if schema_version != _SCHEMA_VERSION:
        raise ValueError(f"不支持的 schema_version: {schema_version}")
    raw_routes = payload.get("routes")
    if not isinstance(raw_routes, list) or not raw_routes:
        raise ValueError("proxy route 文件至少要有一个 routes[] 条目")

    routes = []
    seen_ids = set()
    seen_proxy_keys = set()
    seen_bindings = {}
    for index, item in enumerate(raw_routes, 1):
        route = _normalize_route_item(item, source_path=source_path, index=index)
        route_id = route["id"]
        if route_id in seen_ids:
            raise ValueError(f"route id 重复: {route_id}")
        seen_ids.add(route_id)
        proxy_key = route["proxy_key"]
        if proxy_key in seen_proxy_keys:
            raise ValueError(f"local_proxy_url 重复: {route['local_proxy_url']}")
        seen_proxy_keys.add(proxy_key)
        for binding_key, binding_value in _binding_identity_tokens(route):
            identity = (binding_key, binding_value)
            if identity in seen_bindings:
                raise ValueError(
                    f"route `{route_id}` 与 route `{seen_bindings[identity]}` 复用了同一 sticky_account_binding.{binding_key}"
                )
            seen_bindings[identity] = route_id
        routes.append(route)

    return {
        "schema_version": schema_version,
        "source_path": source_path,
        "routes": routes,
        "routes_by_id": {route["id"]: route for route in routes},
        "routes_by_proxy_key": {route["proxy_key"]: route for route in routes},
    }
