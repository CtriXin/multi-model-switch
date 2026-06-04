"""Session and resume command helpers with dependencies injected by core."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime


def resolve_model_name(model_info):
    if isinstance(model_info, dict):
        for key in ("model", "sonnet", "opus", "haiku"):
            value = model_info.get(key)
            if value:
                return str(value)
        return "official-default"
    return str(model_info or "official-default")


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


def session_gateway_roots(cli_name, *, real_home):
    gateway_names = []
    if cli_name in {"all", "claude"}:
        gateway_names.append(("claude", "claude-gateway"))
    if cli_name in {"all", "codex"}:
        gateway_names.append(("codex", "codex-gateway"))
    if cli_name in {"all", "opencode"}:
        gateway_names.append(("opencode", "opencode-gateway"))
    return [
        (cli, os.path.join(real_home, ".config", "mms", gateway_name, "s"))
        for cli, gateway_name in gateway_names
    ]


def session_dir_size_bytes(path):
    total = 0
    for root, _dirnames, filenames in os.walk(path):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            try:
                if os.path.islink(file_path):
                    continue
                total += os.path.getsize(file_path)
            except OSError:
                continue
    return total


def format_bytes(size):
    value = float(max(0, int(size or 0)))
    for unit in ("B", "K", "M", "G"):
        if value < 1024 or unit == "G":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}G"


def list_stale_gateway_sessions(
    cli_name,
    *,
    session_gateway_roots,
    session_home_is_active,
    session_dir_size_bytes,
):
    rows = []
    for cli, root in session_gateway_roots(cli_name):
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            session_home = os.path.join(root, name)
            if not os.path.isdir(session_home) or os.path.islink(session_home):
                continue
            if session_home_is_active(session_home):
                continue
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(session_home)).isoformat(timespec="seconds")
            except OSError:
                mtime = "-"
            rows.append(
                {
                    "cli": cli,
                    "name": name,
                    "path": session_home,
                    "size": session_dir_size_bytes(session_home),
                    "mtime": mtime,
                }
            )
    rows.sort(key=lambda item: (int(item.get("size") or 0), str(item.get("mtime") or "")), reverse=True)
    return rows


def split_cli_prefixed_resume_ref(session_ref):
    ref = str(session_ref or "").strip()
    if ":" not in ref:
        return "", ref
    prefix, rest = ref.split(":", 1)
    prefix = prefix.strip().lower()
    rest = rest.strip()
    if prefix in {"codex", "claude"} and rest:
        return prefix, rest
    return "", ref


def codex_resume_roots(env, *, real_home):
    roots = []

    def add(path):
        normalized = str(path or "").strip()
        if not normalized:
            return
        expanded = os.path.abspath(os.path.expanduser(normalized))
        if expanded not in roots:
            roots.append(expanded)

    for env_name in ("MMS_CODEX_RESUME_WRITEBACK_ROOT", "CODEX_HOME"):
        add(env.get(env_name))
    add(os.path.join(real_home, ".config", "mms", "codex-gateway", ".codex"))
    add(os.path.join(real_home, ".codex"))
    return roots


def iter_codex_index_records(roots):
    seen = set()
    for root in roots:
        path = os.path.join(root, "session_index.jsonl")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except Exception:
                        continue
                    session_id = str(item.get("id") or "").strip()
                    if not session_id or session_id in seen:
                        continue
                    seen.add(session_id)
                    payload = dict(item)
                    payload["_root"] = root
                    yield payload
        except OSError:
            continue


def resolve_codex_resume_ref(session_ref, *, iter_codex_index_records, allow_passthrough=False):
    ref = str(session_ref or "").strip()
    if not ref:
        return None, None, "session id 不能为空"
    records = list(iter_codex_index_records())
    exact = [item for item in records if str(item.get("id") or "").strip() == ref]
    if exact:
        return str(exact[0]["id"]), exact[0], None
    matches = [item for item in records if str(item.get("id") or "").strip().startswith(ref)]
    if len(matches) == 1:
        return str(matches[0]["id"]), matches[0], None
    if len(matches) > 1:
        return None, None, f"Codex session 前缀不唯一: {ref}"
    if allow_passthrough:
        return ref, {"id": ref, "_unindexed": True}, None
    return None, None, f"找不到 Codex session: {ref}"


def resolve_claude_resume_ref(session_ref, *, list_indexed_sessions, allow_passthrough=False):
    ref = str(session_ref or "").strip()
    if not ref:
        return None, None, "session id 不能为空"
    sessions = [
        item for item in list_indexed_sessions(cli_name="claude")
        if str(item.get("session_id") or "").strip()
    ]
    if ref.isdigit():
        index = int(ref)
        if 1 <= index <= len(sessions):
            item = sessions[index - 1]
            return str(item.get("session_id") or "").strip(), item, None
        return None, None, f"找不到第 {index} 条 Claude session"
    exact = [item for item in sessions if str(item.get("session_id") or "").strip() == ref]
    if exact:
        return str(exact[0].get("session_id") or "").strip(), exact[0], None
    matches = [item for item in sessions if str(item.get("session_id") or "").strip().startswith(ref)]
    if len(matches) == 1:
        return str(matches[0].get("session_id") or "").strip(), matches[0], None
    if len(matches) > 1:
        return None, None, f"Claude session 前缀不唯一: {ref}"
    if allow_passthrough:
        return ref, {"session_id": ref, "_unindexed": True}, None
    return None, None, f"找不到 Claude session: {ref}"


def resolve_resume_target(
    session_ref,
    cli_hint="auto",
    *,
    split_cli_prefixed_resume_ref=split_cli_prefixed_resume_ref,
    resolve_codex_resume_ref,
    resolve_claude_resume_ref,
    uuid_resume_cli_hint,
):
    prefix_cli, ref = split_cli_prefixed_resume_ref(session_ref)
    cli_hint = prefix_cli or str(cli_hint or "auto").strip().lower()
    if cli_hint not in {"auto", "codex", "claude"}:
        return None, None, None, f"不支持的 CLI: {cli_hint}"
    if cli_hint == "codex":
        session_id, record, error = resolve_codex_resume_ref(ref, allow_passthrough=True)
        return "codex", session_id, record, error
    if cli_hint == "claude":
        session_id, record, error = resolve_claude_resume_ref(ref, allow_passthrough=True)
        return "claude", session_id, record, error

    codex_id, codex_record, codex_error = resolve_codex_resume_ref(ref, allow_passthrough=False)
    claude_id, claude_record, claude_error = resolve_claude_resume_ref(ref)
    if codex_id and not claude_id:
        return "codex", codex_id, codex_record, None
    if claude_id and not codex_id:
        return "claude", claude_id, claude_record, None
    if codex_id and claude_id:
        return None, None, None, f"session id 同时匹配 Codex 和 Claude，请使用 codex:{ref} 或 claude:{ref}"
    uuid_cli = uuid_resume_cli_hint(ref)
    if uuid_cli == "codex":
        return "codex", ref, {"id": ref, "_unindexed": True}, None
    if uuid_cli == "claude":
        return "claude", ref, {"session_id": ref, "_unindexed": True}, None
    return None, None, None, codex_error or claude_error or f"找不到 session: {ref}"


def uuid_resume_cli_hint(session_ref):
    ref = str(session_ref or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", ref):
        return ""
    version = ref.split("-", 3)[2][:1]
    if version == "7":
        return "codex"
    if version == "4":
        return "claude"
    return ""


def resume_resolution_diagnostics(session_ref, cli_hint="auto", *, command_name="mms"):
    prefix_cli, ref = split_cli_prefixed_resume_ref(session_ref)
    effective_cli = prefix_cli or str(cli_hint or "auto").strip().lower() or "auto"
    ref_shape = "uuid" if uuid_resume_cli_hint(ref) else ("short-ref" if ref else "empty")
    suggestions = [
        "恢复失败诊断:",
        f"  ref: {ref or '-'}",
        f"  cli: {effective_cli}",
        f"  shape: {ref_shape}",
    ]
    if effective_cli == "auto":
        suggestions.extend([
            f"  try: {command_name} resume codex:{ref}",
            f"  try: {command_name} resume claude:{ref}",
        ])
    elif effective_cli in {"codex", "claude"}:
        suggestions.append(f"  try: {command_name} resume {effective_cli}:{ref}")
    suggestions.extend([
        f"  list Claude index: {command_name} session ls --cli claude",
        "  Codex index roots: MMS_CODEX_RESUME_WRITEBACK_ROOT, CODEX_HOME, ~/.config/mms/codex-gateway/.codex, ~/.codex",
    ])
    return "\n".join(suggestions)


def first_resume_model(cli_models, default_models, recommend=None):
    names = []
    for item in list(cli_models or []) + list(default_models or []):
        name = str(item.get("model") if isinstance(item, dict) else item or "").strip()
        if name and name not in names:
            names.append(name)
    for preferred in recommend or []:
        if preferred in names:
            return preferred
    return names[0] if names else ""


def session_resume_model(session_record):
    if not isinstance(session_record, dict):
        return ""
    for key in ("resume_model", "selected_model", "display_model", "model"):
        value = str(session_record.get(key) or "").strip()
        if value:
            return value
    return ""


def resolve_resume_runtime_and_model(
    cfg,
    cli,
    args,
    default_provider,
    default_models,
    session_record,
    *,
    get_scene_usage,
    session_resume_model=session_resume_model,
    resolve_last_used_runtime,
    trace_runtime_choice,
    choose_runtime_source,
    resolve_model_name=resolve_model_name,
    first_resume_model=first_resume_model,
    uses_managed_entry,
    runtime_with_launch_preferences,
):
    requested_model = str(args.model or "").strip()
    if requested_model:
        model_info = {"model": requested_model}
    elif cli == "claude" and session_resume_model(session_record):
        model_info = {"model": session_resume_model(session_record)}
    else:
        last_by_cli, _scene_counts = get_scene_usage()
        last_item = last_by_cli.get(cli)
        last_model_info = last_item.get("model_info") if isinstance(last_item, dict) else None
        model_info = last_model_info if isinstance(last_model_info, dict) else {}

    account_id = str(args.account or "").strip()
    provider_id = str(args.provider or "").strip()
    if cli == "claude" and not account_id and not provider_id and isinstance(session_record, dict):
        source_id = str(session_record.get("account_id") or "").strip()
        runtime_source_id = str(session_record.get("runtime_account_id") or "").strip()
        runtime_kind = str(session_record.get("runtime_kind") or "").strip()
        if runtime_kind == "api_key":
            provider_id = runtime_source_id or source_id
        elif source_id and runtime_kind == "oauth":
            account_id = source_id

    runtime = cli_models = launch_cli_name = None
    if not account_id and not provider_id:
        last_by_cli, _scene_counts = get_scene_usage()
        last_item = last_by_cli.get(cli)
        runtime, cli_models, choice = resolve_last_used_runtime(cfg, cli, last_item, default_models)
        if runtime is not None:
            launch_cli_name = cli
            trace_runtime_choice("runtime resolve", runtime, launch_cli=cli, choice=choice)
    if runtime is None:
        runtime, cli_models, launch_cli_name = choose_runtime_source(
            cfg,
            cli,
            default_provider,
            default_models,
            account_id=account_id or None,
            provider_id=provider_id or None,
            model_info=model_info or None,
            allow_selected_model_accounts=True,
        )

    if not isinstance(model_info, dict) or not resolve_model_name(model_info):
        model_name = first_resume_model(cli_models, default_models, cfg.get("recommend", {}).get("models", []))
        model_info = {"model": model_name} if model_name else {}
    if resolve_model_name(model_info) == "official-default" and not uses_managed_entry(runtime or {}, cli):
        model_name = first_resume_model(cli_models, default_models, cfg.get("recommend", {}).get("models", []))
        if model_name:
            model_info = {"model": model_name}
    runtime = runtime_with_launch_preferences(cfg, runtime, launch_cli_name or cli)
    return runtime, cli_models or [], launch_cli_name or cli, model_info


def handle_resume_command(
    argv,
    preloaded_command_cfg=None,
    bootstrap_cfg=None,
    lang_override=None,
    *,
    command_name,
    resolve_resume_target,
    load_config,
    setup_wizard,
    resolve_ui_language,
    apply_local_overrides,
    set_language,
    ensure_provider_credentials,
    ensure_models_ready,
    resolve_resume_runtime_and_model,
    launch_with_tracking,
    path_isdir=os.path.isdir,
    chdir=os.chdir,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} resume",
        description="通过 Codex/Claude session id 一键恢复 MMS 托管会话",
    )
    parser.add_argument("session_ref", help="session id、前缀，或 codex:<id> / claude:<id>")
    parser.add_argument("prompt", nargs="*", help="恢复后追加给 CLI 的可选 prompt；若 prompt 以 -- 开头请先写 --")
    parser.add_argument("--cli", choices=["auto", "codex", "claude"], default="auto", help="强制指定恢复目标 CLI")
    parser.add_argument("--provider", help="临时指定 provider")
    parser.add_argument("--account", help="临时指定官方账号档案")
    parser.add_argument("--model", help="临时指定恢复时使用的模型")
    parser.add_argument("--once", action="store_true", help="以一次性会话模式启动底层 CLI")
    args = parser.parse_intermixed_args(argv)

    if args.account and args.provider:
        parser.error("--account 和 --provider 不能同时使用")

    cli, session_id, session_record, error = resolve_resume_target(args.session_ref, args.cli)
    if error:
        console.print(f"[red]{error}[/red]")
        console.print(f"[dim]{resume_resolution_diagnostics(args.session_ref, args.cli, command_name=command_name)}[/dim]")
        raise SystemExit(1)
    if cli not in {"codex", "claude"} or not session_id:
        console.print(f"[red]无法识别 session: {args.session_ref}[/red]")
        console.print(f"[dim]{resume_resolution_diagnostics(args.session_ref, args.cli, command_name=command_name)}[/dim]")
        raise SystemExit(1)

    user_cfg = preloaded_command_cfg or bootstrap_cfg or load_config()
    if user_cfg is None:
        user_cfg = setup_wizard(resolve_ui_language(None, lang_override))
    cfg = apply_local_overrides(user_cfg)
    set_language(resolve_ui_language(cfg, lang_override))

    default_provider = ensure_provider_credentials(cfg)
    default_provider, models_cache = ensure_models_ready(cfg, default_provider)
    runtime, _cli_models, launch_cli_name, model_info = resolve_resume_runtime_and_model(
        cfg,
        cli,
        args,
        default_provider,
        models_cache,
        session_record,
    )
    if runtime is None:
        console.print(f"[red]{cli} 当前没有可用运行来源[/red]")
        raise SystemExit(1)
    if launch_cli_name != cli:
        console.print(f"[red]resume 只支持原 CLI 恢复，当前解析为 {launch_cli_name}[/red]")
        raise SystemExit(1)
    if cli == "claude":
        project_path = str((session_record or {}).get("project_path") or (session_record or {}).get("cwd") or "").strip()
        if project_path and path_isdir(project_path):
            chdir(project_path)
        extra_args = ["--resume", session_id] + list(args.prompt or [])
    else:
        extra_args = ["resume", session_id] + list(args.prompt or [])

    source = "未写入 MMS index，交给 Codex 原生 resume 校验" if (session_record or {}).get("_unindexed") else "MMS index"
    console.print(f"[cyan]恢复 {cli} session:[/cyan] {session_id}")
    console.print(f"[dim]来源: {source}[/dim]")
    launch_with_tracking(cli, model_info, runtime, once=bool(args.once), extra_args=extra_args)


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

