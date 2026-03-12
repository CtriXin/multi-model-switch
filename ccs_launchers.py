"""CCS 启动器：四个 CLI 的环境变量和命令行映射"""

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


def _resolve_model(model_info):
    """从 model_info dict 中提取 model 名称（单模型场景）"""
    if isinstance(model_info, str):
        return model_info
    return model_info.get("model", model_info.get("sonnet", ""))


def launch_claude(model_info, base_url, api_key, once=False):
    """启动 Claude Code，通过环境变量配置"""
    env = os.environ.copy()

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


def launch_codex(model_info, base_url, api_key, once=False):
    """启动 Codex，通过环境变量 + -m flag"""
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = api_key
    env["OPENAI_BASE_URL"] = f"{base_url}/v1"

    model = _resolve_model(model_info)
    cmd = ["codex"]
    if model:
        cmd += ["-m", model]

    _exec_or_run(cmd, env, once)


def launch_qwen(model_info, base_url, api_key, once=False):
    """启动 Qwen，通过 CLI flags 配置"""
    model = _resolve_model(model_info)
    cmd = [
        "qwen",
        "--openai-base-url", f"{base_url}/v1",
        "--openai-api-key", api_key,
    ]
    if model:
        cmd += ["-m", model]

    _exec_or_run(cmd, os.environ.copy(), once)


def launch_kimi(model_info, base_url, api_key, once=False):
    """启动 Kimi：优先走自定义 provider，无配置时退回 OAuth。"""
    model = _resolve_model(model_info)
    env = os.environ.copy()
    cmd = ["kimi"]

    if base_url and api_key and model:
        provider_name = "ccs-openai"
        model_id = f"{provider_name}/{model}"
        config_toml = (
            f'default_model = "{model_id}"\n'
            f'[models."{model_id}"]\n'
            f'provider = "{provider_name}"\n'
            f'model = "{model}"\n'
            f'capabilities = ["thinking"]\n'
            f'[providers."{provider_name}"]\n'
            f'type = "openai_legacy"\n'
            f'base_url = "{base_url}/v1"\n'
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


def get_export_env(cli, base_url, api_key):
    """返回指定 CLI 需要的 export 环境变量字典。"""
    exports = {}
    if cli == "claude":
        exports["ANTHROPIC_BASE_URL"] = base_url
        exports["ANTHROPIC_AUTH_TOKEN"] = api_key
        exports["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        exports["API_TIMEOUT_MS"] = "3000000"
    elif cli == "codex":
        exports["OPENAI_API_KEY"] = api_key
        exports["OPENAI_BASE_URL"] = f"{base_url}/v1"
    elif cli == "kimi":
        exports["OPENAI_API_KEY"] = api_key
        exports["OPENAI_BASE_URL"] = f"{base_url}/v1"
    return exports


def launch_cli(cli, model_info, base_url, api_key, once=False):
    """统一启动入口"""
    launcher = LAUNCHERS.get(cli)
    if not launcher:
        console.print(f"[red]不支持的 CLI: {cli}[/red]")
        sys.exit(1)

    model_display = _resolve_model(model_info) if not isinstance(model_info, dict) else \
        model_info.get("model", model_info.get("sonnet", "多模型配置"))

    console.print(f"\n[bold green]🚀 启动 {cli}[/bold green] — {model_display}")
    console.print("[dim]─" * 40 + "[/dim]\n")

    launcher(model_info, base_url, api_key, once=once)


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
