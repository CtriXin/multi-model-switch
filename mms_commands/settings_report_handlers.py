"""Settings/report/recovery helpers with dependencies injected by core."""

from __future__ import annotations

import json
import os
import sys

from mms_config.preferences import pref_bool as _pref_bool


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


def settings_result_tui_available(*, env=None, stdin=None, stdout=None):
    env = os.environ if env is None else env
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    disabled = str(env.get("MMS_DISABLE_SETTINGS_RESULT_TUI") or "").strip().lower()
    if disabled in {"1", "true", "yes", "on"}:
        return False
    try:
        return bool(stdin.isatty() and stdout.isatty())
    except Exception:
        return False


def select_settings_result_tui(title, rows, note="", *, ok=True, settings_result_tui_payload, select_channel_action_tui):
    tui_title, info_lines, actions = settings_result_tui_payload(title, rows, note, ok=ok)
    return select_channel_action_tui(tui_title, info_lines, actions)


def print_settings_result_report(
    title,
    rows,
    note="",
    *,
    ok=True,
    settings_result_tui_available,
    select_settings_result_tui,
    mark_tui_rendered,
    clear_tui_rendered,
    ensure_rich,
    display_settings_result_report,
    console,
):
    if settings_result_tui_available():
        try:
            select_settings_result_tui(title, rows, note, ok=ok)
        except (KeyboardInterrupt, EOFError):
            pass
        except Exception:
            clear_tui_rendered()
        else:
            mark_tui_rendered()
            return

    ensure_rich()
    return display_settings_result_report(title, rows, note, ok=ok, console=console)


def print_settings_error_report(title, exc, *, print_settings_result_report, localize):
    return print_settings_result_report(
        title,
        [(localize("错误", "Error"), exc)],
        localize("操作未完成；没有改变 runtime defaults。", "Operation did not complete; runtime defaults unchanged."),
        ok=False,
    )


def pause_after_tui_report(prompt_text="按 Enter 返回", *, tui_rendered, clear_tui_rendered, ensure_rich, input_func, console):
    if tui_rendered():
        clear_tui_rendered()
        return

    ensure_rich()
    try:
        console.print(f"[dim]{prompt_text}[/dim]")
    except Exception:
        pass
    try:
        input_func()
    except (EOFError, KeyboardInterrupt):
        pass


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


def select_provider_interactive(cfg, current_provider_id, *, resolve_provider_context, table_cls, prompt_cls, console):
    providers = [
        provider for provider in cfg.get("providers", [])
        if provider.get("enabled", True) and provider.get("id") != current_provider_id
    ]
    if not providers:
        console.print("[yellow]没有可切换的其他 provider[/yellow]")
        return None

    table = table_cls(title="可切换的 Providers")
    table.add_column("#", style="cyan", width=4)
    table.add_column("ID", style="green")
    table.add_column("名称", style="yellow")
    table.add_column("协议", style="magenta")
    for index, item in enumerate(providers, 1):
        table.add_row(
            str(index),
            item.get("id", ""),
            item.get("name", ""),
            ", ".join(item.get("protocols", [])),
        )
    console.print(table)

    while True:
        choice = prompt_cls.ask("切换到哪个 provider？输入编号，留空取消", default="")
        if not choice:
            return None
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(providers):
                return resolve_provider_context(cfg, providers[idx - 1]["id"])
        console.print(f"[red]请输入 1-{len(providers)} 的编号，或直接回车取消[/red]")


def pick_recovery_actions(findings, actions, *, use_tui=False, select_actions_tui=None, panel_cls, prompt_cls, console):
    if use_tui and select_actions_tui is not None:
        selected = select_actions_tui(findings, actions, title="处理发现")
        if selected != "fallback":
            return selected

    console.print(panel_cls(
        "\n".join(f"- {item['title']}: {item['summary']}" for item in findings),
        title="发现",
        border_style="yellow",
    ))
    console.print("[bold]可处理动作：[/bold]")
    for index, action in enumerate(actions, 1):
        tag = " [推荐]" if action.get("recommended") else ""
        console.print(f"  {index}. {action['title']}{tag} — {action['summary']}")
    console.print("[dim]输入编号，支持逗号分隔多选；直接回车等于取消。[/dim]")

    while True:
        raw = prompt_cls.ask("选择动作", default="")
        if not raw:
            return []
        try:
            indexes = []
            for chunk in raw.split(","):
                value = int(chunk.strip())
                if not 1 <= value <= len(actions):
                    raise ValueError
                if value not in indexes:
                    indexes.append(value)
            return [actions[index - 1]["id"] for index in indexes]
        except ValueError:
            console.print(f"[red]请输入 1-{len(actions)} 的编号，可用逗号分隔多选[/red]")


def run_recovery_action(
    cfg,
    provider,
    probe,
    action_id,
    *,
    display_model_probe_details,
    setup_provider_credentials,
    select_provider_interactive,
    console,
):
    if action_id == "show_details":
        display_model_probe_details(probe)
        return provider, False
    if action_id == "edit_credentials":
        return setup_provider_credentials(
            provider,
            provider.get("base_url", ""),
            provider.get("api_key", ""),
            allow_keep=True,
        ), False
    if action_id == "switch_provider":
        selected = select_provider_interactive(cfg, provider.get("id"))
        return (selected or provider), False
    if action_id == "continue_without_validation":
        console.print("[yellow]已跳过模型校验。模型浏览将暂时不可用，但预设和直接 CLI 启动仍可继续。[/yellow]")
        return provider, True
    return provider, False


def ensure_models_ready(
    cfg,
    provider,
    *,
    probe_models_for_startup,
    stdin,
    console,
    config_command_hint,
    exit_func,
    model_validation_findings,
    build_model_recovery_actions,
    pick_recovery_actions,
    run_recovery_action,
    probe_cache,
    probe_file_cache_path,
    remove_file,
    probe_models,
    default_provider_id,
):
    probe = probe_models_for_startup(cfg, provider, emit_output=True)
    models = probe.get("models")
    if models:
        return provider, models

    if not stdin.isatty():
        console.print(f"[red]模型校验失败，请执行 {config_command_hint()} 后重试[/red]")
        exit_func(1)

    while True:
        findings = model_validation_findings(provider, probe)
        actions = build_model_recovery_actions(cfg, provider, probe)
        selected_ids = pick_recovery_actions(findings, actions)
        if not selected_ids:
            exit_func(1)
        ordered_actions = [item for item in actions if item["id"] in selected_ids]
        for action in ordered_actions:
            provider, skip_validation = run_recovery_action(cfg, provider, probe, action["id"])
            if skip_validation:
                return provider, []
            provider_id = provider.get("id", default_provider_id)
            probe_cache.pop(provider_id, None)
            try:
                remove_file(probe_file_cache_path(provider_id))
            except OSError:
                pass
            probe = probe_models(provider, emit_output=True)
            models = probe.get("models")
            if models:
                return provider, models


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
            (localize("生效方式", "applies"), "bridge failure -> latest-approved Router"),
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


def rescue_route_fallback_model_candidates(config_dir=None, *, failed_model="", limit=80, default_config_dir=""):
    failed = str(failed_model or "").strip().lower()
    root = os.path.expanduser(str(config_dir or default_config_dir))
    candidates = []
    seen = set()

    def route_is_openai_usable(route):
        if not isinstance(route, dict):
            return False
        return bool(str(route.get("openai_base_url") or "").strip() and str(route.get("api_key") or "").strip())

    def add_from_router_payload(payload):
        routes = payload.get("routes") if isinstance(payload.get("routes"), dict) else {}
        for model_name, entry in routes.items():
            name = str(model_name or "").strip()
            if not name or name.lower() == failed or name.lower() in seen:
                continue
            if not isinstance(entry, dict):
                continue
            leaves = [entry.get("primary")]
            if isinstance(entry.get("fallbacks"), list):
                leaves.extend(entry.get("fallbacks") or [])
            if not any(route_is_openai_usable(route) for route in leaves):
                continue
            seen.add(name.lower())
            candidates.append(name)

    manifest_path = os.path.join(root, "generated", "model-registry.latest-approved.json")
    if os.path.exists(manifest_path):
        try:
            import mms_registry

            payload = mms_registry.try_load_latest_approved_payload("router", config_dir=root, include_secret=True)
        except Exception:
            payload = {}
        if isinstance(payload, dict) and payload:
            add_from_router_payload(payload)
        return candidates[: max(1, int(limit or 1))]
    try:
        from mms_runtime.state_io import mms_config_root_status

        if mms_config_root_status(config_dir=root).get("mode") == "preview":
            return []
    except Exception:
        pass

    paths = [
        os.path.join(root, "generated", "model-routes.json"),
        os.path.join(root, "model-routes.json"),
    ]
    for path in paths:
        try:
            payload = json.loads(open(path, "r", encoding="utf-8").read())
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        add_from_router_payload(payload)
        if candidates:
            break
    return candidates[: max(1, int(limit or 1))]


def rescue_fallback_model_candidates(
    cfg,
    rescue_event,
    *,
    limit=6,
    load_usage_stats,
    rescue_route_fallback_model_candidates=rescue_route_fallback_model_candidates,
):
    failed_model = str((rescue_event or {}).get("failed_model") or "").strip().lower()
    rows = {}

    def add(model, *, last_used_at="", source_rank=1000):
        name = str(model or "").strip()
        if not name or name.lower() == failed_model:
            return
        key = name.lower()
        existing = rows.get(key)
        candidate = {
            "model": name,
            "last_used_at": str(last_used_at or "").strip(),
            "source_rank": int(source_rank),
        }
        if existing is None:
            rows[key] = candidate
            return
        existing_key = (str(existing.get("last_used_at") or ""), -int(existing.get("source_rank") or 0))
        candidate_key = (candidate["last_used_at"], -candidate["source_rank"])
        if candidate_key > existing_key:
            rows[key] = candidate

    stats = load_usage_stats()
    for item in (stats.get("last_by_cli") or {}).values():
        if not isinstance(item, dict):
            continue
        add(item.get("model"), last_used_at=item.get("last_used_at"), source_rank=0)
    for source in (stats.get("sources") or {}).values():
        if not isinstance(source, dict):
            continue
        model_last_used = source.get("model_last_used_at") if isinstance(source.get("model_last_used_at"), dict) else {}
        for model_name in (source.get("models") or {}).keys():
            add(model_name, last_used_at=model_last_used.get(model_name), source_rank=10)
        add(source.get("last_model"), last_used_at=source.get("last_used_at"), source_rank=5)

    rank = 100
    for provider_def in (cfg or {}).get("providers", []) or []:
        if not isinstance(provider_def, dict) or not provider_def.get("enabled", True):
            continue
        for field in ("extra_models", "fallback_models"):
            for model_name in provider_def.get(field) or []:
                add(model_name, source_rank=rank)
                rank += 1

    for model_name in rescue_route_fallback_model_candidates(failed_model=failed_model, limit=80):
        add(model_name, source_rank=rank)
        rank += 1

    values = list(rows.values())
    recent = sorted(
        [item for item in values if item.get("last_used_at")],
        key=lambda item: (str(item.get("last_used_at") or ""), -int(item.get("source_rank") or 0)),
        reverse=True,
    )
    cold = sorted(
        [item for item in values if not item.get("last_used_at")],
        key=lambda item: (int(item.get("source_rank") or 0), str(item.get("model") or "").lower()),
    )
    ordered = recent + cold
    return [item["model"] for item in ordered[: max(int(limit or 1), 1)]]


def rescue_default_fallback(cfg):
    rescue_cfg = cfg.get("rescue") if isinstance(cfg, dict) and isinstance(cfg.get("rescue"), dict) else {}
    return {
        "model": str(rescue_cfg.get("fallback_model") or rescue_cfg.get("default_fallback_model") or "").strip(),
        "cli": str(rescue_cfg.get("fallback_cli") or rescue_cfg.get("default_fallback_cli") or "").strip(),
    }


def rescue_hot_fallback_enabled_cfg(cfg, *, pref_bool=None):
    rescue_cfg = cfg.get("rescue") if isinstance(cfg, dict) and isinstance(cfg.get("rescue"), dict) else {}
    pref_bool_fn = pref_bool or _pref_bool
    return bool(pref_bool_fn(rescue_cfg.get("hot_fallback_enabled", rescue_cfg.get("enable_hot_fallback"))))


def set_rescue_default_fallback(cfg, *, model="", cli=""):
    cfg = cfg if isinstance(cfg, dict) else {}
    rescue_cfg = cfg.setdefault("rescue", {})
    model = str(model or "").strip()
    cli = str(cli or "").strip()
    for legacy_key in ("default_fallback_model", "default_fallback_cli"):
        rescue_cfg.pop(legacy_key, None)
    if model:
        rescue_cfg["fallback_model"] = model
        if cli:
            rescue_cfg["fallback_cli"] = cli
        else:
            rescue_cfg.pop("fallback_cli", None)
    else:
        rescue_cfg.pop("fallback_model", None)
        rescue_cfg.pop("fallback_cli", None)
        rescue_cfg.pop("hot_fallback_enabled", None)
        rescue_cfg.pop("enable_hot_fallback", None)
    return cfg


def set_rescue_hot_fallback_enabled(cfg, enabled=False):
    cfg = cfg if isinstance(cfg, dict) else {}
    rescue_cfg = cfg.setdefault("rescue", {})
    has_model = bool(str(rescue_cfg.get("fallback_model") or rescue_cfg.get("default_fallback_model") or "").strip())
    if not has_model:
        rescue_cfg.pop("hot_fallback_enabled", None)
        rescue_cfg.pop("enable_hot_fallback", None)
        return cfg, False
    rescue_cfg.pop("enable_hot_fallback", None)
    rescue_cfg["hot_fallback_enabled"] = bool(enabled)
    return cfg, bool(enabled)


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
