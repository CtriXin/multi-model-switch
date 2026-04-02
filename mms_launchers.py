"""MMS 启动器：按 provider 或账号档案启动四个 CLI。"""

from contextlib import contextmanager
import json
import os
import shutil
import sys
import subprocess
import tempfile
from datetime import datetime
from time import perf_counter

from mms_account_state import activated_claude_account_state, seed_claude_state, seed_gemini_state
from mms_core import _probe_models, detect_working_base_url
from mms_project_store import CLAUDE_PERSISTENT_ENTRIES, claude_raw_entry_path, ensure_claude_project_store, read_slot_marker, write_slot_marker
from mms_session_index import finalize_claude_session, record_claude_session_start

_build_gateway_url = None
codex_claude_bridge = None
gemini_claude_bridge = None
gateway_claude_bridge = None
codex_chatcompletions_bridge = None
codex_responses_bridge = None
_write_route_status = None
build_provider_speed_scope = None


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
    # Qwen — hosted 版本支持 1M；qwen3-max 为 262K
    "qwen3.5-plus": 1_000_000,
    "qwen3-coder-plus": 1_000_000,
    "qwen3-max": 262_144,
    # GLM — 全系 200K
    "glm-5": 200_000,
    "glm-5-turbo": 200_000,
    "glm-5.1": 200_000,
    "glm-4.7": 200_000,
    # MiniMax — M2.5 为 196K，M2.7 为 200K
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
_CLAUDE_DISABLE_1M_PROVIDER_IDS = {"xin", "fishcrs", "trcrs", "turkeycrs"}
_CLAUDE_SENSITIVE_PROVIDER_IDS = {"xin", "fishcrs", "trcrs", "turkeycrs"}

def _runtime_supports_claude_1m(runtime):
    provider_id = str((runtime or {}).get("id", "")).strip().lower()
    return provider_id not in _CLAUDE_DISABLE_1M_PROVIDER_IDS


def _runtime_is_sensitive_claude_provider(runtime):
    provider_id = str((runtime or {}).get("id", "")).strip().lower()
    return provider_id in _CLAUDE_SENSITIVE_PROVIDER_IDS


def _effective_context_window(*models, enable_claude_1m=True):
    """取所有活跃模型中最小的 context window。
    智能路由场景下 heavy/medium/light 可能是不同模型，
    conversation context 必须 fit 最小的那个。
    """
    windows = []
    for m in models:
        if not m:
            continue
        clean = m.replace("[1m]", "").strip()
        w = _MODEL_CONTEXT_WINDOWS.get(clean)
        if w is None:
            # 大小写不敏感匹配
            lower = clean.lower()
            for k, v in _MODEL_CONTEXT_WINDOWS.items():
                if k.lower() == lower:
                    w = v
                    break
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


def _inject_real_home_hints(env, *, include_xdg=False):
    real_home = _real_user_home()
    env["MMS_REAL_HOME"] = real_home
    env["ORIGINAL_HOME"] = real_home
    env["REAL_HOME"] = real_home
    env["GH_CONFIG_DIR"] = _real_user_path(".config", "gh")
    if include_xdg:
        env["XDG_CONFIG_HOME"] = _real_user_path(".config")
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

# agent-im daemon 路径（auto-start on mms launch）
_AGENT_IM_DIR = _real_user_path("auto-skills", "CtriXin-repo", "agent-im")
_AGENT_IM_SOCK = _real_user_path(".agent-im", "agent-im.sock")
_LOCAL_STATUSLINE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "statusline-command.sh")

_CLAUDE_STATUSLINE_CONFIG = {
    "command": f"/bin/bash {_LOCAL_STATUSLINE_SCRIPT}",
    "type": "command",
}

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
    _ANTHROPIC_URL_CACHE[provider_id] = {"url": resolved_url, "ts": datetime.now()}
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
    import json as _json

    real_settings_path = os.path.join(_real_user_path(".claude"), "settings.json")
    if not os.path.exists(real_settings_path):
        return {}
    try:
        with open(real_settings_path, encoding="utf-8") as f:
            loaded = _json.load(f)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _strip_agent_im_hooks(hooks_data):
    if not isinstance(hooks_data, dict):
        return None

    filtered = {}
    for event_name, entries in hooks_data.items():
        if not isinstance(entries, list):
            filtered[event_name] = entries
            continue

        kept_entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                kept_entries.append(entry)
                continue

            hook_defs = entry.get("hooks")
            if not isinstance(hook_defs, list):
                kept_entries.append(entry)
                continue

            kept_hook_defs = []
            for hook_def in hook_defs:
                if not isinstance(hook_def, dict):
                    kept_hook_defs.append(hook_def)
                    continue
                command = str(hook_def.get("command", ""))
                if "agent-im" in command:
                    continue
                kept_hook_defs.append(hook_def)

            if kept_hook_defs:
                new_entry = dict(entry)
                new_entry["hooks"] = kept_hook_defs
                kept_entries.append(new_entry)

        if kept_entries:
            filtered[event_name] = kept_entries

    return filtered or None


def _build_claude_session_settings(base_settings=None, *, required_env=None, default_env=None):
    settings_data = dict(base_settings or {})

    existing_env = settings_data.get("env")
    merged_env = dict(existing_env) if isinstance(existing_env, dict) else {}
    if isinstance(default_env, dict):
        for key, value in default_env.items():
            merged_env.setdefault(key, value)
    if isinstance(required_env, dict):
        merged_env.update(required_env)
    settings_data["env"] = merged_env

    hooks = _strip_agent_im_hooks(settings_data.get("hooks"))
    if hooks:
        settings_data["hooks"] = hooks
    else:
        settings_data.pop("hooks", None)

    settings_data.setdefault("includeCoAuthoredBy", False)
    settings_data.setdefault("attribution", {"commit": "", "pr": ""})
    settings_data.setdefault("promptSuggestionEnabled", False)
    settings_data.setdefault("skipDangerousModePermissionPrompt", True)
    settings_data.setdefault("statusLine", dict(_CLAUDE_STATUSLINE_CONFIG))
    settings_data.setdefault("permissions", {
        "allow": list(_CLAUDE_DEFAULT_PERMISSION_ALLOW),
        "defaultMode": "bypassPermissions",
        "deny": list(_CLAUDE_DEFAULT_PERMISSION_DENY),
    })
    return settings_data


def _write_claude_session_settings(session_claude_dir, *, required_env=None, default_env=None):
    import json as _json

    os.makedirs(session_claude_dir, exist_ok=True)
    settings_data = _build_claude_session_settings(
        _load_real_claude_settings(),
        required_env=required_env,
        default_env=default_env,
    )
    settings_path = os.path.join(session_claude_dir, "settings.json")
    with open(settings_path, "w", encoding="utf-8") as f:
        _json.dump(settings_data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return settings_data, settings_path


def _gateway_ping(base_url, api_key):
    """Quick connectivity check; returns True/False/None (None = can't determine)."""
    _ensure_bridge_helpers()
    try:
        import httpx as _httpx
    except ImportError:
        return None
    if not base_url or not api_key:
        return None
    models_url = _build_gateway_url(base_url, "/models")
    try:
        r = _httpx.get(models_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=8)
        return r.status_code < 500
    except Exception:
        return False


def _health_check_due(provider_id):
    try:
        with open(HEALTH_CHECK_PATH) as f:
            data = json.load(f)
        if data.get("provider_id") != provider_id:
            return True
        last = datetime.fromisoformat(data["timestamp"])
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
    ok = _gateway_ping(base_url, api_key)
    if ok is None:
        return
    try:
        os.makedirs(os.path.dirname(HEALTH_CHECK_PATH), exist_ok=True)
        with open(HEALTH_CHECK_PATH, "w") as f:
            json.dump({"timestamp": datetime.now().isoformat(), "provider_id": provider_id, "ok": ok}, f)
    except OSError:
        pass
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


def _account_env(account):
    env = os.environ.copy()
    _inject_real_home_hints(env)
    home_dir = os.path.expanduser(str(account.get("home_dir", "")).strip())
    if not home_dir:
        console.print(f"[red]账号档案 '{account.get('id', 'unknown')}' 未配置 home_dir[/red]")
        sys.exit(1)
    cli_name = account.get("cli")
    if cli_name == "claude":
        seed_claude_state(home_dir)
        # per-PID 会话隔离：每个窗口独立 HOME，避免多窗口 race ~/.claude.json
        sessions_dir = os.path.join(home_dir, "s")
        session_home = os.path.join(sessions_dir, str(os.getpid()))
        os.makedirs(session_home, exist_ok=True)
        _cleanup_stale_sessions(sessions_dir, stale_callback=_finalize_claude_slot)
        # 复制账号的 .claude.json 到 per-session 目录
        import json as _json
        account_json = os.path.join(home_dir, ".claude.json")
        session_json = os.path.join(session_home, ".claude.json")
        if os.path.exists(account_json):
            try:
                shutil.copy2(account_json, session_json)
            except Exception:
                pass
        # symlink .local
        real_local = _real_user_path(".local")
        gw_local = os.path.join(session_home, ".local")
        if os.path.isdir(real_local) and not os.path.exists(gw_local) and not os.path.islink(gw_local):
            os.symlink(real_local, gw_local)
        # symlink Library（macOS Keychain 需要 ~/Library/Keychains）
        real_library = _real_user_path("Library")
        session_library = os.path.join(session_home, "Library")
        if os.path.isdir(real_library) and not os.path.exists(session_library) and not os.path.islink(session_library):
            os.symlink(real_library, session_library)
        _link_shared_dotfiles(session_home)
        # .claude/ 目录：创建真实目录，分项 symlink
        session_claude_dir = os.path.join(session_home, ".claude")
        _prepare_claude_session_tree(
            session_home,
            session_claude_dir,
            account_id=account.get("id", ""),
            runtime_kind="oauth",
            skip_real_entries={"settings.json"},
        )
        env["HOME"] = session_home
        _install_session_command_wrappers(session_home, env)
    elif cli_name == "gemini":
        seed_gemini_state(home_dir)
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
            _sync_codex_session_claude_json(session_home)
            _overlay_codex_shared_resume(home_dir, session_home)
        xdg_config_home = os.path.join(session_home, ".config")
        env["HOME"] = session_home
        env["XDG_CONFIG_HOME"] = xdg_config_home
        _install_session_command_wrappers(session_home, env)
    env["MMS_ACCOUNT_ID"] = str(account.get("id", ""))
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


def _install_session_command_wrappers(session_home, env):
    """Install wrappers for tools that must run against the real HOME."""
    wrapper_dir = os.path.join(session_home, ".mms", "bin")
    os.makedirs(wrapper_dir, exist_ok=True)

    real_home = _real_user_home()
    current_path = os.environ.get("PATH", "")
    for command_name in ("lark-cli", "hive"):
        real_bin = shutil.which(command_name, path=current_path)
        if not real_bin:
            continue

        wrapper_path = os.path.join(wrapper_dir, command_name)
        wrapper = "\n".join(
            [
                "#!/bin/sh",
                f'export HOME="{real_home}"',
                f'export MMS_REAL_HOME="{real_home}"',
                f'export REAL_HOME="{real_home}"',
                f'export ORIGINAL_HOME="{real_home}"',
                f'exec "{real_bin}" "$@"',
                "",
            ]
        )
        with open(wrapper_path, "w", encoding="utf-8") as handle:
            handle.write(wrapper)
        os.chmod(wrapper_path, 0o755)

    session_path = env.get("PATH") or current_path
    env["PATH"] = wrapper_dir + os.pathsep + session_path if session_path else wrapper_dir


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
        data = loaded
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

    with open(session_json, "w", encoding="utf-8") as f:
        _json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


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
    if auth_mode == "oauth":
        env = _account_env(runtime)
        session_claude_dir = os.path.join(env.get("HOME", ""), ".claude")
        _write_claude_session_settings(
            session_claude_dir,
            default_env={
                "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
                "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
            },
        )
        env.setdefault("CLAUDE_CODE_ATTRIBUTION_HEADER", "0")
        env.setdefault("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
        state_home = None  # per-PID HOME 已隔离，不需要 swap .claude.json
        cleanup_ctx = None
    elif auth_mode == "oauth_bridge":
        bridge_model = runtime.get("bridge_model") or _resolve_model(model_info)
        advertised_models = [bridge_model] if bridge_model else []
        if runtime.get("bridge_source_cli") == "gemini":
            cleanup_ctx = gemini_claude_bridge(runtime, bridge_model)
        else:
            cleanup_ctx = codex_claude_bridge(runtime, bridge_model)
        bridge_cfg = cleanup_ctx.__enter__()
        env = _prepare_claude_env_with_status(
            runtime,
            base_url=bridge_cfg["base_url"],
            auth_token=bridge_cfg["api_key"],
            heavy_model=bridge_model,
            selected_model=bridge_model,
        )
        state_home = None
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

        if anthropic_url is not None:
            bridge_gw_url = anthropic_url.rstrip("/")
            if not bridge_gw_url.endswith("/v1"):
                bridge_gw_url += "/v1"
            if lb_light or lb_medium:
                # 智能路由：通过本地 bridge 路由，以便拦截并切换模型
                cleanup_ctx = gateway_claude_bridge(bridge_gw_url, runtime["api_key"],
                                                    heavy_model=probe_model,
                                                    medium_model=lb_medium or None,
                                                    light_model=lb_light or None,
                                                    advertised_models=advertised_models,
                                                    speed_scope=speed_scope,
                                                    route_status_paths=route_status_paths,
                                                    slot_configs=lb_slot_configs,
                                                    openai_url=_gpt_openai_url)
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
                cleanup_ctx = gateway_claude_bridge(
                    bridge_gw_url,
                    runtime["api_key"],
                    heavy_model=probe_model,
                    advertised_models=advertised_models,
                    speed_scope=speed_scope,
                    route_status_paths=route_status_paths,
                    openai_url=_gpt_openai_url,
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
            console.print(f"[dim]🔀 GPT-on-Claude: 通过 OpenAI 端点 bridge → Responses API[/dim]")
            cleanup_ctx = gateway_claude_bridge(openai_url, api_key,
                                                heavy_model=probe_model,
                                                medium_model=lb_medium or None,
                                                light_model=lb_light or None,
                                                advertised_models=advertised_models,
                                                speed_scope=speed_scope,
                                                route_status_paths=route_status_paths,
                                                slot_configs=lb_slot_configs,
                                                openai_url=openai_url)
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
            cleanup_ctx = gateway_claude_bridge(openai_url, api_key,
                                                heavy_model=probe_model,
                                                medium_model=lb_medium or None,
                                                light_model=lb_light or None,
                                                advertised_models=advertised_models,
                                                speed_scope=speed_scope,
                                                route_status_paths=route_status_paths,
                                                slot_configs=lb_slot_configs,
                                                openai_url=openai_url)
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
                cleanup_ctx = gateway_claude_bridge(openai_url, api_key,
                                                    heavy_model=probe_model,
                                                    medium_model=lb_medium,
                                                    light_model=lb_light,
                                                    advertised_models=advertised_models,
                                                    speed_scope=speed_scope,
                                                    route_status_paths=route_status_paths,
                                                    slot_configs=lb_slot_configs,
                                                    openai_url=openai_url)
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
    ctx_window = _effective_context_window(*_real_models, enable_claude_1m=enable_claude_1m)
    env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(ctx_window)
    env["CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE"] = str(max(ctx_window - 3000, 10000))

    cmd = ["claude"]
    if runtime.get("bypass"):
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

    # ---- 内存缓存（TTL 1h）----
    cached = _ANTHROPIC_URL_CACHE.get(provider_id)
    if cached:
        age = (datetime.now() - cached["ts"]).total_seconds()
        if age < 3600:
            return cached["url"], "cached"

    # ---- 文件缓存（跨进程，TTL 24h）----
    cache_key = _anthropic_cache_key(provider_id, url)
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
                _ANTHROPIC_URL_CACHE[provider_id] = {"url": cached_url, "ts": datetime.now()}
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
    body = json.dumps({
        "model": probe_model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
        "metadata": {
            "user_id": json.dumps({
                "device_id": f"mms-probe-{provider_id}",
                "account_uuid": str(runtime.get("id", "")),
                "session_id": f"mms-probe-{provider_id}",
            }, ensure_ascii=False),
        },
    }).encode()
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    candidate = detect_working_base_url(url, "/v1/messages", headers, body=body, timeout=5)

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
        import httpx as _httpx
    except ImportError:
        return None
    api_key = runtime.get("api_key", "")
    if not base_url or not api_key:
        return None
    url_v1 = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
    try:
        r = _httpx.get(f"{url_v1}/models",
                       headers={"Authorization": f"Bearer {api_key}"},
                       timeout=8, follow_redirects=True)
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
        try:
            pid = int(name)
            os.kill(pid, 0)  # 检查进程是否存活
        except (ValueError, ProcessLookupError):
            # PID 无效或进程已死 → 清理
            stale = os.path.join(sessions_dir, name)
            if stale_callback is not None:
                try:
                    stale_callback(stale, stale_cleanup=True)
                except Exception:
                    pass
            shutil.rmtree(stale, ignore_errors=True)
        except PermissionError:
            pass  # 进程存在但无权限发信号，跳过


def _prepare_claude_session_tree(session_home, session_claude_dir, *, account_id="", runtime_kind="api_key", skip_real_entries=None):
    current_cwd = os.path.realpath(os.getcwd())
    store = ensure_claude_project_store(current_cwd)
    skip_real_entries = set(skip_real_entries or ())
    real_claude_dir = _real_user_path(".claude")
    if os.path.islink(session_claude_dir):
        os.unlink(session_claude_dir)
    os.makedirs(session_claude_dir, exist_ok=True)
    if os.path.isdir(real_claude_dir):
        for entry in os.listdir(real_claude_dir):
            if entry in skip_real_entries or entry in CLAUDE_PERSISTENT_ENTRIES:
                continue
            src = os.path.join(real_claude_dir, entry)
            dst = os.path.join(session_claude_dir, entry)
            if not os.path.exists(dst) and not os.path.islink(dst):
                os.symlink(src, dst)
    for entry in CLAUDE_PERSISTENT_ENTRIES:
        dst = os.path.join(session_claude_dir, entry)
        target = str(claude_raw_entry_path(entry, current_cwd))
        if not os.path.exists(dst) and not os.path.islink(dst):
            os.symlink(target, dst)
    record_claude_session_start(
        cwd=current_cwd,
        account_id=str(account_id or ""),
        pid=os.getpid(),
        runtime_kind=runtime_kind,
        slot_home=session_home,
    )
    write_slot_marker(
        session_home,
        cwd=current_cwd,
        project_key_value=store["project_key"],
        account_id=str(account_id or ""),
        runtime_kind=runtime_kind,
    )


def _finalize_claude_slot(session_home, exit_code=None, stale_cleanup=False):
    marker = read_slot_marker(session_home)
    if not marker:
        return
    try:
        pid = int(os.path.basename(str(session_home)))
    except (TypeError, ValueError):
        return
    cwd = marker.get("cwd") or os.getcwd()
    finalize_claude_session(
        cwd=cwd,
        pid=pid,
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
    gateway_home = _claude_gateway_home()
    route_status_path = _claude_route_status_paths()[0]
    os.makedirs(gateway_home, exist_ok=True)

    # 清理 stale sessions（PID 已不存在的目录）
    _cleanup_stale_sessions(sessions_dir, stale_callback=_finalize_claude_slot)

    # 若调用方已通过 _resolve_anthropic_base_url 探测到正确 URL，直接用；
    # 否则保底剥离 /v1（避免双重 /v1/v1/messages）。
    if base_url is None:
        base_url = _anthropic_base_url(runtime)
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]

    # ── .claude.json：剥离 migration flags + 写入 thinking/attribution ──
    # 合并策略：真实 ~/.claude.json 为基础，保留 per-session 已有的用户确认状态
    real_json = _real_user_path(".claude.json")
    gw_json = os.path.join(gateway_home, ".claude.json")
    data: dict = {}
    if os.path.exists(real_json):
        try:
            with open(real_json, encoding="utf-8") as f:
                data = _json.load(f)
        except Exception:
            data = {}
    # 保留 per-session 里用户已确认的状态（如 bypass permissions accept）
    _GW_PRESERVE_KEYS = ("bypassPermissionsModeAccepted",)
    if os.path.exists(gw_json):
        try:
            with open(gw_json, encoding="utf-8") as f:
                gw_existing = _json.load(f)
            for k in _GW_PRESERVE_KEYS:
                if k in gw_existing and k not in data:
                    data[k] = gw_existing[k]
        except Exception:
            pass
    # 当用户在 TUI 选择不 bypass 时，主动移除持久化的 bypass 状态，
    # 避免旧 session 残留的 bypassPermissionsModeAccepted 导致 Claude Code 自动进入 bypass
    if not runtime.get("bypass"):
        data.pop("bypassPermissionsModeAccepted", None)
    data.pop("sonnet1m45MigrationComplete", None)
    data.pop("opusProMigrationComplete", None)
    data["alwaysThinkingEnabled"] = True
    with open(gw_json, "w", encoding="utf-8") as f:
        _json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # ── .local symlink：Claude Code 检测 $HOME/.local/bin/claude（installMethod=native）──
    real_local = _real_user_path(".local")
    gw_local = os.path.join(gateway_home, ".local")
    if os.path.isdir(real_local) and not os.path.exists(gw_local) and not os.path.islink(gw_local):
        os.symlink(real_local, gw_local)

    # ── Library symlink：macOS Keychain 需要 ~/Library/Keychains ──
    real_library = _real_user_path("Library")
    gw_library = os.path.join(gateway_home, "Library")
    if os.path.isdir(real_library) and not os.path.exists(gw_library) and not os.path.islink(gw_library):
        os.symlink(real_library, gw_library)

    _link_shared_dotfiles(gateway_home)

    # ── ~/.claude 目录：持久化历史项指向 project store，其余沿用真实 ~/.claude ──
    gw_claude_dir = os.path.join(gateway_home, ".claude")
    real_claude_dir = _real_user_path(".claude")
    _prepare_claude_session_tree(
        gateway_home,
        gw_claude_dir,
        account_id=str(runtime.get("id", "")),
        runtime_kind=runtime_kind or str(runtime.get("auth_mode", "api_key")),
        skip_real_entries={"settings.json"},
    )

    # ── settings.json：继承用户配置 + 覆盖 gateway 必要字段 ──
    effective_token = auth_token or runtime["api_key"]
    provider_id = runtime.get("id", "")
    enable_claude_1m = _runtime_supports_claude_1m(runtime)
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
    )

    env = os.environ.copy()
    _inject_real_home_hints(env)
    env["HOME"] = gateway_home
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
    source_config = gateway_config_template if os.path.exists(gateway_config_template) else real_config
    gateway_config = os.path.join(codex_dir, "config.toml")
    if os.path.exists(source_config):
        try:
            with open(source_config, "r", encoding="utf-8") as f:
                config_text = f.read()
            config_text = _set_top_level_scalar(config_text, "base_url", base_url)
            config_text = _set_project_base_url(config_text, os.getcwd(), base_url)
            config_text = _set_table_scalar(config_text, "model_providers.custom", "name", "custom")
            config_text = _set_table_scalar(config_text, "model_providers.custom", "wire_api", "responses")
            config_text = _set_table_scalar(config_text, "model_providers.custom", "requires_openai_auth", True)
            config_text = _set_table_scalar(config_text, "model_providers.custom", "base_url", base_url)
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
        try:
            with open(gateway_config, "r", encoding="utf-8") as f:
                config_text = f.read()
            config_text = _append_codex_mcp_servers_from_claude_json(config_text)
            config_text = _normalize_toml_layout(config_text)
            with open(gateway_config, "w", encoding="utf-8") as f:
                f.write(config_text)
        except Exception:
            pass

    # symlink 真实 ~/.codex 下的其余子项（skills、memories 等）
    real_codex_dir = _real_user_path(".codex")
    if os.path.isdir(real_codex_dir):
        skip = {"auth.json", "config.toml"}
        for entry in os.listdir(real_codex_dir):
            if entry in skip:
                continue
            src = os.path.join(real_codex_dir, entry)
            dst = os.path.join(codex_dir, entry)
            if not os.path.exists(dst) and not os.path.islink(dst):
                os.symlink(src, dst)

    env = os.environ.copy()
    _inject_real_home_hints(env, include_xdg=True)
    env["HOME"] = session_home
    env["OPENAI_API_KEY"] = openai_key
    env["OPENAI_BASE_URL"] = base_url
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
    with codex_responses_bridge(
        gateway_url,
        api_key,
        model_name=model or "unknown",
        advertised_models=advertised_models,
        speed_scope=speed_scope,
        provider_id=provider_id,
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

    _exec_or_run(cmd, os.environ.copy(), once)


def launch_kimi(model_info, provider, once=False):
    """启动 Kimi：优先走自定义 provider，无配置时退回 OAuth。"""
    api_key = provider["api_key"]
    model = _resolve_model(model_info)
    env = os.environ.copy()
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

    model_display = _resolve_model(model_info) if not isinstance(model_info, dict) else \
        model_info.get("model", model_info.get("sonnet", "多模型配置"))

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

    if once or cleanup_path or state_home or cleanup_context or exit_callback or force_subprocess:
        exit_code = None
        try:
            if state_home:
                with activated_claude_account_state(state_home):
                    result = subprocess.run(cmd, env=env)
            else:
                result = subprocess.run(cmd, env=env)
            exit_code = result.returncode
        except KeyboardInterrupt:
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
