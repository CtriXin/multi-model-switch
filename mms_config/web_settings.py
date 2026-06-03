# -*- coding: utf-8 -*-
"""Settings/report helpers for the MMS config WebUI.

This module intentionally keeps runtime calls lazy so ``mms_config.web`` can
re-export these functions without creating an import cycle.
"""

from __future__ import annotations

import os
from typing import Any


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


def _webui_capability_coverage() -> list[dict[str, str]]:
    return [
        {
            "area": "通道",
            "capability": "provider 新增/编辑/默认/role/priority/Base URL/API Key/protocol/CLI/timezone/note/Claude 1M",
            "webui": "native",
            "tui": "webui_primary_removed_from_settings_top_level",
        },
        {
            "area": "通道",
            "capability": "模型拉取、手动 extra_models、hidden_models、能力标签",
            "webui": "native",
            "tui": "can_degrade_after_route_guard_verified",
        },
        {
            "area": "通道",
            "capability": "本地使用统计 / 最近使用 / 健康覆盖层",
            "webui": "read_only_detail_report",
            "tui": "can_degrade_after_report_smoke",
        },
        {
            "area": "账号",
            "capability": "CLI account 默认值、启用状态、priority、metadata、timezone、note；OAuth 登录主流程下线",
            "webui": "draft_review_human_gate",
            "tui": "keep_emergency_only_for_remove_and_claude_human_gate",
        },
        {
            "area": "设置",
            "capability": "Registry 源状态、preview doctor、Bundle、就绪度和状态",
            "webui": "read_only_reports_plus_existing_apply",
            "tui": "can_degrade_report_display_after_webui_smoke",
        },
        {
            "area": "设置",
            "capability": "Snapshot Guard 接受基线 / 真实配置 drift 确认",
            "webui": "manual_cli_human_gate",
            "tui": "keep_until_webui_double_confirm_flow_exists",
        },
        {
            "area": "设置",
            "capability": "Rescue fallback 配置",
            "webui": "native",
            "tui": "can_degrade_config_display_after_save_flow_verified",
        },
        {
            "area": "设置",
            "capability": "Rescue packet 浏览 / fallback 交接",
            "webui": "read_only_report",
            "tui": "keep_emergency_only_until_handover_write_flow_exists",
        },
        {
            "area": "设置",
            "capability": "界面语言和关于/版本检查",
            "webui": "report_or_planned",
            "tui": "keep_small",
        },
        {
            "area": "主屏入口",
            "capability": "O 接入 / P 通道 / S 设置入口覆盖状态",
            "webui": "module_native_controls_plus_reports",
            "tui": "keep_as_keyboard_launcher_until_webui_launch_surface_exists",
        },
    ]


def _tui_webui_mapping() -> list[dict[str, str]]:
    """Trace every Settings/Channel TUI action to its WebUI destination."""

    def row(
        row_id: str,
        *,
        tui_area: str,
        tui_action_id: str,
        tui_label: str,
        webui_section: str,
        webui_control: str,
        status: str,
        write_policy: str,
        verification: str,
        manual_check: str,
        webui_section_id: str = "",
        api_action: str = "",
    ) -> dict[str, str]:
        click_targets = []
        if webui_section_id:
            click_targets.append("open_section")
        if api_action:
            click_targets.append("settings_report")
        if status in {"native", "draft_review"}:
            click_targets.append("save_preview")
        if status == "human_gate":
            click_targets.append("human_gate_card")
        if status == "missing":
            click_targets.append("missing_gap")
        click_text = " + ".join(dict.fromkeys(click_targets))
        if status == "human_gate":
            acceptance_check = "点人工确认查看风险/写入范围/命令；只复制命令，不在 WebUI 自动执行。"
        elif status == "report":
            acceptance_check = "点报告确认 API 返回 ok/只读 JSON。"
        elif status == "draft_review":
            acceptance_check = "编辑草稿后生成保存预览，确认审查摘要和 diff。"
        elif status == "native":
            acceptance_check = "点打开 WebUI 落点；如修改配置，继续生成保存预览确认。"
        else:
            acceptance_check = "必须补 WebUI 落点或显式 gate，不允许隐藏。"
        return {
            "id": row_id,
            "tui_area": tui_area,
            "tui_action_id": tui_action_id,
            "tui_label": tui_label,
            "webui_section": webui_section,
            "webui_section_id": webui_section_id,
            "webui_control": webui_control,
            "api_action": api_action,
            "status": status,
            "write_policy": write_policy,
            "verification": verification,
            "manual_check": manual_check,
            "clickable": "yes" if webui_section_id or api_action else "no",
            "click_targets": click_text,
            "acceptance_check": acceptance_check,
        }

    rows = [
        row(
            "connect.add_gateway",
            tui_area="Main / O 接入",
            tui_action_id="connect_gateway",
            tui_label="添加网关通道",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="添加通道按钮 + 通道编辑器 + 保存预览",
            api_action="connect_gateway_status",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan provider_added + save review",
            manual_check="WebUI 新增 provider 后仍需保存预览，不直接写真实配置。",
        ),
        row(
            "connect.add_official",
            tui_area="Main / O 接入",
            tui_action_id="connect_official",
            tui_label="添加官方通道 / OAuth 登录",
            webui_section="Settings / 兼容说明",
            webui_section_id="settings",
            webui_control="OAuth/AGY 官方登录已从 WebUI 主流程下线；仅保留只读兼容说明",
            api_action="connect_official_gate",
            status="report",
            write_policy="deprecated_read_only_compat",
            verification="/api/settings/report?action=connect_official_gate",
            manual_check="新配置使用 API Key 通道；旧 OAuth/AGY 账号只做兼容查看，不再作为新增入口。",
        ),
        row(
            "connect.manage_channels",
            tui_area="Main / O 接入",
            tui_action_id="manage_channels",
            tui_label="管理现有通道",
            webui_section="通道配置 + Settings / 账号",
            webui_section_id="channel",
            webui_control="通道编辑器 + 账号表模块动作",
            api_action="tui_mapping",
            status="native",
            write_policy="mixed_draft_review_human_gate",
            verification="/api/settings/report?action=tui_mapping",
            manual_check="网关通道 native；官方账号危险动作 需要人工确认。",
        ),
        row(
            "connect.migrate_config",
            tui_area="Main / O 接入",
            tui_action_id="migrate_config",
            tui_label="迁移配置到 mms",
            webui_section="能力整合",
            webui_section_id="settings",
            webui_control="迁移人工确认报告",
            api_action="migrate_config_gate",
            status="human_gate",
            write_policy="manual_cli_human_gate",
            verification="/api/settings/report?action=migrate_config_gate",
            manual_check="迁移会读写真实配置树，必须人工执行/确认。",
        ),
        row(
            "channel.provider_browse",
            tui_area="Main / P 通道",
            tui_action_id="provider_browse",
            tui_label="浏览 / 选择通道",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="通道列表、使用统计标签、默认值和 priority 字段",
            api_action="provider_usage_summary",
            status="report",
            write_policy="read_only_report",
            verification="/api/settings/report?action=provider_usage_summary",
            manual_check="启动时选择仍属于 launcher；配置侧状态已在 WebUI 可见。",
        ),
        row(
            "channel.provider_switch",
            tui_area="Model / Channel column",
            tui_action_id="←/→ focus + Enter provider override",
            tui_label="模型页切换通道来源",
            webui_section="通道配置 + Runtime",
            webui_section_id="channel",
            webui_control="默认通道、priority 字段、runtime/opencode 模型选择器",
            api_action="provider_channel_status",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan provider_default/priority/runtime diffs",
            manual_check="WebUI 做持久配置；TUI 的单次启动选择仍保留为 launcher 能力。",
        ),
        row(
            "channel.priority_adjust",
            tui_area="Model / Channel column",
            tui_action_id="+/- priority_changes",
            tui_label="调整通道权重",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="通道 priority + family_priority_overrides 字段 + 保存预览",
            api_action="provider_channel_status",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan provider priority/family override diff",
            manual_check="全局 priority 与 family_priority_overrides 都进入 WebUI 草稿和保存预览。",
        ),
        row(
            "channel.family_autosort",
            tui_area="Model / Channel column",
            tui_action_id="A auto rank",
            tui_label="按 speed stats 智能排序",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="通道报告与确认 tab 的自动排序用途说明",
            api_action="family_autosort_gate",
            status="human_gate",
            write_policy="speed_stats_write_human_gate",
            verification="/api/settings/report?action=family_autosort_gate",
            manual_check="自动排序会批量改 priority/family override；WebUI 当前只展示用途和人工确认说明，不静默改顺序。",
        ),
        row(
            "settings.provider_mgmt",
            tui_area="Settings (WebUI-only)",
            tui_action_id="webui_only:provider_mgmt",
            tui_label="Provider 管理（WebUI-only）",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="左侧通道列表、通道配置 tab、模型配置 tab、保存审计",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan diff + /api/save or /api/registry-v2/apply",
            manual_check="TUI 顶层不再提供 provider 快调；检查 provider add/edit/default/model list 是否都能进入保存预览。",
        ),
        row(
            "settings.account_mgmt",
            tui_area="Settings (WebUI/CLI emergency)",
            tui_action_id="webui_only:account_mgmt",
            tui_label="账号管理（WebUI/CLI）",
            webui_section="Settings / 账号",
            webui_section_id="settings",
            webui_control="账号 / OAuth 通道表 + 非 Claude account 草稿",
            api_action="accounts",
            status="draft_review",
            write_policy="draft_review_human_gate",
            verification="/api/settings/report?action=accounts redacts home_dir/proxy",
            manual_check="非 Claude account 可改 name/enabled/priority/default；Claude/login/remove 保持锁定。",
        ),
        row(
            "settings.registry",
            tui_area="Settings (WebUI/CLI emergency)",
            tui_action_id="webui_only:registry",
            tui_label="模型源状态（WebUI/CLI）",
            webui_section="配置源状态",
            webui_section_id="source",
            webui_control="配置源状态 卡片 + 报告按钮 + 保存 / 应用流程",
            api_action="model_source_status",
            status="report",
            write_policy="read_only_report",
            verification="/api/settings/report?action=model_source_status",
            manual_check="写入类 registry 操作必须继续走 save/apply 人工确认。",
        ),
        row(
            "settings.guard",
            tui_area="Settings (WebUI/CLI emergency)",
            tui_action_id="webui_only:guard",
            tui_label="启动快照（WebUI/CLI）",
            webui_section="Settings / Snapshot Guard",
            webui_section_id="settings",
            webui_control="Snapshot 快照状态 / 人工确认报告",
            api_action="guard_accept_gate",
            status="human_gate",
            write_policy="manual_cli_human_gate",
            verification="/api/settings/report?action=guard_accept_gate",
            manual_check="accept 不自动执行；必须 human double-confirm。",
        ),
        row(
            "settings.rescue",
            tui_area="Settings",
            tui_action_id="rescue",
            tui_label="中断/救援",
            webui_section="Fallback",
            webui_section_id="fallback",
            webui_control="rescue fallback / hot fallback 表单 + rescue 事件报告",
            api_action="rescue_events",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="fallback form feeds /api/plan; events use /api/settings/report?action=rescue_events",
            manual_check="fallback 写入前必须生成保存预览；packet handover 仍未自动写。",
        ),
        row(
            "settings.language",
            tui_area="Settings",
            tui_action_id="language",
            tui_label="界面语言",
            webui_section="Settings / 界面语言",
            webui_section_id="settings",
            webui_control="界面语言选择器 + 保存审计",
            api_action="language_status",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/settings/report?action=language_status",
            manual_check="语言变化进入 /api/plan diff；不直接写真实 config。",
        ),
        row(
            "settings.routes_export",
            tui_area="Settings (WebUI/CLI emergency)",
            tui_action_id="webui_only:routes_export",
            tui_label="Legacy 路由导出（WebUI/CLI）",
            webui_section="保存 / 审计",
            webui_section_id="save",
            webui_control="生成保存预览、stable 审计保存、preview DB 发布",
            api_action="routes_export",
            status="native",
            write_policy="save_flow_or_preview_publish",
            verification="/api/plan + /api/save or /api/registry-v2/apply",
            manual_check="直接导出按钮不单独暴露；保存/发布流负责 routes artifacts。",
        ),
        row(
            "settings.about",
            tui_area="Settings",
            tui_action_id="about",
            tui_label="关于",
            webui_section="Settings / 关于",
            webui_section_id="settings",
            webui_control="关于状态",
            api_action="about",
            status="report",
            write_policy="read_only_report",
            verification="/api/settings/report?action=about",
            manual_check="upgrade 动作仍是 manual CLI/人工确认。",
        ),
        row(
            "provider.local_usage",
            tui_area="Channel / Provider",
            tui_action_id="provider:1",
            tui_label="查看本地统计",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="通道列表使用统计标签 + 使用统计报告",
            api_action="provider_usage_summary",
            status="report",
            write_policy="read_only_report",
            verification="/api/settings/report?action=provider_usage_summary",
            manual_check="WebUI report 返回 TUI 同等 CLI/启动次数/最近模型/最近使用明细。",
        ),
        row(
            "provider.models",
            tui_area="Channel / Provider",
            tui_action_id="provider:2",
            tui_label="模型管理",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="模型配置 tab、拉取模型、extra_models、hidden_models、能力开关",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/provider/models + /api/plan",
            manual_check="检查模型拉取、隐藏/补充、capability toggle、stale cleanup。",
        ),
        row(
            "provider.model_patch_reset",
            tui_area="Channel / Provider",
            tui_action_id="provider:2/model:6",
            tui_label="恢复默认模型补丁",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="模型配置 tab 恢复模型补丁按钮",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan extra_models/hidden_models diff",
            manual_check="一键清空当前通道 extra_models + hidden_models，然后保存预览。",
        ),
        row(
            "provider.default",
            tui_area="Channel / Provider",
            tui_action_id="provider:3",
            tui_label="设为默认网关",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="设为默认通道复选框",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan review_summary.default_provider",
            manual_check="默认 provider 变化必须出现在保存摘要。",
        ),
        row(
            "provider.rename",
            tui_area="Channel / Provider",
            tui_action_id="provider:4",
            tui_label="重命名",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="内部 ID + 显示名字段",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan provider rename/remove/add diff",
            manual_check="ID 变化会影响 route scope，必须看 diff。",
        ),
        row(
            "provider.credentials",
            tui_area="Channel / Provider",
            tui_action_id="provider:5",
            tui_label="编辑地址和 Key",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="OpenAI/Anthropic Base URL、models_endpoint、API Key 待保存",
            status="native",
            write_policy="audited_secret_write",
            verification="/api/plan redacts key; save writes audited secret backend",
            manual_check="API Key 只显示 pending，不回显明文。",
        ),
        row(
            "provider.advanced_metadata",
            tui_area="Channel / Provider",
            tui_action_id="provider.edit metadata",
            tui_label="编辑 Claude 1M / timezone / note",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="通道高级 metadata 字段",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan provider_metadata review_summary",
            manual_check="TUI provider.edit 的非 secret 元数据进入 WebUI 草稿和保存预览。",
        ),
        row(
            "provider.network_policy",
            tui_area="Channel / Provider",
            tui_action_id="provider.edit proxy/no_proxy",
            tui_label="编辑 proxy / no_proxy",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="通道配置模块里的通道网络策略人工确认",
            api_action="provider_network_gate",
            status="human_gate",
            write_policy="network_policy_human_gate",
            verification="/api/settings/report?action=provider_network_gate",
            manual_check="proxy/no_proxy 可能包含凭据或影响 Claude network policy；WebUI 不回显明文，只给 gate。",
        ),
        row(
            "provider.remove",
            tui_area="Channel / Provider",
            tui_action_id="provider:6",
            tui_label="删除通道",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="输入通道 ID 确认 + 保存预览摘要",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan review_summary.provider_removed",
            manual_check="删除只改 WebUI 草稿；真正写入仍需保存预览 + confirm。",
        ),
        row(
            "account.local_usage",
            tui_area="Channel / Account",
            tui_action_id="account:1",
            tui_label="查看本地统计",
            webui_section="Settings / 账号",
            webui_section_id="settings",
            webui_control="账号表使用统计列 + 账号摘要报告",
            api_action="accounts",
            status="report",
            write_policy="read_only_report",
            verification="/api/settings/report?action=accounts",
            manual_check="WebUI accounts report 返回 TUI 同等 CLI/启动次数/最近模型/最近使用明细。",
        ),
        row(
            "account.login",
            tui_area="Channel / Account",
            tui_action_id="account:2",
            tui_label="重新登录",
            webui_section="Settings / 账号",
            webui_section_id="settings",
            webui_control="账号表动作按钮里的登录人工确认",
            api_action="account_login_gate",
            status="human_gate",
            write_policy="manual_login_only",
            verification="/api/settings/report?action=account_login_gate",
            manual_check="登录会碰全局/OAuth 状态，WebUI 不自动执行。",
        ),
        row(
            "account.default",
            tui_area="Channel / Account",
            tui_action_id="account:3",
            tui_label="设为默认官方通道",
            webui_section="Settings / 账号",
            webui_section_id="settings",
            webui_control="非 Claude 默认账号单选按钮",
            api_action="accounts",
            status="draft_review",
            write_policy="draft_review_human_gate",
            verification="/api/plan blocks Claude default and accepts non-Claude default",
            manual_check="Claude default radio disabled；非 Claude 进入保存预览。",
        ),
        row(
            "account.rename",
            tui_area="Channel / Account",
            tui_action_id="account:4",
            tui_label="重命名",
            webui_section="Settings / 账号",
            webui_section_id="settings",
            webui_control="账号表动作按钮里的重命名人工确认",
            api_action="account_rename_gate",
            status="human_gate",
            write_policy="account_home_human_gate",
            verification="/api/settings/report?action=account_rename_gate",
            manual_check="账号重命名会改 home_dir/usage/defaults 并可能移动目录；WebUI 不自动执行。",
        ),
        row(
            "account.edit_metadata",
            tui_area="Channel / Account",
            tui_action_id="account:5",
            tui_label="编辑通道",
            webui_section="Settings / 账号",
            webui_section_id="settings",
            webui_control="非 Claude 名称/启用/priority/family/timezone/Claude 1M/note 草稿字段",
            api_action="accounts",
            status="draft_review",
            write_policy="draft_review_human_gate",
            verification="/api/plan blocks protected fields",
            manual_check="非 Claude metadata 进入 WebUI 保存预览；home_dir/proxy/no_proxy/Claude metadata 仍锁定。",
        ),
        row(
            "account.network_policy",
            tui_area="Channel / Account",
            tui_action_id="account.edit proxy/no_proxy",
            tui_label="编辑账号 proxy / no_proxy",
            webui_section="Settings / 账号",
            webui_section_id="settings",
            webui_control="账号表动作按钮里的网络策略人工确认",
            api_action="account_network_gate",
            status="human_gate",
            write_policy="account_network_human_gate",
            verification="/api/settings/report?action=account_network_gate",
            manual_check="账号 proxy/no_proxy/home_dir 可能涉及 OAuth/Claude protected state；WebUI 不回显明文。",
        ),
        row(
            "account.remove",
            tui_area="Channel / Account",
            tui_action_id="account:6",
            tui_label="删除通道",
            webui_section="Settings / 账号",
            webui_section_id="settings",
            webui_control="账号表动作按钮里的删除人工确认",
            api_action="account_remove_gate",
            status="human_gate",
            write_policy="manual_remove_only",
            verification="/api/settings/report?action=account_remove_gate",
            manual_check="删除账号目录/登录状态必须由 human 手动确认。",
        ),
    ]

    registry_rows = [
        ("registry.model_source_status", "model_source_status", "查看模型源状态状态", "model_source_status", "report", "read_only_report"),
        ("registry.consumer_bundle_status", "consumer_bundle_status", "查看消费端 Bundle", "consumer_bundle_status", "report", "read_only_report"),
        ("registry.v2_save_plan", "registry_v2_save_plan", "查看 v2 保存计划", "", "native", "save_preview"),
        ("registry.config_v2_promotion_plan", "config_v2_promotion_plan", "查看晋级计划", "config_v2_promotion_plan", "report", "read_only_report"),
        ("registry.config_v2_release_readiness", "config_v2_release_readiness", "查看 4.0 就绪度", "config_v2_release_readiness", "report", "read_only_report"),
        ("registry.preview_doctor", "preview_doctor", "运行预览诊断", "preview_doctor", "report", "read_only_report"),
        ("registry.check_staleness", "check_staleness", "检查 source 过期状态", "check_staleness", "report", "read_only_report"),
        ("registry.refresh_due_sources", "refresh_due_sources", "刷新到期 source", "refresh_due_sources_gate", "human_gate", "network_write_human_gate"),
        ("registry.scheduled_dry_run", "scheduled_dry_run", "定时刷新 dry run", "scheduled_refresh_gate", "human_gate", "network_human_gate"),
        ("registry.scheduled_no_network", "scheduled_no_network", "定时刷新 no-network", "scheduled_refresh_gate", "human_gate", "manual_cli_human_gate"),
        ("registry.refresh_sources", "refresh_sources", "刷新全部 source", "refresh_sources_gate", "human_gate", "network_write_human_gate"),
        ("registry.fetch_openrouter", "fetch_openrouter", "拉取 OpenRouter catalog", "fetch_openrouter_gate", "human_gate", "network_human_gate"),
        ("registry.diff_openrouter", "diff_openrouter", "对比 OpenRouter candidate", "diff_openrouter_gate", "human_gate", "network_human_gate"),
        ("registry.publish_approved", "publish_approved", "发布已批准 Bundle", "publish_approved_gate", "human_gate", "write_human_gate"),
        ("registry.verify_approved", "verify_approved", "验证已批准 Bundle", "verify_approved", "report", "read_only_report"),
        ("registry.doctor", "doctor", "Registry 诊断 / 状态", "registry_status", "report", "read_only_report"),
    ]
    for row_id, action_id, label, api_action, status, write_policy in registry_rows:
        manual_check = (
            "只读 manifest/hash 验证，可直接在 WebUI 执行；publish 仍 需要人工确认。"
            if action_id == "verify_approved"
            else "只读项可直接点；network/write 类先人工确认，不静默执行。"
        )
        rows.append(
            row(
                row_id,
                tui_area="Settings / Registry",
                tui_action_id=action_id,
                tui_label=label,
                webui_section="保存 / 审计" if action_id == "registry_v2_save_plan" else "配置源状态",
                webui_section_id="save" if action_id == "registry_v2_save_plan" else "source",
                webui_control="保存页生成保存预览" if action_id == "registry_v2_save_plan" else "配置源状态模块动作按钮",
                api_action=api_action,
                status=status,
                write_policy=write_policy,
                verification=f"/api/settings/report?action={api_action}" if api_action else "/api/plan",
                manual_check=manual_check,
            )
        )

    extra_rows = [
        ("guard.status", "Settings / Snapshot Guard", "status", "查看当前 Snapshot 状态", "guard_status", "report", "read_only_report"),
        ("guard.accept", "Settings / Snapshot Guard", "accept", "接受当前 Snapshot", "guard_accept_gate", "human_gate", "manual_cli_human_gate"),
        ("rescue.default", "Settings / Rescue", "choose_route_default/manual_default", "设置全局默认 fallback", "", "native", "draft_review_confirmed_save"),
        ("rescue.clear_default", "Settings / Rescue", "clear_default", "清除全局默认 fallback", "", "native", "draft_review_confirmed_save"),
        ("rescue.hot_fallback", "Settings / Rescue", "enable_hot_fallback/disable_hot_fallback", "开启/关闭 hot fallback", "", "native", "draft_review_confirmed_save"),
        ("rescue.view_packets", "Settings / Rescue", "view_packets", "查看最近失败 / rescue packet", "rescue_events", "report", "read_only_report"),
        ("rescue.create_demo", "Settings / Rescue", "create_demo", "生成测试 rescue packet", "rescue_create_demo_gate", "human_gate", "local_artifact_human_gate"),
        ("rescue.handover", "Settings / Rescue", "handover/manual_handover", "生成 fallback handover", "rescue_handover_gate", "human_gate", "local_artifact_human_gate"),
        ("rescue.view_md_paths", "Settings / Rescue", "view_md/show_paths", "查看 rescue.md / 显示文件路径", "rescue_events", "report", "read_only_report"),
        ("about.refresh", "Settings / 关于", "refresh_versions", "刷新版本检查", "about_refresh_gate", "human_gate", "network_human_gate"),
        ("about.upgrade", "Settings / 关于", "upgrade_mms/upgrade_codex_cli/upgrade_claude_cli", "升级 MMS / CLI", "about_upgrade_gate", "human_gate", "manual_cli_human_gate"),
    ]
    for row_id, area, action_id, label, api_action, status, write_policy in extra_rows:
        is_rescue = area.endswith("Rescue")
        is_guard = "Snapshot Guard" in area
        is_about = area.endswith("About")
        rows.append(
            row(
                row_id,
                tui_area=area,
                tui_action_id=action_id,
                tui_label=label,
                webui_section="Fallback" if is_rescue else "Settings / Snapshot Guard" if is_guard else "Settings / 关于" if is_about else "Settings",
                webui_section_id="fallback" if is_rescue else "settings",
                webui_control="Fallback 表单 / rescue 动作按钮" if is_rescue else "Snapshot Guard 独立卡片" if is_guard else "关于独立卡片",
                api_action=api_action,
                status=status,
                write_policy=write_policy,
                verification=f"/api/settings/report?action={api_action}" if api_action else "/api/plan",
                manual_check="native 走保存预览；gate/missing 不会伪装成已迁移。",
            )
        )
    return rows


def _tui_webui_mapping_summary(rows: list[dict[str, str]] | None = None) -> dict[str, Any]:
    rows = rows if isinstance(rows, list) else _tui_webui_mapping()
    counts = {"native": 0, "report": 0, "draft_review": 0, "human_gate": 0, "missing": 0}
    clickable = 0
    with_report = 0
    with_open = 0
    for item in rows:
        status = _safe_text(item.get("status"))
        if status in counts:
            counts[status] += 1
        if item.get("clickable") == "yes" or item.get("api_action") or item.get("webui_section_id"):
            clickable += 1
        if item.get("api_action"):
            with_report += 1
        if item.get("webui_section_id"):
            with_open += 1
    return {
        "schema": "mms.setup_web.tui_mapping_summary.v1",
        "total": len(rows),
        "counts": counts,
        "clickable_rows": clickable,
        "rows_with_report_or_gate": with_report,
        "rows_with_open_target": with_open,
        "user_check_policy": "每行都可在 WebUI 点击：打开跳到页面落点，报告/人工确认验证 API 或人工确认卡，原生/草稿行再用保存预览核对写入。",
        "source_files": [
            "mms_display/tui.py:_connect_actions",
            "mms_display/tui.py:select_submodel_tui",
            "mms_display/tui.py:_settings_menu",
            "mms_core.py settings/provider/account/rescue action handlers",
        ],
        "policy": "原生/报告行由对应 WebUI 模块承接；TUI Settings 顶层只保留 WebUI、服务器/救援、语言、关于/升级；human_gate/missing 行保留 CLI 人工路径。load_balance 已明确移除。",
    }


def _about_upgrade_gate_commands() -> list[str]:
    try:
        mms_core = _load_mms_core()
        commands = [
            mms_core._mms_upgrade_shell_command(include_clis=False),  # noqa: SLF001 - display only
            mms_core._cli_upgrade_shell_command("codex"),  # noqa: SLF001 - display only
            mms_core._cli_upgrade_shell_command("claude"),  # noqa: SLF001 - display only
        ]
        return [item for item in commands if _safe_text(item)]
    except Exception:
        return [
            "curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --latest-tag",
            "npm install -g @openai/codex@latest",
            "npm install -g @anthropic-ai/claude-code@latest",
        ]


def _settings_gate_catalog(command_name: str = "mms") -> dict[str, dict[str, Any]]:
    command = _safe_text(command_name) or "mms"
    registry = f"{command} registry"
    webui = f"{command} config web"
    interactive = command
    account_writes = [
        "~/.config/mms/config.toml accounts/account.defaults",
        "~/.config/mms/accounts/** OAuth/account state",
        "可能涉及外部浏览器或 CLI login side effects",
    ]
    registry_writes = [
        "<MMS_CONFIG_ROOT>/registry/model-registry.sqlite",
        "<MMS_CONFIG_ROOT>/generated/model-registry.latest-approved.json",
        "<MMS_CONFIG_ROOT>/generated/model-capabilities.approved.json",
    ]
    return {
        "guard_status": {
            "title": "Snapshot 快照状态 / accept",
            "risk_level": "medium",
            "commands": [f"{command} guard status", f"{command} guard accept"],
            "manual_steps": [
                "先运行 status 查看 accepted/latest/pending snapshot 和 drift。",
                "只有确认当前 config drift 是你要保留的状态后，再手动运行 accept。",
                "WebUI 只展示 gate，不会替你接受 baseline。",
            ],
            "writes": ["<MMS_CONFIG_ROOT>/snapshots/startup/latest.json", "<MMS_CONFIG_ROOT>/snapshots/startup/accepted.json", "<MMS_CONFIG_ROOT>/snapshots/startup/pending.json cleanup"],
            "safe_alternative": "只点 guard_status 查看状态；不要运行 accept。",
        },
        "guard_accept_gate": {
            "title": "接受当前 Snapshot baseline",
            "risk_level": "high",
            "commands": [f"{command} guard status", f"{command} guard accept"],
            "manual_steps": [
                "先运行 status，确认 drift 来自你刚刚认可的配置变化。",
                "再运行 accept；这会把当前 snapshot 设为新的已确认 baseline。",
                "如果 drift 涉及 Claude account/proxy/home_dir，按 human-only 规则停下人工确认。",
            ],
            "writes": ["<MMS_CONFIG_ROOT>/snapshots/startup/latest.json", "<MMS_CONFIG_ROOT>/snapshots/startup/accepted.json", "<MMS_CONFIG_ROOT>/snapshots/startup/pending.json cleanup"],
            "safe_alternative": "保留 pending drift，只在 WebUI/CLI 里查看 status。",
        },
        "connect_official_gate": {
            "title": "OAuth / AGY 官方登录已下线",
            "risk_level": "low",
            "commands": [],
            "manual_steps": [
                "不再新增 WebUI OAuth / AGY 官方登录能力。",
                "已有 account 只保留默认值、priority、note 等兼容配置。",
                "新配置走 API Key provider，并通过保存预览写入。",
            ],
            "writes": [],
            "safe_alternative": "网关 API Key 通道使用 WebUI Add provider + 保存预览，不走 OAuth。",
        },
        "migrate_config_gate": {
            "title": "迁移旧配置 / v2 promotion 人工确认",
            "risk_level": "high",
            "commands": [f"{command} migrate config-v2 --json", f"{command} config migrate", f"{command} config root --json"],
            "manual_steps": [
                "先用只读 migration/promotion plan 看 preview root 与 stable root 的差异。",
                "确认 backup、目标 root、secret 处理和 human-only config 边界。",
                "只有人工确认后才运行实际迁移命令。",
            ],
            "writes": ["~/.config/mms/** stable config tree", "<MMS_CONFIG_ROOT>/registry/** preview DB/root artifacts", "config backups / audit logs"],
            "safe_alternative": "在 WebUI 保存页生成 preview plan，不直接迁移 stable。",
        },
        "family_autosort_gate": {
            "title": "按速度统计批量排序 family priority",
            "risk_level": "medium",
            "commands": [webui, interactive],
            "manual_steps": [
                "先在 WebUI 通道页查看/编辑 provider priority 与 family_priority_overrides。",
                "生成保存预览，确认每个 family 的排序变化。",
                "如要使用 TUI speed stats autosort，只能人工打开主 TUI 并逐项确认，不从 WebUI 自动批量改。",
            ],
            "writes": ["provider.priority", "provider.family_priority_overrides", "account.family_priority_overrides"],
            "safe_alternative": "WebUI 已提供手工 family priority 草稿 + diff review，替代自动批量排序。",
        },
        "account_login_gate": {
            "title": "账号登录",
            "risk_level": "high",
            "commands": [f"{command} config account.list", f"{command} config account.login <account-id>", f"{command} config account.status <account-id>"],
            "manual_steps": [
                "确认 account id 不是 Claude human-only account。",
                "手动执行 login，并完成外部 OAuth/CLI 交互。",
                "回到 WebUI 刷新 accounts report，检查默认账号和状态。",
            ],
            "writes": account_writes,
            "safe_alternative": "非 OAuth API Key 通道使用 WebUI provider credentials draft。",
        },
        "account_remove_gate": {
            "title": "删除账号",
            "risk_level": "high",
            "commands": [f"{command} config account.list", f"{command} config account.status <account-id>", f"{command} config account.remove <account-id>"],
            "manual_steps": [
                "确认该 account 没有作为默认账号或专属 key 绑定使用。",
                "Claude account/remove 必须停在 human-only gate。",
                "手动 remove 后回 WebUI accounts report 和保存预览核对。",
            ],
            "writes": ["~/.config/mms/config.toml accounts/account.defaults", "~/.config/mms/accounts/<account-id>/**"],
            "safe_alternative": "先在 WebUI 将非 Claude account disabled/default 草稿调整并 review。",
        },
        "account_rename_gate": {
            "title": "重命名账号 / 移动账号 home",
            "risk_level": "high",
            "commands": [f"{command} config account.list", f"{command} config account.rename <old-account-id> <new-account-id>"],
            "manual_steps": [
                "先确认 old/new account id、默认账号引用和账号 home_dir。",
                "该动作可能移动 account home 目录并重写 usage/defaults；必须人工确认备份和目标目录不存在。",
                "完成后回 WebUI accounts report，核对 id/default/usage 是否一致。",
            ],
            "writes": ["~/.config/mms/config.toml accounts/account.defaults", "~/.config/mms/accounts/<old-id>/** -> <new-id>/**", "~/.config/mms/usage.json account usage keys"],
            "safe_alternative": "WebUI 已支持非 Claude account 显示名、启用状态、priority、family、timezone、note 的草稿/保存预览。",
        },
        "account_network_gate": {
            "title": "编辑账号 proxy / no_proxy / home_dir",
            "risk_level": "high",
            "commands": [f"{command} config account.list", f"{command} config account.edit <account-id>"],
            "manual_steps": [
                "不要在 WebUI 中回显或复制 proxy/no_proxy 明文；这些字段可能包含凭据或影响 OAuth/Claude 网络边界。",
                "Claude account config 是 human-only；任何 Claude proxy/home_dir/no_proxy 变化都必须停止并人工确认。",
                "非 Claude 账号如需改 proxy/no_proxy，请在终端人工运行 account.edit 并随后回 WebUI 做只读核对。",
            ],
            "writes": ["~/.config/mms/config.toml accounts[*].proxy/no_proxy/home_dir/timezone", "~/.config/mms/accounts/** account state can be affected by launch/login"],
            "safe_alternative": "WebUI 只显示 proxy/no_proxy 是否已配置；非敏感 timezone/note 可在账号表中走保存预览。",
        },
        "provider_network_gate": {
            "title": "编辑通道 proxy / no_proxy",
            "risk_level": "high",
            "commands": [f"{command} config provider.edit <provider-id>"],
            "manual_steps": [
                "proxy/no_proxy 可能包含凭据，也可能改变 Claude/provider 的网络隔离策略；WebUI 不回显明文。",
                "修改前先确认目标 provider、expected proxy、no_proxy 不会命中 Claude/OpenAI 域名造成直连泄漏。",
                "人工执行 provider.edit 后回到 WebUI 生成保存预览或 provider_usage_summary 核对非敏感字段。",
            ],
            "writes": ["~/.config/mms/config.toml providers[*].proxy/no_proxy", "provider network policy for future launches"],
            "safe_alternative": "WebUI 支持通道 URL/API Key/protocol/CLI/timezone/note/Claude 1M 的草稿/保存预览；只把 proxy/no_proxy 留给人工确认。",
        },
        "refresh_due_sources_gate": {
            "title": "刷新到期 registry source",
            "risk_level": "medium",
            "commands": [f"{registry} check-staleness", f"{registry} refresh-sources --if-due"],
            "manual_steps": [
                "先运行 check-staleness，只读确认哪些 source 到期。",
                "确认可写 preview registry root 后，再运行 --if-due refresh。",
                "刷新后运行 source-status/preview-doctor 核对。",
            ],
            "writes": registry_writes[:1],
            "safe_alternative": "WebUI 点击过期检查报告只读查看。",
        },
        "scheduled_refresh_gate": {
            "title": "定时 registry 刷新",
            "risk_level": "medium",
            "commands": [f"{registry} scheduled-refresh --dry-run --no-network", f"{registry} scheduled-refresh --no-network", f"{registry} scheduled-refresh"],
            "manual_steps": [
                "先 dry-run/no-network，确认 due state 和不会访问外网。",
                "需要联网 OpenRouter refresh 时，由人工明确运行不带 --no-network 的命令。",
                "执行后查看 scheduled output、source-status 和 preview doctor。",
            ],
            "writes": registry_writes,
            "safe_alternative": "保留 WebUI 只读报告；不要执行联网/写入刷新。",
        },
        "refresh_sources_gate": {
            "title": "刷新全部 registry source",
            "risk_level": "high",
            "commands": [f"{registry} refresh-sources", f"{registry} source-status --json"],
            "manual_steps": [
                "确认当前 root 是预期 preview/stable root。",
                "运行 refresh-sources 前先确认 reference snapshots 和写入范围。",
                "完成后用 source-status/preview-doctor 验证。",
            ],
            "writes": registry_writes[:1],
            "safe_alternative": "只运行 check-staleness 或 source-status。",
        },
        "fetch_openrouter_gate": {
            "title": "拉取 OpenRouter catalog",
            "risk_level": "medium",
            "commands": [f"{registry} fetch-openrouter-catalog", f"{registry} fetch-openrouter-catalog --from-file <models.json>"],
            "manual_steps": [
                "联网拉取前确认网络可用和 OpenRouter source 仍可信。",
                "如已有离线 catalog，优先使用 --from-file。",
                "完成后再运行 diff-openrouter-catalog 查看候选变化。",
            ],
            "writes": registry_writes[:1],
            "safe_alternative": "用 --from-file 导入人工下载的 catalog，避免 WebUI 自动联网。",
        },
        "diff_openrouter_gate": {
            "title": "对比 OpenRouter candidate 变化",
            "risk_level": "medium",
            "commands": [f"{registry} diff-openrouter-catalog --limit 50", f"{registry} diff-openrouter-catalog --no-store --limit 50"],
            "manual_steps": [
                "先用 --no-store 只读查看 diff。",
                "确认 candidate changes 合理后，再允许 store candidate_change rows。",
                "后续 publish 前必须走 approved bundle 验证。",
            ],
            "writes": ["<MMS_CONFIG_ROOT>/registry/model-registry.sqlite candidate_change rows"],
            "safe_alternative": "只运行 --no-store diff。",
        },
        "publish_approved_gate": {
            "title": "发布已批准 Bundle",
            "risk_level": "high",
            "commands": [f"{registry} publish-approved", f"{registry} verify --json"],
            "manual_steps": [
                "先确认 candidate/bundle revision 和 route shrink guard。",
                "人工运行 publish-approved 后立刻运行 verify。",
                "verify 未通过时不要继续把结果交给 launcher/runtime。",
            ],
            "writes": registry_writes[1:],
            "safe_alternative": "WebUI 保存页 preview apply 会在明确 confirm 后 publish/verify preview bundle。",
        },
        "verify_approved_gate": {
            "title": "验证已批准 Bundle",
            "risk_level": "low",
            "commands": [f"{registry} verify --json", f"{registry} consumer-bundle --json --no-strict-exit"],
            "manual_steps": [
                "运行 verify 检查 latest-approved manifest/hash。",
                "再运行 consumer-bundle 查看下游可读状态。",
                "此 gate 保留 CLI/manual path，WebUI 不替你执行外部命令。",
            ],
            "writes": [],
            "safe_alternative": "WebUI 点击消费端 Bundle 报告读取当前状态。",
        },
        "rescue_create_demo_gate": {
            "title": "生成 demo rescue packet",
            "risk_level": "medium",
            "commands": [interactive, webui],
            "manual_steps": [
                "打开主 TUI：Settings -> Rescue -> 生成测试 rescue packet。",
                "确认写入 repo-local .mms/rescue demo artifacts。",
                "完成后在 WebUI 点击 rescue_events 查看 artifact path。",
            ],
            "writes": ["<repo>/.mms/rescue/**", "~/.config/mms/rescue/index.jsonl metadata"],
            "safe_alternative": "WebUI 只读 rescue_events；不生成 demo artifact。",
        },
        "rescue_handover_gate": {
            "title": "生成 fallback 交接",
            "risk_level": "medium",
            "commands": [interactive, webui],
            "manual_steps": [
                "先在 WebUI rescue_events 找到要处理的 rescue packet。",
                "打开主 TUI：Settings -> Rescue -> 选择 packet -> handover/manual_handover。",
                "确认 fallback model 和 artifact path 后再生成。",
            ],
            "writes": ["<repo>/.mms/rescue/latest-fallback-handover.json", "<repo>/.mms/rescue/latest-fallback-handover.md"],
            "safe_alternative": "WebUI 已支持 fallback/hot fallback 持久配置草稿，handover artifact 仍人工生成。",
        },
        "about_refresh_gate": {
            "title": "刷新版本检查",
            "risk_level": "medium",
            "commands": [interactive, webui],
            "manual_steps": [
                "打开主 TUI：Settings -> About -> 刷新版本检查。",
                "该动作可能访问 GitHub/npm 并更新本地 version cache。",
                "WebUI about report 默认只读 cached 状态，不自动联网刷新。",
            ],
            "writes": ["~/.config/mms/version.json update cache"],
            "safe_alternative": "WebUI 点击关于状态读取缓存版本状态。",
        },
        "about_upgrade_gate": {
            "title": "升级 MMS / Codex / Claude CLI",
            "risk_level": "critical",
            "commands": _about_upgrade_gate_commands(),
            "manual_steps": [
                "先看当前版本和 latest 版本，确认升级目标。",
                "手动复制并运行对应升级命令；这会联网并修改本机安装。",
                "升级后重新打开 WebUI，运行 summary/py_compile/smoke 确认入口可用。",
            ],
            "writes": ["MMS install location", "global npm packages for Codex/Claude CLI"],
            "safe_alternative": "只查看 about cached status，不执行升级。",
        },
        "provider_remove_gate": {
            "title": "删除通道 legacy 人工确认",
            "risk_level": "medium",
            "commands": [webui, f"{command} config provider.remove <provider-id>"],
            "manual_steps": [
                "WebUI 当前已提供 typed confirm 草稿删除；优先使用 WebUI 保存预览。",
                "CLI remove 属于 legacy mutating path，执行前先确认 provider 不再被默认/route/fallback 使用。",
            ],
            "writes": ["~/.config/mms/config.toml providers/provider.default", "credentials/model-policy related entries"],
            "safe_alternative": "WebUI typed confirm -> 生成保存预览 -> confirm save。",
        },
    }


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
