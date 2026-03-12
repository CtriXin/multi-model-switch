"""MMS/CCS 启动器：按 provider 配置四个 CLI 的环境变量和命令行映射"""

import os
import sys
import subprocess
import tempfile

try:
    from rich.console import Console
except ImportError:
    pass

console = Console()
RUNTIME_DIR = os.path.expanduser("~/.config/ccs/runtime")
CLI_PROTOCOL_REQUIREMENTS = {
    "claude": "anthropic_messages",
    "codex": "openai_chat_completions",
    "qwen": "openai_chat_completions",
    "kimi": "openai_chat_completions",
}


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
        console.print(
            f"[red]provider '{provider_id}' ({provider_name}) 缺少协议 {required_protocol}，无法驱动 {cli}[/red]"
        )
        sys.exit(1)

    if not provider.get("base_url"):
        console.print(f"[red]provider '{provider_id}' 未配置 base_url[/red]")
        sys.exit(1)

    if not provider.get("api_key"):
        console.print(f"[red]provider '{provider_id}' 未配置 api_key[/red]")
        sys.exit(1)


def _openai_base_url(provider):
    return f"{provider['base_url'].rstrip('/')}/v1"


def _resolve_model(model_info):
    """从 model_info dict 中提取 model 名称（单模型场景）"""
    if isinstance(model_info, str):
        return model_info
    return model_info.get("model", model_info.get("sonnet", ""))


def launch_claude(model_info, provider, once=False):
    """启动 Claude Code，通过环境变量配置"""
    env = os.environ.copy()
    base_url = provider["base_url"]
    api_key = provider["api_key"]

    env["ANTHROPIC_BASE_URL"] = base_url
    env["ANTHROPIC_AUTH_TOKEN"] = api_key
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    env["API_TIMEOUT_MS"] = "3000000"

    if isinstance(model_info, dict):
        if "opus" in model_info:
            env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = model_info["opus"]
        if "sonnet" in model_info:
            env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = model_info["sonnet"]
        if "haiku" in model_info:
            env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = model_info["haiku"]
        subagent = model_info.get("subagent", model_info.get("sonnet", ""))
        if subagent:
            env["CLAUDE_CODE_SUBAGENT_MODEL"] = subagent
        env["CLAUDE_CODE_ENABLE_SUBAGENT_PARALLELISM"] = "1"
        env["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"] = "5"

        # 单模型模式：把同一个模型设给所有 slot
        if "model" in model_info and "opus" not in model_info:
            m = model_info["model"]
            env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = m
            env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = m
            env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = m
            env["CLAUDE_CODE_SUBAGENT_MODEL"] = m
    else:
        m = model_info
        env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = m
        env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = m
        env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = m
        env["CLAUDE_CODE_SUBAGENT_MODEL"] = m

    cmd = ["claude"]
    _exec_or_run(cmd, env, once)


def launch_codex(model_info, provider, once=False):
    """启动 Codex，通过环境变量 + -m flag"""
    env = os.environ.copy()
    api_key = provider["api_key"]
    env["OPENAI_API_KEY"] = api_key
    env["OPENAI_BASE_URL"] = _openai_base_url(provider)

    model = _resolve_model(model_info)
    cmd = ["codex"]
    if model:
        cmd += ["-m", model]

    _exec_or_run(cmd, env, once)


def launch_qwen(model_info, provider, once=False):
    """启动 Qwen，通过 CLI flags 配置"""
    base_url = provider["base_url"]
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
    base_url = provider["base_url"]
    api_key = provider["api_key"]
    model = _resolve_model(model_info)
    env = os.environ.copy()
    cmd = ["kimi"]

    if base_url and api_key and model:
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


LAUNCHERS = {
    "claude": launch_claude,
    "codex": launch_codex,
    "qwen": launch_qwen,
    "kimi": launch_kimi,
}


def get_export_env(cli, provider):
    """返回指定 CLI 需要的 export 环境变量字典。"""
    validate_provider_for_cli(cli, provider)
    base_url = provider["base_url"]
    api_key = provider["api_key"]
    exports = {}
    if cli == "claude":
        exports["ANTHROPIC_BASE_URL"] = base_url
        exports["ANTHROPIC_AUTH_TOKEN"] = api_key
        exports["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        exports["API_TIMEOUT_MS"] = "3000000"
    elif cli == "codex":
        exports["OPENAI_API_KEY"] = api_key
        exports["OPENAI_BASE_URL"] = _openai_base_url(provider)
    elif cli == "kimi":
        exports["OPENAI_API_KEY"] = api_key
        exports["OPENAI_BASE_URL"] = _openai_base_url(provider)
    return exports


def launch_cli(cli, model_info, provider, once=False):
    """统一启动入口"""
    launcher = LAUNCHERS.get(cli)
    if not launcher:
        console.print(f"[red]不支持的 CLI: {cli}[/red]")
        sys.exit(1)
    validate_provider_for_cli(cli, provider)

    model_display = _resolve_model(model_info) if not isinstance(model_info, dict) else \
        model_info.get("model", model_info.get("sonnet", "多模型配置"))
    provider_label = provider.get("name", provider.get("id", "provider"))

    console.print(f"\n[bold green]🚀 启动 {cli}[/bold green] — {model_display}")
    console.print(f"[dim]provider: {provider_label} ({provider.get('id', 'default')})[/dim]")
    console.print("[dim]─" * 40 + "[/dim]\n")

    launcher(model_info, provider, once=once)


def _write_runtime_config(prefix, content):
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".toml", dir=RUNTIME_DIR)
    os.chmod(path, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _exec_or_run(cmd, env, once, cleanup_path=None):
    """默认用 execvp；需要清理临时文件时回退到 subprocess。"""
    from shutil import which
    exe = which(cmd[0])
    if not exe:
        console.print(f"[red]{cmd[0]} 未找到，请先安装[/red]")
        sys.exit(1)

    if once or cleanup_path:
        try:
            result = subprocess.run(cmd, env=env)
            sys.exit(result.returncode)
        except KeyboardInterrupt:
            sys.exit(0)
        finally:
            if cleanup_path and os.path.exists(cleanup_path):
                os.remove(cleanup_path)
    else:
        os.execvpe(exe, cmd, env)
