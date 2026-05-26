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


__all__ = [
    "opencode_gateway_health_check",
    "opencode_global_command",
    "opencode_is_global_profile_runtime",
    "opencode_session_command",
]
