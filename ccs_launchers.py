"""MMS/CCS 启动器：按 provider 或账号档案启动四个 CLI。"""

import json
import os
import shutil
import sys
import subprocess
import tempfile
from datetime import datetime

from ccs_account_state import activated_claude_account_state, seed_claude_state, seed_gemini_state
from ccs_bridge import codex_claude_bridge, gemini_claude_bridge, gateway_claude_bridge, codex_chatcompletions_bridge
from ccs_core import detect_working_base_url

try:
    from rich.console import Console
except ImportError:
    pass

console = Console()
RUNTIME_DIR = os.path.expanduser("~/.config/mms/runtime")
HEALTH_CHECK_PATH = os.path.expanduser("~/.config/mms/health_check.json")

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


def _gateway_ping(base_url, api_key):
    """Quick connectivity check; returns True/False/None (None = can't determine)."""
    try:
        import httpx as _httpx
    except ImportError:
        return None
    if not base_url or not api_key:
        return None
    url_with_v1 = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
    try:
        r = _httpx.get(f"{url_with_v1}/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=8)
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

    if not provider.get("enabled", True):
        console.print(f"[red]provider '{provider_id}' 已禁用，无法用于 {cli}[/red]")
        sys.exit(1)

    if not _provider_supports_cli(provider, cli):
        console.print(f"[red]provider '{provider_id}' 不支持 CLI: {cli}[/red]")
        sys.exit(1)

    if required_protocol and required_protocol not in _provider_protocols(provider):
        # OpenAI-only provider 可以通过 bridge 驱动 claude，不阻断
        if cli == "claude" and "openai_chat_completions" in _provider_protocols(provider):
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
        _cleanup_stale_sessions(sessions_dir)
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
        real_local = os.path.expanduser("~/.local")
        gw_local = os.path.join(session_home, ".local")
        if os.path.isdir(real_local) and not os.path.exists(gw_local) and not os.path.islink(gw_local):
            os.symlink(real_local, gw_local)
        # symlink Library（macOS Keychain 需要 ~/Library/Keychains）
        real_library = os.path.expanduser("~/Library")
        session_library = os.path.join(session_home, "Library")
        if os.path.isdir(real_library) and not os.path.exists(session_library) and not os.path.islink(session_library):
            os.symlink(real_library, session_library)
        # .claude/ 目录：创建真实目录，分项 symlink
        session_claude_dir = os.path.join(session_home, ".claude")
        real_claude_dir = os.path.expanduser("~/.claude")
        if os.path.islink(session_claude_dir):
            os.unlink(session_claude_dir)
        os.makedirs(session_claude_dir, exist_ok=True)
        if os.path.isdir(real_claude_dir):
            for entry in os.listdir(real_claude_dir):
                src = os.path.join(real_claude_dir, entry)
                dst = os.path.join(session_claude_dir, entry)
                if not os.path.exists(dst) and not os.path.islink(dst):
                    os.symlink(src, dst)
        env["HOME"] = session_home
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
        real_library = os.path.expanduser("~/Library")
        session_library = os.path.join(session_home, "Library")
        if os.path.isdir(real_library) and not os.path.exists(session_library) and not os.path.islink(session_library):
            os.symlink(real_library, session_library)
        xdg_config_home = os.path.join(session_home, ".config")
        env["HOME"] = session_home
        env["XDG_CONFIG_HOME"] = xdg_config_home
    env["MMS_ACCOUNT_ID"] = str(account.get("id", ""))
    return env


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
    return str(provider.get("base_url", "")).strip().rstrip("/")


def _resolve_model(model_info):
    """从 model_info dict 中提取 model 名称（单模型场景）"""
    if isinstance(model_info, str):
        return model_info
    return model_info.get("model", model_info.get("sonnet", ""))


def launch_claude(model_info, runtime, once=False):
    """启动 Claude Code，支持 provider 和 OAuth 账号档案两种模式。"""
    auth_mode = runtime.get("auth_mode", "api_key")
    if auth_mode == "oauth":
        env = _account_env(runtime)
        state_home = None  # per-PID HOME 已隔离，不需要 swap .claude.json
        cleanup_ctx = None
    elif auth_mode == "oauth_bridge":
        bridge_model = runtime.get("bridge_model") or _resolve_model(model_info)
        if runtime.get("bridge_source_cli") == "gemini":
            cleanup_ctx = gemini_claude_bridge(runtime, bridge_model)
        else:
            cleanup_ctx = codex_claude_bridge(runtime, bridge_model)
        bridge_cfg = cleanup_ctx.__enter__()
        env = _claude_gateway_env(runtime, base_url=bridge_cfg["base_url"], auth_token=bridge_cfg["api_key"])
        state_home = None
    else:
        gateway_health_check(runtime)

        # ---- 三级兼容策略 ----
        # 1. 自动探测正确的 ANTHROPIC_BASE_URL（缓存 1h，避免重复请求）
        probe_model = _resolve_model(model_info) if model_info else "claude-sonnet-4-6"
        anthropic_url, detect_method = _resolve_anthropic_base_url(runtime, probe_model=probe_model)

        # 负载模式：提取 lb_light，需要通过 bridge 拦截请求
        lb_light = model_info.get("lb_light") if isinstance(model_info, dict) else None

        if anthropic_url is not None:
            if lb_light:
                # 负载模式：通过本地 bridge 路由，以便拦截并切换模型
                bridge_gw_url = anthropic_url.rstrip("/")
                if not bridge_gw_url.endswith("/v1"):
                    bridge_gw_url += "/v1"
                cleanup_ctx = gateway_claude_bridge(bridge_gw_url, runtime["api_key"],
                                                    heavy_model=probe_model, lb_light_model=lb_light)
                bridge_cfg = cleanup_ctx.__enter__()
                env = _claude_gateway_env(runtime, base_url=bridge_cfg["base_url"], auth_token=bridge_cfg["api_key"])
                console.print(f"[dim]⚖️ 负载模式已启用 — heavy: {probe_model}, light: {lb_light}[/dim]")
            else:
                # 探测成功：使用探测到的 URL
                env = _claude_gateway_env(runtime, base_url=anthropic_url)
                cleanup_ctx = None
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
            env = _claude_gateway_env(runtime, base_url=bridge_cfg["base_url"], auth_token=bridge_cfg["api_key"])
            state_home = None

        elif _openai_base_url(runtime) and not _anthropic_base_url(runtime):
            # 2b. 纯 OpenAI provider（无 Anthropic 端点配置）→ 自动用 gateway bridge
            openai_url = _openai_base_url(runtime)
            api_key = runtime.get("openai_api_key") or runtime.get("api_key", "")
            console.print(
                f"[yellow]⚠ 无 Anthropic 端点，自动通过 OpenAI 端点 bridge[/yellow]"
            )
            cleanup_ctx = gateway_claude_bridge(openai_url, api_key,
                                                heavy_model=probe_model, lb_light_model=lb_light)
            bridge_cfg = cleanup_ctx.__enter__()
            env = _claude_gateway_env(runtime, base_url=bridge_cfg["base_url"], auth_token=bridge_cfg["api_key"])
            state_home = None

        else:
            # 3. 探测失败且无 bridge → 保底继续（剥离 /v1 后缀），让 Claude Code 自己报错
            console.print("[yellow]⚠ Anthropic 端点探测失败，尝试继续（可在 provider 配置 bridge_source_cli 启用自动降级）[/yellow]")
            env = _claude_gateway_env(runtime, base_url=None)
            state_home = None
            cleanup_ctx = None

    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    env["API_TIMEOUT_MS"] = "3000000"

    # bridge 模式下跳过 model slot：Claude Code 用默认 claude-* 模型名通过校验，
    # bridge 在转发时替换成真实模型名（heavy_model / lb_light）。
    _skip_model = auth_mode == "oauth_bridge" or (
        isinstance(model_info, dict) and model_info.get("lb_light")
    )

    if isinstance(model_info, dict):
        if not _skip_model:
            if "opus" in model_info:
                env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = model_info["opus"]
            if "sonnet" in model_info:
                env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = model_info["sonnet"]
            if "haiku" in model_info:
                env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = model_info["haiku"]
            subagent = model_info.get("subagent", model_info.get("sonnet", ""))
            if subagent:
                env["CLAUDE_CODE_SUBAGENT_MODEL"] = subagent

            # 单模型模式：把同一个模型设给所有 slot
            if "model" in model_info and "opus" not in model_info:
                m = model_info["model"]
                env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = m
                env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = m
                env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = m
                env["CLAUDE_CODE_SUBAGENT_MODEL"] = m

        env["CLAUDE_CODE_ENABLE_SUBAGENT_PARALLELISM"] = "1"
        env["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"] = "5"
    elif not _skip_model:
        m = model_info
        env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = m
        env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = m
        env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = m
        env["CLAUDE_CODE_SUBAGENT_MODEL"] = m

    cmd = ["claude"]
    if runtime.get("bypass"):
        cmd.append("--dangerously-skip-permissions")
    try:
        _exec_or_run(cmd, env, once, state_home=state_home, cleanup_context=cleanup_ctx)
    finally:
        if cleanup_ctx is not None:
            cleanup_ctx.__exit__(None, None, None)


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

    # ---- 内存缓存（TTL 1h）----
    cached = _ANTHROPIC_URL_CACHE.get(provider_id)
    if cached:
        age = (datetime.now() - cached["ts"]).total_seconds()
        if age < 3600:
            return cached["url"], "cached"

    # ---- 使用公共工具探测（复用 ccs_core.detect_working_base_url）----
    url = configured.rstrip("/")
    # Claude Code SDK 固定追加 /v1/messages，所以探测路径是 /v1/messages
    body = json.dumps({
        "model": probe_model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }).encode()
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    console.print("[dim]正在探测 Anthropic 端点...[/dim]")
    candidate = detect_working_base_url(url, "/v1/messages", headers, body=body, timeout=5)

    if candidate is not None:
        _ANTHROPIC_URL_CACHE[provider_id] = {"url": candidate, "ts": datetime.now()}
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


def _cleanup_stale_sessions(sessions_dir):
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
            shutil.rmtree(stale, ignore_errors=True)
        except PermissionError:
            pass  # 进程存在但无权限发信号，跳过


def _claude_gateway_env(runtime, base_url=None, auth_token=None):
    """Gateway api_key 模式独立 HOME（per-PID 会话隔离）：
    - 每个 mms 进程使用独立的 ~/.config/mms/claude-gateway/s/{pid}/ 作为 HOME
    - 启动时清理已死进程的残留目录
    - 剥离 migration 标记，防止 claude-sonnet-4-6[1m] 自动升级
    - 自动拉取 gateway 模型列表，填入所有 ANTHROPIC_*_MODEL slot
    - 写入 settings.json：teams 模式 / 隐藏 AI 署名 / 扩展思考
    base_url: 由 _resolve_anthropic_base_url() 探测后传入；
              为 None 时从 runtime 推断并去掉 /v1 后缀（保底兼容）。
    auth_token: 覆盖 ANTHROPIC_AUTH_TOKEN（bridge 模式传 bridge token）。
    """
    import json as _json
    gateway_base = os.path.expanduser("~/.config/mms/claude-gateway")
    sessions_dir = os.path.join(gateway_base, "s")
    gateway_home = os.path.join(sessions_dir, str(os.getpid()))
    os.makedirs(gateway_home, exist_ok=True)

    # 清理 stale sessions（PID 已不存在的目录）
    _cleanup_stale_sessions(sessions_dir)

    # 若调用方已通过 _resolve_anthropic_base_url 探测到正确 URL，直接用；
    # 否则保底剥离 /v1（避免双重 /v1/v1/messages）。
    if base_url is None:
        base_url = _anthropic_base_url(runtime)
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]

    # ── .claude.json：剥离 migration flags + 写入 thinking/attribution ──
    # 合并策略：真实 ~/.claude.json 为基础，保留 per-session 已有的用户确认状态
    real_json = os.path.expanduser("~/.claude.json")
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
    data.pop("sonnet1m45MigrationComplete", None)
    data.pop("opusProMigrationComplete", None)
    data["alwaysThinkingEnabled"] = True
    with open(gw_json, "w", encoding="utf-8") as f:
        _json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # ── .local symlink：Claude Code 检测 $HOME/.local/bin/claude（installMethod=native）──
    real_local = os.path.expanduser("~/.local")
    gw_local = os.path.join(gateway_home, ".local")
    if os.path.isdir(real_local) and not os.path.exists(gw_local) and not os.path.islink(gw_local):
        os.symlink(real_local, gw_local)

    # ── Library symlink：macOS Keychain 需要 ~/Library/Keychains ──
    real_library = os.path.expanduser("~/Library")
    gw_library = os.path.join(gateway_home, "Library")
    if os.path.isdir(real_library) and not os.path.exists(gw_library) and not os.path.islink(gw_library):
        os.symlink(real_library, gw_library)

    # ── ~/.claude 目录：创建真实目录，分项 symlink 子目录，单独写 settings.json ──
    gw_claude_dir = os.path.join(gateway_home, ".claude")
    real_claude_dir = os.path.expanduser("~/.claude")
    # 如果 gw_claude_dir 是整目录 symlink（旧版遗留），删掉重建为真实目录
    if os.path.islink(gw_claude_dir):
        os.unlink(gw_claude_dir)
    os.makedirs(gw_claude_dir, exist_ok=True)
    # symlink all real subdirs/files except settings.json
    if os.path.isdir(real_claude_dir):
        for entry in os.listdir(real_claude_dir):
            if entry == "settings.json":
                continue
            src = os.path.join(real_claude_dir, entry)
            dst = os.path.join(gw_claude_dir, entry)
            if not os.path.exists(dst) and not os.path.islink(dst):
                os.symlink(src, dst)

    # ── settings.json：继承用户配置 + 覆盖 gateway 必要字段 ──
    effective_token = auth_token or runtime["api_key"]
    # bridge 模式下 base_url 是本地代理，不应拉模型列表；直连模式才探测
    best_model = None if auth_token else _pick_gateway_model(runtime, base_url)
    settings_env: dict = {
        "ANTHROPIC_AUTH_TOKEN": effective_token,
        "ANTHROPIC_BASE_URL": base_url,
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
    }
    if best_model:
        for key in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
                    "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                    "ANTHROPIC_REASONING_MODEL"):
            settings_env[key] = best_model
    # 读取用户真实 settings.json 作为基础
    real_settings_path = os.path.join(real_claude_dir, "settings.json")
    settings_data: dict = {}
    if os.path.exists(real_settings_path):
        try:
            with open(real_settings_path, encoding="utf-8") as f:
                settings_data = _json.load(f)
        except Exception:
            settings_data = {}
    # gateway 必须控制的字段 — 覆盖
    settings_data["env"] = settings_env
    settings_data["includeCoAuthoredBy"] = False
    settings_data["attribution"] = {"commit": "", "pr": ""}
    gw_settings = os.path.join(gw_claude_dir, "settings.json")
    with open(gw_settings, "w", encoding="utf-8") as f:
        _json.dump(settings_data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    env = os.environ.copy()
    env["HOME"] = gateway_home
    env["ANTHROPIC_BASE_URL"] = base_url
    env["ANTHROPIC_AUTH_TOKEN"] = effective_token
    if best_model:
        for key in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
                    "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                    "ANTHROPIC_REASONING_MODEL"):
            env[key] = best_model
    env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
    return env


def _codex_gateway_env(runtime, base_url):
    """为 gateway api_key 模式创建独立 HOME，session 数据持久保留。"""
    import json as _json
    openai_key = runtime.get("openai_api_key") or runtime["api_key"]
    gateway_home = os.path.expanduser("~/.config/mms/codex-gateway")
    codex_dir = os.path.join(gateway_home, ".codex")
    os.makedirs(codex_dir, exist_ok=True)

    auth_path = os.path.join(codex_dir, "auth.json")
    with open(auth_path, "w") as f:
        _json.dump({"auth_mode": "apikey", "OPENAI_API_KEY": openai_key}, f)

    # 复制用户 config.toml，但把 base_url 替换成 gateway 地址
    # Codex CLI 优先读 config 里的 base_url，env var 不一定能覆盖
    real_config = os.path.expanduser("~/.codex/config.toml")
    gateway_config = os.path.join(codex_dir, "config.toml")
    if os.path.exists(real_config):
        try:
            with open(real_config, "r", encoding="utf-8") as f:
                config_text = f.read()
            import re
            config_text = re.sub(
                r'^base_url\s*=\s*"[^"]*"',
                f'base_url = "{base_url}"',
                config_text,
                count=1,
                flags=re.MULTILINE,
            )
            with open(gateway_config, "w", encoding="utf-8") as f:
                f.write(config_text)
        except Exception:
            shutil.copy2(real_config, gateway_config)

    env = os.environ.copy()
    env["HOME"] = gateway_home
    env["OPENAI_API_KEY"] = openai_key
    env["OPENAI_BASE_URL"] = base_url
    return env


def _is_gpt_model(model_name):
    """Check if a model name is a GPT model (supports Responses API natively)."""
    if not model_name:
        return True  # Default to GPT behavior if no model specified
    lower = model_name.lower()
    return any(kw in lower for kw in ("gpt-", "gpt4", "gpt5", "o1", "o3", "o4"))


def launch_codex(model_info, runtime, once=False):
    """启动 Codex，支持 provider 和 OAuth 账号档案两种模式。
    非 GPT 模型自动走 Chat Completions bridge（gateway 的 /v1/responses 只支持 GPT）。"""
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

    if not _is_gpt_model(model):
        # Non-GPT model: gateway /v1/responses doesn't support it,
        # use local bridge to translate Responses API → Chat Completions API
        console.print(f"[dim]非 GPT 模型 ({model})，启动 Chat Completions bridge...[/dim]")
        api_key = runtime.get("openai_api_key") or runtime.get("api_key", "")
        with codex_chatcompletions_bridge(gateway_url, api_key, model_name=model) as bridge_cfg:
            env = _codex_gateway_env(runtime, bridge_cfg["base_url"])
            env["OPENAI_API_KEY"] = bridge_cfg["api_key"]
            env["OPENAI_BASE_URL"] = bridge_cfg["base_url"]
            cmd = ["codex"]
            cmd += ["-c", f'base_url="{bridge_cfg["base_url"]}/v1"']
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

    # GPT model: direct Responses API to gateway
    env = _codex_gateway_env(runtime, gateway_url)
    cmd = ["codex"]
    cmd += ["-c", f'base_url="{gateway_url}"']
    cmd += ["-c", "features.responses_websockets=false"]
    cmd += ["-c", "features.responses_websockets_v2=false"]
    if model:
        cmd += ["-m", model]
    if runtime.get("bypass"):
        cmd.append("--dangerously-bypass-approvals-and-sandbox")

    _exec_or_run(cmd, env, once)


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
            import httpx as _httpx
            base_url = _openai_base_url(runtime) or _anthropic_base_url(runtime)
            api_key = runtime.get("api_key", "")
            if base_url and api_key:
                url_v1 = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
                r = _httpx.get(f"{url_v1}/models",
                               headers={"Authorization": f"Bearer {api_key}"},
                               timeout=5, follow_redirects=True)
                if r.status_code == 200:
                    models = [m.get("id", "") for m in r.json().get("data", []) if m.get("id")]
                    if models:
                        console.print(f"[dim]可用模型 ({len(models)}): {', '.join(models[:8])}"
                                      f"{'…' if len(models) > 8 else ''}[/dim]")
        except Exception:
            pass

    # ── 本地用量统计 ──
    try:
        usage_path = os.path.expanduser("~/.config/mms/usage.json")
        if not os.path.exists(usage_path):
            usage_path = os.path.expanduser("~/.config/ccs/usage.json")
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


def _exec_or_run(cmd, env, once, cleanup_path=None, state_home=None, cleanup_context=None):
    """默认用 execvp；需要清理临时文件时回退到 subprocess。"""
    from shutil import which
    exe = which(cmd[0])
    if not exe:
        console.print(f"[red]{cmd[0]} 未找到，请先安装[/red]")
        sys.exit(1)

    if once or cleanup_path or state_home or cleanup_context:
        try:
            if state_home:
                with activated_claude_account_state(state_home):
                    result = subprocess.run(cmd, env=env)
            else:
                result = subprocess.run(cmd, env=env)
            sys.exit(result.returncode)
        except KeyboardInterrupt:
            sys.exit(0)
        finally:
            if cleanup_path and os.path.exists(cleanup_path):
                os.remove(cleanup_path)
    else:
        os.execvpe(exe, cmd, env)
