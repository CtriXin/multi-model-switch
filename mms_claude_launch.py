"""Claude launch flow orchestration for MMS launchers.

The main flow imports launcher helpers lazily so the compatibility wrapper in
``mms_launchers.launch_claude`` keeps existing monkeypatch-based tests working.
"""

from __future__ import annotations

import os
import sys


def launch_claude_runtime(model_info, runtime, once=False, extra_args=None):
    """启动 Claude Code，支持 provider 和 OAuth 账号档案两种模式。"""
    from mms_launchers import (
        _anthropic_base_url,
        _apply_claude_model_overrides,
        _claude_route_status_paths,
        _default_gpt_reasoning_effort,
        _effective_context_window,
        _ensure_bridge_helpers,
        _ensure_speed_stats,
        _exec_or_run,
        _exit_oauth_claude_manual_only,
        _finalize_claude_slot,
        _gateway_claude_bridge_context,
        _health_check_due,
        _is_gpt_model,
        _launch_status,
        _mms_resume_command_name,
        _openai_base_url,
        _prepare_claude_env_with_status,
        _print_launch_step_done,
        _probe_models,
        _rescue_bridge_kwargs,
        _resolve_anthropic_base_url,
        _resolve_model,
        _resolve_native_fallback_routes,
        _resolve_real_home_command_path,
        _runtime_is_sensitive_claude_provider,
        _runtime_reasoning_effort,
        _runtime_supports_claude_1m,
        _runtime_thinking_enabled,
        _runtime_vision_sidecar,
        _safe_getcwd,
        build_provider_speed_scope,
        codex_claude_bridge,
        console,
        gateway_health_check,
        gemini_claude_bridge,
    )

    _ensure_bridge_helpers()
    _ensure_speed_stats()
    auth_mode = runtime.get("auth_mode", "api_key")
    enable_claude_1m = _runtime_supports_claude_1m(runtime)
    advertised_models = []
    bridge_cfg = None  # 由 gateway_claude_bridge 赋值，用于退出摘要
    probe_model = _resolve_model(model_info) if model_info else "claude-sonnet-4-6"
    lb_light = model_info.get("lb_light") if isinstance(model_info, dict) else None
    lb_medium = model_info.get("lb_medium") if isinstance(model_info, dict) else None
    lb_light = lb_light if lb_light and lb_light.strip() else None
    lb_medium = lb_medium if lb_medium and lb_medium.strip() else None
    if auth_mode == "oauth_bridge":
        console.print("[red]官方桥接已临时禁用，避免 Gemini/Codex 请求进入 Claude session。[/red]")
        sys.exit(1)
    if auth_mode == "oauth":
        _exit_oauth_claude_manual_only(runtime, model_info, caller="launch_claude")
    else:
        provider_id = runtime.get("id", "default")
        provider_profile = str(runtime.get("profile") or runtime.get("provider_profile") or "")
        if runtime.get("skip_gateway_health_check"):
            console.print("[dim]· 跳过 gateway 健康检查（provider 配置）[/dim]")
        elif not _health_check_due(provider_id):
            console.print("[dim]· 跳过 gateway 健康检查（24h 缓存有效）[/dim]")
        else:
            with _launch_status("健康检查中...", spinner="dots") as step_start:
                gateway_health_check(runtime)
            _print_launch_step_done("gateway 健康检查", step_start)

        speed_scope = build_provider_speed_scope(runtime)
        route_status_paths = _claude_route_status_paths()
        probe_result = runtime.get("_launch_prefetched_probe")
        if probe_result is None:
            try:
                with _launch_status("读取模型列表中...", spinner="dots") as step_start:
                    probe_result = _probe_models(runtime, emit_output=False)
                    advertised_models = list(probe_result.get("models") or [])
            except Exception:
                advertised_models = []
            if probe_result is None:
                console.print("[yellow]· 模型列表准备失败，继续使用空列表[/yellow]")
            else:
                base_source = probe_result.get("base_source")
                detail = f"{len(advertised_models)} 个模型"
                if base_source:
                    detail += f" · {base_source}"
                _print_launch_step_done("模型列表准备", step_start, detail)
        else:
            advertised_models = list(probe_result.get("models") or [])
            base_source = probe_result.get("base_source")
            detail = f"{len(advertised_models)} 个模型"
            if base_source:
                detail += f" · {base_source} · 复用预读取"
            else:
                detail += " · 复用预读取"
            console.print(f"[dim]· 模型列表准备跳过远端请求 ({detail})[/dim]")

        # ---- 三级兼容策略 ----
        # 1. 自动探测正确的 ANTHROPIC_BASE_URL（缓存 1h，避免重复请求）
        probe_model = _resolve_model(model_info) if model_info else "claude-sonnet-4-6"

        # 对不支持 Claude 模型的 provider，自动映射到支持的模型
        provider_id = runtime.get("id", "")
        strip_upstream_user_agent = "cliproxyapi" in provider_id.lower()
        minimal_claude_header_passthrough = _runtime_is_sensitive_claude_provider(runtime)
        if provider_id == "bailian-codingplan" and probe_model.startswith(("claude-", "sonnet-", "opus-", "haiku-")):
            # 百炼 CodingPlan 不支持 Claude 模型，使用其支持的 fallback 模型
            probe_model = "qwen3.5-plus"
            console.print(f"[dim]百炼 CodingPlan 不支持 Claude 模型，自动切换为: {probe_model}[/dim]")

        with _launch_status("解析 Anthropic endpoint 中...", spinner="dots") as step_start:
            anthropic_url, detect_method = _resolve_anthropic_base_url(runtime, probe_model=probe_model)
        resolve_detail = detect_method
        if anthropic_url:
            resolve_detail = f"{detect_method} · {anthropic_url}"
            _print_launch_step_done("Anthropic endpoint 解析", step_start, resolve_detail)
        else:
            _print_launch_step_done("Anthropic endpoint 解析", step_start, resolve_detail, style="yellow")

        # 跨 provider 负载配置：per-slot upstream url/key
        lb_slot_configs = model_info.get("lb_slot_configs") if isinstance(model_info, dict) else None

        # GPT-on-Claude: 获取 OpenAI URL 供 bridge 转发 GPT 模型
        _gpt_openai_url = _openai_base_url(runtime) or None
        # Claude Code 内部 NM() 只认识 Claude 模型的 context window。
        # 非 Claude 模型走 bridge 替换，env slot 用 Claude 壳名让 NM() 返回 1M，
        # 然后 CLAUDE_CODE_AUTO_COMPACT_WINDOW 按实际模型 context 往下 cap。
        # 路由状态栏仍显示真实模型名。
        _is_claude = any(k in probe_model.lower() for k in ("claude", "opus", "sonnet", "haiku"))
        if _gpt_openai_url and _is_gpt_model(probe_model):
            _env_model = "claude-sonnet-4-6"
        elif not _is_claude:
            _env_model = "claude-sonnet-4-6"
        else:
            _env_model = probe_model
        # 当使用 Claude 壳名时，保留真实模型名供 status line 显示
        _display_model = probe_model if _env_model != probe_model else None

        _thinking_enabled = _runtime_thinking_enabled(runtime)
        _gpt_default_effort = _default_gpt_reasoning_effort()
        if "reasoning_effort" in runtime:
            _reasoning_effort = _runtime_reasoning_effort(runtime, default=_gpt_default_effort)
        elif _gpt_openai_url and _is_gpt_model(probe_model):
            from mms_tui import select_reasoning_effort_tui as _sel_effort_claude
            _reasoning_effort = _sel_effort_claude(default=_gpt_default_effort)
        else:
            _reasoning_effort = "high"
        if _gpt_openai_url and _is_gpt_model(probe_model):
            console.print(f"[dim]thinking: {'on' if _thinking_enabled else 'off'} · effort: {_reasoning_effort}[/dim]")
        _vision_sidecar = _runtime_vision_sidecar(runtime)
        if _vision_sidecar:
            console.print(
                f"[dim]vision sidecar: {_vision_sidecar.get('provider_id', '-')} / {_vision_sidecar.get('model', '-')}[/dim]"
            )
        rescue_bridge_kwargs = _rescue_bridge_kwargs()

        if anthropic_url is not None:
            bridge_gw_url = anthropic_url.rstrip("/")
            if not bridge_gw_url.endswith("/v1"):
                bridge_gw_url += "/v1"
            native_fallback_routes = _resolve_native_fallback_routes(runtime, probe_model)
            if native_fallback_routes:
                fallback_ids = ", ".join(route.get("provider_id", "") for route in native_fallback_routes)
                console.print(f"[dim]native fallback: {fallback_ids}[/dim]")
            if lb_light or lb_medium:
                # 智能路由：通过本地 bridge 路由，以便拦截并切换模型
                cleanup_ctx = _gateway_claude_bridge_context(bridge_gw_url, runtime["api_key"],
                                                    heavy_model=probe_model,
                                                    medium_model=lb_medium or None,
                                                    light_model=lb_light or None,
                                                    advertised_models=advertised_models,
                                                    speed_scope=speed_scope,
                                                    route_status_paths=route_status_paths,
                                                    slot_configs=lb_slot_configs,
                                                    provider_id=provider_id,
                                                    provider_profile=provider_profile,
                                                    openai_url=_gpt_openai_url,
                                                    proxy_url=runtime.get("proxy"),
                                                    no_proxy=runtime.get("no_proxy"),
                                                    strip_upstream_user_agent=strip_upstream_user_agent,
                                                    minimal_claude_header_passthrough=minimal_claude_header_passthrough,
                                                    reasoning_enabled=_thinking_enabled,
                                                    reasoning_effort=_reasoning_effort,
                                                    native_fallback_routes=native_fallback_routes,
                                                    vision_sidecar=_vision_sidecar,
                                                    **rescue_bridge_kwargs)
                bridge_cfg = cleanup_ctx.__enter__()
                env = _prepare_claude_env_with_status(
                    runtime,
                    base_url=bridge_cfg["base_url"],
                    auth_token=bridge_cfg["api_key"],
                    heavy_model=_env_model,
                    medium_model=lb_medium or None,
                    light_model=lb_light or None,
                    selected_model=_env_model,
                    display_model=_display_model,
                )
                parts = [f"heavy: {probe_model}"]
                if lb_medium:
                    parts.append(f"medium: {lb_medium}")
                if lb_light:
                    parts.append(f"light: {lb_light}")
                if lb_slot_configs:
                    parts.append("跨provider")
                console.print(f"[dim]⚖️ 智能路由已启用 — {', '.join(parts)}[/dim]")
            else:
                # 直连 Anthropic provider 也统一过本地 bridge，补齐测速与 patched /v1/models。
                cleanup_ctx = _gateway_claude_bridge_context(
                    bridge_gw_url,
                    runtime["api_key"],
                    heavy_model=probe_model,
                    advertised_models=advertised_models,
                    speed_scope=speed_scope,
                    route_status_paths=route_status_paths,
                    provider_id=provider_id,
                    provider_profile=provider_profile,
                    openai_url=_gpt_openai_url,
                    proxy_url=runtime.get("proxy"),
                    no_proxy=runtime.get("no_proxy"),
                    strip_upstream_user_agent=strip_upstream_user_agent,
                    minimal_claude_header_passthrough=minimal_claude_header_passthrough,
                    reasoning_enabled=_thinking_enabled,
                    reasoning_effort=_reasoning_effort,
                    native_fallback_routes=native_fallback_routes,
                    vision_sidecar=_vision_sidecar,
                    **rescue_bridge_kwargs,
                )
                bridge_cfg = cleanup_ctx.__enter__()
                env = _prepare_claude_env_with_status(
                    runtime,
                    base_url=bridge_cfg["base_url"],
                    auth_token=bridge_cfg["api_key"],
                    heavy_model=_env_model,
                    selected_model=_env_model,
                    display_model=_display_model,
                )
            state_home = None

        elif runtime.get("bridge_source_cli"):
            # 2. Anthropic 端点不通，但配置了 bridge_source_cli → 自动切 bridge 模式
            bridge_src = runtime["bridge_source_cli"]
            console.print(
                f"[yellow]⚠ Anthropic 端点探测失败，自动切换到 {bridge_src} bridge 模式[/yellow]"
            )
            bridge_model = probe_model
            if bridge_src == "gemini":
                cleanup_ctx = gemini_claude_bridge(runtime, bridge_model)
            else:
                cleanup_ctx = codex_claude_bridge(runtime, bridge_model)
            bridge_cfg = cleanup_ctx.__enter__()
            env = _prepare_claude_env_with_status(
                runtime,
                base_url=bridge_cfg["base_url"],
                auth_token=bridge_cfg["api_key"],
                heavy_model=probe_model,
                medium_model=lb_medium or None,
                light_model=lb_light or None,
                selected_model=probe_model,
            )
            state_home = None

        elif _gpt_openai_url and _is_gpt_model(probe_model):
            # 2a-gpt. GPT-on-Claude: Anthropic 探测失败但有 OpenAI URL 且是 GPT 模型
            #   → 用 OpenAI URL 起 bridge，bridge 内部走 Responses API 转发
            openai_url = _gpt_openai_url
            api_key = runtime.get("openai_api_key") or runtime.get("api_key", "")
            console.print(f"[dim]🔀 GPT-on-Claude: 通过 OpenAI 端点 bridge → Responses API (thinking: {'on' if _thinking_enabled else 'off'}, effort: {_reasoning_effort})[/dim]")
            cleanup_ctx = _gateway_claude_bridge_context(openai_url, api_key,
                                                heavy_model=probe_model,
                                                medium_model=lb_medium or None,
                                                light_model=lb_light or None,
                                                advertised_models=advertised_models,
                                                speed_scope=speed_scope,
                                                route_status_paths=route_status_paths,
                                                slot_configs=lb_slot_configs,
                                                provider_id=provider_id,
                                                provider_profile=provider_profile,
                                                openai_url=openai_url,
                                                proxy_url=runtime.get("proxy"),
                                                no_proxy=runtime.get("no_proxy"),
                                                strip_upstream_user_agent=strip_upstream_user_agent,
                                                minimal_claude_header_passthrough=minimal_claude_header_passthrough,
                                                reasoning_enabled=_thinking_enabled,
                                                reasoning_effort=_reasoning_effort,
                                                vision_sidecar=_vision_sidecar,
                                                **rescue_bridge_kwargs)
            bridge_cfg = cleanup_ctx.__enter__()
            env = _prepare_claude_env_with_status(
                runtime,
                base_url=bridge_cfg["base_url"],
                auth_token=bridge_cfg["api_key"],
                heavy_model=_env_model,
                medium_model=lb_medium or None,
                light_model=lb_light or None,
                selected_model=_env_model,
                display_model=_display_model,
            )
            state_home = None

        elif _openai_base_url(runtime) and not _anthropic_base_url(runtime):
            # 2b. 纯 OpenAI provider（无 Anthropic 端点配置）→ 自动用 gateway bridge
            openai_url = _openai_base_url(runtime)
            api_key = runtime.get("openai_api_key") or runtime.get("api_key", "")
            console.print(
                f"[yellow]⚠ 无 Anthropic 端点，自动通过 OpenAI 端点 bridge[/yellow]"
            )
            cleanup_ctx = _gateway_claude_bridge_context(openai_url, api_key,
                                                heavy_model=probe_model,
                                                medium_model=lb_medium or None,
                                                light_model=lb_light or None,
                                                advertised_models=advertised_models,
                                                speed_scope=speed_scope,
                                                route_status_paths=route_status_paths,
                                                slot_configs=lb_slot_configs,
                                                provider_id=provider_id,
                                                provider_profile=provider_profile,
                                                openai_url=openai_url,
                                                proxy_url=runtime.get("proxy"),
                                                no_proxy=runtime.get("no_proxy"),
                                                strip_upstream_user_agent=strip_upstream_user_agent,
                                                minimal_claude_header_passthrough=minimal_claude_header_passthrough,
                                                vision_sidecar=_vision_sidecar,
                                                **rescue_bridge_kwargs)
            bridge_cfg = cleanup_ctx.__enter__()
            env = _prepare_claude_env_with_status(
                runtime,
                base_url=bridge_cfg["base_url"],
                auth_token=bridge_cfg["api_key"],
                heavy_model=_env_model,
                medium_model=lb_medium or None,
                light_model=lb_light or None,
                selected_model=_env_model,
                display_model=_display_model,
            )
            parts = [f"heavy: {probe_model}"]
            if lb_medium:
                parts.append(f"medium: {lb_medium}")
            if lb_light:
                parts.append(f"light: {lb_light}")
            console.print(f"[dim]⚖️ 智能路由已启用 — {', '.join(parts)}[/dim]")
            state_home = None

        elif lb_light or lb_medium:
            # 3b. 探测失败但配置了负载均衡 → 用 OpenAI 端点 + bridge 启用智能路由
            console.print(
                f"[yellow]⚠ Anthropic 探测失败，但配置了负载均衡，用 OpenAI bridge 启用智能路由[/yellow]"
            )
            openai_url = _openai_base_url(runtime)
            api_key = runtime.get("openai_api_key") or runtime.get("api_key", "")
            if openai_url:
                cleanup_ctx = _gateway_claude_bridge_context(openai_url, api_key,
                                                    heavy_model=probe_model,
                                                    medium_model=lb_medium,
                                                    light_model=lb_light,
                                                    advertised_models=advertised_models,
                                                    speed_scope=speed_scope,
                                                    route_status_paths=route_status_paths,
                                                    slot_configs=lb_slot_configs,
                                                    provider_id=provider_id,
                                                    provider_profile=provider_profile,
                                                    openai_url=openai_url,
                                                    proxy_url=runtime.get("proxy"),
                                                    no_proxy=runtime.get("no_proxy"),
                                                    strip_upstream_user_agent=strip_upstream_user_agent,
                                                    minimal_claude_header_passthrough=minimal_claude_header_passthrough,
                                                    vision_sidecar=_vision_sidecar,
                                                    **rescue_bridge_kwargs)
                bridge_cfg = cleanup_ctx.__enter__()
                env = _prepare_claude_env_with_status(
                    runtime,
                    base_url=bridge_cfg["base_url"],
                    auth_token=bridge_cfg["api_key"],
                    heavy_model=_env_model,
                    medium_model=lb_medium or None,
                    light_model=lb_light or None,
                    selected_model=_env_model,
                    display_model=_display_model,
                )
                parts = [f"heavy: {probe_model}"]
                if lb_medium:
                    parts.append(f"medium: {lb_medium}")
                if lb_light:
                    parts.append(f"light: {lb_light}")
                console.print(f"[dim]⚖️ 智能路由已启用 — {', '.join(parts)}[/dim]")
                state_home = None
            else:
                console.print("[red]✗ 无 OpenAI 端点，无法启用智能路由[/red]")
                env = _prepare_claude_env_with_status(runtime, base_url=None, selected_model=_env_model, display_model=_display_model)
                state_home = None
                cleanup_ctx = None

        else:
            # 3c. 探测失败且无 bridge 无负载均衡 → 保底继续
            configured_anthropic_url = str(_anthropic_base_url(runtime) or "").strip().rstrip("/")
            if configured_anthropic_url:
                bridge_gw_url = configured_anthropic_url
                if not bridge_gw_url.endswith("/v1"):
                    bridge_gw_url += "/v1"
                console.print(
                    "[yellow]⚠ Anthropic 端点探测失败，改用配置端点启动本地 bridge；"
                    "non-Claude 模型与 vision sidecar 仍由 bridge 接管[/yellow]"
                )
                native_fallback_routes = _resolve_native_fallback_routes(runtime, probe_model)
                cleanup_ctx = _gateway_claude_bridge_context(
                    bridge_gw_url,
                    runtime["api_key"],
                    heavy_model=probe_model,
                    advertised_models=advertised_models,
                    speed_scope=speed_scope,
                    route_status_paths=route_status_paths,
                    provider_id=provider_id,
                    provider_profile=provider_profile,
                    openai_url=_gpt_openai_url,
                    proxy_url=runtime.get("proxy"),
                    no_proxy=runtime.get("no_proxy"),
                    strip_upstream_user_agent=strip_upstream_user_agent,
                    minimal_claude_header_passthrough=minimal_claude_header_passthrough,
                    reasoning_enabled=_thinking_enabled,
                    reasoning_effort=_reasoning_effort,
                    native_fallback_routes=native_fallback_routes,
                    vision_sidecar=_vision_sidecar,
                    **rescue_bridge_kwargs,
                )
                bridge_cfg = cleanup_ctx.__enter__()
                env = _prepare_claude_env_with_status(
                    runtime,
                    base_url=bridge_cfg["base_url"],
                    auth_token=bridge_cfg["api_key"],
                    heavy_model=_env_model,
                    selected_model=_env_model,
                    display_model=_display_model,
                )
                state_home = None
            else:
                console.print("[yellow]⚠ Anthropic 端点探测失败，尝试继续（可在 provider 配置 bridge_source_cli 启用自动降级）[/yellow]")
                env = _prepare_claude_env_with_status(runtime, base_url=None, selected_model=_env_model, display_model=_display_model)
                state_home = None
                cleanup_ctx = None

    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    env["CLAUDE_CODE_ATTRIBUTION_HEADER"] = "0"
    env["API_TIMEOUT_MS"] = "3000000"
    env["MMS_RESUME_COMMAND_NAME"] = _mms_resume_command_name()

    # bridge 模式下跳过 model slot：Claude Code 用默认 claude-* 模型名通过校验，
    # bridge 在转发时替换成真实模型名（heavy_model / medium_model / light_model）。
    # GPT-on-Claude: OpenAI 模型名会被 Claude Code 拒绝，必须 skip，
    # bridge 层的 heavy_model 替换 + _forward_as_responses 会处理实际模型名。
    _resolved = _resolve_model(model_info) if model_info else ""
    _resolved_is_claude = any(k in (_resolved or "").lower() for k in ("claude", "opus", "sonnet", "haiku"))
    _skip_model = auth_mode == "oauth_bridge" or (
        isinstance(model_info, dict) and (model_info.get("lb_light") or model_info.get("lb_medium"))
    ) or (_resolved and _is_gpt_model(_resolved)) or (
        _resolved and not _resolved_is_claude  # 非 Claude 模型用壳名，跳过 slot 覆盖
    )

    if isinstance(model_info, dict):
        if not _skip_model:
            _apply_claude_model_overrides(env, model_info, enable_1m=enable_claude_1m)

        env["CLAUDE_CODE_ENABLE_SUBAGENT_PARALLELISM"] = "1"
        env["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"] = "5"
    elif not _skip_model:
        _apply_claude_model_overrides(env, model_info, enable_1m=enable_claude_1m)

    # ── Context window: 用真实模型名（probe_model）计算，非壳名 ──
    _real_models = [m for m in (probe_model, lb_medium, lb_light) if m]
    if not _real_models:
        _real_models = [_resolved or "claude-sonnet-4-6"]
    ctx_window = _effective_context_window(
        *_real_models,
        enable_claude_1m=enable_claude_1m,
        provider_id=(runtime or {}).get("id"),
    )
    env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(ctx_window)
    env["CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE"] = str(max(ctx_window - 3000, 10000))

    claude_bin = _resolve_real_home_command_path("claude", env) or "claude"
    cmd = [claude_bin]
    if runtime.get("bypass"):
        cmd += ["--add-dir", os.path.realpath(_safe_getcwd())]
        cmd.append("--dangerously-skip-permissions")
    if extra_args:
        cmd += list(extra_args)
    console.print("[dim]⏳ 正在启动 Claude CLI...[/dim]")
    session_home = env.get("HOME")
    exit_callback = None
    if session_home:
        exit_callback = lambda exit_code: _finalize_claude_slot(session_home, exit_code=exit_code)
    _exec_or_run(
        cmd,
        env,
        once,
        state_home=state_home,
        cleanup_context=cleanup_ctx,
        exit_callback=exit_callback,
        force_subprocess=bool(exit_callback),
        bridge_info=bridge_cfg,
    )
