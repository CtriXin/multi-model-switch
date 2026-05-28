#!/usr/bin/env python3
"""Active MMS route health watchdog with optional Feishu notification.

This script is intentionally dependency-free so launchd can run it even when the
normal Python environment is unavailable.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9 fallback
    ZoneInfo = None  # type: ignore[assignment]
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]


DEFAULT_INTERVAL_SECONDS = 300
DEFAULT_TIMEOUT_SECONDS = 12
DEFAULT_REMIND_SECONDS = 1800
WATCHDOG_DIR_NAME = "health-watchdog"
STATE_FILE_NAME = "state.json"
LATEST_FILE_NAME = "latest.json"
LOG_FILE_NAME = "health-watchdog.log"
ENV_FILE_NAME = "health-watchdog.env"

OLD_ROUTE_MARKERS = {
    "http://82.156.121.141:4001": "xin fallback should use https://apple.clawopen.online",
    "http://82.156.121.141:3000/openai": "privateopenai should use https://privateopenai.clawopen.online/openai",
    "http://161.33.197.51:4001": "tokyo newapi should use https://newapi.evilsngx.ccwu.cc",
    "http://cpabundle.ccwu.cc/codex/v1": "codex should use https://codex.evilsngx.ccwu.cc/v1",
    "http://cpabundle.ccwu.cc/gemini/v1": "gemini should use https://gemini.evilsngx.ccwu.cc/v1",
}


@dataclass
class CheckResult:
    scope: str
    name: str
    level: str
    status: str
    detail: str
    latency_ms: int | None = None
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "scope": self.scope,
            "name": self.name,
            "level": self.level,
            "status": self.status,
            "detail": self.detail,
        }
        if self.latency_ms is not None:
            payload["latency_ms"] = self.latency_ms
        if self.url:
            payload["url"] = self.url
        return payload


def iso_now() -> str:
    tz = ZoneInfo("Asia/Singapore") if ZoneInfo else None
    dt = datetime.now(tz) if tz else datetime.now()
    return dt.isoformat(timespec="seconds")


def real_home() -> Path:
    for key in ("MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return Path(raw).expanduser()
    return Path.home()


def default_config_dir() -> Path:
    for key in ("MMS_CONFIG_ROOT", "MMS_CONFIG_DIR"):
        explicit = os.environ.get(key, "").strip()
        if explicit:
            return Path(explicit).expanduser()
    return real_home() / ".config" / "mms"


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.expanduser().resolve() == right.expanduser().resolve()
    except Exception:
        return os.path.abspath(os.path.expanduser(str(left))) == os.path.abspath(os.path.expanduser(str(right)))


def default_require_bundle_for_config_dir(config_dir: Path) -> bool:
    """Explicit preview/root-selected watchdog runs should fail closed."""
    for key in ("MMS_CONFIG_ROOT", "MMS_CONFIG_DIR"):
        raw = os.environ.get(key, "").strip()
        if raw and _same_path(config_dir, Path(raw)):
            return True
    return False


def resolve_require_bundle(args: argparse.Namespace, config_dir: Path) -> bool:
    if bool(args.require_bundle):
        return True
    raw = os.environ.get("MMS_WATCHDOG_REQUIRE_BUNDLE")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return default_require_bundle_for_config_dir(config_dir)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def read_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def read_toml(path: Path) -> dict[str, Any]:
    if tomllib is None or not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            parsed = tomllib.load(handle)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_verified_latest_bundle(config_dir: Path) -> dict[str, Any]:
    manifest_path = config_dir / "generated" / "model-registry.latest-approved.json"
    if not manifest_path.exists():
        return {
            "status": "missing",
            "manifest_path": str(manifest_path),
            "detail": "latest-approved manifest is missing",
            "payloads": {},
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "invalid",
            "manifest_path": str(manifest_path),
            "detail": f"manifest read failed: {type(exc).__name__}: {exc}",
            "payloads": {},
        }
    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    payloads: dict[str, Any] = {}
    verified_files: dict[str, str] = {}
    for name, entry in files.items():
        if not isinstance(entry, dict):
            return {
                "status": "invalid",
                "manifest_path": str(manifest_path),
                "detail": f"invalid manifest file entry: {name}",
                "payloads": {},
            }
        canonical = str(entry.get("canonical_path") or "").strip()
        expected = str(entry.get("sha256") or "").strip()
        if not canonical or not expected:
            return {
                "status": "invalid",
                "manifest_path": str(manifest_path),
                "detail": f"manifest file entry missing path/hash: {name}",
                "payloads": {},
            }
        path = config_dir / canonical
        if not path.exists():
            return {
                "status": "invalid",
                "manifest_path": str(manifest_path),
                "detail": f"manifest file missing: {path}",
                "payloads": {},
            }
        actual = sha256_file(path)
        if actual != expected:
            return {
                "status": "invalid",
                "manifest_path": str(manifest_path),
                "detail": f"manifest hash mismatch for {name}: {path}",
                "payloads": {},
            }
        verified_files[name] = str(path)
        try:
            payloads[name] = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payloads[name] = {}
    return {
        "status": "ok",
        "manifest_path": str(manifest_path),
        "detail": f"verified latest-approved bundle: {manifest.get('bundle_revision') or ''}",
        "manifest": manifest,
        "payloads": payloads,
        "verified_files": verified_files,
    }


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}-{time.time_ns()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)
    path.chmod(0o600)


def append_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    path.chmod(0o600)


def provider_config_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    providers = config.get("providers") if isinstance(config.get("providers"), list) else []
    result: dict[str, dict[str, Any]] = {}
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        provider_id = str(provider.get("id") or "").strip()
        if provider_id:
            result[provider_id] = provider
    return result


def provider_profile_map(profile_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    profiles = profile_payload.get("profiles") if isinstance(profile_payload.get("profiles"), dict) else {}
    result: dict[str, dict[str, Any]] = {}
    for provider_id, profile in profiles.items():
        if isinstance(provider_id, str) and provider_id.strip() and isinstance(profile, dict):
            result[provider_id.strip()] = profile
    return result


def model_policy_allowed(policy: dict[str, Any]) -> set[str]:
    projects = policy.get("projects") if isinstance(policy.get("projects"), dict) else {}
    models: set[str] = set()
    for project_name in ("hive", "pilot", "ant", "moebius", "mobius", "mms"):
        project = projects.get(project_name)
        if isinstance(project, dict):
            for item in project.get("allowed_models") or []:
                if isinstance(item, str) and item.strip():
                    models.add(item.strip())
    return models


def route_entries(routes_payload: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    routes = routes_payload.get("routes") if isinstance(routes_payload.get("routes"), dict) else {}
    entries: list[tuple[str, str, dict[str, Any]]] = []
    for model, info in routes.items():
        if not isinstance(model, str) or not isinstance(info, dict):
            continue
        primary = info.get("primary")
        if isinstance(primary, dict):
            entries.append((model, "primary", primary))
        fallbacks = info.get("fallbacks")
        if isinstance(fallbacks, list):
            for index, fallback in enumerate(fallbacks):
                if isinstance(fallback, dict):
                    entries.append((model, f"fallback[{index}]", fallback))
    return entries


def auth_header(api_key: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "mms-health-watchdog/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def normalize_url(base_url: str, endpoint: str) -> str:
    base = base_url.rstrip("/")
    endpoint = endpoint.strip()
    if not endpoint or endpoint == "manual":
        endpoint = "/models"
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    return base + endpoint


def provider_models_endpoint(provider_id: str, route: dict[str, Any], providers: dict[str, dict[str, Any]]) -> str | None:
    cfg = providers.get(provider_id) or {}
    endpoint = str(cfg.get("models_endpoint") or "").strip()
    if endpoint == "manual":
        return None
    base = str(route.get("openai_base_url") or route.get("anthropic_base_url") or "").strip()
    if not base:
        return None
    return normalize_url(base, endpoint or "/models")


def url_host_port(url: str) -> tuple[str, int] | None:
    parsed = urllib.parse.urlsplit(url)
    if not parsed.hostname:
        return None
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.hostname, int(port)


def tcp_tls_check(name: str, url: str, timeout: int, failure_level: str = "critical") -> CheckResult:
    start = time.time()
    hp = url_host_port(url)
    if not hp:
        return CheckResult("endpoint", name, "critical", "fail", "invalid url", url=url)
    host, port = hp
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            if urllib.parse.urlsplit(url).scheme == "https":
                ctx = ssl.create_default_context()
                with ctx.wrap_socket(sock, server_hostname=host):
                    pass
    except Exception as exc:
        return CheckResult(
            "endpoint",
            name,
            failure_level,
            "fail",
            f"{type(exc).__name__}: {exc}",
            latency_ms=int((time.time() - start) * 1000),
            url=url,
        )
    return CheckResult(
        "endpoint",
        name,
        "info",
        "ok",
        "tcp/tls reachable",
        latency_ms=int((time.time() - start) * 1000),
        url=url,
    )


def http_get_json(name: str, url: str, api_key: str, timeout: int, failure_level: str = "critical") -> tuple[CheckResult, set[str]]:
    start = time.time()
    req = urllib.request.Request(url, headers=auth_header(api_key), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read(800_000)
            latency = int((time.time() - start) * 1000)
            models = parse_model_ids(raw)
            detail = f"HTTP {response.status}; models={len(models)}"
            level = "info" if models else "warning"
            status = "ok" if response.status < 400 else "fail"
            return CheckResult("models_endpoint", name, level, status, detail, latency, url), models
    except urllib.error.HTTPError as exc:
        raw = exc.read(800)
        latency = int((time.time() - start) * 1000)
        level = "warning" if exc.code == 404 else failure_level
        return (
            CheckResult(
                "models_endpoint",
                name,
                level,
                "fail",
                f"HTTP {exc.code}; {raw.decode('utf-8', 'replace')[:180]}",
                latency,
                url,
            ),
            set(),
        )
    except Exception as exc:
        return (
            CheckResult(
                "models_endpoint",
                name,
                failure_level,
                "fail",
                f"{type(exc).__name__}: {exc}",
                int((time.time() - start) * 1000),
                url,
            ),
            set(),
        )


def parse_model_ids(raw: bytes) -> set[str]:
    try:
        parsed = json.loads(raw.decode("utf-8", "replace") or "{}")
    except Exception:
        return set()
    items: Any = parsed.get("data") if isinstance(parsed, dict) else parsed
    if not isinstance(items, list):
        return set()
    ids = set()
    for item in items:
        if isinstance(item, dict):
            model_id = str(item.get("id") or item.get("model") or item.get("name") or "").strip()
        else:
            model_id = str(item or "").strip()
        if model_id:
            ids.add(model_id)
    return ids


def model_presence_alias_candidates(model_id: str) -> set[str]:
    """Return acceptable /models ids for virtual route aliases.

    Some gateways expose effort variants as request-time aliases like
    `gemini-3-flash-agent(high)` while `/models` only lists the base model.
    """
    normalized = str(model_id or "").strip()
    candidates = {normalized} if normalized else set()
    if normalized.endswith(")") and "(" in normalized:
        base = normalized.rsplit("(", 1)[0].strip()
        if base:
            candidates.add(base)
    return candidates


def route_source_checks(config_dir: Path, routes_payload: dict[str, Any], policy_payload: dict[str, Any]) -> list[CheckResult]:
    results: list[CheckResult] = []
    routes_text = json.dumps(routes_payload, ensure_ascii=False)
    for marker, detail in OLD_ROUTE_MARKERS.items():
        if marker in routes_text:
            results.append(CheckResult("config", marker, "critical", "fail", detail))
    if not results:
        results.append(CheckResult("config", "old_route_markers", "info", "ok", "no forbidden old route URLs in active Router"))

    routes = routes_payload.get("routes") if isinstance(routes_payload.get("routes"), dict) else {}
    allowed = model_policy_allowed(policy_payload)
    missing = sorted(model for model in allowed if model not in routes)
    if missing:
        results.append(CheckResult("policy", "allowed_models", "critical", "fail", "missing from Router: " + ", ".join(missing[:12])))
    else:
        results.append(CheckResult("policy", "allowed_models", "info", "ok", f"{len(allowed)} allowed models present"))
    return results


def endpoint_checks(
    routes_payload: dict[str, Any],
    providers: dict[str, dict[str, Any]],
    timeout: int,
) -> tuple[list[CheckResult], dict[tuple[str, str], set[str]]]:
    results: list[CheckResult] = []
    model_sets: dict[tuple[str, str], set[str]] = {}
    seen: dict[tuple[str, str], tuple[dict[str, Any], str]] = {}
    primary_providers: set[str] = set()
    for _model, role, route in route_entries(routes_payload):
        provider_id = str(route.get("provider_id") or "").strip()
        if not provider_id:
            continue
        if role == "primary":
            primary_providers.add(provider_id)
        endpoint = provider_models_endpoint(provider_id, route, providers)
        if not endpoint:
            continue
        seen.setdefault((provider_id, endpoint), (route, endpoint))

    for (provider_id, endpoint), (route, _endpoint) in sorted(seen.items()):
        base = str(route.get("openai_base_url") or route.get("anthropic_base_url") or endpoint)
        failure_level = "critical" if provider_id in primary_providers else "warning"
        results.append(tcp_tls_check(provider_id, base, timeout, failure_level=failure_level))
        result, models = http_get_json(provider_id, endpoint, str(route.get("api_key") or ""), timeout, failure_level=failure_level)
        results.append(result)
        model_sets[(provider_id, endpoint)] = models
    return results, model_sets


def model_presence_checks(
    routes_payload: dict[str, Any],
    providers: dict[str, dict[str, Any]],
    model_sets: dict[tuple[str, str], set[str]],
    policy_payload: dict[str, Any],
) -> list[CheckResult]:
    allowed = model_policy_allowed(policy_payload)
    missing: list[str] = []
    checked = 0
    for model, role, route in route_entries(routes_payload):
        if allowed and model not in allowed:
            continue
        provider_id = str(route.get("provider_id") or "").strip()
        endpoint = provider_models_endpoint(provider_id, route, providers)
        if not endpoint:
            continue
        models = model_sets.get((provider_id, endpoint)) or set()
        if not models:
            continue
        # Missing models on a fallback provider are not immediately actionable
        # when the primary route remains healthy; treat this watchdog as a
        # primary availability check plus endpoint liveness check.
        if role != "primary":
            continue
        checked += 1
        wire_model = str(route.get("model_id") or model).strip()
        if not (model_presence_alias_candidates(wire_model) & models):
            missing.append(f"{model}@{provider_id}/{role} as {wire_model}")
    if missing:
        return [CheckResult("model_presence", "policy_models", "warning", "fail", "missing: " + ", ".join(missing[:12]))]
    return [CheckResult("model_presence", "policy_models", "info", "ok", f"checked {checked} route entries with model lists")]


def build_report(config_dir: Path, timeout: int, require_bundle: bool = False) -> dict[str, Any]:
    bundle = load_verified_latest_bundle(config_dir)
    results: list[CheckResult] = []
    payloads = bundle.get("payloads") if isinstance(bundle.get("payloads"), dict) else {}
    if bundle.get("status") == "ok":
        routes_payload = payloads.get("router") if isinstance(payloads.get("router"), dict) else {}
        policy_payload = payloads.get("policy") if isinstance(payloads.get("policy"), dict) else {}
        results.append(CheckResult("bundle", "latest_approved", "info", "ok", str(bundle.get("detail") or "")))
        route_source = "latest-approved"
    elif bundle.get("status") != "missing" or require_bundle:
        routes_payload = {}
        policy_payload = {}
        results.append(
            CheckResult(
                "bundle",
                "latest_approved",
                "critical",
                "fail",
                "stale_or_invalid_bundle: " + str(bundle.get("detail") or "unknown bundle error"),
            )
        )
        route_source = "invalid_latest-approved"
    else:
        routes_payload = read_json(config_dir / "model-routes.json")
        policy_payload = read_json(config_dir / "model-policy.json")
        results.append(CheckResult("bundle", "latest_approved", "info", "ok", "latest-approved missing; using legacy root artifacts"))
        route_source = "legacy-root"
    config_payload = read_toml(config_dir / "config.toml")
    providers = provider_config_map(config_payload)
    if bundle.get("status") == "ok":
        for provider_id, profile in provider_profile_map(payloads.get("profile") if isinstance(payloads.get("profile"), dict) else {}).items():
            providers.setdefault(provider_id, profile)
    results.extend(route_source_checks(config_dir, routes_payload, policy_payload))
    endpoint_results, model_sets = endpoint_checks(routes_payload, providers, timeout)
    results.extend(endpoint_results)
    results.extend(model_presence_checks(routes_payload, providers, model_sets, policy_payload))

    failures = [item.to_dict() for item in results if item.status != "ok"]
    critical = [item for item in failures if item.get("level") == "critical"]
    warning = [item for item in failures if item.get("level") == "warning"]
    status = "critical" if critical else ("warning" if warning else "ok")
    return {
        "schema": "mms_health_watchdog.v1",
        "checked_at": iso_now(),
        "status": status,
        "config_dir": str(config_dir),
        "route_source": route_source,
        "bundle": {
            "status": bundle.get("status"),
            "manifest_path": bundle.get("manifest_path"),
            "detail": bundle.get("detail"),
        },
        "summary": {
            "checks": len(results),
            "critical": len(critical),
            "warning": len(warning),
            "ok": len([item for item in results if item.status == "ok"]),
        },
        "results": [item.to_dict() for item in results],
        "failures": failures,
    }


def report_fingerprint(report: dict[str, Any]) -> str:
    relevant = {
        "status": report.get("status"),
        "failures": [
            {
                "scope": item.get("scope"),
                "name": item.get("name"),
                "level": item.get("level"),
                "status": item.get("status"),
                "detail": item.get("detail"),
                "url": item.get("url"),
            }
            for item in report.get("failures") or []
        ],
    }
    return hashlib.sha256(json.dumps(relevant, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def should_notify(report: dict[str, Any], state: dict[str, Any], remind_seconds: int, notify_ok: bool) -> tuple[bool, str]:
    previous_status = str(state.get("last_status") or "")
    previous_fingerprint = str(state.get("last_fingerprint") or "")
    previous_notify = float(state.get("last_notified_at_epoch") or 0)
    fingerprint = report_fingerprint(report)
    status = str(report.get("status") or "unknown")
    now = time.time()
    if status == "ok":
        if notify_ok and previous_status and previous_status != "ok":
            return True, "recovered"
        return False, "ok_silent"
    if fingerprint != previous_fingerprint:
        return True, "new_failure"
    if now - previous_notify >= remind_seconds:
        return True, "reminder"
    return False, "deduped"


def feishu_sign(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def status_label(status: str) -> tuple[str, str, str]:
    if status == "critical":
        return "严重异常", "red", "🔴"
    if status == "warning":
        return "需要关注", "orange", "🟠"
    if status == "ok":
        return "全部正常", "green", "🟢"
    return "状态未知", "grey", "⚪"


def reason_label(reason: str) -> str:
    return {
        "new_failure": "发现新异常",
        "reminder": "异常仍未恢复",
        "recovered": "已恢复正常",
        "notify_always": "手动测试通知",
        "ok_silent": "正常静默",
        "deduped": "已去重",
    }.get(reason, reason or "未知原因")


def scope_label(scope: str) -> str:
    return {
        "config": "配置",
        "policy": "白名单",
        "endpoint": "端口/域名",
        "models_endpoint": "模型列表",
        "model_presence": "模型可用性",
    }.get(scope, scope or "未知")


def trim_detail(value: Any, limit: int = 110) -> str:
    text = str(value or "").replace("\n", " ").strip()
    text = text.replace('{"error":"Not Found","message":"', "")
    text = text.replace('","timestamp"', '" timestamp"')
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_failure_line(item: dict[str, Any]) -> str:
    level = "严重" if item.get("level") == "critical" else "警告"
    head = f"**{level}｜{scope_label(str(item.get('scope') or ''))}｜{item.get('name') or '-'}**"
    detail = trim_detail(item.get("detail"))
    url = str(item.get("url") or "").strip()
    latency = item.get("latency_ms")
    suffix = f" · {latency}ms" if isinstance(latency, int) else ""
    if url:
        return f"{head}\n{detail}{suffix}\n[查看 endpoint]({url})"
    return f"{head}\n{detail}{suffix}"


def format_feishu_card(report: dict[str, Any], reason: str) -> dict[str, Any]:
    status = str(report.get("status") or "unknown")
    title, template, icon = status_label(status)
    summary = report.get("summary") or {}
    failures = report.get("failures") or []
    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**原因：** {reason_label(reason)}\n"
                    f"**时间：** {report.get('checked_at')}\n"
                    f"**结果：** {summary.get('ok', 0)} 正常 · {summary.get('warning', 0)} 警告 · "
                    f"{summary.get('critical', 0)} 严重 / 共 {summary.get('checks', 0)} 项"
                ),
            },
        }
    ]
    if failures:
        elements.append({"tag": "hr"})
        for item in failures[:6]:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": format_failure_line(item)}})
        if len(failures) > 6:
            elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"还有 {len(failures) - 6} 项异常，查看 latest.json 获取完整结果。"}]})
    else:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "所有 active Router / Policy / endpoint 检查均正常。"}})
    elements.append({"tag": "hr"})
    elements.append(
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": "本机结果：~/.config/mms/health-watchdog/latest.json",
                }
            ],
        }
    )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": template,
            "title": {"tag": "plain_text", "content": f"{icon} MMS 探活 · {title}"},
        },
        "elements": elements,
    }


def send_feishu(webhook_url: str, secret: str, card: dict[str, Any], timeout: int) -> tuple[bool, str]:
    payload: dict[str, Any] = {
        "msg_type": "interactive",
        "card": card,
    }
    if secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = feishu_sign(secret, timestamp)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read(500).decode("utf-8", "replace")
            return response.status < 400, f"HTTP {response.status}: {body[:200]}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def update_state(state_path: Path, report: dict[str, Any], notification: dict[str, Any]) -> None:
    state = {
        "schema": "mms_health_watchdog_state.v1",
        "updated_at": iso_now(),
        "last_status": report.get("status"),
        "last_fingerprint": report_fingerprint(report),
        "last_report_at": report.get("checked_at"),
        "last_notification": notification,
    }
    if notification.get("sent"):
        state["last_notified_at_epoch"] = time.time()
        state["last_notified_at"] = iso_now()
    else:
        previous = read_json(state_path)
        if previous.get("last_notified_at_epoch"):
            state["last_notified_at_epoch"] = previous.get("last_notified_at_epoch")
            state["last_notified_at"] = previous.get("last_notified_at")
    write_json_atomic(state_path, state)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MMS health watchdog with Feishu notification")
    parser.add_argument("--config-dir", default=str(default_config_dir()))
    parser.add_argument("--env-file", default="")
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--remind-sec", type=int, default=DEFAULT_REMIND_SECONDS)
    parser.add_argument("--dry-run", action="store_true", help="Do not send Feishu notification or update state")
    parser.add_argument("--notify-ok", action="store_true", help="Notify when recovering to OK")
    parser.add_argument("--notify-always", action="store_true", help="Send a notification regardless of status/dedup")
    parser.add_argument("--print-json", action="store_true", help="Print full report JSON")
    parser.add_argument("--strict-exit", action="store_true", help="Return non-zero when status is warning/critical")
    parser.add_argument("--require-bundle", action="store_true", help="Fail closed when latest-approved bundle is missing")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    config_dir = Path(args.config_dir).expanduser()
    watchdog_dir = config_dir / WATCHDOG_DIR_NAME
    env_file = Path(args.env_file).expanduser() if args.env_file else config_dir / ENV_FILE_NAME
    load_env_file(env_file)

    require_bundle = resolve_require_bundle(args, config_dir)
    report = build_report(config_dir, max(1, int(args.timeout_sec)), require_bundle=require_bundle)
    latest_path = watchdog_dir / LATEST_FILE_NAME
    state_path = watchdog_dir / STATE_FILE_NAME
    log_path = config_dir / "logs" / LOG_FILE_NAME
    write_json_atomic(latest_path, report)
    append_log(log_path, {"ts": iso_now(), "status": report.get("status"), "summary": report.get("summary"), "failures": report.get("failures")})

    state = read_json(state_path)
    notify, reason = should_notify(report, state, max(60, int(args.remind_sec)), bool(args.notify_ok))
    if args.notify_always:
        notify, reason = True, "notify_always"

    notification = {"wanted": notify, "reason": reason, "sent": False, "detail": ""}
    webhook_url = os.environ.get("MMS_FEISHU_WEBHOOK_URL", "").strip()
    webhook_secret = os.environ.get("MMS_FEISHU_WEBHOOK_SECRET", "").strip()
    if notify and not args.dry_run:
        if webhook_url:
            sent, detail = send_feishu(webhook_url, webhook_secret, format_feishu_card(report, reason), max(1, int(args.timeout_sec)))
            notification.update({"sent": sent, "detail": detail})
        else:
            notification.update({"sent": False, "detail": "MMS_FEISHU_WEBHOOK_URL is not set"})
    elif args.dry_run:
        notification["detail"] = "dry_run"

    if not args.dry_run:
        update_state(state_path, report, notification)

    if args.print_json:
        print(json.dumps({"report": report, "notification": notification}, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps({"status": report.get("status"), "summary": report.get("summary"), "notification": notification}, ensure_ascii=False, sort_keys=True))
    if args.strict_exit:
        return 2 if report.get("status") == "critical" else (1 if report.get("status") == "warning" else 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
