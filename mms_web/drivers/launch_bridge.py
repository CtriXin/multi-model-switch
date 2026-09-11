"""Launch the original MMS launcher in a dedicated process per Web session."""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from ..runtime import private_json, real_home, require_private_root
from .base import LaunchSeamUnavailable

_WORKER = Path(__file__).resolve().parents[1] / "launch_worker.py"


@dataclass
class LaunchPlan:
    cmd: list[str]
    env: dict
    cwd: str
    harness: str
    session_home: str | None = None
    notes: list[str] = field(default_factory=list)


def pi_runtime() -> tuple[str, str]:
    executable = shutil.which("pi")
    if not executable:
        return "", ""
    # npm/fnm installations have a matching Node beside their global bin.
    # A GUI-launched shell may otherwise select a different Homebrew Node.
    candidates = []
    resolved = Path(executable).resolve()
    for parent in resolved.parents:
        if parent.name == "node_modules" and parent.parent.name == "lib":
            candidates.append(parent.parent.parent / "bin" / "node")
            break
    current = shutil.which("node")
    if current:
        candidates.append(Path(current))
    for node in candidates:
        if not node.is_file():
            continue
        try:
            result = subprocess.run([str(node), "-e", "process.exit(typeof require('node:zlib').createZstdDecompress === 'function' ? 0 : 1)"], capture_output=True, timeout=5)
            if result.returncode == 0:
                return executable, str(node)
        except (OSError, subprocess.TimeoutExpired):
            continue
    return executable, ""


def probe_mms_pi_seam() -> dict:
    """Whether this machine can run a Pi session, and what is missing if not.

    The reason reaches the page, so it has to name the thing to install rather
    than restate that something is wrong.
    """
    executable, node = pi_runtime()
    if not executable:
        reason = "找不到 pi 命令。重新运行安装脚本，或在能运行 pi 的终端里启动 Pilot。"
    elif not node:
        # pi_runtime accepts a Node only when node:zlib has zstd, which
        # arrived in 22.15. An older Node is the usual cause on a machine
        # where pi itself installed fine.
        reason = "没有找到符合要求的 Node.js：需要 22.15 以上的版本。升级 Node 后重启 Pilot。"
    elif not _WORKER.is_file():
        reason = "这份安装缺少会话执行组件，请重新运行安装脚本。"
    else:
        reason = ""
    return {"available": not reason, "driver": "pi-rpc",
            "launcher": "mms_launchers.launch_cli", "reason": reason}


def build_pi_launch_plan(model_info, runtime, cwd, *, config_root=None, extra_args=None):
    if not isinstance(runtime, dict) or runtime.get("auth_mode", "api_key") != "api_key":
        raise LaunchSeamUnavailable("仅支持所选模型服务的 API Key 通道")
    root = runtime.get("_webConfigRoot")
    if not root:
        raise LaunchSeamUnavailable("缺少独立 MMS 运行目录")
    root = require_private_root(Path(root))
    if not (root / "config.toml").is_file():
        raise LaunchSeamUnavailable("独立 MMS 运行配置不存在")
    executable, node = pi_runtime()
    if not executable or not node:
        raise LaunchSeamUnavailable("需要安装 Pi 和兼容的 Node.js 运行环境")
    env = os.environ.copy()
    env["PATH"] = str(Path(node).parent) + os.pathsep + env.get("PATH", "")
    env.update(MMS_CONFIG_ROOT=str(root), MMS_REAL_HOME=str(real_home()), MMS_WEB_WORKER="1")
    env["PYTHONUNBUFFERED"] = "1"
    payload = root / ("launch-" + uuid.uuid4().hex + ".json")
    private_json(payload, {
        "modelInfo": model_info,
        "runtime": {k: v for k, v in runtime.items() if not k.startswith("_web")},
        "extraArgs": ["--mode", "rpc", "--session", str(root / "conversation.jsonl"), *(extra_args or [])],
    })
    return LaunchPlan([sys.executable, str(_WORKER), str(payload)], env, str(cwd), "pi",
                     notes=["original MMS launcher in a dedicated worker process"])


def mms_pi_launch_plan_builder(config_root=None):
    def build(harness, model_info, runtime, cwd):
        return build_pi_launch_plan(model_info, runtime, cwd) if harness == "pi" else None
    return build


def fixed_command_plan_builder(cmd, *, env=None):
    def build(harness, model_info, runtime, cwd):
        return LaunchPlan(list(cmd), dict(env or os.environ), str(cwd), str(harness))
    return build
