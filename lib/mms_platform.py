"""Platform and browser capability facts shared by CLI and Pilot Web.

The registry is descriptive: it never probes or mutates a user's config,
account, browser profile, or runtime. Unknown login state stays ``unknown``.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class PlatformDescriptor:
    os: str
    shell: str
    home: str
    config_root: str
    state_root: str
    temp_root: str
    path_style: str
    process_control: str
    file_picker: str

    def to_dict(self) -> dict[str, str]:
        return {
            "os": self.os,
            "shell": self.shell,
            "home": self.home,
            "configRoot": self.config_root,
            "stateRoot": self.state_root,
            "tempRoot": self.temp_root,
            "pathStyle": self.path_style,
            "processControl": self.process_control,
            "filePicker": self.file_picker,
        }


@dataclass(frozen=True)
class BrowserCapability:
    backend: str
    supported: bool
    logged_in: bool | None = None
    reason: str = ""
    requires: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        result = {
            "backend": self.backend,
            "supported": self.supported,
            "loggedIn": self.logged_in if self.logged_in is not None else "unknown",
        }
        if self.reason:
            result["reason"] = self.reason
        if self.requires:
            result["requires"] = list(self.requires)
        return result


def _path(value: str | os.PathLike[str]) -> Path:
    return Path(value).expanduser().resolve()


def _effective_config_root(env: Mapping[str, str], fallback: Path) -> Path:
    """The config root MMS actually resolves, not a second opinion about it.

    A descriptor that names one directory while `mms` reads another is worse
    than no descriptor: the Pilot page would show a root nothing uses. There is
    one config-root resolver, so ask it.
    """
    try:
        from mms_state_io import resolve_mms_config_dir
    except Exception:
        return fallback
    try:
        return _path(resolve_mms_config_dir(env))
    except Exception:
        return fallback


def describe_platform(*, platform_name: str | None = None,
                      env: Mapping[str, str] | None = None,
                      home: str | os.PathLike[str] | None = None) -> PlatformDescriptor:
    """Return platform paths without creating directories or reading secrets."""
    env = os.environ if env is None else env
    platform_name = platform_name or sys.platform
    is_windows = platform_name == "win32"
    os_name = "win32" if is_windows else ("darwin" if platform_name == "darwin" else "linux")
    home_path = _path(home or env.get("USERPROFILE") or env.get("HOME") or Path.home())
    if is_windows:
        appdata = _path(env.get("APPDATA") or home_path / "AppData" / "Roaming")
        local = _path(env.get("LOCALAPPDATA") or home_path / "AppData" / "Local")
        config = _effective_config_root(env, _path(appdata / "MMS" / "mms-next"))
        state = _path(env.get("MMS_STATE_ROOT") or local / "MMS" / "mms-web")
        temp = _path(env.get("TEMP") or env.get("TMP") or tempfile.gettempdir())
        return PlatformDescriptor(
            os=os_name,
            shell=env.get("ComSpec") or "powershell.exe",
            home=str(home_path), config_root=str(config), state_root=str(state),
            temp_root=str(temp), path_style="windows",
            # A new process group plus DETACHED_PROCESS is what `mms web start`
            # asks for; Pi children are not in a Job Object yet.
            process_control="windows-process-group",
            # The backend has no Windows folder chooser: the page asks the user
            # to type or paste a path. Claiming a PowerShell picker exists would
            # be a capability the product does not have.
            file_picker="html",
        )
    config = _effective_config_root(env, _path(home_path / ".config" / "mms-next"))
    state_base = env.get("XDG_DATA_HOME") or home_path / ".local" / "share"
    state = _path(env.get("MMS_STATE_ROOT") or Path(state_base) / "mms-web")
    return PlatformDescriptor(
        os=os_name,
        shell=env.get("SHELL") or "/bin/sh",
        home=str(home_path), config_root=str(config), state_root=str(state),
        temp_root=str(_path(env.get("TMPDIR") or tempfile.gettempdir())),
        path_style="posix", process_control="posix-process-group",
        file_picker="osascript" if os_name == "darwin" else "html",
    )


def browser_capabilities(*, platform_name: str | None = None,
                         which=shutil.which) -> list[BrowserCapability]:
    """Describe available browser routes and their explicit login boundary."""
    platform_name = platform_name or sys.platform
    if platform_name == "win32":
        return [
            BrowserCapability("web-access", True, None,
                              "需要用户已授权的 Edge 或 Chrome CDP 会话。",
                              ("Edge/Chrome CDP",)),
            BrowserCapability("edge-cdp", True, None,
                              "仅在 Edge 以 remote debugging 启动并已登录时可用。",
                              ("Edge remote debugging",)),
            BrowserCapability("chrome-cdp", True, None,
                              "仅在 Chrome 以 remote debugging 启动并已登录时可用。",
                              ("Chrome remote debugging",)),
            BrowserCapability("playwright", bool(which("playwright")), False,
                              "isolated backend，不复用浏览器登录态；未找到 Playwright executable。"),
            BrowserCapability("agent-browser", bool(which("agent-browser")), False,
                              "isolated backend，不复用浏览器登录态。"),
            BrowserCapability("ego", False, None,
                              "上游当前没有可验证的 Windows Ego runtime。"),
        ]
    ego = bool(which("ego-browser"))
    return [
        BrowserCapability("ego", ego, None if not ego else False,
                          "未找到 ego-browser executable。" if not ego else "需按 Ego 登录态合同使用。"),
        BrowserCapability("web-access", True, None, "需要已授权的 CDP 或 web-access backend。"),
        BrowserCapability("playwright", bool(which("playwright")), False,
                          "isolated backend，不复用浏览器登录态；未找到 Playwright executable。"),
        BrowserCapability("agent-browser", bool(which("agent-browser")), False,
                          "isolated backend，不复用浏览器登录态。"),
    ]


def capability_snapshot() -> dict:
    return {
        "platform": describe_platform().to_dict(),
        "browser": [item.to_dict() for item in browser_capabilities()],
    }
