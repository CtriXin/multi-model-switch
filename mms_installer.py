"""MMS CLI 自动安装"""

import subprocess
import sys

from mms_runtime import resolve_cli_binary

Confirm = None


class _LazyConsole:
    _instance = None
    def __getattr__(self, name):
        if _LazyConsole._instance is None:
            from rich.console import Console
            _LazyConsole._instance = Console()
            global Confirm
            from rich.prompt import Confirm as _C
            Confirm = _C
        return getattr(_LazyConsole._instance, name)

console = _LazyConsole()

INSTALL_COMMANDS = {
    "claude": "curl -fsSL https://claude.ai/install.sh | sh",
    "codex": "brew install codex",
    "opencode": "curl -fsSL https://opencode.ai/install | bash",
    "gemini": "npm install -g @google/gemini-cli",
}

CLI_DESCRIPTIONS = {
    "claude": "Claude Code (Anthropic)",
    "codex": "Codex CLI (OpenAI)",
    "opencode": "OpenCode CLI",
    "gemini": "Gemini CLI (Google)",
}

def check_and_offer_install(cli_name):
    """检查 CLI 是否安装，未安装则提示安装"""
    if resolve_cli_binary(cli_name):
        return True

    desc = CLI_DESCRIPTIONS.get(cli_name, cli_name)
    cmd = INSTALL_COMMANDS.get(cli_name)

    if not cmd:
        console.print(f"[red]{cli_name} 未安装，且无自动安装方式[/red]")
        return False

    console.print(f"[yellow]{desc} 未安装[/yellow]")
    console.print(f"[dim]安装命令: {cmd}[/dim]")

    if not Confirm.ask("是否立即安装？"):
        console.print("[yellow]跳过安装[/yellow]")
        return False

    return _run_install(cli_name, cmd)


def install_cli(cli_name):
    """直接安装指定 CLI"""
    if cli_name not in INSTALL_COMMANDS:
        console.print(f"[red]不支持的 CLI: {cli_name}[/red]")
        console.print(f"支持: {', '.join(INSTALL_COMMANDS.keys())}")
        sys.exit(1)

    existing = resolve_cli_binary(cli_name)
    if existing:
        console.print(f"[green]{cli_name} 已安装[/green]")
        # Show version
        try:
            subprocess.run([existing, "--version"], timeout=10)
        except Exception:
            pass
        return

    cmd = INSTALL_COMMANDS[cli_name]
    console.print(f"正在安装 {CLI_DESCRIPTIONS.get(cli_name, cli_name)}...")
    console.print(f"[dim]$ {cmd}[/dim]")
    _run_install(cli_name, cmd)


def _run_install(cli_name, cmd):
    """执行安装命令"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            timeout=300,
            executable="/bin/bash",
        )
        if result.returncode == 0:
            console.print(f"[green]✓ {cli_name} 安装成功[/green]")
            return True
        else:
            console.print(f"[red]✗ 安装失败 (exit code {result.returncode})[/red]")
            return False
    except subprocess.TimeoutExpired:
        console.print("[red]安装超时[/red]")
        return False
    except Exception as e:
        console.print(f"[red]安装出错: {e}[/red]")
        return False
