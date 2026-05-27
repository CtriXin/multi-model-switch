"""Codex launch flow orchestration for MMS launchers.

Lazy reads of bridge/speed helpers happen after launcher initialization so the
compatibility wrapper in ``mms_launchers.launch_codex`` keeps existing behavior.
"""

from __future__ import annotations

import subprocess
import sys


def launch_codex_runtime(model_info, runtime, once=False, extra_args=None):
    """启动 Codex，支持 provider 和 OAuth 账号档案两种模式。
    GPT 模型优先直连 Responses API；非 GPT 模型走本地 Chat Completions bridge。"""
    import mms_launchers as _launchers
    from mms_launchers import (
        _account_env,
        _append_codex_bypass_flags,
        _codex_gateway_env,
        _codex_provider_base_url,
        _codex_resume_writeback_callback,
        _default_gpt_reasoning_effort,
        _ensure_bridge_helpers,
        _ensure_speed_stats,
        _exec_or_run,
        _is_gpt_model,
        _openai_base_url,
        _prepare_oauth_home_context,
        _probe_models,
        _rescue_bridge_kwargs,
        _resolve_codex_responses_fallback_routes,
        _resolve_model,
        _runtime_reasoning_effort,
        _runtime_thinking_enabled,
        console,
        gateway_health_check,
        prepare_cli_command,
    )

    _ensure_bridge_helpers()
    _ensure_speed_stats()
    build_provider_speed_scope = _launchers.build_provider_speed_scope
    codex_chatcompletions_bridge = _launchers.codex_chatcompletions_bridge
    codex_responses_bridge = _launchers.codex_responses_bridge
    auth_mode = runtime.get("auth_mode", "api_key")
    if auth_mode == "oauth":
        model = _resolve_model(model_info)
        env = _account_env(runtime, model_info=model_info)
        _prepare_oauth_home_context(runtime, env, "codex")
        cmd = ["codex"]
        if model:
            cmd += ["-m", model]
        if extra_args:
            cmd += list(extra_args)
        _append_codex_bypass_flags(cmd, runtime)
        _exec_or_run(cmd, env, once, exit_callback=_codex_resume_writeback_callback(env))
        return

    gateway_health_check(runtime)
    model = _resolve_model(model_info)
    gateway_url = _openai_base_url(runtime)
    api_key = runtime.get("openai_api_key") or runtime.get("api_key", "")
    provider_id = runtime.get("id", "")
    provider_profile = str(runtime.get("profile") or runtime.get("provider_profile") or "")
    speed_scope = build_provider_speed_scope(runtime)
    try:
        advertised_models = list(_probe_models(runtime, emit_output=False).get("models") or [])
    except Exception:
        advertised_models = [model] if model else []

    if not _is_gpt_model(model):
        bridge_label = f"模型 {model}" if model else "当前模型"
        console.print(f"[dim]{bridge_label} 通过本地 Chat Completions bridge 启动 Codex...[/dim]")
        bridge_thinking_enabled = _runtime_thinking_enabled(runtime)
        bridge_reasoning_effort = _runtime_reasoning_effort(runtime, default="high")
        rescue_bridge_kwargs = _rescue_bridge_kwargs()
        with codex_chatcompletions_bridge(
            gateway_url,
            api_key,
            model_name=model or "unknown",
            advertised_models=advertised_models,
            speed_scope=speed_scope,
            provider_id=provider_id,
            provider_profile=provider_profile,
            reasoning_enabled=bridge_thinking_enabled,
            reasoning_effort=bridge_reasoning_effort,
            proxy_url=runtime.get("proxy"),
            no_proxy=runtime.get("no_proxy"),
            **rescue_bridge_kwargs,
        ) as bridge_cfg:
            bridge_base_url = _codex_provider_base_url(bridge_cfg["base_url"])
            env = _codex_gateway_env(runtime, bridge_cfg["base_url"], model_info=model_info)
            env["OPENAI_API_KEY"] = bridge_cfg["api_key"]
            env["OPENAI_BASE_URL"] = bridge_base_url
            cmd = ["codex"]
            cmd += ["-c", 'model_provider="custom"']
            cmd += ["-c", f'openai_base_url="{bridge_base_url}"']
            cmd += ["-c", f'model_providers.custom.base_url="{bridge_base_url}"']
            cmd += ["-c", "features.responses_websockets=false"]
            cmd += ["-c", "features.responses_websockets_v2=false"]
            if model:
                cmd += ["-m", model]
            if extra_args:
                cmd += list(extra_args)
            _append_codex_bypass_flags(cmd, runtime)
            exit_code = 0
            resume_exit_callback = _codex_resume_writeback_callback(env)
            try:
                cmd, env, _ = prepare_cli_command(cmd, env)
                result = subprocess.run(cmd, env=env)
                exit_code = result.returncode
            except KeyboardInterrupt:
                exit_code = 130
            finally:
                resume_exit_callback(exit_code)
            sys.exit(exit_code)
        return

    thinking_enabled = _runtime_thinking_enabled(runtime)
    gpt_default_effort = _default_gpt_reasoning_effort()
    if "reasoning_effort" in runtime:
        reasoning_effort = _runtime_reasoning_effort(runtime, default=gpt_default_effort)
    else:
        from mms_tui import select_reasoning_effort_tui as _sel_effort
        reasoning_effort = _sel_effort(default=gpt_default_effort)
    console.print(f"[dim]thinking: {'on' if thinking_enabled else 'off'} · effort: {reasoning_effort}[/dim]")
    native_fallback_routes = _resolve_codex_responses_fallback_routes(runtime, model)
    if native_fallback_routes:
        fallback_ids = ", ".join(route.get("provider_id", "") for route in native_fallback_routes)
        console.print(f"[dim]Codex Responses fallback: {fallback_ids}[/dim]")
    rescue_bridge_kwargs = _rescue_bridge_kwargs()
    with codex_responses_bridge(
        gateway_url,
        api_key,
        model_name=model or "unknown",
        advertised_models=advertised_models,
        speed_scope=speed_scope,
        provider_id=provider_id,
        provider_profile=provider_profile,
        reasoning_enabled=thinking_enabled,
        reasoning_effort=reasoning_effort,
        proxy_url=runtime.get("proxy"),
        no_proxy=runtime.get("no_proxy"),
        native_fallback_routes=native_fallback_routes,
        **rescue_bridge_kwargs,
    ) as bridge_cfg:
        bridge_base_url = _codex_provider_base_url(bridge_cfg["base_url"])
        env = _codex_gateway_env(runtime, bridge_cfg["base_url"], model_info=model_info)
        env["OPENAI_API_KEY"] = bridge_cfg["api_key"]
        env["OPENAI_BASE_URL"] = bridge_base_url
        cmd = ["codex"]
        cmd += ["-c", 'model_provider="custom"']
        if thinking_enabled:
            cmd += ["-c", f'model_reasoning_effort="{reasoning_effort}"']
        cmd += ["-c", f'openai_base_url="{bridge_base_url}"']
        cmd += ["-c", f'model_providers.custom.base_url="{bridge_base_url}"']
        cmd += ["-c", "features.responses_websockets=false"]
        cmd += ["-c", "features.responses_websockets_v2=false"]
        if model:
            cmd += ["-m", model]
        if extra_args:
            cmd += list(extra_args)
        _append_codex_bypass_flags(cmd, runtime)
        # 本地 responses bridge 运行在当前 Python 进程内；交互模式若 exec 替换自身，
        # bridge 线程会一并消失，Codex 随后访问 127.0.0.1:port 只会得到 5xx/连接失败。
        _exec_or_run(
            cmd,
            env,
            once,
            force_subprocess=True,
            exit_callback=_codex_resume_writeback_callback(env),
        )
