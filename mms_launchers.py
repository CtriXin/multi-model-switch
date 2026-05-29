"""MMS 启动器：按 provider 或账号档案启动 CLI。"""

from contextlib import contextmanager
import copy
import inspect
import json
import os
import re
import shlex
import shutil
import sys
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from mms_account_state import activated_claude_account_state, seed_agy_state, seed_claude_state, seed_gemini_state
from mms_i18n import normalize_language
from mms_opencode_agents import (
    opencode_apply_agent_bypass_permissions,
    opencode_lite_agent_configs,
    opencode_lite_pro_agent_configs,
    opencode_permission_bypass_value,
)
from mms_opencode_config import (
    OPENCODE_API_KEY_ENV,
    OPENCODE_BYPASS_FLAG,
    OPENCODE_BYPASS_PERMISSION_ENV,
    OPENCODE_DEFAULT_OUTPUT_LIMIT,
    OPENCODE_IMAGE_INPUT_MODELS,
    OPENCODE_LITE_DEFAULT_AGENT,
    OPENCODE_MODEL_LIMIT_OVERRIDES,
    OPENCODE_PROVIDER_ID,
    opencode_agent_model_refs as _opencode_agent_model_refs,
    opencode_apply_bypass_env as _opencode_apply_bypass_env,
    opencode_apply_route_env as _opencode_apply_route_env,
    opencode_build_config_content as _opencode_build_config_content_impl,
    opencode_build_config_payload as _opencode_build_config_payload_impl,
    opencode_bypass_enabled as _opencode_bypass_enabled,
    opencode_config_slug as _opencode_config_slug,
    opencode_entrypoint as _opencode_entrypoint,
    opencode_env_bool as _opencode_env_bool,
    opencode_explicit_output_limit as _opencode_explicit_output_limit,
    opencode_launch_candidates as _opencode_launch_candidates,
    opencode_launch_preflight_enabled as _opencode_launch_preflight_enabled,
    opencode_model_config as _opencode_model_config_impl,
    opencode_model_limit_override as _opencode_model_limit_override,
    opencode_model_names as _opencode_model_names,
    opencode_model_output_limit as _opencode_model_output_limit,
    opencode_model_ref as _opencode_model_ref,
    opencode_model_requires_reasoning_roundtrip_guard as _opencode_model_requires_reasoning_roundtrip_guard,
    opencode_output_limit as _opencode_output_limit,
    opencode_preflight_timeout as _opencode_preflight_timeout,
    opencode_provider_base_url as _opencode_provider_base_url,
    opencode_route_by_id as _opencode_route_by_id,
    opencode_route_env_key as _opencode_route_env_key,
    opencode_route_model_ref as _opencode_route_model_ref,
    opencode_route_provider_ref as _opencode_route_provider_ref,
    opencode_runtime_bool as _opencode_runtime_bool,
    opencode_runtime_routes as _opencode_runtime_routes,
)
from mms_opencode_env import (
    opencode_export_config_path as _opencode_export_config_path_impl,
    opencode_gateway_env as _opencode_gateway_env_impl,
    opencode_global_export_env as _opencode_global_export_env_impl,
    opencode_global_omo_env as _opencode_global_omo_env_impl,
    opencode_provider_export_env as _opencode_provider_export_env_impl,
    opencode_set_soft_home as _opencode_set_soft_home_impl,
    opencode_write_config as _opencode_write_config_impl,
)
from mms_opencode_launch import (
    launch_opencode as _opencode_launch_impl,
    opencode_gateway_health_check as _opencode_gateway_health_check_impl,
    opencode_global_command as _opencode_global_command_impl,
    opencode_is_global_profile_runtime as _opencode_is_global_profile_runtime_impl,
    opencode_session_command as _opencode_session_command_impl,
)
from mms_opencode_preflight import (
    opencode_run_preflight as _opencode_run_preflight_impl,
    opencode_select_launch_candidate as _opencode_select_launch_candidate_impl,
)
from mms_opencode_session import (
    clear_opencode_config_env as _clear_opencode_config_env,
    overlay_opencode_session_assets as _overlay_opencode_session_assets_impl,
    opencode_rtk_plugin_path as _opencode_rtk_plugin_path_impl,
    opencode_session_plugin_runtime as _opencode_session_plugin_runtime,
    opencode_xmem_plugin_path as _opencode_xmem_plugin_path_impl,
    overlay_opencode_plugin as _overlay_opencode_plugin_impl,
)
from mms_core import (
    DEFAULT_ACCOUNT_TIMEZONE,
    _normalize_claude_1m_mode,
    _probe_models,
    _runtime_force_ipv4,
    _runtime_httpx_request,
    detect_working_base_url,
    load_config,
    preference_asset_root,
)
from mms_fake_upstream import (
    ensure_local_proxy as _ensure_fake_upstream_proxy,
    fake_proxy_probe as _fake_proxy_probe,
    is_enabled as _fake_upstream_enabled,
    status_payload as _fake_upstream_status_payload,
)
from mms_host_context import host_capability_env, resolve_tool_bins, write_host_context
from mms_project_store import CLAUDE_PERSISTENT_ENTRIES, claude_raw_entry_path, ensure_claude_project_store, read_slot_marker, write_slot_marker
from mms_runtime import cli_search_dirs, prepare_cli_command
from mms_runtime_context import (
    DEFAULT_CONTEXT_WINDOW as _DEFAULT_CONTEXT_WINDOW,
    MIMO_PLAIN_ONE_M_CONTEXT_WINDOWS as _MIMO_PLAIN_ONE_M_CONTEXT_WINDOWS,
    MODEL_CONTEXT_WINDOWS as _MODEL_CONTEXT_WINDOWS,
    ONE_M_CONTEXT_SUFFIX as _ONE_M_CONTEXT_SUFFIX,
    ONE_M_SUFFIX_BASE_SAFE_CONTEXT_WINDOWS as _ONE_M_SUFFIX_BASE_SAFE_CONTEXT_WINDOWS,
    ONE_M_SUFFIX_CONTEXT_WINDOWS as _ONE_M_SUFFIX_CONTEXT_WINDOWS,
    coerce_context_window as _coerce_context_window_impl,
    load_model_context_overrides as _load_model_context_overrides_impl,
    lookup_context_window as _lookup_context_window_impl,
    provider_advertises_plain_mimo_1m as _provider_advertises_plain_mimo_1m_impl,
)
from mms_session_index import finalize_claude_session, list_indexed_sessions, record_claude_session_start
from mms_session_packet import write_session_packet
from mms_state_io import atomic_write_json, atomic_write_text, locked_state_file
from mms_state_io import resolve_current_workdir as _safe_getcwd

_build_gateway_url = None
codex_claude_bridge = None
gemini_claude_bridge = None
gateway_claude_bridge = None
codex_chatcompletions_bridge = None
codex_responses_bridge = None
_write_route_status = None
build_provider_speed_scope = None

try:
    from mms_health_cache import get_model_health as _get_model_health
except ImportError:
    def _get_model_health(*_a, **_kw): return None


def _ensure_bridge_helpers():
    global _build_gateway_url, codex_claude_bridge, gemini_claude_bridge
    global gateway_claude_bridge, codex_chatcompletions_bridge, codex_responses_bridge, _write_route_status
    if _build_gateway_url is not None:
        return
    from mms_bridge import (
        _build_gateway_url as _bgw,
        codex_claude_bridge as _ccb,
        gemini_claude_bridge as _gcb,
        gateway_claude_bridge as _gwb,
        codex_chatcompletions_bridge as _cccb,
        codex_responses_bridge as _crb,
        _write_route_status as _wrs,
    )
    _build_gateway_url = _bgw
    codex_claude_bridge = _ccb
    gemini_claude_bridge = _gcb
    gateway_claude_bridge = _gwb
    codex_chatcompletions_bridge = _cccb
    codex_responses_bridge = _crb
    _write_route_status = _wrs


def _gateway_claude_bridge_context(*args, **kwargs):
    target = gateway_claude_bridge
    if target is None:
        raise RuntimeError("gateway_claude_bridge 未初始化")
    signature_target = getattr(target, "__wrapped__", target)
    try:
        signature = inspect.signature(signature_target)
    except (TypeError, ValueError):
        signature = None
    if signature is None:
        return target(*args, **kwargs)
    allowed = set(signature.parameters.keys())
    filtered = dict(kwargs)
    dropped = [key for key in list(filtered.keys()) if key not in allowed]
    for key in dropped:
        filtered.pop(key, None)
    if dropped:
        console.print(
            "[yellow]检测到旧版 bridge 签名，已自动降级忽略参数: "
            + ", ".join(sorted(dropped))
            + "[/yellow]"
        )
    return target(*args, **filtered)


def _ensure_speed_stats():
    global build_provider_speed_scope
    if build_provider_speed_scope is not None:
        return
    from mms_speed_stats import build_provider_speed_scope as _bps
    build_provider_speed_scope = _bps

class _LazyConsole:
    _instance = None
    def __getattr__(self, name):
        if _LazyConsole._instance is None:
            from rich.console import Console
            _LazyConsole._instance = Console()
        return getattr(_LazyConsole._instance, name)

console = _LazyConsole()

# Keep the former private helper names importable while the implementation lives in mms_opencode_agents.
_opencode_lite_agent_configs = opencode_lite_agent_configs
_opencode_lite_pro_agent_configs = opencode_lite_pro_agent_configs
_opencode_permission_bypass_value = opencode_permission_bypass_value
_opencode_apply_agent_bypass_permissions = opencode_apply_agent_bypass_permissions


def _mask_secret(value, *, keep=2):
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= keep:
        return "*" * len(text)
    return text[:keep] + "*" * max(2, len(text) - keep)


def _mask_proxy_url(proxy_url):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return ""
    try:
        parsed = urlsplit(proxy_url)
    except Exception:
        return proxy_url
    try:
        parsed_port = parsed.port
    except ValueError:
        return proxy_url
    username = parsed.username or ""
    password = parsed.password or ""
    host = parsed.hostname or ""
    port = f":{parsed_port}" if parsed_port else ""
    auth = ""
    if username:
        auth = _mask_secret(username)
        if password:
            auth += ":****"
        auth += "@"
    netloc = f"{auth}{host}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path or "", parsed.query or "", parsed.fragment or ""))


def _runtime_network_summary(runtime):
    proxy_url = _mask_proxy_url(runtime.get("proxy", ""))
    timezone_name = str(runtime.get("timezone") or DEFAULT_ACCOUNT_TIMEZONE).strip() or DEFAULT_ACCOUNT_TIMEZONE
    ipv4_label = "on" if _runtime_force_ipv4(runtime) else "off"
    dns_mode = "fake-local" if _fake_upstream_enabled() else _proxy_dns_mode(runtime.get("proxy", ""))
    locale_value = _runtime_locale_env(runtime).get("LANG", "en_US.UTF-8")
    parts = [f"DNS {dns_mode}", f"TZ {timezone_name}", f"LANG {locale_value}", f"IPv4 {ipv4_label}"]
    if proxy_url:
        parts.insert(0, f"Proxy {proxy_url}")
    else:
        parts.insert(0, "Proxy direct")
    no_proxy = str(runtime.get("no_proxy") or "").strip()
    if no_proxy:
        parts.append("NO_PROXY set")
    return " | ".join(parts)


def _guard_utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _runtime_locale_env(runtime=None):
    runtime = runtime if isinstance(runtime, dict) else {}
    raw_locale = (
        str(runtime.get("locale") or "").strip()
        or str(os.environ.get("MMS_LOCALE") or "").strip()
        or str(os.environ.get("LC_ALL") or "").strip()
        or str(os.environ.get("LANG") or "").strip()
    )
    normalized_lang = normalize_language(
        str(runtime.get("language") or "").strip()
        or str(os.environ.get("MMS_LANG") or "").strip()
        or raw_locale
    )
    if raw_locale and "." in raw_locale and "_" in raw_locale:
        locale_value = raw_locale
    elif normalized_lang == "zh":
        locale_value = "zh_CN.UTF-8"
    else:
        locale_value = "en_US.UTF-8"
    return {
        "LANG": locale_value,
        "LC_ALL": locale_value,
        "LC_CTYPE": locale_value,
        "LC_MESSAGES": locale_value,
    }


def _apply_runtime_locale_profile(env, runtime=None):
    env = env if isinstance(env, dict) else {}
    env.update(_runtime_locale_env(runtime))
    return env

def _provider_id_set_from_env(env_name):
    raw = str(os.environ.get(env_name) or "").strip()
    return {
        item.strip().lower()
        for item in raw.split(",")
        if item.strip()
    }


def _runtime_declares_sensitive_claude(runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    if bool(runtime.get("skip_anthropic_probe")):
        return True
    return str(runtime.get("claude_provider_sensitivity") or "").strip().lower() in {
        "sensitive",
        "private",
        "isolated",
    }


def _coerce_context_window(value):
    """Compatibility wrapper for context-window coercion."""
    return _coerce_context_window_impl(value)


def _provider_advertises_plain_mimo_1m(provider_id):
    """Compatibility wrapper for MiMo plain 1M provider detection."""
    return _provider_advertises_plain_mimo_1m_impl(provider_id)


def _load_model_context_overrides():
    """Compatibility wrapper for model context-window overrides."""
    return _load_model_context_overrides_impl(
        _MODEL_CONTEXT_OVERRIDES_PATH,
        _MODEL_CONTEXT_OVERRIDES_CACHE,
    )


def _lookup_context_window(model_name, provider_id=None):
    """Compatibility wrapper for runtime context-window lookup."""
    return _lookup_context_window_impl(
        model_name,
        provider_id=provider_id,
        context_overrides_loader=_load_model_context_overrides,
        model_context_windows=_MODEL_CONTEXT_WINDOWS,
    )


def _runtime_supports_claude_1m(runtime):
    """Compatibility wrapper for Claude 1M support policy."""
    from mms_claude_model import runtime_supports_claude_1m

    return runtime_supports_claude_1m(runtime)


def _effective_context_window(*models, enable_claude_1m=True, provider_id=None):
    """Compatibility wrapper for Claude-routed context window resolution."""
    from mms_claude_model import effective_context_window

    return effective_context_window(
        *models,
        enable_claude_1m=enable_claude_1m,
        provider_id=provider_id,
    )


def _runtime_is_sensitive_claude_provider(runtime):
    provider_id = str((runtime or {}).get("id", "")).strip().lower()
    sensitive_ids = _provider_id_set_from_env("MMS_CLAUDE_SENSITIVE_PROVIDER_IDS")
    return (provider_id and provider_id in sensitive_ids) or _runtime_declares_sensitive_claude(runtime)




@contextmanager
def _launch_status(message, *, spinner="dots"):
    """为启动慢步骤提供可见 spinner，避免用户干等。"""
    status_cm = None
    try:
        status_cm = console.status(f"[cyan]{message}[/cyan]", spinner=spinner)
        status_cm.__enter__()
    except Exception:
        console.print(f"[dim]⏳ {message}[/dim]")
    start = perf_counter()
    try:
        yield start
    finally:
        if status_cm is not None:
            exc_type, exc, tb = sys.exc_info()
            status_cm.__exit__(exc_type, exc, tb)


def _print_launch_step_done(label, started_at, detail=None, *, style="dim"):
    elapsed = perf_counter() - started_at
    suffix = f" · {detail}" if detail else ""
    console.print(f"[{style}]· {label} 完成 ({elapsed:.1f}s){suffix}[/{style}]")


def _launch_timing_threshold_sec():
    raw = str(os.environ.get("MMS_LAUNCH_TIMING_THRESHOLD_SEC") or "").strip()
    if not raw:
        return 5.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 5.0


def _launch_timing_enabled():
    return str(os.environ.get("MMS_LAUNCH_TIMING") or "").strip().lower() in {"1", "true", "yes", "on"}


@contextmanager
def _timed_launch_step(timings, label):
    start = perf_counter()
    try:
        yield
    finally:
        if isinstance(timings, list):
            timings.append((str(label), perf_counter() - start))


def _print_launch_timing_breakdown(timings, *, total_elapsed):
    if not isinstance(timings, list) or not timings:
        return
    if not _launch_timing_enabled() and total_elapsed < _launch_timing_threshold_sec():
        return
    top = sorted(
        ((label, elapsed) for label, elapsed in timings if elapsed >= 0.05),
        key=lambda item: item[1],
        reverse=True,
    )[:8]
    if not top:
        return
    detail = "；".join(f"{label} {elapsed:.1f}s" for label, elapsed in top)
    console.print(f"[dim]  慢步骤拆分: {detail}[/dim]")


def _prepare_claude_env_with_status(runtime, **kwargs):
    timings = []
    with _launch_status("准备 Claude 会话环境中...", spinner="dots") as step_start:
        env = _claude_gateway_env(runtime, _timings=timings, **kwargs)
    selected = kwargs.get("selected_model") or kwargs.get("heavy_model")
    detail = selected if selected else runtime.get("id", "provider")
    total_elapsed = perf_counter() - step_start
    _print_launch_step_done("Claude 会话环境准备", step_start, detail)
    _print_launch_timing_breakdown(timings, total_elapsed=total_elapsed)
    return env


def _real_user_home():
    explicit = str(os.environ.get("MMS_REAL_HOME", "")).strip()
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))

    home = os.path.abspath(os.environ.get("HOME") or os.path.expanduser("~"))
    markers = (
        f"{os.sep}.config{os.sep}mms{os.sep}codex-gateway{os.sep}",
        f"{os.sep}.config{os.sep}mms{os.sep}claude-gateway{os.sep}",
    )
    for marker in markers:
        if marker in home:
            return home.split(marker, 1)[0]
    return home


def _real_user_path(*parts):
    return os.path.join(_real_user_home(), *parts)


def _account_guard_state_path():
    return _real_user_path(".config", "mms", "account-guard-state.json")


def _load_json_dict_unlocked(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_account_guard_state():
    path = _account_guard_state_path()
    with locked_state_file(path):
        return _load_json_dict_unlocked(path)


def _write_account_guard_state(payload):
    path = _account_guard_state_path()
    with locked_state_file(path):
        atomic_write_json(path, payload, mode=0o600)


def _claude_account_guard_entry(state, account_id):
    if not isinstance(state, dict):
        state = {}
    accounts = state.setdefault("accounts", {})
    key = str(account_id or "").strip() or "_anonymous"
    entry = accounts.get(key)
    if not isinstance(entry, dict):
        entry = {}
        accounts[key] = entry
    return accounts, key, entry


def _count_live_session_dirs(sessions_dir):
    if not os.path.isdir(sessions_dir):
        return 0
    alive = 0
    for name in os.listdir(sessions_dir):
        session_home = os.path.join(sessions_dir, str(name))
        if not os.path.isdir(session_home):
            continue
        if _session_home_is_active(session_home):
            alive += 1
    return alive


def _proxy_fingerprint(proxy_url):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return "direct"
    try:
        parsed = urlsplit(proxy_url)
    except Exception:
        return proxy_url
    scheme = parsed.scheme or "proxy"
    host = parsed.hostname or "unknown"
    port = f":{parsed.port}" if parsed.port else ""
    auth = "+auth" if parsed.username or parsed.password else ""
    return f"{scheme}://{host}{port}{auth}"


def _account_guard_profile(runtime):
    no_proxy = str(runtime.get("no_proxy") or "").strip()
    return {
        "proxy_fingerprint": _proxy_fingerprint(runtime.get("proxy")),
        "timezone": str(runtime.get("timezone") or DEFAULT_ACCOUNT_TIMEZONE).strip() or DEFAULT_ACCOUNT_TIMEZONE,
        "force_ipv4": bool(_runtime_force_ipv4(runtime)),
        "no_proxy": no_proxy,
        "no_proxy_set": bool(no_proxy),
    }


def _build_account_guard_report(account):
    account_id = str(account.get("id") or "").strip()
    home_dir = os.path.expanduser(str(account.get("home_dir") or "").strip())
    sessions_dir = os.path.join(home_dir, "s") if home_dir else ""
    active_before = _count_live_session_dirs(sessions_dir)
    active_after = active_before + 1 if home_dir else active_before

    state = _read_account_guard_state()
    _accounts, _key, entry = _claude_account_guard_entry(state, account_id)
    previous_profile = entry.get("last_profile") if isinstance(entry.get("last_profile"), dict) else {}
    current_profile = _account_guard_profile(account)

    drift_fields = []
    drift_labels = {
        "proxy_fingerprint": "proxy",
        "timezone": "timezone",
        "force_ipv4": "ipv4",
        "no_proxy": "no_proxy",
    }
    if previous_profile:
        for key, label in drift_labels.items():
            previous_value = previous_profile.get(key)
            current_value = current_profile.get(key)
            if previous_value is None:
                continue
            if previous_value != current_value:
                drift_fields.append(label)

    consecutive_failures = 0
    try:
        consecutive_failures = max(0, int(entry.get("consecutive_failures", 0) or 0))
    except Exception:
        consecutive_failures = 0

    score = 100
    if active_after >= 3:
        score -= 18
    elif active_after >= 2:
        score -= 8
    if "proxy" in drift_fields:
        score -= 22
    if "timezone" in drift_fields:
        score -= 10
    if "ipv4" in drift_fields:
        score -= 8
    if "no_proxy" in drift_fields:
        score -= 5
    score -= min(consecutive_failures, 3) * 12
    score = max(0, min(100, score))

    if active_after > 4:
        status = "blocked"
        blocked_reason = f"该账号当前将达到 {active_after} 个并发会话，已超过安全上限 4"
    elif score >= 85:
        status = "stable"
        blocked_reason = ""
    elif score >= 60:
        status = "watch"
        blocked_reason = ""
    else:
        status = "risky"
        blocked_reason = ""

    return {
        "account_id": account_id,
        "profile": current_profile,
        "drift_fields": drift_fields,
        "active_sessions_before": active_before,
        "active_sessions_after": active_after,
        "consecutive_failures": consecutive_failures,
        "score": score,
        "status": status,
        "blocked_reason": blocked_reason,
        "first_seen": not bool(previous_profile),
        "last_exit_code": entry.get("last_exit_code"),
    }


def _claude_guard_runtime(runtime):
    guard_runtime = dict(runtime or {})
    auth_mode = str(guard_runtime.get("auth_mode") or "api_key").strip() or "api_key"
    if auth_mode == "api_key" and not str(guard_runtime.get("home_dir") or "").strip():
        guard_runtime["home_dir"] = _real_user_path(".config", "mms", "claude-gateway")
    return guard_runtime


def _format_account_guard_summary(report):
    if not isinstance(report, dict):
        return ""
    status_labels = {
        "stable": "stable",
        "watch": "watch",
        "risky": "risky",
        "blocked": "blocked",
    }
    drift = report.get("drift_fields") or []
    drift_label = "first run" if report.get("first_seen") else ("stable" if not drift else ",".join(drift))
    parts = [
        f"账号守护 {status_labels.get(report.get('status'), 'unknown')}",
        f"score {report.get('score', 0)}",
        f"sessions {report.get('active_sessions_after', 0)}",
        f"profile {drift_label}",
    ]
    failures = int(report.get("consecutive_failures", 0) or 0)
    if failures:
        parts.append(f"failures {failures}")
    return " | ".join(parts)


def _persist_account_guard_launch(account_id, report, *, session_home=""):
    path = _account_guard_state_path()
    with locked_state_file(path):
        state = _load_json_dict_unlocked(path)
        _accounts, _key, entry = _claude_account_guard_entry(state, account_id)
        launch_count = 0
        try:
            launch_count = int(entry.get("launch_count", 0) or 0)
        except Exception:
            launch_count = 0
        entry.update(
            {
                "launch_count": launch_count + 1,
                "last_launch_at": _guard_utc_now(),
                "last_profile": dict((report or {}).get("profile") or {}),
                "last_score": int((report or {}).get("score", 0) or 0),
                "last_status": str((report or {}).get("status") or ""),
                "last_drift_fields": list((report or {}).get("drift_fields") or []),
                "last_active_sessions": int((report or {}).get("active_sessions_after", 0) or 0),
                "last_session_home": str(session_home or ""),
            }
        )
        atomic_write_json(path, state, mode=0o600)


def _record_account_guard_finalize(account_id, *, exit_code=None, stale_cleanup=False):
    account_id = str(account_id or "").strip()
    if not account_id:
        return
    path = _account_guard_state_path()
    with locked_state_file(path):
        state = _load_json_dict_unlocked(path)
        _accounts, _key, entry = _claude_account_guard_entry(state, account_id)
        entry["last_exit_at"] = _guard_utc_now()
        entry["last_exit_code"] = exit_code
        if stale_cleanup or exit_code is None:
            atomic_write_json(path, state, mode=0o600)
            return
        failures = 0
        try:
            failures = int(entry.get("consecutive_failures", 0) or 0)
        except Exception:
            failures = 0
        entry["consecutive_failures"] = 0 if int(exit_code) == 0 else max(0, failures) + 1
        atomic_write_json(path, state, mode=0o600)


_MODEL_CONTEXT_OVERRIDES_PATH = _real_user_path(".config", "mms", "model-context-overrides.json")
_MODEL_CONTEXT_OVERRIDES_CACHE = {"mtime": None, "data": {"models": {}, "provider_overrides": {}}}
_CLAUDE_NETWORK_GUARD_CACHE: dict = {}
_CLAUDE_NETWORK_GUARD_TTL_SEC = 20.0
_SESSION_GUARD_MARKER_NAME = ".mms-session-guard.json"
_SESSION_GUARD_LOCK_NAME = ".mms-session-guard.lock"


def _inject_real_home_hints(env, *, include_xdg=False):
    from mms_launcher_export import inject_real_home_hints

    return inject_real_home_hints(
        env,
        include_xdg=include_xdg,
        real_user_home=_real_user_home,
        real_user_path=_real_user_path,
        inject_rescue_launch_env=_inject_rescue_launch_env,
    )


def _truthy(value):
    from mms_launcher_export import truthy

    return truthy(value)


def _rescue_default_fallback_config():
    from mms_launcher_export import rescue_default_fallback_config

    return rescue_default_fallback_config(
        environ=os.environ,
        load_config=load_config,
        truthy=_truthy,
    )


def _rescue_bridge_kwargs():
    from mms_launcher_export import rescue_bridge_kwargs

    return rescue_bridge_kwargs(
        rescue_default_fallback_config=_rescue_default_fallback_config,
    )


def _inject_rescue_launch_env(env):
    from mms_launcher_export import inject_rescue_launch_env

    return inject_rescue_launch_env(
        env,
        safe_getcwd=_safe_getcwd,
        real_user_path=_real_user_path,
        rescue_default_fallback_config=_rescue_default_fallback_config,
    )


def _host_context_real_home():
    from mms_launcher_export import host_context_real_home

    return host_context_real_home(
        real_user_path=_real_user_path,
        real_user_home=_real_user_home,
    )


def _host_tool_context(session_home, env=None):
    from mms_launcher_export import host_tool_context

    return host_tool_context(
        session_home,
        env,
        real_home_wrapper_search_path=_real_home_wrapper_search_path,
        resolve_tool_bins=resolve_tool_bins,
        wrapper_commands=_SESSION_REAL_HOME_WRAPPER_COMMANDS,
    )


def _inject_host_capability_hints(env):
    from mms_launcher_export import inject_host_capability_hints

    return inject_host_capability_hints(
        env,
        host_capability_env=host_capability_env,
        host_context_real_home=_host_context_real_home,
    )


def _install_host_context_env(env, *, cli, runtime=None, model_info=None, session_home=""):
    from mms_launcher_export import install_host_context_env

    return install_host_context_env(
        env,
        cli=cli,
        runtime=runtime,
        model_info=model_info,
        session_home=session_home,
        host_context_real_home=_host_context_real_home,
        selected_model_name=_selected_model_name,
        safe_getcwd=_safe_getcwd,
        host_tool_context=_host_tool_context,
        write_host_context=write_host_context,
    )


def _set_session_home_hint(env, session_home):
    from mms_launcher_export import set_session_home_hint

    return set_session_home_hint(env, session_home)


def _set_codex_home_hint(env, session_home):
    from mms_launcher_export import set_codex_home_hint

    return set_codex_home_hint(env, session_home)


def _set_codex_soft_home(env, session_home):
    """Keep real HOME for tools; isolate Codex config/auth in CODEX_HOME."""
    from mms_launcher_export import set_codex_soft_home

    return set_codex_soft_home(
        env,
        session_home,
        real_user_path=_real_user_path,
        set_session_home_hint=_set_session_home_hint,
        set_codex_home_hint=_set_codex_home_hint,
    )


def _set_opencode_soft_home(env, session_home):
    return _opencode_set_soft_home_impl(
        env,
        session_home,
        real_user_path=_real_user_path,
        set_session_home_hint=_set_session_home_hint,
    )


def _model_name_from_info(model_info):
    from mms_launcher_export import model_name_from_info

    return model_name_from_info(model_info)


def _selected_model_name(*candidates, model_info=None):
    from mms_launcher_export import selected_model_name

    return selected_model_name(*candidates, model_info=model_info)


def _inject_selected_model_name(env, *candidates, model_info=None):
    from mms_launcher_export import inject_selected_model_name

    return inject_selected_model_name(env, *candidates, model_info=model_info)


def _install_session_packet_env(
    env,
    *,
    cli,
    runtime,
    model_info=None,
    session_home="",
    features=None,
    extra_paths=None,
):
    from mms_launcher_export import install_session_packet_env

    return install_session_packet_env(
        env,
        cli=cli,
        runtime=runtime,
        model_info=model_info,
        session_home=session_home,
        features=features,
        extra_paths=extra_paths,
        write_session_packet=write_session_packet,
    )


def _session_guard_marker_path(session_home):
    return os.path.join(str(session_home or "").strip(), _SESSION_GUARD_MARKER_NAME)


def _session_guard_lock_path(sessions_dir):
    return os.path.join(str(sessions_dir or "").strip(), _SESSION_GUARD_LOCK_NAME)


def _session_guard_process_identity(pid):
    try:
        normalized_pid = int(pid)
    except (TypeError, ValueError):
        return ""
    if normalized_pid <= 0:
        return ""
    try:
        result = subprocess.run(
            ["ps", "-p", str(normalized_pid), "-o", "comm=,lstart="],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return str(result.stdout or "").strip()


def _session_guard_pid_alive(pid, *, identity=""):
    try:
        normalized_pid = int(pid)
    except (TypeError, ValueError):
        return False
    if normalized_pid <= 0:
        return False
    try:
        os.kill(normalized_pid, 0)
    except (ProcessLookupError, FileNotFoundError):
        return False
    except PermissionError:
        return True
    if identity:
        return _session_guard_process_identity(normalized_pid) == str(identity or "").strip()
    return True


def _read_session_guard_marker(session_home):
    marker_path = _session_guard_marker_path(session_home)
    if not marker_path:
        return {}
    return _load_json_dict_unlocked(marker_path)


def _write_session_guard_marker(session_home, *, account_id="", runtime_kind="", child_pid=None):
    marker_path = _session_guard_marker_path(session_home)
    if not marker_path:
        return
    os.makedirs(os.path.dirname(marker_path), exist_ok=True)
    with locked_state_file(marker_path):
        marker = _load_json_dict_unlocked(marker_path)
        launcher_pid = int(marker.get("launcher_pid") or os.getpid())
        marker.update(
            {
                "account_id": str(account_id or marker.get("account_id") or "").strip(),
                "runtime_kind": str(runtime_kind or marker.get("runtime_kind") or "").strip(),
                "session_home": str(session_home or ""),
                "launcher_pid": launcher_pid,
                "launcher_identity": str(
                    marker.get("launcher_identity")
                    or _session_guard_process_identity(launcher_pid)
                    or ""
                ).strip(),
                "updated_at": _guard_utc_now(),
            }
        )
        if "created_at" not in marker:
            marker["created_at"] = marker["updated_at"]
        if child_pid is not None:
            try:
                normalized_child_pid = int(child_pid)
            except (TypeError, ValueError):
                normalized_child_pid = 0
            if normalized_child_pid > 0:
                marker["child_pid"] = normalized_child_pid
                marker["child_identity"] = _session_guard_process_identity(normalized_child_pid)
        atomic_write_json(marker_path, marker, mode=0o600)


def _record_session_child_pid(session_home, child_pid):
    _write_session_guard_marker(session_home, child_pid=child_pid)


def _session_home_is_active(session_home):
    session_home = str(session_home or "").strip()
    if not session_home or not os.path.isdir(session_home):
        return False
    marker = _read_session_guard_marker(session_home)
    if marker:
        if _session_guard_pid_alive(
            marker.get("child_pid"),
            identity=marker.get("child_identity"),
        ):
            return True
        if _session_guard_pid_alive(
            marker.get("launcher_pid"),
            identity=marker.get("launcher_identity"),
        ):
            return True
        return False
    try:
        pid = int(os.path.basename(session_home))
    except (TypeError, ValueError):
        return False
    return _session_guard_pid_alive(pid)


def _bounded_env_float(name, default):
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return float(default)
    try:
        return max(0.0, float(raw))
    except ValueError:
        return float(default)


def _session_cleanup_launch_max_entries():
    return _bounded_env_int("MMS_SESSION_CLEANUP_MAX_ENTRIES", 3)


def _session_cleanup_launch_max_seconds():
    return _bounded_env_float("MMS_SESSION_CLEANUP_MAX_SECONDS", 2.0)


def _reserve_session_home(
    sessions_dir,
    *,
    account_id="",
    runtime_kind="",
    stale_callback=None,
    max_live_sessions=None,
    timings=None,
):
    sessions_dir = str(sessions_dir or "").strip()
    if not sessions_dir:
        return "", 0, 0
    os.makedirs(sessions_dir, exist_ok=True)
    session_home = os.path.join(sessions_dir, str(os.getpid()))
    with _timed_launch_step(timings, "reserve session lock+cleanup"):
        with locked_state_file(_session_guard_lock_path(sessions_dir)):
            with _timed_launch_step(timings, "stale session cleanup"):
                _cleanup_stale_sessions(
                    sessions_dir,
                    stale_callback=stale_callback,
                    max_entries=_session_cleanup_launch_max_entries(),
                    max_seconds=_session_cleanup_launch_max_seconds(),
                )
            active_before = _count_live_session_dirs(sessions_dir)
            if _session_home_is_active(session_home):
                active_before = max(0, active_before - 1)
            active_after = active_before + 1
            if max_live_sessions is not None and active_after > int(max_live_sessions):
                return "", active_before, active_after
            os.makedirs(session_home, exist_ok=True)
            _write_session_guard_marker(
                session_home,
                account_id=account_id,
                runtime_kind=runtime_kind,
            )
            return session_home, active_before, active_after


def _real_home_wrapper_scrub_lines():
    from mms_launcher_export import real_home_wrapper_scrub_lines

    return real_home_wrapper_scrub_lines()


def _normalize_path(value):
    text = str(value or "").strip()
    if not text:
        return ""
    return os.path.abspath(os.path.expanduser(text))


def _path_is_within(path, root):
    path = _normalize_path(path)
    root = _normalize_path(root)
    if not path or not root:
        return False
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


def _runtime_net_mode(runtime):
    if _fake_upstream_enabled():
        return "fake"
    return "proxy" if str((runtime or {}).get("proxy") or "").strip() else "direct"


def _runtime_dns_mode(runtime):
    if _fake_upstream_enabled():
        return "fake-local"
    return _proxy_dns_mode((runtime or {}).get("proxy") or "")


def _build_home_context(env, runtime, cli_name):
    env = env or {}
    runtime = dict(runtime or {})
    auth_mode = str(runtime.get("auth_mode") or "api_key").strip() or "api_key"
    real_home_values = {}
    for key in ("MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME"):
        value = _normalize_path(env.get(key) or os.environ.get(key) or "")
        if value:
            real_home_values[key] = value
    if not real_home_values:
        real_home_values["derived"] = _real_user_home()
    unique_real_homes = sorted(set(real_home_values.values()))
    real_home = unique_real_homes[0] if unique_real_homes else ""
    effective_home = _normalize_path(env.get("HOME") or "")
    session_home = _normalize_path(env.get("MMS_SESSION_HOME") or "")
    account_home = _normalize_path(runtime.get("home_dir") or "")
    xdg_config_home = _normalize_path(env.get("XDG_CONFIG_HOME") or "")
    gemini_cli_home = _normalize_path(env.get("GEMINI_CLI_HOME") or "")
    config_root = os.path.join(real_home, ".config", "mms") if real_home else _real_user_path(".config", "mms")
    expected_session_home = auth_mode == "oauth" and (
        cli_name == "claude"
        or (cli_name in {"codex", "agy"} and effective_home and effective_home != real_home)
    )
    locale_value = str(env.get("LC_ALL") or env.get("LANG") or _runtime_locale_env(runtime).get("LANG") or "").strip()
    return {
        "cli": str(cli_name or "").strip(),
        "auth_mode": auth_mode,
        "real_home": real_home,
        "real_home_values": real_home_values,
        "real_home_conflict": len(unique_real_homes) > 1,
        "effective_home": effective_home,
        "session_home": session_home,
        "account_home": account_home,
        "gemini_cli_home": gemini_cli_home,
        "xdg_config_home": xdg_config_home,
        "config_root": config_root,
        "net_mode": _runtime_net_mode(runtime),
        "dns_mode": _runtime_dns_mode(runtime),
        "locale": locale_value,
        "expected_session_home": expected_session_home,
    }


def _validate_home_context_or_exit(context):
    context = dict(context or {})
    cli_name = context.get("cli") or "cli"
    auth_mode = context.get("auth_mode") or "api_key"
    real_home = context.get("real_home") or ""
    effective_home = context.get("effective_home") or ""
    session_home = context.get("session_home") or ""
    account_home = context.get("account_home") or ""
    xdg_config_home = context.get("xdg_config_home") or ""
    config_root = context.get("config_root") or ""
    gemini_cli_home = context.get("gemini_cli_home") or ""

    def _block(reason):
        console.print(f"[red]{cli_name} HOME 保护阻止启动[/red]\n[dim]{reason}[/dim]")
        sys.exit(1)

    if context.get("real_home_conflict"):
        detail = " | ".join(
            f"{key}={value}" for key, value in sorted((context.get("real_home_values") or {}).items())
        )
        _block(f"REAL_HOME hints 不一致：{detail}")
    if not real_home:
        _block("无法解析真实 HOME")

    if auth_mode != "oauth":
        if effective_home and real_home and not _path_is_within(config_root, real_home):
            _block(f"config_root 异常：{config_root}")
        return context

    if context.get("expected_session_home"):
        if not effective_home:
            _block("缺少 HOME")
        if not session_home:
            _block("缺少 MMS_SESSION_HOME")
        if effective_home != session_home:
            _block(f"HOME 与 MMS_SESSION_HOME 不一致：HOME={effective_home} | SESSION={session_home}")
        if effective_home == real_home:
            _block(f"隔离账号 HOME 落回真实 HOME：{effective_home}")
        if account_home:
            sessions_root = os.path.join(account_home, "s")
            if not _path_is_within(session_home, sessions_root):
                _block(f"session HOME 不在账号隔离目录内：{session_home}")
        if cli_name in {"codex", "agy"}:
            expected_xdg = os.path.join(session_home, ".config")
            if xdg_config_home and xdg_config_home != expected_xdg:
                _block(f"XDG_CONFIG_HOME 未跟随 session HOME：{xdg_config_home}")
    elif cli_name == "gemini":
        if not gemini_cli_home:
            _block("缺少 GEMINI_CLI_HOME")
        if gemini_cli_home == real_home:
            _block(f"GEMINI_CLI_HOME 落回真实 HOME：{gemini_cli_home}")
        if account_home and gemini_cli_home != account_home:
            _block(f"GEMINI_CLI_HOME 与账号目录不一致：{gemini_cli_home}")

    if session_home and _path_is_within(config_root, session_home):
        _block(f"config_root 不应落在 session HOME 内：{config_root}")
    if gemini_cli_home and _path_is_within(config_root, gemini_cli_home):
        _block(f"config_root 不应落在账号 HOME 内：{config_root}")
    return context


def _home_context_lines(context):
    context = dict(context or {})
    lines = []
    real_home = context.get("real_home") or ""
    if real_home:
        lines.append(f"HOME real={real_home}")
    session_home = context.get("session_home") or ""
    if session_home:
        lines.append(f"HOME session={session_home}")
    account_home = context.get("account_home") or ""
    if account_home:
        lines.append(f"HOME account={account_home}")
    gemini_cli_home = context.get("gemini_cli_home") or ""
    if gemini_cli_home:
        lines.append(f"GEMINI_CLI_HOME={gemini_cli_home}")
    extras = []
    xdg_config_home = context.get("xdg_config_home") or ""
    if xdg_config_home:
        extras.append(f"xdg={xdg_config_home}")
    config_root = context.get("config_root") or ""
    if config_root:
        extras.append(f"config_root={config_root}")
    net_mode = context.get("net_mode") or ""
    if net_mode:
        extras.append(f"net={net_mode}")
    dns_mode = context.get("dns_mode") or ""
    if dns_mode:
        extras.append(f"dns={dns_mode}")
    locale_value = context.get("locale") or ""
    if locale_value:
        extras.append(f"lang={locale_value}")
    if extras:
        lines.append(" | ".join(extras))
    return lines


def _prepare_oauth_home_context(runtime, env, cli_name):
    context = _build_home_context(env, runtime, cli_name)
    _validate_home_context_or_exit(context)
    runtime["_home_context"] = dict(context)
    for line in _home_context_lines(context):
        console.print(f"[dim]{line}[/dim]")
    return context


def _apply_proxy_env(env, proxy_url, no_proxy=""):
    proxy_url = str(proxy_url or "").strip()
    no_proxy = str(no_proxy or "").strip()
    if not proxy_url:
        return env
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env[key] = proxy_url
    for key in ("NO_PROXY", "no_proxy"):
        env[key] = no_proxy
    return env


_CLAUDE_PROXY_GUARD_TARGETS = [
    ("api", "https://api.anthropic.com"),
    ("site", "https://claude.ai"),
    ("auth", "https://anthropic.auth0.com"),
]
_CLAUDE_NO_PROXY_TOKENS = (
    "*",
    "anthropic.com",
    "api.anthropic.com",
    "claude.ai",
    "claude.com",
    "clau.de",
    "anthropic.auth0.com",
)


def _proxy_dns_mode(proxy_url):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return "direct"
    try:
        scheme = (urlsplit(proxy_url).scheme or "").lower()
    except Exception:
        scheme = ""
    if scheme == "socks5h":
        return "remote"
    if scheme == "socks5":
        return "local-risk"
    if scheme in {"http", "https"}:
        return "proxy-likely"
    return scheme or "proxy"


def _split_no_proxy_values(no_proxy):
    raw = str(no_proxy or "").strip()
    if not raw:
        return []
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _claude_no_proxy_conflicts(no_proxy):
    values = _split_no_proxy_values(no_proxy)
    conflicts = []
    for item in values:
        normalized = item.lstrip(".")
        if normalized in _CLAUDE_NO_PROXY_TOKENS:
            conflicts.append(item)
            continue
        for token in _CLAUDE_NO_PROXY_TOKENS:
            if token == "*":
                continue
            if normalized == token or normalized.endswith(f".{token}"):
                conflicts.append(item)
                break
    return sorted(set(conflicts))


def _run_proxy_probe(proxy_url, target_url, *, no_proxy="", force_ipv4=True, resolve_ip=False):
    proxy_url = str(proxy_url or "").strip()
    if _fake_upstream_enabled():
        return _fake_proxy_probe(
            target_url,
            proxy_url=proxy_url,
            no_proxy=no_proxy,
            force_ipv4=force_ipv4,
            resolve_ip=resolve_ip,
        )
    curl_bin = shutil.which("curl")
    if not curl_bin:
        return {"ok": False, "detail": "curl missing", "http_code": "", "body": ""}
    cmd = [
        curl_bin,
        *(["-4"] if force_ipv4 else []),
        "--silent",
        "--show-error",
        "--location",
        "--max-time",
        "8",
        "--proxy",
        proxy_url,
        target_url,
    ]
    if resolve_ip:
        cmd.extend(["--output", "-"])
    else:
        cmd.extend(["--head", "--output", "/dev/null", "--write-out", "%{http_code}"])
    if str(no_proxy or "").strip():
        cmd.extend(["--noproxy", str(no_proxy).strip()])
    result = subprocess.run(cmd, capture_output=True, text=True)
    body = str(result.stdout or "").strip()
    http_code = body if not resolve_ip else ""
    detail = str(result.stderr or "").strip()
    ok = result.returncode == 0
    if not resolve_ip:
        ok = ok and bool(http_code) and http_code not in {"000", "407"}
        if http_code and http_code not in {"000"}:
            detail = f"HTTP {http_code}" + (f" · {detail}" if detail else "")
    return {
        "ok": ok,
        "detail": detail[:200] + ("..." if len(detail) > 200 else ""),
        "http_code": http_code,
        "body": body[:200],
    }


def _base_claude_network_guard(runtime, *, require_proxy=False):
    runtime = dict(runtime or {})
    proxy_url = str(runtime.get("proxy") or "").strip()
    no_proxy = str(runtime.get("no_proxy") or "").strip()
    force_ipv4 = bool(_runtime_force_ipv4(runtime))
    dns_mode = _proxy_dns_mode(proxy_url)
    fake_enabled = bool(_fake_upstream_enabled())
    return {
        "proxy_required": bool(require_proxy),
        "proxy_present": bool(proxy_url),
        "proxy_fingerprint": _proxy_fingerprint(proxy_url),
        "dns_mode": "fake-local" if fake_enabled else dns_mode,
        "force_ipv4": force_ipv4,
        "no_proxy": no_proxy,
        "no_proxy_conflicts": _claude_no_proxy_conflicts(no_proxy),
        "targets": [],
        "ipv4_egress": "-",
        "ipv6_egress": "blocked" if force_ipv4 else "unknown",
        "status": "ok",
        "block_reason": "",
        "fake_upstream": fake_enabled,
        "proxy_validation": "skipped_fake" if fake_enabled else "pending",
    }


def _claude_bypass_requires_proxy(runtime):
    runtime = dict(runtime or {})
    auth_mode = str(runtime.get("auth_mode") or "api_key").strip() or "api_key"
    runtime_cli = str(runtime.get("cli") or "").strip()
    if auth_mode == "oauth" and runtime_cli == "claude":
        return True
    if auth_mode == "api_key":
        return _runtime_is_sensitive_claude_provider(runtime)
    return False


def _emit_dns_guard_hint(runtime, *, cli_name, auth_mode):
    if auth_mode != "oauth":
        return
    if cli_name not in {"claude", "codex", "gemini", "agy"}:
        return
    dns_mode = _runtime_dns_mode(runtime)
    if dns_mode == "local-risk":
        console.print(
            "[yellow]DNS 风险: 当前 proxy 为 socks5，hostname 可能仍在本地解析；"
            "更稳的是 socks5h 或由上游 relay 负责 remote DNS[/yellow]"
        )
    elif dns_mode == "direct":
        console.print("[yellow]DNS: 当前为 direct，未经过代理 DNS 路径[/yellow]")


def _claude_network_guard_cache_key(runtime, require_proxy):
    runtime = dict(runtime or {})
    return (
        str(runtime.get("id") or runtime.get("name") or "").strip(),
        str(runtime.get("proxy") or "").strip(),
        str(runtime.get("no_proxy") or "").strip(),
        bool(_runtime_force_ipv4(runtime)),
        bool(require_proxy),
        bool(_fake_upstream_enabled()),
    )


def get_claude_network_guard_preview(runtime, *, require_proxy=False):
    cache_key = _claude_network_guard_cache_key(runtime, require_proxy)
    cached = _CLAUDE_NETWORK_GUARD_CACHE.get(cache_key)
    now = perf_counter()
    if cached and now - float(cached.get("ts", 0.0) or 0.0) < _CLAUDE_NETWORK_GUARD_TTL_SEC:
        return dict(cached.get("guard") or {})
    return _base_claude_network_guard(runtime, require_proxy=require_proxy)


def build_claude_network_guard(runtime, *, require_proxy=False):
    runtime = dict(runtime or {})
    proxy_url = str(runtime.get("proxy") or "").strip()
    no_proxy = str(runtime.get("no_proxy") or "").strip()
    force_ipv4 = bool(_runtime_force_ipv4(runtime))
    auth_mode = str(runtime.get("auth_mode") or "api_key").strip() or "api_key"
    cache_key = _claude_network_guard_cache_key(runtime, require_proxy)
    cached = _CLAUDE_NETWORK_GUARD_CACHE.get(cache_key)
    now = perf_counter()
    if cached and now - float(cached.get("ts", 0.0) or 0.0) < _CLAUDE_NETWORK_GUARD_TTL_SEC:
        return dict(cached.get("guard") or {})
    guard = _base_claude_network_guard(runtime, require_proxy=require_proxy)
    if require_proxy and not proxy_url:
        guard["status"] = "blocked"
        if auth_mode == "oauth":
            guard["block_reason"] = "BYPASS 启动要求当前 Claude 官方账号必须配置 proxy"
        else:
            guard["block_reason"] = "敏感 Claude provider 的 BYPASS 启动要求当前通道配置 proxy"
        _CLAUDE_NETWORK_GUARD_CACHE[cache_key] = {"ts": now, "guard": dict(guard)}
        return guard
    if guard["no_proxy_conflicts"]:
        guard["status"] = "blocked"
        guard["block_reason"] = "NO_PROXY 命中了 Claude 域名，存在直连泄漏风险"
        _CLAUDE_NETWORK_GUARD_CACHE[cache_key] = {"ts": now, "guard": dict(guard)}
        return guard
    if not proxy_url:
        _CLAUDE_NETWORK_GUARD_CACHE[cache_key] = {"ts": now, "guard": dict(guard)}
        return guard
    if _fake_upstream_enabled():
        guard["proxy_validation"] = "skipped_fake"
        guard["block_reason"] = "fake upstream 模式下已跳过真实 proxy / egress 校验"
        _CLAUDE_NETWORK_GUARD_CACHE[cache_key] = {"ts": now, "guard": dict(guard)}
        return guard

    failed_targets = []
    for label, url in _CLAUDE_PROXY_GUARD_TARGETS:
        probe = _run_proxy_probe(
            proxy_url or "http://127.0.0.1:0",
            url,
            no_proxy=no_proxy,
            force_ipv4=force_ipv4,
        )
        guard["targets"].append(
            {
                "label": label,
                "url": url,
                "ok": bool(probe.get("ok")),
                "detail": probe.get("detail", ""),
            }
        )
        if not probe.get("ok"):
            failed_targets.append(label)

    ipv4_probe = _run_proxy_probe(
        proxy_url or "http://127.0.0.1:0",
        "https://api4.ipify.org",
        no_proxy=no_proxy,
        force_ipv4=True,
        resolve_ip=True,
    )
    if ipv4_probe.get("ok") and ipv4_probe.get("body"):
        guard["ipv4_egress"] = ipv4_probe["body"]
    if not force_ipv4:
        ipv6_probe = _run_proxy_probe(
            proxy_url or "http://127.0.0.1:0",
            "https://api6.ipify.org",
            no_proxy=no_proxy,
            force_ipv4=False,
            resolve_ip=True,
        )
        if ipv6_probe.get("ok") and ipv6_probe.get("body"):
            guard["ipv6_egress"] = ipv6_probe["body"]

    if failed_targets:
        guard["status"] = "blocked"
        guard["block_reason"] = f"Claude 关键域名代理检测失败: {', '.join(failed_targets)}"
    elif guard.get("dns_mode") == "local-risk":
        guard["status"] = "watch"
        guard["block_reason"] = "当前 proxy 为 socks5，本地 DNS 解析有风险"
    else:
        guard["proxy_validation"] = "validated"
    _CLAUDE_NETWORK_GUARD_CACHE[cache_key] = {"ts": now, "guard": dict(guard)}
    return guard


def _enforce_claude_network_guard_or_exit(runtime, *, require_proxy=False):
    guard = build_claude_network_guard(runtime, require_proxy=require_proxy)
    runtime["_network_guard"] = guard
    if guard.get("status") != "blocked":
        return guard
    detail_lines = []
    if guard.get("block_reason"):
        detail_lines.append(str(guard["block_reason"]))
    for item in guard.get("targets") or []:
        if item.get("ok"):
            continue
        detail = str(item.get("detail") or "").strip()
        detail_lines.append(
            f"{item.get('label')}: {detail}" if detail else str(item.get("label") or "target")
        )
    console.print(
        f"[red]{runtime.get('id') or runtime.get('name') or 'Claude runtime'} 网络保护阻止启动[/red]"
        + (f"\n[dim]{' | '.join(detail_lines)}[/dim]" if detail_lines else "")
    )
    sys.exit(1)


def _validate_timezone_or_exit(timezone_name, *, label="account"):
    timezone_name = str(timezone_name or "").strip()
    if not timezone_name:
        return ""
    try:
        ZoneInfo(timezone_name)
    except Exception:
        console.print(f"[red]{label} 配置了无效时区: {timezone_name}[/red]")
        sys.exit(1)
    return timezone_name


def _check_proxy_connectivity_or_exit(proxy_url, no_proxy="", *, label="account", force_ipv4=True):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return
    if _fake_upstream_enabled():
        probe = _fake_proxy_probe(
            "https://api.anthropic.com",
            proxy_url=proxy_url,
            no_proxy=no_proxy,
            force_ipv4=force_ipv4,
            resolve_ip=False,
        )
        if probe.get("ok"):
            return
        detail = str(probe.get("detail") or probe.get("http_code") or "fake upstream")
        console.print(
            f"[red]{label} 配置的 proxy 不可用，已阻止启动[/red]"
            + (f"\n[dim]{detail}[/dim]" if detail else "")
        )
        sys.exit(1)
    curl_bin = shutil.which("curl")
    if not curl_bin:
        console.print(f"[red]{label} 要求强制 proxy，但当前系统没有 curl，无法做启动前连通性检查[/red]")
        sys.exit(1)
    cmd = [
        curl_bin,
        *(["-4"] if force_ipv4 else []),
        "--silent",
        "--show-error",
        "--head",
        "--location",
        "--max-time",
        "8",
        "--output",
        "/dev/null",
        "--write-out",
        "%{http_code}",
        "--proxy",
        proxy_url,
        "https://api.anthropic.com",
    ]
    if str(no_proxy or "").strip():
        cmd.extend(["--noproxy", str(no_proxy).strip()])
    result = subprocess.run(cmd, capture_output=True, text=True)
    http_code = str(result.stdout or "").strip()
    if result.returncode != 0 or not http_code or http_code in {"000", "407"}:
        detail = (result.stderr or "").strip()
        if http_code and http_code not in {"000"}:
            detail = f"HTTP {http_code}" + (f" · {detail}" if detail else "")
        if len(detail) > 200:
            detail = detail[:200] + "..."
        console.print(
            f"[red]{label} 配置的 proxy 不可用，已阻止启动[/red]"
            + (f"\n[dim]{detail}[/dim]" if detail else "")
        )
        sys.exit(1)


def _apply_runtime_network_profile(env, runtime, *, validate_proxy=True):
    env = env if isinstance(env, dict) else {}
    runtime = runtime if isinstance(runtime, dict) else {}

    timezone_name = _validate_timezone_or_exit(
        runtime.get("timezone") or DEFAULT_ACCOUNT_TIMEZONE,
        label=str(runtime.get("id") or runtime.get("name") or runtime.get("cli") or "runtime"),
    )
    if timezone_name:
        env["TZ"] = timezone_name
    else:
        env.pop("TZ", None)

    _apply_runtime_locale_profile(env, runtime)
    _apply_runtime_ip_stack_profile(env, runtime)

    proxy_url = str(runtime.get("proxy") or "").strip()
    no_proxy = str(runtime.get("no_proxy") or "").strip()
    runtime_label = str(runtime.get("id") or runtime.get("name") or runtime.get("cli") or "runtime")
    proxy_keys = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
    no_proxy_keys = ("NO_PROXY", "no_proxy")
    fake_state_keys = (
        "MMS_FAKE_UPSTREAM_MODE",
        "MMS_FAKE_UPSTREAM_PROXY",
        "MMS_FAKE_UPSTREAM_ORIGINAL_PROXY",
        "MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY",
    )
    ca_keys = ("NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")

    if proxy_url and validate_proxy:
        _check_proxy_connectivity_or_exit(
            proxy_url,
            no_proxy,
            label=runtime_label,
            force_ipv4=bool(_runtime_force_ipv4(runtime)),
        )

    if _fake_upstream_enabled():
        fake_payload = _fake_upstream_status_payload()
        fake_proxy_url = str(fake_payload.get("proxy_url") or "").strip()
        if fake_proxy_url:
            for key in proxy_keys:
                env[key] = fake_proxy_url
            env["MMS_FAKE_UPSTREAM_PROXY"] = fake_proxy_url
        else:
            for key in proxy_keys:
                env.pop(key, None)
            env.pop("MMS_FAKE_UPSTREAM_PROXY", None)
        env["MMS_FAKE_UPSTREAM_MODE"] = "upstream-proxy"
        for key in no_proxy_keys:
            env[key] = "127.0.0.1,localhost,::1"
        if proxy_url:
            env["MMS_FAKE_UPSTREAM_ORIGINAL_PROXY"] = _proxy_fingerprint(proxy_url)
        else:
            env.pop("MMS_FAKE_UPSTREAM_ORIGINAL_PROXY", None)
        if no_proxy:
            env["MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY"] = no_proxy
        else:
            env.pop("MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY", None)
        ca_cert_path = str(fake_payload.get("ca_cert_path") or "").strip()
        for key in ca_keys:
            if ca_cert_path:
                env[key] = ca_cert_path
            else:
                env.pop(key, None)
        return env

    for key in fake_state_keys:
        env.pop(key, None)
    for key in ca_keys:
        env.pop(key, None)

    if proxy_url:
        for key in proxy_keys:
            env[key] = proxy_url
    else:
        for key in proxy_keys:
            env.pop(key, None)

    if no_proxy:
        for key in no_proxy_keys:
            env[key] = no_proxy
    else:
        for key in no_proxy_keys:
            env.pop(key, None)

    return env


def _apply_runtime_ip_stack_profile(env, runtime):
    if not _runtime_force_ipv4(runtime):
        return env
    env["MMS_FORCE_IPV4"] = "1"
    existing = str(env.get("NODE_OPTIONS") or "").strip()
    token = "--dns-result-order=ipv4first"
    if token not in existing.split():
        env["NODE_OPTIONS"] = f"{existing} {token}".strip()
    return env


RUNTIME_DIR = _real_user_path(".config", "mms", "runtime")
HEALTH_CHECK_PATH = _real_user_path(".config", "mms", "health_check.json")
ANTHROPIC_URL_CACHE_PATH = _real_user_path(".config", "mms", "cache", "anthropic_base_urls.json")

# Anthropic URL 探测结果缓存（内存，TTL 1h）
# key: provider_id → {"url": str, "ts": datetime}
_ANTHROPIC_URL_CACHE: dict = {}
CLI_PROTOCOL_REQUIREMENTS = {
    "claude": "anthropic_messages",
    "codex": "openai_chat_completions",
    "opencode": "openai_chat_completions",
}
OAUTH_CAPABLE_CLIS = {"claude", "codex", "gemini", "agy"}
# OpenCode constants and pure config helpers live in mms_opencode_config.
# agent-im daemon 路径（仅在显式配置时启用，避免公开仓库绑定个人目录）
_AGENT_IM_DIR = os.path.realpath(str(os.environ.get("MMS_AGENT_IM_DIR") or "").strip()) if str(os.environ.get("MMS_AGENT_IM_DIR") or "").strip() else ""
_AGENT_IM_SOCK = _real_user_path(".agent-im", "agent-im.sock")
_LOCAL_STATUSLINE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "statusline-command.sh")
def _resolve_local_hooks_dir(module_file=None):
    module_dir = os.path.dirname(os.path.abspath(module_file or __file__))
    parts = module_dir.split(os.sep)
    if ".worktrees" in parts:
        idx = parts.index(".worktrees")
        canonical_root = os.sep.join(parts[:idx]) or os.sep
        canonical_hooks = os.path.join(canonical_root, "hooks")
        required_hooks = (
            "nsr-codex-hook.sh",
            "xmem-session-start-hook.sh",
            "xmem-session-end-hook.sh",
            "xmem-gateway-hook.sh",
        )
        if all(os.path.isfile(os.path.join(canonical_hooks, name)) for name in required_hooks):
            return canonical_hooks
    return os.path.join(module_dir, "hooks")


_LOCAL_HOOKS_DIR = _resolve_local_hooks_dir()
_CLAUDE_FEISHU_WEBFETCH_GUARD_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "claude-feishu-webfetch-guard.sh")
_CLAUDE_HIVE_COMPACT_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "hive-compact-hook.sh")
_CLAUDE_BRAINKEEPER_SESSION_START_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "brainkeeper-session-start-hook.sh")
_CLAUDE_BRAINKEEPER_SESSION_END_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "brainkeeper-session-end-hook.sh")
_CLAUDE_BRAINKEEPER_TOKEN_MONITOR_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "brainkeeper-token-monitor-hook.sh")
_CLAUDE_MINDKEEPER_SESSION_START_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "mindkeeper-session-start-hook.sh")
_CLAUDE_MINDKEEPER_SESSION_END_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "mindkeeper-session-end-hook.sh")
_CLAUDE_MINDKEEPER_TOKEN_MONITOR_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "mindkeeper-token-monitor-hook.sh")
_CLAUDE_CODEGRAPH_AUTO_INDEX_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "claude-codegraph-auto-index.sh")
_CLAUDE_MMS_RESUME_HINT_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "mms-resume-hint.sh")
_XMEM_SESSION_START_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "xmem-session-start-hook.sh")
_XMEM_SESSION_END_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "xmem-session-end-hook.sh")
_XMEM_GATEWAY_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "xmem-gateway-hook.sh")
_NSR_CLAUDE_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "nsr-claude-hook.sh")
_NSR_CODEX_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "nsr-codex-hook.sh")
_NSR_BUILTIN_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "nsr-builtin-hook.py")

_CLAUDE_STATUSLINE_CONFIG = {
    "command": f"/bin/bash {_LOCAL_STATUSLINE_SCRIPT}",
    "type": "command",
}

_CLAUDE_SESSION_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "TZ",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LC_MESSAGES",
    "SSL_CERT_FILE",
    "NODE_EXTRA_CA_CERTS",
    "REQUESTS_CA_BUNDLE",
    "MMS_FORCE_IPV4",
    "MMS_FAKE_UPSTREAM_MODE",
    "MMS_FAKE_UPSTREAM_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY",
)

_CLAUDE_SETTINGS_INHERIT_KEYS = (
    "hooks",
    "statusLine",
    "permissions",
)
_CLAUDE_SESSION_MCP_SERVER_ALLOWLIST = (
    "brainkeeper",
    "codegraph",
)
_CLAUDE_SETTINGS_INHERIT_SCALAR_KEYS = ("theme",)
_CLAUDE_SESSION_SOURCE_ENTRY_ALLOWLIST = (
    ".mcp.json",
    "CLAUDE.md",
    "RTK.md",
    "commands",
    "hooks",
    "skills",
)
_CLAUDE_FAIL_CLOSED_SOURCE_ENTRY_ALLOWLIST = (
    "CLAUDE.md",
    "RTK.md",
)
_CLAUDE_OAUTH_SESSION_SOURCE_ENTRY_ALLOWLIST = _CLAUDE_FAIL_CLOSED_SOURCE_ENTRY_ALLOWLIST
_CLAUDE_SESSION_LIBRARY_ENTRY_ALLOWLIST = ("Keychains",)
_CLAUDE_OAUTH_MANUAL_ONLY_EXIT_CODE = 86
_SESSION_REAL_HOME_WRAPPER_COMMANDS = (
    "open",
    "osascript",
    "security",
    "git",
    "ssh",
    "ssh-add",
    "scp",
    "sftp",
    "brew",
    "gh",
    "lark-cli",
    "rh",
    "hive",
    "pm2",
    "npm",
    "pnpm",
    "npx",
    "yarn",
    "corepack",
    "node",
    "uv",
    "docker",
    "docker-compose",
)
_CLAUDE_OAUTH_STATE_TOP_LEVEL_ALLOWLIST = (
    "userID",
    "firstStartTime",
    "numStartups",
    "bypassPermissionsModeAccepted",
    "alwaysThinkingEnabled",
    "hasCompletedOnboarding",
    "lastOnboardingVersion",
    "lastReleaseNotesSeen",
    "installMethod",
    "deepLinkTerminal",
    "effortCalloutDismissed",
    "effortCalloutV2Dismissed",
    "migrationVersion",
    "officialMarketplaceAutoInstallAttempted",
    "officialMarketplaceAutoInstalled",
    "opus1mMergeNoticeSeenCount",
    "opusProMigrationComplete",
    "sonnet1m45MigrationComplete",
    "voiceNoticeSeenCount",
)
_CLAUDE_OAUTH_UI_STATE_SEED_KEYS = (
    "firstStartTime",
    "numStartups",
    "hasCompletedOnboarding",
    "lastOnboardingVersion",
    "lastReleaseNotesSeen",
    "installMethod",
    "deepLinkTerminal",
    "effortCalloutDismissed",
    "effortCalloutV2Dismissed",
    "migrationVersion",
    "officialMarketplaceAutoInstallAttempted",
    "officialMarketplaceAutoInstalled",
    "opus1mMergeNoticeSeenCount",
    "opusProMigrationComplete",
    "sonnet1m45MigrationComplete",
    "voiceNoticeSeenCount",
)
_CLAUDE_OAUTH_STATE_SCALAR_DICT_ALLOWLIST = ("tipsHistory",)
_CLAUDE_OAUTH_ACCOUNT_ALLOWLIST = (
    "accountCreatedAt",
    "accountUuid",
    "billingType",
    "displayName",
    "emailAddress",
    "hasExtraUsageEnabled",
    "organizationName",
    "organizationRole",
    "organizationUuid",
    "subscriptionCreatedAt",
    "workspaceRole",
)
_CLAUDE_AI_OAUTH_ALLOWLIST = (
    "accessToken",
    "refreshToken",
    "expiresAt",
    "expiresIn",
    "tokenType",
    "token_type",
    "emailAddress",
    "accountUuid",
    "organizationUuid",
)
_CLAUDE_CODEX_STATE_TOP_LEVEL_ALLOWLIST = (
    "firstStartTime",
    "numStartups",
    "bypassPermissionsModeAccepted",
    "alwaysThinkingEnabled",
    "hasCompletedOnboarding",
    "lastOnboardingVersion",
    "installMethod",
)
_CLAUDE_OAUTH_ENV_PREFIX_BLOCKLIST = (
    "ANTHROPIC_",
    "CLAUDE_CODE_",
)
_OPENAI_ENV_PREFIX_BLOCKLIST = (
    "OPENAI_",
)
_RUNTIME_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)
_RUNTIME_FAKE_ENV_KEYS = (
    "MMS_FAKE_UPSTREAM_MODE",
    "MMS_FAKE_UPSTREAM_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY",
)
_RUNTIME_CA_ENV_KEYS = (
    "NODE_EXTRA_CA_CERTS",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
)

_CLAUDE_MAILBOX_PREFIX = os.path.join(_real_user_path(".claude"), "mailbox")

_CLAUDE_DEFAULT_PERMISSION_ALLOW = [
    "Read",
    "Edit",
    "Write",
    "Bash(yarn *)",
    "Bash(npm *)",
    "Bash(node *)",
    "Bash(git *)",
    "Bash(ls *)",
    "Bash(cat *)",
    "Bash(head *)",
    "Bash(tail *)",
    "Bash(find *)",
    "Bash(grep *)",
    "Bash(which *)",
    "Bash(chmod *)",
    "Bash(cd *)",
    "Bash(python3 *)",
    "Bash(rsync *)",
    "Bash(coscli *)",
    f"Bash(mkdir -p {_CLAUDE_MAILBOX_PREFIX}*)",
    f"Bash(rm -rf {_CLAUDE_MAILBOX_PREFIX}/*)",
    f"Bash(ls {_CLAUDE_MAILBOX_PREFIX}*)",
    "Skill(*)",
    "Agent(*)",
]

_CLAUDE_DEFAULT_PERMISSION_DENY = [
    "Bash(rm -rf /)*",
    "Bash(git push --force *)",
]


def _claude_gateway_home():
    gateway_base = _real_user_path(".config", "mms", "claude-gateway")
    sessions_dir = os.path.join(gateway_base, "s")
    return os.path.join(sessions_dir, str(os.getpid()))


def _claude_route_status_paths():
    gateway_home = _claude_gateway_home()
    return [os.path.join(gateway_home, ".config", "mms", "route_status.json")]


def _anthropic_cache_key(provider_id, configured_url):
    return f"{provider_id}::{configured_url.rstrip('/')}"


def _load_anthropic_url_file_cache():
    try:
        with open(ANTHROPIC_URL_CACHE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_anthropic_url_file_cache(cache_data):
    try:
        os.makedirs(os.path.dirname(ANTHROPIC_URL_CACHE_PATH), exist_ok=True)
        tmp_path = ANTHROPIC_URL_CACHE_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(cache_data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_path, ANTHROPIC_URL_CACHE_PATH)
    except Exception:
        pass


def _remember_anthropic_url(provider_id, configured_url, resolved_url):
    now_iso = datetime.now().isoformat()
    cache_key = _anthropic_cache_key(provider_id, configured_url)
    _ANTHROPIC_URL_CACHE[cache_key] = {"url": resolved_url, "ts": datetime.now()}
    cache_data = _load_anthropic_url_file_cache()
    cache_data[cache_key] = {"url": resolved_url, "ts": now_iso}
    _save_anthropic_url_file_cache(cache_data)


def _ensure_agent_im():
    """如果 agent-im daemon 未运行，自动后台拉起。"""
    if os.path.exists(_AGENT_IM_SOCK):
        return
    main_js = os.path.join(_AGENT_IM_DIR, "dist", "main.js")
    if not os.path.isfile(main_js):
        return
    log_dir = os.path.expanduser("~/.agent-im/logs")
    os.makedirs(log_dir, exist_ok=True)
    try:
        subprocess.Popen(
            ["node", main_js],
            stdout=open(os.path.join(log_dir, "daemon.log"), "a"),
            stderr=open(os.path.join(log_dir, "daemon.err.log"), "a"),
            start_new_session=True,
        )
        # 等 socket 就绪（最多 2 秒）
        import time
        for _ in range(20):
            if os.path.exists(_AGENT_IM_SOCK):
                console.print("[dim]✓ agent-im daemon 已自动启动[/dim]")
                return
            time.sleep(0.1)
        console.print("[dim]agent-im daemon 启动中（socket 未就绪，不影响启动）[/dim]")
    except Exception:
        pass  # daemon 启动失败不阻塞 CLI


def _load_real_claude_settings():
    """Compatibility wrapper for reading real Claude settings."""
    from mms_claude_settings import load_real_claude_settings

    return load_real_claude_settings()


def _load_claude_settings_from_dir(claude_dir):
    """Compatibility wrapper for reading Claude settings from a directory."""
    from mms_claude_settings import load_claude_settings_from_dir

    return load_claude_settings_from_dir(claude_dir)


def _load_claude_settings_template(filename):
    """Compatibility wrapper for Claude settings template loading."""
    from mms_claude_settings import load_claude_settings_template

    return load_claude_settings_template(filename)


def _load_mms_claude_settings_template():
    """Compatibility wrapper for the MMS Claude session settings template."""
    from mms_claude_settings import load_mms_claude_settings_template

    return load_mms_claude_settings_template()


def _load_global_claude_settings_template():
    """Compatibility wrapper for the global Claude managed settings template."""
    from mms_claude_settings import load_global_claude_settings_template

    return load_global_claude_settings_template()


def _global_claude_snapshot_path():
    """Compatibility wrapper for global Claude managed snapshot path."""
    from mms_claude_settings import global_claude_snapshot_path

    return global_claude_snapshot_path()


def _normalize_hook_command(command):
    """Compatibility wrapper for hook command normalization."""
    from mms_claude_settings import normalize_hook_command

    return normalize_hook_command(command)


def _extract_managed_claude_snapshot(settings_data, template_settings):
    """Compatibility wrapper for Claude managed settings snapshot extraction."""
    from mms_claude_settings import extract_managed_claude_snapshot

    return extract_managed_claude_snapshot(settings_data, template_settings)


def _snapshot_to_template(snapshot_data, seed_template):
    """Compatibility wrapper for snapshot-to-template conversion."""
    from mms_claude_settings import snapshot_to_template

    return snapshot_to_template(snapshot_data, seed_template)


def _merge_snapshot_with_current(snapshot_data, current_settings):
    """Compatibility wrapper for managed snapshot/current merge."""
    from mms_claude_settings import merge_snapshot_with_current

    return merge_snapshot_with_current(snapshot_data, current_settings)


def _prune_session_only_snapshot_entries(snapshot_data):
    """Compatibility wrapper for pruning session-only snapshot entries."""
    from mms_claude_settings import prune_session_only_snapshot_entries

    return prune_session_only_snapshot_entries(snapshot_data)


def _sanitize_global_snapshot(snapshot_data):
    """Compatibility wrapper for global Claude snapshot sanitization."""
    from mms_claude_settings import sanitize_global_snapshot

    return sanitize_global_snapshot(snapshot_data)


def _managed_snapshot_differs(previous_snapshot, current_settings, seed_template):
    """Compatibility wrapper for managed Claude snapshot diffing."""
    from mms_claude_settings import managed_snapshot_differs

    return managed_snapshot_differs(previous_snapshot, current_settings, seed_template)


def _managed_snapshot_template(previous_snapshot, seed_template, current_settings):
    """Compatibility wrapper for managed Claude snapshot template building."""
    from mms_claude_settings import managed_snapshot_template

    return managed_snapshot_template(previous_snapshot, seed_template, current_settings)


def _load_global_claude_snapshot():
    """Compatibility wrapper for reading the global Claude managed snapshot."""
    from mms_claude_settings import load_global_claude_snapshot

    return load_global_claude_snapshot()


def _write_global_claude_snapshot(snapshot_data):
    """Compatibility wrapper for writing the global Claude managed snapshot."""
    from mms_claude_settings import write_global_claude_snapshot

    return write_global_claude_snapshot(snapshot_data)


def _merge_claude_settings(base_settings, template_settings):
    """Compatibility wrapper for Claude settings template merging."""
    from mms_claude_settings import merge_claude_settings

    return merge_claude_settings(base_settings, template_settings)


def _repair_real_claude_settings():
    import json as _json

    real_claude_dir = _real_user_path(".claude")
    os.makedirs(real_claude_dir, exist_ok=True)
    settings_path = os.path.join(real_claude_dir, "settings.json")
    current_settings = _load_real_claude_settings()
    seed_template = _load_global_claude_settings_template()
    previous_snapshot = _load_global_claude_snapshot()
    snapshot_data, managed_template = _managed_snapshot_template(
        previous_snapshot,
        seed_template,
        current_settings,
    )

    repaired = _merge_claude_settings(current_settings, managed_template)
    repaired = _sanitize_global_snapshot(repaired)
    repaired_snapshot = _sanitize_global_snapshot(
        _extract_managed_claude_snapshot(repaired, managed_template)
    )
    should_write = (
        _managed_snapshot_differs(previous_snapshot, current_settings, managed_template)
        or repaired_snapshot != snapshot_data
        or not os.path.exists(settings_path)
    )
    if should_write:
        with locked_state_file(settings_path):
            atomic_write_json(settings_path, repaired, mode=0o600)
    _write_global_claude_snapshot(repaired_snapshot)
    return repaired


def _refresh_global_claude_snapshot_from_current_settings():
    current_settings = _load_real_claude_settings()
    seed_template = _load_global_claude_settings_template()
    snapshot_data, _ = _managed_snapshot_template({}, seed_template, current_settings)
    _write_global_claude_snapshot(snapshot_data)
    return snapshot_data


def repair_real_claude_settings_for_startup():
    return _repair_real_claude_settings()


def repair_current_session_claude_settings(session_claude_dir):
    """Compatibility wrapper for session-local Claude settings repair."""
    from mms_claude_settings import repair_current_session_claude_settings as _repair_current

    return _repair_current(session_claude_dir)


def _strip_agent_im_hooks(hooks_data):
    """Compatibility wrapper for inherited Claude hook filtering."""
    from mms_claude_settings import strip_agent_im_hooks

    return strip_agent_im_hooks(hooks_data)


def _merge_claude_hook_groups(existing_groups, template_groups):
    """Compatibility wrapper for Claude hook-group merging."""
    from mms_claude_settings import merge_claude_hook_groups

    return merge_claude_hook_groups(existing_groups, template_groups)


def _merge_claude_hooks(existing_hooks, template_hooks):
    """Compatibility wrapper for Claude hook merging."""
    from mms_claude_settings import merge_claude_hooks

    return merge_claude_hooks(existing_hooks, template_hooks)


def _merge_claude_statusline(existing):
    """Compatibility wrapper for Claude statusline defaults."""
    from mms_claude_settings import merge_claude_statusline

    return merge_claude_statusline(existing)


def _merge_claude_permissions(existing):
    """Compatibility wrapper for Claude permissions defaults."""
    from mms_claude_settings import merge_claude_permissions

    return merge_claude_permissions(existing)


def _hook_command_exists(hook_items, command_path):
    """Compatibility wrapper for hook command lookup."""
    from mms_claude_settings import hook_command_exists

    return hook_command_exists(hook_items, command_path)


def _append_command_hook(hooks_data, event_name, command_path, matcher=None, timeout=None, status_message=None):
    """Compatibility wrapper for appending file-backed command hooks."""
    from mms_claude_settings import append_command_hook

    return append_command_hook(
        hooks_data,
        event_name,
        command_path,
        matcher=matcher,
        timeout=timeout,
        status_message=status_message,
    )


def _append_shell_command_hook(
    hooks_data,
    event_name,
    command_text,
    *,
    matcher=None,
    timeout=None,
    status_message=None,
):
    """Compatibility wrapper for appending shell command hooks."""
    from mms_claude_settings import append_shell_command_hook

    return append_shell_command_hook(
        hooks_data,
        event_name,
        command_text,
        matcher=matcher,
        timeout=timeout,
        status_message=status_message,
    )


def _merge_mms_session_hooks(existing_hooks, template_hooks=None):
    """Compatibility wrapper for MMS-managed Claude session hooks."""
    from mms_claude_settings import merge_mms_session_hooks

    return merge_mms_session_hooks(existing_hooks, template_hooks=template_hooks)


def _filter_claude_session_hooks(hooks_data, *, allow_execution_surfaces=True):
    """Compatibility wrapper for Claude session hook filtering."""
    from mms_claude_settings import filter_claude_session_hooks

    return filter_claude_session_hooks(
        hooks_data,
        allow_execution_surfaces=allow_execution_surfaces,
    )


def _caveman_available_for_cli(cli_name):
    return str(cli_name or "").strip() in {"claude", "codex", "opencode", "agy"} and bool(_resolve_caveman_root())


def _resolve_nsr_root():
    candidates = []
    for key in ("MMS_NSR_ROOT", "NSR_ROOT"):
        explicit = str(os.environ.get(key) or "").strip()
        if explicit:
            candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    pref = _asset_root_preference("nsr")
    if pref:
        candidates.append(os.path.abspath(os.path.expanduser(pref)))
    nsr_home = str(os.environ.get("NSR_HOME") or "").strip()
    if nsr_home:
        candidates.append(os.path.abspath(os.path.expanduser(nsr_home)))
    candidates.extend([
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "non-stop-run"),
        _real_user_path("auto-skills", "Non-Stop-Run"),
        _real_user_path("auto-skills", "shared-skills", "looop.deprecated"),
    ])

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if (
            os.path.isfile(os.path.join(candidate, "scripts", "codex_hook.py"))
            and os.path.isfile(os.path.join(candidate, "scripts", "claude_hook.py"))
        ):
            return candidate
    return ""


def _nsr_available_for_cli(cli_name):
    cli_name = str(cli_name or "").strip()
    if cli_name not in {"claude", "codex"}:
        return False
    wrapper = _NSR_CLAUDE_HOOK if cli_name == "claude" else _NSR_CODEX_HOOK
    return os.path.isfile(wrapper) and bool(_resolve_nsr_root() or os.path.isfile(_NSR_BUILTIN_HOOK))


def _normalize_nsr_mode(value, default="enable"):
    raw = str(value or "").strip().lower()
    if raw in {"", "inherit", "default", "auto"}:
        return default if default in {"enable", "disable"} else "enable"
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return "enable"
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return "disable"
    return default if default in {"enable", "disable"} else "enable"


def _runtime_nsr_enabled(runtime):
    return _normalize_nsr_mode((runtime or {}).get("nsr_mode", "enable")) == "enable"


def _normalize_caveman_mode(value, default="disable"):
    raw = str(value or "").strip().lower()
    if raw in {"", "inherit", "default", "auto"}:
        return default if default in {"auto", "enable", "disable"} else "disable"
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return "enable"
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return "disable"
    return default if default in {"auto", "enable", "disable"} else "disable"


def _runtime_caveman_enabled(runtime):
    return _normalize_caveman_mode((runtime or {}).get("caveman_mode", "disable")) == "enable"


def _normalize_thinking_mode(value, default="enable"):
    raw = str(value or "").strip().lower()
    if raw in {"", "inherit", "default", "auto"}:
        return default if default in {"auto", "enable", "disable"} else "enable"
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return "enable"
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return "disable"
    return default if default in {"auto", "enable", "disable"} else "enable"


def _runtime_thinking_enabled(runtime):
    return _normalize_thinking_mode((runtime or {}).get("thinking_mode", "enable")) == "enable"


def _normalize_reasoning_effort(value, default="high"):
    raw = str(value or "").strip().lower()
    if raw in {"low", "medium", "high", "xhigh"}:
        return raw
    return default if default in {"low", "medium", "high", "xhigh"} else "high"


def _runtime_reasoning_effort(runtime, default="high"):
    return _normalize_reasoning_effort((runtime or {}).get("reasoning_effort", default), default=default)


def _runtime_vision_sidecar(runtime):
    sidecar = (runtime or {}).get("vision_sidecar")
    if not isinstance(sidecar, dict):
        return {}
    if not sidecar.get("enabled", True):
        return {}
    return dict(sidecar)


def _resolve_native_fallback_routes(runtime, model_name):
    try:
        from mms_native_fallback import resolve_native_fallback_routes

        return resolve_native_fallback_routes(runtime, model_name)
    except Exception:
        return []


def _resolve_codex_responses_fallback_routes(runtime, model_name):
    try:
        from mms_native_fallback import resolve_codex_responses_fallback_routes

        return resolve_codex_responses_fallback_routes(runtime, model_name)
    except Exception:
        return []


def _is_installed_mms_layout(module_path=None):
    current_path = os.path.abspath(module_path or __file__)
    installed_root = os.path.abspath(_real_user_path(".mms"))
    try:
        return os.path.commonpath([current_path, installed_root]) == installed_root
    except ValueError:
        return False


def _default_gpt_reasoning_effort(module_path=None):
    return "high" if _is_installed_mms_layout(module_path=module_path) else "xhigh"


def _asset_root_preference(asset_name):
    try:
        return str(preference_asset_root(asset_name) or "").strip()
    except Exception:
        return ""


def _resolve_caveman_root():
    candidates = []
    explicit = str(os.environ.get("MMS_CAVEMAN_ROOT") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    pref = _asset_root_preference("caveman")
    if pref:
        candidates.append(os.path.abspath(os.path.expanduser(pref)))
    candidates.extend([
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "caveman"),
        _real_user_path("auto-skills", "vendor", "caveman"),
        _real_user_path("vendor", "caveman"),
        _real_user_path("caveman"),
    ])

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        activate = os.path.join(candidate, "hooks", "caveman-activate.js")
        tracker = os.path.join(candidate, "hooks", "caveman-mode-tracker.js")
        if os.path.isfile(activate) and os.path.isfile(tracker):
            return candidate
    return ""


def _ecc_available_for_claude():
    return bool(_resolve_ecc_root())


def _omc_available_for_claude():
    return bool(_resolve_omc_root())


def _normalize_ecc_mode(value, default="disable"):
    raw = str(value or "").strip().lower()
    if raw in {"", "inherit", "default", "auto"}:
        return default if default in {"auto", "enable", "disable"} else "disable"
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return "enable"
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return "disable"
    return default if default in {"auto", "enable", "disable"} else "disable"


def _normalize_agent_pack(value, default="none"):
    raw = str(value or "").strip().lower()
    fallback = default if default in {"none", "ecc", "omc"} else "none"
    if raw in {"", "inherit", "default", "auto"}:
        return fallback
    if raw in {"0", "false", "no", "off", "disable", "disabled", "none", "null"}:
        return "none"
    if raw in {"ecc", "everything-claude-code", "everything_claude_code"}:
        return "ecc"
    if raw in {"omc", "oh-my-claudecode", "oh_my_claudecode", "oh-my-claude-code"}:
        return "omc"
    return fallback


def _runtime_agent_pack(runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    if "agent_pack" in runtime and str(runtime.get("agent_pack") or "").strip():
        return _normalize_agent_pack(runtime.get("agent_pack"), default="none")
    if _normalize_ecc_mode(runtime.get("ecc_mode", "disable")) == "enable":
        return "ecc"
    if _normalize_ecc_mode(runtime.get("omc_mode", "disable")) == "enable":
        return "omc"
    return "none"


def _runtime_ecc_enabled(runtime):
    return _runtime_agent_pack(runtime) == "ecc"


def _runtime_omc_enabled(runtime):
    return _runtime_agent_pack(runtime) == "omc"


def _resolve_ecc_root():
    candidates = []
    explicit = str(os.environ.get("MMS_ECC_ROOT") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    pref = _asset_root_preference("ecc")
    if pref:
        candidates.append(os.path.abspath(os.path.expanduser(pref)))
    candidates.extend([
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent-packs", "everything-claude-code"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "everything-claude-code"),
        _real_user_path("auto-skills", "vendor", "everything-claude-code"),
        _real_user_path("vendor", "everything-claude-code"),
        _real_user_path("everything-claude-code"),
    ])

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        hooks_path = os.path.join(candidate, "hooks", "hooks.json")
        commands_dir = os.path.join(candidate, "commands")
        skills_dir = os.path.join(candidate, "skills")
        if os.path.isfile(hooks_path) and os.path.isdir(commands_dir) and os.path.isdir(skills_dir):
            return candidate
    return ""


def _resolve_omc_root():
    candidates = []
    explicit = str(os.environ.get("MMS_OMC_ROOT") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    pref = _asset_root_preference("omc")
    if pref:
        candidates.append(os.path.abspath(os.path.expanduser(pref)))
    candidates.extend([
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent-packs", "oh-my-claudecode"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "oh-my-claudecode"),
        _real_user_path("auto-skills", "installed-skills", "oh-my-claudecode"),
        _real_user_path("auto-skills", "vendor", "oh-my-claudecode"),
        _real_user_path("vendor", "oh-my-claudecode"),
        _real_user_path("oh-my-claudecode"),
    ])

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        hooks_path = os.path.join(candidate, "hooks", "hooks.json")
        skills_dir = os.path.join(candidate, "skills")
        plugin_json = os.path.join(candidate, ".claude-plugin", "plugin.json")
        if os.path.isfile(hooks_path) and os.path.isdir(skills_dir) and os.path.isfile(plugin_json):
            return candidate
    return ""


def _resolve_web_access_root():
    candidates = []
    explicit = str(os.environ.get("MMS_WEB_ACCESS_ROOT") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    pref = _asset_root_preference("web_access")
    if pref:
        candidates.append(os.path.abspath(os.path.expanduser(pref)))
    candidates.extend([
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "web-access"),
        _real_user_path("auto-skills", "vendor", "web-access"),
        _real_user_path("vendor", "web-access"),
    ])

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(os.path.join(candidate, "SKILL.md")):
            return candidate
    return ""


def _resolve_weber_root():
    candidates = []
    explicit = str(os.environ.get("MMS_WEBER_ROOT") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    pref = _asset_root_preference("weber")
    if pref:
        candidates.append(os.path.abspath(os.path.expanduser(pref)))
    candidates.extend([
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "weber"),
        _real_user_path("auto-skills", "shared-skills", "weber"),
        _real_user_path("auto-skills", "vendor", "weber"),
        _real_user_path("vendor", "weber"),
    ])

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(os.path.join(candidate, "SKILL.md")):
            return candidate
    return ""


def _resolve_agent_browser_root():
    candidates = []
    explicit = str(os.environ.get("MMS_AGENT_BROWSER_ROOT") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    pref = _asset_root_preference("agent_browser")
    if pref:
        candidates.append(os.path.abspath(os.path.expanduser(pref)))
    candidates.extend([
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "agent-browser"),
        _real_user_path("auto-skills", "installed-skills", "agent-browser"),
        _real_user_path("auto-skills", "vendor", "agent-browser"),
        _real_user_path("vendor", "agent-browser"),
    ])

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(os.path.join(candidate, "SKILL.md")):
            return candidate
    return ""


def _resolve_toon_root():
    candidates = []
    explicit = str(os.environ.get("MMS_TOON_ROOT") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    pref = _asset_root_preference("toon")
    if pref:
        candidates.append(os.path.abspath(os.path.expanduser(pref)))
    candidates.extend([
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "toon"),
        _real_user_path("auto-skills", "vendor", "toon"),
        _real_user_path("vendor", "toon"),
    ])

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(os.path.join(candidate, "SKILL.md")):
            return candidate
    return ""


def _resolve_token_saver_root():
    candidates = []
    explicit = str(os.environ.get("MMS_TOKEN_SAVER_ROOT") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    pref = _asset_root_preference("token_saver")
    if pref:
        candidates.append(os.path.abspath(os.path.expanduser(pref)))
    candidates.extend([
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "token-saver"),
        _real_user_path("auto-skills", "shared-skills", "token-saver"),
        _real_user_path("auto-skills", "vendor", "token-saver"),
        _real_user_path("vendor", "token-saver"),
    ])

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(os.path.join(candidate, "SKILL.md")):
            return candidate
    return ""


def _resolve_xmem_root():
    candidates = []
    explicit = str(os.environ.get("MMS_XMEM_ROOT") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    pref = _asset_root_preference("xmem")
    if pref:
        candidates.append(os.path.abspath(os.path.expanduser(pref)))
    candidates.extend([
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "xmem"),
        _real_user_path("auto-skills", "shared-skills", "xmem"),
        _real_user_path("auto-skills", "CtriXin-repo", "xmem", "skills", "xmem"),
        _real_user_path(".codex", "skills", "xmem"),
        _real_user_path(".agents", "skills", "xmem"),
    ])

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(os.path.join(candidate, "SKILL.md")):
            return candidate
    return ""


def _xmem_cli_path():
    from mms_launcher_export import xmem_cli_path

    return xmem_cli_path(
        environ=os.environ,
        real_user_path=_real_user_path,
        which=shutil.which,
    )


def _resolve_auto_github_contributor_root():
    candidates = []
    explicit = str(os.environ.get("MMS_AUTO_GITHUB_CONTRIBUTOR_ROOT") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    pref = _asset_root_preference("auto_github_contributor")
    if pref:
        candidates.append(os.path.abspath(os.path.expanduser(pref)))
    candidates.extend([
        _real_user_path("auto-skills", "installed-skills", "auto-github-contributor"),
        _real_user_path("auto-skills", "vendor", "auto-github-contributor", "skills", "auto-github-contributor"),
        _real_user_path("vendor", "auto-github-contributor", "skills", "auto-github-contributor"),
    ])

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(os.path.join(candidate, "SKILL.md")):
            return candidate
    return ""


def _mms_toon_script_path():
    from mms_launcher_export import launcher_script_path

    return launcher_script_path(__file__, "mms-toon")


def _mms_context_script_path():
    from mms_launcher_export import launcher_script_path

    return launcher_script_path(__file__, "mms-context")


def _token_saver_script_path():
    from mms_launcher_export import launcher_script_path

    return launcher_script_path(__file__, "token-saver")


def _is_caveman_hook_command(command_text):
    """Compatibility wrapper for caveman hook command detection."""
    from mms_hook_commands import is_caveman_hook_command

    return is_caveman_hook_command(command_text)


def _is_codex_rtk_hook_command(command_text):
    """Compatibility wrapper for Codex RTK hook command detection."""
    from mms_hook_commands import is_codex_rtk_hook_command

    return is_codex_rtk_hook_command(command_text)


def _is_ecc_hook_command(command_text):
    """Compatibility wrapper for ECC hook command detection."""
    from mms_hook_commands import is_ecc_hook_command

    return is_ecc_hook_command(command_text)


def _is_omc_hook_command(command_text):
    """Compatibility wrapper for OMC hook command detection."""
    from mms_hook_commands import is_omc_hook_command

    return is_omc_hook_command(command_text)


def _is_mms_managed_hook_command(command_text):
    """Compatibility wrapper for MMS-managed hook command detection."""
    from mms_hook_commands import is_mms_managed_hook_command

    return is_mms_managed_hook_command(command_text)


def _is_legacy_loop_hook_command(command_text):
    """Compatibility wrapper for legacy loop hook command detection."""
    from mms_hook_commands import is_legacy_loop_hook_command

    return is_legacy_loop_hook_command(command_text)


def _is_nsr_hook_command(command_text):
    """Compatibility wrapper for NSR hook command detection."""
    from mms_hook_commands import is_nsr_hook_command

    return is_nsr_hook_command(command_text)


def _is_loop_family_hook_command(command_text):
    """Compatibility wrapper for loop-family hook command detection."""
    from mms_hook_commands import is_loop_family_hook_command

    return is_loop_family_hook_command(command_text)


def _is_looop_hook_command(command_text):
    """Backward-compatible alias for older tests/callers."""
    from mms_hook_commands import is_looop_hook_command

    return is_looop_hook_command(command_text)


def _hook_command_targets_exist(command_text):
    """Compatibility wrapper for hook command executable target checks."""
    from mms_hook_commands import hook_command_targets_exist

    return hook_command_targets_exist(command_text)


def _filter_missing_managed_hook_commands(hooks_data):
    """Compatibility wrapper for dropping missing managed hook commands."""
    from mms_claude_settings import filter_missing_managed_hook_commands

    return filter_missing_managed_hook_commands(hooks_data)


def _filter_hook_commands(hooks_data, predicate):
    """Compatibility wrapper for filtering hook commands."""
    from mms_claude_settings import filter_hook_commands

    return filter_hook_commands(hooks_data, predicate)


def _normalize_session_surface_disabled(disabled_session_surfaces):
    """Compatibility wrapper for disabled session-surface normalization."""
    from mms_claude_settings import normalize_session_surface_disabled

    return normalize_session_surface_disabled(disabled_session_surfaces)


def _session_surface_disabled(disabled_session_surfaces, surface, value):
    """Compatibility wrapper for disabled session-surface lookup."""
    from mms_claude_settings import session_surface_disabled

    return session_surface_disabled(disabled_session_surfaces, surface, value)


def _filter_mcp_servers_by_disabled(mcp_servers, disabled_session_surfaces=None):
    """Compatibility wrapper for disabled MCP filtering."""
    from mms_claude_settings import filter_mcp_servers_by_disabled

    return filter_mcp_servers_by_disabled(mcp_servers, disabled_session_surfaces)


def _mcp_command_has_path(command):
    """Compatibility wrapper for MCP command path detection."""
    from mms_hook_commands import mcp_command_has_path

    return mcp_command_has_path(command)


def _normalize_session_mcp_server_spec(name, spec, *, env=None):
    """Make inherited MCP commands session-safe; drop missing local CLIs."""
    from mms_claude_settings import normalize_session_mcp_server_spec

    return normalize_session_mcp_server_spec(name, spec, env=env)


def _normalize_session_mcp_servers(mcp_servers, *, disabled_session_surfaces=None, env=None):
    """Compatibility wrapper for session MCP normalization."""
    from mms_claude_settings import normalize_session_mcp_servers

    return normalize_session_mcp_servers(
        mcp_servers,
        disabled_session_surfaces=disabled_session_surfaces,
        env=env,
    )


def _filter_hooks_by_disabled(hooks_data, disabled_session_surfaces=None):
    """Compatibility wrapper for disabled hook filtering."""
    from mms_claude_settings import filter_hooks_by_disabled

    return filter_hooks_by_disabled(hooks_data, disabled_session_surfaces)


def _session_skill_disabled(disabled_session_surfaces, skill_name):
    """Compatibility wrapper for disabled skill lookup."""
    from mms_claude_settings import session_skill_disabled

    return session_skill_disabled(disabled_session_surfaces, skill_name)


def _caveman_claude_activate_command(caveman_root):
    script_path = os.path.join(caveman_root, "hooks", "caveman-activate.js")
    return (
        "CAVEMAN_HOOK_COMPACT=1 "
        "CAVEMAN_HOOK_EVENT=SessionStart "
        f"node {json.dumps(script_path)}"
    )


def _caveman_claude_tracker_command(caveman_root):
    script_path = os.path.join(caveman_root, "hooks", "caveman-mode-tracker.js")
    return f"node {json.dumps(script_path)}"


def _caveman_codex_activate_command(caveman_root):
    """Compatibility wrapper for Codex caveman activation command."""
    from mms_codex_hooks import caveman_codex_activate_command

    return caveman_codex_activate_command(caveman_root)


def _caveman_codex_hook_payload(caveman_root):
    """Compatibility wrapper for Codex caveman hook payload."""
    from mms_codex_hooks import caveman_codex_hook_payload

    return caveman_codex_hook_payload(caveman_root)


def _codex_shell_hook_payload(command_text, *, timeout=None, status_message=None):
    """Compatibility wrapper for Codex shell hook payload rendering."""
    from mms_codex_hooks import codex_shell_hook_payload

    return codex_shell_hook_payload(command_text, timeout=timeout, status_message=status_message)


def _codex_caveman_session_hook(caveman_root):
    """Compatibility wrapper for Codex caveman session hook rendering."""
    from mms_codex_hooks import codex_caveman_session_hook

    return codex_caveman_session_hook(caveman_root)


def _configure_codex_caveman_hooks(hooks_data, *, enable_caveman=False):
    """Compatibility wrapper for Codex caveman hook configuration."""
    from mms_codex_hooks import configure_codex_caveman_hooks

    return configure_codex_caveman_hooks(hooks_data, enable_caveman=enable_caveman)


def _configure_claude_nsr_hooks(hooks_data, *, enable_nsr=False):
    """Compatibility wrapper for Claude NSR hook configuration."""
    from mms_claude_settings import configure_claude_nsr_hooks

    return configure_claude_nsr_hooks(hooks_data, enable_nsr=enable_nsr)


def _configure_codex_nsr_hooks(hooks_data, *, enable_nsr=False):
    """Compatibility wrapper for Codex NSR hook configuration."""
    from mms_codex_hooks import configure_codex_nsr_hooks

    return configure_codex_nsr_hooks(hooks_data, enable_nsr=enable_nsr)


def _configure_claude_caveman_hooks(hooks_data, *, enable_caveman=False):
    """Compatibility wrapper for Claude caveman hook configuration."""
    from mms_claude_settings import configure_claude_caveman_hooks

    return configure_claude_caveman_hooks(hooks_data, enable_caveman=enable_caveman)


def _load_ecc_claude_hooks():
    ecc_root = _resolve_ecc_root()
    if not ecc_root:
        return {}
    hooks_path = os.path.join(ecc_root, "hooks", "hooks.json")
    try:
        with open(hooks_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        hooks_data = payload.get("hooks")
        return copy.deepcopy(hooks_data) if isinstance(hooks_data, dict) else {}
    except Exception:
        return {}


def _load_omc_claude_hooks():
    omc_root = _resolve_omc_root()
    if not omc_root:
        return {}
    hooks_path = os.path.join(omc_root, "hooks", "hooks.json")
    try:
        with open(hooks_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        hooks_data = payload.get("hooks")
        return copy.deepcopy(hooks_data) if isinstance(hooks_data, dict) else {}
    except Exception:
        return {}


def _configure_claude_ecc_hooks(hooks_data, *, enable_ecc=False):
    """Compatibility wrapper for Claude ECC hook configuration."""
    from mms_claude_settings import configure_claude_ecc_hooks

    return configure_claude_ecc_hooks(hooks_data, enable_ecc=enable_ecc)


def _configure_claude_omc_hooks(hooks_data, *, enable_omc=False):
    """Compatibility wrapper for Claude OMC hook configuration."""
    from mms_claude_settings import configure_claude_omc_hooks

    return configure_claude_omc_hooks(hooks_data, enable_omc=enable_omc)


def _build_codex_session_hooks(base_hooks=None, *, enable_caveman=False, enable_nsr=False, disabled_session_surfaces=None):
    """Compatibility wrapper for Codex session hook payload construction."""
    from mms_codex_hooks import build_codex_session_hooks

    return build_codex_session_hooks(
        base_hooks,
        enable_caveman=enable_caveman,
        enable_nsr=enable_nsr,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _codex_hook_event_state_key(event_name):
    """Compatibility wrapper for Codex hook event state keys."""
    from mms_codex_hook_trust import _codex_hook_event_state_key as codex_hook_event_state_key

    return codex_hook_event_state_key(event_name)


def _codex_hook_fingerprint(hook):
    """Compatibility wrapper for Codex hook fingerprinting."""
    from mms_codex_hook_trust import _codex_hook_fingerprint as codex_hook_fingerprint

    return codex_hook_fingerprint(hook)


def _codex_hook_index(hooks_payload):
    """Compatibility wrapper for Codex hook indexing."""
    from mms_codex_hook_trust import _codex_hook_index as codex_hook_index

    return codex_hook_index(hooks_payload)


def _decode_toml_basic_key(value):
    """Compatibility wrapper for TOML basic key decoding."""
    from mms_codex_hook_trust import _decode_toml_basic_key as decode_toml_basic_key

    return decode_toml_basic_key(value)


def _codex_hook_trust_records_from_config(config_text):
    """Compatibility wrapper for Codex hook trust record parsing."""
    from mms_codex_hook_trust import _codex_hook_trust_records_from_config as records_from_config

    return records_from_config(config_text)


def _normalize_codex_hook_trust_toml_layout(config_text):
    """Compatibility wrapper for Codex hook trust TOML layout cleanup."""
    from mms_codex_hook_trust import _normalize_codex_hook_trust_toml_layout as normalize_layout

    return normalize_layout(config_text)


def _replace_codex_hook_trust_hashes(config_text, trusted_hashes_by_key):
    """Compatibility wrapper for replacing Codex hook trust hashes."""
    from mms_codex_hook_trust import _replace_codex_hook_trust_hashes as replace_hashes

    return replace_hashes(config_text, trusted_hashes_by_key)


def _append_codex_exact_hook_trust_hashes(config_text, trusted_hashes_by_key):
    """Compatibility wrapper for appending exact Codex hook trust hashes."""
    from mms_codex_hook_trust import _append_codex_exact_hook_trust_hashes as append_hashes

    return append_hashes(config_text, trusted_hashes_by_key)


def _codex_hook_trust_refresh_enabled():
    """Compatibility wrapper for Codex hook trust refresh flag parsing."""
    from mms_codex_hook_trust import _codex_hook_trust_refresh_enabled as refresh_enabled

    return refresh_enabled()


def _codex_app_server_hooks_list(codex_home, *, cwds=None, timeout=4.0):
    """Compatibility wrapper for reading current Codex app-server hook hashes."""
    from mms_codex_hook_trust import _codex_app_server_hooks_list as app_server_hooks_list

    return app_server_hooks_list(codex_home, cwds=cwds, timeout=timeout)


def _refresh_codex_current_hook_trust_cache(
    target_codex_dir,
    *,
    cwds=None,
    managed_only=False,
    timeout=4.0,
    allow_non_real_home=False,
):
    """Compatibility wrapper for refreshing Codex hook trust cache."""
    from mms_codex_hook_trust import _refresh_codex_current_hook_trust_cache as refresh_cache

    return refresh_cache(
        target_codex_dir,
        cwds=cwds,
        managed_only=managed_only,
        timeout=timeout,
        allow_non_real_home=allow_non_real_home,
    )


def _collect_codex_hook_trust_seed_sources(codex_roots):
    """Compatibility wrapper for collecting Codex hook trust seed sources."""
    from mms_codex_hook_trust import _collect_codex_hook_trust_seed_sources as collect_seed_sources

    return collect_seed_sources(codex_roots)


def _append_codex_session_hook_trust_states(
    config_text,
    *,
    target_hooks_path,
    target_hooks,
    trust_config_texts=None,
    source_hook_payloads_by_path=None,
):
    """Compatibility wrapper for Codex session hook trust state rendering."""
    from mms_codex_hook_trust import _append_codex_session_hook_trust_states as append_trust_states

    return append_trust_states(
        config_text,
        target_hooks_path=target_hooks_path,
        target_hooks=target_hooks,
        trust_config_texts=trust_config_texts,
        source_hook_payloads_by_path=source_hook_payloads_by_path,
    )


def _overlay_session_entry_dir(parent_dir, overlay_root, entry_name, extra_source_root, *, exclude_names=None):
    """Compatibility wrapper for session entry overlays."""
    from mms_session_overlays import _overlay_session_entry_dir as overlay_session_entry_dir

    return overlay_session_entry_dir(
        parent_dir,
        overlay_root,
        entry_name,
        extra_source_root,
        exclude_names=exclude_names,
    )


def _overlay_session_skill_dir(parent_dir, overlay_root, skill_name, skill_root, *, disabled_session_surfaces=None):
    """Compatibility wrapper for session skill overlays."""
    from mms_session_overlays import _overlay_session_skill_dir as overlay_session_skill_dir

    return overlay_session_skill_dir(
        parent_dir,
        overlay_root,
        skill_name,
        skill_root,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_caveman_session_entries(parent_dir, session_home, *, enable_caveman=False, disabled_session_surfaces=None):
    """Compatibility wrapper for Caveman session overlays."""
    from mms_session_overlays import _overlay_caveman_session_entries as overlay_caveman_session_entries

    return overlay_caveman_session_entries(
        parent_dir,
        session_home,
        enable_caveman=enable_caveman,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_ecc_session_entries(parent_dir, session_home, *, enable_ecc=False, disabled_session_surfaces=None):
    """Compatibility wrapper for ECC session overlays."""
    from mms_session_overlays import _overlay_ecc_session_entries as overlay_ecc_session_entries

    return overlay_ecc_session_entries(
        parent_dir,
        session_home,
        enable_ecc=enable_ecc,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_omc_session_entries(parent_dir, session_home, *, enable_omc=False, disabled_session_surfaces=None):
    """Compatibility wrapper for OMC session overlays."""
    from mms_session_overlays import _overlay_omc_session_entries as overlay_omc_session_entries

    return overlay_omc_session_entries(
        parent_dir,
        session_home,
        enable_omc=enable_omc,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_web_access_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for web-access session overlays."""
    from mms_session_overlays import _overlay_web_access_session_entries as overlay_web_access_session_entries

    return overlay_web_access_session_entries(
        parent_dir,
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_weber_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for weber session overlays."""
    from mms_session_overlays import _overlay_weber_session_entries as overlay_weber_session_entries

    return overlay_weber_session_entries(
        parent_dir,
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_agent_browser_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for agent-browser session overlays."""
    from mms_session_overlays import _overlay_agent_browser_session_entries as overlay_agent_browser_session_entries

    return overlay_agent_browser_session_entries(
        parent_dir,
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_toon_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for TOON session overlays."""
    from mms_session_overlays import _overlay_toon_session_entries as overlay_toon_session_entries

    return overlay_toon_session_entries(
        parent_dir,
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_xmem_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for xmem session overlays."""
    from mms_session_overlays import _overlay_xmem_session_entries as overlay_xmem_session_entries

    return overlay_xmem_session_entries(
        parent_dir,
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_token_saver_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for token-saver session overlays."""
    from mms_session_overlays import _overlay_token_saver_session_entries as overlay_token_saver_session_entries

    return overlay_token_saver_session_entries(
        parent_dir,
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_auto_github_contributor_session_entries(parent_dir, session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for auto-github-contributor session overlays."""
    from mms_session_overlays import _overlay_auto_github_contributor_session_entries as overlay_auto_gh_session_entries

    return overlay_auto_gh_session_entries(
        parent_dir,
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _agy_plugin_dir(account_home):
    """Compatibility wrapper for the AGY session plugin path."""
    from mms_agy_assets import agy_plugin_dir

    return agy_plugin_dir(account_home)


def _path_under(path, root):
    """Compatibility wrapper for path containment checks."""
    from mms_agy_assets import path_under

    return path_under(path, root)


def _ensure_agy_plugin_dir(account_home):
    """Compatibility wrapper for AGY session plugin directory setup."""
    from mms_agy_assets import ensure_agy_plugin_dir

    return ensure_agy_plugin_dir(account_home)


def _write_agy_plugin_json(plugin_dir):
    """Compatibility wrapper for AGY plugin metadata writes."""
    from mms_agy_assets import write_agy_plugin_json

    return write_agy_plugin_json(plugin_dir)


def _remove_file_if_exists(path):
    """Compatibility wrapper for optional AGY asset cleanup."""
    from mms_agy_assets import remove_file_if_exists

    return remove_file_if_exists(path)


def _write_agy_mcp_config(plugin_dir, *, disabled_session_surfaces=None):
    """Compatibility wrapper for AGY MCP config writes."""
    from mms_agy_assets import write_agy_mcp_config

    return write_agy_mcp_config(plugin_dir, disabled_session_surfaces=disabled_session_surfaces)


def _write_agy_hooks(plugin_dir, *, enable_caveman=False, disabled_session_surfaces=None):
    """Compatibility wrapper for AGY hook materialization."""
    from mms_agy_assets import write_agy_hooks

    return write_agy_hooks(
        plugin_dir,
        enable_caveman=enable_caveman,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_agy_session_assets(account_home, session_home, *, enable_caveman=False, disabled_session_surfaces=None):
    """Compatibility wrapper for AGY session plugin overlays."""
    from mms_agy_assets import overlay_agy_session_assets

    return overlay_agy_session_assets(
        account_home,
        session_home,
        enable_caveman=enable_caveman,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_opencode_session_assets(config_dir, session_home, *, enable_caveman=False, disabled_session_surfaces=None, runtime=None):
    return _overlay_opencode_session_assets_impl(
        config_dir,
        session_home,
        enable_caveman=enable_caveman,
        disabled_session_surfaces=disabled_session_surfaces,
        runtime=runtime,
        overlay_opencode_rtk_plugin=_overlay_opencode_rtk_plugin,
        overlay_caveman_session_entries=_overlay_caveman_session_entries,
        overlay_web_access_session_entries=_overlay_web_access_session_entries,
        overlay_weber_session_entries=_overlay_weber_session_entries,
        overlay_toon_session_entries=_overlay_toon_session_entries,
        overlay_token_saver_session_entries=_overlay_token_saver_session_entries,
        overlay_xmem_session_entries=_overlay_xmem_session_entries,
        overlay_opencode_xmem_plugin=_overlay_opencode_xmem_plugin,
    )


def _configure_ecc_session_env(env_data, *, enable_ecc=False):
    """Compatibility wrapper for ECC session env configuration."""
    from mms_session_env import configure_ecc_session_env

    return configure_ecc_session_env(env_data, enable_ecc=enable_ecc)


def _configure_agent_pack_session_env(env_data, *, agent_pack="none"):
    """Compatibility wrapper for agent-pack session env configuration."""
    from mms_session_env import configure_agent_pack_session_env

    return configure_agent_pack_session_env(env_data, agent_pack=agent_pack)


def _session_required_env_from_runtime_env(env):
    """Compatibility wrapper for session-required runtime env extraction."""
    from mms_session_env import session_required_env_from_runtime_env

    return session_required_env_from_runtime_env(env)


def _sanitize_claude_inherited_settings_payload(settings_data, *, allow_execution_surfaces=True):
    """Compatibility wrapper for Claude settings inheritance allowlist."""
    from mms_claude_settings import sanitize_claude_inherited_settings_payload

    return sanitize_claude_inherited_settings_payload(
        settings_data,
        allow_execution_surfaces=allow_execution_surfaces,
    )


def _sanitize_account_claude_settings_payload(settings_data):
    """Compatibility wrapper for account-scoped Claude settings sanitization."""
    from mms_claude_settings import sanitize_account_claude_settings_payload

    return sanitize_account_claude_settings_payload(settings_data)


def _default_session_mcp_servers():
    """Compatibility wrapper for default session MCP discovery."""
    from mms_claude_settings import default_session_mcp_servers

    return default_session_mcp_servers()


def _resolve_hive_root(module_path=None):
    """Compatibility wrapper for Hive MCP root discovery."""
    from mms_session_mcp import resolve_hive_root

    return resolve_hive_root(module_path=module_path)


def _default_hive_session_mcp_server():
    """Compatibility wrapper for default Hive session MCP server discovery."""
    from mms_session_mcp import default_hive_session_mcp_server

    return default_hive_session_mcp_server()


def _resolve_pilot_root(module_path=None):
    """Compatibility wrapper for Pilot MCP root discovery."""
    from mms_session_mcp import resolve_pilot_root

    return resolve_pilot_root(module_path=module_path)


def _default_pilot_session_mcp_server():
    """Compatibility wrapper for default Pilot session MCP server discovery."""
    from mms_session_mcp import default_pilot_session_mcp_server

    return default_pilot_session_mcp_server()


def _replace_plugin_root_tokens(value, plugin_root):
    """Compatibility wrapper for plugin MCP root token replacement."""
    from mms_session_mcp import replace_plugin_root_tokens

    return replace_plugin_root_tokens(value, plugin_root)


def _load_plugin_mcp_servers(plugin_root):
    """Compatibility wrapper for plugin MCP server loading."""
    from mms_session_mcp import load_plugin_mcp_servers

    return load_plugin_mcp_servers(plugin_root)


def _agent_pack_mcp_servers(agent_pack):
    """Compatibility wrapper for agent-pack MCP discovery."""
    from mms_claude_settings import agent_pack_mcp_servers

    return agent_pack_mcp_servers(agent_pack)


def _merge_agent_pack_mcp_servers(mcp_servers, *, agent_pack="none", disabled_session_surfaces=None):
    """Compatibility wrapper for agent-pack MCP merging."""
    from mms_claude_settings import merge_agent_pack_mcp_servers

    return merge_agent_pack_mcp_servers(
        mcp_servers,
        agent_pack=agent_pack,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _ensure_session_only_claude_mcp_servers(settings_data, *, disabled_session_surfaces=None):
    """Compatibility wrapper for session-only Claude MCP injection."""
    from mms_claude_settings import ensure_session_only_claude_mcp_servers

    return ensure_session_only_claude_mcp_servers(
        settings_data,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _session_managed_mcp_server_allowlist(*, allow_execution_surfaces=True):
    """Compatibility wrapper for session-managed MCP allowlist."""
    from mms_claude_settings import session_managed_mcp_server_allowlist

    return session_managed_mcp_server_allowlist(
        allow_execution_surfaces=allow_execution_surfaces
    )


def _session_managed_mcp_servers(settings_data, *, allow_execution_surfaces=True, disabled_session_surfaces=None):
    """Compatibility wrapper for session-managed Claude MCP collection."""
    from mms_claude_settings import session_managed_mcp_servers

    return session_managed_mcp_servers(
        settings_data,
        allow_execution_surfaces=allow_execution_surfaces,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _inject_managed_mcp_servers_into_claude_state(
    payload,
    settings_data=None,
    *,
    allow_execution_surfaces=True,
    disabled_session_surfaces=None,
    agent_pack="none",
):
    """Compatibility wrapper for Claude state managed MCP injection."""
    from mms_claude_settings import inject_managed_mcp_servers_into_claude_state

    return inject_managed_mcp_servers_into_claude_state(
        payload,
        settings_data=settings_data,
        allow_execution_surfaces=allow_execution_surfaces,
        disabled_session_surfaces=disabled_session_surfaces,
        agent_pack=agent_pack,
    )


def _copy_allowed_scalar_fields(payload, allowed_keys):
    """Compatibility wrapper for scalar allowlist copies."""
    from mms_claude_state import copy_allowed_scalar_fields

    return copy_allowed_scalar_fields(payload, allowed_keys)


def _copy_allowed_scalar_dict_fields(payload, allowed_keys):
    """Compatibility wrapper for scalar dict allowlist copies."""
    from mms_claude_state import copy_allowed_scalar_dict_fields

    return copy_allowed_scalar_dict_fields(payload, allowed_keys)


def _sanitize_claude_ui_state_seed_payload(payload):
    """Compatibility wrapper for Claude UI state seed sanitization."""
    from mms_claude_state import sanitize_claude_ui_state_seed_payload

    return sanitize_claude_ui_state_seed_payload(payload)


def _merge_scalar_dict_entries(existing_payload, incoming_payload, *, prefer_max_numeric=False):
    """Compatibility wrapper for scalar dict merging."""
    from mms_claude_state import merge_scalar_dict_entries

    return merge_scalar_dict_entries(
        existing_payload,
        incoming_payload,
        prefer_max_numeric=prefer_max_numeric,
    )


def _merge_claude_ui_state_seed(target_payload, seed_payload):
    """Compatibility wrapper for Claude UI state seed merging."""
    from mms_claude_state import merge_claude_ui_state_seed

    return merge_claude_ui_state_seed(target_payload, seed_payload)


def _merge_claude_gateway_ui_state_payload(existing_payload, incoming_payload):
    """Compatibility wrapper for Claude gateway UI state merging."""
    from mms_claude_state import merge_claude_gateway_ui_state_payload

    return merge_claude_gateway_ui_state_payload(existing_payload, incoming_payload)


def _strip_claude_state_execution_surfaces(payload):
    """Compatibility wrapper for stripping execution surfaces from Claude state."""
    from mms_claude_state import strip_claude_state_execution_surfaces

    return strip_claude_state_execution_surfaces(payload)


def _sanitize_claude_project_state_entry(entry):
    """Compatibility wrapper for Claude project state entry sanitization."""
    from mms_claude_state import sanitize_claude_project_state_entry

    return sanitize_claude_project_state_entry(entry)


def _sanitize_claude_project_state_map(projects_data):
    """Compatibility wrapper for Claude project state map sanitization."""
    from mms_claude_state import sanitize_claude_project_state_map

    return sanitize_claude_project_state_map(projects_data)


def _load_real_claude_ui_state_seed():
    """Compatibility wrapper for reading real Claude UI state seed."""
    from mms_claude_state import load_real_claude_ui_state_seed

    return load_real_claude_ui_state_seed()


def _load_real_claude_project_state(project_path):
    """Compatibility wrapper for reading real Claude project state."""
    from mms_claude_state import load_real_claude_project_state

    return load_real_claude_project_state(project_path)


def _sanitize_oauth_claude_state_payload(data):
    """Compatibility wrapper for OAuth Claude state sanitization."""
    from mms_claude_state import sanitize_oauth_claude_state_payload

    return sanitize_oauth_claude_state_payload(data)


def _sanitize_codex_claude_state_payload(data):
    """Compatibility wrapper for Codex-seeded Claude state sanitization."""
    from mms_claude_state import sanitize_codex_claude_state_payload

    return sanitize_codex_claude_state_payload(data)


_CLAUDE_GATEWAY_SENSITIVE_STATE_KEYS = (
    "oauthAccount",
    "provider",
    "api_key",
    "userID",
    "cachedExtraUsageDisabledReason",
    "customApiKeyResponses",
    "passesEligibilityCache",
    "s1mAccessCache",
    "hasAvailableSubscription",
    "penguinModeOrgEnabled",
    "subscriptionNoticeCount",
)


def _strip_claude_restore_state(data, *, strip_sensitive_auth=False):
    """Compatibility wrapper for Claude restore-state stripping."""
    from mms_claude_state import strip_claude_restore_state

    return strip_claude_restore_state(data, strip_sensitive_auth=strip_sensitive_auth)


def _load_project_scoped_claude_resume_session_id(
    project_path,
    *,
    account_id="",
    runtime_kind="",
    resume_model="",
):
    """Compatibility wrapper for project-scoped Claude resume lookup."""
    from mms_claude_session import load_project_scoped_claude_resume_session_id

    return load_project_scoped_claude_resume_session_id(
        project_path,
        account_id=account_id,
        runtime_kind=runtime_kind,
        resume_model=resume_model,
    )


def _overlay_project_scoped_claude_resume_state(
    data,
    project_path,
    *,
    account_id="",
    runtime_kind="",
    resume_model="",
):
    """Compatibility wrapper for project-scoped Claude resume state overlay."""
    from mms_claude_session import overlay_project_scoped_claude_resume_state

    return overlay_project_scoped_claude_resume_state(
        data,
        project_path,
        account_id=account_id,
        runtime_kind=runtime_kind,
        resume_model=resume_model,
    )


def _ensure_claude_project_trust(
    data,
    project_path,
    project_state=None,
    *,
    allow_execution_surfaces=True,
    disabled_session_surfaces=None,
):
    """Compatibility wrapper for Claude project trust state materialization."""
    from mms_claude_state import ensure_claude_project_trust

    return ensure_claude_project_trust(
        data,
        project_path,
        project_state=project_state,
        allow_execution_surfaces=allow_execution_surfaces,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _copy_claude_state_json(src, dst, *, mode="restore"):
    """Compatibility wrapper for Claude state JSON copy/sanitization."""
    from mms_claude_state import copy_claude_state_json

    return copy_claude_state_json(src, dst, mode=mode)


def _parse_iso8601_utc(value):
    """Compatibility wrapper for OAuth token timestamp parsing."""
    from mms_claude_state import parse_iso8601_utc

    return parse_iso8601_utc(value)


def _merge_oauth_token_state(existing_payload, incoming_payload):
    """Compatibility wrapper for OAuth token state merging."""
    from mms_claude_state import merge_oauth_token_state

    return merge_oauth_token_state(existing_payload, incoming_payload)


def _merge_oauth_claude_state_payload(existing_data, incoming_data):
    """Compatibility wrapper for OAuth Claude state merging."""
    from mms_claude_state import merge_oauth_claude_state_payload

    return merge_oauth_claude_state_payload(existing_data, incoming_data)


def _masked_exposure_env_value(key, value):
    """Compatibility wrapper for exposure env masking."""
    from mms_runtime_exposure import masked_exposure_env_value

    return masked_exposure_env_value(key, value)


def inspect_runtime_exposure(cli, runtime):
    """Compatibility wrapper for runtime exposure audits."""
    from mms_runtime_exposure import inspect_runtime_exposure as inspect_runtime_exposure_impl

    return inspect_runtime_exposure_impl(cli, runtime)


def _build_claude_session_settings(
    base_settings=None,
    *,
    required_env=None,
    default_env=None,
    allow_execution_surfaces=True,
    enable_caveman=False,
    enable_nsr=False,
    enable_ecc=False,
    enable_omc=False,
    disabled_session_surfaces=None,
):
    """Compatibility wrapper for Claude session settings materialization."""
    from mms_claude_settings import build_claude_session_settings

    return build_claude_session_settings(
        base_settings,
        required_env=required_env,
        default_env=default_env,
        allow_execution_surfaces=allow_execution_surfaces,
        enable_caveman=enable_caveman,
        enable_nsr=enable_nsr,
        enable_ecc=enable_ecc,
        enable_omc=enable_omc,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _write_claude_session_settings(
    session_claude_dir,
    *,
    required_env=None,
    default_env=None,
    base_settings=None,
    allow_execution_surfaces=True,
    enable_caveman=False,
    enable_nsr=False,
    enable_ecc=False,
    enable_omc=False,
    disabled_session_surfaces=None,
):
    """Compatibility wrapper for writing session-local Claude settings."""
    from mms_claude_settings import write_claude_session_settings

    return write_claude_session_settings(
        session_claude_dir,
        required_env=required_env,
        default_env=default_env,
        base_settings=base_settings,
        allow_execution_surfaces=allow_execution_surfaces,
        enable_caveman=enable_caveman,
        enable_nsr=enable_nsr,
        enable_ecc=enable_ecc,
        enable_omc=enable_omc,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _seed_oauth_claude_session_settings(account_claude_dir, session_claude_dir):
    """Compatibility wrapper for OAuth session settings seeding."""
    from mms_claude_settings import seed_oauth_claude_session_settings

    return seed_oauth_claude_session_settings(account_claude_dir, session_claude_dir)


def _gateway_ping(base_url, api_key, runtime=None):
    """Quick connectivity check; returns True/False/None (None = can't determine)."""
    _ensure_bridge_helpers()
    try:
        import httpx as _httpx  # noqa: F401
    except ImportError:
        return None
    if not base_url or not api_key:
        return None
    models_url = _build_gateway_url(base_url, "/models")
    headers = {"Authorization": f"Bearer {api_key}"}
    anthropic_base = str(_anthropic_base_url(runtime or {}) or "").strip().rstrip("/")
    if anthropic_base and anthropic_base == str(base_url or "").strip().rstrip("/"):
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    try:
        r = _runtime_httpx_request(
            "GET",
            models_url,
            runtime=runtime,
            headers=headers,
            timeout=8,
        )
        return 200 <= int(getattr(r, "status_code", 0) or 0) < 300
    except Exception:
        return False


def _load_gateway_health_cache():
    try:
        with open(HEALTH_CHECK_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    providers = data.get("providers")
    if isinstance(providers, dict):
        return providers
    provider_id = str(data.get("provider_id") or "").strip()
    timestamp = str(data.get("timestamp") or "").strip()
    if provider_id and timestamp:
        return {
            provider_id: {
                "timestamp": timestamp,
                "ok": bool(data.get("ok")),
            }
        }
    return {}


def _save_gateway_health_cache(providers):
    if not isinstance(providers, dict):
        return
    try:
        os.makedirs(os.path.dirname(HEALTH_CHECK_PATH), exist_ok=True)
        tmp_path = HEALTH_CHECK_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({"providers": providers}, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_path, HEALTH_CHECK_PATH)
    except OSError:
        pass


def _health_check_due(provider_id):
    try:
        providers = _load_gateway_health_cache()
        entry = providers.get(str(provider_id or "").strip())
        if not isinstance(entry, dict):
            return True
        last = datetime.fromisoformat(str(entry.get("timestamp") or ""))
        return (datetime.now() - last).total_seconds() > 86400
    except Exception:
        return True


def gateway_health_check(provider):
    """Daily first-use connectivity check for gateway providers."""
    if provider.get("skip_gateway_health_check"):
        return
    provider_id = provider.get("id", "default")
    if not _health_check_due(provider_id):
        return
    base_url = _openai_base_url(provider) or _anthropic_base_url(provider)
    api_key = provider.get("api_key", "")
    ok = _gateway_ping(base_url, api_key, runtime=provider)
    if ok is None:
        return
    providers = _load_gateway_health_cache()
    providers[provider_id] = {
        "timestamp": datetime.now().isoformat(),
        "ok": bool(ok),
    }
    _save_gateway_health_cache(providers)
    if ok:
        console.print(f"[dim]✓ gateway {base_url} 可达[/dim]")
    else:
        console.print(f"[yellow]⚠ gateway {base_url} 健康检查未通过，连接可能不稳定[/yellow]")


def _provider_protocols(provider):
    """Compatibility wrapper for provider protocol normalization."""
    from mms_runtime_urls import provider_protocols

    return provider_protocols(provider)


def _provider_supports_cli(provider, cli):
    """Compatibility wrapper for provider CLI support validation."""
    from mms_runtime_validation import provider_supports_cli

    return provider_supports_cli(provider, cli)


def validate_provider_for_cli(cli, provider):
    """Compatibility wrapper for provider launch validation."""
    from mms_runtime_validation import validate_provider_for_cli as validate_provider_for_cli_impl

    return validate_provider_for_cli_impl(cli, provider)


def _scrub_claude_oauth_env(env):
    """Compatibility wrapper for Claude OAuth env scrubbing."""
    from mms_runtime_env import scrub_claude_oauth_env

    return scrub_claude_oauth_env(env)


def _scrub_inherited_runtime_env(env, *, strip_openai=False, strip_proxy=False):
    """Compatibility wrapper for inherited runtime env scrubbing."""
    from mms_runtime_env import scrub_inherited_runtime_env

    return scrub_inherited_runtime_env(
        env,
        strip_openai=strip_openai,
        strip_proxy=strip_proxy,
    )


def _account_env(account, *, validate_proxy=True, model_info=None):
    """Compatibility wrapper for OAuth/account runtime env materialization."""
    from mms_account_env import build_account_env

    return build_account_env(
        account,
        validate_proxy=validate_proxy,
        model_info=model_info,
    )


def _overlay_codex_shared_resume(home_dir, session_home):
    """Compatibility wrapper for account Codex shared-resume overlay."""
    from mms_codex_assets import overlay_codex_shared_resume

    return overlay_codex_shared_resume(home_dir, session_home)


_CODEX_BOUNDED_RESUME_FILES = {
    "history.jsonl": 200,
    "session_index.jsonl": 50,
}

_CODEX_BOUNDED_RESUME_DIRS = {
    "sessions": 25,
    "shell_snapshots": 20,
    "archived_sessions": 0,
}

_CODEX_RESUME_SEED_MANIFEST = "mms-resume-seed.json"
_CODEX_RESUME_WRITEBACK_MANIFEST = "mms-resume-writeback.json"
_CODEX_RESUME_WRITEBACK_ROOT_ENV = "MMS_CODEX_RESUME_WRITEBACK_ROOT"
_CODEX_RESUME_MAX_FILE_BYTES = 2_000_000
_CODEX_RESUME_PROJECT_MAX_FILE_BYTES = 32_000_000
_CODEX_COPY_INTO_SESSION_FILES = {"installation_id"}
_CODEX_PLUGIN_MARKETPLACE_CACHE_ENTRIES = (
    "plugins",
    "plugins.sha",
    "bundled-marketplaces",
)
_CODEX_SESSION_LOCAL_ONLY_ENTRIES = {
    ".codex-global-state.json",
    ".tmp",
    "models_cache.json",
    "version.json",
    "sqlite",
    "tmp",
    "app-server-control",
    "app-server-daemon",
}
_CODEX_SESSION_LOCAL_ONLY_PREFIXES = (
    ".codex-global-state.json.",
    ".codex-global-state.json.tmp-",
    "app-server-",
)


def _materialize_codex_session_entry(entry, src, dst):
    """Compatibility wrapper for Codex session entry materialization."""
    from mms_codex_assets import materialize_codex_session_entry

    return materialize_codex_session_entry(entry, src, dst)


def _overlay_codex_plugin_marketplace_cache(session_codex_dir, source_codex_dirs):
    """Compatibility wrapper for Codex marketplace cache overlay."""
    from mms_codex_assets import overlay_codex_plugin_marketplace_cache

    return overlay_codex_plugin_marketplace_cache(session_codex_dir, source_codex_dirs)


def _codex_entry_is_session_local(entry):
    """Compatibility wrapper for Codex session-local entry filtering."""
    from mms_codex_assets import codex_entry_is_session_local

    return codex_entry_is_session_local(entry)


def _bounded_env_int(name, default):
    """Compatibility wrapper for bounded integer env parsing."""
    from mms_codex_resume import _bounded_env_int as bounded_env_int

    return bounded_env_int(name, default)


def _first_existing_child(source_roots, entry_name, *, want_dir=False):
    """Compatibility wrapper for first bounded-resume child lookup."""
    from mms_codex_resume import _first_existing_child as first_existing_child

    return first_existing_child(source_roots, entry_name, want_dir=want_dir)


def _existing_children(source_roots, entry_name, *, want_dir=False):
    """Compatibility wrapper for bounded-resume child lookup."""
    from mms_codex_resume import _existing_children as existing_children

    return existing_children(source_roots, entry_name, want_dir=want_dir)


def _copy_tail_lines(src, dst, max_lines):
    """Compatibility wrapper for bounded resume tail copy."""
    from mms_codex_resume import _copy_tail_lines as copy_tail_lines

    return copy_tail_lines(src, dst, max_lines)


def _safe_relative_path(root, path):
    """Compatibility wrapper for bounded resume relative paths."""
    from mms_codex_resume import _safe_relative_path as safe_relative_path

    return safe_relative_path(root, path)


def _codex_session_file_cwd(path):
    """Compatibility wrapper for Codex session-file cwd extraction."""
    from mms_codex_resume import _codex_session_file_cwd as codex_session_file_cwd

    return codex_session_file_cwd(path)


def _path_is_same_or_child(path, root):
    """Compatibility wrapper for same-or-child path checks."""
    from mms_codex_resume import _path_is_same_or_child as path_is_same_or_child

    return path_is_same_or_child(path, root)


def _copy_latest_files_from_roots(src_roots, dst_root, max_files, *, max_file_bytes, project_path=""):
    """Compatibility wrapper for bounded resume latest-file copy."""
    from mms_codex_resume import _copy_latest_files_from_roots as copy_latest_files_from_roots

    return copy_latest_files_from_roots(
        src_roots,
        dst_root,
        max_files,
        max_file_bytes=max_file_bytes,
        project_path=project_path,
    )


def _copy_latest_files(src_root, dst_root, max_files, *, max_file_bytes):
    """Compatibility wrapper for bounded resume latest-file copy."""
    from mms_codex_resume import _copy_latest_files as copy_latest_files

    return copy_latest_files(src_root, dst_root, max_files, max_file_bytes=max_file_bytes)


def _codex_sibling_session_roots(sessions_dir, *, exclude_session_home="", max_roots=None):
    """Compatibility wrapper for Codex sibling session roots."""
    from mms_codex_resume import _codex_sibling_session_roots as codex_sibling_session_roots

    return codex_sibling_session_roots(
        sessions_dir,
        exclude_session_home=exclude_session_home,
        max_roots=max_roots,
    )


def _seed_codex_bounded_resume(source_roots, session_codex_dir):
    """Compatibility wrapper for Codex bounded resume seeding."""
    from mms_codex_resume import _seed_codex_bounded_resume as seed_codex_bounded_resume

    return seed_codex_bounded_resume(source_roots, session_codex_dir)


def _set_codex_resume_writeback_root(env, target_codex_dir):
    """Compatibility wrapper for Codex resume write-back env injection."""
    from mms_codex_resume import _set_codex_resume_writeback_root as set_writeback_root

    return set_writeback_root(env, target_codex_dir)


def _mms_resume_command_name():
    return "mms"


def _print_mms_resume_hint(cli_name, session_id):
    cli_name = str(cli_name or "").strip().lower()
    session_id = str(session_id or "").strip()
    if (
        cli_name not in {"codex", "claude"}
        or not session_id
        or session_id == "None"
        or session_id.startswith("pid-")
    ):
        return
    resume_ref = f"{cli_name}:{session_id}"
    command = f"{_mms_resume_command_name()} resume {shlex.quote(resume_ref)}"
    console.print(f"[dim][MMS] resume:[/dim] [green]{command}[/green]")


def _codex_index_records(codex_dir):
    """Compatibility wrapper for Codex bounded index records."""
    from mms_codex_resume import _codex_index_records as codex_index_records

    return codex_index_records(codex_dir)


def _codex_resume_record_fingerprint(record):
    """Compatibility wrapper for Codex resume record fingerprints."""
    from mms_codex_resume import _codex_resume_record_fingerprint as resume_record_fingerprint

    return resume_record_fingerprint(record)


def _codex_resume_index_snapshot(codex_dir):
    """Compatibility wrapper for Codex resume index snapshots."""
    from mms_codex_resume import _codex_resume_index_snapshot as resume_index_snapshot

    return resume_index_snapshot(codex_dir)


def _codex_resume_sort_key(record):
    """Compatibility wrapper for Codex resume sort keys."""
    from mms_codex_resume import _codex_resume_sort_key as resume_sort_key

    return resume_sort_key(record)


def _codex_resume_hint_session_id(codex_dir, baseline_snapshot):
    """Compatibility wrapper for Codex resume hint session selection."""
    from mms_codex_resume import _codex_resume_hint_session_id as resume_hint_session_id

    return resume_hint_session_id(codex_dir, baseline_snapshot)


def _merge_tail_lines(src, dst, max_lines):
    """Compatibility wrapper for Codex bounded resume tail merge."""
    from mms_codex_resume import _merge_tail_lines as merge_tail_lines

    return merge_tail_lines(src, dst, max_lines)


def _copy_resume_dir_back(src_root, dst_root, max_files, *, max_file_bytes):
    """Compatibility wrapper for Codex bounded resume dir write-back."""
    from mms_codex_resume import _copy_resume_dir_back as copy_resume_dir_back

    return copy_resume_dir_back(src_root, dst_root, max_files, max_file_bytes=max_file_bytes)


def _sync_codex_bounded_resume_back(session_codex_dir, target_codex_dir):
    """Compatibility wrapper for Codex bounded resume write-back."""
    from mms_codex_resume import _sync_codex_bounded_resume_back as sync_bounded_resume_back

    return sync_bounded_resume_back(session_codex_dir, target_codex_dir)


def _write_codex_hook_trust_cache(
    target_codex_dir,
    hooks_payload,
    *,
    trust_config_texts=None,
    source_hook_payloads_by_path=None,
):
    """Compatibility wrapper for writing Codex hook trust cache."""
    from mms_codex_hook_trust import _write_codex_hook_trust_cache as write_hook_trust_cache

    return write_hook_trust_cache(
        target_codex_dir,
        hooks_payload,
        trust_config_texts=trust_config_texts,
        source_hook_payloads_by_path=source_hook_payloads_by_path,
    )


def _sync_codex_hook_trust_back(session_codex_dir, target_codex_dir):
    """Compatibility wrapper for syncing Codex hook trust back to durable cache."""
    from mms_codex_hook_trust import _sync_codex_hook_trust_back as sync_hook_trust_back

    return sync_hook_trust_back(session_codex_dir, target_codex_dir)


def _sync_codex_bounded_resume_back_from_env(env):
    """Compatibility wrapper for env-driven Codex bounded resume write-back."""
    from mms_codex_resume import _sync_codex_bounded_resume_back_from_env as sync_from_env

    return sync_from_env(env)


def _codex_resume_writeback_callback(env):
    """Compatibility wrapper for Codex resume write-back callback."""
    from mms_codex_resume import _codex_resume_writeback_callback as resume_writeback_callback

    return resume_writeback_callback(env)


def _codex_bounded_resume_entries():
    """Compatibility wrapper for Codex bounded resume entry names."""
    from mms_codex_resume import _codex_bounded_resume_entries as bounded_resume_entries

    return bounded_resume_entries()


def _link_shared_dotfiles(session_home):
    """Compatibility wrapper for shared dotfile links in session homes."""
    from mms_session_assets import link_shared_dotfiles

    return link_shared_dotfiles(session_home)


def _link_real_local_bin(session_home):
    """Compatibility wrapper for exposing real ~/.local/bin in Claude sessions."""
    from mms_claude_session import link_real_local_bin

    return link_real_local_bin(session_home)


def _link_claude_library_entries(session_home, entries=_CLAUDE_SESSION_LIBRARY_ENTRY_ALLOWLIST):
    """Compatibility wrapper for Claude session Library allowlist links."""
    from mms_claude_session import link_claude_library_entries

    return link_claude_library_entries(session_home, entries=entries)


def _ensure_account_library_entries(account_home, entries=_CLAUDE_SESSION_LIBRARY_ENTRY_ALLOWLIST):
    """Compatibility wrapper for account Library allowlist preparation."""
    from mms_claude_session import ensure_account_library_entries

    return ensure_account_library_entries(account_home, entries=entries)


def _macos_security_bin():
    """Compatibility wrapper for macOS security binary discovery."""
    from mms_agy_security import macos_security_bin

    return macos_security_bin()


def _agy_keychain_path(account_home):
    """Compatibility wrapper for AGY account keychain path."""
    from mms_agy_security import agy_keychain_path

    return agy_keychain_path(account_home)


def _agy_security_home_env(security_home):
    """Compatibility wrapper for AGY security command env."""
    from mms_agy_security import agy_security_home_env

    return agy_security_home_env(security_home)


def _run_agy_security_command(security_bin, args, *, security_home, check=False):
    """Compatibility wrapper for AGY security command execution."""
    from mms_agy_security import run_agy_security_command

    return run_agy_security_command(
        security_bin,
        args,
        security_home=security_home,
        check=check,
    )


def _ensure_agy_account_keychain(account_home, session_home=None):
    """Compatibility wrapper for AGY account keychain preparation."""
    from mms_agy_security import ensure_agy_account_keychain

    return ensure_agy_account_keychain(account_home, session_home=session_home)


def _install_agy_security_wrapper(session_home, account_home, env):
    """Compatibility wrapper for AGY session security wrapper install."""
    from mms_agy_security import install_agy_security_wrapper

    return install_agy_security_wrapper(session_home, account_home, env)


def _link_account_library_entries(session_home, account_home, entries=_CLAUDE_SESSION_LIBRARY_ENTRY_ALLOWLIST):
    """Compatibility wrapper for account Library links into session homes."""
    from mms_claude_session import link_account_library_entries

    return link_account_library_entries(session_home, account_home, entries=entries)


def _filter_real_home_wrapper_path(path_value, *, session_home=None):
    from mms_launcher_export import filter_real_home_wrapper_path

    return filter_real_home_wrapper_path(
        path_value,
        session_home=session_home,
        real_user_home=_real_user_home,
        environ=os.environ,
    )


def _dedupe_path_parts(parts):
    from mms_launcher_export import dedupe_path_parts

    return dedupe_path_parts(parts)


def _real_home_wrapper_search_path(session_home, env=None):
    from mms_launcher_export import real_home_wrapper_search_path

    return real_home_wrapper_search_path(
        session_home,
        env,
        real_user_home=_real_user_home,
        environ=os.environ,
        filter_real_home_wrapper_path=_filter_real_home_wrapper_path,
        dedupe_path_parts=_dedupe_path_parts,
        cli_search_dirs=cli_search_dirs,
    )


def _write_real_home_script(path, lines):
    from mms_launcher_export import write_real_home_script

    return write_real_home_script(path, lines)


def _install_chrome_host_wrapper(wrapper_dir, env, wrapper_path_env):
    from mms_launcher_export import install_chrome_host_wrapper

    return install_chrome_host_wrapper(
        wrapper_dir,
        env,
        wrapper_path_env,
        real_user_home=_real_user_home,
        real_user_path=_real_user_path,
        real_home_wrapper_scrub_lines=_real_home_wrapper_scrub_lines,
        write_real_home_script=_write_real_home_script,
    )


def _install_session_command_wrappers(session_home, env):
    from mms_launcher_export import install_session_command_wrappers

    return install_session_command_wrappers(
        session_home,
        env,
        real_user_home=_real_user_home,
        real_user_path=_real_user_path,
        real_home_wrapper_search_path=_real_home_wrapper_search_path,
        real_home_wrapper_scrub_lines=_real_home_wrapper_scrub_lines,
        write_real_home_script=_write_real_home_script,
        install_chrome_host_wrapper=_install_chrome_host_wrapper,
        wrapper_commands=_SESSION_REAL_HOME_WRAPPER_COMMANDS,
        mms_toon_script_path=_mms_toon_script_path,
        mms_context_script_path=_mms_context_script_path,
        token_saver_script_path=_token_saver_script_path,
        xmem_cli_path=_xmem_cli_path,
    )


def _resolve_real_home_command_path(command_name, env=None):
    """Compatibility wrapper for real-home command lookup."""
    from mms_launcher_export import resolve_real_home_command_path

    return resolve_real_home_command_path(
        command_name,
        env,
        environ=os.environ,
        real_home_wrapper_search_path=_real_home_wrapper_search_path,
        which=shutil.which,
        defpath=os.defpath,
    )


def _mmc_entry_path():
    """Compatibility wrapper for the retired MMC entry path."""
    from mms_mmc_launch import mmc_entry_path

    return mmc_entry_path()


def _assert_safe_mmc_delegate_binary(path_value, *, label):
    """Compatibility wrapper for MMC delegate binary validation."""
    from mms_mmc_launch import assert_safe_mmc_delegate_binary

    return assert_safe_mmc_delegate_binary(path_value, label=label)


def _build_mmc_delegate_env():
    """Compatibility wrapper for MMC delegate env building."""
    from mms_mmc_launch import build_mmc_delegate_env

    return build_mmc_delegate_env()


def _mmc_launch_env_overrides(model_info, runtime, *, enable_claude_1m=True):
    """Compatibility wrapper for retired MMC launch env projection."""
    from mms_mmc_launch import mmc_launch_env_overrides

    return mmc_launch_env_overrides(
        model_info,
        runtime,
        enable_claude_1m=enable_claude_1m,
    )


def _exit_oauth_claude_manual_only(runtime=None, model_info=None, *, caller="MMS"):
    """Compatibility wrapper for OAuth Claude manual-only hard cut."""
    from mms_mmc_launch import exit_oauth_claude_manual_only

    return exit_oauth_claude_manual_only(runtime, model_info, caller=caller)


def _launch_claude_oauth_via_mmc(model_info, runtime, once=False, *, enable_claude_1m=True):
    """Compatibility wrapper for the retired MMC OAuth Claude path."""
    from mms_mmc_launch import launch_claude_oauth_via_mmc

    return launch_claude_oauth_via_mmc(
        model_info,
        runtime,
        once=once,
        enable_claude_1m=enable_claude_1m,
    )


def _sync_codex_session_claude_json(session_home, *, disabled_session_surfaces=None):
    """Compatibility wrapper for Codex session Claude-state seeding."""
    from mms_codex_claude_state import sync_codex_session_claude_json

    return sync_codex_session_claude_json(
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _toml_quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def _toml_literal(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return _toml_quote(value)


def _toml_bare_key(key):
    import re
    if re.fullmatch(r"[A-Za-z0-9_-]+", str(key)):
        return str(key)
    escaped = str(key).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _strip_codex_mcp_server_blocks(config_text, disabled_session_surfaces=None):
    """Compatibility wrapper for disabled Codex MCP block stripping."""
    from mms_codex_claude_state import strip_codex_mcp_server_blocks

    return strip_codex_mcp_server_blocks(config_text, disabled_session_surfaces)


def _append_codex_mcp_servers_from_claude_json(config_text, *, disabled_session_surfaces=None):
    """Compatibility wrapper for Claude MCP -> Codex config rendering."""
    from mms_codex_claude_state import append_codex_mcp_servers_from_claude_json

    return append_codex_mcp_servers_from_claude_json(
        config_text,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def validate_account_for_cli(cli, account):
    """Compatibility wrapper for account launch validation."""
    from mms_runtime_validation import validate_account_for_cli as validate_account_for_cli_impl

    return validate_account_for_cli_impl(cli, account)


def _openai_base_url(provider):
    """Compatibility wrapper for effective OpenAI base URL."""
    from mms_runtime_urls import openai_base_url

    return openai_base_url(provider)


def _anthropic_base_url(provider):
    """Compatibility wrapper for effective Anthropic base URL."""
    from mms_runtime_urls import anthropic_base_url

    return anthropic_base_url(provider)


def _anthropic_probe_target(runtime):
    """Compatibility wrapper for Anthropic probe target derivation."""
    from mms_runtime_urls import anthropic_probe_target

    return anthropic_probe_target(runtime)


def _resolve_model(model_info):
    """Compatibility wrapper for runtime model extraction."""
    from mms_runtime_models import resolve_model

    return resolve_model(model_info)


def _normalized_model_name(model_name):
    """Compatibility wrapper for model-name normalization."""
    from mms_runtime_models import normalized_model_name

    return normalized_model_name(model_name)


def _strip_one_m_context_suffix(model_name):
    """Compatibility wrapper for Claude 1M suffix stripping."""
    from mms_claude_model import strip_one_m_context_suffix

    return strip_one_m_context_suffix(model_name)


def _is_claude_family_model_name(model_name):
    """Compatibility wrapper for Claude family model detection."""
    from mms_claude_model import is_claude_family_model_name

    return is_claude_family_model_name(model_name)


def _is_mimo_one_m_context_selector(model_name):
    """Compatibility wrapper for MiMo 1M selector detection."""
    from mms_claude_model import is_mimo_one_m_context_selector

    return is_mimo_one_m_context_selector(model_name)


def _claude_visible_model_name(model_name, *, fallback_model=""):
    """Compatibility wrapper for Claude-visible model slot names."""
    from mms_claude_model import claude_visible_model_name

    return claude_visible_model_name(model_name, fallback_model=fallback_model)


def _apply_claude_visible_model_overrides(target, model_name, *, fallback_model=""):
    """Compatibility wrapper for Claude-visible model overrides."""
    from mms_claude_model import apply_claude_visible_model_overrides

    return apply_claude_visible_model_overrides(target, model_name, fallback_model=fallback_model)


def _claude_resume_model_name(*candidates):
    """Compatibility wrapper for Claude resume model normalization."""
    from mms_claude_model import claude_resume_model_name

    return claude_resume_model_name(*candidates)


def _primary_claude_model(model_info):
    """Compatibility wrapper for Claude primary model selection."""
    from mms_claude_model import primary_claude_model

    return primary_claude_model(model_info)


def _with_1m_suffix(model_name, *, enable_1m=True):
    """Compatibility wrapper for Claude 1M model suffixing."""
    from mms_claude_model import with_1m_suffix

    return with_1m_suffix(model_name, enable_1m=enable_1m)


def _apply_claude_model_overrides(target, model_info, *, enable_1m=True):
    """Compatibility wrapper for Claude model env overrides."""
    from mms_claude_model import apply_claude_model_overrides

    return apply_claude_model_overrides(target, model_info, enable_1m=enable_1m)


def launch_claude(model_info, runtime, once=False, extra_args=None):
    """Compatibility wrapper for the Claude launch flow."""
    from mms_claude_launch import launch_claude_runtime

    return launch_claude_runtime(
        model_info,
        runtime,
        once=once,
        extra_args=extra_args,
    )



def _resolve_anthropic_base_url(runtime, probe_model="claude-sonnet-4-6"):
    """Compatibility wrapper for Claude Anthropic endpoint resolution."""
    from mms_claude_endpoint import resolve_anthropic_base_url

    return resolve_anthropic_base_url(runtime, probe_model=probe_model)


def _pick_gateway_model(runtime, base_url):
    """Compatibility wrapper for Claude gateway model selection."""
    from mms_claude_endpoint import pick_gateway_model

    return pick_gateway_model(runtime, base_url)


def _cleanup_stale_sessions(sessions_dir, stale_callback=None, *, max_entries=None, max_seconds=None):
    """Compatibility wrapper for Claude stale session cleanup."""
    from mms_claude_session import cleanup_stale_sessions

    return cleanup_stale_sessions(
        sessions_dir,
        stale_callback=stale_callback,
        max_entries=max_entries,
        max_seconds=max_seconds,
    )


def _copy_tree_files_if_missing(src, dst):
    """Compatibility wrapper for Claude session tree backfill copies."""
    from mms_claude_session import copy_tree_files_if_missing

    return copy_tree_files_if_missing(src, dst)


def _normalized_claude_slot_account(value):
    """Compatibility wrapper for Claude slot account normalization."""
    from mms_claude_session import normalized_claude_slot_account

    return normalized_claude_slot_account(value)


def _claude_project_resume_dir_names(project_path):
    """Compatibility wrapper for Claude project resume dir names."""
    from mms_claude_session import claude_project_resume_dir_names

    return claude_project_resume_dir_names(project_path)


def _claude_slot_roots_for_resume_backfill(account_id):
    """Compatibility wrapper for Claude resume backfill roots."""
    from mms_claude_session import claude_slot_roots_for_resume_backfill

    return claude_slot_roots_for_resume_backfill(account_id)


def _backfill_real_claude_project_resume_files(target_projects_dir, current_cwd):
    """Compatibility wrapper for real Claude project resume backfill."""
    from mms_claude_session import backfill_real_claude_project_resume_files

    return backfill_real_claude_project_resume_files(target_projects_dir, current_cwd)


def _backfill_claude_project_resume_files(target_projects_dir, current_cwd, account_id, current_session_home=""):
    """Compatibility wrapper for Claude project resume backfill."""
    from mms_claude_session import backfill_claude_project_resume_files

    return backfill_claude_project_resume_files(
        target_projects_dir,
        current_cwd,
        account_id,
        current_session_home=current_session_home,
    )


def _link_claude_persistent_entry(session_claude_dir, entry, target):
    """Compatibility wrapper for Claude persistent entry links."""
    from mms_claude_session import link_claude_persistent_entry

    return link_claude_persistent_entry(session_claude_dir, entry, target)


def _prepare_claude_session_tree(
    session_home,
    session_claude_dir,
    *,
    account_id="",
    account_home="",
    runtime_kind="api_key",
    resume_model="",
    skip_real_entries=None,
    source_claude_dir=None,
    allowed_source_entries=None,
):
    """Compatibility wrapper for Claude session tree materialization."""
    from mms_claude_session import prepare_claude_session_tree

    return prepare_claude_session_tree(
        session_home,
        session_claude_dir,
        account_id=account_id,
        account_home=account_home,
        runtime_kind=runtime_kind,
        resume_model=resume_model,
        skip_real_entries=skip_real_entries,
        source_claude_dir=source_claude_dir,
        allowed_source_entries=allowed_source_entries,
    )


def _sync_claude_session_state_to_account_home(session_home, account_home, *, state_mode="oauth"):
    """Compatibility wrapper for Claude session state sync."""
    from mms_claude_session import sync_claude_session_state_to_account_home

    return sync_claude_session_state_to_account_home(
        session_home,
        account_home,
        state_mode=state_mode,
    )


def _finalize_claude_slot(session_home, exit_code=None, stale_cleanup=False):
    """Compatibility wrapper for Claude slot finalization."""
    from mms_claude_session import finalize_claude_slot

    return finalize_claude_slot(session_home, exit_code=exit_code, stale_cleanup=stale_cleanup)


def _claude_gateway_env(
    runtime,
    base_url=None,
    auth_token=None,
    heavy_model=None,
    medium_model=None,
    light_model=None,
    selected_model=None,
    runtime_kind=None,
    display_model=None,
    _timings=None,
):
    """Compatibility wrapper for Claude gateway env materialization."""
    from mms_claude_env import build_claude_gateway_env

    return build_claude_gateway_env(
        runtime,
        base_url=base_url,
        auth_token=auth_token,
        heavy_model=heavy_model,
        medium_model=medium_model,
        light_model=light_model,
        selected_model=selected_model,
        runtime_kind=runtime_kind,
        display_model=display_model,
        _timings=_timings,
    )



def _codex_gateway_env(runtime, base_url, model_info=None):
    """Compatibility wrapper for Codex gateway env materialization."""
    from mms_codex_env import build_codex_gateway_env

    return build_codex_gateway_env(runtime, base_url, model_info=model_info)

def _is_gpt_model(model_name):
    """Check if a model name is a GPT/OpenAI model (supports Responses API natively)."""
    if not model_name:
        return False
    lower = model_name.lower()
    return any(kw in lower for kw in ("gpt-", "gpt4", "gpt5", "o1", "o3", "o4", "codex-"))


def _codex_provider_base_url(base_url):
    normalized = (base_url or "").rstrip("/")
    if normalized and not normalized.endswith("/v1"):
        normalized += "/v1"
    return normalized


def _append_codex_bypass_flags(cmd, runtime):
    """In MMS bypass mode, skip Codex approval and hook-review prompts together."""
    # Contract: isolated MMS/Codex sessions must not stop at startup hook review.
    if not (runtime or {}).get("bypass"):
        return
    for flag in (
        "--dangerously-bypass-approvals-and-sandbox",
        "--dangerously-bypass-hook-trust",
    ):
        if flag not in cmd:
            cmd.append(flag)


def launch_codex(model_info, runtime, once=False, extra_args=None):
    """Compatibility wrapper for the Codex launch flow."""
    from mms_codex_launch import launch_codex_runtime

    return launch_codex_runtime(
        model_info,
        runtime,
        once=once,
        extra_args=extra_args,
    )



def _opencode_run_preflight(env, agent, model_ref, timeout=None, bypass=True):
    return _opencode_run_preflight_impl(
        env,
        agent,
        model_ref,
        timeout=timeout,
        bypass=bypass,
        subprocess_run=subprocess.run,
        perf_counter_fn=perf_counter,
        preflight_timeout=_opencode_preflight_timeout,
    )


def _opencode_select_launch_candidate(runtime, routes, model, env):
    return _opencode_select_launch_candidate_impl(
        runtime,
        routes,
        model,
        env,
        launch_candidates=_opencode_launch_candidates,
        launch_preflight_enabled=_opencode_launch_preflight_enabled,
        run_preflight=_opencode_run_preflight,
        bypass_enabled=_opencode_bypass_enabled,
        console=console,
    )


def _opencode_gateway_health_check(runtime):
    return _opencode_gateway_health_check_impl(
        runtime,
        runtime_routes=_opencode_runtime_routes,
        resolve_model=_resolve_model,
        provider_base_url=_opencode_provider_base_url,
        gateway_health_check=gateway_health_check,
    )


def _opencode_model_config(runtime, model_name):
    return _opencode_model_config_impl(
        runtime,
        model_name,
        context_window_resolver=_effective_context_window,
    )


def _opencode_rtk_plugin_path(runtime=None):
    return _opencode_rtk_plugin_path_impl(
        runtime,
        module_file=__file__,
        normalize_session_surface_disabled=_normalize_session_surface_disabled,
        runtime_bool=_opencode_runtime_bool,
        env_bool=_opencode_env_bool,
    )


def _opencode_xmem_plugin_path(runtime=None):
    return _opencode_xmem_plugin_path_impl(
        runtime,
        module_file=__file__,
        normalize_session_surface_disabled=_normalize_session_surface_disabled,
        session_skill_disabled=_session_skill_disabled,
        resolve_xmem_root=_resolve_xmem_root,
        xmem_cli_path=_xmem_cli_path,
    )


def _overlay_opencode_rtk_plugin(config_dir, runtime=None):
    return _overlay_opencode_plugin_impl(
        config_dir,
        _opencode_rtk_plugin_path(runtime),
        "mms-rtk.ts",
    )


def _overlay_opencode_xmem_plugin(config_dir, runtime=None):
    return _overlay_opencode_plugin_impl(
        config_dir,
        _opencode_xmem_plugin_path(runtime),
        "mms-xmem.ts",
    )


def _opencode_rtk_plugin_enabled(runtime=None):
    return bool(_opencode_rtk_plugin_path(runtime))


def _opencode_xmem_plugin_enabled(runtime=None):
    return bool(_opencode_xmem_plugin_path(runtime))


def _build_opencode_config_payload(runtime, model_name=""):
    return _opencode_build_config_payload_impl(
        runtime,
        model_name,
        context_window_resolver=_effective_context_window,
    )


def _build_opencode_config_content(runtime, model_name=""):
    return _opencode_build_config_content_impl(
        runtime,
        model_name,
        context_window_resolver=_effective_context_window,
    )


def _write_opencode_config(path, runtime, model):
    return _opencode_write_config_impl(
        path,
        runtime,
        model,
        build_config_content=_build_opencode_config_content,
        atomic_write_text=atomic_write_text,
    )


def _opencode_export_config_path(runtime, model):
    return _opencode_export_config_path_impl(
        runtime,
        model,
        real_user_path=_real_user_path,
    )


def _opencode_gateway_env(runtime, model_info=None):
    return _opencode_gateway_env_impl(
        runtime,
        model_info=model_info,
        resolve_model=_resolve_model,
        real_user_path=_real_user_path,
        cleanup_stale_sessions=_cleanup_stale_sessions,
        link_shared_dotfiles=_link_shared_dotfiles,
        scrub_inherited_runtime_env=_scrub_inherited_runtime_env,
        clear_opencode_config_env=_clear_opencode_config_env,
        inject_real_home_hints=_inject_real_home_hints,
        inject_selected_model_name=_inject_selected_model_name,
        set_opencode_soft_home=_set_opencode_soft_home,
        write_opencode_config=_write_opencode_config,
        overlay_opencode_session_assets=_overlay_opencode_session_assets,
        apply_route_env=_opencode_apply_route_env,
        apply_bypass_env=_opencode_apply_bypass_env,
        apply_runtime_network_profile=_apply_runtime_network_profile,
        apply_runtime_locale_profile=_apply_runtime_locale_profile,
        apply_runtime_ip_stack_profile=_apply_runtime_ip_stack_profile,
        install_session_command_wrappers=_install_session_command_wrappers,
        install_session_packet_env=_install_session_packet_env,
        runtime_caveman_enabled=_runtime_caveman_enabled,
        resolve_web_access_root=_resolve_web_access_root,
        resolve_weber_root=_resolve_weber_root,
        resolve_toon_root=_resolve_toon_root,
        resolve_token_saver_root=_resolve_token_saver_root,
        resolve_xmem_root=_resolve_xmem_root,
        session_skill_disabled=_session_skill_disabled,
        opencode_rtk_plugin_enabled=_opencode_rtk_plugin_enabled,
        opencode_xmem_plugin_enabled=_opencode_xmem_plugin_enabled,
    )


def _opencode_global_omo_env(runtime):
    return _opencode_global_omo_env_impl(
        runtime,
        clear_opencode_config_env=_clear_opencode_config_env,
        inject_real_home_hints=_inject_real_home_hints,
        real_user_path=_real_user_path,
        apply_bypass_env=_opencode_apply_bypass_env,
        apply_runtime_network_profile=_apply_runtime_network_profile,
        apply_runtime_locale_profile=_apply_runtime_locale_profile,
        apply_runtime_ip_stack_profile=_apply_runtime_ip_stack_profile,
    )


def _opencode_global_command(runtime, entrypoint):
    return _opencode_global_command_impl(runtime, entrypoint)


def _opencode_session_command(runtime, entrypoint, launch_model_ref, launch_agent):
    return _opencode_session_command_impl(
        runtime,
        entrypoint,
        launch_model_ref,
        launch_agent,
        default_agent=OPENCODE_LITE_DEFAULT_AGENT,
    )


def launch_opencode(model_info, runtime, once=False):
    """启动 OpenCode，通过 OpenAI-compatible provider 注入 session-local config。"""
    return _opencode_launch_impl(
        model_info,
        runtime,
        once=once,
        entrypoint=_opencode_entrypoint,
        global_omo_env=_opencode_global_omo_env,
        global_command=_opencode_global_command,
        exec_or_run=_exec_or_run,
        gateway_health_check=_opencode_gateway_health_check,
        resolve_model=_resolve_model,
        runtime_routes=_opencode_runtime_routes,
        gateway_env=_opencode_gateway_env,
        select_launch_candidate=_opencode_select_launch_candidate,
        console=console,
        sys_exit=sys.exit,
        inject_selected_model_name=_inject_selected_model_name,
        install_session_packet_env=_install_session_packet_env,
        session_command=_opencode_session_command,
    )


def launch_gemini(model_info, runtime, once=False):
    """启动 Gemini，当前只支持官方账号档案模式。"""
    auth_mode = runtime.get("auth_mode", "api_key")
    if auth_mode != "oauth":
        console.print("[red]Gemini 当前只支持官方账号入口，不支持直接使用模型源启动[/red]")
        sys.exit(1)

    env = _account_env(runtime, model_info=model_info)
    _prepare_oauth_home_context(runtime, env, "gemini")
    model = _resolve_model(model_info)
    cmd = ["gemini"]
    if model:
        cmd += ["-m", model]
    _exec_or_run(cmd, env, once)


def launch_agy(model_info, runtime, once=False):
    """启动 Antigravity CLI，当前只支持官方账号档案模式。"""
    auth_mode = runtime.get("auth_mode", "api_key")
    if auth_mode != "oauth":
        console.print("[red]Antigravity CLI 当前只支持官方账号入口，不支持直接使用模型源启动[/red]")
        sys.exit(1)

    env = _account_env(runtime, model_info=model_info)
    _prepare_oauth_home_context(runtime, env, "agy")
    cmd = ["agy"]
    if runtime.get("bypass"):
        cmd.append("--dangerously-skip-permissions")
    if runtime.get("agy_sandbox") or runtime.get("sandbox"):
        cmd.append("--sandbox")
    _exec_or_run(cmd, env, once)


LAUNCHERS = {
    "claude": launch_claude,
    "codex": launch_codex,
    "opencode": launch_opencode,
    "gemini": launch_gemini,
    "agy": launch_agy,
}


def _is_opencode_global_profile_runtime(cli, runtime):
    return _opencode_is_global_profile_runtime_impl(cli, runtime)


def _opencode_global_export_env(runtime):
    return _opencode_global_export_env_impl(
        runtime,
        apply_bypass_env=_opencode_apply_bypass_env,
    )


def _opencode_provider_export_env(runtime, model):
    return _opencode_provider_export_env_impl(
        runtime,
        model,
        export_config_path=_opencode_export_config_path,
        write_opencode_config=_write_opencode_config,
        apply_route_env=_opencode_apply_route_env,
        apply_bypass_env=_opencode_apply_bypass_env,
    )


def get_export_env(cli, runtime):
    """返回指定 CLI 需要的 export 环境变量字典。"""
    from mms_launcher_export import build_export_env

    return build_export_env(
        cli,
        runtime,
        is_opencode_global_profile_runtime=_is_opencode_global_profile_runtime,
        opencode_global_export_env=_opencode_global_export_env,
        validate_account_for_cli=validate_account_for_cli,
        validate_provider_for_cli=validate_provider_for_cli,
        anthropic_base_url=_anthropic_base_url,
        openai_base_url=_openai_base_url,
        resolve_model=_resolve_model,
        opencode_provider_export_env=_opencode_provider_export_env,
        inject_host_capability_hints=_inject_host_capability_hints,
        mms_toon_script_path=_mms_toon_script_path,
        mms_context_script_path=_mms_context_script_path,
        token_saver_script_path=_token_saver_script_path,
        xmem_cli_path=_xmem_cli_path,
        safe_getcwd=_safe_getcwd,
    )


def _show_launch_info(cli, runtime, auth_mode):
    """Compatibility wrapper for launch-time display."""
    from mms_launch_display import show_launch_info

    return show_launch_info(cli, runtime, auth_mode)


def launch_cli(cli, model_info, runtime, once=False, extra_args=None):
    """统一启动入口"""
    runtime = dict(runtime)
    launcher = LAUNCHERS.get(cli)
    if not launcher:
        console.print(f"[red]不支持的 CLI: {cli}[/red]")
        sys.exit(1)
    auth_mode = runtime.get("auth_mode", "api_key")
    if auth_mode == "oauth_bridge":
        source_label = runtime.get("name", runtime.get("id", "account"))
        source_kind = "官方桥接"
    elif auth_mode == "oauth":
        validate_account_for_cli(runtime.get("cli", cli), runtime)
        source_label = runtime.get("name", runtime.get("id", "account"))
        source_kind = "账号档案"
    elif _is_opencode_global_profile_runtime(cli, runtime):
        source_label = runtime.get("name", runtime.get("id", "global-opencode-omo"))
        source_kind = "OpenCode 全局配置"
    else:
        validate_provider_for_cli(cli, runtime)
        source_label = runtime.get("name", runtime.get("id", "provider"))
        source_kind = "模型源"

    if cli == "claude" and auth_mode == "oauth":
        # OAuth Claude 已下线为 standalone 入口；MMS 不再读取或判定其并发 state。
        runtime.pop("_account_guard_report", None)
    if cli == "claude" and auth_mode in {"oauth", "api_key"} and runtime.get("bypass"):
        _enforce_claude_network_guard_or_exit(
            runtime,
            require_proxy=_claude_bypass_requires_proxy(runtime),
        )

    model_display = _resolve_model(model_info) if not isinstance(model_info, dict) else \
        model_info.get("model", model_info.get("sonnet", "多模型配置"))

    if cli == "claude" and auth_mode == "oauth":
        _exit_oauth_claude_manual_only(runtime, model_info, caller="launch_cli")
    if cli == "claude" and auth_mode == "api_key":
        prefetched_probe = None
        try:
            with _launch_status("预读取模型列表中...", spinner="dots") as step_start:
                prefetched_probe = _probe_models(runtime, emit_output=False)
            models = list((prefetched_probe or {}).get("models") or [])
            detail = f"{len(models)} 个模型"
            base_source = (prefetched_probe or {}).get("base_source")
            if base_source:
                detail += f" · {base_source}"
            _print_launch_step_done("启动前模型预读取", step_start, detail)
        except Exception:
            console.print("[yellow]· 启动前模型预读取失败，后续继续按默认流程处理[/yellow]")
        runtime["_launch_prefetched_probe"] = prefetched_probe

    console.print(f"\n[bold green]🚀 启动 {cli}[/bold green] — {model_display}")
    console.print(f"[dim]{source_kind}: {source_label} ({runtime.get('id', 'default')})[/dim]")
    console.print(f"[dim]认证方式: {auth_mode}[/dim]")
    _show_launch_info(cli, runtime, auth_mode)
    console.print("[dim]─" * 40 + "[/dim]\n")

    if extra_args:
        launcher(model_info, runtime, once=once, extra_args=list(extra_args))
    else:
        launcher(model_info, runtime, once=once)


def _write_runtime_config(prefix, content):
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".toml", dir=RUNTIME_DIR)
    os.chmod(path, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _print_session_summary(bridge_info):
    """退出时打印 session 摘要：时长、请求数、token 用量。"""
    if not bridge_info or not isinstance(bridge_info, dict):
        return
    server = bridge_info.get("_server")
    if not server or not hasattr(server, "session_request_count"):
        return
    reqs = getattr(server, "session_request_count", 0)
    if reqs == 0:
        return
    inp = getattr(server, "session_input_tokens", 0)
    out = getattr(server, "session_output_tokens", 0)
    start = getattr(server, "session_start_time", 0)
    import time
    elapsed = time.time() - start if start else 0
    # 格式化时长
    if elapsed >= 3600:
        dur = f"{int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m"
    elif elapsed >= 60:
        dur = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
    else:
        dur = f"{int(elapsed)}s"
    # 格式化 token
    def _fmt_tokens(n):
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}K"
        return str(n)
    model = getattr(server, "heavy_model", None) or getattr(server, "model_name", "?")
    parts = [dur, model, f"{reqs} reqs"]
    if inp or out:
        parts.append(f"{_fmt_tokens(inp)} in + {_fmt_tokens(out)} out")
    try:
        print(f"\n\033[2m[MMS] {' · '.join(parts)}\033[0m")
    except Exception:
        pass


def _exec_or_run(
    cmd,
    env,
    once,
    cleanup_path=None,
    state_home=None,
    cleanup_context=None,
    exit_callback=None,
    force_subprocess=False,
    bridge_info=None,
):
    """默认用 execvp；需要清理临时文件时回退到 subprocess。"""
    cmd, env, exe = prepare_cli_command(cmd, env)
    if not exe:
        console.print(f"[red]{cmd[0]} 未找到，请先安装[/red]")
        sys.exit(1)
    session_home = str((env or {}).get("MMS_SESSION_HOME") or "").strip()

    if once or cleanup_path or state_home or cleanup_context or exit_callback or force_subprocess:
        exit_code = None
        child = None
        try:
            if state_home:
                with activated_claude_account_state(state_home):
                    child = subprocess.Popen(cmd, env=env)
                    if session_home:
                        _record_session_child_pid(session_home, child.pid)
                    exit_code = child.wait()
            else:
                child = subprocess.Popen(cmd, env=env)
                if session_home:
                    _record_session_child_pid(session_home, child.pid)
                exit_code = child.wait()
        except KeyboardInterrupt:
            if child is not None:
                try:
                    exit_code = child.wait(timeout=5)
                except Exception:
                    exit_code = 130
            if exit_code is None:
                exit_code = 130
        finally:
            if exit_callback is not None:
                try:
                    exit_callback(exit_code)
                except Exception:
                    pass
            if cleanup_path and os.path.exists(cleanup_path):
                try:
                    os.remove(cleanup_path)
                except OSError:
                    pass
            if cleanup_context is not None:
                try:
                    cleanup_context.__exit__(None, None, None)
                except (KeyboardInterrupt, Exception):
                    pass
            _print_session_summary(bridge_info)
        sys.exit(exit_code or 0)
    else:
        os.execvpe(exe, cmd, env)
