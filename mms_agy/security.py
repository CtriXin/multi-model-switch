"""Antigravity account keychain and security wrapper helpers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys


def _launchers():
    import mms_launchers as _module

    return _module


def macos_security_bin():
    if sys.platform != "darwin":
        return ""
    for candidate in ("/usr/bin/security", shutil.which("security")):
        if candidate and os.path.exists(candidate):
            return candidate
    return ""


def agy_keychain_path(account_home):
    return os.path.join(account_home, "Library", "Keychains", "login.keychain-db")


def agy_security_home_env(security_home):
    env = os.environ.copy()
    env["HOME"] = security_home
    env["MMS_SESSION_HOME"] = security_home
    env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    env["XDG_CONFIG_HOME"] = os.path.join(security_home, ".config")
    env["XDG_CACHE_HOME"] = os.path.join(security_home, ".cache")
    env["XDG_DATA_HOME"] = os.path.join(security_home, ".local", "share")
    env["XDG_STATE_HOME"] = os.path.join(security_home, ".local", "state")
    return env


def run_agy_security_command(security_bin, args, *, security_home, check=False):
    try:
        result = subprocess.run(
            [security_bin, *args],
            env=_launchers()._agy_security_home_env(security_home),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except Exception:
        return False
    return result.returncode == 0 or not check


def ensure_agy_account_keychain(account_home, session_home=None):
    """Create a per-account default keychain before Antigravity OAuth writes."""
    account_home = os.path.abspath(os.path.expanduser(str(account_home or "").strip()))
    if not account_home:
        return ""
    keychain_path = _launchers()._agy_keychain_path(account_home)
    os.makedirs(os.path.dirname(keychain_path), exist_ok=True)
    os.makedirs(os.path.join(account_home, "Library", "Preferences"), exist_ok=True)

    security_bin = _launchers()._macos_security_bin()
    if not security_bin:
        return keychain_path

    security_home = os.path.abspath(os.path.expanduser(str(session_home or account_home).strip()))
    os.makedirs(security_home, exist_ok=True)
    if not os.path.exists(keychain_path):
        if not _launchers()._run_agy_security_command(
            security_bin,
            ["create-keychain", "-p", "", keychain_path],
            security_home=security_home,
            check=True,
        ):
            return keychain_path

    _launchers()._run_agy_security_command(security_bin, ["set-keychain-settings", "-lut", "21600", keychain_path], security_home=security_home)
    _launchers()._run_agy_security_command(security_bin, ["unlock-keychain", "-p", "", keychain_path], security_home=security_home)
    _launchers()._run_agy_security_command(security_bin, ["list-keychains", "-d", "user", "-s", keychain_path], security_home=security_home)
    _launchers()._run_agy_security_command(security_bin, ["default-keychain", "-d", "user", "-s", keychain_path], security_home=security_home)
    return keychain_path


def install_agy_security_wrapper(session_home, account_home, env):
    security_bin = _launchers()._macos_security_bin()
    if not security_bin:
        return ""
    wrapper_dir = os.path.join(session_home, ".mms", "bin")
    os.makedirs(wrapper_dir, exist_ok=True)
    wrapper_path = os.path.join(wrapper_dir, "security")
    wrapper = [
        "#!/bin/sh",
        f'export HOME={json.dumps(session_home)}',
        f'export MMS_SESSION_HOME={json.dumps(session_home)}',
        f'export MMS_AGY_ACCOUNT_HOME={json.dumps(account_home)}',
        f'export PATH={json.dumps("/usr/bin:/bin:/usr/sbin:/sbin")}',
        f'export XDG_CONFIG_HOME={json.dumps(os.path.join(session_home, ".config"))}',
        f'export XDG_CACHE_HOME={json.dumps(os.path.join(session_home, ".cache"))}',
        f'export XDG_DATA_HOME={json.dumps(os.path.join(session_home, ".local", "share"))}',
        f'export XDG_STATE_HOME={json.dumps(os.path.join(session_home, ".local", "state"))}',
        f'exec {json.dumps(security_bin)} "$@"',
        "",
    ]
    _launchers()._write_real_home_script(wrapper_path, wrapper)
    return wrapper_path
