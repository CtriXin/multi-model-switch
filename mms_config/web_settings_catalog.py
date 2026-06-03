# -*- coding: utf-8 -*-
"""Static Settings catalogs and human-gate reports for the MMS config WebUI."""

from __future__ import annotations

from typing import Any

from mms_config.web_settings_gates import _settings_gate_catalog
from mms_config.web_settings_mapping import (
    _tui_webui_mapping,
    _tui_webui_mapping_summary,
    _webui_capability_coverage,
)


def _backend():
    from mms_config import web

    return web


def _safe_text(value: Any) -> str:
    return _backend()._safe_text(value)


def _load_mms_core():
    return _backend()._load_mms_core()


def _settings_action_cards() -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    try:
        from mms_display.settings_actions import list_tui_settings_actions

        for descriptor in list_tui_settings_actions():
            item = descriptor.as_dict()
            item["webui_status"] = {
                "refresh-sources": "report_only",
                "probe-selected": "native_test_panel",
                "registry-doctor": "report_only",
                "recoverable-models": "planned",
                "interrupted-sessions": "report_only",
                "export-approved-bundle": "existing_save_flow",
                "legacy-tools-emergency-debug": "manual_cli_only",
                "usage-health-overlay": "report_only",
            }.get(str(item.get("action_id") or ""), "planned")
            actions.append(item)
    except Exception:
        actions = []
    return actions


def _settings_gate_report(action: str, *, write_policy: str = "human_gate", note: str = "", command_name: str = "mms") -> dict[str, Any]:
    mapping_rows = [item for item in _tui_webui_mapping() if item.get("api_action") == action]
    gate = _settings_gate_catalog(command_name).get(action, {})
    commands = [item for item in (gate.get("commands") or []) if _safe_text(item)]
    return {
        "ok": True,
        "schema": "mms.setup_web.settings_report.v1",
        "action": action,
        "title": gate.get("title") or action,
        "write_policy": write_policy,
        "status": "human_gate",
        "risk_level": gate.get("risk_level") or "high",
        "requires_human_confirmation": True,
        "blocked_auto_execute": True,
        "copyable": bool(commands),
        "commands": commands,
        "manual_steps": gate.get("manual_steps") or [],
        "writes": gate.get("writes") or [],
        "safe_alternative": gate.get("safe_alternative") or "",
        "note": note or "该 TUI 动作会触发 network/write/OAuth/global-config 风险；WebUI 当前只显示 gate，不会自动执行。",
        "mapping": mapping_rows,
    }
