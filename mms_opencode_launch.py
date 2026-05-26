"""OpenCode launch command and health-check helpers."""

from __future__ import annotations


def opencode_gateway_health_check(
    runtime,
    *,
    runtime_routes,
    resolve_model,
    provider_base_url,
    gateway_health_check,
):
    runtime = runtime if isinstance(runtime, dict) else {}
    routes = runtime_routes(runtime, resolve_model(runtime))
    if len(routes) > 1:
        seen = set()
        for route in routes:
            protocol = str(route.get("protocol") or "openai_chat_completions").strip()
            route_base_url = route.get("anthropic_base_url") if protocol == "anthropic_messages" else route.get("openai_base_url")
            key = (route.get("provider_id"), protocol, route_base_url)
            if key in seen:
                continue
            seen.add(key)
            health_runtime = dict(runtime)
            health_runtime["id"] = route.get("provider_id") or health_runtime.get("id")
            if protocol == "anthropic_messages":
                health_runtime["openai_base_url"] = ""
                health_runtime["anthropic_base_url"] = route.get("anthropic_base_url") or health_runtime.get("anthropic_base_url")
            else:
                health_runtime["openai_base_url"] = route.get("openai_base_url") or health_runtime.get("openai_base_url")
                health_runtime["anthropic_base_url"] = ""
            health_runtime["api_key"] = route.get("api_key") or health_runtime.get("api_key")
            gateway_health_check(health_runtime)
        return
    health_runtime = dict(runtime)
    health_runtime["openai_base_url"] = provider_base_url(runtime)
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
