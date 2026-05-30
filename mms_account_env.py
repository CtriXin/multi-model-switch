"""OAuth/account runtime environment materialization for MMS launchers.

The implementation resolves helpers through ``mms_launchers`` at call time so
existing monkeypatch-based tests keep observing the compatibility wrapper.
"""

from __future__ import annotations

import os


def build_account_env(account, *, validate_proxy=True, model_info=None):
    import json as _json
    import mms_launchers as _launchers

    env = os.environ.copy()
    _launchers._scrub_inherited_runtime_env(env, strip_openai=True, strip_proxy=True)
    _launchers._inject_real_home_hints(env)
    _launchers._inject_selected_model_name(env, model_info=model_info)
    home_dir = os.path.expanduser(str(account.get("home_dir", "")).strip())
    session_home = ""
    if not home_dir:
        _launchers.console.print(f"[red]账号档案 '{account.get('id', 'unknown')}' 未配置 home_dir[/red]")
        _launchers.sys.exit(1)
    cli_name = account.get("cli")
    disabled_session_surfaces = account.get("disabled_session_surfaces")
    if cli_name == "claude":
        _launchers.seed_claude_state(home_dir)
        account_claude_dir = os.path.join(home_dir, ".claude")
        os.makedirs(account_claude_dir, exist_ok=True)
        sessions_dir = os.path.join(home_dir, "s")
        session_home, active_before, active_after = _launchers._reserve_session_home(
            sessions_dir,
            account_id=account.get("id", ""),
            runtime_kind="oauth",
            stale_callback=_launchers._finalize_claude_slot,
            max_live_sessions=4,
        )
        if not session_home:
            _launchers.console.print(f"[red]该账号当前将达到 {active_after} 个并发会话，已超过安全上限 4[/red]")
            _launchers.sys.exit(1)
        report = account.get("_account_guard_report")
        if isinstance(report, dict):
            report["active_sessions_before"] = active_before
            report["active_sessions_after"] = active_after
        account_json = os.path.join(home_dir, ".claude.json")
        session_json = os.path.join(session_home, ".claude.json")
        if os.path.exists(account_json):
            try:
                _launchers._copy_claude_state_json(account_json, session_json, mode="oauth")
            except Exception:
                pass
        current_project = os.path.realpath(_launchers._safe_getcwd())
        current_project_state = _launchers._load_real_claude_project_state(current_project)
        session_state = {}
        if os.path.exists(session_json):
            try:
                with open(session_json, encoding="utf-8") as f:
                    loaded = _json.load(f)
                if isinstance(loaded, dict):
                    session_state = loaded
            except Exception:
                session_state = {}
        session_state = _launchers._merge_claude_ui_state_seed(
            session_state,
            _launchers._load_real_claude_ui_state_seed(),
        )
        session_state = _launchers._strip_claude_state_execution_surfaces(session_state)
        if account.get("bypass"):
            session_state["bypassPermissionsModeAccepted"] = True
        else:
            session_state.pop("bypassPermissionsModeAccepted", None)
        session_state = _launchers._ensure_claude_project_trust(
            session_state,
            current_project,
            project_state=current_project_state,
            allow_execution_surfaces=False,
        )
        with _launchers.locked_state_file(session_json):
            _launchers.atomic_write_json(session_json, session_state, mode=0o600)
        _launchers._link_real_local_bin(session_home)
        _launchers._link_claude_library_entries(session_home)
        _launchers._link_shared_dotfiles(session_home)
        session_claude_dir = os.path.join(session_home, ".claude")
        _launchers._prepare_claude_session_tree(
            session_home,
            session_claude_dir,
            account_id=account.get("id", ""),
            account_home=home_dir,
            runtime_kind="oauth",
            skip_real_entries={"settings.json"},
            source_claude_dir=account_claude_dir,
            allowed_source_entries=_launchers._CLAUDE_OAUTH_SESSION_SOURCE_ENTRY_ALLOWLIST,
        )
        _launchers._seed_oauth_claude_session_settings(account_claude_dir, session_claude_dir)
        _launchers._overlay_web_access_session_entries(
            session_claude_dir,
            session_home,
            disabled_session_surfaces=disabled_session_surfaces,
        )
        _launchers._overlay_weber_session_entries(
            session_claude_dir,
            session_home,
            disabled_session_surfaces=disabled_session_surfaces,
        )
        _launchers._overlay_xmem_session_entries(
            session_claude_dir,
            session_home,
            disabled_session_surfaces=disabled_session_surfaces,
        )
        _launchers._scrub_claude_oauth_env(env)
        env["HOME"] = session_home
        _launchers._set_session_home_hint(env, session_home)
        _launchers._install_host_context_env(
            env,
            cli="claude",
            runtime=account,
            model_info=model_info,
            session_home=session_home,
        )
    elif cli_name == "gemini":
        _launchers.seed_gemini_state(home_dir)
        _launchers._scrub_claude_oauth_env(env)
        env["GEMINI_CLI_HOME"] = home_dir
    elif cli_name == "agy":
        _launchers.seed_agy_state(home_dir)
        _launchers._scrub_claude_oauth_env(env)
        _launchers._ensure_account_library_entries(home_dir)
        sessions_dir = os.path.join(home_dir, "s")
        session_home = os.path.join(sessions_dir, str(os.getpid()))
        os.makedirs(session_home, exist_ok=True)
        _launchers._cleanup_stale_sessions(sessions_dir)
        for entry in os.listdir(home_dir):
            if entry == "s":
                continue
            src = os.path.join(home_dir, entry)
            dst = os.path.join(session_home, entry)
            if not os.path.exists(dst) and not os.path.islink(dst):
                os.symlink(src, dst)
        _launchers._link_account_library_entries(session_home, home_dir)
        _launchers._link_shared_dotfiles(session_home)
        env["HOME"] = session_home
        env["XDG_CONFIG_HOME"] = os.path.join(session_home, ".config")
        _launchers._set_session_home_hint(env, session_home)
        _launchers._install_session_command_wrappers(session_home, env)
        keychain_path = _launchers._ensure_agy_account_keychain(home_dir, session_home=session_home)
        if keychain_path:
            env["MMS_AGY_KEYCHAIN"] = keychain_path
        _launchers._install_agy_security_wrapper(session_home, home_dir, env)
        _launchers._overlay_agy_session_assets(
            home_dir,
            session_home,
            enable_caveman=_launchers._runtime_caveman_enabled(account),
            caveman_level=_launchers._runtime_caveman_level(account),
            disabled_session_surfaces=disabled_session_surfaces,
        )
        host_context_env = _launchers._install_host_context_env(
            env,
            cli="agy",
            runtime=account,
            model_info=model_info,
            session_home=session_home,
        )
    else:
        sessions_dir = os.path.join(home_dir, "s")
        session_home = os.path.join(sessions_dir, str(os.getpid()))
        os.makedirs(session_home, exist_ok=True)
        _launchers._cleanup_stale_sessions(sessions_dir)
        for entry in os.listdir(home_dir):
            if entry == "s":
                continue
            src = os.path.join(home_dir, entry)
            dst = os.path.join(session_home, entry)
            if not os.path.exists(dst) and not os.path.islink(dst):
                os.symlink(src, dst)
        _launchers._link_claude_library_entries(session_home)
        _launchers._link_shared_dotfiles(session_home)
        if cli_name == "codex":
            _launchers._scrub_claude_oauth_env(env)
            _launchers._sync_codex_session_claude_json(
                session_home,
                disabled_session_surfaces=disabled_session_surfaces,
            )
            codex_resume_writeback_root = _launchers._overlay_codex_shared_resume(home_dir, session_home)
            _launchers._overlay_web_access_session_entries(
                os.path.join(session_home, ".codex"),
                session_home,
                disabled_session_surfaces=disabled_session_surfaces,
            )
            _launchers._overlay_weber_session_entries(
                os.path.join(session_home, ".codex"),
                session_home,
                disabled_session_surfaces=disabled_session_surfaces,
            )
            _launchers._overlay_agent_browser_session_entries(
                os.path.join(session_home, ".codex"),
                session_home,
                disabled_session_surfaces=disabled_session_surfaces,
            )
            _launchers._overlay_toon_session_entries(
                os.path.join(session_home, ".codex"),
                session_home,
                disabled_session_surfaces=disabled_session_surfaces,
            )
            _launchers._overlay_token_saver_session_entries(
                os.path.join(session_home, ".codex"),
                session_home,
                disabled_session_surfaces=disabled_session_surfaces,
            )
            _launchers._overlay_xmem_session_entries(
                os.path.join(session_home, ".codex"),
                session_home,
                disabled_session_surfaces=disabled_session_surfaces,
            )
            _launchers._overlay_auto_github_contributor_session_entries(
                os.path.join(session_home, ".codex"),
                session_home,
                disabled_session_surfaces=disabled_session_surfaces,
            )
        if cli_name == "codex":
            _launchers._set_codex_soft_home(env, session_home)
            _launchers._set_codex_resume_writeback_root(env, codex_resume_writeback_root)
        else:
            xdg_config_home = os.path.join(session_home, ".config")
            env["HOME"] = session_home
            env["XDG_CONFIG_HOME"] = xdg_config_home
            _launchers._set_session_home_hint(env, session_home)
        _launchers._install_session_command_wrappers(session_home, env)
        host_context_env = _launchers._install_host_context_env(
            env,
            cli=cli_name or "codex",
            runtime=account,
            model_info=model_info,
            session_home=session_home,
        )
    if cli_name == "codex" and session_home:
        _launchers._install_session_packet_env(
            env,
            cli="codex",
            runtime=account,
            model_info=model_info,
            session_home=session_home,
            features={
                "web_access": bool(_launchers._resolve_web_access_root()) and not _launchers._session_skill_disabled(disabled_session_surfaces, "web-access"),
                "weber": bool(_launchers._resolve_weber_root()) and not _launchers._session_skill_disabled(disabled_session_surfaces, "weber"),
                "agent_browser": bool(_launchers._resolve_agent_browser_root()) and not _launchers._session_skill_disabled(disabled_session_surfaces, "agent-browser"),
                "toon": bool(_launchers._resolve_toon_root()) and not _launchers._session_skill_disabled(disabled_session_surfaces, "toon"),
                "token_saver": bool(_launchers._resolve_token_saver_root()) and not _launchers._session_skill_disabled(disabled_session_surfaces, "token-saver"),
                "xmem": bool(_launchers._resolve_xmem_root()) and not _launchers._session_skill_disabled(disabled_session_surfaces, "xmem"),
                "auto_github_contributor": bool(_launchers._resolve_auto_github_contributor_root()) and not _launchers._session_skill_disabled(disabled_session_surfaces, "auto-github-contributor"),
            },
            extra_paths={"host_context": host_context_env.get("MMS_HOST_CONTEXT_JSON", "")},
        )
    _launchers._apply_runtime_network_profile(env, account, validate_proxy=validate_proxy)
    env["MMS_ACCOUNT_ID"] = str(account.get("id", ""))
    if cli_name == "claude":
        _launchers._persist_account_guard_launch(
            account.get("id", ""),
            account.get("_account_guard_report", {}),
            session_home=env.get("HOME", ""),
        )
    return env
