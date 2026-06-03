# -*- coding: utf-8 -*-
"""Settings report dispatchers for the MMS config WebUI."""

from __future__ import annotations

import os
from typing import Any

from mms_config.web_settings_catalog import (
    _settings_gate_report,
    _tui_webui_mapping,
    _tui_webui_mapping_summary,
)


def _backend():
    from mms_config import web

    return web


def _safe_text(value: Any) -> str:
    return _backend()._safe_text(value)


def _load_mms_core():
    return _backend()._load_mms_core()


def _sanitize_for_output(value: Any) -> Any:
    return _backend()._sanitize_for_output(value)


def _config_root_for_snapshot(config_path: str = "") -> str:
    return _backend()._config_root_for_snapshot(config_path)


def build_config_snapshot(
    cfg: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    return _backend().build_config_snapshot(
        cfg,
        config_path=config_path,
        preferences_path=preferences_path,
        command_name=command_name,
    )


def _snapshot_guard_status_report(cfg: dict[str, Any], *, config_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    mapping_rows = [item for item in _tui_webui_mapping() if item.get("api_action") == "guard_status"]
    try:
        mms_core = _load_mms_core()
        target_config_path = config_path or mms_core._config_write_target_path()  # noqa: SLF001 - read-only status
        current_snapshot = mms_core._build_config_guard_snapshot(cfg if isinstance(cfg, dict) else {}, config_path=target_config_path)  # noqa: SLF001
        latest_path = mms_core._config_snapshot_path("startup", "latest.json", config_path=target_config_path)  # noqa: SLF001
        accepted_path = mms_core._config_snapshot_path("startup", "accepted.json", config_path=target_config_path)  # noqa: SLF001
        pending_path = mms_core._config_snapshot_path("startup", "pending.json", config_path=target_config_path)  # noqa: SLF001
        accepted_payload = mms_core._load_json_snapshot(accepted_path) or {}  # noqa: SLF001
        accepted_snapshot = accepted_payload.get("snapshot") if isinstance(accepted_payload, dict) else None
        diff_lines = mms_core._snapshot_diff_lines(accepted_snapshot, current_snapshot) if accepted_snapshot else []  # noqa: SLF001
        status_value = "missing" if not accepted_snapshot else ("drift" if diff_lines else "stable")
        report = {
            "status": status_value,
            "accepted_path": accepted_path,
            "latest_path": latest_path,
            "pending_path": pending_path if os.path.exists(pending_path) else "",
            "real_home": _safe_text(current_snapshot.get("real_home")),
            "config_path": _safe_text(current_snapshot.get("config_path")),
            "accounts": len(current_snapshot.get("accounts") or []),
            "providers": len(current_snapshot.get("providers") or []),
            "diff_count": len(diff_lines),
            "diff_preview": diff_lines[:20],
        }
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": "guard_status",
            "status": "report",
            "write_policy": "read_only_report",
            "commands": [f"{_safe_text(command_name) or 'mms'} guard status"],
            "report": _sanitize_for_output(report),
            "mapping": mapping_rows,
            "note": "只读 Snapshot 快照状态；accept baseline 仍在 guard_accept_gate 人工确认。",
        }
    except Exception as exc:
        return {
            "ok": False,
            "schema": "mms.setup_web.settings_report.v1",
            "action": "guard_status",
            "status": "report",
            "write_policy": "read_only_report",
            "error": f"{type(exc).__name__}: {exc}",
            "mapping": mapping_rows,
            "note": "读取 Snapshot 快照状态 失败；未执行 accept 或任何写入。",
        }


def build_settings_report(
    cfg: dict[str, Any],
    payload: dict[str, Any] | None = None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    """Return one bounded settings report for the WebUI; mutating TUI actions stay 需要人工确认."""
    payload = payload if isinstance(payload, dict) else {}
    action = _safe_text(payload.get("action") or "coverage")
    snapshot = build_config_snapshot(cfg, config_path=config_path, preferences_path=preferences_path, command_name=command_name)
    mapping = snapshot.get("tui_webui_mapping") or []
    if action in {"tui_mapping", "tui_webui_mapping"}:
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "mixed",
            "summary": snapshot.get("tui_webui_mapping_summary") or _tui_webui_mapping_summary(mapping),
            "mapping": mapping,
        }
    if action in {"coverage", "capability_coverage"}:
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "read_only",
            "coverage": snapshot.get("webui_capability_coverage") or [],
            "settings_actions": snapshot.get("settings_actions") or [],
            "tui_webui_mapping_summary": snapshot.get("tui_webui_mapping_summary") or {},
        }
    if action in {"accounts", "account_status"}:
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "draft_review_human_gate",
            "accounts": snapshot.get("accounts") or [],
            "account_defaults": snapshot.get("account_defaults") or {},
            "account_write_policy": snapshot.get("account_write_policy") or {},
            "note": "WebUI 支持已有非 Claude account 的 name/enabled/priority/family/timezone/Claude 1M/note/default 草稿预览；OAuth / AGY 新登录主流程已下线，remove/rename/home_dir/proxy 与 Claude account 仍 需要人工确认。",
        }
    if action in {"model_source_status", "source"}:
        return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "report": snapshot.get("model_source_status") or {}}
    if action in {"consumer_bundle_status", "bundle"}:
        return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "report": snapshot.get("consumer_bundle_status") or {}}
    if action in {"config_v2_promotion_plan", "promotion_plan"}:
        return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "report": snapshot.get("config_v2_promotion_plan") or {}}
    if action in {"config_v2_release_readiness", "release_readiness"}:
        return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "report": snapshot.get("config_v2_release_readiness") or {}}
    if action == "registry_v2_save_plan":
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "save_preview",
            "note": "WebUI 的 v2 Save Plan 由“保存 / 审计”页的“生成保存预览”生成；不在 settings report 里构造假 plan。",
            "webui_section": "save",
        }
    if action == "check_staleness":
        try:
            from mms_registry.cli import source_freshness

            report = source_freshness()
            return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "write_policy": "read_only", "report": _sanitize_for_output(report)}
        except Exception as exc:
            return {"ok": False, "schema": "mms.setup_web.settings_report.v1", "action": action, "error": f"{type(exc).__name__}: {exc}"}
    if action == "preview_doctor":
        config_root = _config_root_for_snapshot(config_path)
        try:
            from mms_registry.cli import preview_doctor

            report = preview_doctor(config_dir=config_root or None, command_name=f"{command_name} config doctor")
            return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "report": _sanitize_for_output(report)}
        except Exception as exc:
            return {"ok": False, "schema": "mms.setup_web.settings_report.v1", "action": action, "error": f"{type(exc).__name__}: {exc}"}
    if action == "registry_status":
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "read_only",
            "report": snapshot.get("model_source_status") or {},
            "note": "registry_status CLI can initialize SQLite; WebUI uses model_source_status instead to stay read-only.",
        }
    if action == "verify_approved":
        config_root = _config_root_for_snapshot(config_path)
        try:
            from mms_registry.cli import verify_approved_bundle

            report = verify_approved_bundle(config_dir=config_root or None)
            return {
                "ok": True,
                "schema": "mms.setup_web.settings_report.v1",
                "action": action,
                "write_policy": "read_only_report",
                "status": "report",
                "report": _sanitize_for_output(report),
                "note": "只读验证 latest-approved manifest/hash；不会 publish、写入 bundle 或修改真实 config。",
            }
        except Exception as exc:
            return {
                "ok": False,
                "schema": "mms.setup_web.settings_report.v1",
                "action": action,
                "write_policy": "read_only_report",
                "status": "report",
                "error": f"{type(exc).__name__}: {exc}",
                "note": "只读验证 latest-approved manifest/hash 失败；WebUI 没有执行 publish/write。",
            }
    if action == "provider_usage_summary":
        requested_provider_id = _safe_text(payload.get("provider_id"))
        provider_items = [item for item in (snapshot.get("providers") or []) if isinstance(item, dict)]
        if requested_provider_id:
            provider_items = [item for item in provider_items if _safe_text(item.get("id")) == requested_provider_id]
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "read_only",
            "provider_id": requested_provider_id,
            "scope": "provider" if requested_provider_id else "all_providers",
            "providers": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "usage": item.get("usage") or {},
                    "model_count": item.get("model_count"),
                    "enabled": item.get("enabled"),
                    "role": item.get("role"),
                    "priority": item.get("priority"),
                    "models": [
                        {
                            "id": row.get("id"),
                            "source": row.get("source"),
                            "visible": row.get("visible", True),
                            "favorite": row.get("favorite", False),
                        }
                        for row in (item.get("models") or [])
                        if isinstance(row, dict) and row.get("id")
                    ],
                    "usage_rows": item.get("usage_rows") or [],
                }
                for item in provider_items
            ],
        }
    if action == "connect_gateway_status":
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "draft_review_confirmed_save",
            "status": "native",
            "webui_section": "channel",
            "provider_count": len(snapshot.get("providers") or []),
            "note": "TUI O 接入 -> 添加网关通道 已迁到 WebUI 的 Add provider / provider editor；保存前必须生成 diff preview。",
        }
    if action == "provider_channel_status":
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "draft_review_confirmed_save",
            "status": "native",
            "provider_default": snapshot.get("provider_default"),
            "providers": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "enabled": item.get("enabled"),
                    "role": item.get("role"),
                    "priority": item.get("priority"),
                    "family_priority_overrides": item.get("family_priority_overrides") or {},
                    "model_count": item.get("model_count"),
                }
                for item in (snapshot.get("providers") or [])
                if isinstance(item, dict)
            ],
            "note": "WebUI 暴露持久 provider default/priority/role；TUI 单次启动 provider override 仍属于 launcher 选择面。",
        }
    if action == "guard_status":
        return _snapshot_guard_status_report(snapshot, config_path=config_path, command_name=command_name)
    if action == "language_status":
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "draft_review_confirmed_save",
            "status": "native",
            "ui_language": _safe_text((cfg.get("ui") if isinstance(cfg.get("ui"), dict) else {}).get("language") or "zh"),
            "note": "WebUI Settings 页可暂存 ui.language，真正写入仍要经过保存预览与 confirm。",
        }
    if action == "routes_export":
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "save_flow_or_preview_publish",
            "status": "native",
            "webui_section": "save",
            "note": "Legacy model-routes.json 不再单独做 settings 按钮；WebUI 保存/preview publish 会产出对应 routes artifacts。",
            "writes": (snapshot.get("save_contract") or {}).get("preview_v2_writes") or [],
        }
    if action == "about":
        try:
            mms_core = _load_mms_core()
            report = mms_core._about_status_snapshot(force_update=False)  # noqa: SLF001 - read-only cached about status
            return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "report": _sanitize_for_output(report)}
        except Exception as exc:
            return {"ok": False, "schema": "mms.setup_web.settings_report.v1", "action": action, "error": f"{type(exc).__name__}: {exc}"}
    if action == "rescue_events":
        try:
            from mms_runtime.rescue import list_rescue_events

            events = list_rescue_events(repo_root=os.getcwd(), limit=20)
            return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "write_policy": "read_only", "events": _sanitize_for_output(events)}
        except Exception as exc:
            return {"ok": False, "schema": "mms.setup_web.settings_report.v1", "action": action, "error": f"{type(exc).__name__}: {exc}"}
    if action == "connect_official_gate":
        mapping_rows = [item for item in mapping if item.get("api_action") == action]
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "title": "OAuth / AGY 官方登录已下线",
            "status": "deprecated",
            "risk_level": "low",
            "write_policy": "deprecated_read_only_compat",
            "blocked_auto_execute": True,
            "requires_human_confirmation": False,
            "copyable": False,
            "commands": [],
            "manual_steps": [
                "WebUI 不再提供新的 OAuth / AGY 官方登录入口。",
                "新通道请在「通道配置」里维护 Base URL、API Key、protocol 和模型清单。",
                "已存在的 account 只保留默认值、priority、note 等兼容配置；login/remove/Claude account 仍按人工边界处理。",
            ],
            "writes": [],
            "safe_alternative": "使用 API Key provider：通道配置 -> 新增通道 -> 生成保存预览 -> 写入。",
            "note": "OAuth/AGY 官方登录已从 WebUI 主流程下线；这里只解释兼容边界，不提供登录命令。",
            "mapping": mapping_rows,
        }
    gate_actions = {
        "guard_accept_gate": ("manual_cli_human_gate", "Snapshot Guard accept 会更新 guard baseline；WebUI 不自动执行。"),
        "provider_remove_gate": ("planned_human_confirm", "删除 provider 需要 typed confirm + diff review；本 slice 只标出缺口。"),
        "provider_network_gate": ("network_policy_human_gate", "proxy/no_proxy 可能包含凭据并影响网络隔离；WebUI 不回显或自动写入。"),
        "migrate_config_gate": ("manual_cli_human_gate", "配置迁移会读写真实配置树；必须人工确认迁移源、目标和备份。"),
        "family_autosort_gate": ("speed_stats_write_human_gate", "用于按测速 / 使用统计重排 priority 与 family_priority_overrides；会批量影响路由优先级，所以 WebUI 只显示人工确认说明。"),
        "account_login_gate": ("manual_login_only", "OAuth login 会写外部账号状态；WebUI 当前不触发。"),
        "account_remove_gate": ("manual_remove_only", "删除 account 可能删除账号目录/登录状态；WebUI 当前不触发。"),
        "account_rename_gate": ("account_home_human_gate", "账号重命名可能移动 home_dir 并改 usage/defaults；WebUI 当前不自动执行。"),
        "account_network_gate": ("account_network_human_gate", "账号 proxy/no_proxy/home_dir 可能涉及 OAuth/Claude protected state；WebUI 不回显或自动写入。"),
        "refresh_due_sources_gate": ("network_write_human_gate", "刷新 registry source 可能触发 network/write；当前保持 人工确认。"),
        "scheduled_refresh_gate": ("network_human_gate", "scheduled refresh 需要单独确认执行模式；当前保持 人工确认。"),
        "refresh_sources_gate": ("network_write_human_gate", "刷新全部 sources 是 network/write 动作；当前保持 人工确认。"),
        "fetch_openrouter_gate": ("network_human_gate", "Fetch OpenRouter Catalog 需要联网；当前保持 人工确认。"),
        "diff_openrouter_gate": ("network_human_gate", "OpenRouter diff 可能依赖外部 catalog；当前保持 人工确认。"),
        "publish_approved_gate": ("write_human_gate", "发布 approved bundle 是写入动作；WebUI 只允许通过保存/发布审计流执行。"),
        "rescue_create_demo_gate": ("local_artifact_human_gate", "生成 demo rescue packet 会写本地 artifact；当前不自动执行。"),
        "rescue_handover_gate": ("planned_human_confirm", "fallback handover 写 artifact；后续需要 WebUI confirm flow。"),
        "about_refresh_gate": ("network_human_gate", "刷新版本检查可能联网；当前不自动执行。"),
        "about_upgrade_gate": ("manual_cli_human_gate", "升级 MMS/Codex/Claude CLI 是外部写入/安装动作；必须 human 手动执行。"),
    }
    if action in gate_actions:
        write_policy, note = gate_actions[action]
        return _settings_gate_report(action, write_policy=write_policy, note=note, command_name=command_name)
    return {
        "ok": False,
        "schema": "mms.setup_web.settings_report.v1",
        "action": action,
        "error": "unknown settings report action",
        "available_actions": [
            "tui_mapping",
            "coverage",
            "accounts",
            "model_source_status",
            "consumer_bundle_status",
            "registry_v2_save_plan",
            "config_v2_promotion_plan",
            "config_v2_release_readiness",
            "preview_doctor",
            "check_staleness",
            "registry_status",
            "verify_approved",
            "provider_usage_summary",
            "connect_gateway_status",
            "connect_official_gate",
            "provider_channel_status",
            "guard_status",
            "language_status",
            "routes_export",
            "about",
            "rescue_events",
            *sorted(gate_actions.keys()),
        ],
    }
