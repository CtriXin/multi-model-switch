"""Windows Pi executable resolution: never the extensionless npm shim.

The npm-global layout on Windows puts ``pi`` (POSIX shell), ``pi.cmd`` and
``pi.ps1`` directly in the prefix with no ``bin/`` directory. Only the
``.cmd``/``.exe`` sibling is a valid subprocess.Popen target.
"""
import os
import stat

import pytest


def _npm_layout(tmp_path):
    prefix = tmp_path / "npm-prefix"
    prefix.mkdir()
    bare = prefix / "pi"
    bare.write_text("#!/bin/sh\n", encoding="utf-8")
    bare.chmod(0o755)
    cmd = prefix / "pi.cmd"
    cmd.write_text("@echo off\r\n", encoding="utf-8")
    cmd.chmod(0o755)  # the X_OK check still runs on the POSIX test host
    return prefix, bare, cmd


def test_pi_global_executable_prefers_cmd_sibling_on_windows(tmp_path, monkeypatch):
    import mms_pi_support

    prefix, bare, cmd = _npm_layout(tmp_path)
    monkeypatch.setattr(mms_pi_support.os, "name", "nt")
    # PATHEXT quirk: which() returns the bare shim first.
    monkeypatch.setattr(mms_pi_support.shutil, "which", lambda name: str(bare))

    assert mms_pi_support._pi_global_executable() == str(cmd)


def test_pi_global_executable_uses_windows_prefix_layout_without_bin(tmp_path, monkeypatch):
    """No PATH hit: Windows npm-global has shims in the prefix, not prefix/bin."""
    import mms_pi_support

    prefix, bare, cmd = _npm_layout(tmp_path)
    monkeypatch.setattr(mms_pi_support.os, "name", "nt")
    monkeypatch.setattr(mms_pi_support.shutil, "which", lambda name: None)
    monkeypatch.setattr(mms_pi_support, "_npm_global_prefix", lambda: str(prefix))

    assert mms_pi_support._pi_global_executable() == str(cmd)


def test_pi_global_executable_never_returns_extensionless_shim_on_windows(tmp_path, monkeypatch):
    import mms_pi_support

    prefix, bare, cmd = _npm_layout(tmp_path)
    cmd.unlink()
    monkeypatch.setattr(mms_pi_support.os, "name", "nt")
    monkeypatch.setattr(mms_pi_support.shutil, "which", lambda name: str(bare))
    monkeypatch.setattr(mms_pi_support, "_npm_global_prefix", lambda: str(prefix))

    assert mms_pi_support._pi_global_executable() == ""


def test_pi_global_executable_posix_layout_unchanged(tmp_path, monkeypatch):
    import mms_pi_support

    prefix, bare, _ = _npm_layout(tmp_path)
    bin_dir = prefix / "bin"
    bin_dir.mkdir()
    posix_pi = bin_dir / "pi"
    posix_pi.write_text("#!/bin/sh\n", encoding="utf-8")
    posix_pi.chmod(0o755)
    monkeypatch.setattr(mms_pi_support.os, "name", "posix")
    monkeypatch.setattr(mms_pi_support.shutil, "which", lambda name: None)
    monkeypatch.setattr(mms_pi_support, "_npm_global_prefix", lambda: str(prefix))

    assert mms_pi_support._pi_global_executable() == str(posix_pi)


def _npx_cache_layout(tmp_path, *, with_cmd=True, with_cli_js=False):
    cache = tmp_path / "npm-cache"
    package = cache / "_npx" / "abc123" / "node_modules" / "@earendil-works" / "pi-coding-agent"
    bin_dir = cache / "_npx" / "abc123" / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    package.mkdir(parents=True)
    (package / "package.json").write_text("{}", encoding="utf-8")
    bare = bin_dir / "pi"
    bare.write_text("#!/bin/sh\n", encoding="utf-8")
    bare.chmod(0o755)
    if with_cmd:
        cmd = bin_dir / "pi.cmd"
        cmd.write_text("@echo off\r\n", encoding="utf-8")
        cmd.chmod(0o755)
    if with_cli_js:
        cli = package / "dist" / "cli.js"
        cli.parent.mkdir(parents=True, exist_ok=True)
        cli.write_text("// cli\n", encoding="utf-8")
        cli.chmod(0o755)
    return cache, bin_dir


def test_cached_pi_returns_cmd_sibling_on_windows(tmp_path, monkeypatch):
    from mms_web.drivers import launch_bridge

    cache, bin_dir = _npx_cache_layout(tmp_path)
    monkeypatch.setattr(launch_bridge.os, "name", "nt")
    monkeypatch.setattr(launch_bridge, "_npx_caches", lambda: [cache])

    resolved = launch_bridge.cached_pi()

    assert resolved == str(bin_dir / "pi.cmd")
    assert not resolved.endswith("\\pi") and not resolved.endswith("/pi")


def test_cached_pi_skips_unstartable_entries_on_windows(tmp_path, monkeypatch):
    """cli.js and a lone extensionless shim are both dead ends for Popen."""
    from mms_web.drivers import launch_bridge

    cache, _ = _npx_cache_layout(tmp_path, with_cmd=False, with_cli_js=True)
    monkeypatch.setattr(launch_bridge.os, "name", "nt")
    monkeypatch.setattr(launch_bridge, "_npx_caches", lambda: [cache])

    assert launch_bridge.cached_pi() == ""


def test_cached_pi_posix_keeps_extensionless_shim(tmp_path, monkeypatch):
    from mms_web.drivers import launch_bridge

    cache, bin_dir = _npx_cache_layout(tmp_path, with_cmd=False)
    monkeypatch.setattr(launch_bridge.os, "name", "posix")
    monkeypatch.setattr(launch_bridge, "_npx_caches", lambda: [cache])

    assert launch_bridge.cached_pi() == str(bin_dir / "pi")
