"""MMS 启动器：按 provider 或账号档案启动四个 CLI。"""

from contextlib import contextmanager
import copy
import inspect
import json
import os
import shutil
import sys
import subprocess
import tempfile
from datetime import datetime, timezone
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from mms_account_state import activated_claude_account_state, seed_claude_state, seed_gemini_state
from mms_i18n import normalize_language
from mms_core import (
    DEFAULT_ACCOUNT_TIMEZONE,
    _normalize_claude_1m_mode,
    _probe_models,
    _runtime_force_ipv4,
    _runtime_httpx_request,
    detect_working_base_url,
)
from mms_fake_upstream import (
    ensure_local_proxy as _ensure_fake_upstream_proxy,
    fake_proxy_probe as _fake_proxy_probe,
    is_enabled as _fake_upstream_enabled,
    status_payload as _fake_upstream_status_payload,
)
from mms_project_store import CLAUDE_PERSISTENT_ENTRIES, claude_raw_entry_path, ensure_claude_project_store, read_slot_marker, write_slot_marker
from mms_session_index import finalize_claude_session, list_indexed_sessions, record_claude_session_start
from mms_state_io import atomic_write_json, locked_state_file

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

# ── 已知模型的 context window（tokens）──
# 用于设置 CLAUDE_CODE_AUTO_COMPACT_WINDOW，使 Claude Code 按实际模型 context 触发 compact。
# 来源：各厂商官方 API 文档 / OpenRouter / HuggingFace，2026-03 更新。
_MODEL_CONTEXT_WINDOWS = {
    # Claude — 标准 200k，[1m] 变体由 Claude Code 内部处理
    "claude-opus-4-6": 1_000_000,
    "claude-sonnet-4-6": 1_000_000,
    "claude-haiku-4-5-20251001": 200_000,
    "claude-haiku-4-5": 200_000,
    # Kimi — kimi-k2.5 系列均为 256K (262144)
    "kimi-for-coding": 262_144,
    "kimi-k2.5": 262_144,
    # Qwen — hosted plus/coder-plus/3.6-plus 支持 1M；qwen3-max 为 262K
    "qwen3.5-plus": 1_000_000,
    "qwen3.6-plus": 1_000_000,
    "qwen3-coder-plus": 1_000_000,
    "qwen3-max": 262_144,
    # GLM — 全系 200K
    "glm-5": 200_000,
    "glm-5-turbo": 200_000,
    "glm-5.1": 200_000,
    "glm-4.7": 200_000,
    # MiniMax / MiMo — 已确认 mimo-v2-pro 为 1M；M2.5 为 196K，M2.7 为 200K
    "mimo-v2-pro": 1_000_000,
    "MiniMax-M2.5": 196_608,
    "MiniMax-M2.7": 200_000,
    # GPT-5 系列 — 大部分 1M，nano 256K
    "gpt-5": 1_000_000,
    "gpt-5-mini": 1_000_000,
    "gpt-5-nano": 256_000,
    "gpt-5-codex": 1_000_000,
    "gpt-5.1-codex": 1_000_000,
    "gpt-5.1-codex-max": 1_000_000,
    "gpt-5.1-codex-mini": 1_000_000,
    "gpt-5.2": 1_000_000,
    "gpt-5.2-codex": 1_000_000,
    "gpt-5.3-codex": 1_000_000,
    "gpt-5.3-codex-spark": 1_000_000,
    "gpt-5.4": 1_000_000,
    "gpt-5.4-pro": 1_000_000,
}
_DEFAULT_CONTEXT_WINDOW = 200_000  # 未知模型的安全默认值


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
    try:
        window = int(value)
    except Exception:
        return None
    return window if window > 0 else None


def _load_model_context_overrides():
    try:
        mtime = os.path.getmtime(_MODEL_CONTEXT_OVERRIDES_PATH)
    except OSError:
        _MODEL_CONTEXT_OVERRIDES_CACHE["mtime"] = None
        _MODEL_CONTEXT_OVERRIDES_CACHE["data"] = {"models": {}, "provider_overrides": {}}
        return _MODEL_CONTEXT_OVERRIDES_CACHE["data"]

    if _MODEL_CONTEXT_OVERRIDES_CACHE["mtime"] == mtime:
        return _MODEL_CONTEXT_OVERRIDES_CACHE["data"]

    models = {}
    provider_overrides = {}
    try:
        with open(_MODEL_CONTEXT_OVERRIDES_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        payload = {}

    if isinstance(payload, dict):
        raw_models = payload.get("models", payload)
        if isinstance(raw_models, dict):
            for key, value in raw_models.items():
                if key in {"models", "provider_overrides"}:
                    continue
                window = _coerce_context_window(value)
                if window:
                    models[str(key).strip()] = window

        raw_provider_overrides = payload.get("provider_overrides", {})
        if isinstance(raw_provider_overrides, dict):
            for key, value in raw_provider_overrides.items():
                if isinstance(value, dict):
                    provider_id = str(key or "").strip()
                    if not provider_id:
                        continue
                    for model_id, window_value in value.items():
                        window = _coerce_context_window(window_value)
                        if window:
                            provider_overrides[f"{provider_id}:{str(model_id).strip()}"] = window
                else:
                    window = _coerce_context_window(value)
                    if window:
                        provider_overrides[str(key).strip()] = window

    _MODEL_CONTEXT_OVERRIDES_CACHE["mtime"] = mtime
    _MODEL_CONTEXT_OVERRIDES_CACHE["data"] = {
        "models": models,
        "provider_overrides": provider_overrides,
    }
    return _MODEL_CONTEXT_OVERRIDES_CACHE["data"]


def _lookup_context_window(model_name, provider_id=None):
    clean = str(model_name or "").replace("[1m]", "").strip()
    if not clean:
        return None

    provider_key = str(provider_id or "").strip()
    lower = clean.lower()
    overrides = _load_model_context_overrides()

    if provider_key:
        provider_overrides = overrides.get("provider_overrides", {})
        direct = provider_overrides.get(f"{provider_key}:{clean}")
        if direct is not None:
            return direct
        for key, value in provider_overrides.items():
            try:
                override_provider, override_model = key.split(":", 1)
            except ValueError:
                continue
            if override_provider == provider_key and override_model.lower() == lower:
                return value

    models = overrides.get("models", {})
    direct = models.get(clean)
    if direct is not None:
        return direct
    for key, value in models.items():
        if key.lower() == lower:
            return value

    direct = _MODEL_CONTEXT_WINDOWS.get(clean)
    if direct is not None:
        return direct
    for key, value in _MODEL_CONTEXT_WINDOWS.items():
        if key.lower() == lower:
            return value
    return None

def _runtime_supports_claude_1m(runtime):
    explicit = _normalize_claude_1m_mode((runtime or {}).get("claude_1m_mode", "auto"))
    if explicit == "enable":
        return True
    if explicit == "disable":
        return False
    provider_id = str((runtime or {}).get("id", "")).strip().lower()
    disabled_ids = _provider_id_set_from_env("MMS_CLAUDE_DISABLE_1M_PROVIDER_IDS")
    if provider_id and provider_id in disabled_ids:
        return False
    return not _runtime_declares_sensitive_claude(runtime)


def _runtime_is_sensitive_claude_provider(runtime):
    provider_id = str((runtime or {}).get("id", "")).strip().lower()
    sensitive_ids = _provider_id_set_from_env("MMS_CLAUDE_SENSITIVE_PROVIDER_IDS")
    return (provider_id and provider_id in sensitive_ids) or _runtime_declares_sensitive_claude(runtime)


def _effective_context_window(*models, enable_claude_1m=True, provider_id=None):
    """取所有活跃模型中最小的 context window。
    智能路由场景下 heavy/medium/light 可能是不同模型，
    conversation context 必须 fit 最小的那个。
    """
    windows = []
    for m in models:
        if not m:
            continue
        clean = m.replace("[1m]", "").strip()
        w = _lookup_context_window(clean, provider_id=provider_id)
        if not enable_claude_1m:
            lower = clean.lower()
            if lower.startswith("claude-") and "haiku" not in lower:
                w = 200_000
        windows.append(w or _DEFAULT_CONTEXT_WINDOW)
    return min(windows) if windows else _DEFAULT_CONTEXT_WINDOW


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


def _prepare_claude_env_with_status(runtime, **kwargs):
    with _launch_status("准备 Claude 会话环境中...", spinner="dots") as step_start:
        env = _claude_gateway_env(runtime, **kwargs)
    selected = kwargs.get("selected_model") or kwargs.get("heavy_model")
    detail = selected if selected else runtime.get("id", "provider")
    _print_launch_step_done("Claude 会话环境准备", step_start, detail)
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
    real_home = _real_user_home()
    env["MMS_REAL_HOME"] = real_home
    env["ORIGINAL_HOME"] = real_home
    env["REAL_HOME"] = real_home
    env["GH_CONFIG_DIR"] = _real_user_path(".config", "gh")
    if include_xdg:
        env["XDG_CONFIG_HOME"] = _real_user_path(".config")
    return env


def _set_session_home_hint(env, session_home):
    if session_home:
        env["MMS_SESSION_HOME"] = session_home
    return env


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


def _reserve_session_home(
    sessions_dir,
    *,
    account_id="",
    runtime_kind="",
    stale_callback=None,
    max_live_sessions=None,
):
    sessions_dir = str(sessions_dir or "").strip()
    if not sessions_dir:
        return "", 0, 0
    os.makedirs(sessions_dir, exist_ok=True)
    session_home = os.path.join(sessions_dir, str(os.getpid()))
    with locked_state_file(_session_guard_lock_path(sessions_dir)):
        _cleanup_stale_sessions(sessions_dir, stale_callback=stale_callback)
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
    return [
        'for _mms_var in $(env | cut -d= -f1); do',
        '  case "$_mms_var" in',
        '    ANTHROPIC_*|CLAUDE_CODE_*|OPENAI_*|HTTP_PROXY|HTTPS_PROXY|ALL_PROXY|NO_PROXY|http_proxy|https_proxy|all_proxy|no_proxy|MMS_FAKE_UPSTREAM_*|NODE_EXTRA_CA_CERTS|SSL_CERT_FILE|REQUESTS_CA_BUNDLE)',
        '      unset "$_mms_var" ;;',
        '  esac',
        'done',
        'unset _mms_var',
    ]


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
    expected_session_home = auth_mode == "oauth" and cli_name in {"claude", "codex"}
    config_root = os.path.join(real_home, ".config", "mms") if real_home else _real_user_path(".config", "mms")
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
        if cli_name == "codex":
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
    if cli_name not in {"claude", "codex", "gemini"}:
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
    "qwen": "openai_chat_completions",
    "kimi": "openai_chat_completions",
}
OAUTH_CAPABLE_CLIS = {"claude", "codex", "gemini"}

# agent-im daemon 路径（仅在显式配置时启用，避免公开仓库绑定个人目录）
_AGENT_IM_DIR = os.path.realpath(str(os.environ.get("MMS_AGENT_IM_DIR") or "").strip()) if str(os.environ.get("MMS_AGENT_IM_DIR") or "").strip() else ""
_AGENT_IM_SOCK = _real_user_path(".agent-im", "agent-im.sock")
_LOCAL_STATUSLINE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "statusline-command.sh")
_LOCAL_HOOKS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hooks")
_CLAUDE_FEISHU_WEBFETCH_GUARD_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "claude-feishu-webfetch-guard.sh")

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
    "hive",
    "mindkeeper",
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
    "gh",
    "lark-cli",
    "hive",
    "pm2",
    "npm",
    "pnpm",
    "npx",
    "yarn",
    "corepack",
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
    return _load_claude_settings_from_dir(_real_user_path(".claude"))


def _load_claude_settings_from_dir(claude_dir):
    import json as _json

    settings_path = os.path.join(str(claude_dir), "settings.json")
    if not os.path.exists(settings_path):
        return {}
    try:
        with open(settings_path, encoding="utf-8") as f:
            loaded = _json.load(f)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _load_claude_settings_template(filename):
    import json as _json

    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if not os.path.exists(template_path):
        return {}
    try:
        with open(template_path, encoding="utf-8") as f:
            loaded = _json.load(f)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _load_mms_claude_settings_template():
    return _load_claude_settings_template("claude-settings.template.json")


def _load_global_claude_settings_template():
    return _load_claude_settings_template("claude-settings.global-template.json")


def _global_claude_snapshot_path():
    state_root = os.environ.get("MMS_HOME") or os.path.join(_real_user_path(".mms"), "state")
    return os.path.join(state_root, "claude-global-managed-snapshot.json")


def _normalize_hook_command(command):
    return " ".join(str(command or "").strip().split())


def _extract_managed_claude_snapshot(settings_data, template_settings):
    settings_data = settings_data if isinstance(settings_data, dict) else {}
    template_settings = template_settings if isinstance(template_settings, dict) else {}
    snapshot = {}

    managed_scalar_keys = set(
        [
            "includeCoAuthoredBy",
            "skipDangerousModePermissionPrompt",
            "model",
            "promptSuggestionEnabled",
        ]
    )
    if isinstance(template_settings.get("statusLine"), dict):
        managed_scalar_keys.add("statusLine")
    if isinstance(template_settings.get("attribution"), dict):
        managed_scalar_keys.add("attribution")
    if isinstance(template_settings.get("permissions"), dict):
        managed_scalar_keys.add("permissions")

    for key in managed_scalar_keys:
        value = settings_data.get(key)
        if isinstance(value, dict):
            snapshot[key] = dict(value)
        elif isinstance(value, list):
            snapshot[key] = list(value)
        else:
            snapshot[key] = value

    current_hooks = settings_data.get("hooks") or {}
    template_hooks = template_settings.get("hooks") or {}
    snapshot_hooks = {}

    for event_name, current_groups in current_hooks.items():
        event_snapshot = []
        known_matchers = set()
        template_groups = template_hooks.get(event_name) or []
        for template_group in template_groups:
            if not isinstance(template_group, dict):
                continue
            known_matchers.add(str(template_group.get("matcher") or "").strip())
        for group in current_groups:
            if not isinstance(group, dict):
                continue
            matcher = str(group.get("matcher") or "").strip()
            commands = []
            for hook in group.get("hooks") or []:
                if not isinstance(hook, dict):
                    continue
                command = _normalize_hook_command(hook.get("command"))
                if command:
                    commands.append(command)
            if not commands:
                continue
            event_snapshot.append({"matcher": matcher, "commands": sorted(set(commands))})
            known_matchers.add(matcher)
        if event_snapshot:
            snapshot_hooks[event_name] = sorted(
                event_snapshot,
                key=lambda item: (item.get("matcher") or "", ",".join(item.get("commands") or [])),
            )
    snapshot["hooks"] = snapshot_hooks
    return snapshot


def _snapshot_to_template(snapshot_data, seed_template):
    snapshot_data = snapshot_data if isinstance(snapshot_data, dict) else {}
    seed_template = seed_template if isinstance(seed_template, dict) else {}
    template = {}

    for key in [
        "includeCoAuthoredBy",
        "skipDangerousModePermissionPrompt",
        "model",
        "promptSuggestionEnabled",
        "statusLine",
        "attribution",
        "permissions",
    ]:
        if key in snapshot_data:
            value = snapshot_data.get(key)
        else:
            value = seed_template.get(key)
        if isinstance(value, dict):
            template[key] = dict(value)
        elif isinstance(value, list):
            template[key] = list(value)
        elif value is not None:
            template[key] = value

    hooks = {}
    snapshot_hooks = snapshot_data.get("hooks") or {}
    seed_hooks = seed_template.get("hooks") or {}
    all_events = sorted(set(snapshot_hooks.keys()) | set(seed_hooks.keys()))
    for event_name in all_events:
        groups = []
        seen = set()
        for source_groups in [seed_hooks.get(event_name) or [], snapshot_hooks.get(event_name) or []]:
            for group in source_groups:
                if not isinstance(group, dict):
                    continue
                matcher = str(group.get("matcher") or "").strip()
                commands = []
                if "commands" in group:
                    commands = [
                        _normalize_hook_command(command)
                        for command in group.get("commands") or []
                        if _normalize_hook_command(command)
                    ]
                else:
                    for hook in group.get("hooks") or []:
                        if not isinstance(hook, dict):
                            continue
                        command = _normalize_hook_command(hook.get("command"))
                        if command:
                            commands.append(command)
                commands = sorted(set(commands))
                if not commands:
                    continue
                group_key = (matcher, tuple(commands))
                if group_key in seen:
                    continue
                seen.add(group_key)
                groups.append(
                    {
                        "matcher": matcher,
                        "hooks": [
                            {"type": "command", "command": command} for command in commands
                        ],
                    }
                )
        if groups:
            hooks[event_name] = groups
    if hooks:
        template["hooks"] = hooks
    return template


def _merge_snapshot_with_current(snapshot_data, current_settings):
    snapshot_data = snapshot_data if isinstance(snapshot_data, dict) else {}
    current_snapshot = _extract_managed_claude_snapshot(current_settings, snapshot_data)
    merged = dict(snapshot_data)

    for key, value in current_snapshot.items():
        if key == "hooks":
            continue
        if isinstance(value, dict):
            merged[key] = dict(value)
        elif isinstance(value, list):
            merged[key] = list(value)
        elif value is not None:
            merged[key] = value

    merged_hooks = {}
    known_events = set((snapshot_data.get("hooks") or {}).keys()) | set((current_snapshot.get("hooks") or {}).keys())
    for event_name in known_events:
        groups = []
        seen = set()
        for source_groups in [snapshot_data.get("hooks", {}).get(event_name) or [], current_snapshot.get("hooks", {}).get(event_name) or []]:
            for group in source_groups:
                if not isinstance(group, dict):
                    continue
                matcher = str(group.get("matcher") or "").strip()
                commands = sorted(
                    set(
                        _normalize_hook_command(command)
                        for command in group.get("commands") or []
                        if _normalize_hook_command(command)
                    )
                )
                if not commands:
                    continue
                group_key = (matcher, tuple(commands))
                if group_key in seen:
                    continue
                seen.add(group_key)
                groups.append({"matcher": matcher, "commands": commands})
        if groups:
            merged_hooks[event_name] = groups
    merged["hooks"] = merged_hooks
    return merged


def _prune_session_only_snapshot_entries(snapshot_data):
    snapshot_data = snapshot_data if isinstance(snapshot_data, dict) else {}
    hooks = snapshot_data.get("hooks") or {}
    feishu_guard = os.path.join(_LOCAL_HOOKS_DIR, "claude-feishu-webfetch-guard.sh")
    hive_compact = os.path.join(_LOCAL_HOOKS_DIR, "hive-compact-hook.sh")
    session_only_commands = {
        _normalize_hook_command(feishu_guard),
        _normalize_hook_command(f"bash {hive_compact}"),
    }
    pruned_hooks = {}
    for event_name, groups in hooks.items():
        kept_groups = []
        for group in groups or []:
            if not isinstance(group, dict):
                continue
            commands = [
                command
                for command in group.get("commands") or []
                if _normalize_hook_command(command) not in session_only_commands
            ]
            if not commands:
                continue
            kept_groups.append({"matcher": str(group.get("matcher") or "").strip(), "commands": commands})
        if kept_groups:
            pruned_hooks[event_name] = kept_groups
    snapshot_data["hooks"] = pruned_hooks
    return snapshot_data


def _sanitize_global_snapshot(snapshot_data):
    snapshot_data = snapshot_data if isinstance(snapshot_data, dict) else {}
    snapshot_data.pop("env", None)
    return _prune_session_only_snapshot_entries(snapshot_data)


def _managed_snapshot_differs(previous_snapshot, current_settings, seed_template):
    previous_snapshot = _sanitize_global_snapshot(previous_snapshot)
    current_snapshot = _sanitize_global_snapshot(_extract_managed_claude_snapshot(current_settings, seed_template))
    return previous_snapshot != current_snapshot


def _managed_snapshot_template(previous_snapshot, seed_template, current_settings):
    merged_snapshot = _merge_snapshot_with_current(previous_snapshot, current_settings)
    sanitized_snapshot = _sanitize_global_snapshot(merged_snapshot)
    return sanitized_snapshot, _snapshot_to_template(sanitized_snapshot, seed_template)


def _load_global_claude_snapshot():
    import json as _json

    snapshot_path = _global_claude_snapshot_path()
    if not os.path.exists(snapshot_path):
        return {}
    try:
        with open(snapshot_path, encoding="utf-8") as f:
            loaded = _json.load(f)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _write_global_claude_snapshot(snapshot_data):
    snapshot_path = _global_claude_snapshot_path()
    with locked_state_file(snapshot_path):
        atomic_write_json(snapshot_path, snapshot_data, mode=0o600)


def _merge_claude_settings(base_settings, template_settings):
    settings_data = dict(base_settings) if isinstance(base_settings, dict) else {}
    template_settings = template_settings if isinstance(template_settings, dict) else {}

    hooks = _merge_claude_hooks(settings_data.get("hooks"), template_settings.get("hooks"))
    if hooks:
        settings_data["hooks"] = hooks

    if isinstance(template_settings.get("statusLine"), dict):
        settings_data["statusLine"] = _merge_claude_statusline(settings_data.get("statusLine"))
    if isinstance(template_settings.get("permissions"), dict):
        settings_data["permissions"] = _merge_claude_permissions(settings_data.get("permissions"))

    settings_data.setdefault(
        "includeCoAuthoredBy",
        template_settings.get("includeCoAuthoredBy", False),
    )
    settings_data.setdefault(
        "attribution",
        template_settings.get("attribution") if isinstance(template_settings.get("attribution"), dict) else {"commit": "", "pr": ""},
    )
    settings_data.setdefault(
        "promptSuggestionEnabled",
        template_settings.get("promptSuggestionEnabled", False),
    )
    if template_settings.get("model") and not settings_data.get("model"):
        settings_data["model"] = template_settings.get("model")
    if "skipDangerousModePermissionPrompt" in template_settings:
        settings_data["skipDangerousModePermissionPrompt"] = bool(
            template_settings.get("skipDangerousModePermissionPrompt")
        )
    return settings_data


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
    import json as _json

    os.makedirs(session_claude_dir, exist_ok=True)
    session_path = os.path.join(session_claude_dir, "settings.json")
    current = {}
    if os.path.exists(session_path):
        try:
            with open(session_path, encoding="utf-8") as f:
                loaded = _json.load(f)
            if isinstance(loaded, dict):
                current = loaded
        except Exception:
            current = {}
    repaired = _merge_claude_settings(current, _load_mms_claude_settings_template())
    with locked_state_file(session_path):
        atomic_write_json(session_path, repaired, mode=0o600)
    return repaired


def repair_real_claude_settings_for_startup():
    return _repair_real_claude_settings()


def repair_current_session_claude_settings(session_claude_dir):
    os.makedirs(session_claude_dir, exist_ok=True)
    session_path = os.path.join(session_claude_dir, "settings.json")
    current = {}
    if os.path.exists(session_path):
        try:
            with open(session_path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                current = loaded
        except Exception:
            current = {}
    repaired = _merge_claude_settings(current, _load_mms_claude_settings_template())
    with locked_state_file(session_path):
        atomic_write_json(session_path, repaired, mode=0o600)
    return repaired


def _strip_agent_im_hooks(hooks_data):
    # Inherit hooks from global settings as-is
    # Users control what's in their ~/.claude/settings.json
    return hooks_data if isinstance(hooks_data, dict) else None


def _merge_claude_hook_groups(existing_groups, template_groups):
    groups = []
    if isinstance(existing_groups, list):
        groups.extend(existing_groups)
    if not isinstance(template_groups, list):
        return groups
    for template_group in template_groups:
        if not isinstance(template_group, dict):
            continue
        matcher = str(template_group.get("matcher") or "").strip()
        template_hooks = template_group.get("hooks")
        if not isinstance(template_hooks, list):
            continue
        target_group = None
        for group in groups:
            if not isinstance(group, dict):
                continue
            if str(group.get("matcher") or "").strip() == matcher:
                target_group = group
                break
        if target_group is None:
            target_group = {"matcher": matcher, "hooks": []}
            groups.append(target_group)
        hook_items = target_group.get("hooks")
        if not isinstance(hook_items, list):
            hook_items = []
            target_group["hooks"] = hook_items
        for hook in template_hooks:
            if not isinstance(hook, dict):
                continue
            command = str(hook.get("command") or "").strip()
            if not command or _hook_command_exists(hook_items, command):
                continue
            hook_items.append(dict(hook))
    return groups


def _merge_claude_hooks(existing_hooks, template_hooks):
    merged = dict(existing_hooks) if isinstance(existing_hooks, dict) else {}
    if not isinstance(template_hooks, dict):
        return merged
    for event_name, template_groups in template_hooks.items():
        merged[event_name] = _merge_claude_hook_groups(merged.get(event_name), template_groups)
    return merged


def _merge_claude_statusline(existing):
    merged = dict(existing) if isinstance(existing, dict) else {}
    merged.update(_CLAUDE_STATUSLINE_CONFIG)
    return merged


def _merge_claude_permissions(existing):
    base = dict(existing) if isinstance(existing, dict) else {}
    allow_existing = base.get("allow")
    deny_existing = base.get("deny")
    allow = []
    seen_allow = set()
    for item in list(allow_existing or []) + list(_CLAUDE_DEFAULT_PERMISSION_ALLOW):
        value = str(item or "").strip()
        if not value or value in seen_allow:
            continue
        seen_allow.add(value)
        allow.append(value)
    deny = []
    seen_deny = set()
    for item in list(deny_existing or []) + list(_CLAUDE_DEFAULT_PERMISSION_DENY):
        value = str(item or "").strip()
        if not value or value in seen_deny:
            continue
        seen_deny.add(value)
        deny.append(value)
    base["allow"] = allow
    base["deny"] = deny
    base["defaultMode"] = "bypassPermissions"
    return base


def _hook_command_exists(hook_items, command_path):
    if not isinstance(hook_items, list):
        return False
    for hook in hook_items:
        if not isinstance(hook, dict):
            continue
        if str(hook.get("type") or "").strip() != "command":
            continue
        if str(hook.get("command") or "").strip() == command_path:
            return True
    return False


def _append_command_hook(hooks_data, event_name, command_path, matcher=None):
    if not command_path or not os.path.isfile(command_path):
        return hooks_data

    merged = dict(hooks_data) if isinstance(hooks_data, dict) else {}
    event_groups = list(merged.get(event_name) or [])

    for group in event_groups:
        if not isinstance(group, dict):
            continue
        existing_matcher = str(group.get("matcher") or "").strip() if matcher is not None else ""
        target_matcher = str(matcher or "").strip()
        if existing_matcher != target_matcher:
            continue
        hook_items = group.get("hooks")
        if _hook_command_exists(hook_items, command_path):
            merged[event_name] = event_groups
            return merged
        if isinstance(hook_items, list):
            hook_items.append({"type": "command", "command": command_path})
            merged[event_name] = event_groups
            return merged

    new_group = {"hooks": [{"type": "command", "command": command_path}]}
    if matcher is not None:
        new_group["matcher"] = matcher
    event_groups.append(new_group)
    merged[event_name] = event_groups
    return merged


def _append_shell_command_hook(
    hooks_data,
    event_name,
    command_text,
    *,
    matcher=None,
    timeout=None,
    status_message=None,
):
    command_text = str(command_text or "").strip()
    if not command_text:
        return hooks_data

    merged = dict(hooks_data) if isinstance(hooks_data, dict) else {}
    event_groups = list(merged.get(event_name) or [])
    target_matcher = str(matcher or "").strip()
    hook_payload = {"type": "command", "command": command_text}
    if timeout is not None:
        hook_payload["timeout"] = timeout
    if status_message:
        hook_payload["statusMessage"] = str(status_message)

    for group in event_groups:
        if not isinstance(group, dict):
            continue
        existing_matcher = str(group.get("matcher") or "").strip() if matcher is not None else ""
        if existing_matcher != target_matcher:
            continue
        hook_items = group.get("hooks")
        if _hook_command_exists(hook_items, command_text):
            merged[event_name] = event_groups
            return merged
        if isinstance(hook_items, list):
            hook_items.append(dict(hook_payload))
            merged[event_name] = event_groups
            return merged

    new_group = {"hooks": [dict(hook_payload)]}
    if matcher is not None:
        new_group["matcher"] = matcher
    event_groups.append(new_group)
    merged[event_name] = event_groups
    return merged


def _merge_mms_session_hooks(existing_hooks, template_hooks=None):
    hooks_data = _merge_claude_hooks(existing_hooks, template_hooks)
    hooks_data = _append_command_hook(
        hooks_data,
        "PreToolUse",
        _CLAUDE_FEISHU_WEBFETCH_GUARD_HOOK,
        matcher="WebFetch",
    )
    return hooks_data


def _filter_claude_session_hooks(hooks_data, *, allow_execution_surfaces=True):
    hooks_data = hooks_data if isinstance(hooks_data, dict) else {}
    if not allow_execution_surfaces:
        return {}
    return hooks_data


def _caveman_available_for_cli(cli_name):
    return str(cli_name or "").strip() in {"claude", "codex"} and bool(_resolve_caveman_root())


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


def _resolve_caveman_root():
    candidates = []
    explicit = str(os.environ.get("MMS_CAVEMAN_ROOT") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    candidates.append(_real_user_path("caveman"))

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


def _normalize_ecc_mode(value, default="disable"):
    raw = str(value or "").strip().lower()
    if raw in {"", "inherit", "default", "auto"}:
        return default if default in {"auto", "enable", "disable"} else "disable"
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return "enable"
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return "disable"
    return default if default in {"auto", "enable", "disable"} else "disable"


def _runtime_ecc_enabled(runtime):
    return _normalize_ecc_mode((runtime or {}).get("ecc_mode", "disable")) == "enable"


def _resolve_ecc_root():
    candidates = []
    explicit = str(os.environ.get("MMS_ECC_ROOT") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    candidates.extend([
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


def _resolve_web_access_root():
    candidates = []
    explicit = str(os.environ.get("MMS_WEB_ACCESS_ROOT") or "").strip()
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
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


def _is_caveman_hook_command(command_text):
    command_text = str(command_text or "").strip().lower()
    if not command_text:
        return False
    markers = (
        "caveman-activate.js",
        "caveman-mode-tracker.js",
        "caveman mode active",
    )
    return any(marker in command_text for marker in markers)


def _is_ecc_hook_command(command_text):
    command_text = str(command_text or "").strip().lower()
    if not command_text:
        return False
    markers = (
        "plugin-hook-bootstrap.js",
        "run-with-flags.js",
        "run-with-flags-shell.sh",
        "session-start-bootstrap.js",
        "pre-bash-dispatcher.js",
        "post-bash-dispatcher.js",
        "quality-gate.js",
        "stop-format-typecheck.js",
        "continuous-learning-v2/hooks/observe.sh",
        "everything-claude-code",
    )
    return any(marker in command_text for marker in markers)


def _filter_hook_commands(hooks_data, predicate):
    hooks_data = hooks_data if isinstance(hooks_data, dict) else {}
    filtered = {}
    for event_name, groups in hooks_data.items():
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            if not isinstance(group, dict):
                kept_groups.append(group)
                continue
            hook_items = group.get("hooks")
            if not isinstance(hook_items, list):
                kept_groups.append(dict(group))
                continue
            kept_hooks = []
            for hook in hook_items:
                if not isinstance(hook, dict):
                    kept_hooks.append(hook)
                    continue
                if (
                    str(hook.get("type") or "").strip() == "command"
                    and predicate(str(hook.get("command") or ""))
                ):
                    continue
                kept_hooks.append(dict(hook))
            if not kept_hooks and hook_items:
                continue
            next_group = dict(group)
            next_group["hooks"] = kept_hooks
            kept_groups.append(next_group)
        if kept_groups:
            filtered[event_name] = kept_groups
    return filtered


def _caveman_claude_activate_command(caveman_root):
    script_path = os.path.join(caveman_root, "hooks", "caveman-activate.js")
    return f"node {json.dumps(script_path)}"


def _caveman_claude_tracker_command(caveman_root):
    script_path = os.path.join(caveman_root, "hooks", "caveman-mode-tracker.js")
    return f"node {json.dumps(script_path)}"


def _caveman_codex_hook_payload(caveman_root):
    hooks_path = os.path.join(caveman_root, ".codex", "hooks.json")
    try:
        with open(hooks_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        for group in ((payload.get("hooks") or {}).get("SessionStart") or []):
            if str(group.get("matcher") or "").strip() != "startup|resume":
                continue
            for hook in group.get("hooks") or []:
                if not isinstance(hook, dict):
                    continue
                command = str(hook.get("command") or "").strip()
                if command:
                    return dict(hook)
    except Exception:
        pass
    return {
        "type": "command",
        "command": (
            "echo 'CAVEMAN MODE ACTIVE. Rules: Drop articles/filler/pleasantries/hedging. "
            "Fragments OK. Short synonyms. Pattern: [thing] [action] [reason]. [next step]. "
            "Not: Sure! I would be happy to help you with that. Yes: Bug in auth middleware. "
            "Fix: Code/commits/security: write normal. User says stop caveman or normal mode to deactivate.'"
        ),
        "timeout": 5,
        "statusMessage": "Loading caveman mode",
    }


def _configure_claude_caveman_hooks(hooks_data, *, enable_caveman=False):
    hooks_data = _filter_hook_commands(hooks_data, _is_caveman_hook_command)
    if not enable_caveman:
        return hooks_data
    caveman_root = _resolve_caveman_root()
    if not caveman_root:
        return hooks_data
    hooks_data = _append_shell_command_hook(
        hooks_data,
        "SessionStart",
        _caveman_claude_activate_command(caveman_root),
        timeout=5,
        status_message="Loading caveman mode...",
    )
    hooks_data = _append_shell_command_hook(
        hooks_data,
        "UserPromptSubmit",
        _caveman_claude_tracker_command(caveman_root),
        timeout=5,
        status_message="Tracking caveman mode...",
    )
    return hooks_data


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


def _configure_claude_ecc_hooks(hooks_data, *, enable_ecc=False):
    hooks_data = _filter_hook_commands(hooks_data, _is_ecc_hook_command)
    if not enable_ecc:
        return hooks_data
    ecc_hooks = _load_ecc_claude_hooks()
    if not ecc_hooks:
        return hooks_data
    return _merge_claude_hooks(hooks_data, ecc_hooks)


def _build_codex_session_hooks(base_hooks=None, *, enable_caveman=False):
    payload = dict(base_hooks) if isinstance(base_hooks, dict) else {}
    hooks_data = _filter_hook_commands(payload.get("hooks"), _is_caveman_hook_command)
    if enable_caveman:
        caveman_root = _resolve_caveman_root()
        if caveman_root:
            hook_payload = _caveman_codex_hook_payload(caveman_root)
            hooks_data = _append_shell_command_hook(
                hooks_data,
                "SessionStart",
                hook_payload.get("command"),
                matcher="startup|resume",
                timeout=hook_payload.get("timeout"),
                status_message=hook_payload.get("statusMessage"),
            )
    if hooks_data:
        payload["hooks"] = hooks_data
    else:
        payload.pop("hooks", None)
    return payload


def _overlay_session_entry_dir(parent_dir, overlay_root, entry_name, extra_source_root):
    extra_source_root = str(extra_source_root or "").strip()
    if not extra_source_root:
        return False
    extra_dir = os.path.join(extra_source_root, entry_name)
    if not os.path.isdir(extra_dir):
        return False

    dst = os.path.join(parent_dir, entry_name)
    merged_dir = os.path.join(overlay_root, entry_name)
    os.makedirs(merged_dir, exist_ok=True)

    def _merge_dir(src_dir):
        src_dir = str(src_dir or "").strip()
        if not src_dir or not os.path.isdir(src_dir):
            return
        try:
            if os.path.samefile(src_dir, merged_dir):
                return
        except Exception:
            pass
        for item in os.listdir(src_dir):
            src = os.path.join(src_dir, item)
            link = os.path.join(merged_dir, item)
            if os.path.exists(link) or os.path.islink(link):
                continue
            os.symlink(src, link)

    if os.path.exists(dst) or os.path.islink(dst):
        _merge_dir(os.path.realpath(dst))
    _merge_dir(extra_dir)
    if not os.listdir(merged_dir):
        return False
    if os.path.islink(dst):
        os.unlink(dst)
    elif os.path.isdir(dst):
        shutil.rmtree(dst)
    elif os.path.exists(dst):
        os.unlink(dst)
    os.symlink(merged_dir, dst)
    return True


def _overlay_session_skill_dir(parent_dir, overlay_root, skill_name, skill_root):
    skill_name = str(skill_name or "").strip()
    skill_root = str(skill_root or "").strip()
    if not skill_name or not skill_root:
        return False
    if not os.path.isfile(os.path.join(skill_root, "SKILL.md")):
        return False

    os.makedirs(parent_dir, exist_ok=True)
    skills_dir = os.path.join(parent_dir, "skills")
    merged_dir = os.path.join(overlay_root, "skills")
    os.makedirs(merged_dir, exist_ok=True)

    def _merge_dir(src_dir):
        src_dir = str(src_dir or "").strip()
        if not src_dir or not os.path.isdir(src_dir):
            return
        try:
            if os.path.samefile(src_dir, merged_dir):
                return
        except Exception:
            pass
        for item in os.listdir(src_dir):
            src = os.path.join(src_dir, item)
            link = os.path.join(merged_dir, item)
            if os.path.exists(link) or os.path.islink(link):
                continue
            os.symlink(src, link)

    if os.path.exists(skills_dir) or os.path.islink(skills_dir):
        _merge_dir(os.path.realpath(skills_dir))

    skill_link = os.path.join(merged_dir, skill_name)
    if not os.path.exists(skill_link) and not os.path.islink(skill_link):
        os.symlink(skill_root, skill_link)

    if not os.listdir(merged_dir):
        return False
    if os.path.islink(skills_dir):
        os.unlink(skills_dir)
    elif os.path.isdir(skills_dir):
        shutil.rmtree(skills_dir)
    elif os.path.exists(skills_dir):
        os.unlink(skills_dir)
    os.symlink(merged_dir, skills_dir)
    return True


def _overlay_caveman_session_entries(parent_dir, session_home, *, enable_caveman=False):
    if not enable_caveman:
        return
    caveman_root = _resolve_caveman_root()
    if not caveman_root:
        return
    overlay_root = os.path.join(session_home, ".mms-caveman-overlay")
    os.makedirs(overlay_root, exist_ok=True)
    for entry_name in ("commands", "skills"):
        _overlay_session_entry_dir(parent_dir, overlay_root, entry_name, caveman_root)


def _overlay_ecc_session_entries(parent_dir, session_home, *, enable_ecc=False):
    if not enable_ecc:
        return
    ecc_root = _resolve_ecc_root()
    if not ecc_root:
        return
    overlay_root = os.path.join(session_home, ".mms-ecc-overlay")
    os.makedirs(overlay_root, exist_ok=True)
    for source_root, entry_name in (
        (os.path.join(ecc_root, ".claude"), "commands"),
        (ecc_root, "commands"),
        (os.path.join(ecc_root, ".claude"), "skills"),
        (os.path.join(ecc_root, ".agents"), "skills"),
        (ecc_root, "skills"),
        (os.path.join(ecc_root, ".claude"), "rules"),
        (ecc_root, "rules"),
    ):
        _overlay_session_entry_dir(parent_dir, overlay_root, entry_name, source_root)


def _overlay_web_access_session_entries(parent_dir, session_home):
    web_access_root = _resolve_web_access_root()
    if not web_access_root:
        return
    overlay_root = os.path.join(session_home, ".mms-web-access-overlay")
    os.makedirs(overlay_root, exist_ok=True)
    _overlay_session_skill_dir(parent_dir, overlay_root, "web-access", web_access_root)


def _configure_ecc_session_env(env_data, *, enable_ecc=False):
    merged = dict(env_data) if isinstance(env_data, dict) else {}
    for key in ("CLAUDE_PLUGIN_ROOT", "ECC_PLUGIN_ROOT", "ECC_HOOK_PROFILE", "ECC_DISABLED_HOOKS"):
        merged.pop(key, None)
    if not enable_ecc:
        return merged
    ecc_root = _resolve_ecc_root()
    if not ecc_root:
        return merged
    merged["CLAUDE_PLUGIN_ROOT"] = ecc_root
    merged["ECC_PLUGIN_ROOT"] = ecc_root
    merged.setdefault("ECC_HOOK_PROFILE", "standard")
    return merged


def _session_required_env_from_runtime_env(env):
    env = env if isinstance(env, dict) else {}
    required = {}
    for key in _CLAUDE_SESSION_ENV_KEYS:
        value = str(env.get(key) or "").strip()
        if value:
            required[key] = value
    return required


def _sanitize_claude_inherited_settings_payload(settings_data, *, allow_execution_surfaces=True):
    settings_data = settings_data if isinstance(settings_data, dict) else {}
    inherited = {}
    if allow_execution_surfaces:
        for key in _CLAUDE_SETTINGS_INHERIT_KEYS:
            value = settings_data.get(key)
            if isinstance(value, dict):
                inherited[key] = copy.deepcopy(value)
    for key in _CLAUDE_SETTINGS_INHERIT_SCALAR_KEYS:
        value = settings_data.get(key)
        if isinstance(value, (str, int, float, bool)):
            inherited[key] = copy.deepcopy(value)
    return inherited


def _sanitize_account_claude_settings_payload(settings_data):
    return _sanitize_claude_inherited_settings_payload(settings_data)


def _default_session_mcp_servers():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    servers = {}

    hive_command = os.path.join(repo_root, "hive", "bin", "mcp-server.sh")
    if os.path.isfile(hive_command):
        servers["hive"] = {
            "args": [],
            "command": hive_command,
            "env": {"HOME": _real_user_home()},
            "type": "stdio",
        }

    mindkeeper_server = os.path.join(repo_root, "mindkeeper", "dist", "server.js")
    if os.path.isfile(mindkeeper_server):
        servers["mindkeeper"] = {
            "args": [mindkeeper_server],
            "command": "node",
            "type": "stdio",
        }

    return servers


def _session_managed_mcp_server_allowlist(*, allow_execution_surfaces=True):
    if allow_execution_surfaces:
        return _CLAUDE_SESSION_MCP_SERVER_ALLOWLIST
    return ()


def _session_managed_mcp_servers(settings_data, *, allow_execution_surfaces=True):
    settings_data = settings_data if isinstance(settings_data, dict) else {}
    inherited = {}
    allowlist = _session_managed_mcp_server_allowlist(
        allow_execution_surfaces=allow_execution_surfaces
    )
    mcp_servers = settings_data.get("mcpServers")
    if isinstance(mcp_servers, dict):
        for name in allowlist:
            spec = mcp_servers.get(name)
            if isinstance(spec, dict) and str(spec.get("command") or "").strip():
                inherited[name] = copy.deepcopy(spec)

    fallback = _default_session_mcp_servers()
    for name in allowlist:
        if name not in inherited and isinstance(fallback.get(name), dict):
            inherited[name] = copy.deepcopy(fallback[name])
    return inherited


def _inject_managed_mcp_servers_into_claude_state(
    payload,
    settings_data=None,
    *,
    allow_execution_surfaces=True,
):
    state = dict(payload) if isinstance(payload, dict) else {}
    managed = _session_managed_mcp_servers(
        settings_data if isinstance(settings_data, dict) else _load_real_claude_settings(),
        allow_execution_surfaces=allow_execution_surfaces,
    )
    existing = state.get("mcpServers")
    merged = copy.deepcopy(managed)
    allowlist = _session_managed_mcp_server_allowlist(
        allow_execution_surfaces=allow_execution_surfaces
    )
    if isinstance(existing, dict):
        for name in allowlist:
            spec = existing.get(name)
            if isinstance(spec, dict) and str(spec.get("command") or "").strip():
                merged[name] = copy.deepcopy(spec)
    if merged:
        state["mcpServers"] = merged
    else:
        state.pop("mcpServers", None)
    return state


def _copy_allowed_scalar_fields(payload, allowed_keys):
    payload = payload if isinstance(payload, dict) else {}
    copied = {}
    for key in allowed_keys:
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)):
            copied[key] = copy.deepcopy(value)
    return copied


def _copy_allowed_scalar_dict_fields(payload, allowed_keys):
    payload = payload if isinstance(payload, dict) else {}
    copied = {}
    for key in allowed_keys:
        value = payload.get(key)
        if not isinstance(value, dict):
            continue
        child = {}
        for child_key, child_value in value.items():
            if isinstance(child_value, (str, int, float, bool)):
                child[str(child_key)] = copy.deepcopy(child_value)
        if child:
            copied[key] = child
    return copied


def _sanitize_claude_ui_state_seed_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    seed = _copy_allowed_scalar_fields(payload, _CLAUDE_OAUTH_UI_STATE_SEED_KEYS)
    seed.update(_copy_allowed_scalar_dict_fields(payload, _CLAUDE_OAUTH_STATE_SCALAR_DICT_ALLOWLIST))
    mcp_servers = payload.get("mcpServers")
    if isinstance(mcp_servers, dict):
        seed["mcpServers"] = copy.deepcopy(mcp_servers)
    return seed


def _merge_scalar_dict_entries(existing_payload, incoming_payload, *, prefer_max_numeric=False):
    existing_payload = existing_payload if isinstance(existing_payload, dict) else {}
    incoming_payload = incoming_payload if isinstance(incoming_payload, dict) else {}
    merged = copy.deepcopy(existing_payload)
    for key, incoming_value in incoming_payload.items():
        existing_value = existing_payload.get(key)
        if (
            prefer_max_numeric
            and isinstance(existing_value, (int, float))
            and not isinstance(existing_value, bool)
            and isinstance(incoming_value, (int, float))
            and not isinstance(incoming_value, bool)
        ):
            merged[key] = max(existing_value, incoming_value)
        else:
            merged[key] = copy.deepcopy(incoming_value)
    return merged


def _merge_claude_ui_state_seed(target_payload, seed_payload):
    target_payload = dict(target_payload) if isinstance(target_payload, dict) else {}
    seed_payload = seed_payload if isinstance(seed_payload, dict) else {}
    for key, value in seed_payload.items():
        if key == "numStartups" and isinstance(value, (int, float)) and not isinstance(value, bool):
            existing_value = target_payload.get(key)
            if isinstance(existing_value, (int, float)) and not isinstance(existing_value, bool):
                target_payload[key] = max(existing_value, value)
            else:
                target_payload[key] = value
            continue
        if key in _CLAUDE_OAUTH_STATE_SCALAR_DICT_ALLOWLIST and isinstance(value, dict):
            target_payload[key] = _merge_scalar_dict_entries(
                target_payload.get(key),
                value,
                prefer_max_numeric=(key == "tipsHistory"),
            )
            continue
        if key == "mcpServers" and isinstance(value, dict):
            merged_servers = copy.deepcopy(value)
            existing_servers = target_payload.get(key)
            if isinstance(existing_servers, dict):
                merged_servers.update(copy.deepcopy(existing_servers))
            target_payload[key] = merged_servers
            continue
        target_payload.setdefault(key, copy.deepcopy(value))
    return target_payload


def _strip_claude_state_execution_surfaces(payload):
    payload = dict(payload) if isinstance(payload, dict) else {}
    payload.pop("mcpServers", None)
    projects = payload.get("projects")
    if isinstance(projects, dict):
        stripped_projects = {}
        for project_path, entry in projects.items():
            if not isinstance(entry, dict):
                continue
            next_entry = dict(entry)
            next_entry.pop("mcpServers", None)
            next_entry["enabledMcpjsonServers"] = []
            next_entry["disabledMcpjsonServers"] = []
            stripped_projects[project_path] = next_entry
        payload["projects"] = stripped_projects
    return payload


def _sanitize_claude_project_state_entry(entry):
    entry = entry if isinstance(entry, dict) else {}
    cleaned = _copy_allowed_scalar_fields(
        entry,
        (
            "hasTrustDialogAccepted",
            "hasCompletedProjectOnboarding",
            "hasClaudeMdExternalIncludesApproved",
            "hasClaudeMdExternalIncludesWarningShown",
            "projectOnboardingSeenCount",
            "lastGracefulShutdown",
        ),
    )
    for key in ("allowedTools", "mcpContextUris", "enabledMcpjsonServers", "disabledMcpjsonServers"):
        value = entry.get(key)
        if isinstance(value, list):
            cleaned[key] = copy.deepcopy(value)
    mcp_servers = entry.get("mcpServers")
    if isinstance(mcp_servers, dict):
        cleaned["mcpServers"] = copy.deepcopy(mcp_servers)
    return cleaned


def _sanitize_claude_project_state_map(projects_data):
    projects = {}
    if not isinstance(projects_data, dict):
        return projects
    for project_path, entry in projects_data.items():
        normalized_path = os.path.realpath(str(project_path or "").strip())
        if not normalized_path:
            continue
        cleaned_entry = _sanitize_claude_project_state_entry(entry)
        if cleaned_entry:
            projects[normalized_path] = cleaned_entry
    return projects


def _load_real_claude_ui_state_seed():
    import json as _json

    real_json = _real_user_path(".claude.json")
    if not os.path.exists(real_json):
        return {}
    try:
        with open(real_json, encoding="utf-8") as f:
            loaded = _json.load(f)
        if not isinstance(loaded, dict):
            return {}
        return _sanitize_claude_ui_state_seed_payload(loaded)
    except Exception:
        return {}


def _load_real_claude_project_state(project_path):
    import json as _json

    real_json = _real_user_path(".claude.json")
    normalized_project = os.path.realpath(str(project_path or "").strip())
    if not normalized_project or not os.path.exists(real_json):
        return None
    try:
        with open(real_json, encoding="utf-8") as f:
            loaded = _json.load(f)
        if not isinstance(loaded, dict):
            return None
        projects = loaded.get("projects")
        if not isinstance(projects, dict):
            return None
        project_state = projects.get(normalized_project)
        if not isinstance(project_state, dict):
            return None
        cleaned = _sanitize_claude_project_state_entry(project_state)
        return cleaned or None
    except Exception:
        return None


def _sanitize_oauth_claude_state_payload(data):
    raw_data = data if isinstance(data, dict) else {}
    payload = _strip_claude_restore_state(raw_data)
    cleaned = _copy_allowed_scalar_fields(payload, _CLAUDE_OAUTH_STATE_TOP_LEVEL_ALLOWLIST)
    cleaned.update(_copy_allowed_scalar_dict_fields(raw_data, _CLAUDE_OAUTH_STATE_SCALAR_DICT_ALLOWLIST))

    oauth_account = _copy_allowed_scalar_fields(
        payload.get("oauthAccount"),
        _CLAUDE_OAUTH_ACCOUNT_ALLOWLIST,
    )
    if oauth_account:
        cleaned["oauthAccount"] = oauth_account

    claude_ai_oauth = _copy_allowed_scalar_fields(
        payload.get("claudeAiOauth"),
        _CLAUDE_AI_OAUTH_ALLOWLIST,
    )
    if claude_ai_oauth:
        cleaned["claudeAiOauth"] = claude_ai_oauth

    projects = _sanitize_claude_project_state_map(raw_data.get("projects"))
    if projects:
        cleaned["projects"] = projects

    return cleaned


def _sanitize_codex_claude_state_payload(data):
    payload = _strip_claude_restore_state(data, strip_sensitive_auth=True)
    return _copy_allowed_scalar_fields(payload, _CLAUDE_CODEX_STATE_TOP_LEVEL_ALLOWLIST)


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
    payload = dict(data) if isinstance(data, dict) else {}
    payload.pop("projects", None)
    payload.pop("lastSessionId", None)
    payload.pop("lastCost", None)
    if strip_sensitive_auth:
        for key in _CLAUDE_GATEWAY_SENSITIVE_STATE_KEYS:
            payload.pop(key, None)
    return payload


def _load_project_scoped_claude_resume_session_id(
    project_path,
    *,
    account_id="",
    runtime_kind="",
    resume_model="",
):
    normalized_project = os.path.realpath(str(project_path or "").strip())
    normalized_account_id = str(account_id or "").strip()
    normalized_runtime_kind = str(runtime_kind or "").strip()
    normalized_resume_model = _claude_resume_model_name(resume_model)
    if not normalized_project or not normalized_account_id:
        return None
    try:
        sessions = list_indexed_sessions("claude")
    except Exception:
        return None

    candidates: list[tuple[str, str]] = []
    for session in sessions:
        if str(session.get("account_id") or "").strip() != normalized_account_id:
            continue
        session_project = os.path.realpath(
            str(session.get("project_path") or session.get("cwd") or "").strip()
        )
        if session_project != normalized_project:
            continue
        session_runtime_kind = str(session.get("runtime_kind") or "").strip()
        if normalized_runtime_kind and session_runtime_kind and session_runtime_kind != normalized_runtime_kind:
            continue
        if normalized_resume_model:
            session_resume_model = _claude_resume_model_name(
                session.get("resume_model"),
                session.get("display_model"),
                session.get("selected_model"),
            )
            if session_resume_model != normalized_resume_model:
                continue
        session_id = str(session.get("session_id") or "").strip()
        if not session_id or session_id.startswith("pid-"):
            continue
        sort_key = str(session.get("last_active_at") or session.get("started_at") or "").strip()
        candidates.append((sort_key, session_id))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _overlay_project_scoped_claude_resume_state(
    data,
    project_path,
    *,
    account_id="",
    runtime_kind="",
    resume_model="",
):
    payload = dict(data) if isinstance(data, dict) else {}
    normalized_project = os.path.realpath(str(project_path or "").strip())
    if not normalized_project:
        return payload
    session_id = _load_project_scoped_claude_resume_session_id(
        normalized_project,
        account_id=account_id,
        runtime_kind=runtime_kind,
        resume_model=resume_model,
    )
    if not session_id:
        return payload

    projects = payload.get("projects")
    if not isinstance(projects, dict):
        projects = {}
    entry = projects.get(normalized_project)
    next_entry = dict(entry) if isinstance(entry, dict) else {}
    next_entry["lastSessionId"] = session_id
    projects[normalized_project] = next_entry
    payload["projects"] = projects
    return payload


def _ensure_claude_project_trust(
    data,
    project_path,
    project_state=None,
    *,
    allow_execution_surfaces=True,
):
    payload = dict(data) if isinstance(data, dict) else {}
    project_path = os.path.realpath(str(project_path or "").strip())
    projects = payload.get("projects")
    if not isinstance(projects, dict):
        projects = {}

    entry = {}
    if isinstance(project_state, dict):
        entry.update(project_state)
    elif isinstance(projects.get(project_path), dict):
        entry.update(projects[project_path])

    entry.setdefault("allowedTools", [])
    entry.setdefault("mcpContextUris", [])
    entry.setdefault("mcpServers", {})
    entry.setdefault("enabledMcpjsonServers", [])
    entry.setdefault("disabledMcpjsonServers", [])
    if not allow_execution_surfaces:
        entry["mcpServers"] = {}
        entry["enabledMcpjsonServers"] = []
        entry["disabledMcpjsonServers"] = []
    entry["hasTrustDialogAccepted"] = True
    entry["hasCompletedProjectOnboarding"] = True
    entry["hasClaudeMdExternalIncludesApproved"] = True
    entry["hasClaudeMdExternalIncludesWarningShown"] = True
    seen_count = entry.get("projectOnboardingSeenCount")
    if isinstance(seen_count, (int, float)) and not isinstance(seen_count, bool):
        entry["projectOnboardingSeenCount"] = max(int(seen_count), 1)
    else:
        entry["projectOnboardingSeenCount"] = 1
    entry.setdefault("lastGracefulShutdown", False)

    projects[project_path] = entry
    payload["projects"] = projects
    return payload


def _copy_claude_state_json(src, dst, *, mode="restore"):
    import json as _json

    payload = {}
    if os.path.exists(src):
        try:
            with open(src, encoding="utf-8") as f:
                loaded = _json.load(f)
            if isinstance(loaded, dict):
                payload = loaded
        except Exception:
            payload = {}
    if mode == "oauth":
        payload = _sanitize_oauth_claude_state_payload(payload)
    else:
        payload = _strip_claude_restore_state(payload)
    with locked_state_file(dst):
        atomic_write_json(dst, payload, mode=0o600)


def _parse_iso8601_utc(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _merge_oauth_token_state(existing_payload, incoming_payload):
    existing_payload = existing_payload if isinstance(existing_payload, dict) else {}
    incoming_payload = incoming_payload if isinstance(incoming_payload, dict) else {}
    existing_expiry = _parse_iso8601_utc(existing_payload.get("expiresAt"))
    incoming_expiry = _parse_iso8601_utc(incoming_payload.get("expiresAt"))
    if existing_expiry and incoming_expiry:
        return copy.deepcopy(incoming_payload if incoming_expiry >= existing_expiry else existing_payload)
    if incoming_expiry:
        return copy.deepcopy(incoming_payload)
    if existing_expiry:
        return copy.deepcopy(existing_payload)
    incoming_has_tokens = any(
        str(incoming_payload.get(key) or "").strip()
        for key in ("accessToken", "refreshToken", "tokenType", "token_type")
    )
    if incoming_has_tokens:
        return copy.deepcopy(incoming_payload)
    return copy.deepcopy(existing_payload or incoming_payload)


def _merge_oauth_claude_state_payload(existing_data, incoming_data):
    existing = _sanitize_oauth_claude_state_payload(existing_data)
    incoming = _sanitize_oauth_claude_state_payload(incoming_data)
    merged = copy.deepcopy(existing)

    for key in _CLAUDE_OAUTH_STATE_TOP_LEVEL_ALLOWLIST:
        incoming_value = incoming.get(key)
        existing_value = existing.get(key)
        if key == "firstStartTime":
            chosen = existing_value or incoming_value
            if isinstance(chosen, (str, int, float, bool)):
                merged[key] = copy.deepcopy(chosen)
            continue
        if key == "numStartups":
            numeric_values = [value for value in (existing_value, incoming_value) if isinstance(value, (int, float))]
            if numeric_values:
                merged[key] = max(numeric_values)
            continue
        if key in {"bypassPermissionsModeAccepted", "alwaysThinkingEnabled", "hasCompletedOnboarding"}:
            if existing_value or incoming_value:
                merged[key] = bool(existing_value or incoming_value)
            elif key in merged:
                merged[key] = bool(merged.get(key))
            continue
        if isinstance(incoming_value, (str, int, float, bool)):
            merged[key] = copy.deepcopy(incoming_value)

    for key in _CLAUDE_OAUTH_STATE_SCALAR_DICT_ALLOWLIST:
        merged_dict = _merge_scalar_dict_entries(
            existing.get(key),
            incoming.get(key),
            prefer_max_numeric=(key == "tipsHistory"),
        )
        if merged_dict:
            merged[key] = merged_dict

    merged_account = copy.deepcopy(existing.get("oauthAccount") or {})
    if isinstance(incoming.get("oauthAccount"), dict):
        merged_account.update(copy.deepcopy(incoming["oauthAccount"]))
    if merged_account:
        merged["oauthAccount"] = merged_account

    merged_token = _merge_oauth_token_state(existing.get("claudeAiOauth"), incoming.get("claudeAiOauth"))
    if merged_token:
        merged["claudeAiOauth"] = merged_token

    merged_projects = copy.deepcopy(existing.get("projects") or {})
    for project_path, entry in (incoming.get("projects") or {}).items():
        current_entry = merged_projects.get(project_path)
        next_entry = dict(current_entry) if isinstance(current_entry, dict) else {}
        if isinstance(entry, dict):
            next_entry.update(copy.deepcopy(entry))
        if next_entry:
            merged_projects[project_path] = next_entry
    if merged_projects:
        merged["projects"] = merged_projects

    return merged


def _masked_exposure_env_value(key, value):
    key = str(key or "").strip()
    value = str(value or "").strip()
    if not value:
        return ""
    lower_key = key.lower()
    if "proxy" in lower_key and "://" in value:
        return _mask_proxy_url(value)
    return value


def inspect_runtime_exposure(cli, runtime):
    cli = str(cli or "").strip()
    runtime = dict(runtime or {})
    auth_mode = str(runtime.get("auth_mode") or "api_key").strip() or "api_key"
    runtime_id = str(runtime.get("id") or runtime.get("name") or "").strip()
    real_home = _real_user_home()
    account_home = _normalize_path(runtime.get("home_dir") or "")
    fake_payload = _fake_upstream_status_payload() if _fake_upstream_enabled() else {}
    locale_env = _runtime_locale_env(runtime)
    timezone_name = _validate_timezone_or_exit(
        runtime.get("timezone") or DEFAULT_ACCOUNT_TIMEZONE,
        label=runtime_id or cli or "runtime",
    )
    process_env = {
        "MMS_REAL_HOME": real_home,
        "REAL_HOME": real_home,
        "ORIGINAL_HOME": real_home,
        "TZ": timezone_name,
    }
    process_env.update(locale_env)
    home_info = {
        "real_home": real_home,
        "account_home": account_home,
        "session_home": "",
        "settings_path": "",
    }
    settings_info = {
        "path": "",
        "statusline": False,
        "hook_events": [],
        "env_keys": [],
    }
    notes = [
        "CLI 进程可直接读取这些环境变量；上游通常看不到本地 proxy URL，但能观察到出口 IP / DNS 行为 / 时间与语言表现。",
    ]

    if cli == "claude" and auth_mode == "oauth":
        session_home = os.path.join(account_home, "s", str(os.getpid())) if account_home else ""
        account_claude_dir = os.path.join(account_home, ".claude") if account_home else ""
        session_claude_dir = os.path.join(session_home, ".claude") if session_home else ""
        process_env["HOME"] = session_home
        process_env["MMS_SESSION_HOME"] = session_home
        home_info["session_home"] = session_home
        home_info["settings_path"] = os.path.join(session_claude_dir, "settings.json") if session_claude_dir else ""
        account_settings = _load_claude_settings_from_dir(account_claude_dir)
        projected_env = dict(process_env)
        _apply_runtime_network_profile(projected_env, runtime, validate_proxy=False)
        required_env = _session_required_env_from_runtime_env(projected_env)
        session_settings = _build_claude_session_settings(
            base_settings=account_settings,
            required_env=required_env,
            default_env={
                "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
                "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
            },
            allow_execution_surfaces=False,
        )
        settings_info = {
            "path": home_info["settings_path"],
            "statusline": isinstance(session_settings.get("statusLine"), dict),
            "hook_events": sorted((session_settings.get("hooks") or {}).keys()),
            "env_keys": sorted((session_settings.get("env") or {}).keys()),
        }
        notes.append("Claude OAuth session 采用 fail-closed 隔离策略：不注入 MMS 管理的 hooks / statusLine / MCP / wrapper。")
    elif cli == "claude":
        gateway_home = _claude_gateway_home()
        home_info["session_home"] = gateway_home
        home_info["settings_path"] = os.path.join(gateway_home, ".claude", "settings.json")
        process_env["HOME"] = gateway_home
        process_env["MMS_SESSION_HOME"] = gateway_home
        projected_settings = _build_claude_session_settings(
            base_settings=_load_real_claude_settings(),
            default_env={"CLAUDE_CODE_ATTRIBUTION_HEADER": "0"},
        )
        settings_info = {
            "path": home_info["settings_path"],
            "statusline": isinstance(projected_settings.get("statusLine"), dict),
            "hook_events": sorted((projected_settings.get("hooks") or {}).keys()),
            "env_keys": sorted((projected_settings.get("env") or {}).keys()),
        }
        notes.append("Claude provider/gateway 模式也会在 session settings.json 中暴露 statusLine / hooks / env。")
    elif cli == "codex" and auth_mode == "oauth":
        session_home = os.path.join(account_home, "s", str(os.getpid())) if account_home else ""
        process_env["HOME"] = session_home
        process_env["MMS_SESSION_HOME"] = session_home
        process_env["XDG_CONFIG_HOME"] = os.path.join(session_home, ".config") if session_home else ""
        home_info["session_home"] = session_home
        notes.append("Codex OAuth 主要通过进程环境与 session HOME/XDG 路径感知隔离态。")
    elif cli == "gemini" and auth_mode == "oauth":
        process_env["GEMINI_CLI_HOME"] = account_home
        home_info["session_home"] = account_home
        notes.append("Gemini OAuth 当前通过 GEMINI_CLI_HOME 指向账号目录，不走 Claude 那套 session settings。")

    if _runtime_force_ipv4(runtime):
        process_env["MMS_FORCE_IPV4"] = "1"
    proxy_url = str(runtime.get("proxy") or "").strip()
    no_proxy = str(runtime.get("no_proxy") or "").strip()
    if _fake_upstream_enabled():
        fake_proxy_url = str(fake_payload.get("proxy_url") or "").strip()
        if fake_proxy_url:
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
                process_env[key] = fake_proxy_url
        for key in ("NO_PROXY", "no_proxy"):
            process_env[key] = "127.0.0.1,localhost,::1"
        process_env["MMS_FAKE_UPSTREAM_MODE"] = "upstream-proxy"
        if proxy_url:
            process_env["MMS_FAKE_UPSTREAM_ORIGINAL_PROXY"] = _proxy_fingerprint(proxy_url)
        if no_proxy:
            process_env["MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY"] = no_proxy
        if fake_payload.get("ca_cert_path"):
            process_env["NODE_EXTRA_CA_CERTS"] = str(fake_payload.get("ca_cert_path") or "")
            process_env["SSL_CERT_FILE"] = str(fake_payload.get("ca_cert_path") or "")
    elif proxy_url:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            process_env[key] = proxy_url
        for key in ("NO_PROXY", "no_proxy"):
            process_env[key] = no_proxy

    process_env_rows = [
        {"key": key, "value": _masked_exposure_env_value(key, value)}
        for key, value in sorted(process_env.items())
        if str(value or "").strip()
    ]
    return {
        "cli": cli,
        "runtime_id": runtime_id,
        "runtime_name": str(runtime.get("name") or runtime_id or "").strip(),
        "auth_mode": auth_mode,
        "network": {
            "proxy_mode": _runtime_net_mode(runtime),
            "proxy_fingerprint": _proxy_fingerprint(proxy_url),
            "dns_mode": _runtime_dns_mode(runtime),
            "timezone": timezone_name,
            "locale": locale_env.get("LANG", ""),
            "force_ipv4": bool(_runtime_force_ipv4(runtime)),
            "fake_upstream": bool(_fake_upstream_enabled()),
        },
        "home": home_info,
        "process_env": process_env_rows,
        "settings": settings_info,
        "notes": notes,
    }


def _build_claude_session_settings(
    base_settings=None,
    *,
    required_env=None,
    default_env=None,
    allow_execution_surfaces=True,
    enable_caveman=False,
    enable_ecc=False,
):
    template_settings = _load_mms_claude_settings_template()
    inherited_settings = _sanitize_claude_inherited_settings_payload(
        base_settings,
        allow_execution_surfaces=allow_execution_surfaces,
    )
    settings_data = _merge_claude_settings(
        inherited_settings,
        _load_global_claude_settings_template(),
    )
    managed_mcp_servers = _session_managed_mcp_servers(
        base_settings,
        allow_execution_surfaces=allow_execution_surfaces,
    )

    template_hooks = template_settings.get("hooks")
    hooks = _filter_claude_session_hooks(
        _merge_mms_session_hooks(
            _strip_agent_im_hooks(settings_data.get("hooks")),
            template_hooks,
        ),
        allow_execution_surfaces=allow_execution_surfaces,
    )
    hooks = _configure_claude_caveman_hooks(
        hooks,
        enable_caveman=bool(enable_caveman and allow_execution_surfaces),
    )
    hooks = _configure_claude_ecc_hooks(
        hooks,
        enable_ecc=bool(enable_ecc and allow_execution_surfaces),
    )
    if hooks:
        settings_data["hooks"] = hooks
    else:
        settings_data.pop("hooks", None)

    existing_env = settings_data.get("env")
    merged_env = dict(existing_env) if isinstance(existing_env, dict) else {}
    template_env = template_settings.get("env")
    if isinstance(template_env, dict):
        for key, value in template_env.items():
            merged_env.setdefault(key, value)
    if isinstance(default_env, dict):
        for key, value in default_env.items():
            merged_env.setdefault(key, value)
    if isinstance(required_env, dict):
        merged_env.update(required_env)
    settings_data["env"] = _configure_ecc_session_env(
        merged_env,
        enable_ecc=bool(enable_ecc and allow_execution_surfaces),
    )

    if managed_mcp_servers:
        settings_data["mcpServers"] = managed_mcp_servers
    else:
        settings_data.pop("mcpServers", None)

    settings_data.setdefault(
        "includeCoAuthoredBy",
        template_settings.get("includeCoAuthoredBy", False),
    )
    settings_data.setdefault(
        "attribution",
        template_settings.get("attribution") if isinstance(template_settings.get("attribution"), dict) else {"commit": "", "pr": ""},
    )
    settings_data.setdefault(
        "promptSuggestionEnabled",
        template_settings.get("promptSuggestionEnabled", False),
    )
    if template_settings.get("model") and not settings_data.get("model"):
        settings_data["model"] = template_settings.get("model")
    settings_data["skipDangerousModePermissionPrompt"] = bool(
        template_settings.get("skipDangerousModePermissionPrompt", True)
    )
    if allow_execution_surfaces:
        settings_data["statusLine"] = _merge_claude_statusline(settings_data.get("statusLine"))
        settings_data["permissions"] = _merge_claude_permissions(settings_data.get("permissions"))
    else:
        settings_data.pop("statusLine", None)
        settings_data.pop("permissions", None)
    return settings_data


def _write_claude_session_settings(
    session_claude_dir,
    *,
    required_env=None,
    default_env=None,
    base_settings=None,
    allow_execution_surfaces=True,
    enable_caveman=False,
    enable_ecc=False,
):
    import json as _json

    os.makedirs(session_claude_dir, exist_ok=True)
    source_settings = (
        dict(base_settings) if isinstance(base_settings, dict) else _load_real_claude_settings()
    )
    settings_data = _build_claude_session_settings(
        source_settings,
        required_env=required_env,
        default_env=default_env,
        allow_execution_surfaces=allow_execution_surfaces,
        enable_caveman=enable_caveman,
        enable_ecc=enable_ecc,
    )
    settings_path = os.path.join(session_claude_dir, "settings.json")
    with locked_state_file(settings_path):
        atomic_write_json(settings_path, settings_data, mode=0o600)
    return settings_data, settings_path


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
    protocols = provider.get("protocols", [])
    if isinstance(protocols, str):
        return [protocols]
    return list(protocols)


def _provider_supports_cli(provider, cli):
    supported_clis = provider.get("supported_clis", [])
    if isinstance(supported_clis, str):
        supported_clis = [supported_clis]
    return cli in supported_clis


def validate_provider_for_cli(cli, provider):
    """在真正启动前做 fail-fast 校验。"""
    provider_name = provider.get("name", provider.get("id", "provider"))
    provider_id = provider.get("id", "provider")
    required_protocol = CLI_PROTOCOL_REQUIREMENTS.get(cli)
    protocols = _provider_protocols(provider)

    if cli == "codex" and str(provider_id).strip().lower().startswith("kimi"):
        console.print(f"[red]provider '{provider_id}' 当前不支持直接驱动 codex；请改走 claude 路径[/red]")
        sys.exit(1)

    if not provider.get("enabled", True):
        console.print(f"[red]provider '{provider_id}' 已禁用，无法用于 {cli}[/red]")
        sys.exit(1)

    if not _provider_supports_cli(provider, cli):
        # OpenAI-compatible providers can still drive Claude through the bridge path.
        if not (cli == "claude" and "openai_chat_completions" in protocols):
            console.print(f"[red]provider '{provider_id}' 不支持 CLI: {cli}[/red]")
            sys.exit(1)

    if required_protocol and required_protocol not in _provider_protocols(provider):
        # OpenAI-only provider 可以通过 bridge 驱动 claude，不阻断
        if cli == "claude" and "openai_chat_completions" in protocols:
            pass
        else:
            console.print(
                f"[red]provider '{provider_id}' ({provider_name}) 缺少协议 {required_protocol}，无法驱动 {cli}[/red]"
            )
            sys.exit(1)

    if not provider.get("api_key"):
        console.print(f"[red]provider '{provider_id}' 未配置 api_key[/red]")
        sys.exit(1)
    if cli == "claude" and not _anthropic_base_url(provider) and not _openai_base_url(provider):
        console.print(f"[red]provider '{provider_id}' 未配置任何 API 地址[/red]")
        sys.exit(1)
    if cli in {"codex", "qwen", "kimi"} and not _openai_base_url(provider):
        console.print(f"[red]provider '{provider_id}' 未配置 OpenAI 地址[/red]")
        sys.exit(1)


def _scrub_claude_oauth_env(env):
    env = env if isinstance(env, dict) else {}
    for key in list(env.keys()):
        normalized = str(key or "").strip()
        if any(normalized.startswith(prefix) for prefix in _CLAUDE_OAUTH_ENV_PREFIX_BLOCKLIST):
            env.pop(key, None)
    return env


def _scrub_inherited_runtime_env(env, *, strip_openai=False, strip_proxy=False):
    env = _scrub_claude_oauth_env(env)
    if strip_openai:
        for key in list(env.keys()):
            normalized = str(key or "").strip()
            if any(normalized.startswith(prefix) for prefix in _OPENAI_ENV_PREFIX_BLOCKLIST):
                env.pop(key, None)
    if strip_proxy:
        for key in (*_RUNTIME_PROXY_ENV_KEYS, *_RUNTIME_FAKE_ENV_KEYS, *_RUNTIME_CA_ENV_KEYS):
            env.pop(key, None)
    return env


def _account_env(account, *, validate_proxy=True):
    env = os.environ.copy()
    _scrub_inherited_runtime_env(env, strip_openai=True, strip_proxy=True)
    _inject_real_home_hints(env)
    home_dir = os.path.expanduser(str(account.get("home_dir", "")).strip())
    if not home_dir:
        console.print(f"[red]账号档案 '{account.get('id', 'unknown')}' 未配置 home_dir[/red]")
        sys.exit(1)
    cli_name = account.get("cli")
    if cli_name == "claude":
        seed_claude_state(home_dir)
        account_claude_dir = os.path.join(home_dir, ".claude")
        os.makedirs(account_claude_dir, exist_ok=True)
        # per-PID 会话隔离：每个窗口独立 HOME，避免多窗口 race ~/.claude.json
        sessions_dir = os.path.join(home_dir, "s")
        session_home, active_before, active_after = _reserve_session_home(
            sessions_dir,
            account_id=account.get("id", ""),
            runtime_kind="oauth",
            stale_callback=_finalize_claude_slot,
            max_live_sessions=4,
        )
        if not session_home:
            console.print(f"[red]该账号当前将达到 {active_after} 个并发会话，已超过安全上限 4[/red]")
            sys.exit(1)
        report = account.get("_account_guard_report")
        if isinstance(report, dict):
            report["active_sessions_before"] = active_before
            report["active_sessions_after"] = active_after
        # 复制账号的 .claude.json 到 per-session 目录
        import json as _json
        account_json = os.path.join(home_dir, ".claude.json")
        session_json = os.path.join(session_home, ".claude.json")
        if os.path.exists(account_json):
            try:
                _copy_claude_state_json(account_json, session_json, mode="oauth")
            except Exception:
                pass
        current_project = os.path.realpath(os.getcwd())
        current_project_state = _load_real_claude_project_state(current_project)
        session_state = {}
        if os.path.exists(session_json):
            try:
                with open(session_json, encoding="utf-8") as f:
                    loaded = _json.load(f)
                if isinstance(loaded, dict):
                    session_state = loaded
            except Exception:
                session_state = {}
        session_state = _merge_claude_ui_state_seed(session_state, _load_real_claude_ui_state_seed())
        session_state = _strip_claude_state_execution_surfaces(session_state)
        if account.get("bypass"):
            session_state["bypassPermissionsModeAccepted"] = True
        else:
            session_state.pop("bypassPermissionsModeAccepted", None)
        session_state = _ensure_claude_project_trust(
            session_state,
            current_project,
            project_state=current_project_state,
            allow_execution_surfaces=False,
        )
        with locked_state_file(session_json):
            atomic_write_json(session_json, session_state, mode=0o600)
        # symlink .local
        real_local = _real_user_path(".local")
        gw_local = os.path.join(session_home, ".local")
        if os.path.isdir(real_local) and not os.path.exists(gw_local) and not os.path.islink(gw_local):
            os.symlink(real_local, gw_local)
        # 仅暴露 Keychain 依赖，避免把整个 ~/Library 带进 Claude session。
        _link_claude_library_entries(session_home)
        _link_shared_dotfiles(session_home)
        # .claude/ 目录：创建真实目录，只按 allowlist 暴露可继承项。
        session_claude_dir = os.path.join(session_home, ".claude")
        _prepare_claude_session_tree(
            session_home,
            session_claude_dir,
            account_id=account.get("id", ""),
            account_home=home_dir,
            runtime_kind="oauth",
            skip_real_entries={"settings.json"},
            source_claude_dir=account_claude_dir,
            allowed_source_entries=_CLAUDE_OAUTH_SESSION_SOURCE_ENTRY_ALLOWLIST,
        )
        _overlay_web_access_session_entries(session_claude_dir, session_home)
        _scrub_claude_oauth_env(env)
        env["HOME"] = session_home
        _set_session_home_hint(env, session_home)
    elif cli_name == "gemini":
        seed_gemini_state(home_dir)
        _scrub_claude_oauth_env(env)
        env["GEMINI_CLI_HOME"] = home_dir
    else:
        # codex 等其他 CLI：per-PID 会话隔离
        sessions_dir = os.path.join(home_dir, "s")
        session_home = os.path.join(sessions_dir, str(os.getpid()))
        os.makedirs(session_home, exist_ok=True)
        _cleanup_stale_sessions(sessions_dir)
        # symlink home_dir 下的所有子项到 session_home
        for entry in os.listdir(home_dir):
            if entry == "s":
                continue
            src = os.path.join(home_dir, entry)
            dst = os.path.join(session_home, entry)
            if not os.path.exists(dst) and not os.path.islink(dst):
                os.symlink(src, dst)
        # symlink Library（macOS Keychain）
        real_library = _real_user_path("Library")
        session_library = os.path.join(session_home, "Library")
        if os.path.isdir(real_library) and not os.path.exists(session_library) and not os.path.islink(session_library):
            os.symlink(real_library, session_library)
        _link_shared_dotfiles(session_home)
        if cli_name == "codex":
            _scrub_claude_oauth_env(env)
            _sync_codex_session_claude_json(session_home)
            _overlay_codex_shared_resume(home_dir, session_home)
            _overlay_web_access_session_entries(os.path.join(session_home, ".codex"), session_home)
        xdg_config_home = os.path.join(session_home, ".config")
        env["HOME"] = session_home
        env["XDG_CONFIG_HOME"] = xdg_config_home
        _set_session_home_hint(env, session_home)
        _install_session_command_wrappers(session_home, env)
    _apply_runtime_network_profile(env, account, validate_proxy=validate_proxy)
    env["MMS_ACCOUNT_ID"] = str(account.get("id", ""))
    if cli_name == "claude":
        _persist_account_guard_launch(
            account.get("id", ""),
            account.get("_account_guard_report", {}),
            session_home=env.get("HOME", ""),
        )
    return env


def _overlay_codex_shared_resume(home_dir, session_home):
    account_codex_dir = os.path.join(home_dir, ".codex")
    if not os.path.isdir(account_codex_dir):
        return

    session_codex_dir = os.path.join(session_home, ".codex")
    if os.path.islink(session_codex_dir):
        os.unlink(session_codex_dir)
    os.makedirs(session_codex_dir, exist_ok=True)

    shared_entries = {
        "archived_sessions",
        "history.jsonl",
        "session_index.jsonl",
        "sessions",
        "shell_snapshots",
    }
    for entry in os.listdir(account_codex_dir):
        if entry in shared_entries:
            continue
        src = os.path.join(account_codex_dir, entry)
        dst = os.path.join(session_codex_dir, entry)
        if not os.path.exists(dst) and not os.path.islink(dst):
            os.symlink(src, dst)

    real_codex_dir = _real_user_path(".codex")
    for entry in shared_entries:
        source_root = real_codex_dir if os.path.isdir(real_codex_dir) else account_codex_dir
        src = os.path.join(source_root, entry)
        dst = os.path.join(session_codex_dir, entry)
        if (not os.path.exists(src) and not os.path.islink(src)) or os.path.exists(dst) or os.path.islink(dst):
            continue
        os.symlink(src, dst)


def _link_shared_dotfiles(session_home):
    """Expose user-level Git/SSH config inside isolated HOME sessions."""
    real_home = _real_user_home()
    for dot_name in (".ssh", ".gitconfig", ".gitignore_global"):
        src = os.path.join(real_home, dot_name)
        dst = os.path.join(session_home, dot_name)
        if os.path.exists(src) and not os.path.exists(dst) and not os.path.islink(dst):
            os.symlink(src, dst)


def _link_claude_library_entries(session_home, entries=_CLAUDE_SESSION_LIBRARY_ENTRY_ALLOWLIST):
    real_library = _real_user_path("Library")
    if not os.path.isdir(real_library):
        return

    session_library = os.path.join(session_home, "Library")
    if os.path.islink(session_library):
        try:
            os.unlink(session_library)
        except OSError:
            return
    os.makedirs(session_library, exist_ok=True)

    for entry in entries:
        normalized = str(entry or "").strip()
        if not normalized:
            continue
        src = os.path.join(real_library, normalized)
        dst = os.path.join(session_library, normalized)
        if (not os.path.exists(src) and not os.path.islink(src)) or os.path.exists(dst) or os.path.islink(dst):
            continue
        os.symlink(src, dst)


def _filter_real_home_wrapper_path(path_value):
    raw_path = str(path_value or "")
    if not raw_path:
        return ""
    session_home = os.path.abspath(os.path.expanduser(str(os.environ.get("HOME") or "").strip()))
    real_home = os.path.abspath(os.path.expanduser(_real_user_home()))
    strip_session_entries = bool(session_home) and session_home != real_home
    filtered = []
    for part in raw_path.split(os.pathsep):
        normalized = os.path.abspath(os.path.expanduser(str(part or "").strip()))
        if not normalized:
            continue
        if normalized.endswith(os.path.join(".mms", "bin")):
            continue
        if strip_session_entries and normalized.startswith(session_home + os.sep):
            continue
        filtered.append(part)
    return os.pathsep.join(filtered)


def _install_session_command_wrappers(session_home, env):
    """Install wrappers for tools that must run against the real HOME."""
    wrapper_dir = os.path.join(session_home, ".mms", "bin")
    os.makedirs(wrapper_dir, exist_ok=True)

    real_home = _real_user_home()
    current_path = _filter_real_home_wrapper_path(os.environ.get("PATH", ""))
    wrapper_path_env = json.dumps(current_path or os.defpath)
    xdg_config_home = json.dumps(_real_user_path(".config"))
    xdg_cache_home = json.dumps(_real_user_path(".cache"))
    xdg_data_home = json.dumps(_real_user_path(".local", "share"))
    xdg_state_home = json.dumps(_real_user_path(".local", "state"))
    for command_name in _SESSION_REAL_HOME_WRAPPER_COMMANDS:
        wrapper_path = os.path.join(wrapper_dir, command_name)
        extra_exports = []
        if command_name == "gh":
            extra_exports.append(f'export GH_CONFIG_DIR={json.dumps(_real_user_path(".config", "gh"))}')
        if command_name == "pm2":
            extra_exports.append(f'export PM2_HOME={json.dumps(_real_user_path(".pm2"))}')
        wrapper = "\n".join(
            [
                "#!/bin/sh",
                f'export HOME={json.dumps(real_home)}',
                f'export MMS_REAL_HOME={json.dumps(real_home)}',
                f'export REAL_HOME={json.dumps(real_home)}',
                f'export ORIGINAL_HOME={json.dumps(real_home)}',
                f"export PATH={wrapper_path_env}",
                f"export XDG_CONFIG_HOME={xdg_config_home}",
                f"export XDG_CACHE_HOME={xdg_cache_home}",
                f"export XDG_DATA_HOME={xdg_data_home}",
                f"export XDG_STATE_HOME={xdg_state_home}",
                *_real_home_wrapper_scrub_lines(),
                *extra_exports,
                f'real_bin="$(command -v {json.dumps(command_name)} 2>/dev/null || true)"',
                'if [ -z "$real_bin" ]; then',
                f'  printf "%s\\n" "mms: command {command_name} not found in real HOME PATH" >&2',
                "  exit 127",
                "fi",
                'exec "$real_bin" "$@"',
                "",
            ]
        )
        with open(wrapper_path, "w", encoding="utf-8") as handle:
            handle.write(wrapper)
        os.chmod(wrapper_path, 0o755)

    session_path = env.get("PATH") or current_path
    env["PATH"] = wrapper_dir + os.pathsep + session_path if session_path else wrapper_dir


def _resolve_real_home_command_path(command_name, env=None):
    command_name = str(command_name or "").strip()
    if not command_name:
        return ""
    path_value = ""
    if isinstance(env, dict):
        path_value = str(env.get("PATH") or "").strip()
    if not path_value:
        path_value = os.environ.get("PATH", "")
    filtered_path = _filter_real_home_wrapper_path(path_value) or os.defpath
    return shutil.which(command_name, path=filtered_path) or ""


def _mmc_entry_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "mmc")


def _assert_safe_mmc_delegate_binary(path_value, *, label):
    normalized = os.path.realpath(str(path_value or "").strip())
    if not normalized:
        console.print(f"[red]缺少 {label} binary[/red]")
        sys.exit(1)
    forbidden_parts = ("/.mms/", "/.config/mms/", "/ccswitch", "/hive")
    lowered = normalized.lower()
    for token in forbidden_parts:
        if token.lower() in lowered:
            console.print(f"[red]{label} binary 命中禁止路径: {normalized}[/red]")
            sys.exit(1)
    if not os.path.isabs(normalized) or not os.path.exists(normalized):
        console.print(f"[red]{label} binary 非法: {normalized}[/red]")
        sys.exit(1)
    return normalized


def _build_mmc_delegate_env():
    env = {}
    for key in ("TERM", "COLORTERM"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            env[key] = value
    env["PATH"] = os.pathsep.join(
        (
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
            "/opt/homebrew/bin",
            "/usr/local/bin",
        )
    )
    env["MMC_REAL_HOME"] = _real_user_home()
    return env


def _mmc_launch_env_overrides(model_info, runtime, *, enable_claude_1m=True):
    if isinstance(model_info, dict):
        if model_info.get("lb_light") or model_info.get("lb_medium"):
            console.print("[red]OAuth Claude 已切到 MMC 隔离模式，不再支持 load-balance / bridge 路线[/red]")
            sys.exit(1)
        resolved_model = _resolve_model(model_info)
    else:
        resolved_model = _resolve_model(model_info)

    resolved_model = str(resolved_model or "claude-sonnet-4-6").strip() or "claude-sonnet-4-6"
    resolved_lower = resolved_model.lower()
    if not any(token in resolved_lower for token in ("claude", "opus", "sonnet", "haiku")):
        console.print(f"[red]OAuth Claude 仅支持 Claude family 模型，当前选择不允许: {resolved_model}[/red]")
        sys.exit(1)

    env = {
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "API_TIMEOUT_MS": "3000000",
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
    }
    _apply_claude_model_overrides(env, model_info or resolved_model, enable_1m=enable_claude_1m)
    if isinstance(model_info, dict):
        env["CLAUDE_CODE_ENABLE_SUBAGENT_PARALLELISM"] = "1"
        env["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"] = "5"

    ctx_window = _effective_context_window(
        resolved_model,
        enable_claude_1m=enable_claude_1m,
        provider_id=(runtime or {}).get("id"),
    )
    env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(ctx_window)
    env["CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE"] = str(max(ctx_window - 3000, 10000))
    return env


def _exit_oauth_claude_manual_only(runtime=None, model_info=None, *, caller="MMS"):
    runtime = runtime if isinstance(runtime, dict) else {}
    runtime_label = (
        str(runtime.get("id") or runtime.get("name") or runtime.get("cli") or "claude-oauth").strip()
        or "claude-oauth"
    )
    model_name = _resolve_model(model_info) if model_info else ""
    model_name = str(model_name or "").strip() or "claude-sonnet-4-6"
    console.print("[red]已阻止 OAuth Claude 自动进入。[/red]")
    console.print(
        "[yellow]OAuth Claude 现在是 manual-only 保护面：MMS / MMC / Hive / fallback / 子进程都不能自动启动它。[/yellow]"
    )
    console.print(f"[dim]入口: {caller} · runtime={runtime_label} · model={model_name}[/dim]")
    console.print("[dim]允许的唯一入口：你自己在 real/global shell 手动输入 `claude`，并先跑你的验证脚本。[/dim]")
    raise SystemExit(_CLAUDE_OAUTH_MANUAL_ONLY_EXIT_CODE)


def _launch_claude_oauth_via_mmc(model_info, runtime, once=False, *, enable_claude_1m=True):
    _exit_oauth_claude_manual_only(runtime, model_info, caller="MMS->MMC")
    mmc_entry = _mmc_entry_path()
    if not os.path.exists(mmc_entry):
        console.print(f"[red]未找到 MMC 入口: {mmc_entry}[/red]")
        sys.exit(1)

    workspace = os.path.realpath(os.getcwd())
    locale_env = _runtime_locale_env(runtime)
    timezone_name = _validate_timezone_or_exit(
        runtime.get("timezone") or DEFAULT_ACCOUNT_TIMEZONE,
        label=str(runtime.get("id") or runtime.get("name") or runtime.get("cli") or "claude-oauth"),
    )
    launch_env = _mmc_launch_env_overrides(
        model_info,
        runtime,
        enable_claude_1m=enable_claude_1m,
    )
    if _runtime_force_ipv4(runtime):
        console.print("[red]OAuth Claude / MMC 路线已禁用 force_ipv4 注入；请改系统网络层，不再透传 NODE_OPTIONS[/red]")
        sys.exit(1)
    claude_bin = _assert_safe_mmc_delegate_binary(
        _resolve_real_home_command_path("claude"),
        label="claude",
    )
    node_bin = _assert_safe_mmc_delegate_binary(
        _resolve_real_home_command_path("node"),
        label="node",
    )

    cmd = [sys.executable, mmc_entry, "run", "--workspace", workspace]
    cmd.extend(["--claude-bin", claude_bin, "--node-bin", node_bin])
    proxy_url = str(runtime.get("proxy") or "").strip()
    if proxy_url:
        cmd.extend(["--proxy", proxy_url])
    no_proxy = str(runtime.get("no_proxy") or "").strip()
    if no_proxy:
        cmd.extend(["--no-proxy", no_proxy])
    for flag, value in (
        ("--lang", locale_env.get("LANG")),
        ("--lc-all", locale_env.get("LC_ALL")),
        ("--lc-ctype", locale_env.get("LC_CTYPE")),
        ("--lc-messages", locale_env.get("LC_MESSAGES")),
        ("--tz", timezone_name),
    ):
        if str(value or "").strip():
            cmd.extend([flag, str(value).strip()])
    if runtime.get("bypass"):
        cmd.extend(["--allow-dir", workspace, "--bypass"])
    for key, value in launch_env.items():
        if str(value or "").strip():
            cmd.extend(["--set-env", f"{key}={value}"])

    env = _build_mmc_delegate_env()

    console.print("[dim]⏳ OAuth Claude 已委托给 MMC 隔离启动...[/dim]")
    _exec_or_run(cmd, env, once)


def _sync_codex_session_claude_json(session_home):
    """Seed isolated Codex HOME with the real user's MCP-capable .claude.json."""
    import json as _json

    real_json = _real_user_path(".claude.json")
    if not os.path.exists(real_json):
        return

    session_json = os.path.join(session_home, ".claude.json")
    if os.path.islink(session_json):
        return

    try:
        with open(real_json, "r", encoding="utf-8") as f:
            loaded = _json.load(f)
        if not isinstance(loaded, dict):
            return
        data = _sanitize_codex_claude_state_payload(loaded)
    except Exception:
        return

    if os.path.exists(session_json):
        try:
            with open(session_json, "r", encoding="utf-8") as f:
                existing = _json.load(f)
            if isinstance(existing, dict):
                # Keep per-session metadata stable while inheriting global MCP servers.
                if "firstStartTime" in existing:
                    data["firstStartTime"] = existing["firstStartTime"]
                if "bypassPermissionsModeAccepted" in existing:
                    data["bypassPermissionsModeAccepted"] = existing["bypassPermissionsModeAccepted"]
        except Exception:
            pass

    with locked_state_file(session_json):
        atomic_write_json(session_json, data, mode=0o600)


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


def _append_codex_mcp_servers_from_claude_json(config_text):
    """Translate Claude-style mcpServers into Codex [mcp_servers.*] sections."""
    import json as _json
    import re

    real_json = _real_user_path(".claude.json")
    if not os.path.exists(real_json):
        return config_text

    try:
        with open(real_json, "r", encoding="utf-8") as f:
            loaded = _json.load(f)
        servers = loaded.get("mcpServers", {}) if isinstance(loaded, dict) else {}
    except Exception:
        return config_text

    if not isinstance(servers, dict) or not servers:
        return config_text

    existing = set()
    pattern = re.compile(r'^\[mcp_servers\.(?:"([^"]+)"|([A-Za-z0-9_-]+))\]\s*$', flags=re.MULTILINE)
    for match in pattern.finditer(config_text):
        existing.add(match.group(1) or match.group(2))

    blocks = []
    for name, spec in servers.items():
        if name in existing or not isinstance(spec, dict):
            continue

        section_name = _toml_bare_key(name)
        lines = [f"[mcp_servers.{section_name}]"]

        url = spec.get("url")
        command = spec.get("command")
        if isinstance(url, str) and url.strip():
            lines.append(f"url = {_toml_quote(url)}")
            bearer_token_env_var = spec.get("bearer_token_env_var")
            if isinstance(bearer_token_env_var, str) and bearer_token_env_var.strip():
                lines.append(f"bearer_token_env_var = {_toml_quote(bearer_token_env_var)}")
        elif isinstance(command, str) and command.strip():
            lines.append(f"command = {_toml_quote(command)}")
            args = spec.get("args")
            if isinstance(args, list):
                rendered_args = ", ".join(_toml_quote(arg) for arg in args)
                lines.append(f"args = [{rendered_args}]")
            env = spec.get("env")
            if isinstance(env, dict):
                env_lines = []
                for env_key in sorted(env):
                    env_value = env[env_key]
                    if isinstance(env_value, (str, int, float, bool)):
                        env_lines.append(f"{_toml_bare_key(env_key)} = {_toml_quote(env_value)}")
                if env_lines:
                    lines.append("")
                    lines.append(f"[mcp_servers.{section_name}.env]")
                    lines.extend(env_lines)
        else:
            continue

        blocks.append("\n".join(lines))

    if not blocks:
        return config_text

    config_text = config_text.rstrip()
    if config_text:
        config_text += "\n\n"
    return config_text + "\n\n".join(blocks) + "\n"


def validate_account_for_cli(cli, account):
    account_id = account.get("id", "account")
    account_cli = account.get("cli")
    if cli not in OAUTH_CAPABLE_CLIS:
        console.print(f"[red]{cli} 当前不支持 OAuth 账号档案[/red]")
        sys.exit(1)
    if not account.get("enabled", True):
        console.print(f"[red]账号档案 '{account_id}' 已禁用[/red]")
        sys.exit(1)
    if account_cli and account_cli != cli:
        console.print(f"[red]账号档案 '{account_id}' 绑定的是 {account_cli}，不能用于 {cli}[/red]")
        sys.exit(1)
    if not str(account.get("home_dir", "")).strip():
        console.print(f"[red]账号档案 '{account_id}' 缺少 home_dir[/red]")
        sys.exit(1)


def _openai_base_url(provider):
    explicit = str(provider.get("openai_base_url", "")).strip().rstrip("/")
    if explicit:
        return explicit
    base_url = str(provider.get("base_url", "")).strip().rstrip("/")
    if not base_url:
        return ""
    if base_url.endswith("/v1"):
        return base_url
    return f"{base_url}/v1"


def _anthropic_base_url(provider):
    explicit = str(provider.get("anthropic_base_url", "")).strip().rstrip("/")
    if explicit:
        return explicit
    if "anthropic_messages" not in _provider_protocols(provider):
        return ""
    return str(provider.get("base_url", "")).strip().rstrip("/")


def _resolve_model(model_info):
    """从 model_info dict 中提取 model 名称（单模型场景）"""
    if isinstance(model_info, str):
        return model_info
    return model_info.get("model", model_info.get("sonnet", ""))


def _normalized_model_name(model_name):
    if not isinstance(model_name, str):
        return ""
    return model_name.strip()


def _claude_resume_model_name(*candidates):
    for candidate in candidates:
        normalized = _normalized_model_name(candidate)
        if normalized:
            return normalized
    return ""


def _primary_claude_model(model_info):
    if isinstance(model_info, dict):
        for key in ("model", "sonnet", "opus", "haiku"):
            value = _normalized_model_name(model_info.get(key))
            if value:
                return value
        return ""
    return _normalized_model_name(model_info)


def _with_1m_suffix(model_name, *, enable_1m=True):
    """对 opus/sonnet Claude 模型追加 [1m] 后缀以启用 1M context。
    Haiku 不支持 1M。非 Claude 模型原样返回。
    Claude Code 会在 API 请求前自动剥离 [1m]，不影响 bridge/proxy。
    """
    if not enable_1m:
        return model_name
    if not model_name or "[1m]" in model_name:
        return model_name
    lower = model_name.lower()
    # opus 和 sonnet 支持 1M context
    if any(k in lower for k in ("opus", "sonnet")) and "haiku" not in lower:
        return model_name + "[1m]"
    return model_name


def _apply_claude_model_overrides(target, model_info, *, enable_1m=True):
    primary_model = _primary_claude_model(model_info)
    if not primary_model:
        return ""

    if isinstance(model_info, dict):
        opus_model = _normalized_model_name(model_info.get("opus")) or primary_model
        sonnet_model = _normalized_model_name(model_info.get("sonnet")) or primary_model
        haiku_model = _normalized_model_name(model_info.get("haiku")) or primary_model
        target["ANTHROPIC_DEFAULT_OPUS_MODEL"] = _with_1m_suffix(opus_model, enable_1m=enable_1m)
        target["ANTHROPIC_DEFAULT_SONNET_MODEL"] = _with_1m_suffix(sonnet_model, enable_1m=enable_1m)
        target["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = haiku_model  # haiku 不支持 1M
        target["ANTHROPIC_MODEL"] = _with_1m_suffix(primary_model, enable_1m=enable_1m)
        target["ANTHROPIC_REASONING_MODEL"] = _with_1m_suffix(
            sonnet_model or primary_model,
            enable_1m=enable_1m,
        )
        subagent_model = _normalized_model_name(model_info.get("subagent")) or sonnet_model or primary_model
        target["CLAUDE_CODE_SUBAGENT_MODEL"] = _with_1m_suffix(
            subagent_model,
            enable_1m=enable_1m,
        )
        return primary_model

    primary_1m = _with_1m_suffix(primary_model, enable_1m=enable_1m)
    for key in (
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_REASONING_MODEL",
        "CLAUDE_CODE_SUBAGENT_MODEL",
    ):
        target[key] = primary_1m
    target["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = primary_model  # haiku slot 不加 [1m]
    return primary_model


def launch_claude(model_info, runtime, once=False):
    """启动 Claude Code，支持 provider 和 OAuth 账号档案两种模式。"""
    _ensure_bridge_helpers()
    _ensure_speed_stats()
    auth_mode = runtime.get("auth_mode", "api_key")
    enable_claude_1m = _runtime_supports_claude_1m(runtime)
    advertised_models = []
    bridge_cfg = None  # 由 gateway_claude_bridge 赋值，用于退出摘要
    probe_model = _resolve_model(model_info) if model_info else "claude-sonnet-4-6"
    lb_light = model_info.get("lb_light") if isinstance(model_info, dict) else None
    lb_medium = model_info.get("lb_medium") if isinstance(model_info, dict) else None
    lb_light = lb_light if lb_light and lb_light.strip() else None
    lb_medium = lb_medium if lb_medium and lb_medium.strip() else None
    if auth_mode == "oauth_bridge":
        console.print("[red]官方桥接已临时禁用，避免 Gemini/Codex 请求进入 Claude session。[/red]")
        sys.exit(1)
    if auth_mode == "oauth":
        _exit_oauth_claude_manual_only(runtime, model_info, caller="launch_claude")
    else:
        provider_id = runtime.get("id", "default")
        if runtime.get("skip_gateway_health_check"):
            console.print("[dim]· 跳过 gateway 健康检查（provider 配置）[/dim]")
        elif not _health_check_due(provider_id):
            console.print("[dim]· 跳过 gateway 健康检查（24h 缓存有效）[/dim]")
        else:
            with _launch_status("健康检查中...", spinner="dots") as step_start:
                gateway_health_check(runtime)
            _print_launch_step_done("gateway 健康检查", step_start)

        speed_scope = build_provider_speed_scope(runtime)
        route_status_paths = _claude_route_status_paths()
        probe_result = runtime.get("_launch_prefetched_probe")
        if probe_result is None:
            try:
                with _launch_status("读取模型列表中...", spinner="dots") as step_start:
                    probe_result = _probe_models(runtime, emit_output=False)
                    advertised_models = list(probe_result.get("models") or [])
            except Exception:
                advertised_models = []
            if probe_result is None:
                console.print("[yellow]· 模型列表准备失败，继续使用空列表[/yellow]")
            else:
                base_source = probe_result.get("base_source")
                detail = f"{len(advertised_models)} 个模型"
                if base_source:
                    detail += f" · {base_source}"
                _print_launch_step_done("模型列表准备", step_start, detail)
        else:
            advertised_models = list(probe_result.get("models") or [])
            base_source = probe_result.get("base_source")
            detail = f"{len(advertised_models)} 个模型"
            if base_source:
                detail += f" · {base_source} · 复用预读取"
            else:
                detail += " · 复用预读取"
            console.print(f"[dim]· 模型列表准备跳过远端请求 ({detail})[/dim]")

        # ---- 三级兼容策略 ----
        # 1. 自动探测正确的 ANTHROPIC_BASE_URL（缓存 1h，避免重复请求）
        probe_model = _resolve_model(model_info) if model_info else "claude-sonnet-4-6"

        # 对不支持 Claude 模型的 provider，自动映射到支持的模型
        provider_id = runtime.get("id", "")
        strip_upstream_user_agent = "cliproxyapi" in provider_id.lower()
        minimal_claude_header_passthrough = _runtime_is_sensitive_claude_provider(runtime)
        if provider_id == "bailian-codingplan" and probe_model.startswith(("claude-", "sonnet-", "opus-", "haiku-")):
            # 百炼 CodingPlan 不支持 Claude 模型，使用其支持的 fallback 模型
            probe_model = "qwen3.5-plus"
            console.print(f"[dim]百炼 CodingPlan 不支持 Claude 模型，自动切换为: {probe_model}[/dim]")

        with _launch_status("解析 Anthropic endpoint 中...", spinner="dots") as step_start:
            anthropic_url, detect_method = _resolve_anthropic_base_url(runtime, probe_model=probe_model)
        resolve_detail = detect_method
        if anthropic_url:
            resolve_detail = f"{detect_method} · {anthropic_url}"
            _print_launch_step_done("Anthropic endpoint 解析", step_start, resolve_detail)
        else:
            _print_launch_step_done("Anthropic endpoint 解析", step_start, resolve_detail, style="yellow")

        # 跨 provider 负载配置：per-slot upstream url/key
        lb_slot_configs = model_info.get("lb_slot_configs") if isinstance(model_info, dict) else None

        # GPT-on-Claude: 获取 OpenAI URL 供 bridge 转发 GPT 模型
        _gpt_openai_url = _openai_base_url(runtime) or None
        # Claude Code 内部 NM() 只认识 Claude 模型的 context window。
        # 非 Claude 模型走 bridge 替换，env slot 用 Claude 壳名让 NM() 返回 1M，
        # 然后 CLAUDE_CODE_AUTO_COMPACT_WINDOW 按实际模型 context 往下 cap。
        # 路由状态栏仍显示真实模型名。
        _is_claude = any(k in probe_model.lower() for k in ("claude", "opus", "sonnet", "haiku"))
        if _gpt_openai_url and _is_gpt_model(probe_model):
            _env_model = "claude-sonnet-4-6"
        elif not _is_claude:
            _env_model = "claude-sonnet-4-6"
        else:
            _env_model = probe_model
        # 当使用 Claude 壳名时，保留真实模型名供 status line 显示
        _display_model = probe_model if _env_model != probe_model else None

        # GPT 模型走 Responses API，提前询问 reasoning effort（所有分支共用）
        if _gpt_openai_url and _is_gpt_model(probe_model):
            from mms_tui import select_reasoning_effort_tui as _sel_effort_claude
            _reasoning_effort = _sel_effort_claude(default="high")
            console.print(f"[dim]reasoning effort: {_reasoning_effort}[/dim]")
        else:
            _reasoning_effort = "high"

        if anthropic_url is not None:
            bridge_gw_url = anthropic_url.rstrip("/")
            if not bridge_gw_url.endswith("/v1"):
                bridge_gw_url += "/v1"
            if lb_light or lb_medium:
                # 智能路由：通过本地 bridge 路由，以便拦截并切换模型
                cleanup_ctx = _gateway_claude_bridge_context(bridge_gw_url, runtime["api_key"],
                                                    heavy_model=probe_model,
                                                    medium_model=lb_medium or None,
                                                    light_model=lb_light or None,
                                                    advertised_models=advertised_models,
                                                    speed_scope=speed_scope,
                                                    route_status_paths=route_status_paths,
                                                    slot_configs=lb_slot_configs,
                                                    openai_url=_gpt_openai_url,
                                                    proxy_url=runtime.get("proxy"),
                                                    no_proxy=runtime.get("no_proxy"),
                                                    strip_upstream_user_agent=strip_upstream_user_agent,
                                                    minimal_claude_header_passthrough=minimal_claude_header_passthrough,
                                                    reasoning_effort=_reasoning_effort)
                bridge_cfg = cleanup_ctx.__enter__()
                env = _prepare_claude_env_with_status(
                    runtime,
                    base_url=bridge_cfg["base_url"],
                    auth_token=bridge_cfg["api_key"],
                    heavy_model=_env_model,
                    medium_model=lb_medium or None,
                    light_model=lb_light or None,
                    selected_model=_env_model,
                    display_model=_display_model,
                )
                parts = [f"heavy: {probe_model}"]
                if lb_medium:
                    parts.append(f"medium: {lb_medium}")
                if lb_light:
                    parts.append(f"light: {lb_light}")
                if lb_slot_configs:
                    parts.append("跨provider")
                console.print(f"[dim]⚖️ 智能路由已启用 — {', '.join(parts)}[/dim]")
            else:
                # 直连 Anthropic provider 也统一过本地 bridge，补齐测速与 patched /v1/models。
                cleanup_ctx = _gateway_claude_bridge_context(
                    bridge_gw_url,
                    runtime["api_key"],
                    heavy_model=probe_model,
                    advertised_models=advertised_models,
                    speed_scope=speed_scope,
                    route_status_paths=route_status_paths,
                    openai_url=_gpt_openai_url,
                    proxy_url=runtime.get("proxy"),
                    no_proxy=runtime.get("no_proxy"),
                    strip_upstream_user_agent=strip_upstream_user_agent,
                    minimal_claude_header_passthrough=minimal_claude_header_passthrough,
                    reasoning_effort=_reasoning_effort,
                )
                bridge_cfg = cleanup_ctx.__enter__()
                env = _prepare_claude_env_with_status(
                    runtime,
                    base_url=bridge_cfg["base_url"],
                    auth_token=bridge_cfg["api_key"],
                    heavy_model=_env_model,
                    selected_model=_env_model,
                    display_model=_display_model,
                )
            state_home = None

        elif runtime.get("bridge_source_cli"):
            # 2. Anthropic 端点不通，但配置了 bridge_source_cli → 自动切 bridge 模式
            bridge_src = runtime["bridge_source_cli"]
            console.print(
                f"[yellow]⚠ Anthropic 端点探测失败，自动切换到 {bridge_src} bridge 模式[/yellow]"
            )
            bridge_model = probe_model
            if bridge_src == "gemini":
                cleanup_ctx = gemini_claude_bridge(runtime, bridge_model)
            else:
                cleanup_ctx = codex_claude_bridge(runtime, bridge_model)
            bridge_cfg = cleanup_ctx.__enter__()
            env = _prepare_claude_env_with_status(
                runtime,
                base_url=bridge_cfg["base_url"],
                auth_token=bridge_cfg["api_key"],
                heavy_model=probe_model,
                medium_model=lb_medium or None,
                light_model=lb_light or None,
                selected_model=probe_model,
            )
            state_home = None

        elif _gpt_openai_url and _is_gpt_model(probe_model):
            # 2a-gpt. GPT-on-Claude: Anthropic 探测失败但有 OpenAI URL 且是 GPT 模型
            #   → 用 OpenAI URL 起 bridge，bridge 内部走 Responses API 转发
            openai_url = _gpt_openai_url
            api_key = runtime.get("openai_api_key") or runtime.get("api_key", "")
            console.print(f"[dim]🔀 GPT-on-Claude: 通过 OpenAI 端点 bridge → Responses API (reasoning: {_reasoning_effort})[/dim]")
            cleanup_ctx = _gateway_claude_bridge_context(openai_url, api_key,
                                                heavy_model=probe_model,
                                                medium_model=lb_medium or None,
                                                light_model=lb_light or None,
                                                advertised_models=advertised_models,
                                                speed_scope=speed_scope,
                                                route_status_paths=route_status_paths,
                                                slot_configs=lb_slot_configs,
                                                openai_url=openai_url,
                                                proxy_url=runtime.get("proxy"),
                                                no_proxy=runtime.get("no_proxy"),
                                                strip_upstream_user_agent=strip_upstream_user_agent,
                                                minimal_claude_header_passthrough=minimal_claude_header_passthrough,
                                                reasoning_effort=_reasoning_effort)
            bridge_cfg = cleanup_ctx.__enter__()
            env = _prepare_claude_env_with_status(
                runtime,
                base_url=bridge_cfg["base_url"],
                auth_token=bridge_cfg["api_key"],
                heavy_model=_env_model,
                medium_model=lb_medium or None,
                light_model=lb_light or None,
                selected_model=_env_model,
                display_model=_display_model,
            )
            state_home = None

        elif _openai_base_url(runtime) and not _anthropic_base_url(runtime):
            # 2b. 纯 OpenAI provider（无 Anthropic 端点配置）→ 自动用 gateway bridge
            openai_url = _openai_base_url(runtime)
            api_key = runtime.get("openai_api_key") or runtime.get("api_key", "")
            console.print(
                f"[yellow]⚠ 无 Anthropic 端点，自动通过 OpenAI 端点 bridge[/yellow]"
            )
            cleanup_ctx = _gateway_claude_bridge_context(openai_url, api_key,
                                                heavy_model=probe_model,
                                                medium_model=lb_medium or None,
                                                light_model=lb_light or None,
                                                advertised_models=advertised_models,
                                                speed_scope=speed_scope,
                                                route_status_paths=route_status_paths,
                                                slot_configs=lb_slot_configs,
                                                openai_url=openai_url,
                                                proxy_url=runtime.get("proxy"),
                                                no_proxy=runtime.get("no_proxy"),
                                                strip_upstream_user_agent=strip_upstream_user_agent,
                                                minimal_claude_header_passthrough=minimal_claude_header_passthrough)
            bridge_cfg = cleanup_ctx.__enter__()
            env = _prepare_claude_env_with_status(
                runtime,
                base_url=bridge_cfg["base_url"],
                auth_token=bridge_cfg["api_key"],
                heavy_model=_env_model,
                medium_model=lb_medium or None,
                light_model=lb_light or None,
                selected_model=_env_model,
                display_model=_display_model,
            )
            parts = [f"heavy: {probe_model}"]
            if lb_medium:
                parts.append(f"medium: {lb_medium}")
            if lb_light:
                parts.append(f"light: {lb_light}")
            console.print(f"[dim]⚖️ 智能路由已启用 — {', '.join(parts)}[/dim]")
            state_home = None

        elif lb_light or lb_medium:
            # 3b. 探测失败但配置了负载均衡 → 用 OpenAI 端点 + bridge 启用智能路由
            console.print(
                f"[yellow]⚠ Anthropic 探测失败，但配置了负载均衡，用 OpenAI bridge 启用智能路由[/yellow]"
            )
            openai_url = _openai_base_url(runtime)
            api_key = runtime.get("openai_api_key") or runtime.get("api_key", "")
            if openai_url:
                cleanup_ctx = _gateway_claude_bridge_context(openai_url, api_key,
                                                    heavy_model=probe_model,
                                                    medium_model=lb_medium,
                                                    light_model=lb_light,
                                                    advertised_models=advertised_models,
                                                    speed_scope=speed_scope,
                                                    route_status_paths=route_status_paths,
                                                    slot_configs=lb_slot_configs,
                                                    openai_url=openai_url,
                                                    proxy_url=runtime.get("proxy"),
                                                    no_proxy=runtime.get("no_proxy"),
                                                    strip_upstream_user_agent=strip_upstream_user_agent,
                                                    minimal_claude_header_passthrough=minimal_claude_header_passthrough)
                bridge_cfg = cleanup_ctx.__enter__()
                env = _prepare_claude_env_with_status(
                    runtime,
                    base_url=bridge_cfg["base_url"],
                    auth_token=bridge_cfg["api_key"],
                    heavy_model=_env_model,
                    medium_model=lb_medium or None,
                    light_model=lb_light or None,
                    selected_model=_env_model,
                    display_model=_display_model,
                )
                parts = [f"heavy: {probe_model}"]
                if lb_medium:
                    parts.append(f"medium: {lb_medium}")
                if lb_light:
                    parts.append(f"light: {lb_light}")
                console.print(f"[dim]⚖️ 智能路由已启用 — {', '.join(parts)}[/dim]")
                state_home = None
            else:
                console.print("[red]✗ 无 OpenAI 端点，无法启用智能路由[/red]")
                env = _prepare_claude_env_with_status(runtime, base_url=None, selected_model=_env_model, display_model=_display_model)
                state_home = None
                cleanup_ctx = None

        else:
            # 3c. 探测失败且无 bridge 无负载均衡 → 保底继续
            console.print("[yellow]⚠ Anthropic 端点探测失败，尝试继续（可在 provider 配置 bridge_source_cli 启用自动降级）[/yellow]")
            env = _prepare_claude_env_with_status(runtime, base_url=None, selected_model=_env_model, display_model=_display_model)
            state_home = None
            cleanup_ctx = None

    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    env["API_TIMEOUT_MS"] = "3000000"

    # bridge 模式下跳过 model slot：Claude Code 用默认 claude-* 模型名通过校验，
    # bridge 在转发时替换成真实模型名（heavy_model / medium_model / light_model）。
    # GPT-on-Claude: OpenAI 模型名会被 Claude Code 拒绝，必须 skip，
    # bridge 层的 heavy_model 替换 + _forward_as_responses 会处理实际模型名。
    _resolved = _resolve_model(model_info) if model_info else ""
    _resolved_is_claude = any(k in (_resolved or "").lower() for k in ("claude", "opus", "sonnet", "haiku"))
    _skip_model = auth_mode == "oauth_bridge" or (
        isinstance(model_info, dict) and (model_info.get("lb_light") or model_info.get("lb_medium"))
    ) or (_resolved and _is_gpt_model(_resolved)) or (
        _resolved and not _resolved_is_claude  # 非 Claude 模型用壳名，跳过 slot 覆盖
    )

    if isinstance(model_info, dict):
        if not _skip_model:
            _apply_claude_model_overrides(env, model_info, enable_1m=enable_claude_1m)

        env["CLAUDE_CODE_ENABLE_SUBAGENT_PARALLELISM"] = "1"
        env["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"] = "5"
    elif not _skip_model:
        _apply_claude_model_overrides(env, model_info, enable_1m=enable_claude_1m)

    # ── Context window: 用真实模型名（probe_model）计算，非壳名 ──
    _real_models = [m for m in (probe_model, lb_medium, lb_light) if m]
    if not _real_models:
        _real_models = [_resolved or "claude-sonnet-4-6"]
    ctx_window = _effective_context_window(
        *_real_models,
        enable_claude_1m=enable_claude_1m,
        provider_id=(runtime or {}).get("id"),
    )
    env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(ctx_window)
    env["CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE"] = str(max(ctx_window - 3000, 10000))

    claude_bin = _resolve_real_home_command_path("claude", env) or "claude"
    cmd = [claude_bin]
    if runtime.get("bypass"):
        cmd += ["--add-dir", os.path.realpath(os.getcwd())]
        cmd.append("--dangerously-skip-permissions")
    console.print("[dim]⏳ 正在启动 Claude CLI...[/dim]")
    session_home = env.get("HOME")
    exit_callback = None
    if session_home:
        exit_callback = lambda exit_code: _finalize_claude_slot(session_home, exit_code=exit_code)
    _exec_or_run(
        cmd,
        env,
        once,
        state_home=state_home,
        cleanup_context=cleanup_ctx,
        exit_callback=exit_callback,
        force_subprocess=bool(exit_callback),
        bridge_info=bridge_cfg,
    )


def _resolve_anthropic_base_url(runtime, probe_model="claude-sonnet-4-6"):
    """
    自动探测并缓存 ANTHROPIC_BASE_URL（Claude Code SDK 所需格式）。

    Claude Code TypeScript SDK 固定使用路径 /v1/messages，因此：
      ANTHROPIC_BASE_URL = https://xxx       → SDK 请求 https://xxx/v1/messages  ✓
      ANTHROPIC_BASE_URL = https://xxx/v1    → SDK 请求 https://xxx/v1/v1/messages ✗

    探测顺序（优先去掉 /v1）：
      候选1: base_without_v1  （通常正确）
      候选2: base_with_v1     （少数兼容两种路径的 gateway）

    Returns: (base_url: str | None, method: str)
      method: 'cached' | 'probed' | 'fallback' | 'failed'
    """
    configured = _anthropic_base_url(runtime)
    api_key = runtime.get("api_key", "")
    provider_id = runtime.get("id", "default")

    if not configured or not api_key:
        return None, "no_config"

    # 预处理 URL
    url = configured.rstrip("/")
    normalized_url = url[:-3] if url.endswith("/v1") else url
    cache_key = _anthropic_cache_key(provider_id, url)

    # ---- 内存缓存（TTL 1h）----
    cached = _ANTHROPIC_URL_CACHE.get(cache_key)
    if cached:
        age = (datetime.now() - cached["ts"]).total_seconds()
        if age < 3600:
            return cached["url"], "cached"

    # ---- 文件缓存（跨进程，TTL 24h）----
    file_cached = _load_anthropic_url_file_cache().get(cache_key)
    if isinstance(file_cached, dict):
        cached_url = str(file_cached.get("url", "")).strip()
        cached_ts = str(file_cached.get("ts", "")).strip()
        if cached_url and cached_ts:
            try:
                age = (datetime.now() - datetime.fromisoformat(cached_ts)).total_seconds()
            except ValueError:
                age = 999999
            if age < 24 * 3600:
                _ANTHROPIC_URL_CACHE[cache_key] = {"url": cached_url, "ts": datetime.now()}
                return cached_url, "file_cached"

    # ---- 快速兼容：Claude SDK 自己会拼 /v1/messages，配置尾部 /v1 时直接裁掉 ----
    if url.endswith("/v1"):
        _remember_anthropic_url(provider_id, url, normalized_url)
        return normalized_url, "normalized"

    if provider_id and runtime.get("skip_anthropic_probe"):
        console.print("[dim]已跳过 Anthropic 端点探测，直接使用配置 URL[/dim]")
        _remember_anthropic_url(provider_id, url, url)
        return url, "config_bypass"

    if _runtime_is_sensitive_claude_provider(runtime):
        console.print("[dim]敏感 Claude provider：跳过 Anthropic 端点探测，直接使用配置 URL[/dim]")
        _remember_anthropic_url(provider_id, url, url)
        return url, "sensitive_bypass"

    # 对 bailian-codingplan，直接使用配置的 URL，不做探测（百炼 Anthropic 端点行为特殊）
    if provider_id == "bailian-codingplan":
        console.print(f"[dim]百炼 CodingPlan：跳过 Anthropic 端点探测，直接使用配置 URL[/dim]")
        _remember_anthropic_url(provider_id, url, url)
        return url, "bypass_for_bailian"

    # ---- 使用公共工具探测（复用 mms_core.detect_working_base_url）----
    # Claude Code SDK 固定追加 /v1/messages，所以探测路径是 /v1/messages
    probe_nonce = os.urandom(8).hex()
    body = json.dumps({
        "model": probe_model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
        "metadata": {
            "user_id": json.dumps({
                "device_id": f"device-{probe_nonce}",
                "session_id": f"session-{probe_nonce}",
            }, ensure_ascii=False),
        },
    }).encode()
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    candidate = detect_working_base_url(url, "/v1/messages", headers, body=body, timeout=5, runtime=runtime)

    if candidate is not None:
        _remember_anthropic_url(provider_id, url, candidate)
        if candidate != url:
            console.print(f"[dim]✓ Anthropic 端点自动修正: {url} → {candidate}[/dim]")
        return candidate, "probed"

    return None, "failed"


def _pick_gateway_model(runtime, base_url):
    """Fetch /models from gateway and return the best model ID for Claude slots.

    Priority: opus-4 > opus > sonnet-4 > sonnet > first available > None
    """
    try:
        import httpx as _httpx  # noqa: F401
    except ImportError:
        return None
    api_key = runtime.get("api_key", "")
    if not base_url or not api_key:
        return None
    url_v1 = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
    try:
        r = _runtime_httpx_request(
            "GET",
            f"{url_v1}/models",
            runtime=runtime,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8,
            follow_redirects=True,
        )
        if r.status_code != 200:
            return None
        models = [m.get("id", "") for m in r.json().get("data", [])]
    except Exception:
        return None
    if not models:
        return None
    for keyword in ("opus-4", "opus", "sonnet-4", "sonnet", "claude"):
        for m in models:
            if keyword in m.lower():
                return m
    # 没有匹配到任何 Claude 模型 → 返回 None，不把 gpt-* 等非 Claude 模型填入 slot
    return None


def _cleanup_stale_sessions(sessions_dir, stale_callback=None):
    """清理已死进程的残留 session 目录。"""
    if not os.path.isdir(sessions_dir):
        return
    for name in os.listdir(sessions_dir):
        stale = os.path.join(sessions_dir, name)
        if not os.path.isdir(stale):
            continue
        if _session_home_is_active(stale):
            continue
        if stale_callback is not None:
            try:
                stale_callback(stale, stale_cleanup=True)
            except Exception:
                pass
        shutil.rmtree(stale, ignore_errors=True)


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
    current_cwd = os.path.realpath(os.getcwd())
    normalized_account_id = str(account_id or "").strip()
    store = ensure_claude_project_store(current_cwd, account_id=normalized_account_id)
    skip_real_entries = set(skip_real_entries or ())
    allowed_source_entries = [
        str(entry).strip()
        for entry in (
            allowed_source_entries
            if allowed_source_entries is not None
            else _CLAUDE_SESSION_SOURCE_ENTRY_ALLOWLIST
        )
        if str(entry or "").strip()
    ]
    allowed_source_entry_set = set(allowed_source_entries)
    scoped_claude_dir = source_claude_dir or _real_user_path(".claude")
    if os.path.islink(session_claude_dir):
        os.unlink(session_claude_dir)
    os.makedirs(session_claude_dir, exist_ok=True)
    for entry in os.listdir(session_claude_dir):
        if entry in CLAUDE_PERSISTENT_ENTRIES or entry in allowed_source_entry_set:
            continue
        dst = os.path.join(session_claude_dir, entry)
        if os.path.islink(dst):
            try:
                os.unlink(dst)
            except OSError:
                pass
    if os.path.isdir(scoped_claude_dir):
        for entry in allowed_source_entries:
            if entry in skip_real_entries or entry in CLAUDE_PERSISTENT_ENTRIES:
                continue
            src = os.path.join(scoped_claude_dir, entry)
            dst = os.path.join(session_claude_dir, entry)
            if (not os.path.exists(src) and not os.path.islink(src)) or os.path.exists(dst) or os.path.islink(dst):
                continue
            os.symlink(src, dst)
    for entry in CLAUDE_PERSISTENT_ENTRIES:
        dst = os.path.join(session_claude_dir, entry)
        target = str(
            claude_raw_entry_path(
                entry,
                current_cwd,
                account_id=normalized_account_id,
            )
        )
        if not os.path.exists(dst) and not os.path.islink(dst):
            os.symlink(target, dst)
    record_claude_session_start(
        cwd=current_cwd,
        account_id=normalized_account_id,
        pid=os.getpid(),
        runtime_kind=runtime_kind,
        slot_home=session_home,
        resume_model=resume_model,
    )
    write_slot_marker(
        session_home,
        cwd=current_cwd,
        project_key_value=store["project_key"],
        account_id=normalized_account_id,
        runtime_kind=runtime_kind,
        account_home=account_home,
    )


def _sync_claude_session_state_to_account_home(session_home, account_home):
    import json as _json

    account_home = os.path.expanduser(str(account_home or "").strip())
    if not account_home:
        return

    os.makedirs(account_home, exist_ok=True)
    account_claude_dir = os.path.join(account_home, ".claude")
    os.makedirs(account_claude_dir, exist_ok=True)

    sync_pairs = [
        (
            os.path.join(session_home, ".claude.json"),
            os.path.join(account_home, ".claude.json"),
        ),
        (
            os.path.join(session_home, ".claude", "settings.json"),
            os.path.join(account_claude_dir, "settings.json"),
        ),
    ]
    for src, dst in sync_pairs:
        if not os.path.exists(src):
            continue
        try:
            if os.path.basename(dst) == "settings.json":
                with open(src, "r", encoding="utf-8") as f:
                    loaded = _json.load(f)
                cleaned = _sanitize_account_claude_settings_payload(loaded)
                with locked_state_file(dst):
                    atomic_write_json(dst, cleaned, mode=0o600)
            elif os.path.basename(dst) == ".claude.json":
                with open(src, "r", encoding="utf-8") as f:
                    incoming = _json.load(f)
                with locked_state_file(dst):
                    existing = _load_json_dict_unlocked(dst)
                    merged = _merge_oauth_claude_state_payload(existing, incoming)
                    atomic_write_json(dst, merged, mode=0o600)
            else:
                shutil.copy2(src, dst)
        except Exception:
            continue


def _finalize_claude_slot(session_home, exit_code=None, stale_cleanup=False):
    marker = read_slot_marker(session_home)
    if not marker:
        return
    try:
        pid = int(os.path.basename(str(session_home)))
    except (TypeError, ValueError):
        return
    cwd = marker.get("cwd") or os.getcwd()
    account_id = str(marker.get("account_id") or "").strip()
    account_home = str(marker.get("account_home") or "").strip()
    if not stale_cleanup:
        _sync_claude_session_state_to_account_home(session_home, account_home)
    finalize_claude_session(
        cwd=cwd,
        pid=pid,
        account_id=account_id,
        exit_code=exit_code,
        stale_cleanup=stale_cleanup,
    )
    _record_account_guard_finalize(
        account_id,
        exit_code=exit_code,
        stale_cleanup=stale_cleanup,
    )


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
):
    """Gateway api_key 模式独立 HOME（per-PID 会话隔离）：
    - 每个 mms 进程使用独立的 ~/.config/mms/claude-gateway/s/{pid}/ 作为 HOME
    - 启动时清理已死进程的残留目录
    - 剥离 migration 标记，防止 claude-sonnet-4-6[1m] 自动升级
    - 自动拉取 gateway 模型列表，填入所有 ANTHROPIC_*_MODEL slot
    - 写入 settings.json：teams 模式 / 隐藏 AI 署名 / 扩展思考
    base_url: 由 _resolve_anthropic_base_url() 探测后传入；
              为 None 时从 runtime 推断并去掉 /v1 后缀（保底兼容）。
    auth_token: 覆盖 ANTHROPIC_AUTH_TOKEN（bridge 模式传 bridge token）。
    heavy_model: bridge 模式下指定 heavy model，用于设置模型 slot。
    medium_model: bridge 模式下可选 medium model（仅用于展示）。
    light_model: bridge 模式下可选 light model（仅用于展示）。
    """
    import json as _json
    gateway_base = _real_user_path(".config", "mms", "claude-gateway")
    sessions_dir = os.path.join(gateway_base, "s")
    gateway_home, _active_before, _active_after = _reserve_session_home(
        sessions_dir,
        account_id=str(runtime.get("id", "")),
        runtime_kind=runtime_kind or str(runtime.get("auth_mode", "api_key")),
        stale_callback=_finalize_claude_slot,
    )
    route_status_path = _claude_route_status_paths()[0]
    os.makedirs(gateway_home, exist_ok=True)

    # 若调用方已通过 _resolve_anthropic_base_url 探测到正确 URL，直接用；
    # 否则保底剥离 /v1（避免双重 /v1/v1/messages）。
    if base_url is None:
        base_url = _anthropic_base_url(runtime)
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]

    # ── .claude.json：schema-based allowlist，避免未知 global 字段渗入 gateway session ──
    real_json = _real_user_path(".claude.json")
    gw_json = os.path.join(gateway_home, ".claude.json")
    data: dict = {}
    current_project = os.path.realpath(os.getcwd())
    current_project_state = _load_real_claude_project_state(current_project)
    resume_model = _claude_resume_model_name(display_model, selected_model, heavy_model)
    gw_existing = {}

    if os.path.exists(gw_json):
        try:
            with open(gw_json, encoding="utf-8") as f:
                loaded = _json.load(f)
            if isinstance(loaded, dict):
                gw_existing = loaded
            if (
                runtime.get("bypass")
                and isinstance(gw_existing, dict)
                and gw_existing.get("bypassPermissionsModeAccepted") is True
            ):
                data["bypassPermissionsModeAccepted"] = True
        except Exception:
            pass

    data = _merge_claude_ui_state_seed(data, _sanitize_claude_ui_state_seed_payload(gw_existing))
    data = _merge_claude_ui_state_seed(data, _load_real_claude_ui_state_seed())
    data = _inject_managed_mcp_servers_into_claude_state(data)

    # 当用户在 TUI 选择不 bypass 时，主动移除持久化的 bypass 状态，
    # 避免旧 session 残留的 bypassPermissionsModeAccepted 导致 Claude Code 自动进入 bypass
    if not runtime.get("bypass"):
        data.pop("bypassPermissionsModeAccepted", None)
    data["alwaysThinkingEnabled"] = True
    data = _ensure_claude_project_trust(
        data,
        current_project,
        project_state=current_project_state,
    )
    data = _overlay_project_scoped_claude_resume_state(
        data,
        current_project,
        account_id=str(runtime.get("id", "")),
        runtime_kind=runtime_kind or str(runtime.get("auth_mode", "api_key")),
        resume_model=resume_model,
    )
    with locked_state_file(gw_json):
        atomic_write_json(gw_json, data, mode=0o600)

    # ── .local symlink：Claude Code 检测 $HOME/.local/bin/claude（installMethod=native）──
    real_local = _real_user_path(".local")
    gw_local = os.path.join(gateway_home, ".local")
    if os.path.isdir(real_local) and not os.path.exists(gw_local) and not os.path.islink(gw_local):
        os.symlink(real_local, gw_local)

    # ── Library allowlist：仅保留 Keychain 依赖 ──
    _link_claude_library_entries(gateway_home)

    _link_shared_dotfiles(gateway_home)

    # ── ~/.claude 目录：仅保留 project-scoped 持久项，其余不再继承真实树 ──
    gw_claude_dir = os.path.join(gateway_home, ".claude")
    _prepare_claude_session_tree(
        gateway_home,
        gw_claude_dir,
        account_id=str(runtime.get("id", "")),
        runtime_kind=runtime_kind or str(runtime.get("auth_mode", "api_key")),
        resume_model=resume_model,
        skip_real_entries={"settings.json"},
    )
    report = runtime.get("_account_guard_report")
    if report:
        _persist_account_guard_launch(
            str(runtime.get("id", "")),
            report,
            session_home=gateway_home,
        )

    # ── settings.json：继承用户配置 + 覆盖 gateway 必要字段 ──
    effective_token = auth_token or runtime["api_key"]
    provider_id = runtime.get("id", "")
    enable_claude_1m = _runtime_supports_claude_1m(runtime)
    enable_caveman = _runtime_caveman_enabled(runtime)
    enable_ecc = _runtime_ecc_enabled(runtime)
    sensitive_provider = _runtime_is_sensitive_claude_provider(runtime)
    # 启动首帧优先写本次选中的真实模型名，避免 statusline / 初始 active model
    # 先落到 slot 占位名；bridge 仍负责把请求路由到实际目标模型。
    if auth_token:
        best_model = selected_model or heavy_model or "claude-sonnet-4-6"
    elif selected_model:
        best_model = selected_model
    elif provider_id == "bailian-codingplan":
        # 百炼 CodingPlan：使用其支持的模型名（如 qwen3.5-plus）
        fallback = runtime.get("fallback_models", [])
        best_model = fallback[0] if fallback else "qwen3.5-plus"
    else:
        best_model = _pick_gateway_model(runtime, base_url)
    required_settings_env: dict = {
        "ANTHROPIC_AUTH_TOKEN": effective_token,
        "ANTHROPIC_BASE_URL": base_url,
        "MMS_ROUTE_STATUS_PATH": route_status_path,
    }
    default_settings_env: dict = {
        "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
    }
    if sensitive_provider:
        required_settings_env["CLAUDE_CODE_DISABLE_1M_CONTEXT"] = "1"
    else:
        default_settings_env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
    if best_model:
        for key in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
                    "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                    "ANTHROPIC_REASONING_MODEL"):
            required_settings_env[key] = best_model
    if selected_model:
        _apply_claude_model_overrides(
            required_settings_env,
            selected_model,
            enable_1m=enable_claude_1m,
        )
    # 非 Claude 模型：ANTHROPIC_MODEL 用真实模型名让 status line 显示正确
    # 其余 DEFAULT_*_MODEL slot 保持 Claude 壳名供 Claude Code 内部 slot 匹配
    if display_model:
        required_settings_env["ANTHROPIC_MODEL"] = display_model
    _write_claude_session_settings(
        gw_claude_dir,
        required_env=required_settings_env,
        default_env=default_settings_env,
        enable_caveman=enable_caveman,
        enable_ecc=enable_ecc,
    )
    _overlay_caveman_session_entries(
        gw_claude_dir,
        gateway_home,
        enable_caveman=enable_caveman,
    )
    _overlay_ecc_session_entries(
        gw_claude_dir,
        gateway_home,
        enable_ecc=enable_ecc,
    )
    _overlay_web_access_session_entries(gw_claude_dir, gateway_home)

    env = os.environ.copy()
    _scrub_inherited_runtime_env(env, strip_openai=True, strip_proxy=True)
    _inject_real_home_hints(env)
    env["HOME"] = gateway_home
    _set_session_home_hint(env, gateway_home)
    env["ANTHROPIC_BASE_URL"] = base_url
    env["ANTHROPIC_AUTH_TOKEN"] = effective_token
    env["MMS_ROUTE_STATUS_PATH"] = route_status_path
    if sensitive_provider:
        env["CLAUDE_CODE_DISABLE_1M_CONTEXT"] = "1"
    if best_model:
        best_1m = _with_1m_suffix(best_model, enable_1m=enable_claude_1m)
        for key in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
                    "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_REASONING_MODEL"):
            env[key] = best_1m
        env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = best_model  # haiku 不支持 1M
    if selected_model:
        _apply_claude_model_overrides(env, selected_model, enable_1m=enable_claude_1m)
    if display_model:
        env["ANTHROPIC_MODEL"] = display_model
    if not sensitive_provider:
        env.setdefault("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    env = _configure_ecc_session_env(env, enable_ecc=enable_ecc)
    _apply_runtime_network_profile(
        env,
        runtime,
        validate_proxy=bool(runtime.get("proxy")),
    )
    _install_session_command_wrappers(gateway_home, env)

    # Context window 在 launch_claude() 中用真实模型名计算，此处不设置

    # ── 写入 route_status.json 供 statusline 读取 ──
    # bridge 模式下用 heavy_model，直连模式下用 best_model
    status_model = display_model or selected_model or heavy_model or best_model or "unknown"
    status_tier = "heavy" if auth_token else "-"
    status_reason = "init_selected_model" if selected_model else ("bridge_ready" if auth_token else "direct")
    _ensure_bridge_helpers()
    try:
        _write_route_status(status_tier, status_model, status_reason, status_paths=[route_status_path])
    except Exception:
        pass

    # ── health 预检摘要 ──
    try:
        _h = _get_model_health(status_model)
        if _h:
            _s = _h.get("status", "?")
            _b = _h.get("latency_bucket", "?")
            _icon = {"ok": "●", "slow": "◐", "degraded": "◑"}.get(_s, "?")
            print(f"  {_icon} {status_model}: {_s} ({_b})")
    except Exception:
        pass

    return env


def _codex_gateway_env(runtime, base_url):
    """为 gateway api_key 模式创建独立 HOME，per-PID session 隔离。"""
    import json as _json
    openai_key = runtime.get("openai_api_key") or runtime["api_key"]
    gateway_base = _real_user_path(".config", "mms", "codex-gateway")
    os.makedirs(gateway_base, exist_ok=True)

    # --- per-PID session 隔离（与 Claude gateway 对齐） ---
    sessions_dir = os.path.join(gateway_base, "s")
    session_home = os.path.join(sessions_dir, str(os.getpid()))
    os.makedirs(session_home, exist_ok=True)
    _cleanup_stale_sessions(sessions_dir)

    # symlink gateway_base 下的非 s 子项到 session_home
    for entry in os.listdir(gateway_base):
        if entry == "s":
            continue
        src = os.path.join(gateway_base, entry)
        dst = os.path.join(session_home, entry)
        if not os.path.exists(dst) and not os.path.islink(dst):
            os.symlink(src, dst)
    # symlink Library（macOS Keychain）
    real_library = _real_user_path("Library")
    session_library = os.path.join(session_home, "Library")
    if os.path.isdir(real_library) and not os.path.exists(session_library) and not os.path.islink(session_library):
        os.symlink(real_library, session_library)

    _link_shared_dotfiles(session_home)
    _sync_codex_session_claude_json(session_home)

    # --- .codex 目录：auth + config 写入 session，其余从真实 ~/.codex symlink ---
    codex_dir = os.path.join(session_home, ".codex")
    # 如果上面 symlink 了 gateway_base/.codex，先去掉，改成真目录
    if os.path.islink(codex_dir):
        os.unlink(codex_dir)
    os.makedirs(codex_dir, exist_ok=True)

    auth_path = os.path.join(codex_dir, "auth.json")
    with open(auth_path, "w") as f:
        _json.dump({"auth_mode": "apikey", "OPENAI_API_KEY": openai_key}, f)
    enable_caveman = _runtime_caveman_enabled(runtime)

    def _set_top_level_scalar(text, key, value):
        import re
        section_match = re.search(r'^\[', text, flags=re.MULTILINE)
        preamble_end = section_match.start() if section_match else len(text)
        preamble = text[:preamble_end]
        rest = text[preamble_end:]
        pattern = rf'^{re.escape(key)}\s*=\s*.+$'
        replacement = f'{key} = {_toml_literal(value)}'
        if re.search(pattern, preamble, flags=re.MULTILINE):
            preamble = re.sub(pattern, replacement, preamble, count=1, flags=re.MULTILINE)
        else:
            if preamble and not preamble.endswith("\n"):
                preamble += "\n"
            preamble += f"{replacement}\n"
        return preamble + rest

    def _set_project_base_url(text, project_path, value):
        import re
        escaped_path = re.escape(project_path)
        header_pattern = rf'^\[projects\."{escaped_path}"\]\s*$'
        match = re.search(header_pattern, text, flags=re.MULTILINE)
        if not match:
            block = f'\n[projects."{project_path}"]\nbase_url = {_toml_literal(value)}\n'
            return text.rstrip() + block + "\n"

        block_start = match.end()
        next_header = re.search(r'^\[', text[block_start:], flags=re.MULTILINE)
        block_end = block_start + next_header.start() if next_header else len(text)
        block = text[block_start:block_end]
        if re.search(r'^\s*base_url\s*=\s*"[^"]*"', block, flags=re.MULTILINE):
            block = re.sub(
                r'^\s*base_url\s*=\s*"[^"]*"',
                f'base_url = {_toml_literal(value)}',
                block,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            if not block.startswith("\n"):
                block = "\n" + block
            if block and not block.endswith("\n"):
                block += "\n"
            block += f'base_url = {_toml_literal(value)}\n'
        return text[:block_start] + block + text[block_end:]

    def _set_project_scalar(text, project_path, key, value):
        import re
        escaped_path = re.escape(project_path)
        header_pattern = rf'^\[projects\."{escaped_path}"\]\s*$'
        match = re.search(header_pattern, text, flags=re.MULTILINE)
        if not match:
            block = (
                f'\n[projects."{project_path}"]\n'
                f'{key} = {_toml_literal(value)}\n'
            )
            return text.rstrip() + block + "\n"

        block_start = match.end()
        next_header = re.search(r'^\[', text[block_start:], flags=re.MULTILINE)
        block_end = block_start + next_header.start() if next_header else len(text)
        block = text[block_start:block_end]
        key_pattern = rf'^\s*{re.escape(key)}\s*=\s*.+$'
        if re.search(key_pattern, block, flags=re.MULTILINE):
            block = re.sub(
                key_pattern,
                f'{key} = {_toml_literal(value)}',
                block,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            if not block.startswith("\n"):
                block = "\n" + block
            if block and not block.endswith("\n"):
                block += "\n"
            block += f'{key} = {_toml_literal(value)}\n'
        return text[:block_start] + block + text[block_end:]

    def _set_table_scalar(text, table_header, key, value):
        import re
        escaped_header = re.escape(table_header)
        header_pattern = rf'^\[{escaped_header}\]\s*$'
        match = re.search(header_pattern, text, flags=re.MULTILINE)
        if not match:
            block = f'\n[{table_header}]\n{key} = {_toml_literal(value)}\n'
            return text.rstrip() + block + "\n"

        block_start = match.end()
        next_header = re.search(r'^\[', text[block_start:], flags=re.MULTILINE)
        block_end = block_start + next_header.start() if next_header else len(text)
        block = text[block_start:block_end]
        key_pattern = rf'^\s*{re.escape(key)}\s*=\s*.+$'
        if re.search(key_pattern, block, flags=re.MULTILINE):
            block = re.sub(
                key_pattern,
                f'{key} = {_toml_literal(value)}',
                block,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            if not block.startswith("\n"):
                block = "\n" + block
            if block and not block.endswith("\n"):
                block += "\n"
            block += f'{key} = {_toml_literal(value)}\n'
        return text[:block_start] + block + text[block_end:]

    def _rewrite_table_block(text, table_header, entries):
        import re
        escaped_header = re.escape(table_header)
        pattern = re.compile(
            rf'^\[{escaped_header}\]\s*$.*?(?=^\[|\Z)',
            flags=re.MULTILINE | re.DOTALL,
        )
        text = pattern.sub("", text).rstrip()
        block_lines = [f'[{table_header}]']
        for key, value in entries:
            block_lines.append(f'{key} = {_toml_literal(value)}')
        block = "\n".join(block_lines) + "\n"
        if text:
            text += "\n\n"
        return text + block

    def _normalize_toml_layout(text):
        import re
        # Repair malformed cases like `[model_providers.custom]name = "custom"`.
        text = re.sub(r'(\[[^\]\n]+\])([A-Za-z0-9_"-]+\s*=)', r'\1' + "\n" + r'\2', text)
        if text and not text.endswith("\n"):
            text += "\n"
        return text

    # 复制用户 config.toml，但把顶层和当前项目的 base_url 都替换成隔离地址
    # Codex CLI 会读取 project-scoped config，单改顶层 base_url 不够。
    gateway_config_template = os.path.join(gateway_base, ".codex", "config.toml")
    real_config = _real_user_path(".codex", "config.toml")
    # Prefer the user's real config as the source of truth. The gateway template
    # may contain stale custom sections from previous buggy generations.
    source_config = real_config if os.path.exists(real_config) else gateway_config_template
    gateway_config = os.path.join(codex_dir, "config.toml")
    if os.path.exists(source_config):
        try:
            with open(source_config, "r", encoding="utf-8") as f:
                config_text = f.read()
            config_text = _set_top_level_scalar(config_text, "base_url", base_url)
            config_text = _set_project_base_url(config_text, os.getcwd(), base_url)
            config_text = _set_project_scalar(config_text, os.getcwd(), "trust_level", "trusted")
            config_text = _rewrite_table_block(
                config_text,
                "model_providers.custom",
                [
                    ("name", "custom"),
                    ("wire_api", "responses"),
                    ("requires_openai_auth", True),
                    ("base_url", base_url),
                ],
            )
            config_text = _append_codex_mcp_servers_from_claude_json(config_text)
            config_text = _normalize_toml_layout(config_text)
            with open(gateway_config, "w", encoding="utf-8") as f:
                f.write(config_text)
        except Exception:
            shutil.copy2(source_config, gateway_config)
    else:
        with open(gateway_config, "w", encoding="utf-8") as f:
            f.write(f'base_url = "{base_url}"\n')
            f.write('\n[model_providers.custom]\n')
            f.write('name = "custom"\n')
            f.write('wire_api = "responses"\n')
            f.write('requires_openai_auth = true\n')
            f.write(f'base_url = "{base_url}"\n')
            f.write(f'\n[projects."{os.getcwd()}"]\n')
            f.write(f'base_url = "{base_url}"\n')
            f.write('trust_level = "trusted"\n')
        try:
            with open(gateway_config, "r", encoding="utf-8") as f:
                config_text = f.read()
            config_text = _append_codex_mcp_servers_from_claude_json(config_text)
            config_text = _normalize_toml_layout(config_text)
            with open(gateway_config, "w", encoding="utf-8") as f:
                f.write(config_text)
        except Exception:
            pass

    real_codex_dir = _real_user_path(".codex")
    real_hooks_path = os.path.join(real_codex_dir, "hooks.json")
    if enable_caveman or os.path.exists(real_hooks_path):
        try:
            with open(real_hooks_path, "r", encoding="utf-8") as f:
                base_hooks = _json.load(f)
        except Exception:
            base_hooks = {}
        session_hooks = _build_codex_session_hooks(
            base_hooks,
            enable_caveman=enable_caveman,
        )
        hooks_path = os.path.join(codex_dir, "hooks.json")
        atomic_write_json(hooks_path, session_hooks, mode=0o600)

    # symlink 真实 ~/.codex 下的其余子项（skills、memories 等）
    if os.path.isdir(real_codex_dir):
        skip = {"auth.json", "config.toml", "hooks.json"}
        for entry in os.listdir(real_codex_dir):
            if entry in skip:
                continue
            src = os.path.join(real_codex_dir, entry)
            dst = os.path.join(codex_dir, entry)
            if not os.path.exists(dst) and not os.path.islink(dst):
                os.symlink(src, dst)
    _overlay_caveman_session_entries(
        codex_dir,
        session_home,
        enable_caveman=enable_caveman,
    )
    _overlay_web_access_session_entries(codex_dir, session_home)

    env = os.environ.copy()
    _scrub_inherited_runtime_env(env, strip_openai=True, strip_proxy=True)
    _inject_real_home_hints(env, include_xdg=True)
    env["HOME"] = session_home
    _set_session_home_hint(env, session_home)
    env["OPENAI_API_KEY"] = openai_key
    env["OPENAI_BASE_URL"] = base_url
    _apply_runtime_network_profile(env, runtime, validate_proxy=False)
    _apply_runtime_locale_profile(env, runtime)
    _apply_runtime_ip_stack_profile(env, runtime)
    _install_session_command_wrappers(session_home, env)
    return env


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


def launch_codex(model_info, runtime, once=False):
    """启动 Codex，支持 provider 和 OAuth 账号档案两种模式。
    GPT 模型优先直连 Responses API；非 GPT 模型走本地 Chat Completions bridge。"""
    _ensure_bridge_helpers()
    _ensure_speed_stats()
    auth_mode = runtime.get("auth_mode", "api_key")
    if auth_mode == "oauth":
        env = _account_env(runtime)
        _prepare_oauth_home_context(runtime, env, "codex")
        model = _resolve_model(model_info)
        cmd = ["codex"]
        if model:
            cmd += ["-m", model]
        if runtime.get("bypass"):
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        _exec_or_run(cmd, env, once)
        return

    gateway_health_check(runtime)
    model = _resolve_model(model_info)
    gateway_url = _openai_base_url(runtime)
    api_key = runtime.get("openai_api_key") or runtime.get("api_key", "")
    speed_scope = build_provider_speed_scope(runtime)
    try:
        advertised_models = list(_probe_models(runtime, emit_output=False).get("models") or [])
    except Exception:
        advertised_models = [model] if model else []

    if not _is_gpt_model(model):
        bridge_label = f"模型 {model}" if model else "当前模型"
        console.print(f"[dim]{bridge_label} 通过本地 Chat Completions bridge 启动 Codex...[/dim]")
        with codex_chatcompletions_bridge(
            gateway_url,
            api_key,
            model_name=model or "unknown",
            advertised_models=advertised_models,
            speed_scope=speed_scope,
            proxy_url=runtime.get("proxy"),
            no_proxy=runtime.get("no_proxy"),
        ) as bridge_cfg:
            bridge_base_url = _codex_provider_base_url(bridge_cfg["base_url"])
            env = _codex_gateway_env(runtime, bridge_cfg["base_url"])
            env["OPENAI_API_KEY"] = bridge_cfg["api_key"]
            env["OPENAI_BASE_URL"] = bridge_base_url
            cmd = ["codex"]
            cmd += ["-c", 'model_provider="custom"']
            cmd += ["-c", f'openai_base_url="{bridge_base_url}"']
            cmd += ["-c", f'model_providers.custom.base_url="{bridge_base_url}"']
            cmd += ["-c", "features.responses_websockets=false"]
            cmd += ["-c", "features.responses_websockets_v2=false"]
            if model:
                cmd += ["-m", model]
            if runtime.get("bypass"):
                cmd.append("--dangerously-bypass-approvals-and-sandbox")
            try:
                result = subprocess.run(cmd, env=env)
                sys.exit(result.returncode)
            except KeyboardInterrupt:
                sys.exit(0)
        return

    provider_id = runtime.get("id", "")
    from mms_tui import select_reasoning_effort_tui as _sel_effort
    reasoning_effort = _sel_effort(default="high")
    console.print(f"[dim]reasoning effort: {reasoning_effort}[/dim]")
    with codex_responses_bridge(
        gateway_url,
        api_key,
        model_name=model or "unknown",
        advertised_models=advertised_models,
        speed_scope=speed_scope,
        provider_id=provider_id,
        reasoning_effort=reasoning_effort,
        proxy_url=runtime.get("proxy"),
        no_proxy=runtime.get("no_proxy"),
    ) as bridge_cfg:
        bridge_base_url = _codex_provider_base_url(bridge_cfg["base_url"])
        env = _codex_gateway_env(runtime, bridge_cfg["base_url"])
        env["OPENAI_API_KEY"] = bridge_cfg["api_key"]
        env["OPENAI_BASE_URL"] = bridge_base_url
        cmd = ["codex"]
        cmd += ["-c", 'model_provider="custom"']
        cmd += ["-c", f'model_reasoning_effort="{reasoning_effort}"']
        cmd += ["-c", f'openai_base_url="{bridge_base_url}"']
        cmd += ["-c", f'model_providers.custom.base_url="{bridge_base_url}"']
        cmd += ["-c", "features.responses_websockets=false"]
        cmd += ["-c", "features.responses_websockets_v2=false"]
        if model:
            cmd += ["-m", model]
        if runtime.get("bypass"):
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        # 本地 responses bridge 运行在当前 Python 进程内；交互模式若 exec 替换自身，
        # bridge 线程会一并消失，Codex 随后访问 127.0.0.1:port 只会得到 5xx/连接失败。
        _exec_or_run(cmd, env, once, force_subprocess=True)


def launch_qwen(model_info, provider, once=False):
    """启动 Qwen，通过 CLI flags 配置"""
    api_key = provider["api_key"]
    model = _resolve_model(model_info)
    cmd = [
        "qwen",
        "--openai-base-url", _openai_base_url(provider),
        "--openai-api-key", api_key,
    ]
    if model:
        cmd += ["-m", model]

    env = os.environ.copy()
    _scrub_inherited_runtime_env(env, strip_openai=True, strip_proxy=True)
    _apply_runtime_network_profile(env, provider, validate_proxy=False)
    _apply_runtime_locale_profile(env, provider)
    _apply_runtime_ip_stack_profile(env, provider)
    _exec_or_run(cmd, env, once)


def launch_kimi(model_info, provider, once=False):
    """启动 Kimi：优先走自定义 provider，无配置时退回 OAuth。"""
    api_key = provider["api_key"]
    model = _resolve_model(model_info)
    env = os.environ.copy()
    _scrub_inherited_runtime_env(env, strip_openai=True, strip_proxy=True)
    _apply_runtime_network_profile(env, provider, validate_proxy=False)
    _apply_runtime_locale_profile(env, provider)
    _apply_runtime_ip_stack_profile(env, provider)
    cmd = ["kimi"]

    if _openai_base_url(provider) and api_key and model:
        provider_name = provider.get("id", "mms-openai")
        model_id = f"{provider_name}/{model}"
        config_toml = (
            f'default_model = "{model_id}"\n'
            f'[models."{model_id}"]\n'
            f'provider = "{provider_name}"\n'
            f'model = "{model}"\n'
            f'capabilities = ["thinking"]\n'
            f'[providers."{provider_name}"]\n'
            f'type = "openai_legacy"\n'
            f'base_url = "{_openai_base_url(provider)}"\n'
            f'api_key = "{api_key}"\n'
        )
        config_path = _write_runtime_config("kimi-", config_toml)
        cmd += ["--config", config_path]
        _exec_or_run(cmd, env, once, cleanup_path=config_path)
        return

    if model:
        cmd += ["-m", model]
    _exec_or_run(cmd, env, once)


def launch_gemini(model_info, runtime, once=False):
    """启动 Gemini，当前只支持官方账号档案模式。"""
    auth_mode = runtime.get("auth_mode", "api_key")
    if auth_mode != "oauth":
        console.print("[red]Gemini 当前只支持官方账号入口，不支持直接使用模型源启动[/red]")
        sys.exit(1)

    env = _account_env(runtime)
    _prepare_oauth_home_context(runtime, env, "gemini")
    model = _resolve_model(model_info)
    cmd = ["gemini"]
    if model:
        cmd += ["-m", model]
    _exec_or_run(cmd, env, once)


LAUNCHERS = {
    "claude": launch_claude,
    "codex": launch_codex,
    "qwen": launch_qwen,
    "kimi": launch_kimi,
    "gemini": launch_gemini,
}


def get_export_env(cli, runtime):
    """返回指定 CLI 需要的 export 环境变量字典。"""
    if runtime.get("auth_mode") == "broker_profile":
        return {}
    if runtime.get("auth_mode") == "oauth_bridge":
        return {}
    if runtime.get("auth_mode") == "oauth":
        validate_account_for_cli(runtime.get("cli", cli), runtime)
        return {}

    validate_provider_for_cli(cli, runtime)
    api_key = runtime["api_key"]
    exports = {}
    if cli == "claude":
        exports["ANTHROPIC_BASE_URL"] = _anthropic_base_url(runtime)
        exports["ANTHROPIC_AUTH_TOKEN"] = api_key
        exports["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        exports["API_TIMEOUT_MS"] = "3000000"
    elif cli == "codex":
        exports["OPENAI_API_KEY"] = api_key
        exports["OPENAI_BASE_URL"] = _openai_base_url(runtime)
    elif cli == "kimi":
        exports["OPENAI_API_KEY"] = api_key
        exports["OPENAI_BASE_URL"] = _openai_base_url(runtime)
    return exports


def _show_launch_info(cli, runtime, auth_mode):
    """启动前轻量展示：gateway 可用模型 + 本地用量统计（失败不阻塞）。"""
    runtime_kind = runtime.get("runtime_kind", "provider")
    runtime_id = runtime.get("id", "default")

    # ── gateway 可用模型列表 ──
    if auth_mode == "api_key":
        try:
            probe_result = runtime.get("_launch_prefetched_probe")
            if probe_result is None:
                probe_result = _probe_models(runtime, emit_output=False)
            models = list(probe_result.get("models") or [])
            if models:
                console.print(f"[dim]可用模型 ({len(models)}): {', '.join(models[:8])}"
                              f"{'…' if len(models) > 8 else ''}[/dim]")
        except Exception:
            pass

    # ── 本地用量统计 ──
    try:
        usage_path = _real_user_path(".config", "mms", "usage.json")
        if not os.path.exists(usage_path):
            usage_path = _real_user_path(".config", "ccs", "usage.json")
        if os.path.exists(usage_path):
            with open(usage_path, "r", encoding="utf-8") as f:
                stats = json.load(f)
            key = f"{runtime_kind}:{cli}:{runtime_id}"
            entry = stats.get("sources", {}).get(key)
            if entry:
                launches = entry.get("launches", 0)
                last_model = entry.get("last_model", "")
                last_at = entry.get("last_used_at", "")[:10]
                parts = [f"历史启动 {launches} 次"]
                if last_model:
                    parts.append(f"上次模型 {last_model}")
                if last_at:
                    parts.append(f"最近 {last_at}")
                console.print(f"[dim]{' | '.join(parts)}[/dim]")
    except Exception:
        pass

    if cli == "claude":
        try:
            one_m = "开启" if _runtime_supports_claude_1m(runtime) else "关闭"
            mode = _normalize_claude_1m_mode((runtime or {}).get("claude_1m_mode", "auto"))
            console.print(f"[dim]Claude 1M: {one_m} ({mode})[/dim]")
        except Exception:
            pass
        try:
            report = runtime.get("_account_guard_report")
            if report:
                style = {
                    "stable": "green",
                    "watch": "yellow",
                    "risky": "yellow",
                    "blocked": "red",
                }.get(report.get("status"), "dim")
                console.print(f"[{style}]{_format_account_guard_summary(report)}[/{style}]")
        except Exception:
            pass
    try:
        console.print(f"[dim]网络: {_runtime_network_summary(runtime)}[/dim]")
    except Exception:
        pass
    try:
        _emit_dns_guard_hint(runtime, cli_name=cli, auth_mode=auth_mode)
    except Exception:
        pass


def launch_cli(cli, model_info, runtime, once=False):
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
    else:
        validate_provider_for_cli(cli, runtime)
        source_label = runtime.get("name", runtime.get("id", "provider"))
        source_kind = "模型源"

    if cli == "claude" and auth_mode == "oauth":
        # OAuth Claude 已委托给 MMC 管理 session/state；MMS 不再读取或判定其并发 state。
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
    from shutil import which
    exe = which(cmd[0])
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
