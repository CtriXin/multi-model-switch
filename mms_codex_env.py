"""Codex gateway environment materialization for MMS launchers.

Imports from ``mms_launchers`` stay lazy so existing monkeypatch-based tests keep
working through the compatibility wrapper in ``mms_launchers._codex_gateway_env``.
"""

from __future__ import annotations

import os
import shutil


def build_codex_gateway_env(runtime, base_url, model_info=None):
    """为 gateway api_key 模式创建隔离 session，并复用稳定 CODEX_HOME。"""
    import json as _json
    from mms_launchers import (
        _append_codex_mcp_servers_from_claude_json,
        _append_codex_session_hook_trust_states,
        _apply_runtime_ip_stack_profile,
        _apply_runtime_locale_profile,
        _apply_runtime_network_profile,
        _build_codex_session_hooks,
        _cleanup_stale_sessions,
        _codex_bounded_resume_entries,
        _codex_entry_is_session_local,
        _codex_sibling_session_roots,
        _collect_codex_hook_trust_seed_sources,
        _inject_real_home_hints,
        _inject_selected_model_name,
        _install_host_context_env,
        _install_session_command_wrappers,
        _install_session_packet_env,
        _link_claude_library_entries,
        _link_shared_dotfiles,
        _materialize_codex_session_entry,
        _overlay_agent_browser_session_entries,
        _overlay_auto_github_contributor_session_entries,
        _overlay_caveman_session_entries,
        _overlay_codex_plugin_marketplace_cache,
        _overlay_token_saver_session_entries,
        _overlay_toon_session_entries,
        _overlay_web_access_session_entries,
        _overlay_weber_session_entries,
        _overlay_xmem_session_entries,
        _real_user_path,
        _resolve_agent_browser_root,
        _resolve_auto_github_contributor_root,
        _resolve_token_saver_root,
        _resolve_toon_root,
        _resolve_web_access_root,
        _resolve_weber_root,
        _resolve_xmem_root,
        _runtime_caveman_enabled,
        _runtime_nsr_enabled,
        _safe_getcwd,
        _scrub_inherited_runtime_env,
        _seed_codex_bounded_resume,
        _session_skill_disabled,
        _set_codex_resume_writeback_root,
        _set_codex_soft_home,
        _sync_codex_session_claude_json,
        _toml_literal,
        _write_codex_hook_trust_cache,
        atomic_write_json,
    )
    openai_key = runtime.get("openai_api_key") or runtime["api_key"]
    disabled_session_surfaces = runtime.get("disabled_session_surfaces")
    gateway_base = _real_user_path(".config", "mms", "codex-gateway")
    gateway_codex_dir = os.path.join(gateway_base, ".codex")
    os.makedirs(gateway_base, exist_ok=True)

    # --- per-PID session 隔离（与 Claude gateway 对齐） ---
    sessions_dir = os.path.join(gateway_base, "s")
    session_home = os.path.join(sessions_dir, str(os.getpid()))
    os.makedirs(session_home, exist_ok=True)
    precleanup_trust_texts, precleanup_trust_payloads = _collect_codex_hook_trust_seed_sources(
        _codex_sibling_session_roots(
            sessions_dir,
            exclude_session_home=session_home,
            max_roots=24,
        )
    )
    _cleanup_stale_sessions(sessions_dir)

    # symlink gateway_base 下的非 s 子项到 session_home
    for entry in os.listdir(gateway_base):
        if entry == "s":
            continue
        src = os.path.join(gateway_base, entry)
        dst = os.path.join(session_home, entry)
        if not os.path.exists(dst) and not os.path.islink(dst):
            os.symlink(src, dst)
    # Codex 已使用 soft-home；这里只清理旧的 broad Library symlink 并保留最小 Keychains。
    _link_claude_library_entries(session_home)

    _link_shared_dotfiles(session_home)
    _sync_codex_session_claude_json(
        session_home,
        disabled_session_surfaces=disabled_session_surfaces,
    )

    # Codex hook trust is keyed by CODEX_HOME/hooks.json. Keep session_home
    # per-PID for wrappers/tmp, but make CODEX_HOME stable across launches.
    codex_dir = gateway_codex_dir
    os.makedirs(codex_dir, exist_ok=True)
    session_codex_link = os.path.join(session_home, ".codex")
    if not os.path.exists(session_codex_link) and not os.path.islink(session_codex_link):
        try:
            os.symlink(codex_dir, session_codex_link)
        except OSError:
            pass

    auth_path = os.path.join(codex_dir, "auth.json")
    with open(auth_path, "w") as f:
        _json.dump({"auth_mode": "apikey", "OPENAI_API_KEY": openai_key}, f)
    enable_caveman = _runtime_caveman_enabled(runtime)
    enable_nsr = _runtime_nsr_enabled(runtime)
    real_codex_dir = _real_user_path(".codex")
    real_hooks_path = os.path.join(real_codex_dir, "hooks.json")
    sibling_codex_roots = _codex_sibling_session_roots(
        sessions_dir,
        exclude_session_home=session_home,
    )
    _overlay_codex_plugin_marketplace_cache(
        codex_dir,
        [gateway_codex_dir, real_codex_dir],
    )
    trust_config_texts, trust_hook_payloads = _collect_codex_hook_trust_seed_sources(
        [real_codex_dir, gateway_codex_dir] + sibling_codex_roots
    )
    trust_config_texts = precleanup_trust_texts + trust_config_texts
    trust_hook_payloads = {**precleanup_trust_payloads, **trust_hook_payloads}
    base_hooks = {}
    session_hooks = None
    hooks_path = os.path.join(codex_dir, "hooks.json")
    if enable_caveman or enable_nsr or os.path.exists(real_hooks_path):
        try:
            with open(real_hooks_path, "r", encoding="utf-8") as f:
                base_hooks = _json.load(f)
        except Exception:
            base_hooks = {}
        if isinstance(base_hooks, dict):
            trust_hook_payloads[real_hooks_path] = base_hooks
        session_hooks = _build_codex_session_hooks(
            base_hooks,
            enable_caveman=enable_caveman,
            enable_nsr=enable_nsr,
            disabled_session_surfaces=disabled_session_surfaces,
        )

    def _set_top_level_scalar(text, key, value):
        import re
        section_match = re.search(r'^\[', text, flags=re.MULTILINE)
        preamble_end = section_match.start() if section_match else len(text)
        preamble = text[:preamble_end]
        rest = text[preamble_end:]
        pattern = rf'^{re.escape(key)}\s*=\s*.+$'
        replacement = f'{key} = {_toml_literal(value)}'
        if re.search(pattern, preamble, flags=re.MULTILINE):
            preamble = re.sub(pattern, replacement, preamble, count=1, flags=re.MULTILINE)
        else:
            if preamble and not preamble.endswith("\n"):
                preamble += "\n"
            preamble += f"{replacement}\n"
        return preamble + rest

    def _set_project_base_url(text, project_path, value):
        import re
        escaped_path = re.escape(project_path)
        header_pattern = rf'^\[projects\."{escaped_path}"\]\s*$'
        match = re.search(header_pattern, text, flags=re.MULTILINE)
        if not match:
            block = f'\n[projects."{project_path}"]\nbase_url = {_toml_literal(value)}\n'
            return text.rstrip() + block + "\n"

        block_start = match.end()
        next_header = re.search(r'^\[', text[block_start:], flags=re.MULTILINE)
        block_end = block_start + next_header.start() if next_header else len(text)
        block = text[block_start:block_end]
        if re.search(r'^\s*base_url\s*=\s*"[^"]*"', block, flags=re.MULTILINE):
            block = re.sub(
                r'^\s*base_url\s*=\s*"[^"]*"',
                f'base_url = {_toml_literal(value)}',
                block,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            if not block.startswith("\n"):
                block = "\n" + block
            if block and not block.endswith("\n"):
                block += "\n"
            block += f'base_url = {_toml_literal(value)}\n'
        return text[:block_start] + block + text[block_end:]

    def _set_project_scalar(text, project_path, key, value):
        import re
        escaped_path = re.escape(project_path)
        header_pattern = rf'^\[projects\."{escaped_path}"\]\s*$'
        match = re.search(header_pattern, text, flags=re.MULTILINE)
        if not match:
            block = (
                f'\n[projects."{project_path}"]\n'
                f'{key} = {_toml_literal(value)}\n'
            )
            return text.rstrip() + block + "\n"

        block_start = match.end()
        next_header = re.search(r'^\[', text[block_start:], flags=re.MULTILINE)
        block_end = block_start + next_header.start() if next_header else len(text)
        block = text[block_start:block_end]
        key_pattern = rf'^\s*{re.escape(key)}\s*=\s*.+$'
        if re.search(key_pattern, block, flags=re.MULTILINE):
            block = re.sub(
                key_pattern,
                f'{key} = {_toml_literal(value)}',
                block,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            if not block.startswith("\n"):
                block = "\n" + block
            if block and not block.endswith("\n"):
                block += "\n"
            block += f'{key} = {_toml_literal(value)}\n'
        return text[:block_start] + block + text[block_end:]

    def _set_table_scalar(text, table_header, key, value):
        import re
        escaped_header = re.escape(table_header)
        header_pattern = rf'^\[{escaped_header}\]\s*$'
        match = re.search(header_pattern, text, flags=re.MULTILINE)
        if not match:
            block = f'\n[{table_header}]\n{key} = {_toml_literal(value)}\n'
            return text.rstrip() + block + "\n"

        block_start = match.end()
        next_header = re.search(r'^\[', text[block_start:], flags=re.MULTILINE)
        block_end = block_start + next_header.start() if next_header else len(text)
        block = text[block_start:block_end]
        key_pattern = rf'^\s*{re.escape(key)}\s*=\s*.+$'
        if re.search(key_pattern, block, flags=re.MULTILINE):
            block = re.sub(
                key_pattern,
                f'{key} = {_toml_literal(value)}',
                block,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            if not block.startswith("\n"):
                block = "\n" + block
            if block and not block.endswith("\n"):
                block += "\n"
            block += f'{key} = {_toml_literal(value)}\n'
        return text[:block_start] + block + text[block_end:]

    def _rewrite_table_block(text, table_header, entries):
        import re
        escaped_header = re.escape(table_header)
        pattern = re.compile(
            rf'^\[{escaped_header}\]\s*$.*?(?=^\[|\Z)',
            flags=re.MULTILINE | re.DOTALL,
        )
        text = pattern.sub("", text).rstrip()
        block_lines = [f'[{table_header}]']
        for key, value in entries:
            block_lines.append(f'{key} = {_toml_literal(value)}')
        block = "\n".join(block_lines) + "\n"
        if text:
            text += "\n\n"
        return text + block

    def _normalize_toml_layout(text):
        import re
        # Repair malformed cases like `[model_providers.custom]name = "custom"`.
        text = re.sub(r'(\[[^\]\n]+\])([A-Za-z0-9_"-]+\s*=)', r'\1' + "\n" + r'\2', text)
        if text and not text.endswith("\n"):
            text += "\n"
        return text

    # 复制用户 config.toml，但把顶层和当前项目的 base_url 都替换成隔离地址
    # Codex CLI 会读取 project-scoped config，单改顶层 base_url 不够。
    gateway_config_template = os.path.join(gateway_base, ".codex", "config.toml")
    real_config = _real_user_path(".codex", "config.toml")
    # Prefer the user's real config as the source of truth. The gateway template
    # may contain stale custom sections from previous buggy generations.
    source_config = real_config if os.path.exists(real_config) else gateway_config_template
    gateway_config = os.path.join(codex_dir, "config.toml")
    if os.path.exists(source_config):
        try:
            with open(source_config, "r", encoding="utf-8") as f:
                config_text = f.read()
            config_text = _set_top_level_scalar(config_text, "forced_login_method", "api")
            config_text = _set_top_level_scalar(config_text, "disable_response_storage", True)
            config_text = _set_top_level_scalar(config_text, "base_url", base_url)
            config_text = _set_project_base_url(config_text, _safe_getcwd(), base_url)
            config_text = _set_project_scalar(config_text, _safe_getcwd(), "trust_level", "trusted")
            config_text = _rewrite_table_block(
                config_text,
                "model_providers.custom",
                [
                    ("name", "custom"),
                    ("wire_api", "responses"),
                    ("requires_openai_auth", True),
                    ("base_url", base_url),
                ],
            )
            config_text = _append_codex_mcp_servers_from_claude_json(
                config_text,
                disabled_session_surfaces=disabled_session_surfaces,
            )
            config_text = _normalize_toml_layout(config_text)
            config_text = _append_codex_session_hook_trust_states(
                config_text,
                target_hooks_path=hooks_path,
                target_hooks=session_hooks,
                trust_config_texts=trust_config_texts,
                source_hook_payloads_by_path=trust_hook_payloads,
            )
            with open(gateway_config, "w", encoding="utf-8") as f:
                f.write(config_text)
        except Exception:
            shutil.copy2(source_config, gateway_config)
    else:
        with open(gateway_config, "w", encoding="utf-8") as f:
            f.write('forced_login_method = "api"\n')
            f.write('disable_response_storage = true\n')
            f.write(f'base_url = "{base_url}"\n')
            f.write('\n[model_providers.custom]\n')
            f.write('name = "custom"\n')
            f.write('wire_api = "responses"\n')
            f.write('requires_openai_auth = true\n')
            f.write(f'base_url = "{base_url}"\n')
            f.write(f'\n[projects."{_safe_getcwd()}"]\n')
            f.write(f'base_url = "{base_url}"\n')
            f.write('trust_level = "trusted"\n')
        try:
            with open(gateway_config, "r", encoding="utf-8") as f:
                config_text = f.read()
            config_text = _append_codex_mcp_servers_from_claude_json(
                config_text,
                disabled_session_surfaces=disabled_session_surfaces,
            )
            config_text = _normalize_toml_layout(config_text)
            config_text = _append_codex_session_hook_trust_states(
                config_text,
                target_hooks_path=hooks_path,
                target_hooks=session_hooks,
                trust_config_texts=trust_config_texts,
                source_hook_payloads_by_path=trust_hook_payloads,
            )
            with open(gateway_config, "w", encoding="utf-8") as f:
                f.write(config_text)
        except Exception:
            pass

    if session_hooks is not None:
        try:
            with open(gateway_config, "r", encoding="utf-8") as handle:
                session_config_for_trust = handle.read()
        except Exception:
            session_config_for_trust = ""
        launch_trust_payloads = dict(trust_hook_payloads)
        launch_trust_payloads[hooks_path] = session_hooks
        _write_codex_hook_trust_cache(
            gateway_codex_dir,
            session_hooks,
            trust_config_texts=trust_config_texts + [session_config_for_trust],
            source_hook_payloads_by_path=launch_trust_payloads,
        )
        atomic_write_json(hooks_path, session_hooks, mode=0o600)

    # symlink 真实 ~/.codex 下的其余子项（skills、memories 等），
    # but materialize resume/history entries locally with hard bounds below.
    if os.path.isdir(real_codex_dir):
        skip = {"auth.json", "config.toml", "hooks.json"} | _codex_bounded_resume_entries()
        for entry in os.listdir(real_codex_dir):
            if entry in skip or _codex_entry_is_session_local(entry):
                continue
            src = os.path.join(real_codex_dir, entry)
            dst = os.path.join(codex_dir, entry)
            _materialize_codex_session_entry(entry, src, dst)
    source_roots = [gateway_codex_dir]
    source_roots.extend(sibling_codex_roots)
    source_roots.append(real_codex_dir)
    _seed_codex_bounded_resume(source_roots, codex_dir)
    _overlay_caveman_session_entries(
        codex_dir,
        session_home,
        enable_caveman=enable_caveman,
        disabled_session_surfaces=disabled_session_surfaces,
    )
    _overlay_web_access_session_entries(codex_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    _overlay_weber_session_entries(codex_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    _overlay_agent_browser_session_entries(codex_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    _overlay_toon_session_entries(codex_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    _overlay_token_saver_session_entries(codex_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    _overlay_xmem_session_entries(codex_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)
    _overlay_auto_github_contributor_session_entries(codex_dir, session_home, disabled_session_surfaces=disabled_session_surfaces)

    env = os.environ.copy()
    _scrub_inherited_runtime_env(env, strip_openai=True, strip_proxy=True)
    _inject_real_home_hints(env, include_xdg=True)
    _inject_selected_model_name(env, model_info=model_info)
    _set_codex_soft_home(env, session_home)
    env["CODEX_HOME"] = codex_dir
    _set_codex_resume_writeback_root(env, gateway_codex_dir)
    env["OPENAI_API_KEY"] = openai_key
    env["OPENAI_BASE_URL"] = base_url
    _apply_runtime_network_profile(env, runtime, validate_proxy=False)
    _apply_runtime_locale_profile(env, runtime)
    _apply_runtime_ip_stack_profile(env, runtime)
    _install_session_command_wrappers(session_home, env)
    host_context_env = _install_host_context_env(
        env,
        cli="codex",
        runtime=runtime,
        model_info=model_info,
        session_home=session_home,
    )
    _install_session_packet_env(
        env,
        cli="codex",
        runtime=runtime,
        model_info=model_info,
        session_home=session_home,
        features={
            "caveman": enable_caveman,
            "nsr": enable_nsr,
            "web_access": bool(_resolve_web_access_root()) and not _session_skill_disabled(disabled_session_surfaces, "web-access"),
            "weber": bool(_resolve_weber_root()) and not _session_skill_disabled(disabled_session_surfaces, "weber"),
            "agent_browser": bool(_resolve_agent_browser_root()) and not _session_skill_disabled(disabled_session_surfaces, "agent-browser"),
            "toon": bool(_resolve_toon_root()) and not _session_skill_disabled(disabled_session_surfaces, "toon"),
            "token_saver": bool(_resolve_token_saver_root()) and not _session_skill_disabled(disabled_session_surfaces, "token-saver"),
            "xmem": bool(_resolve_xmem_root()) and not _session_skill_disabled(disabled_session_surfaces, "xmem"),
            "auto_github_contributor": bool(_resolve_auto_github_contributor_root()) and not _session_skill_disabled(disabled_session_surfaces, "auto-github-contributor"),
        },
        extra_paths={"host_context": host_context_env.get("MMS_HOST_CONTEXT_JSON", "")},
    )
    return env
