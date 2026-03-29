"""MMS CLI 自动安装"""

import subprocess
import sys
from shutil import which

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
    "gemini": "npm install -g @google/gemini-cli",
    "qwen": "npm install -g @qwen-code/qwen-code",
    "kimi": "uv tool install kimi-cli",
}

CLI_DESCRIPTIONS = {
    "claude": "Claude Code (Anthropic)",
    "codex": "Codex CLI (OpenAI)",
    "gemini": "Gemini CLI (Google)",
    "qwen": "Qwen Code (Alibaba)",
    "kimi": "Kimi CLI (Moonshot)",
}

NVM_INSTALL = "curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash"
NODE22_INSTALL = (
    'export NVM_DIR="$HOME/.nvm" && '
    '[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && '
    'nvm install 22 && nvm alias default 22 && nvm use 22'
)


def _node_major_version():
    if not which("node"):
        return None

    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except Exception:
        return None

    version = result.stdout.strip().lstrip("v")
    major = version.split(".", 1)[0]
    return int(major) if major.isdigit() else None


def _nvm_has_node22():
    try:
        result = subprocess.run(
            [
                "/bin/bash",
                "-lc",
                'export NVM_DIR="$HOME/.nvm"; '
                '[ -s "$NVM_DIR/nvm.sh" ] || exit 1; '
                '. "$NVM_DIR/nvm.sh"; '
                'nvm version 22'
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return False

    return result.returncode == 0 and result.stdout.strip() != "N/A"


def _use_nvm_node22():
    return _run_install(
        "node",
        'export NVM_DIR="$HOME/.nvm" && '
        '[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && '
        'nvm alias default 22 && nvm use 22',
    )


def _ensure_node22():
    major = _node_major_version()
    if major is not None and major >= 22:
        console.print(f"[green]✓ Node.js v{major} 已满足 Qwen 依赖[/green]")
        return True

    if _nvm_has_node22():
        console.print("[green]✓ 检测到 nvm 已安装 Node.js 22，直接切换[/green]")
        return _use_nvm_node22()

    console.print("[yellow]Qwen 安装前需要 Node.js 22+[/yellow]")
    console.print("[dim]将通过 nvm 安装 Node.js 22；nvm 可能写入你的 shell 配置。[/dim]")

    if not Confirm.ask("是否继续安装 nvm / Node.js 22？"):
        console.print("[yellow]跳过 Node.js 安装[/yellow]")
        return False

    if not _run_install("nvm", NVM_INSTALL):
        return False
    return _run_install("node", NODE22_INSTALL)


def check_and_offer_install(cli_name):
    """检查 CLI 是否安装，未安装则提示安装"""
    if which(cli_name):
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

    if cli_name == "qwen" and not _ensure_node22():
        return False

    return _run_install(cli_name, cmd)


def install_cli(cli_name):
    """直接安装指定 CLI"""
    if cli_name not in INSTALL_COMMANDS:
        console.print(f"[red]不支持的 CLI: {cli_name}[/red]")
        console.print(f"支持: {', '.join(INSTALL_COMMANDS.keys())}")
        sys.exit(1)

    if which(cli_name):
        console.print(f"[green]{cli_name} 已安装[/green]")
        # Show version
        try:
            subprocess.run([cli_name, "--version"], timeout=10)
        except Exception:
            pass
        return

    if cli_name == "qwen" and not _ensure_node22():
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
