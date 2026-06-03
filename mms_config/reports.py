"""Read-only Config/Registry report payload builders for MMS core commands."""

from __future__ import annotations

from typing import Any, Callable

Localize = Callable[[str, str], str]


def _default_localize(zh: str, en: str | None = None) -> str:
    return zh if en is None else zh


def model_source_status_rows(summary, *, localize=_default_localize):
    summary = summary if isinstance(summary, dict) else {}
    root = summary.get("root") if isinstance(summary.get("root"), dict) else {}
    registry_db = summary.get("registry_db") if isinstance(summary.get("registry_db"), dict) else {}
    legacy = summary.get("legacy_import") if isinstance(summary.get("legacy_import"), dict) else {}
    bundle = summary.get("generated_bundle") if isinstance(summary.get("generated_bundle"), dict) else {}
    counts = registry_db.get("counts") if isinstance(registry_db.get("counts"), dict) else {}
    candidates = legacy.get("candidates") if isinstance(legacy.get("candidates"), dict) else {}
    if not candidates and isinstance(registry_db.get("legacy_import_candidates"), dict):
        candidates = registry_db.get("legacy_import_candidates")
    next_action = summary.get("next_action") if isinstance(summary.get("next_action"), dict) else {}
    return [
        (localize("结果", "result"), summary.get("result") or "-"),
        (localize("状态", "status"), summary.get("status") or "-"),
        (localize("Ready", "Ready"), "yes" if summary.get("ready") else "no"),
        (localize("一句话", "headline"), summary.get("headline") or "-"),
        ("Root", root.get("config_root") or summary.get("config_root") or "-"),
        ("Mode", root.get("mode") or "-"),
        ("DB", registry_db.get("path") or "-"),
        (localize("DB 状态", "DB status"), registry_db.get("status") or "-"),
        (localize("来源快照", "source snapshots"), counts.get("source_snapshot", 0)),
        (localize("模型事实", "model facts"), counts.get("model_fact", 0)),
        (localize("Provider routes", "provider routes"), counts.get("provider_route", 0)),
        (localize("Legacy 冲突", "legacy conflicts"), legacy.get("conflict_count", 0)),
        (localize("Legacy 候选状态", "legacy candidate status"), candidates.get("status") or "not_imported"),
        (localize("Legacy 候选 routes", "legacy candidate routes"), candidates.get("provider_route_count", 0)),
        (localize("Legacy 下一步", "legacy next action"), legacy.get("next_action") or "-"),
        (localize("Bundle 状态", "bundle status"), bundle.get("status") or "-"),
        (localize("Bundle 校验", "bundle verified"), "yes" if bundle.get("verified") else "no"),
        (localize("Bundle runtime", "bundle runtime"), bundle.get("runtime_ready_status") or "unknown"),
        (localize("Router 缺失 key", "router missing keys"), bundle.get("router_missing_api_key_count", 0)),
        (localize("下一步", "next action"), next_action.get("label") or "-"),
        (localize("建议命令", "suggested command"), next_action.get("command") or "-"),
    ]


def model_source_status_report_payload(summary, *, localize=_default_localize):
    return (
        localize("Model Source Status", "Model Source Status"),
        model_source_status_rows(summary, localize=localize),
        localize("只读视图：不写 DB、不发布 bundle、不改变 runtime defaults。", "Read-only view: no DB writes, no bundle publish, runtime defaults unchanged."),
    )


def consumer_bundle_status_rows(summary, *, localize=_default_localize):
    summary = summary if isinstance(summary, dict) else {}
    root = summary.get("root") if isinstance(summary.get("root"), dict) else {}
    revisions = summary.get("component_revisions") if isinstance(summary.get("component_revisions"), dict) else {}
    files = summary.get("files") if isinstance(summary.get("files"), dict) else {}
    rules = summary.get("consumer_rules") if isinstance(summary.get("consumer_rules"), list) else []
    next_action = summary.get("next_action") if isinstance(summary.get("next_action"), dict) else {}
    return [
        (localize("结果", "result"), summary.get("result") or "-"),
        (localize("状态", "status"), summary.get("status") or "-"),
        (localize("Bundle 校验", "bundle verified"), "yes" if summary.get("verified") else "no"),
        (localize("入口", "entrypoint"), summary.get("consumer_entrypoint") or summary.get("manifest_path") or "-"),
        ("Root", root.get("config_root") or summary.get("config_root") or "-"),
        (localize("Bundle revision", "bundle revision"), revisions.get("bundle") or "-"),
        (localize("Route revision", "route revision"), revisions.get("route") or "-"),
        (localize("Policy revision", "policy revision"), revisions.get("policy") or "-"),
        (localize("Profile revision", "profile revision"), revisions.get("profile") or "-"),
        (localize("文件数", "file count"), len(files)),
        (localize("消费规则", "consumer rules"), " / ".join(str(item) for item in rules) or "-"),
        (localize("下一步", "next action"), next_action.get("label") or "-"),
        (localize("建议命令", "suggested command"), next_action.get("command") or "-"),
    ]


def consumer_bundle_status_report_payload(summary, *, localize=_default_localize):
    return (
        localize("Consumer Bundle Status", "Consumer Bundle Status"),
        consumer_bundle_status_rows(summary, localize=localize),
        localize("只读视图：验证 latest-approved manifest/hash；不写 DB、不发布 bundle、不读取 SQLite。", "Read-only view: verifies latest-approved manifest/hashes; no DB writes, no bundle publish, no SQLite reads."),
    )


def registry_v2_save_plan_rows(plan, *, localize=_default_localize):
    plan = plan if isinstance(plan, dict) else {}
    root = plan.get("root") if isinstance(plan.get("root"), dict) else {}
    db = plan.get("db") if isinstance(plan.get("db"), dict) else {}
    would_write = plan.get("would_write") if isinstance(plan.get("would_write"), dict) else {}
    legacy = would_write.get("legacy_compat_files") if isinstance(would_write.get("legacy_compat_files"), dict) else {}
    plan_json = plan.get("plan_json") if isinstance(plan.get("plan_json"), dict) else {}
    apply_plan = plan.get("apply_plan") if isinstance(plan.get("apply_plan"), dict) else {}
    blocked = ", ".join(str(item) for item in (plan.get("blocked_reasons") or [])) or "-"
    steps = " -> ".join(str(item) for item in (plan.get("ordered_steps") or [])) or "-"
    return [
        ("Root", root.get("config_root") or "-"),
        ("Mode", root.get("mode") or "-"),
        (localize("执行状态", "execution state"), plan.get("execution_state") or "-"),
        (localize("实际保存启用", "actual save enabled"), "yes" if plan.get("actual_save_enabled") else "no"),
        ("DB", db.get("path") or "-"),
        (localize("DB 存在", "DB exists"), "yes" if db.get("exists") else "no"),
        (localize("DB 备份目录", "DB backup dir"), db.get("backup_dir") or "-"),
        (localize("将备份 DB", "would backup DB"), "yes" if db.get("would_backup_existing_db") else "no"),
        (localize("DB candidate revision", "DB candidate revision"), "yes" if would_write.get("db_candidate_revision") else "no"),
        (localize("Secret backend", "secret backend"), "yes" if would_write.get("secret_backend") else "no"),
        (localize("Generated bundle", "generated bundle"), "yes" if would_write.get("generated_latest_approved_bundle") else "no"),
        (localize("Legacy config.toml", "legacy config.toml"), "yes" if legacy.get("config_toml") else "no"),
        (localize("Legacy model-policy.json", "legacy model-policy.json"), "yes" if legacy.get("model_policy_json") else "no"),
        (localize("Legacy credentials.sh", "legacy credentials.sh"), "yes" if legacy.get("credentials_sh") else "no"),
        (localize("阻塞原因", "blocked reasons"), blocked),
        (localize("Plan JSON", "Plan JSON"), plan_json.get("name") or "-"),
        (localize("Plan JSON 密钥", "Plan JSON secrets"), "redacted" if plan_json.get("redacted") else ("included" if plan_json.get("secrets_included") else "-")),
        (localize("WebUI 写入", "WebUI apply"), apply_plan.get("webui_button") or "-"),
        (localize("CLI 写入命令", "CLI apply command"), apply_plan.get("cli_apply_command") or "-"),
        (localize("步骤", "steps"), steps),
        (localize("下一步", "next step"), plan.get("next_implementation_step") or "-"),
    ]


def registry_v2_save_plan_report_payload(plan, *, localize=_default_localize):
    return (
        localize("Registry v2 Save Plan", "Registry v2 Save Plan"),
        registry_v2_save_plan_rows(plan, localize=localize),
        localize("只读计划：不写 DB、不写 secret backend、不发布 bundle、不改变 runtime defaults。", "Read-only plan: no DB writes, no secret backend writes, no bundle publish, runtime defaults unchanged."),
    )


def preview_doctor_report_payload(summary, *, localize=_default_localize):
    summary = summary if isinstance(summary, dict) else {}
    counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}
    bundle = summary.get("bundle") if isinstance(summary.get("bundle"), dict) else {}
    next_actions = [item for item in (summary.get("next_actions") or []) if isinstance(item, dict)]
    next_action = next_actions[0] if next_actions else {}
    rows = [
        (localize("结果", "result"), summary.get("result") or "-"),
        (localize("状态", "status"), summary.get("status") or "-"),
        (localize("Ready", "ready"), "yes" if summary.get("ready") else "no"),
        ("Root", summary.get("config_root") or "-"),
        (localize("候选 routes", "candidate routes"), counts.get("candidate_provider_routes", 0)),
        (localize("Bundle 校验", "bundle verified"), "yes" if bundle.get("verified") else "no"),
        (localize("Bundle runtime", "bundle runtime"), bundle.get("runtime_ready_status") or "unknown"),
        (localize("Router 缺失 key", "router missing keys"), counts.get("missing_api_keys", 0)),
        (localize("Preview secrets", "preview secrets"), counts.get("preview_secret_count", 0)),
        (localize("下一步", "next action"), next_action.get("label") or "-"),
        (localize("建议命令", "suggested command"), next_action.get("command") or "-"),
    ]
    return (
        localize("Preview Doctor", "Preview Doctor"),
        rows,
        localize("只读检查：不写 DB、不发布 bundle、不改变 runtime defaults。", "Read-only check: no DB writes, no bundle publish, runtime defaults unchanged."),
    )


def config_v2_promotion_plan_report_payload(summary, *, localize=_default_localize):
    summary = summary if isinstance(summary, dict) else {}
    preview = summary.get("preview") if isinstance(summary.get("preview"), dict) else {}
    stable = summary.get("stable") if isinstance(summary.get("stable"), dict) else {}
    preview_root = preview.get("root") if isinstance(preview.get("root"), dict) else {}
    stable_root = stable.get("root") if isinstance(stable.get("root"), dict) else {}
    preview_check_summary = preview.get("check") if isinstance(preview.get("check"), dict) else {}
    bundle = preview.get("bundle") if isinstance(preview.get("bundle"), dict) else {}
    safety = summary.get("promotion_safety") if isinstance(summary.get("promotion_safety"), dict) else {}
    backup_plan = summary.get("stable_backup_plan") if isinstance(summary.get("stable_backup_plan"), dict) else {}
    comparison = summary.get("bundle_comparison") if isinstance(summary.get("bundle_comparison"), dict) else {}
    comparison_preview = comparison.get("preview") if isinstance(comparison.get("preview"), dict) else {}
    comparison_stable = comparison.get("stable") if isinstance(comparison.get("stable"), dict) else {}
    next_action = summary.get("next_action") if isinstance(summary.get("next_action"), dict) else {}
    rows = [
        (localize("结果", "result"), summary.get("result") or "-"),
        (localize("状态", "status"), summary.get("status") or "-"),
        (localize("Ready for review", "Ready for review"), "yes" if summary.get("ready_for_human_review") else "no"),
        (localize("Preview root", "Preview root"), preview_root.get("config_root") or "-"),
        (localize("Stable root", "Stable root"), stable_root.get("config_root") or "-"),
        (localize("Preview check", "Preview check"), preview_check_summary.get("result") or "-"),
        (localize("Bundle 校验", "bundle verified"), "yes" if bundle.get("verified") else "no"),
        (localize("Bundle 入口", "bundle entrypoint"), bundle.get("entrypoint") or "-"),
        (localize("Stable 写策略", "stable write policy"), safety.get("stable_write_policy") or "human_only"),
        (localize("Apply 启用", "apply enabled"), "yes" if summary.get("apply_enabled") or safety.get("apply_enabled") else "no"),
        (localize("必须备份", "backup required"), "yes" if backup_plan.get("requires_backup_before_apply") or safety.get("requires_backup") else "no"),
        (localize("本命令创建备份", "backup created by this command"), "yes" if backup_plan.get("would_create_backup") else "no"),
        (localize("Bundle 对比", "bundle comparison"), comparison.get("comparison_status") or "-"),
        (localize("Preview bundle", "preview bundle"), comparison_preview.get("bundle_revision") or comparison_preview.get("status") or "-"),
        (localize("Stable bundle", "stable bundle"), comparison_stable.get("bundle_revision") or comparison_stable.get("status") or "-"),
        (localize("阻塞原因", "blocked reasons"), ", ".join(str(item) for item in (summary.get("blocked_reasons") or [])) or "-"),
        (localize("下一步", "next action"), next_action.get("label") or "-"),
        (localize("建议命令", "suggested command"), next_action.get("command") or "-"),
    ]
    return (
        localize("Config v2 Promote Plan", "Config v2 Promote Plan"),
        rows,
        localize("只读计划：停止在 human gate；不写 stable root、不改 Claude config、不发布 stable bundle。", "Read-only plan: stops at the human gate; no stable-root writes, no Claude config writes, no stable bundle publish."),
    )


def config_v2_release_readiness_report_payload(summary, *, localize=_default_localize):
    summary = summary if isinstance(summary, dict) else {}
    requirements = [item for item in (summary.get("requirements") or []) if isinstance(item, dict)]
    ok_count = sum(1 for item in requirements if item.get("ok"))
    blocked = [str(item) for item in (summary.get("blocked_requirements") or [])]
    promotion = summary.get("promotion_plan") if isinstance(summary.get("promotion_plan"), dict) else {}
    next_action = summary.get("next_action") if isinstance(summary.get("next_action"), dict) else {}
    rows = [
        (localize("结果", "result"), summary.get("result") or "-"),
        (localize("状态", "status"), summary.get("status") or "-"),
        (localize("Release complete", "release complete"), "yes" if summary.get("release_complete") else "no"),
        (localize("Ready for human gate", "ready for human gate"), "yes" if summary.get("ready_for_human_gate") else "no"),
        (localize("Human gate required", "human gate required"), "yes" if summary.get("human_gate_required") else "no"),
        (localize("完成阻塞", "completion blocker"), summary.get("completion_blocker") or "-"),
        (localize("Preview root", "Preview root"), summary.get("config_root") or "-"),
        (localize("Stable root", "Stable root"), summary.get("stable_config_root") or "-"),
        (localize("Requirements", "requirements"), f"{ok_count}/{len(requirements)} ok"),
        (localize("Blocked requirements", "blocked requirements"), ", ".join(blocked) or "-"),
        (localize("Promotion 状态", "promotion status"), promotion.get("status") or "-"),
        (localize("Promotion apply", "promotion apply"), "yes" if promotion.get("apply_enabled") else "no"),
        (localize("Promotion 阻塞", "promotion blockers"), ", ".join(str(item) for item in (promotion.get("blocked_reasons") or [])) or "-"),
        (localize("下一步", "next action"), next_action.get("label") or "-"),
        (localize("建议命令", "suggested command"), next_action.get("command") or "-"),
    ]
    return (
        localize("Config v2 Release Readiness", "Config v2 Release Readiness"),
        rows,
        localize("只读审计：证明自动检查只到 stable promotion human gate；不写 stable root、不改 Claude config、不写 DB、不发布 bundle。", "Read-only audit: proves automated checks only reach the stable promotion human gate; no stable-root writes, no Claude config writes, no DB writes, no bundle publish."),
    )


def model_source_status_tui_payload(summary, *, localize=_default_localize):
    actions = [
        ("model_source_status", localize("查看 Model Source Status", "View Model Source Status")),
        ("consumer_bundle_status", localize("查看 Consumer Bundle", "View Consumer Bundle")),
        ("registry_v2_save_plan", localize("查看 v2 Save Plan", "View v2 Save Plan")),
        ("config_v2_promotion_plan", localize("查看 Promote Plan", "View Promote Plan")),
        ("config_v2_release_readiness", localize("查看 4.0 Readiness", "View 4.0 Readiness")),
        ("preview_doctor", localize("运行 Preview Doctor", "Run Preview Doctor")),
        ("check_staleness", localize("检查 Source Staleness", "Check Source Staleness")),
        ("refresh_due_sources", localize("刷新到期 Sources", "Refresh Due Sources")),
        ("scheduled_dry_run", localize("定时刷新 Dry Run", "Scheduled Refresh Dry Run")),
        ("scheduled_no_network", localize("定时刷新 No Network", "Scheduled Refresh No Network")),
        ("refresh_sources", localize("刷新全部 Sources", "Refresh Sources")),
        ("fetch_openrouter", localize("拉取 OpenRouter Catalog", "Fetch OpenRouter Catalog")),
        ("diff_openrouter", localize("对比 OpenRouter Candidate", "OpenRouter Candidate Diff")),
        ("publish_approved", localize("发布 Approved Bundle", "Publish Approved Bundle")),
        ("verify_approved", localize("验证 Approved Bundle", "Verify Approved Bundle")),
        ("doctor", localize("Registry Doctor / 状态", "Registry Doctor / Status")),
        ("back", localize("返回", "Back")),
    ]
    return localize("模型真源 / Registry Truth", "Registry Truth"), model_source_status_rows(summary, localize=localize), actions


__all__ = [
    "model_source_status_rows",
    "model_source_status_report_payload",
    "consumer_bundle_status_rows",
    "consumer_bundle_status_report_payload",
    "registry_v2_save_plan_rows",
    "registry_v2_save_plan_report_payload",
    "preview_doctor_report_payload",
    "config_v2_promotion_plan_report_payload",
    "config_v2_release_readiness_report_payload",
    "model_source_status_tui_payload",
]
