"""Launch trace and tracking helpers with dependencies injected by core."""

from __future__ import annotations


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
