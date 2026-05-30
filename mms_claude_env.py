"""Claude gateway environment materialization for MMS launchers.

The imports from ``mms_launchers`` stay lazy so existing tests that monkeypatch
launcher helpers keep observing the same behavior through the compatibility
wrapper in ``mms_launchers._claude_gateway_env``.
"""

from __future__ import annotations

import os
from time import perf_counter


def build_claude_gateway_env(
    runtime,
    base_url=None,
    auth_token=None,
    heavy_model=None,
    medium_model=None,
    light_model=None,
    selected_model=None,
    runtime_kind=None,
    display_model=None,
    _timings=None,
):
    """Gateway api_key 模式独立 HOME（per-PID 会话隔离）：
    - 每个 mms 进程使用独立的 ~/.config/mms/claude-gateway/s/{pid}/ 作为 HOME
    - 启动时清理已死进程的残留目录
    - 剥离 migration 标记，防止 claude-sonnet-4-6[1m] 自动升级
    - 自动拉取 gateway 模型列表，填入所有 ANTHROPIC_*_MODEL slot
    - 写入 settings.json：teams 模式 / 隐藏 AI 署名 / 扩展思考
    base_url: 由 _resolve_anthropic_base_url() 探测后传入；
              为 None 时从 runtime 推断并去掉 /v1 后缀（保底兼容）。
    auth_token: 覆盖 ANTHROPIC_AUTH_TOKEN（bridge 模式传 bridge token）。
    heavy_model: bridge 模式下指定 heavy model，用于设置模型 slot。
    medium_model: bridge 模式下可选 medium model（仅用于展示）。
    light_model: bridge 模式下可选 light model（仅用于展示）。
    """
    import json as _json
    import mms_launchers as _launchers
    from mms_launchers import (
        _anthropic_base_url,
        _apply_claude_model_overrides,
        _apply_claude_visible_model_overrides,
        _apply_runtime_network_profile,
        _claude_resume_model_name,
        _claude_route_status_paths,
        _configure_agent_pack_session_env,
        _ensure_bridge_helpers,
        _ensure_claude_project_trust,
        _finalize_claude_slot,
        _get_model_health,
        _inject_managed_mcp_servers_into_claude_state,
        _inject_real_home_hints,
        _inject_selected_model_name,
        _install_host_context_env,
        _install_session_command_wrappers,
        _install_session_packet_env,
        _link_claude_library_entries,
        _link_real_local_bin,
        _link_shared_dotfiles,
        _load_claude_settings_from_dir,
        _load_json_dict_unlocked,
        _load_real_claude_project_state,
        _load_real_claude_settings,
        _load_real_claude_ui_state_seed,
        _merge_claude_settings,
        _merge_claude_ui_state_seed,
        _overlay_auto_github_contributor_session_entries,
        _overlay_caveman_session_entries,
        _overlay_codegraph_session_entries,
        _overlay_ecc_session_entries,
        _overlay_omc_session_entries,
        _overlay_project_scoped_claude_resume_state,
        _overlay_token_saver_session_entries,
        _overlay_toon_session_entries,
        _overlay_web_access_session_entries,
        _overlay_weber_session_entries,
        _overlay_xmem_session_entries,
        _persist_account_guard_launch,
        _pick_gateway_model,
        _prepare_claude_session_tree,
        _real_user_path,
        _reserve_session_home,
        _resolve_auto_github_contributor_root,
        _resolve_codegraph_root,
        _resolve_token_saver_root,
        _resolve_toon_root,
        _resolve_web_access_root,
        _resolve_weber_root,
        _resolve_xmem_root,
        _runtime_agent_pack,
        _runtime_caveman_enabled,
        _runtime_caveman_level,
        _runtime_is_sensitive_claude_provider,
        _runtime_nsr_enabled,
        _runtime_supports_claude_1m,
        _runtime_thinking_enabled,
        _safe_getcwd,
        _sanitize_claude_ui_state_seed_payload,
        _scrub_inherited_runtime_env,
        _selected_model_name,
        _session_skill_disabled,
        _set_session_home_hint,
        _timed_launch_step,
        _with_1m_suffix,
        _write_claude_session_settings,
        atomic_write_json,
        locked_state_file,
    )
    gateway_base = _real_user_path(".config", "mms", "claude-gateway")
    sessions_dir = os.path.join(gateway_base, "s")
    gateway_home, _active_before, _active_after = _reserve_session_home(
        sessions_dir,
        account_id=str(runtime.get("id", "")),
        runtime_kind=runtime_kind or str(runtime.get("auth_mode", "api_key")),
        stale_callback=_finalize_claude_slot,
        timings=_timings,
    )
    route_status_path = _claude_route_status_paths()[0]
    os.makedirs(gateway_home, exist_ok=True)
    disabled_session_surfaces = runtime.get("disabled_session_surfaces")
    agent_pack = _runtime_agent_pack(runtime)

    # 若调用方已通过 _resolve_anthropic_base_url 探测到正确 URL，直接用；
    # 否则保底剥离 /v1（避免双重 /v1/v1/messages）。
    if base_url is None:
        base_url = _anthropic_base_url(runtime)
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]

    # ── .claude.json：schema-based allowlist，避免未知 global 字段渗入 gateway session ──
    state_step_start = perf_counter()
    real_json = _real_user_path(".claude.json")
    gw_json = os.path.join(gateway_home, ".claude.json")
    data: dict = {}
    current_project = os.path.realpath(_safe_getcwd())
    current_project_state = _load_real_claude_project_state(current_project)
    resume_model = _claude_resume_model_name(display_model, selected_model, heavy_model)
    gw_existing = {}
    persistent_gateway_json = os.path.join(gateway_base, ".claude.json")
    persistent_gateway_claude_dir = os.path.join(gateway_base, ".claude")

    if os.path.exists(gw_json):
        try:
            with open(gw_json, encoding="utf-8") as f:
                loaded = _json.load(f)
            if isinstance(loaded, dict):
                gw_existing = loaded
            if (
                runtime.get("bypass")
                and isinstance(gw_existing, dict)
                and gw_existing.get("bypassPermissionsModeAccepted") is True
            ):
                data["bypassPermissionsModeAccepted"] = True
        except Exception:
            pass

    data = _merge_claude_ui_state_seed(data, _sanitize_claude_ui_state_seed_payload(gw_existing))
    data = _merge_claude_ui_state_seed(
        data,
        _sanitize_claude_ui_state_seed_payload(_load_json_dict_unlocked(persistent_gateway_json)),
    )
    data = _merge_claude_ui_state_seed(data, _load_real_claude_ui_state_seed())
    data = _inject_managed_mcp_servers_into_claude_state(
        data,
        disabled_session_surfaces=disabled_session_surfaces,
        agent_pack=agent_pack,
    )

    # 当用户在 TUI 选择不 bypass 时，主动移除持久化的 bypass 状态，
    # 避免旧 session 残留的 bypassPermissionsModeAccepted 导致 Claude Code 自动进入 bypass
    if not runtime.get("bypass"):
        data.pop("bypassPermissionsModeAccepted", None)
    data["alwaysThinkingEnabled"] = _runtime_thinking_enabled(runtime)
    data = _ensure_claude_project_trust(
        data,
        current_project,
        project_state=current_project_state,
        disabled_session_surfaces=disabled_session_surfaces,
    )
    data = _overlay_project_scoped_claude_resume_state(
        data,
        current_project,
        account_id=str(runtime.get("id", "")),
        runtime_kind=runtime_kind or str(runtime.get("auth_mode", "api_key")),
        resume_model=resume_model,
    )
    with locked_state_file(gw_json):
        atomic_write_json(gw_json, data, mode=0o600)
    if isinstance(_timings, list):
        _timings.append(("claude state seed", perf_counter() - state_step_start))

    # ── .local/bin symlink：Claude Code 检测 $HOME/.local/bin/claude（installMethod=native）──
    with _timed_launch_step(_timings, "link shared home entries"):
        _link_real_local_bin(gateway_home)

        # ── Library allowlist：仅保留 Keychain 依赖 ──
        _link_claude_library_entries(gateway_home)

        _link_shared_dotfiles(gateway_home)

    # ── ~/.claude 目录：仅保留 project-scoped 持久项，其余不再继承真实树 ──
    gw_claude_dir = os.path.join(gateway_home, ".claude")
    with _timed_launch_step(_timings, "prepare claude tree"):
        _prepare_claude_session_tree(
            gateway_home,
            gw_claude_dir,
            account_id=str(runtime.get("id", "")),
            account_home=gateway_base,
            runtime_kind=runtime_kind or str(runtime.get("auth_mode", "api_key")),
            resume_model=resume_model,
            skip_real_entries={"settings.json"},
        )
    report = runtime.get("_account_guard_report")
    if report:
        _persist_account_guard_launch(
            str(runtime.get("id", "")),
            report,
            session_home=gateway_home,
        )

    # ── settings.json：继承用户配置 + 覆盖 gateway 必要字段 ──
    effective_token = auth_token or runtime["api_key"]
    provider_id = runtime.get("id", "")
    enable_claude_1m = _runtime_supports_claude_1m(runtime)
    enable_caveman = _runtime_caveman_enabled(runtime)
    caveman_level = _runtime_caveman_level(runtime)
    enable_nsr = _runtime_nsr_enabled(runtime)
    enable_ecc = agent_pack == "ecc"
    enable_omc = agent_pack == "omc"
    sensitive_provider = _runtime_is_sensitive_claude_provider(runtime)
    # 启动首帧优先写本次选中的真实模型名，避免 statusline / 初始 active model
    # 先落到 slot 占位名；bridge 仍负责把请求路由到实际目标模型。
    if auth_token:
        best_model = selected_model or heavy_model or "claude-sonnet-4-6"
    elif selected_model:
        best_model = selected_model
    elif provider_id == "bailian-codingplan":
        # 百炼 CodingPlan：使用其支持的模型名（如 qwen3.5-plus）
        fallback = runtime.get("fallback_models", [])
        best_model = fallback[0] if fallback else "qwen3.5-plus"
    else:
        best_model = _pick_gateway_model(runtime, base_url)
    mms_model_name = _selected_model_name(display_model, selected_model, heavy_model, best_model)
    required_settings_env: dict = {
        "ANTHROPIC_AUTH_TOKEN": effective_token,
        "ANTHROPIC_BASE_URL": base_url,
        "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
        "MMS_ROUTE_STATUS_PATH": route_status_path,
    }
    if mms_model_name:
        required_settings_env["MMS_MODEL_NAME"] = mms_model_name
    default_settings_env: dict = {}
    if sensitive_provider:
        required_settings_env["CLAUDE_CODE_DISABLE_1M_CONTEXT"] = "1"
    else:
        default_settings_env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
    if best_model:
        for key in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
                    "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                    "ANTHROPIC_REASONING_MODEL"):
            required_settings_env[key] = best_model
    if selected_model:
        _apply_claude_model_overrides(
            required_settings_env,
            selected_model,
            enable_1m=enable_claude_1m,
        )
    # 非 Claude 模型默认仍可用于 status；但 non-Claude [1m] selector 不能进入
    # ANTHROPIC_MODEL，否则 Claude Code compact/resume 会按字面模型名校验失败。
    if display_model:
        _apply_claude_visible_model_overrides(
            required_settings_env,
            display_model,
            fallback_model=(
                required_settings_env.get("ANTHROPIC_MODEL")
                or selected_model
                or heavy_model
                or best_model
            ),
        )
    with _timed_launch_step(_timings, "write session settings"):
        host_context_env = _install_host_context_env(
            {},
            cli="claude",
            runtime=runtime,
            model_info={"model": display_model or selected_model or heavy_model or best_model or ""},
            session_home=gateway_home,
        )
        session_packet_env = _install_session_packet_env(
            {},
            cli="claude",
            runtime=runtime,
            model_info={
                "model": display_model or selected_model or heavy_model or best_model or "",
                "lb_medium": medium_model or "",
                "lb_light": light_model or "",
            },
            session_home=gateway_home,
            features={
                "caveman": enable_caveman,
                "nsr": enable_nsr,
                "ecc": enable_ecc,
                "omc": enable_omc,
                "agent_pack": agent_pack,
                "web_access": bool(_resolve_web_access_root()) and not _session_skill_disabled(disabled_session_surfaces, "web-access"),
                "weber": bool(_resolve_weber_root()) and not _session_skill_disabled(disabled_session_surfaces, "weber"),
                "codegraph": bool(_resolve_codegraph_root()) and not _session_skill_disabled(disabled_session_surfaces, "codegraph"),
                "toon": bool(_resolve_toon_root()) and not _session_skill_disabled(disabled_session_surfaces, "toon"),
                "token_saver": bool(_resolve_token_saver_root()) and not _session_skill_disabled(disabled_session_surfaces, "token-saver"),
                "xmem": bool(_resolve_xmem_root()) and not _session_skill_disabled(disabled_session_surfaces, "xmem"),
                "auto_github_contributor": bool(_resolve_auto_github_contributor_root()) and not _session_skill_disabled(disabled_session_surfaces, "auto-github-contributor"),
            },
            extra_paths={
                "route_status": route_status_path,
                "host_context": host_context_env.get("MMS_HOST_CONTEXT_JSON", ""),
            },
        )
        required_settings_env.update(host_context_env)
        required_settings_env.update(session_packet_env)
        session_base_settings = _merge_claude_settings(
            _load_real_claude_settings(),
            _load_claude_settings_from_dir(persistent_gateway_claude_dir),
        )
        _write_claude_session_settings(
            gw_claude_dir,
            required_env=required_settings_env,
            default_env=default_settings_env,
            base_settings=session_base_settings,
            enable_caveman=enable_caveman,
            caveman_level=caveman_level,
            enable_nsr=enable_nsr,
            enable_ecc=enable_ecc,
            enable_omc=enable_omc,
            disabled_session_surfaces=disabled_session_surfaces,
        )
    with _timed_launch_step(_timings, "overlay session assets"):
        _overlay_caveman_session_entries(
            gw_claude_dir,
            gateway_home,
            enable_caveman=enable_caveman,
            disabled_session_surfaces=disabled_session_surfaces,
        )
        _overlay_ecc_session_entries(
            gw_claude_dir,
            gateway_home,
            enable_ecc=enable_ecc,
            disabled_session_surfaces=disabled_session_surfaces,
        )
        _overlay_omc_session_entries(
            gw_claude_dir,
            gateway_home,
            enable_omc=enable_omc,
            disabled_session_surfaces=disabled_session_surfaces,
        )
        _overlay_web_access_session_entries(gw_claude_dir, gateway_home, disabled_session_surfaces=disabled_session_surfaces)
        _overlay_weber_session_entries(gw_claude_dir, gateway_home, disabled_session_surfaces=disabled_session_surfaces)
        _overlay_codegraph_session_entries(gw_claude_dir, gateway_home, disabled_session_surfaces=disabled_session_surfaces)
        _overlay_toon_session_entries(gw_claude_dir, gateway_home, disabled_session_surfaces=disabled_session_surfaces)
        _overlay_token_saver_session_entries(gw_claude_dir, gateway_home, disabled_session_surfaces=disabled_session_surfaces)
        _overlay_xmem_session_entries(gw_claude_dir, gateway_home, disabled_session_surfaces=disabled_session_surfaces)
        _overlay_auto_github_contributor_session_entries(gw_claude_dir, gateway_home, disabled_session_surfaces=disabled_session_surfaces)

    with _timed_launch_step(_timings, "build env and wrappers"):
        env = os.environ.copy()
        _scrub_inherited_runtime_env(env, strip_openai=True, strip_proxy=True)
        _inject_real_home_hints(env)
        env["HOME"] = gateway_home
        _set_session_home_hint(env, gateway_home)
        env.update(host_context_env)
        env.update(session_packet_env)
        env["ANTHROPIC_BASE_URL"] = base_url
        env["ANTHROPIC_AUTH_TOKEN"] = effective_token
        env["MMS_ROUTE_STATUS_PATH"] = route_status_path
        _inject_selected_model_name(env, mms_model_name)
        if sensitive_provider:
            env["CLAUDE_CODE_DISABLE_1M_CONTEXT"] = "1"
        if best_model:
            best_1m = _with_1m_suffix(best_model, enable_1m=enable_claude_1m)
            for key in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
                        "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_REASONING_MODEL"):
                env[key] = best_1m
            env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = best_model  # haiku 不支持 1M
        if selected_model:
            _apply_claude_model_overrides(env, selected_model, enable_1m=enable_claude_1m)
        if display_model:
            _apply_claude_visible_model_overrides(
                env,
                display_model,
                fallback_model=env.get("ANTHROPIC_MODEL")
                or selected_model
                or heavy_model
                or best_model,
            )
        if not sensitive_provider:
            env.setdefault("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
        env = _configure_agent_pack_session_env(env, agent_pack=agent_pack)
        _apply_runtime_network_profile(
            env,
            runtime,
            validate_proxy=bool(runtime.get("proxy")),
        )
        _install_session_command_wrappers(gateway_home, env)

    # Context window 在 launch_claude() 中用真实模型名计算，此处不设置

    # ── 写入 route_status.json 供 statusline 读取 ──
    # bridge 模式下用 heavy_model，直连模式下用 best_model
    with _timed_launch_step(_timings, "route status"):
        status_model = display_model or selected_model or heavy_model or best_model or "unknown"
        status_tier = "heavy" if auth_token else "-"
        status_reason = "init_selected_model" if selected_model else ("bridge_ready" if auth_token else "direct")
        _ensure_bridge_helpers()
        try:
            _launchers._write_route_status(status_tier, status_model, status_reason, status_paths=[route_status_path])
        except Exception:
            pass

        # ── health 预检摘要 ──
        try:
            _h = _get_model_health(status_model)
            if _h:
                _s = _h.get("status", "?")
                _b = _h.get("latency_bucket", "?")
                _icon = {"ok": "●", "slow": "◐", "degraded": "◑"}.get(_s, "?")
                print(f"  {_icon} {status_model}: {_s} ({_b})")
        except Exception:
            pass

    return env
