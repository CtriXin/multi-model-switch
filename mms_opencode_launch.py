"""OpenCode launch command and health-check helpers."""

from __future__ import annotations

import os


_FALSE_VALUES = {"0", "false", "no", "off", "disable", "disabled", "skip"}
_TRUE_VALUES = {"1", "true", "yes", "on", "enable", "enabled"}
_DEFAULT_OPENCODE_HEALTH_TIMEOUT_SEC = 2.0


def _env(environ=None):
    return os.environ if environ is None else environ


def _opencode_health_check_enabled(runtime, *, environ=None):
    runtime = runtime if isinstance(runtime, dict) else {}
    if runtime.get("skip_gateway_health_check"):
        return False
    raw = str(_env(environ).get("MMS_OPENCODE_HEALTHCHECK") or "").strip().lower()
    if raw in _FALSE_VALUES:
        return False
    if raw in _TRUE_VALUES:
        return True
    return True


def _opencode_float_setting(runtime, env_name, runtime_keys, default, *, environ=None):
    runtime = runtime if isinstance(runtime, dict) else {}
    raw = str(_env(environ).get(env_name) or "").strip()
    if not raw:
        for key in runtime_keys:
            if key in runtime and runtime.get(key) not in (None, ""):
                raw = str(runtime.get(key)).strip()
                break
    if not raw:
        return float(default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(default)
    if value <= 0:
        return float(default)
    return min(value, 8.0)


def _opencode_int_setting(runtime, env_name, runtime_keys, default, *, environ=None):
    runtime = runtime if isinstance(runtime, dict) else {}
    raw = str(_env(environ).get(env_name) or "").strip()
    if not raw:
        for key in runtime_keys:
            if key in runtime and runtime.get(key) not in (None, ""):
                raw = str(runtime.get(key)).strip()
                break
    if not raw:
        return int(default)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return int(default)


def _opencode_health_check_timeout(runtime, *, environ=None):
    return _opencode_float_setting(
        runtime,
        "MMS_OPENCODE_HEALTHCHECK_TIMEOUT",
        ("opencode_health_check_timeout_sec", "gateway_health_timeout_sec"),
        _DEFAULT_OPENCODE_HEALTH_TIMEOUT_SEC,
        environ=environ,
    )


def _opencode_route_health_key(route):
    protocol = str(route.get("protocol") or "openai_chat_completions").strip()
    route_base_url = route.get("anthropic_base_url") if protocol == "anthropic_messages" else route.get("openai_base_url")
    return (route.get("provider_id"), protocol, route_base_url)


def _opencode_ordered_unique_routes(runtime, routes):
    runtime = runtime if isinstance(runtime, dict) else {}
    routes = [route for route in (routes or []) if isinstance(route, dict)]
    if len(routes) <= 1:
        return routes

    by_id = {}
    for route in routes:
        route_id = str(route.get("id") or "").strip()
        if route_id and route_id not in by_id:
            by_id[route_id] = route

    ordered = []
    preferred_ids = []
    default_route_key = str(runtime.get("opencode_default_route_key") or "").strip()
    if default_route_key:
        preferred_ids.append(default_route_key)
    configured = runtime.get("opencode_launch_fallback_route_keys")
    if isinstance(configured, str):
        configured = [configured]
    if isinstance(configured, (list, tuple)):
        preferred_ids.extend(str(item or "").strip() for item in configured)
    for route_id in preferred_ids:
        route = by_id.get(route_id)
        if route is not None and route not in ordered:
            ordered.append(route)
    for route in routes:
        if route not in ordered:
            ordered.append(route)

    unique = []
    seen = set()
    for route in ordered:
        key = _opencode_route_health_key(route)
        if key in seen:
            continue
        seen.add(key)
        unique.append(route)
    return unique


def _opencode_health_check_routes(runtime, routes, *, environ=None):
    unique = _opencode_ordered_unique_routes(runtime, routes)
    if len(unique) <= 1:
        return unique
    max_routes = _opencode_int_setting(
        runtime,
        "MMS_OPENCODE_HEALTHCHECK_MAX_ROUTES",
        ("opencode_health_check_max_routes",),
        1,
        environ=environ,
    )
    if max_routes <= 0:
        return []
    return unique[:max_routes]


def _opencode_route_health_runtime(runtime, route, *, timeout_sec):
    runtime = runtime if isinstance(runtime, dict) else {}
    health_runtime = dict(runtime)
    protocol = str(route.get("protocol") or "openai_chat_completions").strip()
    health_runtime["id"] = route.get("provider_id") or health_runtime.get("id")
    if protocol == "anthropic_messages":
        health_runtime["openai_base_url"] = ""
        health_runtime["anthropic_base_url"] = route.get("anthropic_base_url") or health_runtime.get("anthropic_base_url")
    else:
        health_runtime["openai_base_url"] = route.get("openai_base_url") or health_runtime.get("openai_base_url")
        health_runtime["anthropic_base_url"] = ""
    health_runtime["api_key"] = route.get("api_key") or health_runtime.get("api_key")
    health_runtime["gateway_health_timeout_sec"] = timeout_sec
    health_runtime["gateway_health_source"] = "opencode"
    return health_runtime


def opencode_gateway_health_check(
    runtime,
    *,
    runtime_routes,
    resolve_model,
    provider_base_url,
    gateway_health_check,
):
    runtime = runtime if isinstance(runtime, dict) else {}
    if not _opencode_health_check_enabled(runtime):
        return
    timeout_sec = _opencode_health_check_timeout(runtime)
    routes = runtime_routes(runtime, resolve_model(runtime))
    checked_routes = _opencode_health_check_routes(runtime, routes)
    if checked_routes:
        for route in checked_routes:
            gateway_health_check(_opencode_route_health_runtime(runtime, route, timeout_sec=timeout_sec))
        return
    if routes:
        return
    health_runtime = dict(runtime)
    health_runtime["openai_base_url"] = provider_base_url(runtime)
    health_runtime["gateway_health_timeout_sec"] = timeout_sec
    health_runtime["gateway_health_source"] = "opencode"
    gateway_health_check(health_runtime)


def opencode_is_global_profile_runtime(cli, runtime):
    if cli != "opencode" or not isinstance(runtime, dict):
        return False
    profile = str(runtime.get("opencode_profile") or "").strip().lower()
    return (
        profile in {"heavy", "heavy_omo", "omo"}
        or runtime.get("opencode_use_global_config")
        or (
            runtime.get("runtime_kind") == "opencode_profile"
            and runtime.get("auth_mode") == "global_config"
        )
    )


def opencode_global_command(runtime, entrypoint):
    runtime = runtime if isinstance(runtime, dict) else {}
    cmd = ["opencode"]
    if entrypoint in {"serve", "acp"}:
        cmd.append(entrypoint)
    agent = str(runtime.get("opencode_agent") or "").strip()
    if agent and entrypoint == "tui":
        cmd += ["--agent", agent]
    return cmd


def opencode_session_command(runtime, entrypoint, launch_model_ref, launch_agent, *, default_agent):
    runtime = runtime if isinstance(runtime, dict) else {}
    cmd = ["opencode"]
    if entrypoint in {"serve", "acp"}:
        cmd.append(entrypoint)
    if runtime.get("opencode_pure", True) is not False:
        cmd.append("--pure")
    agent = str(launch_agent or runtime.get("opencode_agent", default_agent) or "").strip()
    if agent and entrypoint == "tui":
        cmd += ["--agent", agent]
    if entrypoint == "tui":
        cmd += ["-m", launch_model_ref]
    return cmd


def launch_opencode(
    model_info,
    runtime,
    once=False,
    *,
    entrypoint,
    global_omo_env,
    global_command,
    exec_or_run,
    gateway_health_check,
    resolve_model,
    runtime_routes,
    gateway_env,
    select_launch_candidate,
    console,
    sys_exit,
    inject_selected_model_name,
    install_session_packet_env,
    session_command,
):
    runtime = runtime if isinstance(runtime, dict) else {}
    profile = str(runtime.get("opencode_profile") or "lite").strip().lower() or "lite"
    selected_entrypoint = entrypoint(runtime)
    if profile in {"heavy", "heavy_omo", "omo"} or runtime.get("opencode_use_global_config"):
        env = global_omo_env(runtime)
        inject_selected_model_name(env, resolve_model(model_info), model_info=model_info)
        env["MMS_OPENCODE_ENTRYPOINT"] = selected_entrypoint
        cmd = global_command(runtime, selected_entrypoint)
        exec_or_run(cmd, env, once)
        return

    gateway_health_check(runtime)
    model = resolve_model(model_info)
    routes = runtime_routes(runtime, model)
    env = gateway_env(runtime, model_info=model_info)
    launch_model_ref, launch_agent, preflight_checks = select_launch_candidate(runtime, routes, model, env)
    if not launch_model_ref and preflight_checks:
        console.print("[red]OpenCode Agent preflight 全部失败；未启动可能坏掉的 primary route。[/red]")
        console.print("[dim]可运行 `mms opencode-smoke --profile agent --live` 查看完整 Moebius trace。[/dim]")
        sys_exit(2)
    if not launch_model_ref:
        console.print("[red]OpenCode 启动需要先选择一个模型[/red]")
        sys_exit(1)
    launch_model_name = launch_model_ref.rsplit("/", 1)[-1]
    inject_selected_model_name(env, launch_model_name)
    env["MMS_OPENCODE_LAUNCH_MODEL"] = launch_model_ref
    env["MMS_OPENCODE_LAUNCH_AGENT"] = str(launch_agent or "")
    if env.get("MMS_SESSION_HOME"):
        launch_model_info = dict(model_info) if isinstance(model_info, dict) else {}
        launch_model_info["model"] = launch_model_name
        launch_model_info["opencode_model_ref"] = launch_model_ref
        install_session_packet_env(
            env,
            cli="opencode",
            runtime=runtime,
            model_info=launch_model_info,
            session_home=env.get("MMS_SESSION_HOME"),
            features={
                "opencode_launch_preflight": bool(preflight_checks),
                "opencode_launch_route": launch_model_ref,
            },
        )
    env["MMS_OPENCODE_ENTRYPOINT"] = selected_entrypoint
    cmd = session_command(runtime, selected_entrypoint, launch_model_ref, launch_agent)
    exec_or_run(cmd, env, once)


__all__ = [
    "launch_opencode",
    "opencode_gateway_health_check",
    "opencode_global_command",
    "opencode_is_global_profile_runtime",
    "opencode_session_command",
]
