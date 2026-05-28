"""Small command handlers that are not part of the launcher runtime path."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys


CONFIG_HELP_TOPICS = {
    "-h",
    "--help",
    "help",
    "preferences",
    "preferences.help",
    "preference.help",
    "preferences.path",
    "preference.path",
    "preferences.example",
    "preference.example",
    "preferences.doc",
    "preference.doc",
    "web",
    "webui",
    "setup.web",
    "setup-web",
    "gates",
    "human-gate",
    "humangate",
    "human-gates",
}


def trace_source_for(field, value, trace_overrides):
    expected = str(value or "").strip()
    if not expected:
        return "(not set)"
    fallback_source = ""
    generic_match = ""
    prefer_explicit = field in {"cli", "provider", "account", "model"}
    for source, kv in reversed(trace_overrides or []):
        if field not in kv:
            continue
        candidate = str(kv.get(field) or "").strip()
        if candidate == expected:
            if prefer_explicit and source == "runtime resolve":
                generic_match = source
                continue
            return source
        if not fallback_source:
            fallback_source = source
    return fallback_source or generic_match or "runtime result"


def format_launch_trace(
    cli_name,
    model_info,
    runtime,
    trace_overrides,
    *,
    runtime_provider_id,
    runtime_account_id,
    runtime_bridge,
):
    model = ""
    if isinstance(model_info, dict):
        model = model_info.get("model", "")
    elif isinstance(model_info, str):
        model = model_info

    provider_id = runtime_provider_id(runtime)
    account_id = runtime_account_id(runtime)
    auth_mode = runtime.get("auth_mode", "") if isinstance(runtime, dict) else ""
    bridge = runtime_bridge(runtime)

    lines = [
        "",
        "[MMS Trace]",
        f"  cli:      {cli_name or '-'} <- {trace_source_for('cli', cli_name, trace_overrides)}",
        f"  provider: {provider_id or '-'} <- {trace_source_for('provider', provider_id, trace_overrides)}",
        f"  account:  {account_id or '-'} <- {trace_source_for('account', account_id, trace_overrides)}",
        f"  model:    {model or '-'} <- {trace_source_for('model', model, trace_overrides)}",
        f"  bridge:   {bridge or '-'} <- {trace_source_for('bridge', bridge, trace_overrides)}",
        f"  runtime:  {auth_mode or '-'} <- {trace_source_for('runtime', auth_mode, trace_overrides)}",
        "",
        "Override chain:",
    ]
    if trace_overrides:
        for source, kv in trace_overrides:
            if kv:
                parts = ", ".join(f"{k}={v}" for k, v in kv.items())
                lines.append(f"  {source:<16s}-> {parts}")
            else:
                lines.append(f"  {source:<16s}-> (none)")
    else:
        lines.append("  (no overrides recorded)")
    lines.append("")
    return "\n".join(lines)


def compact_tui_report_value(value, max_len=96):
    text = str(value if value is not None else "-").replace("\n", " ").strip()
    if len(text) <= max_len:
        return text or "-"
    return text[: max(1, max_len - 1)].rstrip() + "…"


def settings_result_tui_payload(title, rows, note="", *, ok=True, localize):
    prefix = "✓ " if ok else "✗ "
    info_lines = [(localize("状态", "Status"), localize("成功", "OK") if ok else localize("失败", "Failed"))]
    info_lines.extend(
        (str(label or "-"), compact_tui_report_value(value, max_len=120))
        for label, value in list(rows or [])
    )
    if note:
        info_lines.append((localize("说明", "Note"), compact_tui_report_value(note, max_len=160)))
    return (
        f"{prefix}{title}",
        info_lines,
        [("back", localize("返回", "Back"))],
    )


def display_settings_result_report(title, rows, note="", *, ok=True, console):
    color = "green" if ok else "red"
    prefix = "✓ " if ok else "✗ "
    console.print(f"[{color}]{prefix}{title}[/{color}]")
    for label, value in rows:
        console.print(f"[cyan]{label}[/cyan] {compact_tui_report_value(value)}")
    if note:
        console.print(f"[dim]{note}[/dim]")


def model_validation_findings(provider, probe, *, provider_label):
    findings = []
    error_kind = probe.get("error_kind")
    provider_name = provider_label(provider)
    if error_kind == "protocol_unsupported":
        findings.append({
            "severity": "high",
            "title": "当前 provider 不支持模型探测",
            "summary": f"{provider_name} 没有声明 openai_chat_completions，无法访问 /v1/models。",
        })
    elif error_kind in {"missing_credentials", "missing_base_url", "missing_api_key"}:
        findings.append({
            "severity": "high",
            "title": "当前 provider 凭据不完整",
            "summary": f"{provider_name} 还缺少地址或 Key，无法验证可用模型。",
        })
    elif error_kind == "empty_models":
        findings.append({
            "severity": "medium",
            "title": "接口连通，但没有拿到模型列表",
            "summary": f"{provider_name} 返回了空列表，可能是账号权限或网关映射问题。",
        })
    elif error_kind == "missing_httpx":
        findings.append({
            "severity": "high",
            "title": "本地缺少依赖",
            "summary": "当前环境缺少 httpx，暂时无法做模型探测。",
        })
    else:
        findings.append({
            "severity": "high",
            "title": "模型校验失败",
            "summary": probe.get("error") or f"{provider_name} 暂时无法拉取模型列表。",
        })
    if provider.get("id"):
        findings.append({
            "severity": "low",
            "title": "可以跳过校验继续",
            "summary": "预设和直接 CLI 启动仍然可以继续使用，但模型浏览会受限。",
        })
    return findings


def rank_recovery_actions(actions):
    return sorted(
        actions,
        key=lambda item: (
            item.get("priority", 999),
            0 if item.get("recommended") else 1,
            item.get("title", ""),
        ),
    )


def build_model_recovery_actions(cfg, provider, probe, *, provider_map):
    providers = provider_map(cfg)
    active_provider_id = provider.get("id")
    actions = [
        {
            "id": "edit_credentials",
            "title": "重新输入地址和 Key",
            "summary": "修复当前 provider 的地址或认证信息。",
            "priority": 10,
            "recommended": probe.get("error_kind") != "protocol_unsupported",
        },
        {
            "id": "show_details",
            "title": "查看详细错误",
            "summary": "展开本次校验的 provider、协议和错误明细。",
            "priority": 20,
            "recommended": False,
        },
        {
            "id": "continue_without_validation",
            "title": "跳过校验并继续",
            "summary": "继续使用预设或直接 CLI 启动，但不会有模型浏览列表。",
            "priority": 30,
            "recommended": False,
        },
    ]
    if len(providers) > 1:
        actions.insert(
            1,
            {
                "id": "switch_provider",
                "title": "切换到其他 provider",
                "summary": f"当前可切到其他已配置 provider，避免卡在 {active_provider_id}。",
                "priority": 12,
                "recommended": probe.get("error_kind") == "protocol_unsupported",
            },
        )
    return rank_recovery_actions(actions)


def display_model_probe_details(probe, *, panel_cls, console):
    lines = [f"- {line}" for line in probe.get("details", [])]
    console.print(panel_cls("\n".join(lines), title="校验详情", border_style="yellow"))


def rescue_default_fallback_report_payload(model, *, cleared=False, hot_fallback_enabled=False, localize):
    if cleared:
        return (
            localize("全局 fallback 已清除", "Global fallback cleared"),
            [
                (localize("保存位置", "saved at"), "[rescue].fallback_model"),
                (localize("安全边界", "safety"), "routed providers only; no global OAuth"),
            ],
            "",
        )
    return (
        localize("全局 fallback 已设置", "Global fallback set"),
        [
            ("Model", model or "-"),
            ("Hot fallback", localize("开启", "on") if hot_fallback_enabled else localize("关闭", "off")),
            (localize("保存位置", "saved at"), "[rescue].fallback_model"),
            (localize("生效方式", "applies"), "bridge failure -> model-routes.json"),
            (localize("安全边界", "safety"), "no global OAuth"),
        ],
        (
            localize("真实 failure 会先写 rescue packet，再尝试该 routed model。", "Real failures write a rescue packet before trying this routed model.")
            if hot_fallback_enabled
            else localize("默认只记录 rescue / fallback handoff；开启 hot fallback 后才会自动模型调用。", "By default MMS records rescue / fallback handoff only; automatic model calls require hot fallback to be enabled.")
        ),
    )


def rescue_hot_fallback_toggle_report_payload(enabled, *, has_default=True, localize):
    if enabled and not has_default:
        return (
            localize("无法开启 hot fallback", "Cannot enable hot fallback"),
            [
                (localize("原因", "reason"), localize("请先设置全局 fallback model", "Set a global fallback model first")),
                (localize("安全边界", "safety"), "no global OAuth"),
            ],
            "",
        )
    return (
        localize("hot fallback 已开启", "hot fallback enabled") if enabled else localize("hot fallback 已关闭", "hot fallback disabled"),
        [
            ("Hot fallback", localize("开启", "on") if enabled else localize("关闭", "off")),
            (localize("前置条件", "requires"), "[rescue].fallback_model"),
            (localize("默认行为", "default"), localize("关闭时只记录 rescue / handoff", "off means rescue / handoff only")),
        ],
        localize("开关保存到 [rescue].hot_fallback_enabled。", "Switch is saved to [rescue].hot_fallback_enabled."),
    )


def rescue_demo_packet_report_payload(payload, *, localize):
    payload = payload if isinstance(payload, dict) else {}
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    return (
        localize("测试 rescue packet 已生成", "Demo rescue packet created"),
        [
            ("rescue.md", artifacts.get("markdown") or "-"),
            ("rescue.json", artifacts.get("json") or "-"),
        ],
        "",
    )


def rescue_paths_report_payload(selected_rescue, *, localize):
    selected_rescue = selected_rescue if isinstance(selected_rescue, dict) else {}
    return (
        localize("Rescue 文件路径", "Rescue file paths"),
        [
            ("rescue.md", selected_rescue.get("artifact_markdown") or "-"),
            ("rescue.json", selected_rescue.get("artifact_json") or "-"),
        ],
        "",
    )


def rescue_handover_report_payload(handover, fallback_model, *, localize):
    handover = handover if isinstance(handover, dict) else {}
    artifacts = handover.get("artifacts") if isinstance(handover.get("artifacts"), dict) else {}
    return (
        localize("fallback handover 已生成", "fallback handover created"),
        [
            ("Model", fallback_model or "-"),
            ("handover.md", artifacts.get("markdown") or "-"),
            ("latest", artifacts.get("latest_markdown") or "-"),
        ],
        localize("handover 只写本地 rescue artifact；不切换当前 session。", "handover writes local rescue artifacts only; it does not switch the current session."),
    )


def registry_source_staleness_report_payload(summary, *, localize):
    summary = summary if isinstance(summary, dict) else {}
    rows = [
        ("DB", summary.get("db_path") or "-"),
        (localize("到期 Source", "sources due"), f"{summary.get('due_count')} / {summary.get('source_count')}"),
    ]
    for idx, item in enumerate((summary.get("sources") or [])[:5], start=1):
        due = localize("到期", "due") if item.get("due") else localize("未到期", "not due")
        rows.append(
            (
                f"Source {idx}",
                f"{due} · {item.get('reason') or '-'} · {item.get('checked_at') or '-'} · {item.get('source_path') or '-'}",
            )
        )
    hidden = max(0, len(summary.get("sources") or []) - 5)
    if hidden:
        rows.append((localize("更多 Source", "more sources"), hidden))
    return localize("模型真源 Source Staleness", "Registry Source Staleness"), rows, ""


def registry_refresh_sources_report_payload(summary, *, localize):
    summary = summary if isinstance(summary, dict) else {}
    return (
        localize("刷新 Sources 完成", "Refresh Sources Complete"),
        [
            ("DB", summary.get("db_path") or "-"),
            (localize("导入", "imported"), summary.get("imported_count")),
            (localize("跳过", "skipped"), summary.get("skipped_count", 0)),
            (localize("模型", "models"), summary.get("model_count")),
            (localize("事实", "facts"), summary.get("fact_count")),
        ],
        localize("只写 source truth / candidate evidence；不改变当前 runtime defaults。", "Writes source truth / candidate evidence only; runtime defaults unchanged."),
    )


def registry_scheduled_refresh_report_payload(summary, *, localize):
    summary = summary if isinstance(summary, dict) else {}
    source_refresh = summary.get("source_refresh") if isinstance(summary.get("source_refresh"), dict) else {}
    openrouter_fetch = summary.get("openrouter_fetch") if isinstance(summary.get("openrouter_fetch"), dict) else {}
    return (
        localize("定时刷新结果", "Scheduled Refresh Result"),
        [
            ("DB", summary.get("db_path") or "-"),
            ("Dry Run", summary.get("dry_run")),
            (localize("到期 Source", "source due"), summary.get("source_due_count")),
            (localize("导入 Source", "source imported"), source_refresh.get("imported_count", 0)),
            (localize("OpenRouter 到期", "OpenRouter due"), summary.get("openrouter_due")),
            ("OpenRouter", openrouter_fetch.get("reason") or localize("No Network 模式未拉取", "not fetched in no-network mode")),
        ],
        localize("安全 schedule wrapper：不接入 startup，不发布 latest-approved。", "Safe schedule wrapper: no startup hook and no latest-approved publish."),
    )


def registry_openrouter_fetch_report_payload(summary, *, localize):
    summary = summary if isinstance(summary, dict) else {}
    return (
        localize("OpenRouter Catalog 拉取完成", "OpenRouter Catalog Fetch Complete"),
        [
            ("DB", summary.get("db_path") or "-"),
            ("Snapshot", summary.get("snapshot_id") or "-"),
            (localize("模型", "models"), summary.get("model_count")),
        ],
        localize("只写 provider_catalog source snapshot；不改变当前 runtime defaults。", "Writes provider_catalog source snapshot only; runtime defaults unchanged."),
    )


def registry_openrouter_diff_report_payload(summary, *, localize):
    summary = summary if isinstance(summary, dict) else {}
    rows = [
        (localize("变化", "changes"), f"{summary.get('change_count')} stored={summary.get('stored_count')}"),
        (localize("缺少 reference", "missing reference"), summary.get("missing_reference_count")),
        (localize("未追踪 catalog", "untracked catalog"), summary.get("untracked_catalog_count")),
    ]
    for idx, item in enumerate((summary.get("changes") or [])[:5], start=1):
        rows.append(
            (
                f"Change {idx}",
                f"{item.get('field_key') or '-'} · {item.get('model_key') or '-'} -> {item.get('provider_model_id') or '-'}",
            )
        )
    hidden = max(0, len(summary.get("changes") or []) - 5)
    if hidden:
        rows.append((localize("更多变化", "more changes"), hidden))
    return (
        localize("OpenRouter Candidate Diff", "OpenRouter Candidate Diff"),
        rows,
        localize("只写 candidate_change evidence；不改变当前 runtime defaults。", "Writes candidate_change evidence only; runtime defaults unchanged."),
    )


def registry_publish_approved_report_payload(summary, *, localize):
    summary = summary if isinstance(summary, dict) else {}
    return (
        localize("发布 Approved Bundle 完成", "Publish Approved Bundle Complete"),
        [
            ("Manifest", summary.get("manifest_path") or "-"),
            ("Bundle", summary.get("bundle_revision") or "-"),
        ],
        localize("发布 generated/latest-approved bundle；不改 root aliases，不改 runtime defaults。", "Publishes generated/latest-approved bundle; root aliases and runtime defaults unchanged."),
    )


def registry_verify_approved_report_payload(summary, *, localize):
    summary = summary if isinstance(summary, dict) else {}
    manifest = summary.get("manifest") if isinstance(summary.get("manifest"), dict) else {}
    files = summary.get("verified_files") if isinstance(summary.get("verified_files"), dict) else {}
    return (
        localize("Latest-approved hash 验证完成", "Latest-approved hash verified"),
        [
            ("Manifest", summary.get("manifest_path") or "-"),
            ("Bundle", manifest.get("bundle_revision") or "-"),
            (localize("文件", "files"), len(files)),
        ],
        "",
    )


def registry_doctor_report_payload(status, *, localize):
    status = status if isinstance(status, dict) else {}
    counts = status.get("counts") if isinstance(status.get("counts"), dict) else {}
    rows = [
        ("DB", status.get("db_path") or "-"),
        ("user_version", status.get("user_version") or "-"),
    ]
    for key in sorted(counts):
        rows.append((key, counts[key]))
    return localize("Registry Doctor / 状态", "Registry Doctor / Status"), rows, ""


def short_update_status_label(status, *, localize):
    status = str(status or "").strip()
    if not status:
        return ""
    if status.startswith(localize("有新版", "update available")):
        return localize("有新版", "update available")
    if status.startswith(localize("高于 latest", "newer than latest")):
        return localize("高于 latest", "newer than latest")
    return status


def format_cli_about_line(cli_status, *, localize):
    current = str(cli_status.get("version") or cli_status.get("label") or "").strip()
    status = short_update_status_label(cli_status.get("status"), localize=localize)
    status_suffix = f" · {status}" if status else ""
    return f"{current}{status_suffix}".strip() or "-"


def format_about_latest_value(status, *, localize):
    latest = str((status or {}).get("latest") or "").strip()
    return latest or localize("未检查", "not checked")


def about_check_error_summary(error_text, *, localize):
    raw = str(error_text or "").strip()
    if not raw:
        return ""
    lower = raw.lower()
    if "ssl" in lower or "handshake" in lower:
        return localize("MMS latest 检查失败：SSL handshake，可稍后重试", "MMS latest check failed: SSL handshake; retry later")
    if "timed out" in lower or "timeout" in lower:
        return localize("MMS latest 检查超时，可稍后重试", "MMS latest check timed out; retry later")
    if len(raw) > 72:
        raw = raw[:69].rstrip() + "..."
    return raw


def about_tui_payload(about_snapshot, *, config_path, localize):
    about_snapshot = about_snapshot if isinstance(about_snapshot, dict) else {}
    version_info = about_snapshot.get("version_info") if isinstance(about_snapshot.get("version_info"), dict) else {}
    mms_status = about_snapshot.get("mms") if isinstance(about_snapshot.get("mms"), dict) else {}
    clis = about_snapshot.get("clis") if isinstance(about_snapshot.get("clis"), dict) else {}
    codex_status = clis.get("codex") if isinstance(clis.get("codex"), dict) else {}
    claude_status = clis.get("claude") if isinstance(clis.get("claude"), dict) else {}
    info_lines = [
        ("MMS", f"{mms_status.get('current') or version_info.get('release') or 'dev'} · {mms_status.get('status') or '-'}"),
        (localize("MMS 最新", "MMS latest"), mms_status.get("latest") or localize("未检查", "not checked")),
        ("Codex", format_cli_about_line(codex_status, localize=localize)),
        (localize("Codex 最新", "Codex latest"), format_about_latest_value(codex_status, localize=localize)),
        ("Claude", format_cli_about_line(claude_status, localize=localize)),
        (localize("Claude 最新", "Claude latest"), format_about_latest_value(claude_status, localize=localize)),
        ("Git", f"{version_info.get('git_branch') or '-'} @ {version_info.get('git_commit') or '-'}"),
        (localize("安装", "Install"), f"{version_info.get('install_channel') or '-'} / {version_info.get('source') or '-'}"),
        ("Config", config_path),
    ]
    if mms_status.get("last_error"):
        info_lines.append((localize("检查错误", "Check error"), about_check_error_summary(mms_status.get("last_error"), localize=localize)))
    actions = [("refresh_versions", localize("刷新版本检查", "Refresh Version Check"))]
    if mms_status.get("outdated"):
        actions.append(("upgrade_mms", localize("升级 MMS", "Upgrade MMS")))
    if codex_status.get("outdated"):
        actions.append(("upgrade_codex_cli", localize("升级 Codex CLI", "Upgrade Codex CLI")))
    if claude_status.get("outdated"):
        actions.append(("upgrade_claude_cli", localize("升级 Claude CLI", "Upgrade Claude CLI")))
    actions.append(("back", localize("返回", "Back")))
    return localize("关于 / About", "About"), info_lines, actions


def snapshot_guard_tui_payload(*, command_name, localize):
    info_lines = [
        (localize("用途", "Purpose"), localize("检查/接受 MMS config drift", "Inspect / accept MMS config drift")),
        ("CLI", f"{command_name} guard status / accept"),
    ]
    actions = [
        ("status", localize("查看当前 Snapshot 状态", "Status")),
        ("accept", localize("接受当前 Snapshot", "Accept Current Snapshot")),
        ("back", localize("返回", "Back")),
    ]
    return localize("启动快照 / Snapshot Guard", "Snapshot Guard"), info_lines, actions


def display_about_version_summary(about_snapshot, *, payload_builder, console):
    title, info_lines, _actions = payload_builder(about_snapshot)
    console.print(f"[cyan]{title}[/cyan]")
    for label, value in info_lines:
        console.print(f"[cyan]{label}[/cyan] {value}")


def mask_key(value):
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


def set_nested(target, parts, value):
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            target[part] = {}
        target = target[part]
    target[parts[-1]] = value


def get_nested(target, parts):
    current = target
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None, False
        current = current[part]
    return current, True


def unset_nested(target, parts):
    current = target
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    if not isinstance(current, dict) or parts[-1] not in current:
        return False
    current.pop(parts[-1], None)
    return True


def coerce_config_value(key_path, raw_value, *, validate_user_role, normalize_language, normalize_positive_seconds):
    if key_path == "user.role":
        return validate_user_role(raw_value)
    if key_path == "ui.language":
        lang = normalize_language(raw_value)
        if not lang:
            raise ValueError("ui.language 只支持 zh 或 en")
        return lang
    if key_path == "provider.default":
        return str(raw_value).strip()
    if key_path in {"cache.probe_async_refresh_after_sec", "cache.probe_async_min_interval_sec"}:
        return normalize_positive_seconds(raw_value, 1)
    if key_path.startswith("provider.") and key_path.endswith(".enabled"):
        return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}
    return raw_value


def validate_config(
    cfg,
    *,
    default_provider_protocols,
    cli_names,
    legacy_provider_cli_aliases,
    default_priority,
    oauth_capable_clis,
    mode_all,
    mode_recommended,
    canonical_model_family,
    normalize_priority,
    normalize_claude_1m_mode,
    normalize_user_role,
):
    errors = []

    def _validate_family_priority_overrides(value, label):
        if value is None:
            return
        if not isinstance(value, dict):
            errors.append(f"{label} 的 family_priority_overrides 必须是对象")
            return
        for family_name, priority in value.items():
            canonical_family = canonical_model_family(family_name)
            if not canonical_family:
                errors.append(f"{label} 的 family_priority_overrides 存在不支持的 family: {family_name}")
                continue
            if normalize_priority(priority) != priority:
                errors.append(f"{label} 的 family_priority_overrides.{canonical_family} 必须是正整数")

    cache_cfg = cfg.get("cache", {})
    if cache_cfg and not isinstance(cache_cfg, dict):
        errors.append("cache 必须是对象")
    elif isinstance(cache_cfg, dict):
        for key in ("probe_async_refresh_after_sec", "probe_async_min_interval_sec"):
            value = cache_cfg.get(key)
            if value is None:
                continue
            try:
                if int(value) <= 0:
                    errors.append(f"{key} 必须是正整数")
            except (TypeError, ValueError):
                errors.append(f"{key} 必须是正整数")
    providers = cfg.get("providers", [])
    if not isinstance(providers, list) or not providers:
        errors.append("providers 不能为空")
    else:
        seen_ids = set()
        for item in providers:
            if not isinstance(item, dict):
                errors.append("providers 中存在非对象条目")
                continue
            provider_id = str(item.get("id", "")).strip()
            if not provider_id:
                errors.append("存在缺少 id 的模型源")
                continue
            if provider_id in seen_ids:
                errors.append(f"模型源 ID 重复: {provider_id}")
            seen_ids.add(provider_id)

            protocols = item.get("protocols", [])
            if isinstance(protocols, str):
                protocols = [protocols]
            invalid_protocols = [value for value in protocols if value not in default_provider_protocols]
            if invalid_protocols:
                errors.append(f"模型源 {provider_id} 存在不支持的协议: {', '.join(invalid_protocols)}")

            supported_clis = item.get("supported_clis", [])
            if isinstance(supported_clis, str):
                supported_clis = [supported_clis]
            invalid_clis = [
                value for value in supported_clis
                if value not in cli_names and value not in legacy_provider_cli_aliases
            ]
            if invalid_clis:
                errors.append(f"模型源 {provider_id} 存在不支持的 CLI: {', '.join(invalid_clis)}")
            if normalize_priority(item.get("priority", default_priority)) != item.get("priority", default_priority):
                errors.append(f"模型源 {provider_id} 的 priority 必须是正整数")
            _validate_family_priority_overrides(
                item.get("family_priority_overrides"),
                f"模型源 {provider_id}",
            )
            if normalize_claude_1m_mode(item.get("claude_1m_mode", "auto")) != item.get("claude_1m_mode", "auto"):
                errors.append(f"模型源 {provider_id} 的 claude_1m_mode 必须是 auto/enable/disable")
    default_id = cfg.get("provider", {}).get("default")
    provider_ids = {item.get("id") for item in providers if isinstance(item, dict)}
    if default_id and default_id not in provider_ids:
        errors.append(f"默认模型源不存在: {default_id}")

    accounts = cfg.get("accounts", [])
    seen_account_ids = set()
    if not isinstance(accounts, list):
        errors.append("accounts 必须是列表")
    else:
        for item in accounts:
            if not isinstance(item, dict):
                errors.append("accounts 中存在非对象条目")
                continue
            account_id = str(item.get("id", "")).strip()
            if not account_id:
                errors.append("存在缺少 id 的账号档案")
                continue
            if account_id in seen_account_ids:
                errors.append(f"账号档案 ID 重复: {account_id}")
            seen_account_ids.add(account_id)
            cli_name = str(item.get("cli", "")).strip()
            if cli_name not in oauth_capable_clis:
                errors.append(f"账号档案 {account_id} 绑定了不支持的 CLI: {cli_name}")
            auth_mode = str(item.get("auth_mode", "oauth")).strip()
            if auth_mode != "oauth":
                errors.append(f"账号档案 {account_id} 目前只支持 oauth 模式")
            if not str(item.get("home_dir", "")).strip():
                errors.append(f"账号档案 {account_id} 缺少 home_dir")
            if normalize_priority(item.get("priority", default_priority)) != item.get("priority", default_priority):
                errors.append(f"账号档案 {account_id} 的 priority 必须是正整数")
            _validate_family_priority_overrides(
                item.get("family_priority_overrides"),
                f"账号档案 {account_id}",
            )
            if normalize_claude_1m_mode(item.get("claude_1m_mode", "auto")) != item.get("claude_1m_mode", "auto"):
                errors.append(f"账号档案 {account_id} 的 claude_1m_mode 必须是 auto/enable/disable")
    account_defaults = cfg.get("account", {}).get("defaults", {})
    if isinstance(account_defaults, dict):
        for cli_name, account_id in account_defaults.items():
            if cli_name not in oauth_capable_clis:
                errors.append(f"存在不支持的默认账号 CLI: {cli_name}")
            elif account_id not in seen_account_ids:
                errors.append(f"{cli_name} 的默认账号不存在: {account_id}")

    role = cfg.get("user", {}).get("role", mode_all)
    if normalize_user_role(role) not in {mode_all, mode_recommended}:
        errors.append(f"不支持的模型模式: {role}")

    return errors


def handle_config_get(cfg, args_rest, *, command_name, console):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config get <dot.path>[/red]")
        return
    key_path = args_rest[0]
    value, found = get_nested(cfg, key_path.split("."))
    if not found:
        console.print(f"[red]配置项 '{key_path}' 不存在[/red]")
        return
    display = mask_key(str(value)) if "key" in key_path.lower() else str(value)
    console.print(f"[cyan]{key_path}[/cyan] = {display}")


def handle_config_set(
    cfg,
    args_rest,
    *,
    command_name,
    coerce_config_value,
    normalize_config_sections,
    save_config,
    console,
):
    if len(args_rest) < 2:
        console.print(f"[red]用法: {command_name} config set <dot.path> <value>[/red]")
        return
    key_path = args_rest[0]
    raw_value = args_rest[1]
    new_value = coerce_config_value(key_path, raw_value)
    updated_cfg = dict(cfg)
    set_nested(updated_cfg, key_path.split("."), new_value)
    updated_cfg = normalize_config_sections(updated_cfg)
    save_config(updated_cfg)
    display = mask_key(str(new_value)) if "key" in key_path.lower() else str(new_value)
    console.print(f"[green]✓ {key_path} = {display}[/green]")


def handle_config_unset(
    cfg,
    args_rest,
    *,
    command_name,
    normalize_config_sections,
    save_config,
    console,
):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config unset <dot.path>[/red]")
        return
    key_path = args_rest[0]
    updated_cfg = dict(cfg)
    removed = unset_nested(updated_cfg, key_path.split("."))
    if not removed:
        console.print(f"[red]配置项 '{key_path}' 不存在[/red]")
        return
    updated_cfg = normalize_config_sections(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ 已移除 {key_path}[/green]")


def handle_config_validate(cfg, *, validate_config, console):
    errors = validate_config(cfg)
    if errors:
        console.print("[red]配置校验失败:[/red]")
        for item in errors:
            console.print(f"  - {item}")
        sys.exit(1)
    console.print("[green]✓ 配置校验通过[/green]")


def session_status_label(item):
    session_id = str(item.get("session_id") or "").strip()
    if not session_id:
        return "active"
    if item.get("stale_cleanup"):
        return "stale-finalized"
    if item.get("exit_code") is None:
        return "active"
    return f"exit:{item.get('exit_code')}"


def session_display_id(item):
    session_id = str(item.get("session_id") or "").strip()
    if session_id:
        return session_id
    pid = item.get("pid")
    return f"pid-{pid}" if pid is not None else "-"


def handle_session_ls(cli_name, *, list_indexed_sessions, table_cls, console):
    rows = list_indexed_sessions(cli_name=cli_name)
    if not rows:
        console.print(f"[yellow]当前没有已索引的 {cli_name} session[/yellow]")
        return

    table = table_cls(title=f"{cli_name} session 列表", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("项目", style="green")
    table.add_column("来源", style="magenta")
    table.add_column("状态", style="yellow")
    table.add_column("最近活动", style="blue")
    for item in rows:
        project_name = os.path.basename(str(item.get("project_path", "")).rstrip(os.sep)) or "-"
        source_label = str(item.get("account_id") or item.get("runtime_kind") or "-")
        last_active = str(item.get("last_active_at") or item.get("started_at") or "-")
        table.add_row(
            session_display_id(item),
            project_name,
            source_label,
            session_status_label(item),
            last_active,
        )
    console.print(table)


def handle_session_info(session_id, cli_name, *, get_indexed_session, table_cls, console):
    item = get_indexed_session(session_id, cli_name=cli_name)
    if item is None:
        console.print(f"[red]找不到 session: {session_id}[/red]")
        sys.exit(1)

    table = table_cls(title=f"{cli_name} session 详情")
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")
    ordered_keys = [
        "session_id",
        "project_key",
        "project_path",
        "account_id",
        "runtime_kind",
        "pid",
        "cwd",
        "started_at",
        "last_active_at",
        "exit_code",
        "stale_cleanup",
        "slot_home",
        "_path",
    ]
    seen = set()
    for key in ordered_keys:
        seen.add(key)
        table.add_row(key, str(item.get(key, "")))
    for key in sorted(item):
        if key in seen:
            continue
        table.add_row(str(key), str(item.get(key, "")))
    console.print(table)


def handle_session_prune(
    cli_name,
    *,
    apply=False,
    yes=False,
    list_stale_gateway_sessions,
    finalize_claude_slot,
    remove_tree,
    format_bytes,
    table_cls,
    console,
):
    rows = list_stale_gateway_sessions(cli_name)
    if not rows:
        console.print("[green]没有可清理的 stale MMS session[/green]")
        return

    table = table_cls(title="Stale MMS session dry-run" if not apply else "Stale MMS session prune")
    table.add_column("CLI", style="cyan")
    table.add_column("Session", style="green")
    table.add_column("Size", style="yellow")
    table.add_column("Modified", style="blue")
    table.add_column("Path", style="white")
    for item in rows:
        table.add_row(
            str(item["cli"]),
            str(item["name"]),
            format_bytes(item["size"]),
            str(item["mtime"]),
            str(item["path"]),
        )
    console.print(table)

    if not apply:
        console.print(f"[dim]dry-run only：加 --apply --yes 才会删除 {len(rows)} 个 stale session[/dim]")
        return
    if not yes:
        console.print("[red]拒绝删除：需要显式传 --yes[/red]")
        return

    removed = 0
    for item in rows:
        session_home = str(item.get("path") or "")
        root = os.path.dirname(session_home)
        try:
            if os.path.commonpath([os.path.abspath(session_home), os.path.abspath(root)]) != os.path.abspath(root):
                continue
        except ValueError:
            continue
        if item.get("cli") == "claude":
            try:
                finalize_claude_slot(session_home, stale_cleanup=True)
            except Exception:
                pass
        remove_tree(session_home, ignore_errors=True)
        removed += 1
    console.print(f"[green]已删除 {removed} 个 stale MMS session[/green]")


def is_config_help_request(args_rest):
    if not args_rest:
        return False
    key_path = str(args_rest[0] or "").strip()
    return key_path in CONFIG_HELP_TOPICS


def is_help_request(argv):
    if not argv:
        return False
    if argv[0] == "help":
        return True
    if argv[0] == "config" and is_config_help_request(argv[1:]):
        return True
    return any(str(arg).strip() in {"-h", "--help"} for arg in argv)


def is_setup_web_request(argv):
    if not argv:
        return False
    command = str(argv[0] or "").strip()
    if command in {"setup", "setup-web", "web-setup"}:
        return True
    if command != "config" or len(argv) < 2:
        return False
    return str(argv[1] or "").strip() in {"web", "webui", "setup.web", "setup-web"}


def is_session_prune_dry_run(argv):
    if len(argv) < 2:
        return False
    if argv[0] != "session" or argv[1] != "prune":
        return False
    return "--apply" not in argv


def handle_fake_upstream_command(
    argv,
    *,
    command_name,
    set_enabled,
    status_payload,
    tail_log,
    table_cls,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} fake-upstream",
        description="开发期 fake upstream：不访问真实上游，并把请求写入日志",
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser("status", help="查看 fake upstream 状态")
    subparsers.add_parser("on", help="开启 fake upstream")
    subparsers.add_parser("off", help="关闭 fake upstream")
    log_parser = subparsers.add_parser("log", help="查看 fake upstream 日志")
    log_parser.add_argument("--tail", type=int, default=20, help="最后 N 条")

    args = parser.parse_args(argv)

    if args.subcommand == "on":
        set_enabled(True)
        payload = status_payload()
        console.print("[green]✓ fake upstream 已开启[/green]")
        console.print(f"[dim]state: {payload['state_path']}[/dim]")
        console.print(f"[dim]log:   {payload['log_path']}[/dim]")
        return
    if args.subcommand == "off":
        set_enabled(False)
        payload = status_payload()
        console.print("[green]✓ fake upstream 已关闭[/green]")
        console.print(f"[dim]state: {payload['state_path']}[/dim]")
        return
    if args.subcommand == "log":
        rows = tail_log(args.tail)
        if not rows:
            console.print("[yellow]暂无 fake upstream 日志[/yellow]")
            return
        table = table_cls(title="Fake Upstream Log")
        table.add_column("Time", style="cyan")
        table.add_column("Kind", style="green")
        table.add_column("Target", style="magenta")
        table.add_column("Detail", style="white")
        for row in rows:
            target = str(row.get("url") or row.get("host") or "-")
            if str(row.get("kind") or "") == "upstream":
                detail = row.get("request_body_preview") or row.get("path") or "-"
            else:
                detail = (
                    row.get("path")
                    or row.get("request_body_preview")
                    or row.get("body")
                    or row.get("proxy")
                    or row.get("listen")
                    or "-"
                )
            table.add_row(str(row.get("ts") or "-"), str(row.get("kind") or "-"), target, str(detail))
        console.print(table)
        return

    payload = status_payload()
    table = table_cls(title="Fake Upstream")
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")
    table.add_row("enabled", "yes" if payload.get("enabled") else "no")
    table.add_row("state_path", str(payload.get("state_path") or "-"))
    table.add_row("log_path", str(payload.get("log_path") or "-"))
    table.add_row("proxy_url", str(payload.get("proxy_url") or "-"))
    table.add_row("ca_cert_path", str(payload.get("ca_cert_path") or "-"))
    table.add_row("proxy_pid", str(payload.get("proxy_pid") or "-"))
    table.add_row("proxy_started_at", str(payload.get("proxy_started_at") or "-"))
    table.add_row("updated_at", str(payload.get("updated_at") or "-"))
    console.print(table)


def handle_logs_command(
    argv,
    *,
    command_name,
    fake_upstream_status_payload,
    config_root,
    table_cls,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} logs",
        description="显示 MMS 常用日志路径与可直接复制的查看命令",
    )
    parser.add_argument("--tail", type=int, default=20, help="默认 tail 行数")
    args = parser.parse_args(argv)

    fake_payload = fake_upstream_status_payload()
    fake_log_path = str(fake_payload.get("log_path") or "-")
    fake_status_cmd = f"{command_name} fake-upstream status"
    fake_log_cmd = f"{command_name} fake-upstream log --tail {args.tail}"
    raw_tail_cmd = f"tail -n {args.tail} {shlex.quote(fake_log_path)}" if fake_log_path not in {"", "-"} else "-"
    guard_status_cmd = f"{command_name} guard status"

    table = table_cls(title="MMS Logs")
    table.add_column("项", style="cyan", no_wrap=True)
    table.add_column("值", style="green")
    table.add_row("config_root", config_root)
    table.add_row("fake_upstream", "on" if fake_payload.get("enabled") else "off")
    table.add_row("fake_log_path", fake_log_path)
    table.add_row("cmd.status", fake_status_cmd)
    table.add_row("cmd.fake_log", fake_log_cmd)
    table.add_row("cmd.raw_tail", raw_tail_cmd)
    table.add_row("cmd.guard", guard_status_cmd)
    console.print(table)


def handle_exposure_command(
    argv,
    *,
    command_name,
    cli_names,
    load_command_config,
    ensure_provider_credentials,
    ensure_models_ready,
    choose_runtime_source,
    inspect_runtime_exposure,
    table_cls,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} exposure",
        description="审计当前 runtime 会向 CLI 暴露哪些 env / settings / HOME 信息",
    )
    parser.add_argument("cli", nargs="?", default="claude", choices=cli_names, help="目标 CLI")
    parser.add_argument("--account", help="指定账号 id")
    parser.add_argument("--provider", help="指定 provider id")
    args = parser.parse_args(argv)

    cfg = load_command_config()
    default_provider = ensure_provider_credentials(cfg)
    default_provider, models_cache = ensure_models_ready(cfg, default_provider)
    runtime, _models, launch_cli = choose_runtime_source(
        cfg,
        args.cli,
        default_provider,
        models_cache,
        account_id=args.account,
        provider_id=args.provider,
    )
    if runtime is None:
        console.print(f"[red]{args.cli} 当前没有可用运行来源[/red]")
        return

    payload = inspect_runtime_exposure(launch_cli, runtime)

    summary = table_cls(title="MMS Exposure Audit")
    summary.add_column("字段", style="cyan")
    summary.add_column("值", style="green")
    summary.add_row("cli", str(payload.get("cli") or "-"))
    summary.add_row("runtime", str(payload.get("runtime_name") or payload.get("runtime_id") or "-"))
    summary.add_row("auth_mode", str(payload.get("auth_mode") or "-"))
    network = payload.get("network") or {}
    summary.add_row("net", str(network.get("proxy_mode") or "-"))
    summary.add_row("dns", str(network.get("dns_mode") or "-"))
    summary.add_row("proxy", str(network.get("proxy_fingerprint") or "-"))
    summary.add_row("timezone", str(network.get("timezone") or "-"))
    summary.add_row("locale", str(network.get("locale") or "-"))
    summary.add_row("fake_upstream", "on" if network.get("fake_upstream") else "off")
    summary.add_row("ipv4", "on" if network.get("force_ipv4") else "off")
    console.print(summary)

    home = payload.get("home") or {}
    home_table = table_cls(title="Session Home / Settings")
    home_table.add_column("字段", style="cyan")
    home_table.add_column("值", style="green")
    home_table.add_row("real_home", str(home.get("real_home") or "-"))
    home_table.add_row("account_home", str(home.get("account_home") or "-"))
    home_table.add_row("session_home", str(home.get("session_home") or "-"))
    home_table.add_row("settings_path", str(home.get("settings_path") or "-"))
    console.print(home_table)

    env_table = table_cls(title="Process Env Exposed To CLI")
    env_table.add_column("Key", style="cyan")
    env_table.add_column("Value", style="green")
    for item in payload.get("process_env") or []:
        env_table.add_row(str(item.get("key") or "-"), str(item.get("value") or "-"))
    console.print(env_table)

    settings = payload.get("settings") or {}
    settings_table = table_cls(title="Session Settings Exposure")
    settings_table.add_column("字段", style="cyan")
    settings_table.add_column("值", style="green")
    settings_table.add_row("statusLine", "on" if settings.get("statusline") else "off")
    settings_table.add_row("hook_events", ", ".join(settings.get("hook_events") or []) or "-")
    settings_table.add_row("env_keys", ", ".join(settings.get("env_keys") or []) or "-")
    console.print(settings_table)

    notes = payload.get("notes") or []
    if notes:
        console.print("[yellow]可观察性说明：[/yellow]")
        for note in notes:
            console.print(f"  - {note}")


def _save_cache_config_value(
    cfg,
    key,
    value,
    *,
    normalize_positive_seconds,
    ensure_provider_config,
    ensure_account_config,
    normalize_user_config,
    normalize_cache_config,
    save_config,
):
    updated_cfg = dict(cfg)
    cache_cfg = dict(updated_cfg.get("cache", {}) if isinstance(updated_cfg.get("cache"), dict) else {})
    cache_cfg[key] = normalize_positive_seconds(value, 1)
    updated_cfg["cache"] = cache_cfg
    updated_cfg, _ = ensure_provider_config(updated_cfg)
    updated_cfg, _ = ensure_account_config(updated_cfg)
    updated_cfg, _ = normalize_user_config(updated_cfg)
    updated_cfg, _ = normalize_cache_config(updated_cfg)
    save_config(updated_cfg)
    return updated_cfg


def _display_cache_settings(
    cfg,
    *,
    probe_async_refresh_after,
    probe_async_min_interval,
    command_name,
    table_cls,
    console,
):
    cache_cfg = cfg.get("cache", {}) if isinstance(cfg.get("cache"), dict) else {}
    refresh_after = cache_cfg.get("probe_async_refresh_after_sec", probe_async_refresh_after)
    min_interval = cache_cfg.get("probe_async_min_interval_sec", probe_async_min_interval)
    table = table_cls(title="MMS Cache Settings")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Meaning", style="white")
    table.add_row("probe_async_refresh_after_sec", str(refresh_after), "cache 超过多久后，启动时后台刷新")
    table.add_row("probe_async_min_interval_sec", str(min_interval), "同一 provider 两次异步刷新最小间隔")
    console.print(table)
    console.print(f"[dim]命令示例: {command_name} cache refresh-after 1800[/dim]")
    console.print(f"[dim]命令示例: {command_name} cache min-interval 300[/dim]")
    console.print(f"[dim]命令示例: {command_name} cache reset[/dim]")


def handle_cache_command(
    argv,
    *,
    command_name,
    load_command_config,
    normalize_positive_seconds,
    ensure_provider_config,
    ensure_account_config,
    normalize_user_config,
    normalize_cache_config,
    save_config,
    probe_async_refresh_after,
    probe_async_min_interval,
    table_cls,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} cache",
        description="查看或调整启动期 provider model cache 的异步刷新窗口",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    subparsers.add_parser("show", help="显示当前 cache 异步刷新参数")

    refresh_parser = subparsers.add_parser("refresh-after", help="设置 cache 多久后触发后台刷新")
    refresh_parser.add_argument("seconds", type=int, help="正整数秒数")

    interval_parser = subparsers.add_parser("min-interval", help="设置同一 provider 最小异步刷新间隔")
    interval_parser.add_argument("seconds", type=int, help="正整数秒数")

    subparsers.add_parser("reset", help="恢复默认异步刷新参数")

    args = parser.parse_args(argv)
    cfg = load_command_config()

    display_kwargs = {
        "probe_async_refresh_after": probe_async_refresh_after,
        "probe_async_min_interval": probe_async_min_interval,
        "command_name": command_name,
        "table_cls": table_cls,
        "console": console,
    }

    if args.subcommand in {None, "show"}:
        _display_cache_settings(cfg, **display_kwargs)
        return
    if args.subcommand == "refresh-after":
        _save_cache_config_value(
            cfg,
            "probe_async_refresh_after_sec",
            args.seconds,
            normalize_positive_seconds=normalize_positive_seconds,
            ensure_provider_config=ensure_provider_config,
            ensure_account_config=ensure_account_config,
            normalize_user_config=normalize_user_config,
            normalize_cache_config=normalize_cache_config,
            save_config=save_config,
        )
        console.print(f"[green]✓ cache.probe_async_refresh_after_sec = {int(args.seconds)}[/green]")
        return
    if args.subcommand == "min-interval":
        _save_cache_config_value(
            cfg,
            "probe_async_min_interval_sec",
            args.seconds,
            normalize_positive_seconds=normalize_positive_seconds,
            ensure_provider_config=ensure_provider_config,
            ensure_account_config=ensure_account_config,
            normalize_user_config=normalize_user_config,
            normalize_cache_config=normalize_cache_config,
            save_config=save_config,
        )
        console.print(f"[green]✓ cache.probe_async_min_interval_sec = {int(args.seconds)}[/green]")
        return
    if args.subcommand == "reset":
        updated_cfg = dict(cfg)
        updated_cfg["cache"] = {
            "probe_async_refresh_after_sec": probe_async_refresh_after,
            "probe_async_min_interval_sec": probe_async_min_interval,
        }
        updated_cfg, _ = normalize_cache_config(updated_cfg)
        save_config(updated_cfg)
        console.print("[green]✓ 已恢复默认 cache 异步刷新参数[/green]")
        _display_cache_settings(updated_cfg, **display_kwargs)
        return

    parser.print_help()


def handle_guard_command(
    argv,
    *,
    command_name,
    bootstrap_cfg,
    load_config,
    default_config,
    config_write_target_path,
    build_config_guard_snapshot,
    config_snapshot_path,
    load_json_snapshot,
    snapshot_diff_lines,
    iso_now,
    snapshot_digest,
    write_json_snapshot,
    table_cls,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} guard",
        description="查看或接受 MMS 配置/关键文件快照",
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser("status", help="查看当前快照状态")
    subparsers.add_parser("accept", help="把当前状态设为新的已确认快照")

    args = parser.parse_args(argv)
    config_path = config_write_target_path()
    cfg = bootstrap_cfg if isinstance(bootstrap_cfg, dict) else (load_config() or default_config())
    current_snapshot = build_config_guard_snapshot(cfg, config_path=config_path)
    latest_path = config_snapshot_path("startup", "latest.json", config_path=config_path)
    accepted_path = config_snapshot_path("startup", "accepted.json", config_path=config_path)
    pending_path = config_snapshot_path("startup", "pending.json", config_path=config_path)
    accepted_payload = load_json_snapshot(accepted_path) or {}
    accepted_snapshot = accepted_payload.get("snapshot") if isinstance(accepted_payload, dict) else None
    diff_lines = snapshot_diff_lines(accepted_snapshot, current_snapshot) if accepted_snapshot else []

    if args.subcommand == "accept":
        payload = {
            "kind": "startup",
            "captured_at": iso_now(),
            "digest": snapshot_digest(current_snapshot),
            "snapshot": current_snapshot,
        }
        write_json_snapshot(latest_path, payload)
        write_json_snapshot(accepted_path, payload)
        if os.path.exists(pending_path):
            try:
                os.remove(pending_path)
            except OSError:
                pass
        console.print(f"[green]✓ 已接受当前快照[/green]\n[dim]{accepted_path}[/dim]")
        return

    status = "missing" if not accepted_snapshot else ("drift" if diff_lines else "stable")
    table = table_cls(title="MMS Snapshot Guard")
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")
    table.add_row("status", status)
    table.add_row("accepted", accepted_path)
    table.add_row("latest", latest_path)
    table.add_row("pending", pending_path if os.path.exists(pending_path) else "-")
    table.add_row("real_home", current_snapshot.get("real_home", "-"))
    table.add_row("config_path", current_snapshot.get("config_path", "-"))
    table.add_row("accounts", str(len(current_snapshot.get("accounts", []))))
    table.add_row("providers", str(len(current_snapshot.get("providers", []))))
    console.print(table)
    if diff_lines:
        console.print("[red]检测到漂移：[/red]")
        for item in diff_lines[:20]:
            console.print(f"  - {item}")
        if len(diff_lines) > 20:
            console.print(f"[dim]... 还有 {len(diff_lines) - 20} 项[/dim]")


def handle_session_command(
    argv,
    *,
    command_name,
    handle_session_ls,
    handle_session_info,
    handle_session_prune,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} session",
        description="查看 MMS 托管 CLI session",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    ls_parser = subparsers.add_parser("ls", help="列出已索引 session")
    ls_parser.add_argument("--cli", default="claude", choices=["claude"])

    info_parser = subparsers.add_parser("info", help="查看单个 session 详情")
    info_parser.add_argument("session_id", help="session_id 或 pid-<pid>")
    info_parser.add_argument("--cli", default="claude", choices=["claude"])

    prune_parser = subparsers.add_parser("prune", help="列出或删除 stale MMS gateway session")
    prune_parser.add_argument("--cli", default="all", choices=["claude", "codex", "opencode", "all"])
    prune_parser.add_argument("--dry-run", action="store_true", help="只列出候选项；默认行为")
    prune_parser.add_argument("--apply", action="store_true", help="实际删除 stale session；默认只 dry-run")
    prune_parser.add_argument("--yes", action="store_true", help="配合 --apply，确认删除")

    args = parser.parse_args(argv)
    if args.subcommand == "ls":
        handle_session_ls(args.cli)
        return
    if args.subcommand == "info":
        handle_session_info(args.session_id, args.cli)
        return
    if args.subcommand == "prune":
        handle_session_prune(args.cli, apply=bool(args.apply), yes=bool(args.yes))
        return
    parser.print_help()


def handle_env_command(
    cfg,
    argv,
    *,
    command_name,
    resolve_named_preset,
    resolve_preset_export_runtime,
    env_dir,
    preset_env_file_path,
    display_title,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} env",
        description="输出预设对应的 export 环境变量",
    )
    parser.add_argument("preset_name", help="预设名称")
    parser.add_argument("--apply", action="store_true", help="写入 ~/.config/mms/env/<preset>.sh")
    parser.add_argument("--provider", help="临时覆盖预设中的 provider")
    args = parser.parse_args(argv)

    preset = resolve_named_preset(cfg, args.preset_name)
    if preset is None:
        return

    result = resolve_preset_export_runtime(cfg, preset, provider_override=args.provider)
    if result is None:
        return

    cli, exports, _runtime = result
    lines = [f"export {key}={shlex.quote(str(value))}" for key, value in exports.items()]
    export_block = "\n".join(lines)

    console.print(f"\n[bold cyan]{args.preset_name} ({cli}) 环境变量:[/bold cyan]\n")
    console.print(export_block)

    if args.apply:
        os.makedirs(env_dir, exist_ok=True)
        env_path = preset_env_file_path(args.preset_name)
        with open(env_path, "w") as handle:
            handle.write(f"# Generated by {display_title()} — preset: {args.preset_name}\n")
            handle.write(export_block + "\n")
        console.print(f"\n[green]✓ 已写入 {env_path}[/green]")
        console.print(f"[dim]需要时手动执行: source {env_path}[/dim]")
    else:
        console.print(
            f"\n[dim]复制上面的命令临时使用，或执行 {command_name} env {args.preset_name} --apply 生成独立 env 文件[/dim]"
        )


def handle_activate_command(
    cfg,
    argv,
    *,
    command_name,
    resolve_named_preset,
    resolve_preset_export_runtime,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} activate",
        description="输出可 eval 的 export 语句",
    )
    parser.add_argument("preset_name", help="预设名称")
    parser.add_argument("--provider", help="临时覆盖预设中的 provider")
    args = parser.parse_args(argv)

    preset = resolve_named_preset(cfg, args.preset_name, stderr_only=True)
    if preset is None:
        sys.exit(1)

    result = resolve_preset_export_runtime(cfg, preset, provider_override=args.provider, stderr_only=True)
    if result is None:
        sys.exit(1)

    _cli, exports, _runtime = result
    for key, value in exports.items():
        print(f"export {key}={shlex.quote(str(value))}")

    if sys.stderr.isatty():
        print(f"# ✓ preset '{args.preset_name}' activated", file=sys.stderr)


def handle_models_command(
    cfg,
    argv,
    *,
    command_name,
    provider_map,
    select_provider_for_models,
    manage_provider_models,
    text_cls,
    console,
):
    if argv and argv[0] in {"-h", "--help"}:
        console.print("[cyan]用法:[/cyan]", text_cls(f"{command_name} ls [provider_id]"))
        console.print("[dim]不带参数时先选通道，再进入模型列表与测速页。[/dim]")
        return
    provider_id = str(argv[0]).strip() if argv else ""
    providers = provider_map(cfg)
    if provider_id:
        if provider_id not in providers:
            console.print(f"[red]未找到模型源: {provider_id}[/red]")
            console.print(f"[dim]可用模型源: {', '.join(sorted(providers.keys()))}[/dim]")
            sys.exit(1)
    else:
        provider_id = select_provider_for_models(cfg)
        if not provider_id:
            return

    manage_provider_models(cfg, provider_id)


def handle_warm_command(
    cfg,
    argv,
    *,
    command_name,
    provider_map,
    select_provider_for_warm,
    resolve_provider_context,
    probe_models,
    recent_models_for_provider,
    pick_manual_models,
    warm_model_request,
    text_cls,
    panel_cls,
    prompt_cls,
    confirm_cls,
    table_cls,
    console,
):
    if argv and argv[0] in {"-h", "--help"}:
        console.print("[cyan]用法:[/cyan]", text_cls(f"{command_name} warm [provider_id]"))
        console.print("[dim]不带参数时先选通道，再选择最近使用 / 手动选择 / 全部模型。[/dim]")
        return

    provider_id = str(argv[0]).strip() if argv else ""
    providers = provider_map(cfg)
    if provider_id:
        if provider_id not in providers:
            console.print(f"[red]未找到模型源: {provider_id}[/red]")
            console.print(f"[dim]可用模型源: {', '.join(sorted(providers.keys()))}[/dim]")
            sys.exit(1)
    else:
        provider_id = select_provider_for_warm(cfg)
        if not provider_id:
            return

    provider = resolve_provider_context(cfg, provider_id)
    probe = probe_models(provider, emit_output=False)
    models = list(probe.get("models") or [])
    if not models:
        console.print("[yellow]当前通道没有可预热的模型[/yellow]")
        return

    recent_models = [item for item in recent_models_for_provider(provider_id) if item in models]

    console.print(panel_cls(
        f"[bold]通道:[/bold] {provider.get('name', provider_id)}\n"
        f"[bold]可用模型数:[/bold] {len(models)}\n"
        f"[dim]预热会真实发请求，建议优先预热最近常用模型，不建议默认全量预热。[/dim]",
        title="模型预热",
        border_style="cyan",
    ))
    console.print("  1. 预热最近使用模型（推荐）")
    console.print("  2. 手动选择模型")
    console.print("  3. 预热全部模型（不推荐）")
    console.print("  4. 返回")
    choice = prompt_cls.ask("选择操作", choices=["1", "2", "3", "4"], default="1")

    selected_models = []
    if choice == "1":
        selected_models = recent_models
        if not selected_models:
            console.print("[yellow]当前没有最近使用模型，已改为手动选择[/yellow]")
            selected_models = pick_manual_models(models)
    elif choice == "2":
        selected_models = pick_manual_models(models)
    elif choice == "3":
        if not confirm_cls.ask("确认预热当前通道全部模型？这会产生真实请求成本。", default=False):
            console.print("[yellow]已取消全量预热[/yellow]")
            return
        selected_models = models
    else:
        return

    if not selected_models:
        console.print("[yellow]没有选择任何模型，已取消预热[/yellow]")
        return

    results = []
    for model_name in selected_models:
        console.print(f"[dim]正在预热 {model_name} ...[/dim]")
        ok, detail = warm_model_request(provider, model_name)
        results.append((model_name, ok, detail))

    table = table_cls(title=f"{provider.get('name', provider_id)} · 预热结果", show_lines=True)
    table.add_column("模型", style="cyan")
    table.add_column("结果", style="green")
    table.add_column("详情", style="yellow")
    success_count = 0
    for model_name, ok, detail in results:
        if ok:
            success_count += 1
        table.add_row(model_name, "成功" if ok else "失败", detail)
    console.print(table)
    console.print(f"[green]✓ 已完成预热：成功 {success_count} / {len(results)}[/green]")


def handle_export(
    cli_name,
    provider,
    *,
    apply=False,
    cli_names,
    get_export_env,
    env_dir,
    env_file_path,
    display_title,
    export_command_hint,
    console,
):
    if cli_name not in cli_names:
        console.print(f"[red]不支持的 CLI: {cli_name}[/red]")
        console.print(f"支持: {', '.join(cli_names)}")
        return

    exports = get_export_env(cli_name, provider)
    if not exports:
        console.print(f"[yellow]{cli_name} 无需 export；启动时会按 CLI 自己的参数或登录方式处理[/yellow]")
        return

    lines = [f"export {key}={shlex.quote(str(value))}" for key, value in exports.items()]
    export_block = "\n".join(lines)

    console.print(f"\n[bold cyan]{cli_name} 环境变量:[/bold cyan]\n")
    console.print(export_block)

    if apply:
        os.makedirs(env_dir, exist_ok=True)
        path = env_file_path(cli_name)
        with open(path, "w") as handle:
            handle.write(f"# Generated by {display_title()}\n")
            handle.write(export_block + "\n")

        console.print(f"\n[green]✓ 已写入 {path}[/green]")
        console.print("[dim]这是独立 env 文件，不会自动修改 ~/.zshrc 或 ~/.bashrc[/dim]")
        console.print(f"[dim]需要时手动执行: source {path}[/dim]")
    else:
        console.print(
            f"\n[dim]复制上面的命令临时使用，或执行 {export_command_hint(cli_name)} 生成独立 env 文件[/dim]"
        )


def emit_preset_error(message, *, stderr_only=False, console):
    if stderr_only:
        print(message, file=sys.stderr)
    else:
        console.print(message)


def preset_env_file_path(preset_name, *, env_dir):
    safe_name = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "-"
        for ch in str(preset_name or "").strip().lower()
    ).strip("-_")
    safe_name = safe_name or "preset"
    return os.path.join(env_dir, f"{safe_name}.sh")


def resolve_named_preset(
    cfg,
    preset_name,
    *,
    normalize_preset_entry,
    emit_preset_error,
    stderr_only=False,
):
    presets = cfg.get("presets", {})
    if preset_name not in presets:
        emit_preset_error(f"预设 '{preset_name}' 不存在", stderr_only=stderr_only)
        if presets:
            emit_preset_error(f"可用预设: {', '.join(presets.keys())}", stderr_only=stderr_only)
        return None
    return normalize_preset_entry(preset_name, presets[preset_name])


def infer_preset_auth_mode(preset):
    if not isinstance(preset, dict):
        return None
    if preset.get("bridge"):
        return "oauth_bridge"
    if preset.get("account"):
        return "oauth"
    if preset.get("provider"):
        return "api_key"
    return None


def resolve_preset_export_runtime(
    cfg,
    preset,
    provider_override=None,
    *,
    stderr_only=False,
    infer_preset_auth_mode,
    emit_preset_error,
    ensure_provider_credentials,
    validate_provider_for_cli,
    get_export_env,
):
    cli = preset.get("cli", "claude")
    auth_mode = infer_preset_auth_mode(preset)

    if auth_mode in ("oauth", "oauth_bridge"):
        emit_preset_error(f"此预设使用 {auth_mode} 模式，不支持 env export", stderr_only=stderr_only)
        return None

    provider_id = provider_override or preset.get("provider") or None

    runtime = ensure_provider_credentials(cfg, provider_id)
    if runtime is None:
        emit_preset_error(f"无法解析 provider: {provider_id or 'default'}", stderr_only=stderr_only)
        return None

    if not provider_id and sys.stderr.isatty():
        default_name = runtime.get("id", "default") if isinstance(runtime, dict) else "default"
        print(f"预设未指定 provider，使用默认: {default_name}", file=sys.stderr)

    try:
        validate_provider_for_cli(cli, runtime)
    except Exception as exc:
        emit_preset_error(str(exc), stderr_only=stderr_only)
        return None

    exports = get_export_env(cli, runtime)
    if not exports:
        emit_preset_error(f"{cli} 无需 export；启动时会按 CLI 自己的参数或登录方式处理", stderr_only=stderr_only)
        return None

    return cli, exports, runtime


def handle_presets_command(
    cfg,
    *,
    preset_has_visible_model_options,
    infer_preset_auth_mode,
    default_provider_id,
    table_cls,
    console,
):
    presets = cfg.get("presets", {})
    visible_presets = {
        name: preset for name, preset in presets.items()
        if preset_has_visible_model_options(preset)
    }
    if visible_presets:
        table = table_cls(title="已保存预设")
        table.add_column("名称", style="cyan")
        table.add_column("CLI", style="green")
        table.add_column("Provider", style="magenta")
        table.add_column("模型", style="yellow")
        table.add_column("描述", style="dim")
        table.add_column("模式", style="blue")
        for name, preset in visible_presets.items():
            model_str = preset.get("model", f"opus={preset.get('opus','')}, sonnet={preset.get('sonnet','')}")
            desc = preset.get("description", "")
            auth = infer_preset_auth_mode(preset) or "—"
            table.add_row(
                name,
                preset.get("cli", "?"),
                preset.get("provider", default_provider_id),
                str(model_str),
                desc,
                auth,
            )
        console.print(table)


def display_config_help(*, command_name, console):
    console.print(f"[bold]{command_name} config[/bold] — 配置查看与管理")
    console.print(f"[dim]用法: {command_name} config [子命令] [参数][/dim]")
    console.print("\n[bold]常用子命令:[/bold]")
    console.print(f"  {command_name} config")
    console.print(f"  {command_name} config file")
    console.print(f"  {command_name} config validate")
    console.print(f"  {command_name} config get <dot.path>")
    console.print(f"  {command_name} config set <dot.path> <value>")
    console.print(f"  {command_name} config unset <dot.path>")
    console.print(f"  {command_name} config connect")
    console.print(f"  {command_name} config web [--no-open]")
    console.print(f"  {command_name} config preferences.help")
    console.print(f"  {command_name} config human-gate")
    console.print(f"  [dim]可调参数示例: cache.probe_async_refresh_after_sec / cache.probe_async_min_interval_sec[/dim]")
    console.print("\n[bold]Provider:[/bold]")
    console.print(f"  {command_name} config provider.list")
    console.print(f"  {command_name} config provider.default [id]")
    console.print(f"  {command_name} config provider.add [id]")
    console.print(f"  {command_name} config provider.edit <id>")
    console.print(f"  {command_name} config provider.remove <id>")
    console.print(f"  {command_name} config provider.credentials [id]")
    console.print(f"  {command_name} config extension.openrouter [add|status|models]")
    console.print("\n[bold]Account:[/bold]")
    console.print(f"  {command_name} config account.list")
    console.print(f"  {command_name} config account.add \\[codex|agy]")
    console.print(f"  {command_name} config account.edit <id>")
    console.print(f"  {command_name} config account.remove <id>")
    console.print(f"  {command_name} config account.status [id]")
    console.print(f"  {command_name} config account.login <id>")
    console.print(f"  {command_name} config account.default <cli> <id>")
    console.print("  [dim]Claude OAuth 独立入口已下线；MMS 不再新增/登录/设默认 Claude 官方账号。[/dim]")
    console.print("\n[bold]其他:[/bold]")
    console.print(f"  {command_name} config stats")
    console.print(f"  {command_name} config api.edit")


def display_preferences_path(*, preference_paths, preferences_doc_path, console):
    console.print("[bold]MMS preferences.toml[/bold]")
    for path in preference_paths:
        marker = "active" if os.path.exists(path) else "create-if-needed"
        console.print(f"  {path}  [dim]({marker})[/dim]")
    console.print(f"[dim]文档: {preferences_doc_path}[/dim]")
    console.print("[yellow]Human gate:[/yellow] agents may inspect/propose, but must not auto-write real ~/.config/mms/** without human confirmation.")


def display_preferences_example(*, preferences_example_toml, console):
    console.print(preferences_example_toml.rstrip(), markup=False)


def display_human_gate_help(*, command_name, preferences_doc_path, console):
    console.print("[bold]MMS Human Gate[/bold]")
    console.print("- real config tree `~/.config/mms/**` is human-only for agents.")
    console.print("- allowed for agents: inspect, explain, generate manual diff, print examples.")
    console.print("- blocked without human confirmation: writing config.toml, preferences.toml, override.toml, credentials.sh, accounts/**, env/**, usage/account state, or Claude config.")
    console.print("- required write flow: plan -> backup -> human double check -> audited write -> post-write human double check.")
    console.print("- `preferences.toml` is safer than `override.toml`, but it is still real user config and stays behind the same human gate.")
    console.print(f"[dim]LLM entry: run `{command_name} config preferences.help` and read {preferences_doc_path} before advising config edits.[/dim]")


def display_preferences_help(*, command_name, preference_paths, preferences_doc_path, console):
    console.print("[bold]MMS User Preferences[/bold]")
    console.print(f"Path: {preference_paths[0]}")
    console.print("Purpose: user-owned, install-safe, allowlisted launch preference overlay.")
    console.print("\n[bold]Commands:[/bold]")
    console.print(f"  {command_name} config preferences.path")
    console.print(f"  {command_name} config preferences.example")
    console.print(f"  {command_name} config preferences.doc")
    console.print(f"  {command_name} config human-gate")
    console.print("\n[bold]Allowed keys:[/bold]")
    console.print("  launch.defaults: thinking_mode, reasoning_effort, caveman_mode, nsr_mode, agent_pack, bypass")
    console.print("  launch.cli.<claude|codex|opencode|agy>: same launch keys")
    console.print("  session_surfaces.disabled: skills, mcp, hooks")
    console.print("  assets.roots: web_access, weber, agent_browser, token_saver, toon, xmem, caveman, nsr, ecc, omc, auto_github_contributor")
    console.print("\n[bold]Denied / ignored:[/bold]")
    console.print("  api_key, base_url, proxy, account identity, provider routes, OAuth tokens, credentials, Claude config, real HOME/XDG/auth state")
    console.print("\n[bold]Overlay order:[/bold]")
    console.print("  config.toml -> override.toml -> preferences.toml launch allowlist -> confirm screen changes -> launcher")
    console.print(f"[dim]Full doc: {preferences_doc_path}[/dim]")
    console.print("[yellow]Human gate:[/yellow] agents can propose edits, but must not auto-write real ~/.config/mms/** without human confirmation.")


def display_usage_stats(*, load_usage_stats, usage_path, table_cls, console):
    stats = load_usage_stats()
    sources = stats.get("sources", {})
    if not sources:
        console.print("[yellow]还没有本地启动统计[/yellow]")
        console.print(f"[dim]统计文件会写入 {usage_path}[/dim]")
        return

    table = table_cls(title="本地启动统计", show_lines=True)
    table.add_column("来源", style="cyan")
    table.add_column("CLI", style="green")
    table.add_column("启动次数", style="yellow")
    table.add_column("最近模型", style="magenta")
    table.add_column("最近使用", style="white")

    rows = sorted(
        sources.values(),
        key=lambda item: (item.get("last_used_at", ""), item.get("launches", 0)),
        reverse=True,
    )
    for item in rows:
        table.add_row(
            f"{item.get('runtime_kind', 'source')} / {item.get('name', item.get('id', 'default'))}",
            str(item.get("cli", "")),
            str(item.get("launches", 0)),
            str(item.get("last_model", "")),
            str(item.get("last_used_at", "")),
        )
    console.print(table)
    console.print("[dim]这是本地软统计，用于排序/推荐参考；不等于真实计费数据。[/dim]")


def display_adapter_registry(*, top_source_companies, default_adapter_policy, command_name, table_cls, console):
    table = table_cls(title="来源公司 / Adapter Registry (Top 10)", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("公司/品牌", style="green")
    table.add_column("模型族", style="yellow")
    table.add_column("推荐 Adapter", style="magenta")
    table.add_column("当前状态", style="white")
    table.add_column("OAuth", style="white")
    table.add_column("默认 Claude Bridge", style="white")

    for idx, item in enumerate(top_source_companies, 1):
        table.add_row(
            str(idx),
            f"{item.get('company', '')} / {item.get('brand', '')}",
            ", ".join(item.get("families", [])),
            str(item.get("default_adapter", "")),
            str(item.get("current_support", "")),
            "yes" if item.get("oauth_native") else "no",
            "yes" if item.get("claude_bridge_default") else "no",
        )
    console.print(table)
    console.print("[bold]默认策略:[/bold]")
    for key, text in default_adapter_policy.items():
        console.print(f"  [cyan]{key}[/cyan]: {text}")
    console.print(
        f"[dim]详情文档: docs/ADAPTER_REGISTRY.md；命令: {command_name} config adapter.registry[/dim]"
    )


def display_providers(
    cfg,
    *,
    default_provider_id,
    default_priority,
    resolve_provider_context,
    provider_openai_base_url,
    provider_anthropic_base_url,
    command_name,
    table_cls,
    console,
):
    providers = cfg.get("providers", [])
    if not providers:
        console.print("[yellow]未配置模型源[/yellow]")
        return

    table = table_cls(title="模型源列表", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("名称", style="green")
    table.add_column("协议", style="yellow")
    table.add_column("CLI", style="magenta")
    table.add_column("优先级", style="white")
    table.add_column("状态", style="white")
    table.add_column("地址", style="blue")

    default_id = cfg.get("provider", {}).get("default", default_provider_id)
    for provider in providers:
        provider_ctx = resolve_provider_context(cfg, provider.get("id"))
        status = "默认" if provider.get("id") == default_id else ""
        status = f"{status} 启用" if provider.get("enabled", True) else f"{status} 禁用".strip()
        table.add_row(
            str(provider.get("id", "")),
            str(provider.get("name", "")),
            ", ".join(provider.get("protocols", [])),
            ", ".join(provider.get("supported_clis", [])),
            str(provider.get("priority", default_priority)),
            status.strip(),
            provider_openai_base_url(provider_ctx) or provider_anthropic_base_url(provider_ctx) or "(未设置)",
        )
    console.print(table)
    console.print(
        f"[dim]提示: 可用 {command_name} config provider.default <id> 切换默认模型源。[/dim]"
    )


def display_accounts(
    cfg,
    *,
    default_priority,
    probe_account_status,
    command_name,
    table_cls,
    console,
):
    accounts = cfg.get("accounts", [])
    if not accounts:
        console.print("[yellow]未配置账号档案[/yellow]")
        return

    defaults = cfg.get("account", {}).get("defaults", {})
    table = table_cls(title="账号档案列表", show_lines=True)
    table.add_column("文件夹名", style="cyan")
    table.add_column("显示名", style="green")
    table.add_column("CLI", style="yellow")
    table.add_column("优先级", style="white")
    table.add_column("状态", style="magenta")
    table.add_column("登录态", style="white")
    table.add_column("文件夹目录", style="blue")

    for account in accounts:
        login_state = probe_account_status(account)
        status = []
        if defaults.get(account.get("cli")) == account.get("id"):
            status.append("默认")
        status.append("启用" if account.get("enabled", True) else "禁用")
        table.add_row(
            str(account.get("id", "")),
            str(account.get("name", "")),
            str(account.get("cli", "")),
            str(account.get("priority", default_priority)),
            " ".join(status).strip(),
            login_state.get("summary") or login_state.get("state", ""),
            str(account.get("home_dir", "")),
        )
    console.print(table)
    console.print(
        f"[dim]提示: 可用 {command_name} config account.default <cli> <id> 设置默认账号，"
        f"{command_name} config account.login <id> 进入官方登录。[/dim]"
    )
    console.print("[dim]注: Claude OAuth 独立入口已下线，这里仅保留旧配置只读兼容。[/dim]")


def display_runtime_usage(
    runtime_kind,
    runtime_id,
    title,
    *,
    use_tui,
    clear_console,
    usage_rows_for_runtime,
    active_usage_path,
    pause_after_tui_report,
    table_cls,
    console,
):
    if use_tui():
        try:
            clear_console()
        except Exception:
            pass
    rows = usage_rows_for_runtime(runtime_kind, runtime_id)
    if not rows:
        console.print(f"[yellow]{title} 还没有本地启动统计[/yellow]")
        console.print(f"[dim]统计文件: {active_usage_path()}[/dim]")
        if use_tui():
            pause_after_tui_report("按 Enter 返回通道详情")
        return

    table = table_cls(title=f"{title} · 本地统计", show_lines=True)
    table.add_column("CLI", style="cyan")
    table.add_column("启动次数", style="green")
    table.add_column("最近模型", style="yellow")
    table.add_column("最近使用", style="magenta")
    for item in rows:
        table.add_row(
            str(item.get("cli", "")),
            str(item.get("launches", 0)),
            str(item.get("last_model", "")),
            str(item.get("last_used_at", "")),
        )
    console.print(table)
    console.print("[dim]这里只是本地启动统计，不代表官方真实余额或剩余额度。[/dim]")
    if use_tui():
        pause_after_tui_report("按 Enter 返回通道详情")


def display_provider_model_table(
    provider,
    probe,
    *,
    get_speed_entry,
    infer_model_family,
    model_capability_summary,
    model_cli_summary,
    model_source_label,
    ttfb_label,
    tps_label,
    table_cls,
    console,
):
    table = table_cls(title=f"{provider.get('name', provider.get('id'))} · 模型列表", show_lines=True)
    table.add_column("模型", style="cyan")
    table.add_column("家族", style="yellow")
    table.add_column("能力", style="magenta")
    table.add_column("CLI", style="dim")
    table.add_column("来源", style="green")
    table.add_column("首字节延迟", style="yellow")
    table.add_column("生成速度", style="magenta")
    table.add_column("样本", style="white")
    table.add_column("最近更新", style="blue")

    for model_id in probe.get("models") or []:
        speed = get_speed_entry(model_id, provider=provider)
        ttfb = "暂无数据"
        tps = "暂无数据"
        samples = "-"
        updated = "-"
        if speed:
            ttfb_value = speed.get("ttfb_avg_ms")
            ttfb = f"{ttfb_value:.0f}ms / {ttfb_label(ttfb_value)}" if isinstance(ttfb_value, (int, float)) else "暂无数据"
            tps_value = speed.get("tps_avg")
            tps = f"{tps_value:.1f} / {tps_label(tps_value)}" if isinstance(tps_value, (int, float)) else "暂无数据"
            samples = str(speed.get("samples", 0))
            if speed.get("warming_up"):
                samples = f"{samples}（预热中）"
            updated = str(speed.get("last_updated") or "-")
            if speed.get("is_stale"):
                updated = f"{updated} (stale)"
        table.add_row(
            model_id,
            infer_model_family(model_id)[0],
            model_capability_summary(model_id),
            model_cli_summary(model_id),
            model_source_label((probe.get("model_sources") or {}).get(model_id, probe.get("base_source", "remote"))),
            ttfb,
            tps,
            samples,
            updated,
        )
    console.print(table)
    hidden_models = probe.get("hidden_models") or []
    extra_models = probe.get("extra_models") or []
    if extra_models:
        console.print(f"[dim]手工补充模型: {', '.join(extra_models)}[/dim]")
    if hidden_models:
        console.print(f"[dim]已隐藏模型: {', '.join(hidden_models)}[/dim]")
    raw_models = probe.get("raw_models") or []
    if raw_models and raw_models != (probe.get("models") or []):
        console.print(f"[dim]原始模型数: {len(raw_models)} | 最终展示模型数: {len(probe.get('models') or [])}[/dim]")


def display_openrouter_extension_help(command_name, *, console):
    console.print(f"[bold]{command_name} config extension.openrouter[/bold] — OpenRouter 可选扩展")
    console.print(f"  {command_name} config extension.openrouter add")
    console.print(f"  {command_name} config extension.openrouter status [provider_id] [--limit N] [--json]")
    console.print(f"  {command_name} config extension.openrouter models [provider_id] [--limit N] [--json]")
    console.print("[dim]status/models 默认不写真实 MMS 配置；add 会进入交互式 provider 接入。[/dim]")


def display_openrouter_model_rows(title, rows, *, limit, table_cls, console):
    table = table_cls(title=title, show_lines=False)
    table.add_column("模型", style="cyan")
    table.add_column("原始来源", style="green")
    table.add_column("免费", style="yellow", width=6)
    table.add_column("输入", style="magenta")
    table.add_column("输出", style="magenta")
    table.add_column("Context", justify="right")
    shown = list(rows or [])[: int(limit)]
    for item in shown:
        table.add_row(
            str(item.get("id") or ""),
            str(item.get("origin") or ""),
            "yes" if item.get("is_free") else "no",
            ",".join(item.get("input_modalities") or []),
            ",".join(item.get("output_modalities") or []),
            str(item.get("context_length") or ""),
        )
    console.print(table)
    if len(rows or []) > len(shown):
        console.print(f"[dim]仅展示前 {len(shown)} / {len(rows)} 个；可加 --limit 调整。[/dim]")


def display_openrouter_video_rows(rows, *, limit, table_cls, console):
    table = table_cls(title="OpenRouter Video 模型", show_lines=False)
    table.add_column("模型", style="cyan")
    table.add_column("原始来源", style="green")
    table.add_column("分辨率", style="yellow")
    table.add_column("时长", style="magenta")
    shown = list(rows or [])[: int(limit)]
    for item in shown:
        table.add_row(
            str(item.get("id") or ""),
            str(item.get("origin") or ""),
            ",".join(str(value) for value in item.get("supported_resolutions") or []),
            ",".join(str(value) for value in item.get("supported_durations") or []),
        )
    console.print(table)
    if len(rows or []) > len(shown):
        console.print(f"[dim]仅展示前 {len(shown)} / {len(rows)} 个；可加 --limit 调整。[/dim]")


def display_openrouter_extension_summary(
    summary,
    *,
    provider_label="",
    limit=12,
    show_models=False,
    table_cls,
    console,
):
    account = summary.get("account") or {}
    counts = summary.get("counts") or {}
    requests = summary.get("requests") or {}
    table = table_cls(title="OpenRouter Extension", show_lines=True)
    table.add_column("项目", style="cyan")
    table.add_column("值", style="green")
    table.add_row("provider/key", provider_label or "env/public")
    table.add_row("account tier", f"{account.get('tier')} ({account.get('reason')})")
    table.add_row("model source", str(summary.get("model_source") or "-"))
    table.add_row("visible text", str(counts.get("visible_text", 0)))
    table.add_row("image/video", f"{'on' if summary.get('image_enabled') else 'off'} / {'on' if summary.get('video_enabled') else 'off'}")
    table.add_row("requests", ", ".join(f"{key}:{value.get('status')}" for key, value in requests.items()))
    console.print(table)
    if summary.get("free_only"):
        console.print("[yellow]当前按 free-only 策略展示：只列免费文本模型，隐藏 OpenRouter Image / Video。[/yellow]")
    if not show_models:
        return
    display_openrouter_model_rows("OpenRouter Text 模型", summary.get("text_models") or [], limit=limit, table_cls=table_cls, console=console)
    if summary.get("image_enabled"):
        display_openrouter_model_rows("OpenRouter Image 模型", summary.get("image_models") or [], limit=limit, table_cls=table_cls, console=console)
    if summary.get("video_enabled"):
        display_openrouter_video_rows(summary.get("video_models") or [], limit=limit, table_cls=table_cls, console=console)


def display_config(
    cfg,
    *,
    prefix="",
    depth=0,
    resolve_provider_context,
    provider_openai_base_url,
    provider_anthropic_base_url,
    mask_key,
    active_credentials_path,
    active_usage_path,
    display_providers,
    display_accounts,
    probe_async_refresh_after,
    probe_async_min_interval,
    existing_override_paths,
    override_paths,
    existing_preferences_paths,
    preference_paths,
    command_name,
    console,
):
    if depth == 0:
        provider = resolve_provider_context(cfg)
        console.print("[bold]模型源:[/bold]")
        console.print(f"  [cyan]default[/cyan] = {cfg.get('provider', {}).get('default', 'default')}")
        console.print(f"  [cyan]openai_base_url[/cyan] = {provider_openai_base_url(provider) or '(未设置)'}")
        console.print(f"  [cyan]anthropic_base_url[/cyan] = {provider_anthropic_base_url(provider) or '(未设置)'}")
        key_display = mask_key(provider.get("api_key", "")) if provider.get("api_key") else "(未设置)"
        console.print(f"  [cyan]api_key[/cyan] = {key_display}")
        console.print(f"  [cyan]credentials_file[/cyan] = {active_credentials_path()}")
        console.print("  [dim]api_key 为掩码显示；真实值请查看 credentials_file。[/dim]")
        display_providers(cfg)
        display_accounts(cfg)
        console.print(f"  [cyan]usage_file[/cyan] = {active_usage_path()}")
        console.print("  [dim]usage 只记录本地启动统计，不代表真实余额或官方剩余额度。[/dim]")
        cache_cfg = cfg.get("cache", {})
        if isinstance(cache_cfg, dict):
            console.print(f"  [cyan]probe_async_refresh_after_sec[/cyan] = {cache_cfg.get('probe_async_refresh_after_sec', probe_async_refresh_after)}")
            console.print(f"  [cyan]probe_async_min_interval_sec[/cyan] = {cache_cfg.get('probe_async_min_interval_sec', probe_async_min_interval)}")
            console.print("  [dim]以上窗口控制模型列表异步刷新：首屏先读 cache，后台再 refresh。[/dim]")
        active_overrides = existing_override_paths()
        if active_overrides:
            console.print(f"  [cyan]override_files[/cyan] = {active_overrides}")
            console.print("  [dim]override 仅在运行时叠加，不会直接写回 config.toml。[/dim]")
        else:
            console.print(f"  [cyan]override_files[/cyan] = {override_paths}")
            console.print("  [dim]如需团队共享默认值，可在以上路径创建 override.toml。[/dim]")
        active_preferences = existing_preferences_paths()
        console.print(f"  [cyan]preferences_files[/cyan] = {active_preferences or preference_paths}")
        console.print(f"  [dim]用户偏好 allowlist: {command_name} config preferences.help；真实配置仍受 human-gate 保护。[/dim]")

    for key, value in cfg.items():
        if depth == 0 and key in {"providers", "provider", "accounts", "account", "_mms_preferences"}:
            continue
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            console.print(f"{'  ' * depth}[bold]{key}:[/bold]")
            display_config(
                value,
                prefix=full_key,
                depth=depth + 1,
                resolve_provider_context=resolve_provider_context,
                provider_openai_base_url=provider_openai_base_url,
                provider_anthropic_base_url=provider_anthropic_base_url,
                mask_key=mask_key,
                active_credentials_path=active_credentials_path,
                active_usage_path=active_usage_path,
                display_providers=display_providers,
                display_accounts=display_accounts,
                probe_async_refresh_after=probe_async_refresh_after,
                probe_async_min_interval=probe_async_min_interval,
                existing_override_paths=existing_override_paths,
                override_paths=override_paths,
                existing_preferences_paths=existing_preferences_paths,
                preference_paths=preference_paths,
                command_name=command_name,
                console=console,
            )
        elif isinstance(value, list):
            console.print(f"{'  ' * depth}[cyan]{key}[/cyan] = {value}")
        else:
            display = mask_key(str(value)) if "key" in key.lower() else str(value)
            console.print(f"{'  ' * depth}[cyan]{key}[/cyan] = {display}")


def run_script_subcommand(script_name, argv, subcommand_name, *, script_dir, command_name, console):
    script_path = os.path.join(script_dir, script_name)
    if not os.path.exists(script_path):
        console.print(f"[red]找不到脚本: {script_path}[/red]")
        return 1
    env = os.environ.copy()
    env["MMS_SUBCOMMAND_PROG"] = f"{command_name} {subcommand_name}"
    try:
        completed = subprocess.run([sys.executable, script_path, *argv], env=env)
        return int(completed.returncode or 0)
    except KeyboardInterrupt:
        return 130


def handle_doctor_command(argv, *, script_dir, command_name, console):
    return run_script_subcommand(
        "doctor_claude_models.py",
        argv,
        "doctor",
        script_dir=script_dir,
        command_name=command_name,
        console=console,
    )


def handle_test_command(argv, *, subcommand_name, script_dir, command_name, console):
    return run_script_subcommand(
        "smoke_cli_channels.py",
        argv,
        subcommand_name,
        script_dir=script_dir,
        command_name=command_name,
        console=console,
    )


def handle_opencode_smoke_command(argv, *, script_dir, command_name, console):
    return run_script_subcommand(
        "smoke_opencode_profile.py",
        argv,
        "opencode-smoke",
        script_dir=script_dir,
        command_name=command_name,
        console=console,
    )
