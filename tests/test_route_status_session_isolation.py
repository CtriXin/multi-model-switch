"""Regression tests for route_status.json per-session isolation.

Covers the committee blocker on issue #86: route_status path must come from
the current launch's explicit gateway_home, not from ambient MMS_SESSION_HOME.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


def _paths(gateway_home=None):
    import mms_launchers

    return mms_launchers._claude_route_status_paths(gateway_home=gateway_home)


def test_ignores_ambient_session_home_env(monkeypatch):
    """显式 gateway_home 必须压过 ambient MMS_SESSION_HOME env。"""
    monkeypatch.setenv("MMS_SESSION_HOME", "/tmp/ambient-session-home-PID-777")
    monkeypatch.setenv("MMS_CONFIG_ROOT", "/tmp/ambient-config-root")

    result = _paths(gateway_home="/tmp/explicit-gateway-home/1111")

    assert len(result) == 1
    assert result[0] == "/tmp/explicit-gateway-home/1111/.config/mms/route_status.json"
    # ambient env 绝不能渗进来
    assert "ambient-session-home" not in result[0]
    assert "ambient-config-root" not in result[0]


def test_multi_session_isolation():
    """两个不同 gateway_home 必须算出两个不同 route_status 路径。"""
    pid_a = "/tmp/gateway-home/s/7180"
    pid_b = "/tmp/gateway-home/s/98400"

    paths_a = _paths(gateway_home=pid_a)
    paths_b = _paths(gateway_home=pid_b)

    assert paths_a != paths_b
    assert paths_a[0].endswith("/s/7180/.config/mms/route_status.json")
    assert paths_b[0].endswith("/s/98400/.config/mms/route_status.json")


def test_fallback_without_gateway_home_uses_config_root(monkeypatch):
    """不传 gateway_home 时，退回到 MMS_CONFIG_ROOT 全局路径（非 gateway 场景）。"""
    monkeypatch.setenv("MMS_CONFIG_ROOT", "/tmp/fallback-config-root")
    monkeypatch.delenv("MMS_SESSION_HOME", raising=False)

    with patch("mms_launchers._resolve_mms_config_dir", return_value="/tmp/fallback-config-root"):
        result = _paths(gateway_home=None)

    assert result[0] == "/tmp/fallback-config-root/route_status.json"
