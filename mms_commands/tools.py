"""Small command handlers that are not part of the launcher runtime path."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

try:
    import tomllib
except ImportError:
    import tomli as tomllib


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


def normalize_ui_config(cfg, *, normalize_language, default_language="zh"):
    cfg = dict(cfg)
    raw_ui = cfg.get("ui")
    current = raw_ui if isinstance(raw_ui, dict) else {}
    lang = normalize_language(current.get("language", "")) or default_language
    new_cfg = dict(cfg)
    new_cfg["ui"] = {"language": lang}
    return new_cfg, new_cfg != cfg


def resolve_ui_language(
    cfg=None,
    cli_override=None,
    *,
    normalize_language,
    load_version_meta,
    environ=None,
    default_language="zh",
):
    environ = os.environ if environ is None else environ
    cli_lang = normalize_language(cli_override)
    if cli_lang:
        return cli_lang
    env_lang = normalize_language(environ.get("MMS_LANG", ""))
    if env_lang:
        return env_lang
    if isinstance(cfg, dict):
        ui_lang = normalize_language((cfg.get("ui") or {}).get("language", ""))
        if ui_lang:
            return ui_lang
    locale_lang = normalize_language(environ.get("LC_ALL", "") or environ.get("LANG", ""))
    if locale_lang:
        return locale_lang
    version_meta = load_version_meta()
    version_lang = normalize_language(
        version_meta.get("preferred_language", "") if isinstance(version_meta, dict) else ""
    )
    if version_lang:
        return version_lang
    return default_language


def extract_global_lang(argv, *, normalize_language):
    cleaned = []
    lang = ""
    idx = 0
    while idx < len(argv):
        item = argv[idx]
        if item == "--lang" and idx + 1 < len(argv):
            candidate = normalize_language(argv[idx + 1])
            if candidate:
                lang = candidate
                idx += 2
                continue
        cleaned.append(item)
        idx += 1
    return cleaned, lang


def current_command(*, primary_command, environ=None, argv0=None):
    environ = {} if environ is None else environ
    explicit = str(environ.get("MMS_COMMAND_NAME") or "").strip()
    invoked = os.path.basename(str(argv0 if argv0 is not None else (sys.argv[0] if sys.argv else ""))).strip()
    known_entrypoints = {"mms", "mmd", "mmf", "mmg", "mmm"}
    if explicit and (explicit in known_entrypoints or invoked == explicit):
        return explicit
    if invoked in known_entrypoints:
        return invoked
    return primary_command


def display_title(title="MMS", *, current_command_fn=None):
    if current_command_fn is not None and current_command_fn() == "mmf":
        return "MMF"
    return title


def normalize_config_sections(
    cfg,
    *,
    ensure_provider_config,
    ensure_account_config,
    ensure_broker_config,
    normalize_ui_config,
    normalize_presets_config,
    normalize_user_config,
    normalize_cache_config,
):
    cfg, _ = ensure_provider_config(cfg)
    cfg, _ = ensure_account_config(cfg)
    cfg, _ = ensure_broker_config(cfg)
    cfg, _ = normalize_ui_config(cfg)
    cfg, _ = normalize_presets_config(cfg)
    cfg, _ = normalize_user_config(cfg)
    cfg, _ = normalize_cache_config(cfg)
    return cfg


def load_runtime_config(*, load_config, apply_local_overrides):
    cfg = load_config()
    if cfg is None:
        return None
    return apply_local_overrides(cfg)


from mms_config.snapshot_guard import (
    config_write_target_path,
    config_lock_path,
    config_audit_path,
    config_backup_root,
    sha1_file,
    backup_config_file,
    append_config_audit_entry,
    atomic_write_toml,
    config_write_caller,
    locked_file_context,
    locked_config_write,
    locked_state_file,
    config_command_hint,
    export_command_hint,
    base_user_config_path_from_gateway,
    base_user_primary_dir_from_gateway,
    active_sibling_path_from_gateway,
    merge_base_user_broker_profiles,
    config_guard_root_dir,
    config_snapshot_root,
    config_snapshot_path,
    ensure_mms_config_guard_files,
    snapshot_proxy_fingerprint,
    is_snapshot_ignored_file,
    sha256_text,
    snapshot_cli_state,
    normalize_claude_state_snapshot_payload,
    normalize_claude_settings_snapshot_payload,
    snapshot_claude_identity_entry,
    snapshot_account_entry,
    snapshot_provider_entry,
    build_config_guard_snapshot,
    snapshot_file_content_bytes,
    snapshot_file_entry,
    snapshot_digest,
    load_json_snapshot,
    write_json_snapshot,
    snapshot_period_bucket,
    update_periodic_snapshot,
    snapshot_prompt_allowed,
    confirm_startup_snapshot_drift,
    ensure_startup_snapshot_guard,
)


from mms_config.preferences import (
    load_toml_file,
    existing_paths,
    load_user_preferences_from_paths,
    apply_local_overrides,
    preference_asset_root,
    merge_dicts,
    pref_bool,
    pref_enable_disable,
    pref_reasoning_effort,
    pref_caveman_level,
    pref_agent_pack,
    sanitize_surface_list,
    sanitize_disabled_session_surfaces,
    sanitize_launch_preferences,
    sanitize_asset_roots,
    sanitize_managed_assets_root,
    sanitize_disabled_clis,
    sanitize_user_preferences,
    managed_assets_enabled,
    managed_assets_root,
    preference_disabled_clis,
    disabled_clis_for_cfg,
    cli_disabled_by_preferences,
    merge_disabled_session_surfaces,
    preference_runtime_overlay,
    runtime_with_launch_preferences,
)


def iso_now(*, now_func=None):
    now = now_func() if now_func is not None else datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def local_now_slug(*, now_func=None):
    now = now_func() if now_func is not None else datetime.now()
    return now.strftime("%Y%m%d-%H%M%S")


def load_usage_stats_from_path(usage_path, *, path_exists=os.path.exists):
    if not path_exists(usage_path):
        return {"sources": {}}
    try:
        with open(usage_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            data.setdefault("sources", {})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"sources": {}}


def write_usage_stats_locked(
    usage_path,
    data,
    *,
    ensure_mms_config_guard_files,
    config_write_target_path,
    makedirs=os.makedirs,
    replace=os.replace,
    chmod=os.chmod,
):
    ensure_mms_config_guard_files(config_write_target_path())
    makedirs(os.path.dirname(usage_path), exist_ok=True)
    tmp_path = usage_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    replace(tmp_path, usage_path)
    chmod(usage_path, 0o600)


def load_usage_stats(*, active_usage_path, load_usage_stats_from_path):
    return load_usage_stats_from_path(active_usage_path())


def save_usage_stats(
    data,
    *,
    active_usage_path,
    locked_state_file,
    write_usage_stats_locked,
    trigger_routes_export_after_usage_write,
):
    usage_path = active_usage_path()
    with locked_state_file(usage_path):
        write_usage_stats_locked(usage_path, data)
    trigger_routes_export_after_usage_write()


def update_usage_stats(
    mutator,
    *,
    active_usage_path,
    locked_state_file,
    load_usage_stats_from_path,
    write_usage_stats_locked,
    trigger_routes_export_after_usage_write,
):
    usage_path = active_usage_path()
    with locked_state_file(usage_path):
        stats = load_usage_stats_from_path(usage_path)
        result = mutator(stats)
        write_usage_stats_locked(usage_path, stats)
    trigger_routes_export_after_usage_write()
    return result


def trigger_routes_export_after_usage_write(
    *,
    lock,
    is_running,
    set_running,
    get_last_started_at,
    set_last_started_at,
    min_interval_sec,
    refresh_routes_export_for_hive,
    thread_cls,
    monotonic,
):
    now = monotonic()
    with lock:
        if is_running():
            return
        if now - get_last_started_at() < min_interval_sec:
            return
        set_running(True)
        set_last_started_at(now)

    def _run():
        try:
            refresh_routes_export_for_hive(force=True, quiet=True)
        except Exception:
            pass
        finally:
            with lock:
                set_running(False)

    thread_cls(
        target=_run,
        daemon=True,
        name="mms-usage-routes-export",
    ).start()


def backup_config_tree(
    label,
    *,
    resolve_real_user_home,
    primary_config_dir,
    local_now_slug,
    makedirs=os.makedirs,
    path_exists=os.path.exists,
    copytree=shutil.copytree,
):
    backup_root = os.path.join(resolve_real_user_home(), ".config", "mms-backups")
    makedirs(backup_root, exist_ok=True)
    backup_dir = os.path.join(backup_root, f"{label}-{local_now_slug()}")
    makedirs(backup_dir, exist_ok=True)
    if path_exists(primary_config_dir):
        copytree(
            primary_config_dir,
            os.path.join(backup_dir, os.path.basename(primary_config_dir)),
            symlinks=True,
            ignore_dangling_symlinks=True,
        )
    return backup_dir


def refresh_routes_export_for_hive(
    cfg=None,
    *,
    force=True,
    quiet=False,
    startup_safe=False,
    load_config,
    apply_local_overrides,
    export_model_routes,
    console,
):
    try:
        current_cfg = cfg
        if current_cfg is None:
            current_cfg = load_config()
            if current_cfg is None:
                return False
            current_cfg = apply_local_overrides(current_cfg)
        export_model_routes(current_cfg, force=force, startup_safe=startup_safe)
        return True
    except Exception as exc:
        if not quiet:
            console.print(f"[yellow]⚠ Hive routes export 刷新失败: {exc}[/yellow]")
        return False


def trigger_routes_export_after_credentials_write(*, refresh_routes_export_for_hive):
    refresh_routes_export_for_hive(force=True, quiet=True)


def confirm_guard_accept_from_tui(
    cfg,
    *,
    config_write_target_path,
    build_config_guard_snapshot,
    config_snapshot_path,
    load_json_snapshot,
    snapshot_diff_lines,
    confirm_startup_snapshot_drift,
    console,
):
    config_path = config_write_target_path()
    current_snapshot = build_config_guard_snapshot(cfg, config_path=config_path)
    latest_path = config_snapshot_path("startup", "latest.json", config_path=config_path)
    accepted_path = config_snapshot_path("startup", "accepted.json", config_path=config_path)
    accepted_payload = load_json_snapshot(accepted_path) or {}
    accepted_snapshot = accepted_payload.get("snapshot") if isinstance(accepted_payload, dict) else None
    diff_lines = snapshot_diff_lines(accepted_snapshot, current_snapshot) if accepted_snapshot else []
    if not diff_lines:
        console.print("[green]当前快照没有 drift，不需要 accept。[/green]")
        return False
    return confirm_startup_snapshot_drift(
        diff_lines,
        accepted_path=accepted_path,
        latest_path=latest_path,
    )


def load_json_file(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else default
    except (OSError, json.JSONDecodeError):
        return default


def save_json_file(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.chmod(path, 0o600)


def record_trace_override(trace_enabled, trace_overrides, source, **kv):
    if not trace_enabled:
        return
    trace_overrides.append((source, {k: v for k, v in kv.items() if v is not None}))


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


def launch_with_tracking(
    cli_name,
    model_info,
    runtime,
    once=False,
    extra_args=None,
    *,
    runtime_with_launch_preferences,
    load_user_preferences,
    load_config,
    runtime_with_vision_sidecar,
    trace_enabled,
    print_trace,
    record_usage,
    console,
    resolve_model_name,
    run_broker_profile_interactive,
    launch_cli,
):
    runtime = runtime_with_launch_preferences(
        {"_mms_preferences": load_user_preferences()},
        runtime,
        cli_name,
    )
    if cli_name == "claude":
        runtime = runtime_with_vision_sidecar(load_config() or {}, runtime)
    if trace_enabled:
        print_trace(cli_name, model_info, runtime)
    record_usage(runtime, cli_name, model_info)
    if runtime and runtime.get("runtime_kind") == "broker" and cli_name == "claude":
        if extra_args:
            console.print("[red]broker profile 暂不支持 CLI resume 参数[/red]")
            raise SystemExit(1)
        model_override = resolve_model_name(model_info)
        if model_override == "official-default":
            model_override = runtime.get("remote_service_model", "")
        exit_code = run_broker_profile_interactive(
            load_config(),
            runtime.get("broker_profile_id", runtime.get("id", "")),
            model_override=model_override,
        )
        if exit_code != 0:
            raise SystemExit(exit_code)
        return
    launch_cli(cli_name, model_info, runtime, once=once, extra_args=extra_args)


from mms_commands.settings_report_handlers import (
    compact_tui_report_value,
    settings_result_tui_payload,
    settings_result_tui_available,
    select_settings_result_tui,
    print_settings_result_report,
    print_settings_error_report,
    pause_after_tui_report,
    display_settings_result_report,
    model_validation_findings,
    rank_recovery_actions,
    build_model_recovery_actions,
    display_model_probe_details,
    select_provider_interactive,
    pick_recovery_actions,
    run_recovery_action,
    ensure_models_ready,
    rescue_default_fallback_report_payload,
    rescue_hot_fallback_toggle_report_payload,
    rescue_route_fallback_model_candidates,
    rescue_fallback_model_candidates,
    rescue_default_fallback,
    rescue_hot_fallback_enabled_cfg,
    set_rescue_default_fallback,
    set_rescue_hot_fallback_enabled,
    rescue_demo_packet_report_payload,
    rescue_paths_report_payload,
    rescue_handover_report_payload,
    registry_source_staleness_report_payload,
    registry_refresh_sources_report_payload,
    registry_scheduled_refresh_report_payload,
    registry_openrouter_fetch_report_payload,
    registry_openrouter_diff_report_payload,
    registry_publish_approved_report_payload,
    registry_verify_approved_report_payload,
    registry_doctor_report_payload,
)


from mms_commands.about_handlers import (
    short_update_status_label,
    format_cli_about_line,
    format_about_latest_value,
    about_check_error_summary,
    mms_upgrade_shell_command,
    cli_upgrade_shell_command,
    run_about_upgrade,
    about_tui_payload,
    snapshot_guard_tui_payload,
    display_about_version_summary,
    parse_semver_tag,
    normalize_semver_tags,
    fetch_latest_semver_tags,
    fetch_latest_semver_tag,
    extract_semver_text,
    parse_semver_text,
    compare_semver_text,
    detect_cli_version,
    fetch_npm_package_latest_version,
    git_output,
    semver_tag_gap,
    installed_update_semver,
    update_notice,
    major_update_notice,
    start_async_update_check,
    mms_update_status,
    release_track_for_channel,
    release_version_info,
    cli_version_status,
    refresh_update_cache_for_about,
    about_status_snapshot,
)


def render_mms_config_agents_guard():
    return """# AGENTS.md

This folder stores the real MMS user config.

## MMS Config Human Gate

- Any agent, any repo, any automation touching this folder must stop and require human confirmation before write.
- Before every write, create a timestamped backup first. Never overwrite in place without a backup.
- Applies to the whole MMS config tree, including `config.toml`, `override.toml`, `credentials.sh`, `usage.json`, `accounts/**`, `env/**`, and any account state under this folder.
- Agents may inspect, diff, and propose changes, but must not auto-apply user config edits without human confirmation.
- Any proposed change must show target path, affected fields/files, before/after values, and reason.
- If the process is running inside an isolated HOME or gateway session, still resolve and protect the real user config under `~/.config/mms`.
"""


def render_mms_config_claude_guard():
    return """# CLAUDE.md

This folder stores the real MMS user config.

## Claude Hard Rule

- Claude must treat this folder as human-only config.
- Claude must never auto-write MMS user config without explicit human confirmation.
- Before every write, Claude must create a timestamped backup first.
- Claude may only inspect, explain, and generate manual diffs for changes to this folder until the human confirms.
- This applies to the full MMS config tree, including `config.toml`, `override.toml`, `credentials.sh`, `usage.json`, `accounts/**`, `env/**`, and account state files.
- If Claude is about to touch these files, it must stop and report the exact path, intended change, before/after values, and reason.
"""


from mms_commands.manage_handlers import (
    build_manage_targets,
    select_manage_target_fallback,
    select_manage_target,
    run_manage_channels,
    run_connect_wizard,
    manage_provider_target,
    prompt_account_rename,
    manage_account_target,
    run_account_mgmt_tui,
    run_recommend_mgmt_tui,
    format_rescue_hot_fallback_event,
    latest_rescue_hot_fallback_event,
    rescue_landing_tui_payload,
    registry_truth_tui_payload,
)


def model_source_label(source):
    mapping = {
        "remote": "远端列表",
        "fallback": "内置回退",
        "manual": "手工列表",
        "extra": "手工补充",
        "derived_alias": "本地别名",
    }
    return mapping.get(str(source or "").strip(), str(source or "-").strip() or "-")


def ttfb_label(ttfb_ms):
    if not isinstance(ttfb_ms, (int, float)):
        return "暂无数据"
    if ttfb_ms < 1200:
        return "很快"
    if ttfb_ms < 2500:
        return "正常"
    if ttfb_ms < 4500:
        return "偏慢"
    return "很慢"


def tps_label(tps_value):
    if not isinstance(tps_value, (int, float)):
        return "暂无数据"
    if tps_value >= 80:
        return "很快"
    if tps_value >= 40:
        return "正常"
    if tps_value >= 20:
        return "偏慢"
    return "很慢"


def provider_map(cfg):
    providers = cfg.get("providers", [])
    return {provider["id"]: provider for provider in providers if isinstance(provider, dict) and provider.get("id")}


def provider_label(provider, *, default_provider_id):
    return provider.get("name", provider.get("id", default_provider_id))


def provider_openai_base_url(provider):
    explicit = str(provider.get("openai_base_url", "")).strip().rstrip("/")
    if explicit:
        return explicit
    base_url = str(provider.get("base_url", "")).strip().rstrip("/")
    if not base_url:
        return ""
    if base_url.endswith("/v1"):
        return base_url
    return f"{base_url}/v1"


def provider_anthropic_base_url(provider):
    explicit = str(provider.get("anthropic_base_url", "")).strip().rstrip("/")
    if explicit:
        return explicit
    protocols = provider.get("protocols", [])
    if isinstance(protocols, str):
        protocols = [protocols]
    if "anthropic_messages" not in protocols:
        return ""
    return str(provider.get("base_url", "")).strip().rstrip("/")


def provider_has_configured_base_url(provider):
    return bool(
        provider_openai_base_url(provider)
        or provider_anthropic_base_url(provider)
        or str(provider.get("base_url", "")).strip().rstrip("/")
    )


def provider_id_variants(provider_id):
    raw = str(provider_id or "").strip()
    if not raw:
        return []
    variants = [raw]
    for candidate in (raw.replace("_", "-"), raw.replace("-", "_")):
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


def resolve_config_provider_id(provider_defs, provider_id):
    provider_defs = provider_defs or {}
    for candidate in provider_id_variants(provider_id):
        if candidate in provider_defs:
            return candidate
    return ""


def config_truthy(value, default=False):
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", "disable", "disabled"}


def provider_template_payload(template_key, *, provider_templates):
    template = provider_templates.get(template_key) or provider_templates["generic"]
    payload = {
        "id": template["id"],
        "name": template["name"],
        "protocols": list(template["protocols"]),
        "supported_clis": list(template["supported_clis"]),
        "enabled": True,
        "priority": template["priority"],
        "note": template["note"],
    }
    if "default_openai_base_url" in template:
        payload["default_openai_base_url"] = template["default_openai_base_url"]
    if "default_anthropic_base_url" in template:
        payload["default_anthropic_base_url"] = template["default_anthropic_base_url"]
    if "key_prefix" in template:
        payload["key_prefix"] = template["key_prefix"]
    if "fallback_models" in template:
        payload["fallback_models"] = list(template["fallback_models"])
    if "models_endpoint" in template:
        payload["models_endpoint"] = template["models_endpoint"]
    if "provider_profile" in template:
        payload["provider_profile"] = template["provider_profile"]
    if "extension" in template:
        payload["extension"] = template["extension"]
    if "capabilities" in template:
        payload["capabilities"] = dict(template["capabilities"])
    return payload


def select_provider_template(preset_id=None, *, console):
    if preset_id == "openrouter":
        return "openrouter"
    if preset_id and preset_id != "generic":
        console.print("[yellow]已统一收敛为“通用兼容网关”，将直接进入通用网关配置。[/yellow]")
    return "generic"


def ensure_interactive_terminal(
    action_hint,
    *,
    stdin,
    ensure_rich,
    console,
    current_command,
    exit_func=sys.exit,
):
    if stdin.isatty():
        ensure_rich()
        return
    console.print(
        f"[red]当前不是交互终端，无法执行 {action_hint}，请在终端里运行 {current_command()}[/red]"
    )
    exit_func(1)


def parse_csv_values(raw_value, allowed_values=None, *, console=None):
    values = []
    for chunk in str(raw_value or "").split(","):
        item = chunk.strip()
        if item and item not in values:
            values.append(item)
    if allowed_values is None:
        return values
    invalid = [item for item in values if item not in allowed_values]
    if invalid:
        if console is not None:
            console.print(f"[red]不支持的值: {', '.join(invalid)}[/red]")
            console.print(f"[dim]可选值: {', '.join(allowed_values)}[/dim]")
        sys.exit(1)
    return values


def prompt_csv_values(
    label,
    default_values,
    allowed_values,
    *,
    ensure_rich,
    prompt_ask,
    parse_csv_values,
    console,
    exit_func=sys.exit,
):
    ensure_rich()
    default_text = ",".join(default_values)
    raw_value = prompt_ask(label, default=default_text)
    values = parse_csv_values(raw_value, allowed_values=allowed_values)
    if not values:
        console.print(f"[red]{label} 不能为空[/red]")
        exit_func(1)
    return values


def prompt_provider_metadata(
    existing=None,
    preset_id=None,
    *,
    ensure_interactive_terminal,
    normalize_provider,
    default_provider_id,
    default_provider_protocols,
    provider_capable_clis,
    prompt_ask,
    prompt_csv_values,
    confirm_ask,
    normalize_models_endpoint,
    normalize_priority,
    default_priority,
    normalize_claude_1m_mode,
    prompt_validated_proxy_fields,
    default_account_timezone,
    prompt_validated_timezone,
):
    ensure_interactive_terminal("模型源配置编辑")
    current = normalize_provider(existing or {})
    provider_id = preset_id or current.get("id") or default_provider_id
    if not preset_id:
        provider_id = prompt_ask("系统内部标识（高级）", default=provider_id).strip() or default_provider_id
    name = prompt_ask("显示名称 / 列表展示名", default=current.get("name") or provider_id).strip() or provider_id
    protocols = prompt_csv_values(
        "协议（逗号分隔）",
        current.get("protocols", list(default_provider_protocols)),
        list(default_provider_protocols),
    )
    supported_clis = prompt_csv_values(
        "支持的 CLI（逗号分隔）",
        current.get("supported_clis", list(provider_capable_clis)),
        list(provider_capable_clis),
    )
    use_custom_models_endpoint = confirm_ask(
        "模型列表地址与接口地址不同？（高级）",
        default=current.get("models_endpoint", "/models") != "/models",
    )
    models_endpoint = "/models"
    if use_custom_models_endpoint:
        models_endpoint = normalize_models_endpoint(
            prompt_ask("模型列表地址（高级；仅用于拉取模型列表，输入 manual 表示完全手工维护模型）", default=current.get("models_endpoint", "/models"))
        )
    priority = normalize_priority(prompt_ask("优先级（数字越大越优先）", default=str(current.get("priority", default_priority))))
    claude_1m_mode = normalize_claude_1m_mode(
        prompt_ask(
            "Claude 1M 策略（auto/enable/disable）",
            choices=["auto", "enable", "disable"],
            default=current.get("claude_1m_mode", "auto"),
        )
    )
    proxy, no_proxy = prompt_validated_proxy_fields(
        current.get("proxy", ""),
        current.get("no_proxy", ""),
        wizard=False,
    )
    timezone_name = prompt_validated_timezone(current.get("timezone") or default_account_timezone, wizard=False)
    note = prompt_ask("备注（可选）", default=current.get("note", "")).strip()
    enabled = confirm_ask("启用这个模型源？", default=bool(current.get("enabled", True)))
    return normalize_provider({
        "id": provider_id,
        "name": name,
        "protocols": protocols,
        "supported_clis": supported_clis,
        "models_endpoint": models_endpoint,
        "priority": priority,
        "claude_1m_mode": claude_1m_mode,
        "proxy": proxy,
        "no_proxy": no_proxy,
        "timezone": timezone_name,
        "note": note,
        "enabled": enabled,
    })


def prompt_account_metadata(
    existing=None,
    preset_id=None,
    preset_cli=None,
    *,
    ensure_interactive_terminal,
    normalize_account,
    normalize_account_id,
    default_account_home,
    managed_oauth_clis,
    prompt_ask,
    confirm_ask,
    normalize_priority,
    default_priority,
    normalize_claude_1m_mode,
    prompt_validated_proxy_fields,
    default_account_timezone,
    prompt_validated_timezone,
):
    ensure_interactive_terminal("账号档案配置编辑")
    current = normalize_account(existing or {"cli": preset_cli or "claude", "id": preset_id or ""})
    account_id = preset_id or current.get("id") or "claude-main"
    if not preset_id:
        account_id = normalize_account_id(prompt_ask("文件夹名（用于目录和命令）", default=account_id))
    cli_name = preset_cli or current.get("cli", "claude")
    if not preset_cli:
        if cli_name not in managed_oauth_clis:
            cli_name = managed_oauth_clis[0]
        cli_name = prompt_ask("绑定的 CLI", choices=list(managed_oauth_clis), default=cli_name)
    name = prompt_ask("显示名 / 列表展示名", default=current.get("name") or account_id).strip() or account_id
    home_dir = current.get("home_dir") or default_account_home(account_id)
    priority = normalize_priority(prompt_ask("优先级（数字越大越优先）", default=str(current.get("priority", default_priority))))
    claude_1m_mode = normalize_claude_1m_mode(
        prompt_ask(
            "Claude 1M 策略（auto/enable/disable）",
            choices=["auto", "enable", "disable"],
            default=current.get("claude_1m_mode", "auto"),
        )
    )
    proxy, no_proxy = prompt_validated_proxy_fields(
        current.get("proxy", ""),
        current.get("no_proxy", ""),
        wizard=False,
    )
    timezone_name = prompt_validated_timezone(current.get("timezone") or default_account_timezone, wizard=False)
    note = prompt_ask("备注（可选）", default=current.get("note", "")).strip()
    enabled = confirm_ask("启用这个账号档案？", default=bool(current.get("enabled", True)))
    return normalize_account({
        "id": account_id,
        "name": name,
        "cli": cli_name,
        "home_dir": home_dir,
        "priority": priority,
        "claude_1m_mode": claude_1m_mode,
        "proxy": proxy,
        "no_proxy": no_proxy,
        "timezone": timezone_name,
        "note": note,
        "enabled": enabled,
    })


def usage_rows_for_runtime(runtime_kind, runtime_id, *, load_usage_stats):
    stats = load_usage_stats()
    rows = []
    for item in stats.get("sources", {}).values():
        if item.get("runtime_kind") == runtime_kind and item.get("id") == runtime_id:
            rows.append(item)
    rows.sort(key=lambda item: (item.get("last_used_at", ""), item.get("launches", 0)), reverse=True)
    return rows


def usage_summary_for_runtime(runtime_kind, runtime_id, *, usage_rows_for_runtime):
    rows = usage_rows_for_runtime(runtime_kind, runtime_id)
    launches = sum(int(item.get("launches", 0)) for item in rows)
    last_used_at = rows[0].get("last_used_at", "") if rows else ""
    return launches, last_used_at


def infer_model_family(model_name, *, model_families):
    raw = str(model_name or "").strip().lower()
    parts = raw.rsplit("/", 1)
    candidates = [raw] if len(parts) == 1 else [raw, parts[-1]]
    for entry in model_families:
        for candidate in candidates:
            if any(kw in candidate for kw in entry["keywords"]):
                return entry["family"], entry["category"]
    return "其他", "其他"


def model_info_looks_domestic(model_info, *, infer_model_family, domestic_model_families, domestic_model_keywords):
    values = []
    if isinstance(model_info, dict):
        primary = str(model_info.get("model") or "").strip()
        if primary:
            values.append(primary)
        values.extend(
            str(value or "").strip()
            for key, value in model_info.items()
            if key not in {"subagent", "model"} and str(value or "").strip()
        )
    else:
        values.append(str(model_info or "").strip())

    for value in values:
        lower = value.lower()
        family, _ = infer_model_family(value)
        if family in domestic_model_families:
            return True
        if any(keyword in lower for keyword in domestic_model_keywords):
            return True
    return False


def mms_model_visible(model_name, *, infer_model_family, hidden_models, hidden_model_families):
    normalized = str(model_name or "").strip()
    if not normalized:
        return True
    if normalized.lower() in hidden_models:
        return False
    family, _ = infer_model_family(normalized)
    return family not in hidden_model_families


def filter_visible_models(models, *, mms_model_visible):
    return [
        str(model_name).strip()
        for model_name in (models or [])
        if str(model_name or "").strip() and mms_model_visible(model_name)
    ]


def model_info_has_visible_models(model_info, *, mms_model_visible):
    if isinstance(model_info, str):
        return mms_model_visible(model_info)
    if not isinstance(model_info, dict):
        return True
    model_like_keys = ("model", "opus", "sonnet", "haiku", "subagent")
    found_model = False
    for key in model_like_keys:
        value = str(model_info.get(key) or "").strip()
        if not value:
            continue
        found_model = True
        if mms_model_visible(value):
            return True
    return not found_model


def vision_sidecar_model_candidates_for_provider(provider_id):
    normalized = str(provider_id or "").strip().lower()
    generic = [
        "mimo-v2.5",
        "mimo-v2-omni",
        "K2.6",
        "K2.6-code-preview",
        "kimi-k2.5",
        "qwen3.6-flash",
        "qwen3.6-plus",
    ]
    if "mimo" in normalized:
        return ["mimo-v2.5", "mimo-v2-omni"]
    if "kimi" in normalized:
        return ["K2.6", "K2.6-code-preview", "kimi-k2.5"]
    if "qwen" in normalized:
        return ["qwen3.6-plus", "qwen3.6-flash"]
    return generic


def vision_sidecar_candidate_pairs(raw, provider_ids, *, explicit_model="", explicit_provider_id=""):
    configured = (raw.get("candidates") or raw.get("routes")) if isinstance(raw, dict) else None
    pairs = []

    def _append(provider_id, model):
        provider_id = str(provider_id or "").strip()
        model = str(model or "").strip()
        if provider_id and model and (provider_id, model) not in pairs:
            pairs.append((provider_id, model))

    if isinstance(configured, list):
        for item in configured:
            if not isinstance(item, dict):
                continue
            provider_id = item.get("provider_id") or item.get("provider")
            model = item.get("model") or item.get("vision_model")
            _append(provider_id, model)

    if explicit_model:
        for provider_id in provider_ids:
            _append(provider_id, explicit_model)
        return pairs

    if explicit_provider_id:
        for model in vision_sidecar_model_candidates_for_provider(explicit_provider_id):
            _append(explicit_provider_id, model)
        return pairs

    preferred_pairs = [
        ("mimo-direct-anthropic", "mimo-v2.5"),
        ("direct-mimo", "mimo-v2.5"),
        ("direct-kimi", "K2.6"),
        ("newapi-personal-kimi", "K2.6-code-preview"),
        ("newapi-personal-kimi", "kimi-k2.5"),
        ("direct-qwen", "qwen3.6-plus"),
        ("newapi-personal-qwen", "qwen3.6-plus"),
        ("newapi-personal-tokyo", "K2.6"),
        ("xin", "K2.6"),
    ]
    for provider_id, model in preferred_pairs:
        _append(provider_id, model)
    for provider_id in provider_ids:
        for model in vision_sidecar_model_candidates_for_provider(provider_id):
            _append(provider_id, model)
    return pairs


def runtime_with_vision_sidecar(
    cfg,
    runtime,
    *,
    config_truthy,
    provider_map,
    resolve_config_provider_id,
    vision_sidecar_candidate_pairs=vision_sidecar_candidate_pairs,
    resolve_provider_context,
    provider_anthropic_base_url,
    load_probe_file_cache,
    provider_effective_models,
    environ=None,
):
    if not isinstance(runtime, dict) or runtime.get("vision_sidecar"):
        return runtime
    raw = cfg.get("vision_sidecar") if isinstance(cfg, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    if raw and not config_truthy(raw.get("enabled"), default=True):
        return runtime

    environ = os.environ if environ is None else environ
    explicit_model = str(
        environ.get("MMS_VISION_SIDECAR_MODEL")
        or raw.get("model")
        or raw.get("vision_model")
        or ""
    ).strip()
    explicit_provider_id = str(
        environ.get("MMS_VISION_SIDECAR_PROVIDER")
        or raw.get("provider_id")
        or raw.get("provider")
        or ""
    ).strip()
    preferred_ids = (
        [explicit_provider_id]
        if explicit_provider_id
        else [
            "mimo-direct-anthropic",
            "direct-mimo",
            "direct-kimi",
            "newapi-personal-kimi",
            "newapi-personal-tokyo",
            "xin",
        ]
    )
    providers = cfg.get("providers", []) if isinstance(cfg, dict) else []
    provider_defs = provider_map(cfg) if isinstance(cfg, dict) else {}
    explicit_provider_id = resolve_config_provider_id(provider_defs, explicit_provider_id)
    all_ids = [
        str(item.get("id") or "").strip()
        for item in providers
        if isinstance(item, dict) and item.get("id")
    ]
    candidate_ids = []
    for provider_id in preferred_ids + all_ids:
        if provider_id and provider_id not in candidate_ids:
            candidate_ids.append(provider_id)

    for provider_id, model in vision_sidecar_candidate_pairs(
        raw,
        candidate_ids,
        explicit_model=explicit_model,
        explicit_provider_id=explicit_provider_id,
    ):
        if provider_id not in provider_defs:
            continue
        try:
            provider = resolve_provider_context(cfg, provider_id)
        except Exception:
            continue
        if not provider or not provider.get("enabled", True):
            continue
        api_key = str(provider.get("api_key") or provider.get("openai_api_key") or "").strip()
        anthropic_url = provider_anthropic_base_url(provider)
        if not api_key or not anthropic_url:
            continue
        if not explicit_provider_id:
            try:
                cached = load_probe_file_cache(provider_id, allow_stale=True)
                cached_models = (cached or {}).get("raw_models") or (cached or {}).get("models")
                models = provider_effective_models(provider, cached_models, cfg)
            except Exception:
                models = []
            model_l = model.lower()
            if models and model_l not in {str(item or "").strip().lower() for item in models}:
                continue
        updated = dict(runtime)
        updated["vision_sidecar"] = {
            "enabled": True,
            "provider_id": provider_id,
            "provider_profile": str(provider.get("profile") or provider.get("provider_profile") or ""),
            "model": model,
            "anthropic_base_url": anthropic_url,
            "api_key": api_key,
            "proxy_url": str(provider.get("proxy") or "").strip(),
            "no_proxy": str(provider.get("no_proxy") or "").strip(),
        }
        return updated
    return runtime


def native_clis_for_model(model_name):
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return []
    if normalized.startswith("claude-"):
        return ["claude"]
    if normalized.startswith(("gpt-", "o1-", "o3-", "o4-", "codex-")):
        return ["codex"]
    return []


def model_context_window(
    model_name,
    *,
    resolve_model_capabilities,
    model_context_windows,
):
    clean = str(model_name or "").replace("[1m]", "").strip()
    if not clean:
        return None
    try:
        caps = resolve_model_capabilities(clean)
        if caps.get("sources", {}).get("context_window_tokens") in {"approved_facts", "model_policy", "manual_override"}:
            window = int(caps.get("context_window_tokens"))
            if window > 0:
                return window
    except Exception:
        pass
    try:
        windows = model_context_windows()
    except Exception:
        return None
    window = windows.get(clean)
    if window is not None:
        return window
    lower = clean.lower()
    for key, value in windows.items():
        if key.lower() == lower:
            return value
    return None


def model_matches_account_cli(cli_name, model_name):
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return False
    if cli_name == "claude":
        return normalized.startswith("claude-")
    if cli_name == "codex":
        return normalized.startswith(("gpt-", "o1-", "o3-", "o4-", "codex-"))
    if cli_name == "gemini":
        return normalized.startswith("gemini-")
    return False


def model_matches_cli_family(cli_name, model_name, *, cli_model_family_hints):
    hints = cli_model_family_hints.get(cli_name, ())
    normalized = str(model_name or "").lower()
    return any(hint in normalized for hint in hints)


def models_for_cli_family(
    cli_name,
    models,
    *,
    cli_model_family_hints,
    model_matches_cli_family=model_matches_cli_family,
):
    if cli_name not in cli_model_family_hints:
        return list(models or [])
    return [
        model_name
        for model_name in (models or [])
        if model_matches_cli_family(cli_name, model_name, cli_model_family_hints=cli_model_family_hints)
    ]


def provider_models_for_cli(
    cli_name,
    models,
    *,
    cli_model_family_hints,
    provider=None,
    pi_model_available_for_runtime=None,
):
    if cli_name in cli_model_family_hints:
        result = models_for_cli_family(cli_name, models, cli_model_family_hints=cli_model_family_hints)
    else:
        result = list(models or [])
    if cli_name == "pi" and isinstance(provider, dict) and callable(pi_model_available_for_runtime):
        result = [model_name for model_name in result if pi_model_available_for_runtime(provider, model_name)]
    return result


def provider_supports_cli_name(provider, cli_name):
    provider_id = str(provider.get("id", "")).strip().lower()
    cli_name = str(cli_name or "").strip().lower()
    if cli_name == "agy":
        return False
    if cli_name == "codex" and provider_id.startswith("kimi"):
        return False
    supported_clis = provider.get("supported_clis", [])
    if isinstance(supported_clis, str):
        supported_clis = [supported_clis]
    supported_clis = [str(item or "").strip().lower() for item in supported_clis]
    protocols = provider.get("protocols", [])
    if isinstance(protocols, str):
        protocols = [protocols]
    protocols = [str(item or "").strip() for item in protocols]
    if cli_name == "pi" and "pi" not in supported_clis:
        if "openai_chat_completions" in protocols and any(
            item in supported_clis for item in ("codex", "opencode", "claude")
        ):
            return True
        if "anthropic_messages" in protocols and "claude" in supported_clis:
            return True
    if cli_name == "opencode" and "opencode" not in supported_clis:
        if "openai_chat_completions" in protocols and any(
            item in supported_clis for item in ("codex", "claude")
        ):
            return True
        if "anthropic_messages" in protocols and "claude" in supported_clis:
            return True
    return cli_name in supported_clis


def provider_supports_model_for_cli(
    provider,
    cli_name,
    model_name=None,
    *,
    model_matches_account_cli,
    provider_supports_cli_name,
    bridge_clis_for_model,
    pi_model_available_for_runtime=None,
):
    normalized_model = str(model_name or "").strip()
    if cli_name == "pi" and normalized_model and callable(pi_model_available_for_runtime):
        if not pi_model_available_for_runtime(provider, normalized_model):
            return False
    if cli_name == "claude" and normalized_model:
        if model_matches_account_cli("claude", normalized_model):
            return provider_supports_cli_name(provider, "claude")
        bridge_clis = bridge_clis_for_model(normalized_model)
        return cli_name in bridge_clis and provider_supports_cli_name(provider, cli_name)

    if provider_supports_cli_name(provider, cli_name):
        return True
    if not normalized_model:
        return False
    return False


def probe_file_cache_path(provider_id, *, probe_file_cache_dir):
    return os.path.join(probe_file_cache_dir, f"models_{provider_id}.json")


def invalidate_probe_cache(
    provider_id,
    *,
    probe_cache,
    probe_file_cache_path,
    path_exists=os.path.exists,
    remove=os.remove,
):
    probe_cache.pop(provider_id, None)
    path = probe_file_cache_path(provider_id)
    if path_exists(path):
        try:
            remove(path)
        except OSError:
            pass


def probe_cache_age(
    provider_id,
    *,
    probe_file_cache_path,
    path_exists=os.path.exists,
    getmtime=os.path.getmtime,
    time_func=None,
):
    path = probe_file_cache_path(provider_id)
    if not path_exists(path):
        return None
    try:
        if time_func is None:
            import time as _time

            time_func = _time.time
        return max(0.0, time_func() - getmtime(path))
    except OSError:
        return None


def load_probe_file_cache(
    provider_id,
    allow_stale=False,
    *,
    probe_file_cache_path,
    normalize_model_id_list,
    file_cache_ttl,
    negative_ttl,
    path_exists=os.path.exists,
    getmtime=os.path.getmtime,
    time_func=None,
):
    """Read provider model probe cache without owning global MMS paths."""
    path = probe_file_cache_path(provider_id)
    try:
        if time_func is None:
            import time as _time

            time_func = _time.time
        if not path_exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        raw_models = normalize_model_id_list(data.get("raw_models") or data.get("models") or [])
        error_kind = data.get("error_kind")
        ttl = negative_ttl if error_kind or not raw_models else file_cache_ttl
        age = time_func() - getmtime(path)
        is_stale = age > ttl
        if is_stale and not allow_stale:
            return None
        normalized = dict(data)
        normalized["raw_models"] = raw_models
        normalized["models"] = list(raw_models)
        normalized.setdefault("base_source", "remote")
        normalized.setdefault("error", None)
        normalized.setdefault("error_kind", None)
        normalized.setdefault("details", [])
        normalized["is_stale"] = is_stale
        return normalized
    except Exception:
        pass
    return None


def save_probe_file_cache(
    provider_id,
    result,
    *,
    probe_file_cache_dir,
    probe_file_cache_path,
    makedirs=os.makedirs,
):
    base_source = result.get("base_source")
    if base_source not in {"remote", "fallback", "manual"}:
        return
    try:
        makedirs(probe_file_cache_dir, exist_ok=True)
        path = probe_file_cache_path(provider_id)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "raw_models": result.get("raw_models") or [],
                    "working_url": result.get("working_url"),
                    "base_source": base_source or "remote",
                    "error": result.get("error"),
                    "error_kind": result.get("error_kind"),
                },
                handle,
            )
    except Exception:
        pass


def base_probe_result_from_cache(provider_id, file_cached):
    return {
        "provider_id": provider_id,
        "raw_models": list(file_cached["raw_models"]),
        "models": list(file_cached["raw_models"]),
        "error": file_cached.get("error"),
        "error_kind": file_cached.get("error_kind"),
        "working_url": file_cached.get("working_url"),
        "details": list(file_cached.get("details") or []),
        "base_source": file_cached.get("base_source", "remote"),
        "is_stale": bool(file_cached.get("is_stale")),
    }


def probe_models(
    provider,
    *,
    emit_output=True,
    force_refresh=False,
    skip_cache=False,
    default_provider_id,
    probe_cache,
    probe_cache_ttl,
    invalidate_probe_cache,
    load_probe_file_cache,
    base_probe_result_from_cache,
    apply_provider_model_patch,
    provider_openai_base_url,
    ensure_httpx,
    get_httpx,
    runtime_httpx_request,
    save_probe_file_cache,
    provider_label,
    console,
    time_func,
):
    provider_id = provider.get("id", default_provider_id)
    if force_refresh:
        invalidate_probe_cache(provider_id)

    if not skip_cache:
        cached = probe_cache.get(provider_id)
        if cached:
            cached_at, cached_result = cached
            if time_func() - cached_at < probe_cache_ttl:
                patched_cached = apply_provider_model_patch(provider, cached_result)
                if emit_output and cached_result.get("error"):
                    style = "yellow" if cached_result.get("error_kind") == "protocol_unsupported" else "red"
                    console.print(f"[{style}]{cached_result['error']}[/{style}]")
                return patched_cached

        file_cached = load_probe_file_cache(provider_id)
        if file_cached:
            base_result = base_probe_result_from_cache(provider_id, file_cached)
            probe_cache[provider_id] = (time_func(), base_result)
            return apply_provider_model_patch(provider, base_result)

    protocols = provider.get("protocols", [])
    base_url = provider_openai_base_url(provider)
    api_key = provider.get("api_key", "")
    result = {
        "provider_id": provider_id,
        "models": None,
        "raw_models": None,
        "error": None,
        "error_kind": None,
        "working_url": None,
        "details": [],
        "base_source": "remote",
    }

    ensure_httpx()
    if "openai_chat_completions" not in protocols:
        result["error_kind"] = "protocol_unsupported"
        models_endpoint = provider.get("models_endpoint", "/models")
        result["error"] = f"provider '{provider_id}' 未声明 openai_chat_completions，无法探测 {models_endpoint}"
    elif get_httpx() is None:
        result["error_kind"] = "missing_httpx"
        result["error"] = "缺少 httpx，请执行: pip install httpx"
    elif not base_url and not api_key:
        result["error_kind"] = "missing_credentials"
        result["error"] = "当前 provider 还没有配置 API 地址和 API Key"
    elif not base_url:
        result["error_kind"] = "missing_base_url"
        result["error"] = "当前 provider 缺少 API 地址"
    elif not api_key:
        result["error_kind"] = "missing_api_key"
        result["error"] = "当前 provider 缺少 API Key"
    else:
        alt_url = base_url[:-3] if base_url.endswith("/v1") else f"{base_url}/v1"
        last_exc = None
        models_endpoint = provider.get("models_endpoint", "/models")
        if models_endpoint == "manual":
            fallback = provider.get("fallback_models") or []
            result["raw_models"] = list(fallback)
            result["models"] = list(fallback)
            result["working_url"] = base_url
            result["error"] = None
            result["error_kind"] = None
            result["base_source"] = "manual"
            if emit_output:
                console.print("[dim]已跳过远端 /models 探测，直接使用手工模型列表[/dim]")
        else:
            if not models_endpoint.startswith("/"):
                models_endpoint = "/" + models_endpoint
            for try_url in [base_url, alt_url]:
                try:
                    if "{key}" in models_endpoint:
                        endpoint_url = models_endpoint.replace("{key}", api_key)
                    elif "?" in models_endpoint:
                        endpoint_url = f"{models_endpoint}&key={api_key}"
                    else:
                        endpoint_url = models_endpoint
                    full_url = f"{try_url}{endpoint_url}"
                    headers = {}
                    if "/api/models/info" not in models_endpoint:
                        headers["Authorization"] = f"Bearer {api_key}"
                    response = runtime_httpx_request(
                        "GET",
                        full_url,
                        runtime=provider,
                        headers=headers,
                        timeout=15,
                    )
                    response.raise_for_status()
                    data = response.json()
                    models = [m["id"] for m in data.get("data", [])]
                    models.sort()
                    result["raw_models"] = models
                    result["models"] = models
                    result["working_url"] = try_url
                    if try_url != base_url and emit_output:
                        console.print(f"[yellow]⚠ 地址 {base_url} 不通，已自动用 {try_url} 连接成功[/yellow]")
                    if not models:
                        continue
                    break
                except Exception as exc:
                    last_exc = exc
            if result["models"] is not None and not result["models"]:
                result["error_kind"] = "empty_models"
                result["error"] = "接口返回成功，但模型列表为空"
            elif result["models"] is None and last_exc is not None:
                fallback = provider.get("fallback_models")
                if fallback:
                    result["raw_models"] = list(fallback)
                    result["models"] = list(fallback)
                    result["working_url"] = base_url
                    result["error"] = None
                    result["error_kind"] = None
                    result["base_source"] = "fallback"
                    if emit_output:
                        console.print(f"[dim]该来源不支持 /models 端点，使用内置模型列表 ({len(fallback)} 个模型)[/dim]")
                else:
                    result["error_kind"] = "request_failed"
                    result["error"] = f"拉取模型列表失败: {last_exc}"

    details = [
        f"provider: {provider_label(provider)} ({provider_id})",
        f"openai_base_url: {base_url or '(未设置)'}",
        f"protocols: {', '.join(protocols) if protocols else '(未声明)'}",
    ]
    if result["error"]:
        details.append(f"error: {result['error']}")
    result["details"] = details

    if emit_output and result["error"]:
        style = "yellow" if result["error_kind"] == "protocol_unsupported" else "red"
        console.print(f"[{style}]{result['error']}[/{style}]")

    probe_cache[provider_id] = (time_func(), result)
    save_probe_file_cache(provider_id, result)
    return apply_provider_model_patch(provider, result)


def probe_models_for_startup(
    cfg,
    provider,
    *,
    emit_output=True,
    default_provider_id,
    probe_cache,
    probe_cache_ttl,
    load_probe_file_cache,
    base_probe_result_from_cache,
    schedule_probe_refresh,
    apply_provider_model_patch,
    probe_models,
    console,
    time_func,
):
    provider_id = provider.get("id", default_provider_id)

    cached = probe_cache.get(provider_id)
    if cached:
        cached_at, cached_result = cached
        if time_func() - cached_at < probe_cache_ttl:
            return apply_provider_model_patch(provider, cached_result)

    fresh_file_cached = load_probe_file_cache(provider_id)
    if fresh_file_cached:
        base_result = base_probe_result_from_cache(provider_id, fresh_file_cached)
        probe_cache[provider_id] = (time_func(), base_result)
        return apply_provider_model_patch(provider, base_result)

    stale_file_cached = load_probe_file_cache(provider_id, allow_stale=True)
    if stale_file_cached:
        base_result = base_probe_result_from_cache(provider_id, stale_file_cached)
        probe_cache[provider_id] = (time_func(), base_result)
        schedule_probe_refresh(provider, cfg, reason="startup_stale")
        if emit_output:
            console.print("[dim]已使用本地模型缓存快速启动，后台正在刷新 provider 模型列表[/dim]")
        return apply_provider_model_patch(provider, base_result)

    return probe_models(provider, emit_output=emit_output)


def warm_probe_cache_async(
    cfg,
    default_provider,
    *,
    probe_async_refresh_after,
    probe_cache_age,
    schedule_probe_refresh,
    resolve_provider_context,
):
    default_id = default_provider.get("id")
    refresh_after = probe_async_refresh_after(cfg)
    for provider_def in cfg.get("providers", []):
        provider_id = provider_def.get("id")
        if not provider_id or provider_id == default_id:
            continue
        age = probe_cache_age(provider_id)
        if age is not None and age < refresh_after:
            continue
        schedule_probe_refresh(resolve_provider_context(cfg, provider_id), cfg, reason="startup_warm")


def select_provider_for_warm(cfg, *, select_provider_for_models):
    return select_provider_for_models(cfg)


def fetch_models(provider, *, probe_models):
    return probe_models(provider, emit_output=True).get("models")


def ensure_models_cache_available(models_cache, *, console):
    if models_cache:
        return True
    console.print("[yellow]当前没有可用的模型列表。请先修复 provider 校验，或先使用预设 / 直接 CLI 启动。[/yellow]")
    return False


def check_cli_installed(cli_name, *, resolve_cli_binary):
    return bool(resolve_cli_binary(cli_name))


def prompt_provider_credentials(
    provider,
    existing_base_url="",
    existing_api_key="",
    allow_keep=False,
    *,
    stdin_isatty,
    console,
    current_command,
    config_command_hint,
    localize,
    ensure_rich,
    default_base_url,
    provider_label,
    prompt_ask,
    exit_func,
):
    if not stdin_isatty():
        console.print(
            f"[red]{localize('当前不是交互终端，无法输入 API URL / API Key，请在终端里运行', 'Not running in an interactive terminal. Please run')} {current_command()} "
            f"{localize('或执行', 'or')} {config_command_hint()}[/red]"
        )
        exit_func(1)
    ensure_rich()

    default_openai = provider.get("default_openai_base_url", "")
    default_anthropic = provider.get("default_anthropic_base_url", "")
    current_openai = provider.get("openai_base_url", "") or existing_base_url
    current_anthropic = provider.get("anthropic_base_url", "") or existing_base_url
    protocols = provider.get("protocols", [])
    needs_openai = "openai_chat_completions" in protocols
    needs_anthropic = "anthropic_messages" in protocols

    base_url = ""
    openai_base_url = ""
    anthropic_base_url = ""

    if needs_openai and needs_anthropic and default_openai and default_anthropic and default_openai != default_anthropic:
        openai_base_url = prompt_ask(
            f"请输入 OpenAI 接口地址 / Base URL（请求地址，通道: {provider_label(provider)}）",
            default=current_openai or default_openai,
        ).rstrip("/")
        anthropic_base_url = prompt_ask(
            f"请输入 Anthropic 接口地址 / Base URL（请求地址，通道: {provider_label(provider)}）",
            default=current_anthropic or default_anthropic,
        ).rstrip("/")
        base_url = anthropic_base_url or openai_base_url
    elif needs_openai and not needs_anthropic:
        openai_base_url = prompt_ask(
            f"请输入 OpenAI 接口地址 / Base URL（请求地址，通道: {provider_label(provider)}）",
            default=current_openai or default_openai or existing_base_url or default_base_url,
        ).rstrip("/")
        base_url = openai_base_url
    elif needs_anthropic and not needs_openai:
        anthropic_base_url = prompt_ask(
            f"请输入 Anthropic 接口地址 / Base URL（请求地址，通道: {provider_label(provider)}）",
            default=current_anthropic or default_anthropic or existing_base_url or default_base_url,
        ).rstrip("/")
        base_url = anthropic_base_url
    else:
        base_default = existing_base_url or default_base_url
        base_url = prompt_ask(
            f"请输入接口地址 / Base URL（请求地址，通道: {provider_label(provider)}）",
            default=base_default,
        ).rstrip("/")
        openai_base_url = base_url if needs_openai else ""
        anthropic_base_url = base_url if needs_anthropic else ""

        key_prompt = f"{localize('请输入 API Key', 'Enter API key')}（{localize('通道', 'channel')}: {provider_label(provider)}）"
    if allow_keep and existing_api_key:
        key_prompt = f"{localize('请输入 API Key', 'Enter API key')}（{localize('通道', 'channel')}: {provider_label(provider)}，{localize('留空保持不变', 'leave empty to keep current value')}）"

    prompt_kwargs = {"password": True}
    if allow_keep:
        prompt_kwargs["default"] = ""
    api_key = prompt_ask(key_prompt, **prompt_kwargs)
    if allow_keep and existing_api_key and not api_key:
        api_key = existing_api_key

    if not api_key:
        console.print(f"[red]{localize('API Key 不能为空', 'API key cannot be empty')}[/red]")
        exit_func(1)

    return base_url, api_key, openai_base_url, anthropic_base_url


def quick_connect_official(
    cfg,
    preset_cli=None,
    *,
    ensure_interactive_terminal,
    localize,
    panel_cls,
    console,
    managed_oauth_clis,
    delegated_oauth_clis,
    wizard_prompt,
    wizard_back_cls,
    wizard_cancel_cls,
    account_map,
    unique_runtime_id,
    normalize_account_id,
    default_account_home,
    prompt_validated_proxy_fields,
    prompt_validated_timezone,
    default_account_timezone,
    normalize_account,
    default_priority,
    ensure_account_config,
    save_config,
    load_config,
    confirm_ask,
):
    ensure_interactive_terminal(localize("官方通道接入", "official channel setup"))
    console.print(panel_cls(
        localize(
            "[bold]官方通道[/bold]\n\n创建一个独立登录目录；创建完成后，回主界面启动该通道时再进入官方 CLI 登录。\n"
            "显示名称给你自己看；系统会自动生成内部标识，避免后续引用丢失。\n"
            "适合多个 ChatGPT / Claude / Antigravity 账号并行使用。\n"
            "[dim]输入 b 返回，q 退出。[/dim]",
            "[bold]Official channel[/bold]\n\nCreate an isolated login directory first; after setup, launch this channel from the main UI to continue the official CLI login flow.\n"
            "The display name is user-facing; MMS auto-generates the stable system ID used by config and follow-up commands.\n"
            "Use this when you want multiple ChatGPT / Claude / Antigravity accounts in parallel.\n"
            "[dim]Type b to go back, q to cancel.[/dim]",
        ),
        title=localize("快速接入", "Quick Connect"),
        border_style="cyan",
    ))
    choices = {
        "1": ("codex", "ChatGPT / Codex"),
        "2": ("agy", "Antigravity CLI"),
    }
    if preset_cli in delegated_oauth_clis:
        console.print("[yellow]Claude OAuth 独立入口已下线；MMS 不再新增 Claude 官方账号。[/yellow]")
        return cfg, False
    if preset_cli in managed_oauth_clis:
        cli_name = preset_cli
    else:
        console.print("  1. ChatGPT / Codex")
        console.print("  2. Antigravity CLI")
        try:
            selected = wizard_prompt(localize("选择官方通道类型", "Select official channel type"), default="1")
        except wizard_back_cls:
            console.print(f"[yellow]{localize('已返回上一层', 'Returned to previous step')}[/yellow]")
            return cfg, False
        except wizard_cancel_cls:
            console.print(f"[yellow]{localize('已退出接入', 'Setup cancelled')}[/yellow]")
            return cfg, False
        if selected not in choices:
            console.print(f"[red]{localize('请输入 1-2', 'Please enter 1-2')}[/red]")
            return cfg, False
        cli_name = choices[selected][0]

    suggested_name = f"{cli_name}-main"
    try:
        name = wizard_prompt(
            localize("显示名 / 列表展示名（主界面里看到的名字）", "Display name / list label"),
            default=suggested_name,
        ).strip() or suggested_name
    except wizard_back_cls:
        console.print(f"[yellow]{localize('已返回上一层', 'Returned to previous step')}[/yellow]")
        return cfg, False
    except wizard_cancel_cls:
        console.print(f"[yellow]{localize('已退出接入', 'Setup cancelled')}[/yellow]")
        return cfg, False
    accounts = account_map(cfg)
    account_id = unique_runtime_id(set(accounts.keys()), normalize_account_id(name))
    console.print(f"[dim]{localize('系统内部标识（自动生成）', 'System ID (auto-generated)')}: {account_id}[/dim]")

    home_dir = default_account_home(account_id)
    try:
        proxy, no_proxy = prompt_validated_proxy_fields("", "", wizard=True)
        timezone_name = prompt_validated_timezone(default_account_timezone, wizard=True)
    except wizard_back_cls:
        console.print(f"[yellow]{localize('已返回上一层', 'Returned to previous step')}[/yellow]")
        return cfg, False
    except wizard_cancel_cls:
        console.print(f"[yellow]{localize('已退出接入', 'Setup cancelled')}[/yellow]")
        return cfg, False
    account = normalize_account({
        "id": account_id,
        "name": name,
        "cli": cli_name,
        "home_dir": home_dir,
        "enabled": True,
        "priority": default_priority,
        "proxy": proxy,
        "no_proxy": no_proxy,
        "timezone": timezone_name,
    })
    updated_cfg = dict(cfg)
    updated_cfg["accounts"] = list(cfg.get("accounts", [])) + [account]
    updated_cfg, _ = ensure_account_config(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ {localize('已添加官方通道', 'Official channel added')}: {name}[/green]")
    console.print(f"[dim]{localize('内部标识', 'System ID')}: {account_id}[/dim]")
    console.print(f"[dim]{localize('文件夹目录', 'Directory')}: {home_dir}[/dim]")
    console.print(
        f"[dim]{localize('已跳过立即登录；请回主界面启动这个官方通道，再完成登录。', 'Immediate login skipped; launch this official channel from the main UI when you are ready to sign in.')}[/dim]"
    )
    if confirm_ask(localize(f"设为 {cli_name} 的默认官方通道？", f"Set as the default {cli_name} official channel?"), default=True):
        updated_cfg = load_config()
        updated_cfg.setdefault("account", {}).setdefault("defaults", {})
        updated_cfg["account"]["defaults"][cli_name] = account_id
        save_config(updated_cfg)
        console.print(f"[green]✓ {localize(f'{cli_name} 默认官方通道已更新为 {account_id}', f'Default {cli_name} official channel set to {account_id}')}[/green]")
    return load_config(), True


def quick_connect_gateway(
    cfg,
    preset_id=None,
    *,
    ensure_interactive_terminal,
    select_provider_template,
    provider_template_payload,
    localize,
    panel_cls,
    console,
    provider_map,
    wizard_prompt,
    wizard_back_cls,
    wizard_cancel_cls,
    normalize_provider_id_input,
    default_provider_id,
    unique_runtime_id,
    normalize_provider,
    default_base_url,
    confirm_ask,
    prompt_ask,
    normalize_models_endpoint,
    prompt_validated_proxy_fields,
    prompt_validated_timezone,
    default_account_timezone,
    upsert_provider,
    save_config,
    save_provider_credentials_with_probe,
    load_config,
):
    ensure_interactive_terminal(localize("网关通道接入", "gateway channel setup"))
    template_key = select_provider_template(preset_id=preset_id)
    template = provider_template_payload(template_key)
    console.print(panel_cls(
        localize(
            "[bold]网关通道[/bold]\n\n填写接口地址（请求地址 / Base URL）和 API Key，接入兼容 OpenAI / Anthropic 的服务。\n"
            "显示名称给你自己看；系统会自动生成内部标识，避免后续功能和外部消费引用丢失。\n"
            "如果模型列表地址和请求地址不同，再额外填写“模型列表地址（高级）”。\n"
            "默认会启用全部 CLI；后续如需精细限制，再用 provider.edit 调整。\n"
            "[dim]输入 b 返回，q 退出。[/dim]",
            "[bold]Gateway channel[/bold]\n\nEnter the request Base URL and API key for any OpenAI- or Anthropic-compatible service.\n"
            "The display name is for you; MMS auto-generates a stable system ID so presets and external consumers do not break.\n"
            "Only fill a separate model list URL if listing models uses a different endpoint.\n"
            "All CLIs are enabled by default; use provider.edit later if you need tighter limits.\n"
            "[dim]Type b to go back, q to cancel.[/dim]",
        ),
        title=localize("快速接入", "Quick Connect"),
        border_style="cyan",
    ))
    providers = provider_map(cfg)
    suggested_name = template["name"]
    try:
        name = wizard_prompt(
            localize("显示名称 / 列表展示名（主界面里看到的名字）", "Display name / list label"),
            default=suggested_name,
        ).strip() or suggested_name
        suggested_id = normalize_provider_id_input(name)
        if suggested_id == default_provider_id:
            suggested_id = normalize_provider_id_input(template["id"] or name)
        provider_id = unique_runtime_id(set(providers.keys()), suggested_id)
    except wizard_back_cls:
        console.print(f"[yellow]{localize('已返回上一层', 'Returned to previous step')}[/yellow]")
        return cfg, False
    except wizard_cancel_cls:
        console.print(f"[yellow]{localize('已退出接入', 'Setup cancelled')}[/yellow]")
        return cfg, False
    console.print(f"[dim]{localize('系统内部标识（自动生成）', 'System ID (auto-generated)')}: {provider_id}[/dim]")

    provider = normalize_provider({
        **template,
        "id": provider_id,
        "name": name,
    })
    try:
        base_url = wizard_prompt(
            localize("接口地址 / Base URL（请求地址）", "Request Base URL"),
            default=provider.get("default_openai_base_url") or provider.get("default_anthropic_base_url") or default_base_url,
            required=True,
        ).rstrip("/")
        api_key = wizard_prompt(
            localize("API Key（不会回显）", "API key (hidden)"),
            password=True,
            required=True,
        )
        if confirm_ask(localize("模型列表地址与请求地址不同？（高级）", "Use a separate model list URL? (advanced)"), default=False):
            provider["models_endpoint"] = normalize_models_endpoint(
                prompt_ask(
                    localize(
                        "模型列表地址（高级，仅用于独立拉取模型列表；通常留默认）",
                        "Model list URL (advanced, only used for a separate model-list endpoint)",
                    ),
                    default=provider.get("models_endpoint", "/models"),
                )
            )
        provider["proxy"], provider["no_proxy"] = prompt_validated_proxy_fields(
            provider.get("proxy", ""),
            provider.get("no_proxy", ""),
            wizard=True,
        )
        provider["timezone"] = prompt_validated_timezone(
            provider.get("timezone") or default_account_timezone,
            wizard=True,
        )
        provider = normalize_provider(provider)
    except wizard_back_cls:
        console.print(f"[yellow]{localize('已返回上一层', 'Returned to previous step')}[/yellow]")
        return cfg, False
    except wizard_cancel_cls:
        console.print(f"[yellow]{localize('已退出接入', 'Setup cancelled')}[/yellow]")
        return cfg, False
    updated_cfg = upsert_provider(cfg, provider)
    save_config(updated_cfg)
    save_provider_credentials_with_probe(
        provider,
        base_url,
        api_key,
        base_url if "openai_chat_completions" in provider.get("protocols", []) else "",
        base_url if "anthropic_messages" in provider.get("protocols", []) else "",
    )
    console.print(f"[green]✓ {localize('已接入网关通道', 'Gateway channel added')}: {name}[/green]")
    console.print(f"[dim]{localize('内部标识', 'System ID')}: {provider_id}[/dim]")
    return load_config(), True


def select_cli(
    cli_names,
    *,
    check_cli_installed,
    check_and_offer_install,
    table_cls,
    int_prompt_cls,
    console,
    exit_func,
):
    if not cli_names:
        console.print("[red]当前没有可用的 CLI。请先检查 provider 配置和模型探测结果。[/red]")
        exit_func(1)
    table = table_cls(title="选择 CLI")
    table.add_column("#", style="cyan", width=4)
    table.add_column("CLI", style="green")
    table.add_column("状态", style="yellow")

    for i, name in enumerate(cli_names, 1):
        status = "[green]已安装[/green]" if check_cli_installed(name) else "[red]未安装[/red]"
        table.add_row(str(i), name, status)

    console.print(table)

    while True:
        try:
            choice = int_prompt_cls.ask("选择 CLI 编号")
            if 1 <= choice <= len(cli_names):
                cli = cli_names[choice - 1]
                if not check_cli_installed(cli):
                    check_and_offer_install(cli)
                return cli
            console.print(f"[red]请输入 1-{len(cli_names)}[/red]")
        except KeyboardInterrupt:
            exit_func(0)


def setup_provider_credentials(
    provider,
    existing_base_url="",
    existing_api_key="",
    allow_keep=False,
    *,
    prompt_provider_credentials,
    save_provider_credentials_with_probe,
):
    base_url, api_key, openai_base_url, anthropic_base_url = prompt_provider_credentials(
        provider,
        existing_base_url,
        existing_api_key,
        allow_keep,
    )
    return save_provider_credentials_with_probe(
        provider,
        base_url,
        api_key,
        openai_base_url,
        anthropic_base_url,
    )


def setup_api_credentials(
    existing_base_url="",
    existing_api_key="",
    allow_keep=False,
    *,
    default_provider,
    setup_provider_credentials,
):
    provider = default_provider()
    provider_ctx = setup_provider_credentials(provider, existing_base_url, existing_api_key, allow_keep)
    return provider_ctx["base_url"], provider_ctx["api_key"]


def ensure_provider_credentials(
    cfg,
    provider_id=None,
    *,
    get_provider_definition,
    load_provider_credentials,
    resolve_provider_context,
    setup_provider_credentials,
):
    provider = get_provider_definition(cfg, provider_id)
    if provider.get("_mms_bundle_runtime") and provider.get("api_key") and (
        provider.get("openai_base_url")
        or provider.get("anthropic_base_url")
        or provider.get("default_openai_base_url")
        or provider.get("default_anthropic_base_url")
    ):
        return resolve_provider_context(cfg, provider["id"])
    credentials = load_provider_credentials(provider["id"])
    if (
        credentials["base_url"]
        or credentials["openai_base_url"]
        or credentials["anthropic_base_url"]
    ) and credentials["api_key"]:
        return resolve_provider_context(cfg, provider["id"])
    existing_base = (
        credentials["base_url"]
        or credentials["openai_base_url"]
        or credentials["anthropic_base_url"]
    )
    return setup_provider_credentials(
        provider,
        existing_base,
        credentials["api_key"],
        allow_keep=bool(credentials["api_key"]),
    )


def ensure_api_credentials(*, default_config, ensure_provider_credentials):
    provider_ctx = ensure_provider_credentials(default_config())
    return provider_ctx["base_url"], provider_ctx["api_key"]


def setup_wizard(
    ui_language=None,
    *,
    normalize_language,
    set_language,
    display_title,
    localize,
    panel_cls,
    default_config,
    setup_provider_credentials,
    get_provider_definition,
    prompt_ask,
    mode_all,
    mode_recommended,
    save_config,
    config_path,
    console,
):
    ui_language = normalize_language(ui_language) or "zh"
    set_language(ui_language)
    title = display_title()
    console.print(panel_cls(
        f"[bold cyan]{localize(f'欢迎使用 {title} — AI Coding CLI 统一启动器', f'Welcome to {title} — unified AI coding CLI launcher')}[/bold cyan]\n\n"
        f"{localize(f'{title} 帮你一键启动 AI 编程助手', f'{title} helps you launch AI coding assistants from one entrypoint')}\n"
        f"{localize('首次使用，需要配置 API 地址和认证信息', 'First-time setup needs an API endpoint and credentials')}",
        title=f"{title} Setup",
    ))

    cfg = default_config()
    cfg.setdefault("ui", {})["language"] = ui_language
    setup_provider_credentials(get_provider_definition(cfg))

    role = prompt_ask(localize("模型模式", "Model mode"), choices=[mode_all, mode_recommended], default=mode_all)
    cfg = default_config(role)
    cfg.setdefault("ui", {})["language"] = ui_language
    save_config(cfg)
    console.print(f"\n[green]✓ {localize('配置已保存到', 'Config saved to')} {config_path}[/green]\n")
    return cfg


def provider_supports_mimo_anthropic_selectors(provider):
    provider = provider if isinstance(provider, dict) else {}
    identity = " ".join(
        str(provider.get(key) or "").strip().lower()
        for key in ("id", "name", "label", "provider_profile")
    )
    urls = " ".join(
        str(provider.get(key) or "").strip().lower()
        for key in ("anthropic_base_url", "openai_base_url", "base_url")
    )
    if "openrouter" in identity or "openrouter.ai" in urls:
        return False
    anthropic_base = str(provider.get("anthropic_base_url") or "").strip().lower()
    if "xiaomimimo.com" in anthropic_base:
        return True
    base_url = str(provider.get("base_url") or "").strip().lower()
    if "xiaomimimo.com" in base_url and "/anthropic" in base_url:
        return True
    return bool(anthropic_base and any(token in identity for token in ("mimo", "xiaomi")))


def derived_model_aliases(
    base_models,
    provider=None,
    *,
    provider_supports_mimo_anthropic_selectors=provider_supports_mimo_anthropic_selectors,
):
    aliases = []
    claude_tails = [str(model_id or "").strip().lower().rsplit("/", 1)[-1] for model_id in base_models]
    if any(model_id.startswith("claude-sonnet-4-") or model_id.startswith("claude-sonnet-4.") for model_id in claude_tails):
        aliases.append("claude-sonnet-4-6")
    if any(model_id.startswith("claude-opus-4-") or model_id.startswith("claude-opus-4.") for model_id in claude_tails):
        aliases.append("claude-opus-4-6")
    # MiMo 1M is now controlled by model-policy context_window_tokens. Keep
    # explicit legacy [1m] selectors from config, but do not invent duplicates.
    return aliases


def apply_provider_model_patch(
    provider,
    base_result,
    *,
    normalize_model_id_list=None,
    derived_model_aliases=derived_model_aliases,
):
    if normalize_model_id_list is None:
        normalize_model_id_list = globals()["normalize_model_id_list"]
    result = dict(base_result)
    base_models = normalize_model_id_list(result.get("raw_models") or result.get("models") or [])
    extra_models = normalize_model_id_list(provider.get("extra_models", []))
    hidden_requested = set(normalize_model_id_list(provider.get("hidden_models", [])))
    hidden_requested_lower = {model_id.lower() for model_id in hidden_requested}
    alias_base_models = [model_id for model_id in base_models if model_id.lower() not in hidden_requested_lower]
    aliases = derived_model_aliases(alias_base_models, provider)
    base_source = result.get("base_source") or ("fallback" if result.get("used_fallback") else "remote")

    effective_models = []
    model_sources = {}
    for model_id in base_models:
        if model_id in model_sources:
            continue
        model_sources[model_id] = base_source
        effective_models.append(model_id)

    for model_id in extra_models:
        if model_id in model_sources:
            continue
        model_sources[model_id] = "extra"
        effective_models.append(model_id)

    for model_id in aliases:
        if model_id in model_sources:
            continue
        model_sources[model_id] = "derived_alias"
        effective_models.append(model_id)

    domestic_keywords = ("glm", "kimi", "qwen", "minimax", "deepseek", "doubao", "seed", "bailian")
    claude_keep = {
        "claude-opus-4-6", "claude-opus-4-6-thinking", "claude-sonnet-4-6",
        "claude-opus-4-5-20251101", "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5-20251001",
    }
    effective_models = [
        model_id for model_id in effective_models
        if not (model_id.startswith("claude-") and any(kw in model_id.lower() for kw in domestic_keywords))
        and not (model_id.startswith("claude-") and model_id not in claude_keep)
    ]

    hidden_applied = [model_id for model_id in effective_models if model_id.lower() in hidden_requested_lower]
    if hidden_requested:
        effective_models = [model_id for model_id in effective_models if model_id.lower() not in hidden_requested_lower]
    visible_sources = {model_id: model_sources.get(model_id, base_source) for model_id in effective_models}

    result["raw_models"] = base_models
    result["models"] = effective_models
    result["model_sources"] = visible_sources
    result["extra_models"] = extra_models + [model_id for model_id in aliases if model_id not in extra_models]
    result["hidden_models"] = hidden_applied
    result["base_source"] = base_source
    return result


def provider_candidates(
    cfg,
    default_provider,
    default_models,
    *,
    load_probe_file_cache,
    resolve_provider_context,
):
    candidates = [(default_provider, list(default_models or []))]
    seen_ids = {default_provider.get("id")}
    for provider_def in cfg.get("providers", []):
        provider_id = provider_def.get("id")
        if not provider_id or provider_id in seen_ids:
            continue
        file_cached = load_probe_file_cache(provider_id, allow_stale=True)
        cached_models = None
        if file_cached is not None and not file_cached.get("is_stale"):
            cached_models = list((file_cached or {}).get("raw_models") or [])
        candidates.append((resolve_provider_context(cfg, provider_id), cached_models))
        seen_ids.add(provider_id)
    return candidates


def provider_effective_models(
    provider,
    cached_models,
    cfg=None,
    *,
    schedule_probe_refresh,
    apply_provider_model_patch,
):
    if provider.get("_mms_bundle_runtime"):
        base_models = list(provider.get("fallback_models") or [])
        base_source = "approved"
    elif cached_models is None:
        if provider.get("models_endpoint") == "manual":
            base_models = list(provider.get("fallback_models") or [])
            base_source = "manual"
        else:
            schedule_probe_refresh(provider, cfg, reason="cache_miss")
            base_models = list(provider.get("fallback_models") or [])
            base_source = "fallback" if base_models else "remote"
    else:
        base_models = list(cached_models or [])
        base_source = "remote"

    patched = apply_provider_model_patch(
        provider,
        {"raw_models": base_models, "models": base_models, "base_source": base_source},
    )
    return list(patched.get("models") or [])


def is_installed_mms_layout(
    module_path,
    *,
    real_user_home,
    abspath=os.path.abspath,
    commonpath=os.path.commonpath,
):
    current_path = abspath(module_path)
    installed_root = abspath(os.path.join(real_user_home(), ".mms"))
    try:
        return commonpath([current_path, installed_root]) == installed_root
    except ValueError:
        return False


def default_gpt_reasoning_effort(*, module_path, is_installed_mms_layout):
    return "high" if is_installed_mms_layout(module_path) else "xhigh"


def default_reasoning_effort_for_model_info(
    model_info,
    *,
    model_matches_account_cli,
    default_gpt_reasoning_effort,
):
    values = []
    if isinstance(model_info, dict):
        values.extend(str(value or "") for key, value in model_info.items() if key != "subagent")
    else:
        values.append(str(model_info or ""))
    for item in values:
        normalized = str(item or "").strip().lower()
        if "/" in normalized:
            normalized = normalized.rsplit("/", 1)[-1]
        if model_matches_account_cli("codex", normalized):
            return default_gpt_reasoning_effort()
    return "high"


def bridge_clis_for_model(model_name, *, infer_model_family):
    family, _ = infer_model_family(model_name)
    if family == "Unknown":
        return []
    native = set(native_clis_for_model(model_name))
    bridge = []
    for cli_name in ("claude", "codex"):
        if cli_name not in native:
            bridge.append(cli_name)
    return bridge


def model_supports_vision(model_name, *, vision_capable_model_names, vision_capable_model_hints):
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return False
    model_id = normalized.rsplit("/", 1)[-1]
    if model_id in vision_capable_model_names:
        return True
    return any(hint in model_id for hint in vision_capable_model_hints)


def model_cli_modes(model_name, *, infer_model_family):
    native = set(native_clis_for_model(model_name))
    bridge = set(bridge_clis_for_model(model_name, infer_model_family=infer_model_family))
    modes = {}
    for cli_name in ("claude", "codex"):
        if cli_name in native:
            modes[cli_name] = "native"
        elif cli_name in bridge:
            modes[cli_name] = "bridge"
        else:
            modes[cli_name] = "unsupported"
    return modes


def model_cli_summary(model_name, *, infer_model_family):
    modes = model_cli_modes(model_name, infer_model_family=infer_model_family)
    parts = []
    for cli_name in ("claude", "codex"):
        mode = modes.get(cli_name)
        if mode == "native":
            parts.append(f"{cli_name}:native")
        elif mode == "bridge":
            parts.append(f"{cli_name}:bridge")
    return ", ".join(parts) if parts else "-"


def model_capability_tags(
    model_name,
    *,
    infer_model_family,
    model_context_window,
    reasoning_model_hints,
    tool_use_families,
    vision_capable_model_names,
    vision_capable_model_hints,
    resolve_model_capabilities=None,
):
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return []
    family, _ = infer_model_family(model_name)
    tags = []
    if model_supports_vision(
        model_name,
        vision_capable_model_names=vision_capable_model_names,
        vision_capable_model_hints=vision_capable_model_hints,
    ):
        tags.append("vision")
    if family in tool_use_families:
        tags.append("tool_use")
    if any(hint in normalized for hint in reasoning_model_hints):
        tags.append("reasoning")
    if resolve_model_capabilities is not None:
        try:
            caps = resolve_model_capabilities(model_name)
            if caps.get("supports_thinking") is True and caps.get("sources", {}).get("supports_thinking") != "conservative_fallback":
                tags.append("thinking")
        except Exception:
            pass
    context_window = model_context_window(model_name)
    if context_window and context_window >= 200_000:
        tags.append("long_context")
    if "claude" in bridge_clis_for_model(model_name, infer_model_family=infer_model_family):
        tags.append("bridge_required")
    return tags


def model_capability_summary(model_name, *, model_capability_tags):
    tags = model_capability_tags(model_name)
    return ", ".join(tags) if tags else "-"


def env_file_path(cli_name, *, env_dir):
    return os.path.join(env_dir, f"{cli_name}.sh")


def shell_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def parse_shell_value(raw):
    raw = raw.strip()
    if not raw:
        return ""
    try:
        parts = shlex.split(f"v {raw}")
    except ValueError:
        return raw.strip("\"'")
    return parts[1] if len(parts) > 1 else ""


def load_env_file(path):
    values = {}
    if not os.path.exists(path):
        return values

    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, sep, raw_value = line.partition("=")
            if not sep:
                continue
            values[key.strip()] = parse_shell_value(raw_value)
    return values


def account_map(cfg):
    accounts = cfg.get("accounts", [])
    return {account["id"]: account for account in accounts if isinstance(account, dict) and account.get("id")}


def accounts_for_cli(cfg, cli_name):
    return [
        account for account in account_map(cfg).values()
        if account.get("cli") == cli_name and account.get("enabled", True)
    ]


def get_provider_definition(
    cfg,
    provider_id=None,
    *,
    provider_map,
    default_provider,
    default_provider_id,
    console,
    exit_func=sys.exit,
):
    providers = provider_map(cfg)
    resolved_id = provider_id or cfg.get("provider", {}).get("default") or default_provider_id
    provider = providers.get(resolved_id)
    if provider:
        return provider
    if provider_id:
        console.print(f"[red]未找到 provider: {provider_id}[/red]")
        exit_func(1)
    if providers:
        return next(iter(providers.values()))
    return default_provider()


def get_account_definition(
    cfg,
    account_id=None,
    cli_name=None,
    *,
    account_map,
    console,
    exit_func=sys.exit,
):
    accounts = account_map(cfg)
    resolved_id = account_id
    if not resolved_id and cli_name:
        resolved_id = cfg.get("account", {}).get("defaults", {}).get(cli_name)
    if resolved_id:
        account = accounts.get(resolved_id)
        if account:
            return account
        console.print(f"[red]未找到账号档案: {resolved_id}[/red]")
        exit_func(1)
    return None


def normalize_provider_id_input(provider_id, *, default_provider_id):
    value = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "-"
        for ch in str(provider_id or "").strip().lower()
    )
    value = value.strip("-_")
    return value or default_provider_id


def sanitize_provider_id(provider_id, *, default_provider_id):
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in str(provider_id).upper())
    cleaned = cleaned.strip("_")
    return cleaned or default_provider_id.upper()


def normalize_model_id_list(values):
    if isinstance(values, str):
        values = [chunk.strip() for chunk in values.split(",")]
    normalized = []
    seen = set()
    for item in values or []:
        model_id = str(item or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        normalized.append(model_id)
    return normalized


def unique_runtime_id(existing_ids, base_id):
    normalized = str(base_id or "").strip()
    if not normalized:
        normalized = "default"
    if normalized not in existing_ids:
        return normalized
    suffix = 2
    while True:
        candidate = f"{normalized}-{suffix}"
        if candidate not in existing_ids:
            return candidate
        suffix += 1


def normalize_models_endpoint(value):
    endpoint = str(value or "").strip()
    if not endpoint:
        return "/models"
    if endpoint.lower() in {"manual", "none", "off"}:
        return "manual"
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    return endpoint


def provider_env_name(provider_id, field, *, default_provider_id):
    return f"MMS_PROVIDER_{sanitize_provider_id(provider_id, default_provider_id=default_provider_id)}_{field}"


def load_provider_credentials(
    provider_id,
    *,
    default_provider_id,
    provider_env_name,
    api_url_env_name,
    api_key_env_name,
    credentials_paths,
    load_env_file,
    active_config_path,
    environ=os.environ,
    path_exists=os.path.exists,
):
    base_key = provider_env_name(provider_id, "BASE_URL")
    openai_base_key = provider_env_name(provider_id, "OPENAI_BASE_URL")
    anthropic_base_key = provider_env_name(provider_id, "ANTHROPIC_BASE_URL")
    api_key_name = provider_env_name(provider_id, "API_KEY")
    openai_api_key_name = provider_env_name(provider_id, "OPENAI_API_KEY")
    base_url = environ.get(base_key, "").strip()
    openai_base_url = environ.get(openai_base_key, "").strip()
    anthropic_base_url = environ.get(anthropic_base_key, "").strip()
    api_key = environ.get(api_key_name, "").strip()
    openai_api_key = environ.get(openai_api_key_name, "").strip()

    if provider_id == default_provider_id:
        base_url = base_url or environ.get(api_url_env_name, "").strip()
        api_key = api_key or environ.get(api_key_env_name, "").strip()

    for credentials_path in credentials_paths:
        if not path_exists(credentials_path):
            continue
        file_values = load_env_file(credentials_path)
        base_url = base_url or file_values.get(base_key, "").strip()
        openai_base_url = openai_base_url or file_values.get(openai_base_key, "").strip()
        anthropic_base_url = anthropic_base_url or file_values.get(anthropic_base_key, "").strip()
        api_key = api_key or file_values.get(api_key_name, "").strip()
        openai_api_key = openai_api_key or file_values.get(openai_api_key_name, "").strip()
        if provider_id == default_provider_id:
            base_url = base_url or file_values.get(api_url_env_name, "").strip()
            api_key = api_key or file_values.get(api_key_env_name, "").strip()

    config_path = active_config_path()
    if provider_id == default_provider_id and (not base_url or not api_key) and path_exists(config_path):
        with open(config_path, "rb") as f:
            legacy_cfg = tomllib.loads(f.read().decode("utf-8"))
        legacy_api = legacy_cfg.get("api", {})
        if isinstance(legacy_api, dict):
            base_url = base_url or str(legacy_api.get("base_url", "")).strip()
            api_key = api_key or str(legacy_api.get("api_key", "")).strip()

    return {
        "base_url": base_url.rstrip("/") if base_url else "",
        "openai_base_url": openai_base_url.rstrip("/") if openai_base_url else "",
        "anthropic_base_url": anthropic_base_url.rstrip("/") if anthropic_base_url else "",
        "api_key": api_key,
        "openai_api_key": openai_api_key,
    }


def save_provider_credentials(
    provider_id,
    base_url,
    api_key,
    openai_base_url="",
    anthropic_base_url="",
    openai_api_key=None,
    *,
    config_dir,
    credentials_path,
    provider_env_name,
    default_provider_id,
    api_url_env_name,
    api_key_env_name,
    load_env_file,
    shell_quote,
    trigger_routes_export_after_credentials_write,
    makedirs=os.makedirs,
    path_exists=os.path.exists,
    chmod=os.chmod,
):
    makedirs(config_dir, exist_ok=True)
    values = load_env_file(credentials_path) if path_exists(credentials_path) else {}
    base_key = provider_env_name(provider_id, "BASE_URL")
    openai_base_key = provider_env_name(provider_id, "OPENAI_BASE_URL")
    anthropic_base_key = provider_env_name(provider_id, "ANTHROPIC_BASE_URL")
    api_key_name = provider_env_name(provider_id, "API_KEY")
    openai_api_key_name = provider_env_name(provider_id, "OPENAI_API_KEY")
    base_url = base_url.rstrip("/")
    openai_base_url = openai_base_url.rstrip("/")
    anthropic_base_url = anthropic_base_url.rstrip("/")
    values[base_key] = base_url
    if openai_base_url:
        values[openai_base_key] = openai_base_url
    else:
        values.pop(openai_base_key, None)
    if anthropic_base_url:
        values[anthropic_base_key] = anthropic_base_url
    else:
        values.pop(anthropic_base_key, None)
    values[api_key_name] = api_key
    if openai_api_key is None:
        if openai_base_url:
            values[openai_api_key_name] = api_key
        else:
            values.pop(openai_api_key_name, None)
    elif openai_api_key:
        values[openai_api_key_name] = openai_api_key
    else:
        values.pop(openai_api_key_name, None)

    if provider_id == default_provider_id:
        values[api_url_env_name] = base_url
        values[api_key_env_name] = api_key

    lines = ["# Generated by MMS"]
    for key in sorted(values):
        lines.append(f"export {key}={shell_quote(str(values[key]))}")
    lines.append("")

    with open(credentials_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    chmod(credentials_path, 0o600)
    trigger_routes_export_after_credentials_write()


def load_api_credentials(*, default_provider_id, load_provider_credentials):
    provider_creds = load_provider_credentials(default_provider_id)
    return provider_creds["base_url"], provider_creds["api_key"]


def save_api_credentials(base_url, api_key, *, default_provider_id, save_provider_credentials):
    return save_provider_credentials(default_provider_id, base_url, api_key)


def default_config(
    role,
    *,
    normalize_user_role,
    probe_async_refresh_after_sec,
    probe_async_min_interval_sec,
    default_provider_id,
    default_provider,
):
    return {
        "ui": {"language": "zh"},
        "user": {"role": normalize_user_role(role)},
        "cache": {
            "probe_async_refresh_after_sec": probe_async_refresh_after_sec,
            "probe_async_min_interval_sec": probe_async_min_interval_sec,
        },
        "provider": {"default": default_provider_id},
        "providers": [default_provider()],
        "account": {"defaults": {}},
        "accounts": [],
        "recommend": {"models": [
            "claude-sonnet-4-6", "qwen3-coder-plus", "gpt-4o-mini",
        ]},
        "presets": {
            "coding": {
                "cli": "claude",
                "opus": "claude-opus-4-6",
                "sonnet": "claude-sonnet-4-6",
                "haiku": "claude-haiku-4-5-20251001",
                "subagent": "claude-sonnet-4-6",
            },
            "cheap": {"cli": "claude", "model": "qwen3-coder-plus"},
            "codex-gpt": {"cli": "codex", "model": "gpt-5.4"},
        },
    }


def migrate_legacy_api_config(
    cfg,
    *,
    load_api_credentials,
    save_api_credentials,
    ensure_provider_config,
    ensure_account_config,
    normalize_user_config,
    save_config,
    credentials_path,
    config_path,
    console,
):
    api_cfg = cfg.get("api")
    updated_cfg = dict(cfg)

    if isinstance(api_cfg, dict):
        base_url = str(api_cfg.get("base_url", "")).strip()
        api_key = str(api_cfg.get("api_key", "")).strip()
        file_base_url, file_api_key, _ = load_api_credentials()

        if base_url and api_key and (not file_base_url or not file_api_key):
            try:
                save_api_credentials(base_url, api_key)
                console.print(f"[yellow]已将 API 凭据迁移到 {credentials_path}[/yellow]")
            except OSError as exc:
                console.print(f"[yellow]无法迁移 API 凭据到 {credentials_path}: {exc}[/yellow]")
                return cfg

        updated_cfg.pop("api", None)

    updated_cfg, changed = ensure_provider_config(updated_cfg)
    updated_cfg, account_changed = ensure_account_config(updated_cfg)
    updated_cfg, role_changed = normalize_user_config(updated_cfg)
    if changed or account_changed or role_changed or updated_cfg != cfg:
        try:
            save_config(updated_cfg)
        except OSError as exc:
            console.print(f"[yellow]无法更新 {config_path}: {exc}[/yellow]")
            return cfg
    return updated_cfg


def resolve_provider_context(
    cfg,
    provider_id=None,
    *,
    get_provider_definition,
    normalize_provider,
    load_provider_credentials,
):
    provider = normalize_provider(get_provider_definition(cfg, provider_id))
    credentials = load_provider_credentials(provider["id"])
    if provider.get("_mms_bundle_runtime"):
        provider["base_url"] = credentials["base_url"] or provider.get("base_url", "")
        provider["openai_base_url"] = (
            credentials["openai_base_url"]
            or provider.get("openai_base_url", "")
            or provider.get("default_openai_base_url", "")
        )
        provider["anthropic_base_url"] = (
            credentials["anthropic_base_url"]
            or provider.get("anthropic_base_url", "")
            or provider.get("default_anthropic_base_url", "")
        )
        provider["api_key"] = credentials["api_key"] or provider.get("api_key", "")
        provider["openai_api_key"] = credentials.get("openai_api_key", "") or provider.get("openai_api_key", "")
    else:
        provider["base_url"] = credentials["base_url"]
        provider["openai_base_url"] = credentials["openai_base_url"] or provider.get("default_openai_base_url", "")
        provider["anthropic_base_url"] = credentials["anthropic_base_url"] or provider.get("default_anthropic_base_url", "")
        provider["api_key"] = credentials["api_key"]
        provider["openai_api_key"] = credentials.get("openai_api_key", "")
    provider["auth_mode"] = "api_key"
    provider["runtime_kind"] = "provider"
    return provider


def resolve_account_context(
    cfg,
    account_id=None,
    cli_name=None,
    *,
    get_account_definition,
    expanduser=os.path.expanduser,
):
    account = get_account_definition(cfg, account_id=account_id, cli_name=cli_name)
    if account is None:
        return None
    resolved = dict(account)
    resolved["auth_mode"] = "oauth"
    resolved["runtime_kind"] = "account"
    resolved["home_dir"] = expanduser(resolved.get("home_dir", ""))
    return resolved


def save_provider_credentials_with_probe(
    provider,
    base_url,
    api_key,
    openai_base_url="",
    anthropic_base_url="",
    *,
    probe_models,
    provider_openai_base_url,
    save_provider_credentials,
    resolve_provider_context,
    credentials_path,
    console,
):
    provider_ctx = dict(provider)
    provider_ctx["base_url"] = base_url
    provider_ctx["openai_base_url"] = openai_base_url
    provider_ctx["anthropic_base_url"] = anthropic_base_url
    provider_ctx["api_key"] = api_key

    console.print("\n正在测试连接...", style="dim")
    probe = probe_models(provider_ctx)
    models = probe.get("models")
    if models is None:
        console.print("[yellow]⚠ 连接失败，但配置仍会保存。请检查地址和 Key。[/yellow]")
    else:
        console.print(f"[green]✓ 连接成功！发现 {len(models)} 个可用模型[/green]")
        working_url = probe.get("working_url")
        computed_openai = provider_openai_base_url(provider_ctx)
        if working_url and working_url != computed_openai:
            fixed_base = working_url
            console.print(f"[yellow]→ 自动修正地址为 {fixed_base}[/yellow]")
            openai_base_url = fixed_base
            base_url = fixed_base

    save_provider_credentials(provider["id"], base_url, api_key, openai_base_url, anthropic_base_url)
    console.print(f"[green]✓ provider '{provider['id']}' 的凭据已保存到 {credentials_path}[/green]")
    console.print("[dim]API Key 在配置显示里会以掩码形式展示，不会直接回显明文。[/dim]")
    return resolve_provider_context({"providers": [provider], "provider": {"default": provider["id"]}}, provider["id"])


def provider_env_value(provider_id, field, *, default_provider_id, environ=None):
    environ = os.environ if environ is None else environ
    return environ.get(provider_env_name(provider_id, field, default_provider_id=default_provider_id), "").strip()


def normalize_supported_clis(value, *, protocols=None, cli_names, legacy_provider_cli_aliases):
    if isinstance(value, str):
        raw_items = [value]
    else:
        raw_items = list(value or [])
    protocol_set = {str(item).strip() for item in (protocols or []) if str(item).strip()}
    normalized = []
    seen = set()

    def add(cli_name):
        if cli_name in cli_names and cli_name not in seen:
            normalized.append(cli_name)
            seen.add(cli_name)

    for item in raw_items:
        cli_name = str(item or "").strip().lower()
        if not cli_name:
            continue
        if cli_name in legacy_provider_cli_aliases:
            if "anthropic_messages" in protocol_set:
                add("claude")
            if "openai_chat_completions" in protocol_set:
                add("codex")
            continue
        add(cli_name)
    return normalized


def normalize_role(value, *, valid_roles):
    role = str(value or "auto").strip().lower()
    return role if role in valid_roles else "auto"


def normalize_positive_seconds(value, default, minimum=1):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def default_provider(*, default_provider_id, default_provider_protocols, provider_capable_clis):
    return {
        "id": default_provider_id,
        "name": "Default Gateway",
        "protocols": list(default_provider_protocols),
        "supported_clis": list(provider_capable_clis),
        "enabled": True,
        "role": "auto",
    }


def normalize_priority(value, *, default_priority):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default_priority


def canonical_model_family(value, *, model_families):
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    for entry in model_families:
        family = str(entry.get("family") or "").strip()
        if family.lower() == raw:
            return family
    return ""


def normalize_family_priority_overrides(value, *, model_families, default_priority):
    if not isinstance(value, dict):
        return {}
    normalized = {}
    for family_name, priority in value.items():
        canonical = canonical_model_family(family_name, model_families=model_families)
        if not canonical:
            continue
        normalized[canonical] = normalize_priority(priority, default_priority=default_priority)
    return normalized


def runtime_priority_for_family(
    runtime,
    family_name,
    *,
    canonical_model_family,
    normalize_priority,
    default_priority,
):
    canonical = canonical_model_family(family_name)
    overrides = runtime.get("family_priority_overrides", {}) if isinstance(runtime, dict) else {}
    if canonical and isinstance(overrides, dict) and canonical in overrides:
        return normalize_priority(overrides.get(canonical))
    if isinstance(runtime, dict):
        return normalize_priority(runtime.get("priority", default_priority))
    return default_priority


def runtime_priority_for_model(
    runtime,
    model_name,
    *,
    infer_model_family,
    runtime_priority_for_family,
):
    family_name, _ = infer_model_family(model_name)
    return runtime_priority_for_family(runtime, family_name)


def runtime_with_priority(
    runtime,
    *,
    model_name="",
    family_name="",
    canonical_model_family,
    infer_model_family,
    runtime_priority_for_family,
    normalize_priority,
    default_priority,
):
    if not isinstance(runtime, dict):
        return runtime
    canonical_family = canonical_model_family(family_name)
    if not canonical_family and model_name:
        canonical_family, _ = infer_model_family(model_name)
    merged = dict(runtime)
    merged["priority"] = (
        runtime_priority_for_family(runtime, canonical_family)
        if canonical_family
        else normalize_priority(runtime.get("priority", default_priority))
    )
    if canonical_family:
        merged["priority_family"] = canonical_family
    return merged


def normalize_claude_1m_mode(value, *, default="auto", valid_modes):
    raw = str(value or "").strip().lower()
    if raw in {"", "inherit", "default", "auto"}:
        return default if default in valid_modes else "auto"
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return "enable"
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return "disable"
    return default if default in valid_modes else "auto"


def normalize_timezone_name(value, *, default):
    timezone_name = str(value or "").strip() or default
    if timezone_name:
        try:
            ZoneInfo(timezone_name)
        except Exception:
            timezone_name = default
    return timezone_name


def normalize_provider(
    provider,
    *,
    default_provider_id,
    default_provider_protocols,
    provider_capable_clis,
    default_priority,
    model_families,
    default_account_timezone,
    claude_1m_valid_modes,
    cli_names,
    legacy_provider_cli_aliases,
):
    merged = dict(
        default_provider(
            default_provider_id=default_provider_id,
            default_provider_protocols=default_provider_protocols,
            provider_capable_clis=provider_capable_clis,
        )
    )
    merged.update(provider)
    merged.pop("cost_level", None)
    merged.pop("daily_budget", None)
    merged["id"] = str(merged.get("id") or default_provider_id).strip() or default_provider_id
    merged["name"] = str(merged.get("name") or merged["id"]).strip() or merged["id"]

    protocols = merged.get("protocols", default_provider_protocols)
    if isinstance(protocols, str):
        protocols = [protocols]
    merged["protocols"] = [str(item).strip() for item in protocols if str(item).strip()]
    if not merged["protocols"]:
        merged["protocols"] = list(default_provider_protocols)

    merged["supported_clis"] = normalize_supported_clis(
        merged.get("supported_clis", provider_capable_clis),
        protocols=merged["protocols"],
        cli_names=cli_names,
        legacy_provider_cli_aliases=legacy_provider_cli_aliases,
    )
    if not merged["supported_clis"]:
        merged["supported_clis"] = list(provider_capable_clis)

    merged["enabled"] = bool(merged.get("enabled", True))
    merged["priority"] = normalize_priority(merged.get("priority", default_priority), default_priority=default_priority)
    merged["family_priority_overrides"] = normalize_family_priority_overrides(
        merged.get("family_priority_overrides", {}),
        model_families=model_families,
        default_priority=default_priority,
    )
    merged["claude_1m_mode"] = normalize_claude_1m_mode(
        merged.get("claude_1m_mode", "auto"),
        valid_modes=claude_1m_valid_modes,
    )
    merged["proxy"] = str(merged.get("proxy", "")).strip()
    merged["no_proxy"] = str(merged.get("no_proxy", "")).strip()
    merged["timezone"] = normalize_timezone_name(merged.get("timezone"), default=default_account_timezone)
    merged["force_ipv4"] = runtime_force_ipv4(merged)
    merged["note"] = str(merged.get("note", "")).strip()
    merged["default_openai_base_url"] = str(merged.get("default_openai_base_url", "")).strip().rstrip("/")
    merged["default_anthropic_base_url"] = str(merged.get("default_anthropic_base_url", "")).strip().rstrip("/")
    merged["fallback_models"] = normalize_model_id_list(merged.get("fallback_models", []))
    merged["extra_models"] = normalize_model_id_list(merged.get("extra_models", []))
    merged["hidden_models"] = normalize_model_id_list(merged.get("hidden_models", []))
    merged["models_endpoint"] = normalize_models_endpoint(merged.get("models_endpoint", "/models"))
    return merged


def default_account_home(account_id, *, accounts_dir):
    return os.path.join(accounts_dir, account_id)


def normalize_account(
    account,
    *,
    oauth_capable_clis,
    accounts_dir,
    default_priority,
    model_families,
    default_account_timezone,
    claude_1m_valid_modes,
):
    cli = str(account.get("cli") or "claude").strip().lower()
    if cli not in oauth_capable_clis:
        cli = "claude"
    account_id = normalize_account_id(account.get("id") or f"{cli}-account")
    default_home = default_account_home(account_id, accounts_dir=accounts_dir)
    home_dir = str(account.get("home_dir") or default_home).strip() or default_home
    proxy = str(account.get("proxy") or "").strip()
    no_proxy = str(account.get("no_proxy") or "").strip()
    timezone_name = normalize_timezone_name(account.get("timezone"), default=default_account_timezone)
    return {
        "id": account_id,
        "name": str(account.get("name") or account_id).strip() or account_id,
        "cli": cli,
        "auth_mode": "oauth",
        "enabled": bool(account.get("enabled", True)),
        "home_dir": os.path.expanduser(home_dir),
        "priority": normalize_priority(account.get("priority", default_priority), default_priority=default_priority),
        "family_priority_overrides": normalize_family_priority_overrides(
            account.get("family_priority_overrides", {}),
            model_families=model_families,
            default_priority=default_priority,
        ),
        "claude_1m_mode": normalize_claude_1m_mode(
            account.get("claude_1m_mode", "auto"),
            valid_modes=claude_1m_valid_modes,
        ),
        "proxy": proxy,
        "no_proxy": no_proxy,
        "timezone": timezone_name,
        "force_ipv4": runtime_force_ipv4(account),
        "note": str(account.get("note", "")).strip(),
    }


def normalize_account_id(account_id):
    value = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(account_id or "").strip().lower())
    value = value.strip("-_")
    return value or "account"


def account_label(account):
    return account.get("name", account.get("id", "account"))


def scrub_account_command_env(
    env,
    *,
    prefix_blocklist,
    proxy_env_keys,
    fake_env_keys,
    ca_env_keys,
):
    env = env if isinstance(env, dict) else {}
    for key in list(env.keys()):
        normalized = str(key or "").strip()
        if not normalized:
            continue
        if any(normalized.startswith(prefix) for prefix in prefix_blocklist):
            env.pop(key, None)
            continue
        if normalized in proxy_env_keys or normalized in fake_env_keys or normalized in ca_env_keys:
            env.pop(key, None)
    return env


def account_env(
    account,
    *,
    scrub_account_command_env,
    seed_claude_state,
    seed_agy_state,
    seed_gemini_state,
    environ=os.environ,
    expanduser=os.path.expanduser,
    path_join=os.path.join,
):
    home_dir = expanduser(str(account.get("home_dir", "")).strip())
    cli_name = account.get("cli")
    if cli_name == "claude":
        seed_claude_state(home_dir)
    elif cli_name == "agy":
        seed_agy_state(home_dir)
    env = dict(environ)
    scrub_account_command_env(env)
    if cli_name == "gemini":
        seed_gemini_state(home_dir)
        env["GEMINI_CLI_HOME"] = home_dir
    else:
        xdg_config_home = path_join(home_dir, ".config")
        env["HOME"] = home_dir
        env["XDG_CONFIG_HOME"] = xdg_config_home
    proxy = str(account.get("proxy", "")).strip()
    no_proxy = str(account.get("no_proxy", "")).strip()
    timezone_name = str(account.get("timezone", "")).strip()
    if proxy:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env[key] = proxy
        for key in ("NO_PROXY", "no_proxy"):
            env[key] = no_proxy
    if timezone_name:
        env["TZ"] = timezone_name
    env["MMS_ACCOUNT_ID"] = str(account.get("id", ""))
    return env


def account_status_command(cli_name):
    if cli_name == "claude":
        return ["claude", "auth", "status"]
    if cli_name == "codex":
        return ["codex", "login", "status"]
    if cli_name == "gemini":
        return None
    if cli_name == "agy":
        return None
    return None


def probe_account_status(
    account,
    *,
    account_env,
    account_status_command=account_status_command,
    expanduser=os.path.expanduser,
    path_exists=os.path.exists,
    path_isdir=os.path.isdir,
    run_command=subprocess.run,
):
    cli_name = account.get("cli")
    if cli_name == "claude":
        return {
            "state": "delegated",
            "summary": "Claude OAuth 独立入口已下线；MMS 不再探测或登录这个账号",
        }
    if cli_name == "gemini":
        home_dir = expanduser(str(account.get("home_dir", "")).strip())
        gemini_dir = os.path.join(home_dir, ".gemini")
        oauth_path = os.path.join(gemini_dir, "oauth_creds.json")
        accounts_path = os.path.join(gemini_dir, "google_accounts.json")
        settings_path = os.path.join(gemini_dir, "settings.json")
        if path_exists(oauth_path) or path_exists(accounts_path):
            return {
                "state": "configured",
                "summary": "已配置 OAuth，建议直接启动 Gemini 验证",
            }
        has_state = path_exists(settings_path)
        return {
            "state": "manual",
            "summary": "已初始化，待登录" if has_state else "待登录",
        }
    if cli_name == "agy":
        home_dir = expanduser(str(account.get("home_dir", "")).strip())
        agy_dir = os.path.join(home_dir, ".gemini", "antigravity-cli")
        settings_path = os.path.join(agy_dir, "settings.json")
        has_state = path_isdir(agy_dir) or path_exists(settings_path)
        return {
            "state": "manual",
            "summary": "已初始化，登录状态需启动 agy 验证" if has_state else "待登录",
        }
    command = account_status_command(cli_name)
    if command is None:
        return {"state": "unsupported", "summary": "不支持状态探测"}
    try:
        result = run_command(
            command,
            env=account_env(account),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        return {"state": "cli_missing", "summary": f"{cli_name} 未安装"}
    except subprocess.TimeoutExpired:
        return {"state": "timeout", "summary": "状态探测超时"}

    output_text = (result.stdout or result.stderr or "").strip()
    output = output_text.splitlines()
    summary = output[0].strip() if output else ""
    if cli_name == "claude" and output_text.startswith("{"):
        try:
            payload = json.loads(output_text)
            email = payload.get("email", "")
            sub = payload.get("subscriptionType", "")
            summary = " / ".join(part for part in [email, sub] if part) or summary
        except json.JSONDecodeError:
            pass
    if result.returncode == 0:
        return {"state": "logged_in", "summary": summary or "已登录"}
    return {"state": "logged_out", "summary": summary or "未登录"}


def run_account_login(
    account,
    *,
    account_env,
    account_label,
    makedirs=os.makedirs,
    run_command=subprocess.run,
    console,
):
    cli_name = account.get("cli")
    if cli_name == "claude":
        console.print("[yellow]Claude OAuth 独立入口已下线；请使用 provider/API route 启动 Claude。[/yellow]")
        return
    env = account_env(account)
    makedirs(account.get("home_dir", ""), exist_ok=True)
    if cli_name == "codex":
        command = ["codex", "login"]
    elif cli_name == "gemini":
        command = ["gemini"]
    elif cli_name == "agy":
        command = ["agy"]
    else:
        console.print(f"[red]不支持的官方账号类型: {cli_name}[/red]")
        sys.exit(1)
    env_hint = f"HOME={account.get('home_dir')}"
    if cli_name == "gemini":
        env_hint = f"GEMINI_CLI_HOME={account.get('home_dir')}"
    console.print(
        f"[cyan]正在为账号档案 {account_label(account)} 打开 {cli_name} 登录流程[/cyan]\n"
        f"[dim]{env_hint}[/dim]"
    )
    if cli_name == "gemini":
        console.print("[dim]Gemini 会在自己的 CLI 内引导 Google 登录；登录完成后按提示重启即可。[/dim]")
    if cli_name == "agy":
        console.print("[dim]Antigravity CLI 会在自己的流程内引导 Google 登录；登录完成后按提示重启即可。[/dim]")
    result = run_command(command, env=env)
    if result.returncode != 0:
        sys.exit(result.returncode)


def upsert_provider(cfg, provider, *, ensure_provider_config):
    providers = []
    replaced = False
    for item in cfg.get("providers", []):
        if item.get("id") == provider["id"]:
            providers.append(provider)
            replaced = True
        else:
            providers.append(item)
    if not replaced:
        providers.append(provider)

    updated_cfg = dict(cfg)
    updated_cfg["providers"] = providers
    updated_cfg, _ = ensure_provider_config(updated_cfg)
    return updated_cfg


def delete_provider_credentials(
    provider_id,
    *,
    credentials_path,
    load_env_file,
    provider_env_name,
    default_provider_id,
    api_url_env_name,
    api_key_env_name,
    shell_quote,
    path_exists=os.path.exists,
    chmod=os.chmod,
):
    if not path_exists(credentials_path):
        return
    values = load_env_file(credentials_path)
    keys_to_remove = {
        provider_env_name(provider_id, "BASE_URL"),
        provider_env_name(provider_id, "OPENAI_BASE_URL"),
        provider_env_name(provider_id, "ANTHROPIC_BASE_URL"),
        provider_env_name(provider_id, "API_KEY"),
    }
    if provider_id == default_provider_id:
        keys_to_remove.update({api_url_env_name, api_key_env_name})
    changed = False
    for key in keys_to_remove:
        if key in values:
            values.pop(key, None)
            changed = True
    if not changed:
        return
    lines = ["# Generated by MMS"]
    for key in sorted(values):
        lines.append(f"export {key}={shell_quote(str(values[key]))}")
    lines.append("")
    with open(credentials_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    chmod(credentials_path, 0o600)


def ensure_provider_config(cfg, *, default_provider_id, default_provider, normalize_provider):
    cfg = dict(cfg)
    raw_providers = cfg.get("providers")
    normalized = []
    seen_ids = set()

    if isinstance(raw_providers, list):
        for item in raw_providers:
            if not isinstance(item, dict):
                continue
            provider = normalize_provider(item)
            if provider["id"] in seen_ids:
                continue
            normalized.append(provider)
            seen_ids.add(provider["id"])

    if not normalized:
        normalized = [default_provider()]

    provider_cfg = cfg.get("provider", {})
    default_provider_value = default_provider_id
    if isinstance(provider_cfg, dict):
        default_provider_value = str(provider_cfg.get("default") or default_provider_id).strip() or default_provider_id
    if default_provider_value not in seen_ids and default_provider_value not in {p["id"] for p in normalized}:
        default_provider_value = normalized[0]["id"]

    new_cfg = dict(cfg)
    new_cfg["providers"] = normalized
    new_cfg["provider"] = {"default": default_provider_value}
    changed = new_cfg != cfg
    return new_cfg, changed


def ensure_account_config(cfg, *, oauth_capable_clis, normalize_account):
    cfg = dict(cfg)
    raw_accounts = cfg.get("accounts")
    normalized = []
    seen_ids = set()

    if isinstance(raw_accounts, list):
        for item in raw_accounts:
            if not isinstance(item, dict):
                continue
            account = normalize_account(item)
            if account["id"] in seen_ids:
                continue
            normalized.append(account)
            seen_ids.add(account["id"])

    raw_defaults = cfg.get("account", {})
    defaults = {}
    if isinstance(raw_defaults, dict):
        raw_cli_defaults = raw_defaults.get("defaults", raw_defaults)
        if isinstance(raw_cli_defaults, dict):
            for cli in oauth_capable_clis:
                account_id = str(raw_cli_defaults.get(cli, "")).strip()
                if account_id:
                    defaults[cli] = account_id

    defaults = {
        cli: account_id for cli, account_id in defaults.items()
        if account_id in seen_ids
    }

    new_cfg = dict(cfg)
    new_cfg["accounts"] = normalized
    new_cfg["account"] = {"defaults": defaults}
    changed = new_cfg != cfg
    return new_cfg, changed


def normalize_preset_entry(name, preset, *, normalize_account_id=normalize_account_id):
    if isinstance(preset, str):
        preset = {"cli": "claude", "model": preset}
    elif not isinstance(preset, dict):
        preset = {"cli": "claude"}

    normalized = {"cli": str(preset.get("cli") or "claude").strip().lower() or "claude"}

    description = str(preset.get("description") or "").strip()
    if description:
        normalized["description"] = description

    provider = str(preset.get("provider") or "").strip()
    if provider:
        normalized["provider"] = provider

    account = str(preset.get("account") or "").strip()
    if account:
        normalized["account"] = normalize_account_id(account)

    bridge = str(preset.get("bridge") or "").strip()
    if bridge:
        normalized["bridge"] = bridge

    model = str(preset.get("model") or "").strip()
    if not model:
        for legacy_key in ("sonnet", "opus", "haiku"):
            value = str(preset.get(legacy_key) or "").strip()
            if value:
                model = value
                break
    if model:
        normalized["model"] = model

    for key, value in preset.items():
        if key in {"cli", "description", "provider", "account", "bridge", "model", "sonnet", "opus", "haiku"}:
            continue
        normalized[key] = value

    return normalized


def normalize_presets_config(cfg, *, normalize_preset_entry=normalize_preset_entry):
    raw_presets = cfg.get("presets")
    if raw_presets is None:
        return cfg, False
    if not isinstance(raw_presets, dict):
        updated = dict(cfg)
        updated["presets"] = {}
        return updated, True

    normalized = {}
    changed = False
    for name, preset in raw_presets.items():
        normalized_name = str(name).strip()
        if not normalized_name:
            changed = True
            continue
        normalized_preset = normalize_preset_entry(normalized_name, preset)
        normalized[normalized_name] = normalized_preset
        if normalized_name != name or normalized_preset != preset:
            changed = True

    if not changed:
        return cfg, False

    updated = dict(cfg)
    updated["presets"] = normalized
    return updated, True


def normalize_user_config(cfg, *, mode_all, normalize_user_role):
    user_cfg = cfg.get("user", {})
    if not isinstance(user_cfg, dict):
        new_cfg = dict(cfg)
        new_cfg["user"] = {"role": mode_all}
        return new_cfg, True

    normalized_role = normalize_user_role(user_cfg.get("role", mode_all))
    if user_cfg.get("role") == normalized_role:
        return cfg, False

    new_cfg = dict(cfg)
    new_user = dict(user_cfg)
    new_user["role"] = normalized_role
    new_cfg["user"] = new_user
    return new_cfg, True


def normalize_cache_config(
    cfg,
    *,
    probe_async_refresh_after,
    probe_async_min_interval,
    normalize_positive_seconds=normalize_positive_seconds,
):
    cache_cfg = cfg.get("cache", {})
    if not isinstance(cache_cfg, dict):
        cache_cfg = {}

    normalized = {
        "probe_async_refresh_after_sec": normalize_positive_seconds(
            cache_cfg.get("probe_async_refresh_after_sec", probe_async_refresh_after),
            probe_async_refresh_after,
        ),
        "probe_async_min_interval_sec": normalize_positive_seconds(
            cache_cfg.get("probe_async_min_interval_sec", probe_async_min_interval),
            probe_async_min_interval,
        ),
    }

    if cache_cfg == normalized:
        return cfg, False

    new_cfg = dict(cfg)
    new_cfg["cache"] = normalized
    return new_cfg, True


def probe_async_refresh_after(cfg, *, default, normalize_positive_seconds=normalize_positive_seconds):
    if isinstance(cfg, dict):
        cache_cfg = cfg.get("cache", {})
        if isinstance(cache_cfg, dict):
            return normalize_positive_seconds(
                cache_cfg.get("probe_async_refresh_after_sec", default),
                default,
            )
    return default


def probe_async_min_interval(cfg, *, default, normalize_positive_seconds=normalize_positive_seconds):
    if isinstance(cfg, dict):
        cache_cfg = cfg.get("cache", {})
        if isinstance(cache_cfg, dict):
            return normalize_positive_seconds(
                cache_cfg.get("probe_async_min_interval_sec", default),
                default,
            )
    return default


def ensure_probe_async_executor(current_executor, *, set_executor, executor_factory):
    if current_executor is None:
        current_executor = executor_factory()
        set_executor(current_executor)
    return current_executor


def schedule_probe_refresh(
    provider,
    cfg=None,
    *,
    reason="stale",
    default_provider_id,
    probe_async_min_interval,
    lock,
    inflight,
    last_started,
    probe_models,
    ensure_probe_async_executor,
    time_func,
):
    provider_id = provider.get("id", default_provider_id)
    min_interval = probe_async_min_interval(cfg)

    with lock:
        if provider_id in inflight:
            return False
        last_at = last_started.get(provider_id, 0)
        if time_func() - last_at < min_interval:
            return False
        inflight.add(provider_id)
        last_started[provider_id] = time_func()

    def _runner():
        try:
            probe_models(provider, emit_output=False, skip_cache=True)
        except Exception:
            pass
        finally:
            with lock:
                inflight.discard(provider_id)

    ensure_probe_async_executor().submit(_runner)
    return True


def snapshot_diff_lines(previous_snapshot, current_snapshot, *, is_snapshot_ignored_file):
    diffs = []
    previous_snapshot = previous_snapshot if isinstance(previous_snapshot, dict) else {}
    current_snapshot = current_snapshot if isinstance(current_snapshot, dict) else {}

    previous_defaults = previous_snapshot.get("defaults") or {}
    current_defaults = current_snapshot.get("defaults") or {}
    if previous_defaults != current_defaults:
        diffs.append("default route/account changed")

    previous_accounts = {
        str(item.get("id") or "").strip(): item
        for item in previous_snapshot.get("accounts", [])
        if isinstance(item, dict)
    }
    current_accounts = {
        str(item.get("id") or "").strip(): item
        for item in current_snapshot.get("accounts", [])
        if isinstance(item, dict)
    }
    for account_id in sorted(set(previous_accounts) | set(current_accounts)):
        previous_entry = previous_accounts.get(account_id)
        current_entry = current_accounts.get(account_id)
        if previous_entry is None:
            diffs.append(f"account added: {account_id}")
            continue
        if current_entry is None:
            diffs.append(f"account removed: {account_id}")
            continue
        field_labels = {
            "cli": "cli",
            "enabled": "enabled",
            "home_dir": "home_dir",
            "priority": "priority",
            "claude_1m_mode": "claude_1m_mode",
            "timezone": "timezone",
            "force_ipv4": "force_ipv4",
            "no_proxy": "no_proxy",
            "proxy_sha256": "proxy",
            "identity_sha256": "identity",
        }
        for field_name, field_label in field_labels.items():
            if field_name == "identity_sha256":
                previous_value = previous_entry.get(field_name, "")
                current_value = current_entry.get(field_name, "")
            else:
                previous_value = previous_entry.get(field_name)
                current_value = current_entry.get(field_name)
            if field_name == "identity_sha256" and field_name not in previous_entry:
                continue
            if previous_value != current_value:
                if field_name == "proxy_sha256":
                    old_value = previous_entry.get("proxy_fingerprint")
                    new_value = current_entry.get("proxy_fingerprint")
                elif field_name == "identity_sha256":
                    old_value = previous_entry.get("identity_fingerprint")
                    new_value = current_entry.get("identity_fingerprint")
                else:
                    old_value = previous_entry.get(field_name)
                    new_value = current_entry.get(field_name)
                diffs.append(f"account {account_id} {field_label}: {old_value} -> {new_value}")

    previous_providers = {
        str(item.get("id") or "").strip(): item
        for item in previous_snapshot.get("providers", [])
        if isinstance(item, dict)
    }
    current_providers = {
        str(item.get("id") or "").strip(): item
        for item in current_snapshot.get("providers", [])
        if isinstance(item, dict)
    }
    for provider_id in sorted(set(previous_providers) | set(current_providers)):
        previous_entry = previous_providers.get(provider_id)
        current_entry = current_providers.get(provider_id)
        if previous_entry is None:
            diffs.append(f"provider added: {provider_id}")
            continue
        if current_entry is None:
            diffs.append(f"provider removed: {provider_id}")
            continue
        field_labels = {
            "enabled": "enabled",
            "priority": "priority",
            "models_endpoint": "models_endpoint",
            "timezone": "timezone",
            "force_ipv4": "force_ipv4",
            "no_proxy": "no_proxy",
            "proxy_sha256": "proxy",
        }
        for field_name, field_label in field_labels.items():
            if previous_entry.get(field_name) != current_entry.get(field_name):
                old_value = previous_entry.get("proxy_fingerprint") if field_name == "proxy_sha256" else previous_entry.get(field_name)
                new_value = current_entry.get("proxy_fingerprint") if field_name == "proxy_sha256" else current_entry.get(field_name)
                diffs.append(f"provider {provider_id} {field_label}: {old_value} -> {new_value}")

    previous_files = {
        str(item.get("path") or ""): item
        for item in previous_snapshot.get("files", [])
        if isinstance(item, dict) and not is_snapshot_ignored_file(item.get("path"))
    }
    current_files = {
        str(item.get("path") or ""): item
        for item in current_snapshot.get("files", [])
        if isinstance(item, dict) and not is_snapshot_ignored_file(item.get("path"))
    }
    for path in sorted(set(previous_files) | set(current_files)):
        if os.path.basename(str(path or "")) == ".claude.json":
            continue
        previous_entry = previous_files.get(path)
        current_entry = current_files.get(path)
        if previous_entry is None:
            diffs.append(f"file added: {path}")
            continue
        if current_entry is None:
            diffs.append(f"file removed: {path}")
            continue
        if bool(previous_entry.get("exists")) != bool(current_entry.get("exists")):
            diffs.append(f"file presence changed: {path}")
            continue
        if previous_entry.get("sha256") != current_entry.get("sha256"):
            diffs.append(f"file changed: {path}")
    return diffs


def runtime_force_ipv4(runtime):
    raw = False if not isinstance(runtime, dict) else runtime.get("force_ipv4", False)
    if isinstance(raw, bool):
        return raw
    value = str(raw or "").strip().lower()
    if value in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    if value in {"1", "true", "yes", "on", "enable", "enabled", ""}:
        return True
    return False


def url_matches_host_suffix(url, host_suffixes):
    raw = str(url or "").strip()
    if not raw:
        return False
    try:
        host = (urlparse(raw).hostname or "").strip().lower()
    except Exception:
        host = ""
    if not host:
        return False
    for suffix in host_suffixes:
        normalized = str(suffix or "").strip().lower().lstrip(".")
        if not normalized:
            continue
        if host == normalized or host.endswith("." + normalized):
            return True
    return False


def runtime_should_disable_ambient_env(
    runtime,
    *,
    target_url="",
    official_hosts,
    url_matches_host_suffix=url_matches_host_suffix,
):
    runtime = runtime if isinstance(runtime, dict) else {}
    if str(runtime.get("proxy") or "").strip():
        return True
    return url_matches_host_suffix(target_url, official_hosts)


def runtime_httpx_kwargs(
    runtime,
    *,
    target_url="",
    official_hosts,
    runtime_force_ipv4=runtime_force_ipv4,
    runtime_should_disable_ambient_env=runtime_should_disable_ambient_env,
):
    transport_kwargs = {}
    proxy_url = str((runtime or {}).get("proxy") or "").strip()
    if proxy_url:
        transport_kwargs["proxy"] = proxy_url
    if runtime_should_disable_ambient_env(runtime, target_url=target_url, official_hosts=official_hosts):
        transport_kwargs["trust_env"] = False
    if runtime_force_ipv4(runtime):
        transport_kwargs["local_address"] = "0.0.0.0"
    return transport_kwargs


def validate_proxy_url(proxy_url, *, supported_proxy_schemes):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return None
    try:
        parsed = urlparse(proxy_url)
    except Exception:
        return "代理地址解析失败"
    if parsed.scheme.lower() not in supported_proxy_schemes:
        return "代理协议仅支持 http / https / socks5 / socks5h"
    if not parsed.hostname:
        return "代理地址缺少 host"
    if parsed.port is None:
        return "代理地址缺少 port"
    return None


def test_proxy_connectivity(
    proxy_url,
    no_proxy="",
    target_url="https://api.anthropic.com",
    force_ipv4=True,
    *,
    http_status_is_success,
    which=shutil.which,
    run_command=subprocess.run,
):
    proxy_url = str(proxy_url or "").strip()
    if not proxy_url:
        return True, "未配置代理，跳过检测"
    curl_bin = which("curl")
    if not curl_bin:
        return False, "当前系统没有 curl，无法测试代理连通性"
    cmd = [
        curl_bin,
        *(["-4"] if force_ipv4 else []),
        "--silent",
        "--show-error",
        "--head",
        "--location",
        "--max-time",
        "8",
        "--output",
        "/dev/null",
        "--write-out",
        "%{http_code}",
        "--proxy",
        proxy_url,
        target_url,
    ]
    if str(no_proxy or "").strip():
        cmd.extend(["--noproxy", str(no_proxy).strip()])
    result = run_command(cmd, capture_output=True, text=True)
    http_code = str(result.stdout or "").strip()
    if result.returncode == 0 and http_status_is_success(http_code):
        return True, f"代理连通性测试通过：{target_url} (HTTP {http_code})"
    detail = (result.stderr or "").strip()
    if http_code and http_code not in {"000"}:
        detail = f"HTTP {http_code}" + (f" · {detail}" if detail else "")
    if len(detail) > 200:
        detail = detail[:200] + "..."
    return False, detail or f"代理连通性测试失败：{target_url}"


def prompt_validated_proxy_fields(
    current_proxy="",
    current_no_proxy="",
    *,
    wizard=False,
    target_url="https://api.anthropic.com",
    wizard_prompt,
    prompt_ask,
    localize,
    validate_proxy_url,
    test_proxy_connectivity,
    confirm_ask,
    console,
):
    prompt_fn = wizard_prompt if wizard else prompt_ask
    proxy_label = "代理地址（可选，直接回车跳过；例 http://127.0.0.1:7890 / socks5h://127.0.0.1:7890）"
    no_proxy_label = "NO_PROXY（可选，直接回车跳过）"
    while True:
        proxy = prompt_fn(
            localize(proxy_label, "Proxy URL (optional, press Enter to skip; e.g. http://127.0.0.1:7890 / socks5h://127.0.0.1:7890)"),
            default=current_proxy or "",
        ).strip()
        error = validate_proxy_url(proxy)
        if error:
            console.print(f"[red]{error}[/red]")
            continue
        if not proxy:
            return "", ""
        no_proxy = prompt_fn(localize(no_proxy_label, "NO_PROXY (optional, press Enter to skip)"), default=current_no_proxy or "").strip()
        if proxy:
            console.print(f"[dim]正在测试代理连通性: {target_url}[/dim]")
            ok, detail = test_proxy_connectivity(
                proxy,
                no_proxy=no_proxy,
                target_url=target_url,
                force_ipv4=True,
            )
            if ok:
                console.print(f"[green]✓ {detail}[/green]")
                return proxy, no_proxy
            console.print(
                f"[yellow]代理测试未通过[/yellow]\n"
                f"[dim]{detail}[/dim]\n"
                f"[dim]这可能是 proxy 不通，也可能是当前代理策略不放行 {target_url}。[/dim]"
            )
            if confirm_ask("仍然保存这个代理配置？", default=False):
                return proxy, no_proxy
            current_proxy = proxy
            current_no_proxy = no_proxy
            continue
        return proxy, no_proxy


def prompt_validated_timezone(
    current_timezone="",
    *,
    wizard=False,
    default_account_timezone,
    wizard_prompt,
    prompt_ask,
    localize,
    zone_info_cls,
    console,
):
    prompt_fn = wizard_prompt if wizard else prompt_ask
    label = localize(
        f"启动时区（默认 {default_account_timezone}）",
        f"Launch timezone (default {default_account_timezone})",
    )
    while True:
        timezone_name = prompt_fn(label, default=current_timezone or default_account_timezone).strip()
        try:
            zone_info_cls(timezone_name)
            return timezone_name
        except Exception:
            console.print(f"[red]无效时区: {timezone_name}[/red]")


def normalize_user_role(role, *, mode_all, mode_recommended):
    value = str(role or "").strip()
    if value in {"dev", "all", mode_all}:
        return mode_all
    if value in {"ops", "recommended", mode_recommended}:
        return mode_recommended
    return mode_all


def runtime_usage_key(runtime, cli_name):
    kind = runtime.get("runtime_kind", "provider")
    runtime_id = runtime.get("id", "default")
    return f"{kind}:{cli_name}:{runtime_id}"


def resolve_model_name(model_info):
    if isinstance(model_info, dict):
        for key in ("model", "sonnet", "opus", "haiku"):
            value = model_info.get(key)
            if value:
                return str(value)
        return "official-default"
    return str(model_info or "official-default")


def runtime_hint_from_runtime(runtime, *, runtime_provider_id, runtime_account_id):
    if not isinstance(runtime, dict):
        return {}
    hint = {
        "runtime_kind": str(runtime.get("runtime_kind", "")).strip(),
        "auth_mode": str(runtime.get("auth_mode", "")).strip(),
    }
    provider_id = runtime_provider_id(runtime)
    account_id = runtime_account_id(runtime)
    runtime_id = str(runtime.get("id") or "").strip()
    if provider_id:
        hint["provider_id"] = provider_id
    if account_id:
        hint["account_id"] = account_id
    if runtime_id:
        hint["runtime_id"] = runtime_id
    return {k: v for k, v in hint.items() if v}


def record_usage(
    runtime,
    cli_name,
    model_info,
    *,
    update_usage_stats,
    iso_now,
    runtime_usage_key=runtime_usage_key,
    resolve_model_name=resolve_model_name,
    runtime_hint_from_runtime,
):
    def _mutate(stats):
        sources = stats.setdefault("sources", {})
        key = runtime_usage_key(runtime, cli_name)
        model_name = resolve_model_name(model_info)
        now = iso_now()
        entry = sources.setdefault(key, {
            "runtime_kind": runtime.get("runtime_kind", "provider"),
            "id": runtime.get("id", "default"),
            "name": runtime.get("name", runtime.get("id", "default")),
            "cli": cli_name,
            "launches": 0,
            "last_used_at": "",
            "last_model": "",
            "models": {},
            "model_last_used_at": {},
        })
        entry["launches"] += 1
        entry["last_used_at"] = now
        entry["last_model"] = model_name
        models = entry.setdefault("models", {})
        models[model_name] = int(models.get(model_name, 0)) + 1
        model_last_used_at = entry.setdefault("model_last_used_at", {})
        model_last_used_at[model_name] = now
        last_by_cli = stats.setdefault("last_by_cli", {})
        last_by_cli[cli_name] = {
            "cli": cli_name,
            "model": model_name,
            "model_info": model_info if isinstance(model_info, dict) else {"model": str(model_info)},
            "runtime_hint": runtime_hint_from_runtime(runtime),
            "last_used_at": now,
        }

    update_usage_stats(_mutate)


def record_scene_usage(
    scene_name,
    cli_name,
    model_info,
    *,
    update_usage_stats,
    iso_now,
    resolve_model_name=resolve_model_name,
):
    if not scene_name or str(scene_name).startswith("__"):
        return

    def _mutate(stats):
        scene_stats = stats.setdefault("scenes", {})
        model_name = resolve_model_name(model_info)
        entry = scene_stats.setdefault(scene_name, {
            "launches": 0,
            "last_used_at": "",
            "last_cli": "",
            "last_model": "",
        })
        entry["launches"] += 1
        entry["last_used_at"] = iso_now()
        entry["last_cli"] = cli_name
        entry["last_model"] = model_name

    update_usage_stats(_mutate)


def infer_runtime_hint_from_usage_stats(stats, cli_name, model_name):
    latest_entry = None
    latest_at = ""
    normalized_model = str(model_name or "").strip()
    for entry in (stats.get("sources", {}) or {}).values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("cli") or "").strip() != str(cli_name or "").strip():
            continue
        if str(entry.get("last_model") or "").strip() != normalized_model:
            continue
        used_at = str(entry.get("last_used_at") or "").strip()
        if used_at < latest_at:
            continue
        latest_at = used_at
        latest_entry = entry

    if not isinstance(latest_entry, dict):
        return {}

    runtime_kind = str(latest_entry.get("runtime_kind") or "").strip()
    runtime_id = str(latest_entry.get("id") or "").strip()
    if not runtime_kind or not runtime_id:
        return {}

    hint = {
        "runtime_kind": runtime_kind,
        "runtime_id": runtime_id,
    }
    if runtime_kind == "provider":
        hint["auth_mode"] = "api_key"
        hint["provider_id"] = runtime_id
    elif runtime_kind == "account":
        hint["auth_mode"] = "oauth"
        hint["account_id"] = runtime_id
    else:
        return {}
    return hint


def get_scene_usage(
    *,
    load_usage_stats,
    resolve_model_name=resolve_model_name,
    infer_runtime_hint_from_usage_stats=infer_runtime_hint_from_usage_stats,
):
    stats = load_usage_stats()
    scene_counts = {}
    for name, entry in stats.get("scenes", {}).items():
        scene_counts[name] = entry.get("launches", 0)
    last_by_cli = {}
    for cli_name, item in (stats.get("last_by_cli", {}) or {}).items():
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        if not isinstance(normalized.get("runtime_hint"), dict):
            model_name = resolve_model_name(
                normalized.get("model_info") if isinstance(normalized.get("model_info"), dict) else normalized.get("model")
            )
            inferred = infer_runtime_hint_from_usage_stats(stats, cli_name, model_name)
            if inferred:
                normalized["runtime_hint"] = inferred
        last_by_cli[cli_name] = normalized
    return last_by_cli, scene_counts


def resolve_last_used_runtime(
    cfg,
    cli_name,
    last_item,
    default_models,
    *,
    resolve_model_name=resolve_model_name,
    resolve_provider_context,
    provider_supports_model_for_cli,
    probe_models,
    provider_effective_models,
    runtime_with_priority,
    resolve_account_context,
    model_matches_account_cli,
):
    if not isinstance(last_item, dict):
        return None, None, None

    hint = last_item.get("runtime_hint")
    if not isinstance(hint, dict):
        return None, None, None

    model_info = last_item.get("model_info") if isinstance(last_item.get("model_info"), dict) else {
        "model": str(last_item.get("model") or "")
    }
    model_name = resolve_model_name(model_info)

    provider_id = str(hint.get("provider_id") or "").strip()
    if provider_id:
        try:
            provider = resolve_provider_context(cfg, provider_id)
        except Exception:
            provider = None
        if provider and provider_supports_model_for_cli(provider, cli_name, model_name):
            models = probe_models(provider, emit_output=False).get("models")
            models = provider_effective_models(provider, models, cfg)
            if str(model_name or "").strip().lower() in {
                str(item or "").strip().lower() for item in (models or [])
            }:
                return (
                    runtime_with_priority(provider, model_name=model_name),
                    models,
                    f"last used provider:{provider_id}",
                )

    auth_mode = str(hint.get("auth_mode") or "").strip()
    account_id = str(hint.get("account_id") or "").strip()
    if account_id and auth_mode != "oauth_bridge":
        try:
            account = resolve_account_context(cfg, account_id=account_id, cli_name=cli_name)
        except Exception:
            account = None
        if account and model_matches_account_cli(cli_name, model_name):
            return (
                runtime_with_priority(account, model_name=model_name),
                list(default_models or []),
                f"last used account:{account_id}",
            )

    return None, None, None


def all_provider_models_for_cli(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    provider_candidates,
    provider_has_configured_base_url,
    provider_effective_models,
    mms_model_visible,
    provider_supports_model_for_cli,
):
    merged = []
    seen = set()
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if not provider_has_configured_base_url(provider) or not provider.get("api_key"):
            continue
        models = provider_effective_models(provider, cached_models, cfg)
        for model_name in models:
            normalized = str(model_name or "").strip()
            if not normalized or normalized in seen:
                continue
            if not mms_model_visible(normalized):
                continue
            if not provider_supports_model_for_cli(provider, cli_name, normalized):
                continue
            seen.add(normalized)
            merged.append(normalized)
    return merged


def aggregate_provider_models(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    provider_candidates,
    provider_has_configured_base_url,
    provider_effective_models,
    provider_label,
    mms_model_visible,
    provider_supports_model_for_cli,
    default_provider_id,
):
    aggregated = []
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if not provider_has_configured_base_url(provider) or not provider.get("api_key"):
            continue
        models = provider_effective_models(provider, cached_models, cfg)
        provider_id = provider.get("id", default_provider_id)
        provider_name = provider_label(provider)
        for model_name in models:
            normalized = str(model_name or "").strip()
            if not normalized:
                continue
            if not mms_model_visible(normalized):
                continue
            if not provider_supports_model_for_cli(provider, cli_name, normalized):
                continue
            aggregated.append({
                "model": normalized,
                "provider_id": provider_id,
                "provider_name": provider_name,
            })
    return aggregated


def categorize_models(models, *, filter_visible_models, infer_model_family):
    categorized = {}
    for model_name in filter_visible_models(models):
        _, category = infer_model_family(model_name)
        categorized.setdefault(category, []).append(model_name)
    return categorized


def display_models(
    models,
    role,
    recommend,
    *,
    ensure_rich,
    categorize_models,
    normalize_user_role,
    mode_recommended,
    model_capability_summary,
    model_cli_summary,
    table_cls,
    console,
):
    ensure_rich()
    categorized = categorize_models(models)
    table = table_cls(title="可用模型", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("模型", style="green")
    table.add_column("分类", style="yellow")
    table.add_column("能力", style="magenta")
    table.add_column("CLI", style="dim")

    flat = []
    for category, category_models in categorized.items():
        for model_name in category_models:
            flat.append((model_name, category))

    if normalize_user_role(role) == mode_recommended and recommend:
        flat = [(model_name, category) for model_name, category in flat if model_name in recommend]

    for index, (model_name, category) in enumerate(flat, 1):
        tag = " ⭐" if recommend and model_name in recommend else ""
        table.add_row(
            str(index),
            model_name + tag,
            category,
            model_capability_summary(model_name),
            model_cli_summary(model_name),
        )

    console.print(table)
    return [model_name for model_name, _ in flat]


def filter_models_for_display(models, role, recommend, *, categorize_models, normalize_user_role, mode_recommended):
    categorized = categorize_models(models)
    flat = []
    for category, category_models in categorized.items():
        for model_name in category_models:
            flat.append((model_name, category))
    if normalize_user_role(role) == mode_recommended and recommend:
        allowed = set(recommend)
        flat = [(model_name, category) for model_name, category in flat if model_name in allowed]
    return flat


def group_models_for_custom(models, role, recommend, *, filter_models_for_display, infer_model_family):
    grouped = {}
    order = []
    for model_name, _ in filter_models_for_display(models, role, recommend):
        family, _ = infer_model_family(model_name)
        if family not in grouped:
            grouped[family] = []
            order.append(family)
        grouped[family].append(model_name)
    return [(family, grouped[family]) for family in order]


def group_models_by_family_and_provider(
    aggregated_models,
    role,
    recommend,
    *,
    filter_models_for_display,
    infer_model_family,
):
    plain_models = [entry["model"] for entry in aggregated_models]
    allowed = {
        model_name for model_name, _ in filter_models_for_display(plain_models, role, recommend)
    }

    family_order = []
    family_providers = {}
    for entry in aggregated_models:
        model_name = entry["model"]
        if model_name not in allowed:
            continue
        family, _ = infer_model_family(model_name)
        provider_key = f"{entry['provider_name']}||{entry['provider_id']}"

        if family not in family_providers:
            family_providers[family] = {}
            family_order.append(family)
        providers = family_providers[family]
        providers.setdefault(provider_key, [])
        if model_name not in providers[provider_key]:
            providers[provider_key].append(model_name)

    return [(family, dict(family_providers[family])) for family in family_order]


def select_custom_model(
    models,
    cli_name,
    role="all",
    recommend=None,
    use_tui=False,
    *,
    group_models_by_family_and_provider,
    group_models_for_custom,
    table_cls,
    int_prompt_cls,
    console,
    exit_func,
    select_model_tui=None,
):
    """Select model by family, provider, then model; supports legacy and aggregated inputs."""
    is_aggregated = models and isinstance(models[0], dict)

    if is_aggregated:
        groups = group_models_by_family_and_provider(models, role, recommend)
    else:
        plain_groups = group_models_for_custom(models, role, recommend)
        groups = [(family, {"_default_||_default_": items}) for family, items in plain_groups]

    if not groups:
        return (None, None) if is_aggregated else None

    if use_tui and select_model_tui is None:
        from mms_display.tui import select_model_tui as select_model_tui_impl

        select_model_tui = select_model_tui_impl

    if len(groups) == 1:
        selected_family, provider_map = groups[0]
    else:
        total_per_family = []
        for family, pmap in groups:
            count = sum(len(m) for m in pmap.values())
            total_per_family.append(count)
        family_labels = [f"{family} ({total_per_family[i]})" for i, (family, _) in enumerate(groups)]
        if use_tui:
            selected_label = select_model_tui(family_labels, title=f"为 {cli_name} 选择模型品牌")
            if selected_label is None:
                return (None, None) if is_aggregated else None
            family_index = family_labels.index(selected_label)
        else:
            family_index = None
            while family_index is None:
                table = table_cls(title=f"{cli_name} · 选择模型品牌", show_lines=True)
                table.add_column("#", style="cyan", width=4)
                table.add_column("品牌", style="green")
                table.add_column("数量", style="yellow", width=6)
                for idx, (family, _) in enumerate(groups, 1):
                    table.add_row(str(idx), family, str(total_per_family[idx - 1]))
                console.print(table)
                try:
                    picked = int_prompt_cls.ask("选择模型品牌编号") - 1
                except KeyboardInterrupt:
                    exit_func(0)
                if 0 <= picked < len(groups):
                    family_index = picked
                else:
                    console.print(f"[red]请输入 1-{len(groups)}[/red]")
        selected_family, provider_map = groups[family_index]

    provider_keys = list(provider_map.keys())
    if len(provider_keys) == 1:
        selected_provider_key = provider_keys[0]
    else:
        provider_labels = []
        for key in provider_keys:
            label, _ = key.split("||", 1)
            count = len(provider_map[key])
            provider_labels.append(f"{label} ({count})")
        if use_tui:
            selected_label = select_model_tui(provider_labels, title=f"{selected_family} · 选择 Provider")
            if selected_label is None:
                return (None, None) if is_aggregated else None
            provider_index = provider_labels.index(selected_label)
        else:
            provider_index = None
            while provider_index is None:
                table = table_cls(title=f"{cli_name} · {selected_family} · 选择 Provider", show_lines=True)
                table.add_column("#", style="cyan", width=4)
                table.add_column("Provider", style="green")
                table.add_column("模型数", style="yellow", width=6)
                for idx, plabel in enumerate(provider_labels, 1):
                    table.add_row(str(idx), plabel, "")
                console.print(table)
                try:
                    picked = int_prompt_cls.ask("选择 Provider 编号") - 1
                except KeyboardInterrupt:
                    exit_func(0)
                if 0 <= picked < len(provider_keys):
                    provider_index = picked
                else:
                    console.print(f"[red]请输入 1-{len(provider_keys)}[/red]")
        selected_provider_key = provider_keys[provider_index]

    family_models = provider_map[selected_provider_key]
    _, selected_provider_id = selected_provider_key.split("||", 1)

    if use_tui:
        model = select_model_tui(family_models, title=f"{selected_family} · 选择子模型")
    else:
        model = None
        while model is None:
            table = table_cls(title=f"{cli_name} · {selected_family}", show_lines=True)
            table.add_column("#", style="cyan", width=4)
            table.add_column("模型", style="green")
            for idx, model_name in enumerate(family_models, 1):
                table.add_row(str(idx), model_name)
            console.print(table)
            try:
                model_index = int_prompt_cls.ask("选择子模型编号") - 1
            except KeyboardInterrupt:
                exit_func(0)
            if 0 <= model_index < len(family_models):
                model = family_models[model_index]
            else:
                console.print(f"[red]请输入 1-{len(family_models)}[/red]")

    if is_aggregated:
        pid = selected_provider_id if selected_provider_id != "_default_" else None
        return (model, pid) if model else (None, None)
    return model


def select_model_interactive(models_list, *, int_prompt_cls, console, exit_func):
    while True:
        try:
            choice = int_prompt_cls.ask("选择模型编号")
            if 1 <= choice <= len(models_list):
                return models_list[choice - 1]
            console.print(f"[red]请输入 1-{len(models_list)}[/red]")
        except KeyboardInterrupt:
            exit_func(0)


def build_provider_options_map(
    cfg,
    cli_name,
    default_provider,
    default_models,
    model_names,
    *,
    infer_model_family,
    provider_candidates,
    provider_has_configured_base_url,
    provider_effective_models,
    provider_supports_model_for_cli,
    runtime_with_priority,
    provider_label,
    account_options_for_model,
    default_provider_id,
):
    result = {}
    for model_name in model_names:
        selected_family, _ = infer_model_family(model_name)
        options = []
        for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
            if not provider.get("enabled", True):
                continue
            if not provider_has_configured_base_url(provider):
                continue
            if not provider.get("api_key"):
                continue
            models = provider_effective_models(provider, cached_models, cfg)
            model_lower = [str(item or "").strip().lower() for item in models]
            if model_name.strip().lower() not in model_lower:
                continue
            if not provider_supports_model_for_cli(provider, cli_name, model_name):
                continue
            runtime = runtime_with_priority(provider, model_name=model_name, family_name=selected_family)
            options.append({
                "provider_name": provider_label(provider),
                "provider_id": provider.get("id", default_provider_id),
                "priority_family": selected_family,
                "provider_ctx": runtime,
            })
        account_options = account_options_for_model(
            cfg,
            cli_name,
            default_models,
            model_info={"model": model_name},
            allow_selected_model=True,
        )
        for option in account_options:
            runtime = option.get("runtime") or {}
            options.append({
                "provider_name": f"{option.get('title', runtime.get('id', 'account'))} OAuth",
                "provider_id": runtime.get("id", ""),
                "priority_family": option.get("priority_family", selected_family),
                "provider_ctx": runtime,
            })
        if len(options) > 1:
            result[model_name] = options
    return result


def make_provider_options_loader(cfg, cli_name, default_provider, default_models, *, build_provider_options_map):
    cache = {}

    def _loader(model_name):
        key = str(model_name or "").strip()
        if not key:
            return []
        if key not in cache:
            cache[key] = build_provider_options_map(
                cfg, cli_name, default_provider, default_models, [key]
            ).get(key, [])
        return cache[key]

    return _loader


def apply_runtime_priority_changes(
    cfg,
    pri_changes,
    *,
    canonical_model_family,
    normalize_family_priority_overrides,
    normalize_priority,
):
    changed = False
    if not pri_changes:
        return changed

    for runtime_id, new_priority in pri_changes.items():
        family_name = ""
        actual_runtime_id = runtime_id
        if "||" in str(runtime_id):
            actual_runtime_id, family_name = str(runtime_id).split("||", 1)
            family_name = canonical_model_family(family_name)
        matched = False
        for provider_def in cfg.get("providers", []):
            if provider_def.get("id") == actual_runtime_id:
                if family_name:
                    overrides = normalize_family_priority_overrides(
                        provider_def.get("family_priority_overrides", {})
                    )
                    overrides[family_name] = normalize_priority(new_priority)
                    provider_def["family_priority_overrides"] = overrides
                else:
                    provider_def["priority"] = normalize_priority(new_priority)
                changed = True
                matched = True
                break
        if matched:
            continue
        for account_def in cfg.get("accounts", []):
            if account_def.get("id") == actual_runtime_id:
                if family_name:
                    overrides = normalize_family_priority_overrides(
                        account_def.get("family_priority_overrides", {})
                    )
                    overrides[family_name] = normalize_priority(new_priority)
                    account_def["family_priority_overrides"] = overrides
                else:
                    account_def["priority"] = normalize_priority(new_priority)
                changed = True
                break
    return changed


def resolve_visible_clis(
    cfg,
    default_provider,
    default_models,
    *,
    cli_names,
    managed_oauth_clis,
    cli_model_family_hints,
    accounts_for_cli,
    check_cli_installed,
    resolve_provider_for_cli,
    disabled_clis=(),
):
    visible = []
    disabled = set(disabled_clis or [])

    for cli_name in cli_names:
        if cli_name in disabled:
            continue
        if cli_name in managed_oauth_clis:
            if accounts_for_cli(cfg, cli_name):
                visible.append(cli_name)
                continue
            # Antigravity is OAuth-native, so show the tab before account setup
            # when the binary exists and let the TUI connect flow handle setup.
            if cli_name == "agy":
                try:
                    if check_cli_installed(cli_name):
                        visible.append(cli_name)
                        continue
                except Exception:
                    pass
        provider, family_models = resolve_provider_for_cli(cfg, cli_name, default_provider, default_models)
        if provider is None:
            continue
        if cli_name in cli_model_family_hints and not family_models:
            continue
        visible.append(cli_name)

    return visible


def use_tui(stdin, get_terminal_size, *, min_columns=40):
    if not stdin.isatty():
        return False
    try:
        cols = get_terminal_size().columns
        return cols >= min_columns
    except OSError:
        return False


def clean_model_info(model_info):
    if not isinstance(model_info, dict):
        return model_info
    return {key: value for key, value in model_info.items() if key != "provider"}


def uses_native_account_entry(runtime, cli, *, oauth_capable_clis):
    return bool(runtime and runtime.get("auth_mode") == "oauth" and cli in oauth_capable_clis)


def uses_broker_entry(runtime, cli):
    return bool(runtime and runtime.get("runtime_kind") == "broker" and cli == "claude")


def uses_managed_entry(runtime, cli, *, oauth_capable_clis):
    return uses_native_account_entry(runtime, cli, oauth_capable_clis=oauth_capable_clis)


DIRECT_CLI_LAUNCH_DEFAULTS = {
    "claude": (
        ("direct-deepseek", "deepseek-v4-pro"),
        ("direct-deepseek", "deepseek-v4-flash"),
        ("mimo-direct", "mimo-v2.5"),
    ),
    "codex": (
        ("uscrsopenai", "gpt-5.4"),
        ("uscrsopenai", "gpt-5.5"),
        ("uscrsopenai", "gpt-5.3-codex"),
    ),
    "pi": (
        ("mimo-direct", "mimo-v2.5"),
        ("direct-deepseek", "deepseek-v4-pro"),
        ("direct-zai", "glm-5.1"),
        ("direct-zai", "glm-5-turbo"),
    ),
}


def resolve_direct_cli_launch_default(
    cli_name,
    cfg,
    default_provider,
    default_models,
    *,
    provider_candidates,
    provider_effective_models,
    provider_supports_model_for_cli,
):
    cli_name = str(cli_name or "").strip().lower()
    if cli_name == "opencode":
        opencode = cfg.get("opencode") if isinstance(cfg, dict) and isinstance(cfg.get("opencode"), dict) else {}
        if opencode.get("default_profile") or opencode.get("profile"):
            return {}
        return {"profile": "pro", "source": "launch default"}

    wanted = DIRECT_CLI_LAUNCH_DEFAULTS.get(cli_name)
    if not wanted:
        return {}

    provider_map = {}
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        provider_id = str((provider or {}).get("id") or "").strip()
        if provider_id and provider_id not in provider_map:
            provider_map[provider_id] = (provider, cached_models)

    for provider_id, model_name in wanted:
        provider_entry = provider_map.get(provider_id)
        if not provider_entry:
            continue
        provider, cached_models = provider_entry
        if not provider.get("enabled", True) or not provider.get("api_key"):
            continue
        models = provider_effective_models(provider, cached_models, cfg)
        models_by_lower = {
            str(item or "").strip().lower(): str(item or "").strip()
            for item in models or []
            if str(item or "").strip()
        }
        actual_model = models_by_lower.get(str(model_name or "").strip().lower())
        if not actual_model:
            continue
        if not provider_supports_model_for_cli(provider, cli_name, actual_model):
            continue
        return {
            "provider": provider_id,
            "model": actual_model,
            "model_info": {"model": actual_model},
            "source": "launch default",
        }
    return {}


def resolve_interactive_launch_model(
    cli,
    runtime,
    cli_models,
    models_cache,
    role,
    recommend,
    *,
    uses_native_account_entry,
    uses_broker_entry,
    ensure_models_cache_available,
    display_models,
    select_model_interactive,
    console,
):
    if uses_native_account_entry(runtime, cli):
        console.print(f"[cyan]{cli} 当前使用账号档案登录，直接进入官方 CLI；模型选择交由官方 CLI 处理。[/cyan]")
        return True, None

    if uses_broker_entry(runtime, cli):
        console.print(f"[cyan]{cli} 当前使用 broker profile；先选模型，然后直接进入 remote official Claude Code。[/cyan]")
        available_models = cli_models or models_cache
        if not ensure_models_cache_available(available_models):
            return False, None
        models_list = display_models(available_models, role, recommend)
        return True, select_model_interactive(models_list)

    available_models = cli_models or models_cache
    if not ensure_models_cache_available(available_models):
        return False, None
    models_list = display_models(available_models, role, recommend)
    return True, select_model_interactive(models_list)


def preset_model_info(preset, *, excluded_keys=frozenset({"cli", "provider", "account", "description", "bridge"})):
    if not isinstance(preset, dict):
        return {}
    return {key: value for key, value in preset.items() if key not in excluded_keys}


def save_preset_interactive(
    cfg,
    cli,
    model_info,
    *,
    prompt_ask,
    normalize_preset_entry,
    save_config,
    console,
):
    name = prompt_ask("预设名称")
    description = prompt_ask("预设描述（可留空）", default="").strip()
    preset = {"cli": cli}
    if isinstance(model_info, dict):
        preset.update(model_info)
    else:
        preset["model"] = model_info
    if "presets" not in cfg:
        cfg["presets"] = {}
    if description:
        preset["description"] = description
    cfg["presets"][name] = normalize_preset_entry(name, preset)
    save_config(cfg)
    console.print(f"[green]✓ 预设 '{name}' 已保存[/green]")


def available_broker_profiles_for_cli(_cfg, _cli_name):
    return []


def broker_enabled_by_cli(cfg, cli_names, *, available_broker_profiles_for_cli=available_broker_profiles_for_cli):
    return {
        cli_name: bool(available_broker_profiles_for_cli(cfg, cli_name))
        for cli_name in (cli_names or [])
    }


def select_broker_profile_interactive(
    cfg,
    cli_name,
    *,
    available_broker_profiles_for_cli,
    ensure_rich,
    table_cls,
    prompt_ask,
    console,
):
    profiles = available_broker_profiles_for_cli(cfg, cli_name)
    if not profiles:
        return None
    if len(profiles) == 1:
        return profiles[0]

    ensure_rich()
    table = table_cls(title="Broker Experiment", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("ID", style="green")
    table.add_column("设备/工作区", style="yellow")
    table.add_column("Broker", style="blue")
    table.add_column("Remote", style="magenta")
    for idx, profile in enumerate(profiles, 1):
        table.add_row(
            str(idx),
            str(profile.get("id", "")),
            f"{profile.get('device_id', '-')}/{profile.get('workspace_id', '-')}",
            str(profile.get("broker_base_url") or "-"),
            str(profile.get("remote_service_label") or profile.get("remote_service_base_url") or "-"),
        )
    console.print(table)

    while True:
        raw = prompt_ask("选择 broker profile，直接回车取消", default="").strip()
        if not raw:
            return None
        if raw.isdigit():
            picked = int(raw)
            if 1 <= picked <= len(profiles):
                return profiles[picked - 1]
        console.print("[yellow]请输入有效编号[/yellow]")


def launch_broker_experiment_interactive(
    cfg,
    cli_name,
    *,
    select_broker_profile_interactive,
    run_broker_profile_interactive,
    console,
):
    profile = select_broker_profile_interactive(cfg, cli_name)
    if profile is None:
        return False

    console.print(
        f"[cyan]Broker experiment[/cyan] -> {profile['name']} "
        f"[dim]({profile['device_id']}/{profile['workspace_id']})[/dim]"
    )
    console.print("[dim]支持续最近 / 新开 / 切换旧会话；默认直接回车续最近。[/dim]")
    exit_code = run_broker_profile_interactive(cfg, profile["id"])
    if exit_code != 0:
        console.print(f"[red]broker experiment 启动失败，退出码 {exit_code}[/red]")
    return True


def opencode_default_profile_from_config(cfg, *, opencode_profile_selection, default_profile=None):
    opencode = cfg.get("opencode") if isinstance(cfg, dict) and isinstance(cfg.get("opencode"), dict) else {}
    return opencode_profile_selection(opencode.get("default_profile") or opencode.get("profile") or default_profile)


def build_opencode_resolver_deps(
    *,
    resolver_deps_cls,
    provider_candidates,
    provider_effective_models,
    provider_supports_cli_name,
    provider_supports_model_for_cli,
    provider_label,
    provider_openai_base_url,
    provider_anthropic_base_url,
    infer_model_family,
    normalize_role,
    runtime_priority_for_model,
    runtime_with_priority,
    mms_model_visible,
    load_route_health_latest,
    route_health_for_route,
    route_health_allows_route,
    route_health_sort_key,
    apply_profile,
    apply_entrypoint,
    role_weights,
    default_priority,
    default_provider_id,
):
    return resolver_deps_cls(
        provider_candidates=provider_candidates,
        provider_effective_models=provider_effective_models,
        provider_supports_cli_name=provider_supports_cli_name,
        provider_supports_model_for_cli=provider_supports_model_for_cli,
        provider_label=provider_label,
        provider_openai_base_url=provider_openai_base_url,
        provider_anthropic_base_url=provider_anthropic_base_url,
        infer_model_family=infer_model_family,
        normalize_role=normalize_role,
        runtime_priority_for_model=runtime_priority_for_model,
        runtime_with_priority=runtime_with_priority,
        mms_model_visible=mms_model_visible,
        load_route_health_latest=load_route_health_latest,
        route_health_for_route=route_health_for_route,
        route_health_allows_route=route_health_allows_route,
        route_health_sort_key=route_health_sort_key,
        apply_profile=apply_profile,
        apply_entrypoint=apply_entrypoint,
        role_weights=role_weights,
        default_priority=default_priority,
        default_provider_id=default_provider_id,
    )


def find_opencode_model_route(
    cfg,
    default_provider,
    default_models,
    model_names,
    *,
    opencode_resolver_deps,
    find_opencode_model_route_impl,
    route_key="route",
    route_policy="",
    profile_id="agent",
    provider_id="",
):
    return find_opencode_model_route_impl(
        cfg,
        default_provider,
        default_models,
        model_names,
        deps=opencode_resolver_deps(),
        route_key=route_key,
        route_policy=route_policy,
        profile_id=profile_id,
        provider_id=provider_id,
    )


def usage_key(runtime_kind, cli_name, runtime_id):
    return f"{runtime_kind}:{cli_name}:{runtime_id}"


def rename_usage_account(
    old_id,
    new_id,
    new_name,
    cli_name,
    *,
    usage_path,
    path_exists=os.path.exists,
    update_usage_stats,
    usage_key=usage_key,
):
    if not path_exists(usage_path):
        return False

    def _mutate(stats):
        sources = stats.get("sources", {})
        old_key = usage_key("account", cli_name, old_id)
        entry = sources.pop(old_key, None)
        if entry is None:
            return False
        entry["id"] = new_id
        entry["name"] = new_name
        sources[usage_key("account", cli_name, new_id)] = entry
        return True

    return bool(update_usage_stats(_mutate))


def rename_usage_provider(
    old_id,
    new_id,
    new_name,
    *,
    usage_path,
    path_exists=os.path.exists,
    update_usage_stats,
    usage_key=usage_key,
):
    if not path_exists(usage_path):
        return False

    def _mutate(stats):
        sources = stats.get("sources", {})
        changed = False
        rewritten = {}
        for key, entry in list(sources.items()):
            if entry.get("runtime_kind") != "provider" or entry.get("id") != old_id:
                continue
            sources.pop(key, None)
            updated = dict(entry)
            updated["id"] = new_id
            updated["name"] = new_name
            cli_name = str(updated.get("cli", "default")).strip() or "default"
            rewritten[usage_key("provider", cli_name, new_id)] = updated
            changed = True
        sources.update(rewritten)
        return changed

    return bool(update_usage_stats(_mutate))


def target_account_home(old_home, new_id, *, accounts_dir, default_account_home):
    expanded = os.path.expanduser(str(old_home or "").strip())
    if not expanded:
        return default_account_home(new_id)
    known_roots = {
        os.path.realpath(accounts_dir),
    }
    parent = os.path.realpath(os.path.dirname(expanded))
    if parent in known_roots:
        return os.path.join(accounts_dir, new_id)
    return os.path.join(os.path.dirname(expanded), new_id)


def migrate_accounts_dirs(
    cfg,
    *,
    target_account_home,
    normalize_account,
    path_exists=os.path.exists,
    makedirs=os.makedirs,
    move,
):
    changed = False
    updated_accounts = []
    for item in cfg.get("accounts", []):
        if not isinstance(item, dict):
            continue
        account = dict(item)
        home_dir = os.path.expanduser(str(account.get("home_dir", "")).strip())
        target_home = target_account_home(home_dir, account.get("id", "account"))
        if os.path.realpath(home_dir) != os.path.realpath(target_home):
            if path_exists(home_dir) and not path_exists(target_home):
                makedirs(os.path.dirname(target_home), exist_ok=True)
                move(home_dir, target_home)
            account["home_dir"] = target_home
            changed = True
        updated_accounts.append(normalize_account(account))

    return updated_accounts, changed


def provider_looks_openrouter(provider):
    if not isinstance(provider, dict):
        return False
    fields = [
        provider.get("id"),
        provider.get("name"),
        provider.get("provider_profile"),
        provider.get("profile"),
        provider.get("extension"),
        provider.get("base_url"),
        provider.get("openai_base_url"),
        provider.get("default_openai_base_url"),
    ]
    return any("openrouter" in str(item or "").lower() for item in fields)


def openrouter_provider_candidates(
    cfg,
    *,
    provider_looks_openrouter=provider_looks_openrouter,
    resolve_provider_context,
):
    providers = []
    for item in cfg.get("providers", []):
        if not provider_looks_openrouter(item):
            continue
        try:
            providers.append(resolve_provider_context(cfg, item.get("id")))
        except Exception:
            providers.append(item)
    return providers


def parse_openrouter_extension_args(args_rest):
    args = list(args_rest or [])
    action = "status"
    provider_id = ""
    limit = 12
    assume_paid = False
    json_output = False
    if args and not args[0].startswith("-"):
        action = args.pop(0).strip().lower() or "status"
    if args and not args[0].startswith("-"):
        provider_id = args.pop(0).strip()
    idx = 0
    while idx < len(args):
        token = args[idx]
        if token in {"--limit", "-n"} and idx + 1 < len(args):
            try:
                limit = max(1, int(args[idx + 1]))
            except ValueError:
                limit = 12
            idx += 2
            continue
        if token == "--assume-paid":
            assume_paid = True
        elif token == "--json":
            json_output = True
        idx += 1
    if action in {"ls", "list"}:
        action = "models"
    if action in {"-h", "--help", "help"}:
        action = "help"
    return {
        "action": action,
        "provider_id": provider_id,
        "limit": limit,
        "assume_paid": assume_paid,
        "json": json_output,
    }


def openrouter_extension_provider(
    cfg,
    provider_id="",
    *,
    provider_map,
    resolve_provider_context,
    provider_looks_openrouter=provider_looks_openrouter,
    openrouter_provider_candidates,
):
    providers = provider_map(cfg)
    if provider_id:
        if provider_id not in providers:
            return None, f"未找到 provider: {provider_id}"
        provider = resolve_provider_context(cfg, provider_id)
        if not provider_looks_openrouter(provider):
            return provider, f"provider '{provider_id}' 不是 OpenRouter 模板，但仍可用其 Key 做探测"
        return provider, ""
    candidates = openrouter_provider_candidates(cfg)
    if candidates:
        return candidates[0], ""
    return None, ""


def handle_openrouter_extension_config(
    cfg,
    args_rest,
    *,
    parse_openrouter_extension_args,
    display_openrouter_extension_help,
    quick_connect_gateway,
    openrouter_extension_provider,
    openrouter_api_key_from_env,
    probe_openrouter_extension,
    display_openrouter_extension_summary,
    console,
):
    parsed = parse_openrouter_extension_args(args_rest)
    action = parsed["action"]
    if action == "help":
        display_openrouter_extension_help()
        return
    if action in {"add", "enable"}:
        quick_connect_gateway(cfg, preset_id="openrouter")
        return

    provider, warning = openrouter_extension_provider(cfg, parsed["provider_id"])
    if warning:
        console.print(f"[yellow]{warning}[/yellow]")
    api_key = ""
    provider_label = ""
    if provider:
        provider_label = f"{provider.get('name') or provider.get('id')} ({provider.get('id')})"
        api_key = str(provider.get("api_key") or "").strip()
    if not api_key:
        api_key = openrouter_api_key_from_env()
        if api_key and not provider_label:
            provider_label = "OPENROUTER_API_KEY"
    summary = probe_openrouter_extension(
        api_key,
        assume_paid=bool(parsed["assume_paid"]),
    )
    if parsed["json"]:
        console.print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    display_openrouter_extension_summary(
        summary,
        provider_label=provider_label,
        limit=int(parsed["limit"]),
        show_models=action == "models",
    )


def parse_usage_timestamp(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def usage_recency_score(value, now=None, half_life_days=14, *, parse_usage_timestamp=parse_usage_timestamp):
    parsed = parse_usage_timestamp(value)
    if parsed is None:
        return 0.0
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    if half_life_days <= 0:
        return 1.0
    age_days = max(0.0, (current - parsed).total_seconds()) / 86400.0
    return 0.5 ** (age_days / float(half_life_days))


def sort_family_entries_for_tui(families, preferred_family="", now=None, *, usage_recency_score=usage_recency_score):
    def _key(item):
        family = str(item.get("family") or "") if isinstance(item, dict) else ""
        last_at = str(item.get("last_used_at") or "").strip() if isinstance(item, dict) else ""
        recency = usage_recency_score(last_at, now=now)
        has_recent = 1 if recency > 0 else 0
        preferred_rank = 0 if family == str(preferred_family or "").strip() else 1
        return (-has_recent, -recency, preferred_rank, family.lower())

    return sorted(list(families or []), key=_key)


def family_is_cold_for_tui(
    family_name,
    total_use,
    last_used_at="",
    *,
    preferred_family="",
    known_model_family_names,
    cold_max_use_count,
    cold_idle_days,
    parse_usage_timestamp=parse_usage_timestamp,
    now=None,
):
    if str(family_name or "").strip() == str(preferred_family or "").strip():
        return False
    if str(family_name or "").strip() in known_model_family_names:
        return False
    if int(total_use or 0) > cold_max_use_count:
        return False
    parsed = parse_usage_timestamp(last_used_at)
    if parsed is None:
        return True
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    return parsed < (current - timedelta(days=cold_idle_days))


def build_model_families_for_cli(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    provider_candidates,
    provider_has_configured_base_url,
    provider_effective_models,
    normalize_role,
    runtime_priority_for_model,
    runtime_with_priority,
    provider_label,
    mms_model_visible,
    infer_model_family,
    load_usage_stats,
    provider_supports_model_for_cli,
    role_weights,
    default_provider_id,
):
    """Aggregate provider models by family and attach the best runtime provider."""
    model_best = {}
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if not provider_has_configured_base_url(provider):
            continue
        if not provider.get("api_key"):
            continue

        models = provider_effective_models(provider, cached_models, cfg)
        if not models:
            continue

        role = normalize_role(provider.get("role", "auto"))
        provider_id = provider.get("id", default_provider_id)
        provider_name = provider_label(provider)

        for model_name in models:
            normalized = str(model_name or "").strip()
            if not normalized:
                continue
            if not provider_supports_model_for_cli(provider, cli_name, normalized):
                continue
            priority = runtime_priority_for_model(provider, normalized)
            score = (role_weights.get(role, 1), -priority)
            existing = model_best.get(normalized)
            if existing is None or score < existing[0]:
                model_best[normalized] = (
                    score,
                    runtime_with_priority(provider, model_name=normalized),
                    provider_name,
                    provider_id,
                )

    use_counts = {}
    last_used_at_by_model = {}
    stats = load_usage_stats()
    for source in stats.get("sources", {}).values():
        if str(source.get("cli") or "").strip() != str(cli_name or "").strip():
            continue
        used_at = str(source.get("last_used_at") or "").strip()
        model_last_used_at = source.get("model_last_used_at")
        if not isinstance(model_last_used_at, dict):
            model_last_used_at = {}
        for model_name, count in source.get("models", {}).items():
            use_counts[model_name] = use_counts.get(model_name, 0) + count
            model_used_at = str(model_last_used_at.get(model_name) or "").strip()
            if model_used_at and model_used_at > last_used_at_by_model.get(model_name, ""):
                last_used_at_by_model[model_name] = model_used_at
        last_model = str(source.get("last_model") or "").strip()
        if (
            last_model
            and used_at
            and last_model not in model_last_used_at
            and used_at > last_used_at_by_model.get(last_model, "")
        ):
            last_used_at_by_model[last_model] = used_at

    family_map = {}
    family_order = []

    for model_name, (_, provider_ctx, provider_name, provider_id) in model_best.items():
        if not mms_model_visible(model_name):
            continue
        family, _ = infer_model_family(model_name)
        if family not in family_map:
            family_map[family] = []
            family_order.append(family)
        family_map[family].append({
            "model": model_name,
            "family": family,
            "provider_id": provider_id,
            "provider_name": provider_name,
            "provider_ctx": provider_ctx,
            "use_count": use_counts.get(model_name, 0),
            "last_used_at": last_used_at_by_model.get(model_name, ""),
        })

    return [{"family": family, "models": family_map[family]} for family in family_order]


def resolve_best_provider(
    cfg,
    model_name,
    default_provider,
    default_models,
    *,
    cli_name=None,
    protocol=None,
    provider_candidates,
    provider_supports_model_for_cli,
    provider_has_configured_base_url,
    provider_effective_models,
    normalize_role,
    runtime_priority_for_model,
    provider_label,
    runtime_with_priority,
    role_weights,
):
    model_lower = str(model_name or "").strip().lower()
    if not model_lower:
        return None, None

    scored = []
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if cli_name and not provider_supports_model_for_cli(provider, cli_name, model_name):
            continue
        if not provider_has_configured_base_url(provider):
            continue
        if not provider.get("api_key"):
            continue
        if protocol:
            protocols = provider.get("protocols", [])
            if protocol not in protocols:
                continue

        models = provider_effective_models(provider, cached_models, cfg)
        model_names_lower = [str(item or "").strip().lower() for item in models]
        if model_lower not in model_names_lower:
            continue

        role = normalize_role(provider.get("role", "auto"))
        priority = runtime_priority_for_model(provider, model_name)
        scored.append((role_weights.get(role, 1), -priority, provider, provider_label(provider)))

    if not scored:
        return None, None

    scored.sort(key=lambda item: (item[0], item[1]))
    return runtime_with_priority(scored[0][2], model_name=model_name), scored[0][3]


def provider_options_for_model(
    cfg,
    cli_name,
    default_provider,
    default_models,
    model_info=None,
    *,
    resolve_model_name=resolve_model_name,
    infer_model_family,
    probe_debug_logger,
    provider_candidates,
    provider_has_configured_base_url,
    provider_effective_models,
    provider_models_for_cli,
    provider_supports_model_for_cli,
    provider_supports_cli_name,
    runtime_with_priority,
    runtime_choice_label,
    provider_label,
    runtime_priority_for_family,
    default_priority,
):
    selected_model = resolve_model_name(model_info) if model_info else ""
    selected_family, _ = infer_model_family(selected_model) if selected_model else ("", "")
    probe_debug_logger.info("=== _provider_options_for_model(cli=%s, selected_model=%s) ===", cli_name, selected_model)
    options = []
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        provider_id = provider.get("id", "?")
        if not provider.get("enabled", True):
            probe_debug_logger.debug("  %s: SKIP (disabled)", provider_id)
            continue
        if not provider_has_configured_base_url(provider) or not provider.get("api_key"):
            probe_debug_logger.debug(
                "  %s: SKIP (no configured base_url=%s or api_key=%s)",
                provider_id,
                provider_has_configured_base_url(provider),
                bool(provider.get("api_key")),
            )
            continue

        models = cached_models
        if models is None:
            probe_debug_logger.debug("  %s: cached_models=None, schedule async refresh", provider_id)
            models = provider_effective_models(provider, None, cfg)
        else:
            probe_debug_logger.debug("  %s: cached_models=%s (len=%d)", provider_id, type(cached_models).__name__, len(cached_models))
        models = provider_effective_models(provider, models, cfg)
        try:
            cli_models = provider_models_for_cli(cli_name, models, provider=provider)
        except TypeError as exc:
            if "provider" not in str(exc):
                raise
            cli_models = provider_models_for_cli(cli_name, models)

        if selected_model:
            if not provider_supports_model_for_cli(provider, cli_name, selected_model):
                probe_debug_logger.info("  %s: SKIP (cli/model incompatible for %s -> %s)", provider_id, cli_name, selected_model)
                continue
            if selected_model not in models:
                probe_debug_logger.info("  %s: SKIP (model '%s' not in %s)", provider_id, selected_model, models[:5])
                continue
            option_models = [selected_model]
        else:
            if not provider_supports_cli_name(provider, cli_name):
                probe_debug_logger.debug("  %s: SKIP (cli not supported)", provider_id)
                continue
            option_models = cli_models

        if not option_models:
            probe_debug_logger.info("  %s: SKIP (no option models for cli=%s)", provider_id, cli_name)
            continue

        probe_debug_logger.info("  %s: ADDED (option_models=%s)", provider_id, option_models)
        options.append({
            "kind": "provider",
            "id": provider.get("id"),
            "runtime": runtime_with_priority(provider, model_name=selected_model, family_name=selected_family),
            "models": option_models,
            "label": runtime_choice_label(provider),
            "title": provider_label(provider),
            "desc": "网关",
            "icon": "🌐",
            "priority": (
                runtime_priority_for_family(provider, selected_family)
                if selected_family
                else provider.get("priority", default_priority)
            ),
            "priority_family": selected_family,
            "is_default": provider.get("id") == default_provider.get("id"),
            "launch_cli": cli_name,
        })
    return options


def account_options_for_model(
    cfg,
    cli_name,
    default_models,
    model_info=None,
    *,
    allow_selected_model=False,
    resolve_model_name=resolve_model_name,
    infer_model_family,
    oauth_capable_clis,
    model_matches_account_cli,
    resolve_account_context,
    runtime_with_priority,
    runtime_choice_label,
    account_label,
    default_priority,
):
    selected_model = resolve_model_name(model_info) if model_info else ""
    selected_family, _ = infer_model_family(selected_model) if selected_model else ("", "")
    options = []
    defaults = cfg.get("account", {}).get("defaults", {})

    for account_def in cfg.get("accounts", []):
        if not isinstance(account_def, dict) or not account_def.get("enabled", True):
            continue
        account_cli = account_def.get("cli")
        if account_cli not in oauth_capable_clis:
            continue
        bridgeable_to_claude = False
        if account_cli != cli_name and not bridgeable_to_claude:
            continue
        if selected_model and not allow_selected_model and not bridgeable_to_claude:
            continue
        if selected_model and not model_matches_account_cli(account_cli, selected_model):
            continue
        runtime = resolve_account_context(cfg, account_id=account_def["id"], cli_name=account_cli)
        launch_cli = account_cli
        desc = "官方"
        if bridgeable_to_claude:
            bridged = dict(runtime)
            bridged["auth_mode"] = "oauth_bridge"
            bridged["bridge_source_cli"] = account_cli
            bridged["bridge_target_cli"] = "claude"
            bridged["bridge_model"] = selected_model
            bridged["bridge_account_id"] = runtime.get("id")
            runtime = bridged
            launch_cli = "claude"
            desc = "官方桥接"
        runtime = runtime_with_priority(runtime, model_name=selected_model, family_name=selected_family)
        options.append({
            "kind": "account",
            "id": runtime.get("id"),
            "runtime": runtime,
            "models": [selected_model] if selected_model else list(default_models or []),
            "label": runtime_choice_label(runtime),
            "title": account_label(runtime),
            "desc": desc,
            "icon": "🔑",
            "priority": runtime.get("priority", default_priority),
            "priority_family": selected_family,
            "is_default": runtime.get("id") == defaults.get(account_cli),
            "launch_cli": launch_cli,
        })
    return options


def resolve_provider_for_cli(cfg, cli_name, default_provider, default_models, *, provider_options_for_model, cli_model_family_hints):
    options = provider_options_for_model(cfg, cli_name, default_provider, default_models)
    for option in options:
        runtime = option["runtime"]
        models = option["models"]
        if cli_name not in cli_model_family_hints:
            return runtime, models
        if models:
            return runtime, models
    return None, []


def resolve_launch_runtime(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    account_id=None,
    provider_id=None,
    resolve_provider_context,
    resolve_provider_for_cli,
    probe_models,
    managed_oauth_clis,
    resolve_account_context,
):
    if provider_id:
        provider = resolve_provider_context(cfg, provider_id)
        return resolve_provider_for_cli(cfg, cli_name, provider, probe_models(provider, emit_output=False).get("models"))
    if cli_name in managed_oauth_clis:
        account = resolve_account_context(cfg, account_id=account_id, cli_name=cli_name)
        if account_id and account is not None:
            return account, list(default_models or [])
        if account is not None and account.get("enabled", True):
            return account, list(default_models or [])
    return resolve_provider_for_cli(cfg, cli_name, default_provider, default_models)


def resolve_provider_runtime(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    provider_id=None,
    resolve_provider_context,
    resolve_provider_for_cli,
    probe_models,
):
    if provider_id:
        provider = resolve_provider_context(cfg, provider_id)
        return resolve_provider_for_cli(cfg, cli_name, provider, probe_models(provider, emit_output=False).get("models"))
    return resolve_provider_for_cli(cfg, cli_name, default_provider, default_models)


def resolve_source_default_index(options, preferred_cli):
    if not options:
        return 0
    for idx, option in enumerate(options):
        if option.get("kind") == "provider" and option.get("launch_cli") == preferred_cli and option.get("is_default"):
            return idx
    for idx, option in enumerate(options):
        if option.get("launch_cli") == preferred_cli and option.get("is_default"):
            return idx
    for idx, option in enumerate(options):
        if option.get("launch_cli") == preferred_cli:
            return idx
    for idx, option in enumerate(options):
        if option.get("is_default"):
            return idx
    return 0


def runtime_choice_label(runtime, *, account_label, provider_label):
    if runtime.get("auth_mode") == "broker_profile":
        return f"Broker / {runtime.get('name', runtime.get('id', 'broker'))}"
    if runtime.get("auth_mode") == "oauth_bridge":
        return f"官方桥接 / {account_label(runtime)}"
    if runtime.get("auth_mode") == "oauth":
        return f"官方 / {account_label(runtime)}"
    return f"网关 / {provider_label(runtime)}"


def list_runtime_sources(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    model_info=None,
    allow_selected_model_accounts=False,
    provider_options_for_model,
    account_options_for_model,
    broker_options_for_cli,
    resolve_source_default_index=resolve_source_default_index,
    default_priority,
):
    options = provider_options_for_model(cfg, cli_name, default_provider, default_models, model_info=model_info)
    options.extend(
        account_options_for_model(
            cfg,
            cli_name,
            default_models,
            model_info=model_info,
            allow_selected_model=allow_selected_model_accounts,
        )
    )
    options.extend(broker_options_for_cli(cfg, cli_name, model_info=model_info))
    options.sort(key=lambda item: (
        -int(item.get("priority", default_priority) or default_priority),
        0 if item.get("launch_cli") == cli_name else 1,
        0 if item["kind"] == "provider" else 1 if item["kind"] == "account" else 2,
        item.get("title", ""),
    ))
    default_choice = resolve_source_default_index(options, cli_name)
    return options, default_choice


def choose_runtime_source(
    cfg,
    cli_name,
    default_provider,
    default_models,
    account_id=None,
    provider_id=None,
    model_info=None,
    allow_selected_model_accounts=False,
    *,
    managed_oauth_clis,
    runtime_with_launch_preferences,
    resolve_launch_runtime,
    trace_runtime_choice,
    list_runtime_sources,
    stdin_isatty,
    ensure_rich,
    table_cls,
    prompt_ask,
    runtime_source_kind_label,
    console,
):
    def with_preferences(runtime, launch_cli):
        return runtime_with_launch_preferences(cfg, runtime, launch_cli)

    if account_id or provider_id or cli_name not in managed_oauth_clis:
        runtime, models = resolve_launch_runtime(
            cfg,
            cli_name,
            default_provider,
            default_models,
            account_id=account_id,
            provider_id=provider_id,
        )
        choice = "single runtime path"
        if provider_id:
            choice = "provider override"
        elif account_id:
            choice = "account override"
        runtime = with_preferences(runtime, cli_name)
        trace_runtime_choice("runtime resolve", runtime, launch_cli=cli_name, choice=choice)
        return runtime, models, cli_name

    options, default_choice = list_runtime_sources(
        cfg,
        cli_name,
        default_provider,
        default_models,
        model_info=model_info,
        allow_selected_model_accounts=allow_selected_model_accounts,
    )

    if not options:
        return None, [], cli_name
    if len(options) == 1:
        chosen = options[0]
        launch_cli = chosen.get("launch_cli", cli_name)
        runtime = with_preferences(chosen["runtime"], launch_cli)
        trace_runtime_choice("runtime resolve", runtime, launch_cli=launch_cli, choice="single option")
        return runtime, chosen["models"], launch_cli

    if not stdin_isatty():
        chosen = options[default_choice or 0]
        launch_cli = chosen.get("launch_cli", cli_name)
        runtime = with_preferences(chosen["runtime"], launch_cli)
        trace_runtime_choice("runtime resolve", runtime, launch_cli=launch_cli, choice="default(no-tty)")
        return runtime, chosen["models"], launch_cli

    ensure_rich()
    table = table_cls(title=f"{cli_name} 使用入口", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("来源", style="green")
    table.add_column("名称", style="yellow")
    table.add_column("调用", style="cyan")
    table.add_column("说明", style="magenta")
    for idx, option in enumerate(options, 1):
        runtime = option["runtime"]
        source_type = runtime_source_kind_label(runtime)
        desc = option.get("desc", "")
        if idx - 1 == default_choice:
            desc = f"{desc} / 默认"
        table.add_row(
            str(idx),
            source_type,
            runtime.get("name", runtime.get("id", "")),
            option.get("launch_cli", cli_name),
            desc,
        )
    console.print(table)

    default_num = str((default_choice or 0) + 1)
    while True:
        raw = prompt_ask(f"为 {cli_name} 选择这次使用的入口", default=default_num)
        if raw.isdigit():
            selected = int(raw)
            if 1 <= selected <= len(options):
                chosen = options[selected - 1]
                launch_cli = chosen.get("launch_cli", cli_name)
                runtime = with_preferences(chosen["runtime"], launch_cli)
                trace_runtime_choice("runtime resolve", runtime, launch_cli=launch_cli, choice=chosen.get("title"))
                return runtime, chosen["models"], launch_cli
        console.print(f"[red]请输入 1-{len(options)} 的编号[/red]")


def trace_runtime_provider_id(runtime):
    if not isinstance(runtime, dict):
        return ""
    if runtime.get("runtime_kind") == "provider" or runtime.get("auth_mode") == "api_key":
        return str(runtime.get("id", "")).strip()
    return ""


def trace_runtime_account_id(runtime):
    if not isinstance(runtime, dict):
        return ""
    if runtime.get("auth_mode") == "oauth_bridge":
        return str(runtime.get("bridge_account_id") or runtime.get("id") or "").strip()
    if runtime.get("auth_mode") == "oauth":
        return str(runtime.get("id") or runtime.get("account_id") or "").strip()
    return str(runtime.get("account_id") or "").strip()


def trace_runtime_bridge(runtime):
    if not isinstance(runtime, dict):
        return ""
    if runtime.get("auth_mode") != "oauth_bridge":
        return ""
    return str(runtime.get("bridge_url") or runtime.get("base_url") or "").strip()


def runtime_source_kind_label(runtime):
    if not runtime:
        return "网关"
    if runtime.get("runtime_kind") == "opencode_profile":
        return "OpenCode"
    auth_mode = runtime.get("auth_mode")
    if auth_mode == "broker_profile" or runtime.get("runtime_kind") == "broker":
        return "Broker"
    if auth_mode == "oauth_bridge":
        return "官方桥接"
    if auth_mode == "oauth":
        return "官方"
    return "网关"


def trace_runtime_choice(
    source,
    runtime,
    *,
    launch_cli=None,
    choice=None,
    trace_record,
    trace_runtime_provider_id=trace_runtime_provider_id,
    trace_runtime_account_id=trace_runtime_account_id,
    trace_runtime_bridge=trace_runtime_bridge,
):
    payload = {
        "cli": launch_cli,
        "provider": trace_runtime_provider_id(runtime),
        "account": trace_runtime_account_id(runtime),
        "bridge": trace_runtime_bridge(runtime),
        "runtime": runtime.get("auth_mode") if isinstance(runtime, dict) else None,
        "choice": choice,
    }
    trace_record(source, **payload)


def http_status_is_success(value):
    try:
        status_code = int(str(value or "").strip())
    except (TypeError, ValueError):
        return False
    return 200 <= status_code < 300


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
    from mms_commands.config_handlers import handle_config_get as _impl

    return _impl(cfg, args_rest, command_name=command_name, console=console)


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
    from mms_commands.config_handlers import handle_config_set as _impl

    return _impl(
        cfg,
        args_rest,
        command_name=command_name,
        coerce_config_value=coerce_config_value,
        normalize_config_sections=normalize_config_sections,
        save_config=save_config,
        console=console,
    )


def handle_config_unset(
    cfg,
    args_rest,
    *,
    command_name,
    normalize_config_sections,
    save_config,
    console,
):
    from mms_commands.config_handlers import handle_config_unset as _impl

    return _impl(
        cfg,
        args_rest,
        command_name=command_name,
        normalize_config_sections=normalize_config_sections,
        save_config=save_config,
        console=console,
    )


def handle_config_validate(cfg, *, validate_config, console):
    from mms_commands.config_handlers import handle_config_validate as _impl

    return _impl(cfg, validate_config=validate_config, console=console)


def handle_config(
    cfg,
    args_rest,
    *,
    preferences_doc_path,
    preference_paths,
    display_config,
    display_config_help,
    handle_config_migrate,
    handle_config_file,
    handle_config_validate,
    display_preferences_help,
    display_preferences_path,
    display_preferences_example,
    run_config_web,
    command_name,
    config_write_target_path,
    display_human_gate_help,
    handle_config_get,
    handle_config_set,
    handle_config_unset,
    run_connect_wizard,
    handle_openrouter_extension_config,
    display_adapter_registry,
    display_providers,
    handle_provider_default_config,
    handle_provider_add_config,
    handle_provider_edit_config,
    handle_provider_rename_config,
    handle_provider_remove_config,
    handle_provider_credentials_config,
    display_accounts,
    handle_account_default_config,
    handle_account_add_config,
    handle_account_edit_config,
    handle_account_remove_config,
    handle_account_rename_config,
    handle_account_status_config,
    handle_account_login_config,
    display_usage_stats,
    resolve_provider_context,
    setup_provider_credentials,
    handle_api_config,
    console,
):
    from mms_commands.config_handlers import handle_config as _impl

    return _impl(
        cfg,
        args_rest,
        preferences_doc_path=preferences_doc_path,
        preference_paths=preference_paths,
        display_config=display_config,
        display_config_help=display_config_help,
        handle_config_migrate=handle_config_migrate,
        handle_config_file=handle_config_file,
        handle_config_validate=handle_config_validate,
        display_preferences_help=display_preferences_help,
        display_preferences_path=display_preferences_path,
        display_preferences_example=display_preferences_example,
        run_config_web=run_config_web,
        command_name=command_name,
        config_write_target_path=config_write_target_path,
        display_human_gate_help=display_human_gate_help,
        handle_config_get=handle_config_get,
        handle_config_set=handle_config_set,
        handle_config_unset=handle_config_unset,
        run_connect_wizard=run_connect_wizard,
        handle_openrouter_extension_config=handle_openrouter_extension_config,
        display_adapter_registry=display_adapter_registry,
        display_providers=display_providers,
        handle_provider_default_config=handle_provider_default_config,
        handle_provider_add_config=handle_provider_add_config,
        handle_provider_edit_config=handle_provider_edit_config,
        handle_provider_rename_config=handle_provider_rename_config,
        handle_provider_remove_config=handle_provider_remove_config,
        handle_provider_credentials_config=handle_provider_credentials_config,
        display_accounts=display_accounts,
        handle_account_default_config=handle_account_default_config,
        handle_account_add_config=handle_account_add_config,
        handle_account_edit_config=handle_account_edit_config,
        handle_account_remove_config=handle_account_remove_config,
        handle_account_rename_config=handle_account_rename_config,
        handle_account_status_config=handle_account_status_config,
        handle_account_login_config=handle_account_login_config,
        display_usage_stats=display_usage_stats,
        resolve_provider_context=resolve_provider_context,
        setup_provider_credentials=setup_provider_credentials,
        handle_api_config=handle_api_config,
        console=console,
    )


def handle_config_file(*, config_path, console):
    from mms_commands.config_handlers import handle_config_file as _impl

    return _impl(config_path=config_path, console=console)


def handle_api_config(
    key_path,
    args_rest,
    *,
    load_api_credentials,
    save_api_credentials,
    credentials_path,
    mask_key,
    console,
):
    from mms_commands.config_handlers import handle_api_config as _impl

    return _impl(
        key_path,
        args_rest,
        load_api_credentials=load_api_credentials,
        save_api_credentials=save_api_credentials,
        credentials_path=credentials_path,
        mask_key=mask_key,
        console=console,
    )


def handle_config_migrate(
    *,
    backup_config_tree,
    load_config,
    migrate_accounts_dirs,
    save_config,
    config_path,
    active_credentials_path,
    active_usage_path,
    console,
):
    from mms_commands.config_handlers import handle_config_migrate as _impl

    return _impl(
        backup_config_tree=backup_config_tree,
        load_config=load_config,
        migrate_accounts_dirs=migrate_accounts_dirs,
        save_config=save_config,
        config_path=config_path,
        active_credentials_path=active_credentials_path,
        active_usage_path=active_usage_path,
        console=console,
    )


def handle_provider_default_config(
    cfg,
    args_rest,
    *,
    default_provider_id,
    provider_map,
    save_config,
    refresh_routes_export_for_hive,
    console,
):
    from mms_commands.config_handlers import handle_provider_default_config as _impl

    return _impl(
        cfg,
        args_rest,
        default_provider_id=default_provider_id,
        provider_map=provider_map,
        save_config=save_config,
        refresh_routes_export_for_hive=refresh_routes_export_for_hive,
        console=console,
    )


def handle_provider_add_config(
    cfg,
    args_rest,
    *,
    quick_connect_gateway,
):
    from mms_commands.config_handlers import handle_provider_add_config as _impl

    return _impl(cfg, args_rest, quick_connect_gateway=quick_connect_gateway)


def update_provider_model_overrides(
    cfg,
    provider_id,
    *,
    extra_models=None,
    hidden_models=None,
    models_endpoint=None,
    normalize_model_id_list=normalize_model_id_list,
    normalize_models_endpoint=normalize_models_endpoint,
    normalize_provider,
    save_config,
    invalidate_probe_cache,
    load_config,
):
    from mms_commands.config_handlers import update_provider_model_overrides as _impl

    return _impl(
        cfg,
        provider_id,
        extra_models=extra_models,
        hidden_models=hidden_models,
        models_endpoint=models_endpoint,
        normalize_model_id_list=normalize_model_id_list,
        normalize_models_endpoint=normalize_models_endpoint,
        normalize_provider=normalize_provider,
        save_config=save_config,
        invalidate_probe_cache=invalidate_probe_cache,
        load_config=load_config,
    )


def manage_provider_models(
    cfg,
    provider_id,
    *,
    ensure_rich,
    resolve_provider_context,
    probe_models,
    model_source_label,
    use_tui,
    select_channel_action_tui,
    clear_console,
    display_provider_model_table,
    pause_after_tui_report,
    prompt_ask,
    update_provider_model_overrides,
    panel_cls,
    console,
    normalize_model_id_list=normalize_model_id_list,
    normalize_models_endpoint=normalize_models_endpoint,
    refresh_all_provider_model_defaults=None,
):
    from mms_commands.config_handlers import manage_provider_models as _impl

    return _impl(
        cfg,
        provider_id,
        ensure_rich=ensure_rich,
        resolve_provider_context=resolve_provider_context,
        probe_models=probe_models,
        model_source_label=model_source_label,
        use_tui=use_tui,
        select_channel_action_tui=select_channel_action_tui,
        clear_console=clear_console,
        display_provider_model_table=display_provider_model_table,
        pause_after_tui_report=pause_after_tui_report,
        prompt_ask=prompt_ask,
        update_provider_model_overrides=update_provider_model_overrides,
        panel_cls=panel_cls,
        console=console,
        normalize_model_id_list=normalize_model_id_list,
        normalize_models_endpoint=normalize_models_endpoint,
        refresh_all_provider_model_defaults=refresh_all_provider_model_defaults,
    )


def handle_provider_edit_config(
    cfg,
    args_rest,
    *,
    command_name,
    provider_map,
    prompt_provider_metadata,
    upsert_provider,
    save_config,
    invalidate_probe_cache,
    refresh_routes_export_for_hive,
    console,
):
    from mms_commands.config_handlers import handle_provider_edit_config as _impl

    return _impl(
        cfg,
        args_rest,
        command_name=command_name,
        provider_map=provider_map,
        prompt_provider_metadata=prompt_provider_metadata,
        upsert_provider=upsert_provider,
        save_config=save_config,
        invalidate_probe_cache=invalidate_probe_cache,
        refresh_routes_export_for_hive=refresh_routes_export_for_hive,
        console=console,
    )


def handle_provider_remove_config(
    cfg,
    args_rest,
    *,
    command_name,
    default_provider_id,
    ensure_interactive_terminal,
    provider_map,
    confirm_ask,
    save_config,
    delete_provider_credentials,
    invalidate_probe_cache,
    refresh_routes_export_for_hive,
    console,
):
    from mms_commands.config_handlers import handle_provider_remove_config as _impl

    return _impl(
        cfg,
        args_rest,
        command_name=command_name,
        default_provider_id=default_provider_id,
        ensure_interactive_terminal=ensure_interactive_terminal,
        provider_map=provider_map,
        confirm_ask=confirm_ask,
        save_config=save_config,
        delete_provider_credentials=delete_provider_credentials,
        invalidate_probe_cache=invalidate_probe_cache,
        refresh_routes_export_for_hive=refresh_routes_export_for_hive,
        console=console,
    )


def handle_provider_credentials_config(
    cfg,
    args_rest,
    *,
    default_provider_id,
    provider_map,
    resolve_provider_context,
    setup_provider_credentials,
    console,
):
    from mms_commands.config_handlers import handle_provider_credentials_config as _impl

    return _impl(
        cfg,
        args_rest,
        default_provider_id=default_provider_id,
        provider_map=provider_map,
        resolve_provider_context=resolve_provider_context,
        setup_provider_credentials=setup_provider_credentials,
        console=console,
    )


def handle_provider_rename_config(
    cfg,
    args_rest,
    *,
    command_name,
    normalize_provider_id_input,
    provider_map,
    normalize_provider,
    backup_config_tree,
    save_config,
    rename_usage_provider,
    invalidate_probe_cache,
    refresh_routes_export_for_hive,
    console,
):
    from mms_commands.config_handlers import handle_provider_rename_config as _impl

    return _impl(
        cfg,
        args_rest,
        command_name=command_name,
        normalize_provider_id_input=normalize_provider_id_input,
        provider_map=provider_map,
        normalize_provider=normalize_provider,
        backup_config_tree=backup_config_tree,
        save_config=save_config,
        rename_usage_provider=rename_usage_provider,
        invalidate_probe_cache=invalidate_probe_cache,
        refresh_routes_export_for_hive=refresh_routes_export_for_hive,
        console=console,
    )


def handle_account_default_config(
    cfg,
    args_rest,
    *,
    managed_oauth_clis,
    delegated_oauth_clis,
    account_map,
    save_config,
    command_name,
    console,
):
    from mms_commands.config_handlers import handle_account_default_config as _impl

    return _impl(
        cfg,
        args_rest,
        managed_oauth_clis=managed_oauth_clis,
        delegated_oauth_clis=delegated_oauth_clis,
        account_map=account_map,
        save_config=save_config,
        command_name=command_name,
        console=console,
    )


def handle_account_add_config(
    cfg,
    args_rest,
    *,
    managed_oauth_clis,
    delegated_oauth_clis,
    quick_connect_official,
    console,
):
    from mms_commands.config_handlers import handle_account_add_config as _impl

    return _impl(
        cfg,
        args_rest,
        managed_oauth_clis=managed_oauth_clis,
        delegated_oauth_clis=delegated_oauth_clis,
        quick_connect_official=quick_connect_official,
        console=console,
    )


def handle_account_edit_config(
    cfg,
    args_rest,
    *,
    command_name,
    account_map,
    delegated_oauth_clis,
    prompt_account_metadata,
    ensure_account_config,
    save_config,
    console,
):
    from mms_commands.config_handlers import handle_account_edit_config as _impl

    return _impl(
        cfg,
        args_rest,
        command_name=command_name,
        account_map=account_map,
        delegated_oauth_clis=delegated_oauth_clis,
        prompt_account_metadata=prompt_account_metadata,
        ensure_account_config=ensure_account_config,
        save_config=save_config,
        console=console,
    )


def handle_account_remove_config(
    cfg,
    args_rest,
    *,
    command_name,
    ensure_interactive_terminal,
    account_map,
    confirm_ask,
    ensure_account_config,
    save_config,
    console,
):
    from mms_commands.config_handlers import handle_account_remove_config as _impl

    return _impl(
        cfg,
        args_rest,
        command_name=command_name,
        ensure_interactive_terminal=ensure_interactive_terminal,
        account_map=account_map,
        confirm_ask=confirm_ask,
        ensure_account_config=ensure_account_config,
        save_config=save_config,
        console=console,
    )


def handle_account_status_config(
    cfg,
    args_rest,
    *,
    resolve_account_context,
    probe_account_status,
    display_accounts,
    console,
):
    from mms_commands.config_handlers import handle_account_status_config as _impl

    return _impl(
        cfg,
        args_rest,
        resolve_account_context=resolve_account_context,
        probe_account_status=probe_account_status,
        display_accounts=display_accounts,
        console=console,
    )


def handle_account_login_config(
    cfg,
    args_rest,
    *,
    command_name,
    delegated_oauth_clis,
    resolve_account_context,
    run_account_login,
    console,
):
    from mms_commands.config_handlers import handle_account_login_config as _impl

    return _impl(
        cfg,
        args_rest,
        command_name=command_name,
        delegated_oauth_clis=delegated_oauth_clis,
        resolve_account_context=resolve_account_context,
        run_account_login=run_account_login,
        console=console,
    )


def handle_account_rename_config(
    cfg,
    args_rest,
    *,
    command_name,
    normalize_account_id,
    account_map,
    backup_config_tree,
    target_account_home,
    path_exists,
    makedirs,
    move,
    normalize_account,
    ensure_account_config,
    save_config,
    rename_usage_account,
    console,
):
    from mms_commands.config_handlers import handle_account_rename_config as _impl

    return _impl(
        cfg,
        args_rest,
        command_name=command_name,
        normalize_account_id=normalize_account_id,
        account_map=account_map,
        backup_config_tree=backup_config_tree,
        target_account_home=target_account_home,
        path_exists=path_exists,
        makedirs=makedirs,
        move=move,
        normalize_account=normalize_account,
        ensure_account_config=ensure_account_config,
        save_config=save_config,
        rename_usage_account=rename_usage_account,
        console=console,
    )


from mms_commands.session_handlers import (
    session_status_label,
    session_display_id,
    handle_session_ls,
    handle_session_info,
    session_gateway_roots,
    session_dir_size_bytes,
    format_bytes,
    list_stale_gateway_sessions,
    split_cli_prefixed_resume_ref,
    codex_resume_roots,
    iter_codex_index_records,
    resolve_codex_resume_ref,
    resolve_claude_resume_ref,
    uuid_resume_cli_hint,
    resume_resolution_diagnostics,
    first_resume_model,
    session_resume_model,
    handle_resume_command,
    handle_session_prune,
)


def resolve_resume_target(
    session_ref,
    cli_hint="auto",
    *,
    split_cli_prefixed_resume_ref=split_cli_prefixed_resume_ref,
    resolve_codex_resume_ref,
    resolve_claude_resume_ref,
    uuid_resume_cli_hint,
):
    from mms_commands.session_handlers import resolve_resume_target as _impl

    return _impl(
        session_ref,
        cli_hint,
        split_cli_prefixed_resume_ref=split_cli_prefixed_resume_ref,
        resolve_codex_resume_ref=resolve_codex_resume_ref,
        resolve_claude_resume_ref=resolve_claude_resume_ref,
        uuid_resume_cli_hint=uuid_resume_cli_hint,
    )


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
    from mms_commands.session_handlers import resolve_resume_runtime_and_model as _impl

    return _impl(
        cfg,
        cli,
        args,
        default_provider,
        default_models,
        session_record,
        get_scene_usage=get_scene_usage,
        session_resume_model=session_resume_model,
        resolve_last_used_runtime=resolve_last_used_runtime,
        trace_runtime_choice=trace_runtime_choice,
        choose_runtime_source=choose_runtime_source,
        resolve_model_name=resolve_model_name,
        first_resume_model=first_resume_model,
        uses_managed_entry=uses_managed_entry,
        runtime_with_launch_preferences=runtime_with_launch_preferences,
    )


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


from mms_commands.standalone_handlers import (
    handle_logs_command,
    handle_exposure_command,
    handle_cache_command,
    handle_guard_command,
)


from mms_commands.launcher_handlers import (
    handle_session_command,
    handle_env_command,
    handle_activate_command,
    handle_models_command,
    select_provider_for_models,
    pick_manual_models,
    warm_model_request,
)


def detect_working_base_url(
    configured_url,
    path,
    headers,
    body=None,
    timeout=5,
    runtime=None,
    *,
    ensure_httpx,
    get_httpx,
    runtime_httpx_request,
):
    ensure_httpx()
    if get_httpx() is None:
        return None
    url = configured_url.rstrip("/")
    candidates = [url[:-3], url] if url.endswith("/v1") else [url, url + "/v1"]
    for candidate in candidates:
        try:
            if body is not None:
                resp = runtime_httpx_request(
                    "POST",
                    f"{candidate}{path}",
                    runtime=runtime,
                    headers=headers,
                    content=body,
                    timeout=timeout,
                )
            else:
                resp = runtime_httpx_request(
                    "GET",
                    f"{candidate}{path}",
                    runtime=runtime,
                    headers=headers,
                    timeout=timeout,
                )
            if resp.status_code == 200:
                return candidate
        except Exception:
            continue
    return None


from mms_commands.launcher_handlers import (
    handle_warm_command,
    handle_export,
    emit_preset_error,
    preset_env_file_path,
    resolve_named_preset,
    infer_preset_auth_mode,
    resolve_preset_export_runtime,
    handle_presets_command,
)


from mms_commands.display_handlers import (
    display_config_help,
    display_preferences_path,
    display_preferences_example,
    display_human_gate_help,
    display_preferences_help,
    display_usage_stats,
    display_adapter_registry,
    display_providers,
    display_accounts,
    recent_models_for_provider,
    display_runtime_usage,
    display_provider_model_table,
    display_openrouter_extension_help,
    display_openrouter_model_rows,
    display_openrouter_video_rows,
    display_openrouter_extension_summary,
    display_config,
)


from mms_commands.standalone_handlers import (
    run_script_subcommand,
    handle_doctor_command,
    handle_test_command,
    handle_opencode_smoke_command,
)
