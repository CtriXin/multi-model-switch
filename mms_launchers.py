"""MMS 启动器：按 provider 或账号档案启动 CLI。"""

import json
import copy
import os
import re
import shlex
import shutil
import sys
import subprocess
import tempfile
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from time import perf_counter

from mms_runtime.account_state import activated_claude_account_state, seed_agy_state, seed_claude_state, seed_gemini_state
from mms_launcher.account_guard import (
    account_guard_profile as _account_guard_profile_impl,
    build_account_guard_report as _build_account_guard_report_impl,
    claude_account_guard_entry as _claude_account_guard_entry_impl,
    claude_guard_runtime as _claude_guard_runtime_impl,
    count_live_session_dirs as _count_live_session_dirs_impl,
    format_account_guard_summary as _format_account_guard_summary_impl,
    persist_account_guard_launch as _persist_account_guard_launch_impl,
    proxy_fingerprint as _proxy_fingerprint_impl,
    record_account_guard_finalize as _record_account_guard_finalize_impl,
)
from mms_runtime.i18n import normalize_language
from mms_launcher.console import LauncherLazyConsole
from mms_launcher.health import (
    health_check_due as _health_check_due_impl,
    load_gateway_health_cache as _load_gateway_health_cache_impl,
    save_gateway_health_cache as _save_gateway_health_cache_impl,
)
from mms_opencode.agents import (
    opencode_apply_agent_bypass_permissions,
    opencode_lite_agent_configs,
    opencode_lite_pro_agent_configs,
    opencode_permission_bypass_value,
)
from mms_opencode.config import (
    OPENCODE_API_KEY_ENV,
    OPENCODE_BYPASS_FLAG,
    OPENCODE_BYPASS_PERMISSION_ENV,
    OPENCODE_DEFAULT_OUTPUT_LIMIT,
    OPENCODE_IMAGE_INPUT_MODELS,
    OPENCODE_LITE_DEFAULT_AGENT,
    OPENCODE_MODEL_LIMIT_OVERRIDES,
    OPENCODE_PROVIDER_ID,
    opencode_agent_model_refs as _opencode_agent_model_refs,
    opencode_apply_bypass_env as _opencode_apply_bypass_env,
    opencode_apply_route_env as _opencode_apply_route_env,
    opencode_build_config_content as _opencode_build_config_content_impl,
    opencode_build_config_payload as _opencode_build_config_payload_impl,
    opencode_bypass_enabled as _opencode_bypass_enabled,
    opencode_config_slug as _opencode_config_slug,
    opencode_entrypoint as _opencode_entrypoint,
    opencode_env_bool as _opencode_env_bool,
    opencode_explicit_output_limit as _opencode_explicit_output_limit,
    opencode_launch_candidates as _opencode_launch_candidates,
    opencode_launch_preflight_enabled as _opencode_launch_preflight_enabled,
    opencode_model_config as _opencode_model_config_impl,
    opencode_model_limit_override as _opencode_model_limit_override,
    opencode_model_names as _opencode_model_names,
    opencode_model_output_limit as _opencode_model_output_limit,
    opencode_model_ref as _opencode_model_ref,
    opencode_model_requires_reasoning_roundtrip_guard as _opencode_model_requires_reasoning_roundtrip_guard,
    opencode_output_limit as _opencode_output_limit,
    opencode_preflight_timeout as _opencode_preflight_timeout,
    opencode_provider_base_url as _opencode_provider_base_url,
    opencode_route_by_id as _opencode_route_by_id,
    opencode_route_env_key as _opencode_route_env_key,
    opencode_route_model_ref as _opencode_route_model_ref,
    opencode_route_provider_ref as _opencode_route_provider_ref,
    opencode_runtime_bool as _opencode_runtime_bool,
    opencode_runtime_routes as _opencode_runtime_routes,
)
from mms_opencode.env import (
    opencode_export_config_path as _opencode_export_config_path_impl,
    opencode_gateway_env as _opencode_gateway_env_impl,
    opencode_global_export_env as _opencode_global_export_env_impl,
    opencode_global_omo_env as _opencode_global_omo_env_impl,
    opencode_provider_export_env as _opencode_provider_export_env_impl,
    opencode_set_soft_home as _opencode_set_soft_home_impl,
    opencode_write_config as _opencode_write_config_impl,
)
from mms_opencode.launch import (
    launch_opencode as _opencode_launch_impl,
    opencode_gateway_health_check as _opencode_gateway_health_check_impl,
    opencode_global_command as _opencode_global_command_impl,
    opencode_is_global_profile_runtime as _opencode_is_global_profile_runtime_impl,
    opencode_session_command as _opencode_session_command_impl,
)
from mms_opencode.preflight import (
    opencode_run_preflight as _opencode_run_preflight_impl,
    opencode_select_launch_candidate as _opencode_select_launch_candidate_impl,
)
from mms_opencode.session import (
    clear_opencode_config_env as _clear_opencode_config_env,
    overlay_opencode_session_assets as _overlay_opencode_session_assets_impl,
    opencode_rtk_plugin_path as _opencode_rtk_plugin_path_impl,
    opencode_session_plugin_runtime as _opencode_session_plugin_runtime,
    opencode_xmem_plugin_path as _opencode_xmem_plugin_path_impl,
    overlay_opencode_plugin as _overlay_opencode_plugin_impl,
)
from mms_agy import security as _agy_security
from mms_codex import assets as _codex_assets
from mms_codex import claude_state as _codex_claude_state
from mms_codex import hooks as _codex_hooks
from mms_codex import hook_trust as _codex_hook_trust
from mms_codex import resume as _codex_resume
from mms_session import env as _session_env
from mms_session import assets as _session_assets
from mms_session import hook_commands as _session_hook_commands
from mms_session import mcp as _session_mcp
from mms_session import overlays as _session_overlays
from mms_core import (
    DEFAULT_ACCOUNT_TIMEZONE,
    _normalize_claude_1m_mode,
    _model_supports_vision,
    _probe_models,
    _runtime_force_ipv4,
    _runtime_httpx_request,
    detect_working_base_url,
    load_config,
    preference_asset_root,
)
from mms_registry.capability_resolver import resolve_model_capabilities
from mms_runtime.fake_upstream import (
    ensure_local_proxy as _ensure_fake_upstream_proxy,
    fake_proxy_probe as _fake_proxy_probe,
    is_enabled as _fake_upstream_enabled,
    status_payload as _fake_upstream_status_payload,
)
from mms_runtime.host_context import host_capability_env, resolve_tool_bins, write_host_context
from mms_claude import endpoint as _claude_endpoint
from mms_claude.launch import launch_claude_runtime as launch_claude
from mms_claude import model as _claude_model
from mms_claude import session as _claude_session
from mms_claude.project_store import CLAUDE_PERSISTENT_ENTRIES, claude_raw_entry_path, ensure_claude_project_store, read_slot_marker, write_slot_marker
from mms_codex.launch import launch_codex_runtime as launch_codex
from mms_display.launch import (
    emit_dns_guard_hint as _emit_dns_guard_hint_impl,
    launch_status as _launch_status_impl,
    print_launch_step_done as _print_launch_step_done_impl,
    show_launch_info as _show_launch_info_impl,
    timed_launch_step as _timed_launch_step_impl,
)
from mms_launcher.exec import (
    exec_or_run as _exec_or_run_impl,
    print_session_summary as _print_session_summary_impl,
)
from mms_launcher.export import (
    dedupe_path_parts as _dedupe_path_parts,
    inject_selected_model_name as _inject_selected_model_name,
    launcher_script_path as _launcher_script_path,
    real_home_wrapper_scrub_lines as _real_home_wrapper_scrub_lines_impl,
    selected_model_name as _selected_model_name,
    set_session_home_hint as _set_session_home_hint,
    truthy as _truthy,
    write_real_home_script as _write_real_home_script,
    xmem_cli_path as _xmem_cli_path_impl,
)
from mms_registry.provider_profiles import profile_context_window, resolve_provider_profile
from mms_pi import support as _pi_support
from mms_runtime import cli_search_dirs, prepare_cli_command
from mms_runtime import exposure as _runtime_exposure
from mms_runtime import models as _runtime_models
from mms_runtime import urls as _runtime_urls
from mms_runtime import validation as _runtime_validation
from mms_runtime.env import (
    apply_runtime_locale_profile as _apply_runtime_locale_profile_impl,
    runtime_locale_env as _runtime_locale_env_impl,
    scrub_claude_oauth_env as _scrub_claude_oauth_env_impl,
    scrub_inherited_runtime_env as _scrub_inherited_runtime_env_impl,
    validate_timezone_or_exit as _validate_timezone_or_exit_impl,
)
from mms_runtime.context import (
    DEFAULT_CONTEXT_WINDOW as _DEFAULT_CONTEXT_WINDOW,
    MIMO_PLAIN_ONE_M_CONTEXT_WINDOWS as _MIMO_PLAIN_ONE_M_CONTEXT_WINDOWS,
    MODEL_CONTEXT_WINDOWS as _MODEL_CONTEXT_WINDOWS,
    ONE_M_CONTEXT_SUFFIX as _ONE_M_CONTEXT_SUFFIX,
    ONE_M_SUFFIX_BASE_SAFE_CONTEXT_WINDOWS as _ONE_M_SUFFIX_BASE_SAFE_CONTEXT_WINDOWS,
    ONE_M_SUFFIX_CONTEXT_WINDOWS as _ONE_M_SUFFIX_CONTEXT_WINDOWS,
    load_model_context_overrides as _load_model_context_overrides_impl,
    lookup_context_window as _lookup_context_window_impl,
)
from mms_runtime.home import (
    build_home_context as _build_home_context_impl,
    home_context_lines as _home_context_lines_impl,
    normalize_path as _normalize_path_impl,
    path_is_within as _path_is_within_impl,
    prepare_oauth_home_context as _prepare_oauth_home_context_impl,
    runtime_dns_mode as _runtime_dns_mode_impl,
    runtime_net_mode as _runtime_net_mode_impl,
    validate_home_context_or_exit as _validate_home_context_or_exit_impl,
)
from mms_runtime.network import (
    CLAUDE_NO_PROXY_TOKENS as _CLAUDE_NO_PROXY_TOKENS,
    CLAUDE_PROXY_GUARD_TARGETS as _CLAUDE_PROXY_GUARD_TARGETS,
    apply_proxy_env as _apply_proxy_env_impl,
    apply_runtime_ip_stack_profile as _apply_runtime_ip_stack_profile_impl,
    apply_runtime_network_profile as _apply_runtime_network_profile_impl,
    base_claude_network_guard as _base_claude_network_guard_impl,
    build_claude_network_guard as _build_claude_network_guard_impl,
    claude_bypass_requires_proxy as _claude_bypass_requires_proxy_impl,
    check_proxy_connectivity_or_exit as _check_proxy_connectivity_or_exit_impl,
    claude_network_guard_cache_key as _claude_network_guard_cache_key_impl,
    claude_no_proxy_conflicts as _claude_no_proxy_conflicts_impl,
    enforce_claude_network_guard_or_exit as _enforce_claude_network_guard_or_exit_impl,
    get_claude_network_guard_preview as _get_claude_network_guard_preview_impl,
    mask_proxy_url as _mask_proxy_url_impl,
    mask_secret as _mask_secret_impl,
    provider_id_set_from_env as _provider_id_set_from_env_impl,
    proxy_dns_mode as _proxy_dns_mode_impl,
    run_proxy_probe as _run_proxy_probe_impl,
    runtime_declares_sensitive_claude as _runtime_declares_sensitive_claude_impl,
    runtime_is_sensitive_claude_provider as _runtime_is_sensitive_claude_provider_impl,
    runtime_network_summary as _runtime_network_summary_impl,
    split_no_proxy_values as _split_no_proxy_values_impl,
)
from mms_session.features import (
    asset_root_preference as _asset_root_preference_impl,
    default_gpt_reasoning_effort as _default_gpt_reasoning_effort_impl,
    is_installed_mms_layout as _is_installed_mms_layout_impl,
    normalize_agent_pack as _normalize_agent_pack_impl,
    normalize_caveman_level as _normalize_caveman_level_impl,
    normalize_caveman_mode as _normalize_caveman_mode_impl,
    normalize_ecc_mode as _normalize_ecc_mode_impl,
    normalize_nsr_mode as _normalize_nsr_mode_impl,
    normalize_reasoning_effort as _normalize_reasoning_effort_impl,
    normalize_thinking_mode as _normalize_thinking_mode_impl,
    resolve_agent_browser_root as _resolve_agent_browser_root_impl,
    resolve_auto_github_contributor_root as _resolve_auto_github_contributor_root_impl,
    resolve_caveman_root as _resolve_caveman_root_impl,
    resolve_codegraph_root as _resolve_codegraph_root_impl,
    resolve_ecc_root as _resolve_ecc_root_impl,
    resolve_nsr_root as _resolve_nsr_root_impl,
    resolve_omc_root as _resolve_omc_root_impl,
    resolve_token_saver_root as _resolve_token_saver_root_impl,
    resolve_toon_root as _resolve_toon_root_impl,
    resolve_web_access_root as _resolve_web_access_root_impl,
    resolve_weber_root as _resolve_weber_root_impl,
    resolve_xmem_root as _resolve_xmem_root_impl,
    runtime_agent_pack as _runtime_agent_pack_impl,
    runtime_caveman_enabled as _runtime_caveman_enabled_impl,
    runtime_caveman_level as _runtime_caveman_level_impl,
    runtime_ecc_enabled as _runtime_ecc_enabled_impl,
    runtime_nsr_enabled as _runtime_nsr_enabled_impl,
    runtime_omc_enabled as _runtime_omc_enabled_impl,
    runtime_reasoning_effort as _runtime_reasoning_effort_impl,
    runtime_thinking_enabled as _runtime_thinking_enabled_impl,
    runtime_vision_sidecar as _runtime_vision_sidecar_impl,
)
from mms_session.guard import (
    bounded_env_float as _bounded_env_float_impl,
    read_session_guard_marker as _read_session_guard_marker_impl,
    reserve_session_home as _reserve_session_home_impl,
    session_guard_lock_path as _session_guard_lock_path_impl,
    session_guard_marker_path as _session_guard_marker_path_impl,
    session_guard_pid_alive as _session_guard_pid_alive_impl,
    session_guard_process_identity as _session_guard_process_identity_impl,
    session_home_is_active as _session_home_is_active_impl,
    write_session_guard_marker as _write_session_guard_marker_impl,
)
from mms_session.assets import resolve_local_hooks_dir as _resolve_local_hooks_dir_impl
from mms_session.index import finalize_claude_session, list_indexed_sessions, record_claude_session_start
from mms_session.packet import write_session_packet
from mms_runtime.state_io import (
    atomic_write_json,
    atomic_write_text,
    load_json_dict_unlocked as _load_json_dict_unlocked_impl,
    locked_state_file,
    mms_config_root_mode,
    resolve_mms_config_dir as _resolve_mms_config_dir,
    utc_now_z as _utc_now_z_impl,
)
from mms_runtime.state_io import resolve_current_workdir as _safe_getcwd

_build_gateway_url = None
codex_claude_bridge = None
gemini_claude_bridge = None
gateway_claude_bridge = None
codex_chatcompletions_bridge = None
codex_responses_bridge = None
_write_route_status = None
build_provider_speed_scope = None

try:
    from mms_runtime.health_cache import get_model_health as _get_model_health
except ImportError:
    def _get_model_health(*_a, **_kw): return None


def _ensure_bridge_helpers():
    global _build_gateway_url, codex_claude_bridge, gemini_claude_bridge
    global gateway_claude_bridge, codex_chatcompletions_bridge, codex_responses_bridge, _write_route_status
    if _build_gateway_url is not None:
        return
    from mms_launcher.bridge import load_bridge_helpers

    helpers = load_bridge_helpers()
    _build_gateway_url = helpers["_build_gateway_url"]
    codex_claude_bridge = helpers["codex_claude_bridge"]
    gemini_claude_bridge = helpers["gemini_claude_bridge"]
    gateway_claude_bridge = helpers["gateway_claude_bridge"]
    codex_chatcompletions_bridge = helpers["codex_chatcompletions_bridge"]
    codex_responses_bridge = helpers["codex_responses_bridge"]
    _write_route_status = helpers["_write_route_status"]


def _gateway_claude_bridge_context(*args, **kwargs):
    """Compatibility wrapper for gateway Claude bridge signature downgrade."""
    from mms_launcher.bridge import gateway_claude_bridge_context

    return gateway_claude_bridge_context(gateway_claude_bridge, *args, console=console, **kwargs)


def _ensure_speed_stats():
    global build_provider_speed_scope
    if build_provider_speed_scope is not None:
        return
    from mms_launcher.bridge import load_speed_stats_helper

    build_provider_speed_scope = load_speed_stats_helper()

console = LauncherLazyConsole()
_launch_status = partial(_launch_status_impl, console=console)
_print_launch_step_done = partial(
    _print_launch_step_done_impl,
    console=console,
    perf_counter_fn=perf_counter,
)
_timed_launch_step = partial(_timed_launch_step_impl, perf_counter_fn=perf_counter)

# Keep the former private helper names importable while the implementation lives in mms_opencode.agents.
_opencode_lite_agent_configs = opencode_lite_agent_configs
_opencode_lite_pro_agent_configs = opencode_lite_pro_agent_configs
_opencode_permission_bypass_value = opencode_permission_bypass_value
_opencode_apply_agent_bypass_permissions = opencode_apply_agent_bypass_permissions


_mask_proxy_url = partial(_mask_proxy_url_impl, mask_secret_fn=_mask_secret_impl)
_runtime_locale_env = partial(_runtime_locale_env_impl, normalize_language_fn=normalize_language)
_proxy_dns_mode = _proxy_dns_mode_impl


_runtime_network_summary = partial(
    _runtime_network_summary_impl,
    mask_proxy_url_fn=_mask_proxy_url,
    runtime_force_ipv4_fn=_runtime_force_ipv4,
    fake_upstream_enabled_fn=_fake_upstream_enabled,
    proxy_dns_mode_fn=_proxy_dns_mode,
    runtime_locale_env_fn=_runtime_locale_env,
    default_account_timezone=DEFAULT_ACCOUNT_TIMEZONE,
)


_guard_utc_now = _utc_now_z_impl


_apply_runtime_locale_profile = partial(
    _apply_runtime_locale_profile_impl,
    runtime_locale_env_fn=_runtime_locale_env,
)

_provider_id_set_from_env = partial(_provider_id_set_from_env_impl, environ=os.environ)


_runtime_declares_sensitive_claude = _runtime_declares_sensitive_claude_impl


def _load_model_context_overrides():
    """Compatibility wrapper for model context-window overrides."""
    return _load_model_context_overrides_impl(
        _model_context_overrides_path(),
        _MODEL_CONTEXT_OVERRIDES_CACHE,
    )


def _lookup_context_window(model_name, provider_id=None):
    """Compatibility wrapper for runtime context-window lookup."""
    return _lookup_context_window_impl(
        model_name,
        provider_id=provider_id,
        context_overrides_loader=_load_model_context_overrides,
        model_context_windows=_MODEL_CONTEXT_WINDOWS,
    )


_runtime_supports_claude_1m = _claude_model.runtime_supports_claude_1m
_effective_context_window = _claude_model.effective_context_window


_runtime_is_sensitive_claude_provider = partial(
    _runtime_is_sensitive_claude_provider_impl,
    provider_id_set_from_env_fn=_provider_id_set_from_env,
    runtime_declares_sensitive_claude_fn=_runtime_declares_sensitive_claude,
)




def _prepare_claude_env_with_status(runtime, **kwargs):
    from mms_display.launch import (
        launch_timing_enabled,
        launch_timing_threshold_sec,
        prepare_claude_env_with_status,
        print_launch_timing_breakdown,
    )

    def _print_timing_breakdown(timings, *, total_elapsed):
        return print_launch_timing_breakdown(
            timings,
            total_elapsed=total_elapsed,
            console=console,
            launch_timing_enabled_fn=lambda: launch_timing_enabled(environ=os.environ),
            launch_timing_threshold_sec_fn=lambda: launch_timing_threshold_sec(environ=os.environ),
        )

    return prepare_claude_env_with_status(
        runtime,
        claude_gateway_env_fn=_claude_gateway_env,
        launch_status_fn=_launch_status,
        print_launch_step_done_fn=_print_launch_step_done,
        print_launch_timing_breakdown_fn=_print_timing_breakdown,
        perf_counter_fn=perf_counter,
        **kwargs,
    )


def _real_user_home():
    explicit = str(os.environ.get("MMS_REAL_HOME", "")).strip()
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))

    home = os.path.abspath(os.environ.get("HOME") or os.path.expanduser("~"))
    markers = (
        f"{os.sep}.config{os.sep}mms{os.sep}codex-gateway{os.sep}",
        f"{os.sep}.config{os.sep}mms{os.sep}claude-gateway{os.sep}",
    )
    for marker in markers:
        if marker in home:
            return home.split(marker, 1)[0]
    return home


def _real_user_path(*parts):
    return os.path.join(_real_user_home(), *parts)


def _account_guard_state_path():
    return _real_user_path(".config", "mms", "account-guard-state.json")


_load_json_dict_unlocked = _load_json_dict_unlocked_impl


def _read_account_guard_state():
    path = _account_guard_state_path()
    with locked_state_file(path):
        return _load_json_dict_unlocked(path)


_claude_account_guard_entry = _claude_account_guard_entry_impl


def _count_live_session_dirs(sessions_dir):
    """Compatibility wrapper for active Claude session counting."""
    return _count_live_session_dirs_impl(
        sessions_dir,
        session_home_is_active_fn=_session_home_is_active,
    )


_proxy_fingerprint = _proxy_fingerprint_impl


_account_guard_profile = partial(
    _account_guard_profile_impl,
    runtime_force_ipv4_fn=_runtime_force_ipv4,
    default_account_timezone=DEFAULT_ACCOUNT_TIMEZONE,
)


def _build_account_guard_report(account):
    """Compatibility wrapper for account guard launch reports."""
    return _build_account_guard_report_impl(
        account,
        read_account_guard_state_fn=_read_account_guard_state,
        count_live_session_dirs_fn=_count_live_session_dirs,
        claude_account_guard_entry_fn=_claude_account_guard_entry,
        account_guard_profile_fn=_account_guard_profile,
    )


def _claude_guard_runtime(runtime):
    """Compatibility wrapper for Claude account guard runtime projection."""
    return _claude_guard_runtime_impl(runtime, real_user_path_fn=_real_user_path)


_format_account_guard_summary = _format_account_guard_summary_impl


def _persist_account_guard_launch(account_id, report, *, session_home=""):
    """Compatibility wrapper for account guard launch persistence."""
    return _persist_account_guard_launch_impl(
        account_id,
        report,
        session_home=session_home,
        account_guard_state_path_fn=_account_guard_state_path,
        locked_state_file_fn=locked_state_file,
        load_json_dict_unlocked_fn=_load_json_dict_unlocked,
        claude_account_guard_entry_fn=_claude_account_guard_entry,
        guard_utc_now_fn=_guard_utc_now,
        atomic_write_json_fn=atomic_write_json,
    )


def _record_account_guard_finalize(account_id, *, exit_code=None, stale_cleanup=False):
    """Compatibility wrapper for account guard exit persistence."""
    return _record_account_guard_finalize_impl(
        account_id,
        exit_code=exit_code,
        stale_cleanup=stale_cleanup,
        account_guard_state_path_fn=_account_guard_state_path,
        locked_state_file_fn=locked_state_file,
        load_json_dict_unlocked_fn=_load_json_dict_unlocked,
        claude_account_guard_entry_fn=_claude_account_guard_entry,
        guard_utc_now_fn=_guard_utc_now,
        atomic_write_json_fn=atomic_write_json,
    )


_MODEL_CONTEXT_OVERRIDES_CACHE = {"path": None, "mtime": None, "data": {"models": {}, "provider_overrides": {}}}
_CLAUDE_NETWORK_GUARD_CACHE: dict = {}
_CLAUDE_NETWORK_GUARD_TTL_SEC = 20.0
_SESSION_GUARD_MARKER_NAME = ".mms-session-guard.json"
_SESSION_GUARD_LOCK_NAME = ".mms-session-guard.lock"


def _model_context_overrides_path():
    try:
        config_root = _resolve_mms_config_dir()
    except Exception:
        config_root = _real_user_path(".config", "mms")
    return os.path.join(config_root, "model-context-overrides.json")


def _inject_real_home_hints(env, *, include_xdg=False):
    from mms_launcher.export import inject_real_home_hints

    return inject_real_home_hints(
        env,
        include_xdg=include_xdg,
        real_user_home=_real_user_home,
        real_user_path=_real_user_path,
        inject_rescue_launch_env=_inject_rescue_launch_env,
    )


def _rescue_default_fallback_config(env=None):
    from mms_launcher.export import rescue_default_fallback_config

    environ = env if isinstance(env, dict) else os.environ
    return rescue_default_fallback_config(
        environ=environ,
        load_config=load_config,
        truthy=_truthy,
        mms_config_root_mode=mms_config_root_mode,
    )


def _rescue_bridge_kwargs():
    from mms_launcher.export import rescue_bridge_kwargs

    return rescue_bridge_kwargs(
        rescue_default_fallback_config=_rescue_default_fallback_config,
    )


def _merged_config_root_env(env):
    merged_env = dict(os.environ)
    if isinstance(env, dict):
        merged_env.update({str(key): str(value) for key, value in env.items() if value is not None})
        if "XDG_CONFIG_HOME" not in env and any(key in env for key in ("HOME", "MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME")):
            merged_env.pop("XDG_CONFIG_HOME", None)
    return merged_env


def _selected_mms_config_root(env):
    merged_env = _merged_config_root_env(env)
    try:
        return _resolve_mms_config_dir(merged_env)
    except Exception:
        return _real_user_path(".config", "mms")


def _config_root_is_explicit(env):
    merged_env = _merged_config_root_env(env)
    return bool(str(merged_env.get("MMS_CONFIG_ROOT") or merged_env.get("MMS_CONFIG_DIR") or "").strip())


def _selected_config_path(*parts):
    return os.path.join(_selected_mms_config_root({}), *parts)


def _inject_rescue_launch_env(env):
    from mms_launcher.export import inject_rescue_launch_env

    return inject_rescue_launch_env(
        env,
        safe_getcwd=_safe_getcwd,
        real_user_path=_real_user_path,
        rescue_default_fallback_config=_rescue_default_fallback_config,
        selected_mms_config_root=_selected_mms_config_root,
    )


def _host_context_real_home():
    from mms_launcher.export import host_context_real_home

    return host_context_real_home(
        real_user_path=_real_user_path,
        real_user_home=_real_user_home,
    )


def _host_tool_context(session_home, env=None):
    from mms_launcher.export import host_tool_context

    return host_tool_context(
        session_home,
        env,
        real_home_wrapper_search_path=_real_home_wrapper_search_path,
        resolve_tool_bins=resolve_tool_bins,
        wrapper_commands=_SESSION_REAL_HOME_WRAPPER_COMMANDS,
    )


def _inject_host_capability_hints(env):
    from mms_launcher.export import inject_host_capability_hints

    return inject_host_capability_hints(
        env,
        host_capability_env=host_capability_env,
        host_context_real_home=_host_context_real_home,
    )


def _install_host_context_env(env, *, cli, runtime=None, model_info=None, session_home=""):
    from mms_launcher.export import install_host_context_env

    return install_host_context_env(
        env,
        cli=cli,
        runtime=runtime,
        model_info=model_info,
        session_home=session_home,
        host_context_real_home=_host_context_real_home,
        selected_model_name=_selected_model_name,
        safe_getcwd=_safe_getcwd,
        host_tool_context=_host_tool_context,
        write_host_context=write_host_context,
    )


def _set_codex_soft_home(env, session_home):
    """Keep real HOME for tools; isolate Codex config/auth in CODEX_HOME."""
    from mms_launcher.export import set_codex_home_hint, set_codex_soft_home

    return set_codex_soft_home(
        env,
        session_home,
        real_user_path=_real_user_path,
        set_session_home_hint=_set_session_home_hint,
        set_codex_home_hint=set_codex_home_hint,
    )


def _set_opencode_soft_home(env, session_home):
    return _opencode_set_soft_home_impl(
        env,
        session_home,
        real_user_path=_real_user_path,
        set_session_home_hint=_set_session_home_hint,
    )


def _install_session_packet_env(
    env,
    *,
    cli,
    runtime,
    model_info=None,
    session_home="",
    features=None,
    extra_paths=None,
):
    from mms_launcher.export import install_session_packet_env

    return install_session_packet_env(
        env,
        cli=cli,
        runtime=runtime,
        model_info=model_info,
        session_home=session_home,
        features=features,
        extra_paths=extra_paths,
        write_session_packet=write_session_packet,
    )


_session_guard_marker_path = partial(_session_guard_marker_path_impl, marker_name=_SESSION_GUARD_MARKER_NAME)
_session_guard_lock_path = partial(_session_guard_lock_path_impl, lock_name=_SESSION_GUARD_LOCK_NAME)
_session_guard_process_identity = _session_guard_process_identity_impl


_session_guard_pid_alive = partial(
    _session_guard_pid_alive_impl,
    process_identity_fn=_session_guard_process_identity,
)
_read_session_guard_marker = partial(
    _read_session_guard_marker_impl,
    marker_path_fn=_session_guard_marker_path,
    load_json_dict_unlocked_fn=_load_json_dict_unlocked,
)


def _write_session_guard_marker(session_home, *, account_id="", runtime_kind="", child_pid=None):
    """Compatibility wrapper for session guard marker writes."""
    return _write_session_guard_marker_impl(
        session_home,
        account_id=account_id,
        runtime_kind=runtime_kind,
        child_pid=child_pid,
        marker_path_fn=_session_guard_marker_path,
        locked_state_file_fn=locked_state_file,
        load_json_dict_unlocked_fn=_load_json_dict_unlocked,
        atomic_write_json_fn=atomic_write_json,
        guard_utc_now_fn=_guard_utc_now,
        process_identity_fn=_session_guard_process_identity,
    )


def _record_session_child_pid(session_home, child_pid):
    _write_session_guard_marker(session_home, child_pid=child_pid)


def _session_home_is_active(session_home):
    """Compatibility wrapper for active session-home checks."""
    return _session_home_is_active_impl(
        session_home,
        read_marker_fn=_read_session_guard_marker,
        pid_alive_fn=_session_guard_pid_alive,
    )


_bounded_env_float = partial(_bounded_env_float_impl, environ=os.environ)


def _session_cleanup_launch_max_entries():
    return _bounded_env_int("MMS_SESSION_CLEANUP_MAX_ENTRIES", 3)


def _session_cleanup_launch_max_seconds():
    return _bounded_env_float("MMS_SESSION_CLEANUP_MAX_SECONDS", 2.0)


def _reserve_session_home(
    sessions_dir,
    *,
    account_id="",
    runtime_kind="",
    stale_callback=None,
    max_live_sessions=None,
    timings=None,
):
    """Compatibility wrapper for guarded session-home reservation."""
    return _reserve_session_home_impl(
        sessions_dir,
        account_id=account_id,
        runtime_kind=runtime_kind,
        stale_callback=stale_callback,
        max_live_sessions=max_live_sessions,
        timings=timings,
        timed_launch_step_fn=_timed_launch_step,
        locked_state_file_fn=locked_state_file,
        session_guard_lock_path_fn=_session_guard_lock_path,
        cleanup_stale_sessions_fn=_cleanup_stale_sessions,
        session_cleanup_launch_max_entries_fn=_session_cleanup_launch_max_entries,
        session_cleanup_launch_max_seconds_fn=_session_cleanup_launch_max_seconds,
        count_live_session_dirs_fn=_count_live_session_dirs,
        session_home_is_active_fn=_session_home_is_active,
        write_session_guard_marker_fn=_write_session_guard_marker,
    )


_real_home_wrapper_scrub_lines = _real_home_wrapper_scrub_lines_impl


_normalize_path = _normalize_path_impl


_path_is_within = _path_is_within_impl


def _path_under(path, root):
    try:
        path_real = os.path.realpath(os.path.abspath(path))
        root_real = os.path.realpath(os.path.abspath(root))
        return os.path.commonpath([path_real, root_real]) == root_real
    except Exception:
        return False


_runtime_net_mode = partial(_runtime_net_mode_impl, fake_upstream_enabled_fn=_fake_upstream_enabled)


_runtime_dns_mode = partial(
    _runtime_dns_mode_impl,
    fake_upstream_enabled_fn=_fake_upstream_enabled,
    proxy_dns_mode_fn=_proxy_dns_mode,
)


def _build_home_context(env, runtime, cli_name):
    """Compatibility wrapper for launch HOME context construction."""
    return _build_home_context_impl(
        env,
        runtime,
        cli_name,
        real_user_home_fn=_real_user_home,
        real_user_path_fn=_real_user_path,
        selected_mms_config_root_fn=_selected_mms_config_root,
        config_root_is_explicit_fn=_config_root_is_explicit,
        runtime_locale_env_fn=_runtime_locale_env,
        runtime_net_mode_fn=_runtime_net_mode,
        runtime_dns_mode_fn=_runtime_dns_mode,
    )


def _validate_home_context_or_exit(context):
    """Compatibility wrapper for launch HOME context validation."""
    return _validate_home_context_or_exit_impl(
        context,
        console=console,
        path_is_within_fn=_path_is_within,
        exit_fn=sys.exit,
    )


_home_context_lines = _home_context_lines_impl


def _prepare_oauth_home_context(runtime, env, cli_name):
    """Compatibility wrapper for OAuth HOME context preparation."""
    return _prepare_oauth_home_context_impl(
        runtime,
        env,
        cli_name,
        build_home_context_fn=_build_home_context,
        validate_home_context_fn=_validate_home_context_or_exit,
        home_context_lines_fn=_home_context_lines,
        console=console,
    )


_apply_proxy_env = _apply_proxy_env_impl


_split_no_proxy_values = _split_no_proxy_values_impl


_claude_no_proxy_conflicts = partial(
    _claude_no_proxy_conflicts_impl,
    no_proxy_tokens=_CLAUDE_NO_PROXY_TOKENS,
)


def _run_proxy_probe(proxy_url, target_url, *, no_proxy="", force_ipv4=True, resolve_ip=False):
    """Compatibility wrapper for proxy reachability probes."""
    return _run_proxy_probe_impl(
        proxy_url,
        target_url,
        no_proxy=no_proxy,
        force_ipv4=force_ipv4,
        resolve_ip=resolve_ip,
        fake_upstream_enabled_fn=_fake_upstream_enabled,
        fake_proxy_probe_fn=_fake_proxy_probe,
    )


_base_claude_network_guard = partial(
    _base_claude_network_guard_impl,
    runtime_force_ipv4_fn=_runtime_force_ipv4,
    fake_upstream_enabled_fn=_fake_upstream_enabled,
    proxy_fingerprint_fn=_proxy_fingerprint,
    proxy_dns_mode_fn=_proxy_dns_mode,
    claude_no_proxy_conflicts_fn=_claude_no_proxy_conflicts,
)
_claude_bypass_requires_proxy = partial(
    _claude_bypass_requires_proxy_impl,
    runtime_is_sensitive_claude_provider_fn=_runtime_is_sensitive_claude_provider,
)


_emit_dns_guard_hint = partial(
    _emit_dns_guard_hint_impl,
    runtime_dns_mode_fn=_runtime_dns_mode,
    console=console,
)


_claude_network_guard_cache_key = partial(
    _claude_network_guard_cache_key_impl,
    runtime_force_ipv4_fn=_runtime_force_ipv4,
    fake_upstream_enabled_fn=_fake_upstream_enabled,
)
get_claude_network_guard_preview = partial(
    _get_claude_network_guard_preview_impl,
    cache=_CLAUDE_NETWORK_GUARD_CACHE,
    ttl_sec=_CLAUDE_NETWORK_GUARD_TTL_SEC,
    perf_counter_fn=perf_counter,
    cache_key_fn=_claude_network_guard_cache_key,
    base_guard_fn=_base_claude_network_guard,
)


def build_claude_network_guard(runtime, *, require_proxy=False):
    """Compatibility wrapper for Claude network guard validation."""
    return _build_claude_network_guard_impl(
        runtime,
        require_proxy=require_proxy,
        cache=_CLAUDE_NETWORK_GUARD_CACHE,
        ttl_sec=_CLAUDE_NETWORK_GUARD_TTL_SEC,
        perf_counter_fn=perf_counter,
        cache_key_fn=_claude_network_guard_cache_key,
        base_guard_fn=_base_claude_network_guard,
        runtime_force_ipv4_fn=_runtime_force_ipv4,
        fake_upstream_enabled_fn=_fake_upstream_enabled,
        run_proxy_probe_fn=_run_proxy_probe,
        guard_targets=_CLAUDE_PROXY_GUARD_TARGETS,
    )


def _enforce_claude_network_guard_or_exit(runtime, *, require_proxy=False):
    """Compatibility wrapper for enforced Claude network guard checks."""
    return _enforce_claude_network_guard_or_exit_impl(
        runtime,
        require_proxy=require_proxy,
        build_network_guard_fn=build_claude_network_guard,
        console=console,
        exit_fn=sys.exit,
    )


def _validate_timezone_or_exit(timezone_name, *, label="account"):
    """Compatibility wrapper for startup timezone validation."""
    return _validate_timezone_or_exit_impl(
        timezone_name,
        label=label,
        console=console,
        exit_fn=sys.exit,
    )


def _check_proxy_connectivity_or_exit(proxy_url, no_proxy="", *, label="account", force_ipv4=True):
    """Compatibility wrapper for startup proxy connectivity checks."""
    return _check_proxy_connectivity_or_exit_impl(
        proxy_url,
        no_proxy,
        label=label,
        force_ipv4=force_ipv4,
        fake_upstream_enabled_fn=_fake_upstream_enabled,
        fake_proxy_probe_fn=_fake_proxy_probe,
        console=console,
        exit_fn=sys.exit,
    )


def _apply_runtime_network_profile(env, runtime, *, validate_proxy=True):
    """Compatibility wrapper for runtime network env projection."""
    return _apply_runtime_network_profile_impl(
        env,
        runtime,
        validate_proxy=validate_proxy,
        validate_timezone_or_exit_fn=_validate_timezone_or_exit,
        apply_runtime_locale_profile_fn=_apply_runtime_locale_profile,
        apply_runtime_ip_stack_profile_fn=_apply_runtime_ip_stack_profile,
        check_proxy_connectivity_or_exit_fn=_check_proxy_connectivity_or_exit,
        fake_upstream_enabled_fn=_fake_upstream_enabled,
        fake_upstream_status_payload_fn=_fake_upstream_status_payload,
        proxy_fingerprint_fn=_proxy_fingerprint,
        runtime_force_ipv4_fn=_runtime_force_ipv4,
        default_account_timezone=DEFAULT_ACCOUNT_TIMEZONE,
    )


def _apply_runtime_ip_stack_profile(env, runtime):
    """Compatibility wrapper for runtime IP stack env projection."""
    return _apply_runtime_ip_stack_profile_impl(
        env,
        runtime,
        runtime_force_ipv4_fn=_runtime_force_ipv4,
    )


RUNTIME_DIR = _selected_config_path("runtime")
HEALTH_CHECK_PATH = _selected_config_path("health_check.json")
ANTHROPIC_URL_CACHE_PATH = _selected_config_path("cache", "anthropic_base_urls.json")

# Anthropic URL 探测结果缓存（内存，TTL 1h）
# key: provider_id → {"url": str, "ts": datetime}
_ANTHROPIC_URL_CACHE: dict = {}
CLI_PROTOCOL_REQUIREMENTS = {
    "claude": "anthropic_messages",
    "codex": "openai_chat_completions",
    "opencode": "openai_chat_completions",
}
OAUTH_CAPABLE_CLIS = {"claude", "codex", "gemini", "agy"}
# OpenCode constants and pure config helpers live in mms_opencode.config.
_LOCAL_STATUSLINE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "statusline-command.sh")
def _resolve_local_hooks_dir(module_file=None):
    """Compatibility wrapper for local hook directory resolution."""
    return _resolve_local_hooks_dir_impl(module_file or __file__)


_LOCAL_HOOKS_DIR = _resolve_local_hooks_dir()
_CLAUDE_FEISHU_WEBFETCH_GUARD_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "claude-feishu-webfetch-guard.sh")
_CLAUDE_HIVE_COMPACT_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "hive-compact-hook.sh")
_CLAUDE_BRAINKEEPER_SESSION_START_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "brainkeeper-session-start-hook.sh")
_CLAUDE_BRAINKEEPER_SESSION_END_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "brainkeeper-session-end-hook.sh")
_CLAUDE_BRAINKEEPER_TOKEN_MONITOR_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "brainkeeper-token-monitor-hook.sh")
_CLAUDE_MINDKEEPER_SESSION_START_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "mindkeeper-session-start-hook.sh")
_CLAUDE_MINDKEEPER_SESSION_END_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "mindkeeper-session-end-hook.sh")
_CLAUDE_MINDKEEPER_TOKEN_MONITOR_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "mindkeeper-token-monitor-hook.sh")
_CLAUDE_CODEGRAPH_AUTO_INDEX_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "claude-codegraph-auto-index.sh")
_CLAUDE_MMS_RESUME_HINT_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "mms-resume-hint.sh")
_XMEM_SESSION_START_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "xmem-session-start-hook.sh")
_XMEM_SESSION_END_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "xmem-session-end-hook.sh")
_XMEM_GATEWAY_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "xmem-gateway-hook.sh")
_NSR_CLAUDE_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "nsr-claude-hook.sh")
_NSR_CODEX_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "nsr-codex-hook.sh")
_NSR_BUILTIN_HOOK = os.path.join(_LOCAL_HOOKS_DIR, "nsr-builtin-hook.py")

_CLAUDE_STATUSLINE_CONFIG = {
    "command": f"/bin/bash {_LOCAL_STATUSLINE_SCRIPT}",
    "type": "command",
}

_CLAUDE_SESSION_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "TZ",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LC_MESSAGES",
    "SSL_CERT_FILE",
    "NODE_EXTRA_CA_CERTS",
    "REQUESTS_CA_BUNDLE",
    "MMS_FORCE_IPV4",
    "MMS_FAKE_UPSTREAM_MODE",
    "MMS_FAKE_UPSTREAM_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY",
)

_CLAUDE_SETTINGS_INHERIT_KEYS = (
    "hooks",
    "statusLine",
    "permissions",
)
_CLAUDE_SESSION_MCP_SERVER_ALLOWLIST = (
    "brainkeeper",
    "codegraph",
)
_CLAUDE_SETTINGS_INHERIT_SCALAR_KEYS = ("theme",)
_CLAUDE_SESSION_SOURCE_ENTRY_ALLOWLIST = (
    ".mcp.json",
    "CLAUDE.md",
    "RTK.md",
    "commands",
    "hooks",
    "skills",
)
_CLAUDE_FAIL_CLOSED_SOURCE_ENTRY_ALLOWLIST = (
    "CLAUDE.md",
    "RTK.md",
)
_CLAUDE_OAUTH_SESSION_SOURCE_ENTRY_ALLOWLIST = _CLAUDE_FAIL_CLOSED_SOURCE_ENTRY_ALLOWLIST
_CLAUDE_SESSION_LIBRARY_ENTRY_ALLOWLIST = ("Keychains",)
_CLAUDE_OAUTH_MANUAL_ONLY_EXIT_CODE = 86
_SESSION_REAL_HOME_WRAPPER_COMMANDS = (
    "open",
    "osascript",
    "security",
    "git",
    "ssh",
    "ssh-add",
    "scp",
    "sftp",
    "brew",
    "gh",
    "lark-cli",
    "rh",
    "hive",
    "pm2",
    "npm",
    "pnpm",
    "npx",
    "yarn",
    "corepack",
    "node",
    "uv",
    "docker",
    "docker-compose",
)
_CLAUDE_OAUTH_STATE_TOP_LEVEL_ALLOWLIST = (
    "userID",
    "firstStartTime",
    "numStartups",
    "bypassPermissionsModeAccepted",
    "alwaysThinkingEnabled",
    "hasCompletedOnboarding",
    "lastOnboardingVersion",
    "lastReleaseNotesSeen",
    "installMethod",
    "deepLinkTerminal",
    "effortCalloutDismissed",
    "effortCalloutV2Dismissed",
    "migrationVersion",
    "officialMarketplaceAutoInstallAttempted",
    "officialMarketplaceAutoInstalled",
    "opus1mMergeNoticeSeenCount",
    "opusProMigrationComplete",
    "sonnet1m45MigrationComplete",
    "voiceNoticeSeenCount",
)
_CLAUDE_OAUTH_UI_STATE_SEED_KEYS = (
    "firstStartTime",
    "numStartups",
    "hasCompletedOnboarding",
    "lastOnboardingVersion",
    "lastReleaseNotesSeen",
    "installMethod",
    "deepLinkTerminal",
    "effortCalloutDismissed",
    "effortCalloutV2Dismissed",
    "migrationVersion",
    "officialMarketplaceAutoInstallAttempted",
    "officialMarketplaceAutoInstalled",
    "opus1mMergeNoticeSeenCount",
    "opusProMigrationComplete",
    "sonnet1m45MigrationComplete",
    "voiceNoticeSeenCount",
)
_CLAUDE_OAUTH_STATE_SCALAR_DICT_ALLOWLIST = ("tipsHistory",)
_CLAUDE_OAUTH_ACCOUNT_ALLOWLIST = (
    "accountCreatedAt",
    "accountUuid",
    "billingType",
    "displayName",
    "emailAddress",
    "hasExtraUsageEnabled",
    "organizationName",
    "organizationRole",
    "organizationUuid",
    "subscriptionCreatedAt",
    "workspaceRole",
)
_CLAUDE_AI_OAUTH_ALLOWLIST = (
    "accessToken",
    "refreshToken",
    "expiresAt",
    "expiresIn",
    "tokenType",
    "token_type",
    "emailAddress",
    "accountUuid",
    "organizationUuid",
)
_CLAUDE_CODEX_STATE_TOP_LEVEL_ALLOWLIST = (
    "firstStartTime",
    "numStartups",
    "bypassPermissionsModeAccepted",
    "alwaysThinkingEnabled",
    "hasCompletedOnboarding",
    "lastOnboardingVersion",
    "installMethod",
)
_CLAUDE_OAUTH_ENV_PREFIX_BLOCKLIST = (
    "ANTHROPIC_",
    "CLAUDE_CODE_",
)
_OPENAI_ENV_PREFIX_BLOCKLIST = (
    "OPENAI_",
)
_RUNTIME_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)
_RUNTIME_FAKE_ENV_KEYS = (
    "MMS_FAKE_UPSTREAM_MODE",
    "MMS_FAKE_UPSTREAM_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_PROXY",
    "MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY",
)
_RUNTIME_CA_ENV_KEYS = (
    "NODE_EXTRA_CA_CERTS",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
)

_CLAUDE_MAILBOX_PREFIX = os.path.join(_real_user_path(".claude"), "mailbox")

_CLAUDE_DEFAULT_PERMISSION_ALLOW = [
    "Read",
    "Edit",
    "Write",
    "Bash(yarn *)",
    "Bash(npm *)",
    "Bash(node *)",
    "Bash(git *)",
    "Bash(ls *)",
    "Bash(cat *)",
    "Bash(head *)",
    "Bash(tail *)",
    "Bash(find *)",
    "Bash(grep *)",
    "Bash(which *)",
    "Bash(chmod *)",
    "Bash(cd *)",
    "Bash(python3 *)",
    "Bash(rsync *)",
    "Bash(coscli *)",
    f"Bash(mkdir -p {_CLAUDE_MAILBOX_PREFIX}*)",
    f"Bash(rm -rf {_CLAUDE_MAILBOX_PREFIX}/*)",
    f"Bash(ls {_CLAUDE_MAILBOX_PREFIX}*)",
    "Skill(*)",
    "Agent(*)",
]

_CLAUDE_DEFAULT_PERMISSION_DENY = [
    "Bash(rm -rf /)*",
    "Bash(git push --force *)",
]


def _claude_gateway_home():
    gateway_base = _real_user_path(".config", "mms", "claude-gateway")
    sessions_dir = os.path.join(gateway_base, "s")
    return os.path.join(sessions_dir, str(os.getpid()))


def _claude_route_status_paths():
    if str(os.environ.get("MMS_CONFIG_ROOT") or os.environ.get("MMS_CONFIG_DIR") or "").strip():
        return [os.path.join(_resolve_mms_config_dir(), "route_status.json")]
    gateway_home = _claude_gateway_home()
    return [os.path.join(gateway_home, ".config", "mms", "route_status.json")]


def _anthropic_cache_key(provider_id, configured_url):
    return f"{provider_id}::{configured_url.rstrip('/')}"


def _load_anthropic_url_file_cache():
    try:
        with open(ANTHROPIC_URL_CACHE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_anthropic_url_file_cache(cache_data):
    try:
        os.makedirs(os.path.dirname(ANTHROPIC_URL_CACHE_PATH), exist_ok=True)
        tmp_path = ANTHROPIC_URL_CACHE_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(cache_data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_path, ANTHROPIC_URL_CACHE_PATH)
    except Exception:
        pass


def _remember_anthropic_url(provider_id, configured_url, resolved_url):
    now_iso = datetime.now().isoformat()
    cache_key = _anthropic_cache_key(provider_id, configured_url)
    _ANTHROPIC_URL_CACHE[cache_key] = {"url": resolved_url, "ts": datetime.now()}
    cache_data = _load_anthropic_url_file_cache()
    cache_data[cache_key] = {"url": resolved_url, "ts": now_iso}
    _save_anthropic_url_file_cache(cache_data)


from mms_claude import settings as _claude_settings
from mms_claude import state as _claude_state

# Claude settings implementation lives in mms_claude.settings; keep the former
# launcher-private names as aliases for existing monkeypatch-based tests/callers.
_load_real_claude_settings = _claude_settings.load_real_claude_settings
_load_claude_settings_from_dir = _claude_settings.load_claude_settings_from_dir
_load_claude_settings_template = _claude_settings.load_claude_settings_template
_load_mms_claude_settings_template = _claude_settings.load_mms_claude_settings_template
_load_global_claude_settings_template = _claude_settings.load_global_claude_settings_template
_global_claude_snapshot_path = _claude_settings.global_claude_snapshot_path
_normalize_hook_command = _claude_settings.normalize_hook_command
_extract_managed_claude_snapshot = _claude_settings.extract_managed_claude_snapshot
_snapshot_to_template = _claude_settings.snapshot_to_template
_merge_snapshot_with_current = _claude_settings.merge_snapshot_with_current
_prune_session_only_snapshot_entries = _claude_settings.prune_session_only_snapshot_entries
_sanitize_global_snapshot = _claude_settings.sanitize_global_snapshot
_managed_snapshot_differs = _claude_settings.managed_snapshot_differs
_managed_snapshot_template = _claude_settings.managed_snapshot_template
_load_global_claude_snapshot = _claude_settings.load_global_claude_snapshot
_write_global_claude_snapshot = _claude_settings.write_global_claude_snapshot
_merge_claude_settings = _claude_settings.merge_claude_settings

def _repair_real_claude_settings():
    import json as _json

    real_claude_dir = _real_user_path(".claude")
    os.makedirs(real_claude_dir, exist_ok=True)
    settings_path = os.path.join(real_claude_dir, "settings.json")
    current_settings = _load_real_claude_settings()
    seed_template = _load_global_claude_settings_template()
    previous_snapshot = _load_global_claude_snapshot()
    snapshot_data, managed_template = _managed_snapshot_template(
        previous_snapshot,
        seed_template,
        current_settings,
    )

    repaired = _merge_claude_settings(current_settings, managed_template)
    repaired = _sanitize_global_snapshot(repaired)
    repaired_snapshot = _sanitize_global_snapshot(
        _extract_managed_claude_snapshot(repaired, managed_template)
    )
    should_write = (
        _managed_snapshot_differs(previous_snapshot, current_settings, managed_template)
        or repaired_snapshot != snapshot_data
        or not os.path.exists(settings_path)
    )
    if should_write:
        with locked_state_file(settings_path):
            atomic_write_json(settings_path, repaired, mode=0o600)
    _write_global_claude_snapshot(repaired_snapshot)
    return repaired


def repair_real_claude_settings_for_startup():
    return _repair_real_claude_settings()


repair_current_session_claude_settings = _claude_settings.repair_current_session_claude_settings
_strip_agent_im_hooks = _claude_settings.strip_agent_im_hooks
_merge_claude_hook_groups = _claude_settings.merge_claude_hook_groups
_merge_claude_hooks = _claude_settings.merge_claude_hooks
_merge_claude_statusline = _claude_settings.merge_claude_statusline
_merge_claude_permissions = _claude_settings.merge_claude_permissions
_hook_command_exists = _claude_settings.hook_command_exists
_append_command_hook = _claude_settings.append_command_hook
_append_shell_command_hook = _claude_settings.append_shell_command_hook
_merge_mms_session_hooks = _claude_settings.merge_mms_session_hooks
_filter_claude_session_hooks = _claude_settings.filter_claude_session_hooks

def _caveman_available_for_cli(cli_name):
    return str(cli_name or "").strip() in {"claude", "codex", "opencode", "agy"} and bool(_resolve_caveman_root())


def _session_feature_root_kwargs():
    return {
        "module_file": __file__,
        "real_user_path_fn": _real_user_path,
        "asset_root_preference_fn": _asset_root_preference,
        "environ": os.environ,
    }


def _make_session_feature_root_resolver(resolve_fn, name):
    def _resolver():
        return resolve_fn(**_session_feature_root_kwargs())

    _resolver.__name__ = name
    return _resolver


_resolve_nsr_root = _make_session_feature_root_resolver(_resolve_nsr_root_impl, "_resolve_nsr_root")


def _nsr_available_for_cli(cli_name):
    cli_name = str(cli_name or "").strip()
    if cli_name not in {"claude", "codex"}:
        return False
    wrapper = _NSR_CLAUDE_HOOK if cli_name == "claude" else _NSR_CODEX_HOOK
    return os.path.isfile(wrapper) and bool(_resolve_nsr_root() or os.path.isfile(_NSR_BUILTIN_HOOK))


_normalize_nsr_mode = _normalize_nsr_mode_impl
_runtime_nsr_enabled = _runtime_nsr_enabled_impl


_normalize_caveman_mode = _normalize_caveman_mode_impl
_runtime_caveman_enabled = _runtime_caveman_enabled_impl


_normalize_caveman_level = _normalize_caveman_level_impl
_runtime_caveman_level = _runtime_caveman_level_impl


def _caveman_hook_mode(caveman_level):
    return {
        "light": "lite",
        "standard": "full",
        "full": "ultra",
    }.get(_normalize_caveman_level(caveman_level), "lite")


def _caveman_hook_env_prefix(caveman_level):
    return f"CAVEMAN_DEFAULT_MODE={shlex.quote(_caveman_hook_mode(caveman_level))} "


_normalize_thinking_mode = _normalize_thinking_mode_impl
_runtime_thinking_enabled = _runtime_thinking_enabled_impl


_normalize_reasoning_effort = _normalize_reasoning_effort_impl
_runtime_reasoning_effort = _runtime_reasoning_effort_impl


_runtime_vision_sidecar = _runtime_vision_sidecar_impl


def _resolve_native_fallback_routes(runtime, model_name):
    try:
        from mms_runtime.native_fallback import resolve_native_fallback_routes

        return resolve_native_fallback_routes(runtime, model_name)
    except Exception:
        return []


def _resolve_codex_responses_fallback_routes(runtime, model_name):
    try:
        from mms_runtime.native_fallback import resolve_codex_responses_fallback_routes

        return resolve_codex_responses_fallback_routes(runtime, model_name)
    except Exception:
        return []


def _is_installed_mms_layout(module_path=None):
    """Compatibility wrapper for installed MMS layout detection."""
    return _is_installed_mms_layout_impl(
        module_path=os.path.abspath(module_path or __file__),
        real_user_path_fn=_real_user_path,
    )


def _default_gpt_reasoning_effort(module_path=None):
    """Compatibility wrapper for default GPT reasoning effort policy."""
    return _default_gpt_reasoning_effort_impl(
        module_path=os.path.abspath(module_path or __file__),
        is_installed_mms_layout_fn=_is_installed_mms_layout,
    )


def _asset_root_preference(asset_name):
    return _asset_root_preference_impl(asset_name, preference_asset_root_fn=preference_asset_root)


_resolve_caveman_root = _make_session_feature_root_resolver(_resolve_caveman_root_impl, "_resolve_caveman_root")


def _ecc_available_for_claude():
    return bool(_resolve_ecc_root())


def _omc_available_for_claude():
    return bool(_resolve_omc_root())


_normalize_ecc_mode = _normalize_ecc_mode_impl


_normalize_agent_pack = _normalize_agent_pack_impl
_runtime_agent_pack = _runtime_agent_pack_impl
_runtime_ecc_enabled = _runtime_ecc_enabled_impl
_runtime_omc_enabled = _runtime_omc_enabled_impl


_resolve_ecc_root = _make_session_feature_root_resolver(_resolve_ecc_root_impl, "_resolve_ecc_root")
_resolve_omc_root = _make_session_feature_root_resolver(_resolve_omc_root_impl, "_resolve_omc_root")
_resolve_web_access_root = _make_session_feature_root_resolver(_resolve_web_access_root_impl, "_resolve_web_access_root")
_resolve_weber_root = _make_session_feature_root_resolver(_resolve_weber_root_impl, "_resolve_weber_root")
_resolve_agent_browser_root = _make_session_feature_root_resolver(_resolve_agent_browser_root_impl, "_resolve_agent_browser_root")
_resolve_codegraph_root = _make_session_feature_root_resolver(_resolve_codegraph_root_impl, "_resolve_codegraph_root")
_resolve_toon_root = _make_session_feature_root_resolver(_resolve_toon_root_impl, "_resolve_toon_root")
_resolve_token_saver_root = _make_session_feature_root_resolver(_resolve_token_saver_root_impl, "_resolve_token_saver_root")
_resolve_xmem_root = _make_session_feature_root_resolver(_resolve_xmem_root_impl, "_resolve_xmem_root")


_xmem_cli_path = partial(
    _xmem_cli_path_impl,
    environ=os.environ,
    real_user_path=_real_user_path,
    which=shutil.which,
)


_resolve_auto_github_contributor_root = _make_session_feature_root_resolver(
    _resolve_auto_github_contributor_root_impl,
    "_resolve_auto_github_contributor_root",
)


_mms_toon_script_path = partial(_launcher_script_path, __file__, "mms-toon")
_mms_context_script_path = partial(_launcher_script_path, __file__, "mms-context")
_mms_gain_script_path = partial(_launcher_script_path, __file__, "mms-gain")
_token_saver_script_path = partial(_launcher_script_path, __file__, "token-saver")
_token_gain_script_path = partial(_launcher_script_path, __file__, "token-gain")


_is_caveman_hook_command = _session_hook_commands.is_caveman_hook_command
_is_codex_rtk_hook_command = _session_hook_commands.is_codex_rtk_hook_command
_is_ecc_hook_command = _session_hook_commands.is_ecc_hook_command
_is_omc_hook_command = _session_hook_commands.is_omc_hook_command
_is_mms_managed_hook_command = _session_hook_commands.is_mms_managed_hook_command
_is_legacy_loop_hook_command = _session_hook_commands.is_legacy_loop_hook_command
_is_nsr_hook_command = _session_hook_commands.is_nsr_hook_command
_is_loop_family_hook_command = _session_hook_commands.is_loop_family_hook_command
_hook_command_targets_exist = _session_hook_commands.hook_command_targets_exist


_filter_missing_managed_hook_commands = _claude_settings.filter_missing_managed_hook_commands
_filter_hook_commands = _claude_settings.filter_hook_commands
_normalize_session_surface_disabled = _claude_settings.normalize_session_surface_disabled
_session_surface_disabled = _claude_settings.session_surface_disabled
_filter_mcp_servers_by_disabled = _claude_settings.filter_mcp_servers_by_disabled


_mcp_command_has_path = _session_hook_commands.mcp_command_has_path


def _normalize_session_mcp_server_spec(name, spec, *, env=None):
    """Make inherited MCP commands session-safe; drop missing local CLIs."""
    from mms_claude.settings import normalize_session_mcp_server_spec

    return normalize_session_mcp_server_spec(name, spec, env=env)


def _mcp_server_spec_has_entrypoint(spec):
    if not isinstance(spec, dict):
        return False
    url = spec.get("url")
    if isinstance(url, str) and url.strip():
        return True
    command = str(spec.get("command") or "").strip()
    return bool(command)


_normalize_session_mcp_servers = _claude_settings.normalize_session_mcp_servers
_filter_hooks_by_disabled = _claude_settings.filter_hooks_by_disabled
_session_skill_disabled = _claude_settings.session_skill_disabled


def _caveman_claude_activate_command(caveman_root, caveman_level="light"):
    script_path = os.path.join(caveman_root, "hooks", "caveman-activate.js")
    return (
        _caveman_hook_env_prefix(caveman_level) +
        "CAVEMAN_HOOK_COMPACT=1 "
        "CAVEMAN_HOOK_EVENT=SessionStart "
        f"node {json.dumps(script_path)}"
    )


def _caveman_claude_tracker_command(caveman_root):
    script_path = os.path.join(caveman_root, "hooks", "caveman-mode-tracker.js")
    return f"node {json.dumps(script_path)}"


_caveman_codex_activate_command = _codex_hooks.caveman_codex_activate_command
_caveman_codex_hook_payload = _codex_hooks.caveman_codex_hook_payload
_codex_shell_hook_payload = _codex_hooks.codex_shell_hook_payload
_codex_caveman_session_hook = _codex_hooks.codex_caveman_session_hook
_configure_codex_caveman_hooks = _codex_hooks.configure_codex_caveman_hooks


_configure_claude_nsr_hooks = _claude_settings.configure_claude_nsr_hooks


_configure_codex_nsr_hooks = _codex_hooks.configure_codex_nsr_hooks


_configure_claude_caveman_hooks = _claude_settings.configure_claude_caveman_hooks


def _load_claude_agent_pack_hooks_from(resolver_name):
    from mms_claude.settings import load_claude_agent_pack_hooks

    return load_claude_agent_pack_hooks(globals()[resolver_name]())


_load_ecc_claude_hooks = partial(_load_claude_agent_pack_hooks_from, "_resolve_ecc_root")
_load_omc_claude_hooks = partial(_load_claude_agent_pack_hooks_from, "_resolve_omc_root")


_configure_claude_ecc_hooks = _claude_settings.configure_claude_ecc_hooks
_configure_claude_omc_hooks = _claude_settings.configure_claude_omc_hooks


_build_codex_session_hooks = _codex_hooks.build_codex_session_hooks


_codex_hook_event_state_key = _codex_hook_trust._codex_hook_event_state_key
_codex_hook_fingerprint = _codex_hook_trust._codex_hook_fingerprint
_codex_hook_index = _codex_hook_trust._codex_hook_index
_decode_toml_basic_key = _codex_hook_trust._decode_toml_basic_key
_codex_hook_trust_records_from_config = _codex_hook_trust._codex_hook_trust_records_from_config
_normalize_codex_hook_trust_toml_layout = _codex_hook_trust._normalize_codex_hook_trust_toml_layout
_replace_codex_hook_trust_hashes = _codex_hook_trust._replace_codex_hook_trust_hashes
_append_codex_exact_hook_trust_hashes = _codex_hook_trust._append_codex_exact_hook_trust_hashes
_codex_hook_trust_refresh_enabled = _codex_hook_trust._codex_hook_trust_refresh_enabled
_codex_app_server_hooks_list = _codex_hook_trust._codex_app_server_hooks_list
_refresh_codex_current_hook_trust_cache = _codex_hook_trust._refresh_codex_current_hook_trust_cache
_collect_codex_hook_trust_seed_sources = _codex_hook_trust._collect_codex_hook_trust_seed_sources
_append_codex_session_hook_trust_states = _codex_hook_trust._append_codex_session_hook_trust_states


_overlay_session_entry_dir = _session_overlays._overlay_session_entry_dir
_overlay_session_skill_dir = _session_overlays._overlay_session_skill_dir
_overlay_caveman_session_entries = _session_overlays._overlay_caveman_session_entries
_overlay_ecc_session_entries = _session_overlays._overlay_ecc_session_entries
_overlay_omc_session_entries = _session_overlays._overlay_omc_session_entries
_overlay_web_access_session_entries = _session_overlays._overlay_web_access_session_entries
_overlay_weber_session_entries = _session_overlays._overlay_weber_session_entries
_overlay_agent_browser_session_entries = _session_overlays._overlay_agent_browser_session_entries
_overlay_codegraph_session_entries = _session_overlays._overlay_codegraph_session_entries
_overlay_toon_session_entries = _session_overlays._overlay_toon_session_entries
_overlay_xmem_session_entries = _session_overlays._overlay_xmem_session_entries
_overlay_token_saver_session_entries = _session_overlays._overlay_token_saver_session_entries
_overlay_auto_github_contributor_session_entries = _session_overlays._overlay_auto_github_contributor_session_entries


def _overlay_agy_session_assets(
    account_home,
    session_home,
    *,
    enable_caveman=False,
    caveman_level="light",
    disabled_session_surfaces=None,
):
    """Compatibility wrapper for AGY session plugin overlays."""
    from mms_agy.assets import overlay_agy_session_assets

    return overlay_agy_session_assets(
        account_home,
        session_home,
        enable_caveman=enable_caveman,
        caveman_level=caveman_level,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def _overlay_opencode_session_assets(config_dir, session_home, *, enable_caveman=False, disabled_session_surfaces=None, runtime=None):
    return _overlay_opencode_session_assets_impl(
        config_dir,
        session_home,
        enable_caveman=enable_caveman,
        disabled_session_surfaces=disabled_session_surfaces,
        runtime=runtime,
        overlay_opencode_rtk_plugin=_overlay_opencode_rtk_plugin,
        overlay_caveman_session_entries=_overlay_caveman_session_entries,
        overlay_web_access_session_entries=_overlay_web_access_session_entries,
        overlay_weber_session_entries=_overlay_weber_session_entries,
        overlay_codegraph_session_entries=_overlay_codegraph_session_entries,
        overlay_toon_session_entries=_overlay_toon_session_entries,
        overlay_token_saver_session_entries=_overlay_token_saver_session_entries,
        overlay_xmem_session_entries=_overlay_xmem_session_entries,
        overlay_opencode_xmem_plugin=_overlay_opencode_xmem_plugin,
    )


_configure_ecc_session_env = _session_env.configure_ecc_session_env
_configure_agent_pack_session_env = _session_env.configure_agent_pack_session_env
_session_required_env_from_runtime_env = _session_env.session_required_env_from_runtime_env


_sanitize_claude_inherited_settings_payload = _claude_settings.sanitize_claude_inherited_settings_payload
_sanitize_account_claude_settings_payload = _claude_settings.sanitize_account_claude_settings_payload
_default_session_mcp_servers = _claude_settings.default_session_mcp_servers


def _installed_claude_plugin_paths():
    plugins_root = _real_user_path(".claude", "plugins")
    installed_path = os.path.join(plugins_root, "installed_plugins.json")
    loaded = _load_json_dict_unlocked(installed_path)
    plugins = loaded.get("plugins") if isinstance(loaded, dict) else {}
    if not isinstance(plugins, dict):
        return []

    resolved_paths = []
    seen = set()
    for records in plugins.values():
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            install_path = os.path.abspath(
                os.path.expanduser(str(record.get("installPath") or "").strip())
            )
            if not install_path or install_path in seen:
                continue
            if not os.path.isdir(install_path):
                continue
            if not _path_under(install_path, plugins_root):
                continue
            seen.add(install_path)
            resolved_paths.append(install_path)
    return resolved_paths


def _installed_claude_plugin_mcp_manifest_paths(install_path):
    install_root = os.path.abspath(os.path.expanduser(str(install_path or "").strip()))
    if not install_root:
        return []

    candidates = []
    metadata_paths = (
        os.path.join(install_root, ".cursor-plugin", "plugin.json"),
        os.path.join(install_root, ".claude-plugin", "plugin.json"),
    )
    for metadata_path in metadata_paths:
        metadata = _load_json_dict_unlocked(metadata_path)
        manifest_rel = metadata.get("mcpServers")
        if not isinstance(manifest_rel, str) or not manifest_rel.strip():
            continue
        manifest_path = os.path.abspath(os.path.join(install_root, manifest_rel.strip()))
        if _path_under(manifest_path, install_root):
            candidates.append(manifest_path)

    candidates.append(os.path.join(install_root, ".mcp.json"))

    manifests = []
    seen = set()
    for candidate in candidates:
        normalized = os.path.abspath(os.path.expanduser(str(candidate or "").strip()))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if os.path.isfile(normalized):
            manifests.append(normalized)
    return manifests


def _installed_claude_plugin_mcp_servers():
    servers = {}
    for install_path in _installed_claude_plugin_paths():
        for manifest_path in _installed_claude_plugin_mcp_manifest_paths(install_path):
            payload = _load_json_dict_unlocked(manifest_path)
            plugin_servers = payload.get("mcpServers") if isinstance(payload, dict) else {}
            if not isinstance(plugin_servers, dict):
                continue
            for name, spec in plugin_servers.items():
                key = str(name or "").strip()
                if not key or key in servers or not _mcp_server_spec_has_entrypoint(spec):
                    continue
                servers[key] = copy.deepcopy(spec)
    return servers


def _enabled_real_codex_plugin_names():
    import re

    config_path = _real_user_path(".codex", "config.toml")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return set()

    header_pattern = re.compile(
        r'^\[plugins\."((?:\\.|[^"\\])*)"\]\s*$',
        flags=re.MULTILINE,
    )
    matches = list(header_pattern.finditer(text))
    enabled = set()
    for index, match in enumerate(matches):
        plugin_id = _decode_toml_basic_key(match.group(1))
        block_start = match.end()
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[block_start:block_end]
        enabled_match = re.search(
            r'^\s*enabled\s*=\s*(true|false)\s*$',
            block,
            flags=re.MULTILINE | re.IGNORECASE,
        )
        if not enabled_match or enabled_match.group(1).lower() != "true":
            continue
        plugin_name = str(plugin_id or "").split("@", 1)[0].strip().lower()
        if plugin_name:
            enabled.add(plugin_name)
    return enabled


_resolve_hive_root = _session_mcp.resolve_hive_root
_default_hive_session_mcp_server = _session_mcp.default_hive_session_mcp_server
_resolve_pilot_root = _session_mcp.resolve_pilot_root
_default_pilot_session_mcp_server = _session_mcp.default_pilot_session_mcp_server
_replace_plugin_root_tokens = _session_mcp.replace_plugin_root_tokens
_load_plugin_mcp_servers = _session_mcp.load_plugin_mcp_servers


_agent_pack_mcp_servers = _claude_settings.agent_pack_mcp_servers
_merge_agent_pack_mcp_servers = _claude_settings.merge_agent_pack_mcp_servers
_ensure_session_only_claude_mcp_servers = _claude_settings.ensure_session_only_claude_mcp_servers
_session_managed_mcp_server_allowlist = _claude_settings.session_managed_mcp_server_allowlist
_session_managed_mcp_servers = _claude_settings.session_managed_mcp_servers
_inject_managed_mcp_servers_into_claude_state = _claude_settings.inject_managed_mcp_servers_into_claude_state


_copy_allowed_scalar_fields = _claude_state.copy_allowed_scalar_fields
_copy_allowed_scalar_dict_fields = _claude_state.copy_allowed_scalar_dict_fields
_sanitize_claude_ui_state_seed_payload = _claude_state.sanitize_claude_ui_state_seed_payload
_merge_scalar_dict_entries = _claude_state.merge_scalar_dict_entries
_merge_claude_ui_state_seed = _claude_state.merge_claude_ui_state_seed
_merge_claude_gateway_ui_state_payload = _claude_state.merge_claude_gateway_ui_state_payload
_strip_claude_state_execution_surfaces = _claude_state.strip_claude_state_execution_surfaces
_sanitize_claude_project_state_entry = _claude_state.sanitize_claude_project_state_entry
_sanitize_claude_project_state_map = _claude_state.sanitize_claude_project_state_map
_load_real_claude_ui_state_seed = _claude_state.load_real_claude_ui_state_seed
_load_real_claude_project_state = _claude_state.load_real_claude_project_state
_sanitize_oauth_claude_state_payload = _claude_state.sanitize_oauth_claude_state_payload
_sanitize_codex_claude_state_payload = _claude_state.sanitize_codex_claude_state_payload


_CLAUDE_GATEWAY_SENSITIVE_STATE_KEYS = (
    "oauthAccount",
    "provider",
    "api_key",
    "userID",
    "cachedExtraUsageDisabledReason",
    "customApiKeyResponses",
    "passesEligibilityCache",
    "s1mAccessCache",
    "hasAvailableSubscription",
    "penguinModeOrgEnabled",
    "subscriptionNoticeCount",
)


_strip_claude_restore_state = _claude_state.strip_claude_restore_state
_load_project_scoped_claude_resume_session_id = _claude_session.load_project_scoped_claude_resume_session_id
_overlay_project_scoped_claude_resume_state = _claude_session.overlay_project_scoped_claude_resume_state
_ensure_claude_project_trust = _claude_state.ensure_claude_project_trust
_copy_claude_state_json = _claude_state.copy_claude_state_json
_parse_iso8601_utc = _claude_state.parse_iso8601_utc
_merge_oauth_token_state = _claude_state.merge_oauth_token_state
_merge_oauth_claude_state_payload = _claude_state.merge_oauth_claude_state_payload


_masked_exposure_env_value = _runtime_exposure.masked_exposure_env_value
inspect_runtime_exposure = _runtime_exposure.inspect_runtime_exposure


_build_claude_session_settings = _claude_settings.build_claude_session_settings
_write_claude_session_settings = _claude_settings.write_claude_session_settings
_seed_oauth_claude_session_settings = _claude_settings.seed_oauth_claude_session_settings


def _gateway_ping(base_url, api_key, runtime=None):
    """Quick connectivity check; returns True/False/None (None = can't determine)."""
    _ensure_bridge_helpers()
    try:
        import httpx as _httpx  # noqa: F401
    except ImportError:
        return None
    if not base_url or not api_key:
        return None
    models_url = _build_gateway_url(base_url, "/models")
    headers = {"Authorization": f"Bearer {api_key}"}
    anthropic_base = str(_anthropic_base_url(runtime or {}) or "").strip().rstrip("/")
    if anthropic_base and anthropic_base == str(base_url or "").strip().rstrip("/"):
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    try:
        r = _runtime_httpx_request(
            "GET",
            models_url,
            runtime=runtime,
            headers=headers,
            timeout=8,
        )
        return 200 <= int(getattr(r, "status_code", 0) or 0) < 300
    except Exception:
        return False


def _load_gateway_health_cache():
    return _load_gateway_health_cache_impl(HEALTH_CHECK_PATH)


def _save_gateway_health_cache(providers):
    return _save_gateway_health_cache_impl(HEALTH_CHECK_PATH, providers)


def _health_check_due(provider_id):
    return _health_check_due_impl(_load_gateway_health_cache(), provider_id)


def gateway_health_check(provider):
    """Daily first-use connectivity check for gateway providers."""
    if provider.get("skip_gateway_health_check"):
        return
    provider_id = provider.get("id", "default")
    if not _health_check_due(provider_id):
        return
    base_url = _openai_base_url(provider) or _anthropic_base_url(provider)
    api_key = provider.get("api_key", "")
    ok = _gateway_ping(base_url, api_key, runtime=provider)
    if ok is None:
        return
    providers = _load_gateway_health_cache()
    providers[provider_id] = {
        "timestamp": datetime.now().isoformat(),
        "ok": bool(ok),
    }
    _save_gateway_health_cache(providers)
    if ok:
        console.print(f"[dim]✓ gateway {base_url} 可达[/dim]")
    else:
        console.print(f"[yellow]⚠ gateway {base_url} 健康检查未通过，连接可能不稳定[/yellow]")


_provider_protocols = _runtime_urls.provider_protocols
_provider_supports_cli = _runtime_validation.provider_supports_cli
validate_provider_for_cli = _runtime_validation.validate_provider_for_cli
_scrub_claude_oauth_env = _scrub_claude_oauth_env_impl
_scrub_inherited_runtime_env = _scrub_inherited_runtime_env_impl


def _account_env(account, *, validate_proxy=True, model_info=None):
    """Compatibility wrapper for OAuth/account runtime env materialization."""
    from mms_launcher.account_env import build_account_env

    return build_account_env(
        account,
        validate_proxy=validate_proxy,
        model_info=model_info,
    )


_overlay_codex_shared_resume = _codex_assets.overlay_codex_shared_resume


_CODEX_BOUNDED_RESUME_FILES = {
    "history.jsonl": 200,
    "session_index.jsonl": 50,
}

_CODEX_BOUNDED_RESUME_DIRS = {
    "sessions": 25,
    "shell_snapshots": 20,
    "archived_sessions": 0,
}

_CODEX_RESUME_SEED_MANIFEST = "mms-resume-seed.json"
_CODEX_RESUME_WRITEBACK_MANIFEST = "mms-resume-writeback.json"
_CODEX_RESUME_WRITEBACK_ROOT_ENV = "MMS_CODEX_RESUME_WRITEBACK_ROOT"
_CODEX_RESUME_MAX_FILE_BYTES = 2_000_000
_CODEX_RESUME_PROJECT_MAX_FILE_BYTES = 32_000_000
_CODEX_COPY_INTO_SESSION_FILES = {"installation_id"}
_CODEX_PLUGIN_MARKETPLACE_CACHE_ENTRIES = (
    "plugins",
    "plugins.sha",
    "bundled-marketplaces",
)
_CODEX_SESSION_LOCAL_ONLY_ENTRIES = {
    ".codex-global-state.json",
    ".tmp",
    "models_cache.json",
    "version.json",
    "sqlite",
    "tmp",
    "app-server-control",
    "app-server-daemon",
}
_CODEX_SESSION_LOCAL_ONLY_PREFIXES = (
    ".codex-global-state.json.",
    ".codex-global-state.json.tmp-",
    "app-server-",
)


_materialize_codex_session_entry = _codex_assets.materialize_codex_session_entry
_overlay_codex_plugin_marketplace_cache = _codex_assets.overlay_codex_plugin_marketplace_cache
_codex_entry_is_session_local = _codex_assets.codex_entry_is_session_local
_bounded_env_int = _codex_resume._bounded_env_int
_first_existing_child = _codex_resume._first_existing_child
_existing_children = _codex_resume._existing_children
_copy_tail_lines = _codex_resume._copy_tail_lines
_safe_relative_path = _codex_resume._safe_relative_path
_codex_session_file_cwd = _codex_resume._codex_session_file_cwd
_path_is_same_or_child = _codex_resume._path_is_same_or_child
_copy_latest_files_from_roots = _codex_resume._copy_latest_files_from_roots
_copy_latest_files = _codex_resume._copy_latest_files
_codex_sibling_session_roots = _codex_resume._codex_sibling_session_roots
_seed_codex_bounded_resume = _codex_resume._seed_codex_bounded_resume
_set_codex_resume_writeback_root = _codex_resume._set_codex_resume_writeback_root


def _mms_resume_command_name():
    return "mms"


def _print_mms_resume_hint(cli_name, session_id):
    """Compatibility wrapper for MMS resume hint display."""
    from mms_display.launch import print_mms_resume_hint

    return print_mms_resume_hint(
        cli_name,
        session_id,
        resume_command_name_fn=_mms_resume_command_name,
        console=console,
    )


_codex_index_records = _codex_resume._codex_index_records
_codex_resume_record_fingerprint = _codex_resume._codex_resume_record_fingerprint
_codex_resume_index_snapshot = _codex_resume._codex_resume_index_snapshot
_codex_resume_sort_key = _codex_resume._codex_resume_sort_key
_codex_resume_hint_session_id = _codex_resume._codex_resume_hint_session_id
_merge_tail_lines = _codex_resume._merge_tail_lines
_copy_resume_dir_back = _codex_resume._copy_resume_dir_back
_sync_codex_bounded_resume_back = _codex_resume._sync_codex_bounded_resume_back


_write_codex_hook_trust_cache = _codex_hook_trust._write_codex_hook_trust_cache
_sync_codex_hook_trust_back = _codex_hook_trust._sync_codex_hook_trust_back


_sync_codex_bounded_resume_back_from_env = _codex_resume._sync_codex_bounded_resume_back_from_env
_codex_resume_writeback_callback = _codex_resume._codex_resume_writeback_callback
_codex_bounded_resume_entries = _codex_resume._codex_bounded_resume_entries


_link_shared_dotfiles = _session_assets.link_shared_dotfiles
_link_real_local_bin = _claude_session.link_real_local_bin
_link_claude_library_entries = _claude_session.link_claude_library_entries
_ensure_account_library_entries = _claude_session.ensure_account_library_entries


_macos_security_bin = _agy_security.macos_security_bin
_agy_keychain_path = _agy_security.agy_keychain_path
_agy_security_home_env = _agy_security.agy_security_home_env
_run_agy_security_command = _agy_security.run_agy_security_command
_ensure_agy_account_keychain = _agy_security.ensure_agy_account_keychain
_install_agy_security_wrapper = _agy_security.install_agy_security_wrapper


_link_account_library_entries = _claude_session.link_account_library_entries


def _filter_real_home_wrapper_path(path_value, *, session_home=None):
    from mms_launcher.export import filter_real_home_wrapper_path

    return filter_real_home_wrapper_path(
        path_value,
        session_home=session_home,
        real_user_home=_real_user_home,
        environ=os.environ,
    )


def _real_home_wrapper_search_path(session_home, env=None):
    from mms_launcher.export import real_home_wrapper_search_path

    return real_home_wrapper_search_path(
        session_home,
        env,
        real_user_home=_real_user_home,
        environ=os.environ,
        filter_real_home_wrapper_path=_filter_real_home_wrapper_path,
        dedupe_path_parts=_dedupe_path_parts,
        cli_search_dirs=cli_search_dirs,
    )


def _install_chrome_host_wrapper(wrapper_dir, env, wrapper_path_env):
    from mms_launcher.export import install_chrome_host_wrapper

    return install_chrome_host_wrapper(
        wrapper_dir,
        env,
        wrapper_path_env,
        real_user_home=_real_user_home,
        real_user_path=_real_user_path,
        real_home_wrapper_scrub_lines=_real_home_wrapper_scrub_lines,
        write_real_home_script=_write_real_home_script,
    )


def _install_session_command_wrappers(session_home, env):
    from mms_launcher.export import install_session_command_wrappers

    return install_session_command_wrappers(
        session_home,
        env,
        real_user_home=_real_user_home,
        real_user_path=_real_user_path,
        real_home_wrapper_search_path=_real_home_wrapper_search_path,
        real_home_wrapper_scrub_lines=_real_home_wrapper_scrub_lines,
        write_real_home_script=_write_real_home_script,
        install_chrome_host_wrapper=_install_chrome_host_wrapper,
        wrapper_commands=_SESSION_REAL_HOME_WRAPPER_COMMANDS,
        mms_toon_script_path=_mms_toon_script_path,
        mms_context_script_path=_mms_context_script_path,
        mms_gain_script_path=_mms_gain_script_path,
        token_saver_script_path=_token_saver_script_path,
        token_gain_script_path=_token_gain_script_path,
        xmem_cli_path=_xmem_cli_path,
    )


def _resolve_real_home_command_path(command_name, env=None):
    """Compatibility wrapper for real-home command lookup."""
    from mms_launcher.export import resolve_real_home_command_path

    return resolve_real_home_command_path(
        command_name,
        env,
        environ=os.environ,
        real_home_wrapper_search_path=_real_home_wrapper_search_path,
        which=shutil.which,
        defpath=os.defpath,
    )


def _exit_oauth_claude_manual_only(runtime=None, model_info=None, *, caller="MMS"):
    """Compatibility wrapper for OAuth Claude manual-only hard cut."""
    from mms_launcher.mmc import exit_oauth_claude_manual_only

    return exit_oauth_claude_manual_only(runtime, model_info, caller=caller)


_sync_codex_session_claude_json = _codex_claude_state.sync_codex_session_claude_json


def _toml_quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def _toml_literal(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return _toml_quote(value)


def _toml_bare_key(key):
    import re
    if re.fullmatch(r"[A-Za-z0-9_-]+", str(key)):
        return str(key)
    escaped = str(key).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


_strip_codex_mcp_server_blocks = _codex_claude_state.strip_codex_mcp_server_blocks
_append_codex_mcp_servers_from_claude_json = _codex_claude_state.append_codex_mcp_servers_from_claude_json


validate_account_for_cli = _runtime_validation.validate_account_for_cli
_openai_base_url = _runtime_urls.openai_base_url
_anthropic_base_url = _runtime_urls.anthropic_base_url
_anthropic_probe_target = _runtime_urls.anthropic_probe_target
_resolve_model = _runtime_models.resolve_model
_normalized_model_name = _runtime_models.normalized_model_name


_is_claude_family_model_name = _claude_model.is_claude_family_model_name
_claude_visible_model_name = _claude_model.claude_visible_model_name
_apply_claude_visible_model_overrides = _claude_model.apply_claude_visible_model_overrides
_claude_resume_model_name = _claude_model.claude_resume_model_name
_with_1m_suffix = _claude_model.with_1m_suffix
_apply_claude_model_overrides = _claude_model.apply_claude_model_overrides


_resolve_anthropic_base_url = _claude_endpoint.resolve_anthropic_base_url
_pick_gateway_model = _claude_endpoint.pick_gateway_model


_cleanup_stale_sessions = _claude_session.cleanup_stale_sessions
_copy_tree_files_if_missing = _claude_session.copy_tree_files_if_missing
_claude_project_resume_dir_names = _claude_session.claude_project_resume_dir_names
_claude_resume_scope_id = _claude_session.claude_resume_scope_id
_claude_resume_scope_is_model_shared = _claude_session.claude_resume_scope_is_model_shared
_claude_slot_roots_for_resume_backfill = _claude_session.claude_slot_roots_for_resume_backfill
_backfill_real_claude_project_resume_files = _claude_session.backfill_real_claude_project_resume_files
_backfill_claude_project_resume_files = _claude_session.backfill_claude_project_resume_files
_link_claude_persistent_entry = _claude_session.link_claude_persistent_entry
_prepare_claude_session_tree = _claude_session.prepare_claude_session_tree
_sync_claude_session_state_to_account_home = _claude_session.sync_claude_session_state_to_account_home
_finalize_claude_slot = _claude_session.finalize_claude_slot


def _claude_gateway_env(
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
    """Compatibility wrapper for Claude gateway env materialization."""
    from mms_claude.env import build_claude_gateway_env

    return build_claude_gateway_env(
        runtime,
        base_url=base_url,
        auth_token=auth_token,
        heavy_model=heavy_model,
        medium_model=medium_model,
        light_model=light_model,
        selected_model=selected_model,
        runtime_kind=runtime_kind,
        display_model=display_model,
        _timings=_timings,
    )



def _codex_gateway_env(runtime, base_url, model_info=None):
    """Compatibility wrapper for Codex gateway env materialization."""
    from mms_codex.env import build_codex_gateway_env

    return build_codex_gateway_env(runtime, base_url, model_info=model_info)

def _is_gpt_model(model_name):
    """Check if a model name is a GPT/OpenAI model (supports Responses API natively)."""
    if not model_name:
        return False
    lower = model_name.lower()
    return any(kw in lower for kw in ("gpt-", "gpt4", "gpt5", "o1", "o3", "o4", "codex-"))


def _codex_provider_base_url(base_url):
    normalized = (base_url or "").rstrip("/")
    if normalized and not normalized.endswith("/v1"):
        normalized += "/v1"
    return normalized


def _append_codex_bypass_flags(cmd, runtime):
    """In MMS bypass mode, skip Codex approval and hook-review prompts together."""
    # Contract: isolated MMS/Codex sessions must not stop at startup hook review.
    if not (runtime or {}).get("bypass"):
        return
    for flag in (
        "--dangerously-bypass-approvals-and-sandbox",
        "--dangerously-bypass-hook-trust",
    ):
        if flag not in cmd:
            cmd.append(flag)


def _opencode_run_preflight(env, agent, model_ref, timeout=None, bypass=True):
    return _opencode_run_preflight_impl(
        env,
        agent,
        model_ref,
        timeout=timeout,
        bypass=bypass,
        subprocess_run=subprocess.run,
        perf_counter_fn=perf_counter,
        preflight_timeout=_opencode_preflight_timeout,
    )


def _opencode_select_launch_candidate(runtime, routes, model, env):
    return _opencode_select_launch_candidate_impl(
        runtime,
        routes,
        model,
        env,
        launch_candidates=_opencode_launch_candidates,
        launch_preflight_enabled=_opencode_launch_preflight_enabled,
        run_preflight=_opencode_run_preflight,
        bypass_enabled=_opencode_bypass_enabled,
        console=console,
    )


def _opencode_gateway_health_check(runtime):
    return _opencode_gateway_health_check_impl(
        runtime,
        runtime_routes=_opencode_runtime_routes,
        resolve_model=_resolve_model,
        provider_base_url=_opencode_provider_base_url,
        gateway_health_check=gateway_health_check,
    )
_opencode_model_config = partial(
    _opencode_model_config_impl,
    context_window_resolver=_effective_context_window,
)
_opencode_rtk_plugin_path = partial(
    _opencode_rtk_plugin_path_impl,
    module_file=__file__,
    normalize_session_surface_disabled=_normalize_session_surface_disabled,
    runtime_bool=_opencode_runtime_bool,
    env_bool=_opencode_env_bool,
)
_opencode_xmem_plugin_path = partial(
    _opencode_xmem_plugin_path_impl,
    module_file=__file__,
    normalize_session_surface_disabled=_normalize_session_surface_disabled,
    session_skill_disabled=_session_skill_disabled,
    resolve_xmem_root=_resolve_xmem_root,
    xmem_cli_path=_xmem_cli_path,
)


def _overlay_opencode_rtk_plugin(config_dir, runtime=None):
    return _overlay_opencode_plugin_impl(
        config_dir,
        _opencode_rtk_plugin_path(runtime),
        "mms-rtk.ts",
    )


def _overlay_opencode_xmem_plugin(config_dir, runtime=None):
    return _overlay_opencode_plugin_impl(
        config_dir,
        _opencode_xmem_plugin_path(runtime),
        "mms-xmem.ts",
    )


def _opencode_rtk_plugin_enabled(runtime=None):
    return bool(_opencode_rtk_plugin_path(runtime))


def _opencode_xmem_plugin_enabled(runtime=None):
    return bool(_opencode_xmem_plugin_path(runtime))


_build_opencode_config_payload = partial(
    _opencode_build_config_payload_impl,
    context_window_resolver=_effective_context_window,
)
_build_opencode_config_content = partial(
    _opencode_build_config_content_impl,
    context_window_resolver=_effective_context_window,
)
_write_opencode_config = partial(
    _opencode_write_config_impl,
    build_config_content=_build_opencode_config_content,
    atomic_write_text=atomic_write_text,
)
_opencode_export_config_path = partial(
    _opencode_export_config_path_impl,
    real_user_path=_real_user_path,
)


def _opencode_gateway_env(runtime, model_info=None):
    return _opencode_gateway_env_impl(
        runtime,
        model_info=model_info,
        resolve_model=_resolve_model,
        real_user_path=_real_user_path,
        cleanup_stale_sessions=_cleanup_stale_sessions,
        link_shared_dotfiles=_link_shared_dotfiles,
        scrub_inherited_runtime_env=_scrub_inherited_runtime_env,
        clear_opencode_config_env=_clear_opencode_config_env,
        inject_real_home_hints=_inject_real_home_hints,
        inject_selected_model_name=_inject_selected_model_name,
        set_opencode_soft_home=_set_opencode_soft_home,
        write_opencode_config=_write_opencode_config,
        overlay_opencode_session_assets=_overlay_opencode_session_assets,
        apply_route_env=_opencode_apply_route_env,
        apply_bypass_env=_opencode_apply_bypass_env,
        apply_runtime_network_profile=_apply_runtime_network_profile,
        apply_runtime_locale_profile=_apply_runtime_locale_profile,
        apply_runtime_ip_stack_profile=_apply_runtime_ip_stack_profile,
        install_session_command_wrappers=_install_session_command_wrappers,
        install_session_packet_env=_install_session_packet_env,
        runtime_caveman_enabled=_runtime_caveman_enabled,
        resolve_web_access_root=_resolve_web_access_root,
        resolve_weber_root=_resolve_weber_root,
        resolve_codegraph_root=_resolve_codegraph_root,
        resolve_toon_root=_resolve_toon_root,
        resolve_token_saver_root=_resolve_token_saver_root,
        resolve_xmem_root=_resolve_xmem_root,
        session_skill_disabled=_session_skill_disabled,
        opencode_rtk_plugin_enabled=_opencode_rtk_plugin_enabled,
        opencode_xmem_plugin_enabled=_opencode_xmem_plugin_enabled,
    )


_opencode_global_omo_env = partial(
    _opencode_global_omo_env_impl,
    clear_opencode_config_env=_clear_opencode_config_env,
    inject_real_home_hints=_inject_real_home_hints,
    real_user_path=_real_user_path,
    apply_bypass_env=_opencode_apply_bypass_env,
    apply_runtime_network_profile=_apply_runtime_network_profile,
    apply_runtime_locale_profile=_apply_runtime_locale_profile,
    apply_runtime_ip_stack_profile=_apply_runtime_ip_stack_profile,
)
_opencode_global_command = _opencode_global_command_impl
_opencode_session_command = partial(
    _opencode_session_command_impl,
    default_agent=OPENCODE_LITE_DEFAULT_AGENT,
)


# Pi implementation lives in mms_pi.support; keep the former launcher-private
# names as direct aliases for existing monkeypatch-based tests/callers.
_pi_wrapper_path = _pi_support._pi_wrapper_path
_pi_retry_extension_path = _pi_support._pi_retry_extension_path
_pi_npx_cache_dir = _pi_support._pi_npx_cache_dir
_pi_settings_payload = _pi_support._pi_settings_payload
_pi_provider_ref = _pi_support._pi_provider_ref
_pi_normalize_model_key = _pi_support._pi_normalize_model_key
_pi_reference_payload = _pi_support._pi_reference_payload
_pi_reference_model_row = _pi_support._pi_reference_model_row
_pi_first_positive_int = _pi_support._pi_first_positive_int
_pi_hint_max_tokens = _pi_support._pi_hint_max_tokens
_pi_hint_context_window = _pi_support._pi_hint_context_window
_pi_reference_supports_vision = _pi_support._pi_reference_supports_vision
_pi_model_supported = _pi_support._pi_model_supported
_pi_model_replacement = _pi_support._pi_model_replacement
_pi_model_block_reason = _pi_support._pi_model_block_reason
_pi_model_available_for_runtime = _pi_support._pi_model_available_for_runtime
_pi_exposed_model_names = _pi_support._pi_exposed_model_names
_pi_model_input_types = _pi_support._pi_model_input_types
_pi_model_capabilities = _pi_support._pi_model_capabilities
_pi_anthropic_base_root = _pi_support._pi_anthropic_base_root
_pi_openai_base_url = _pi_support._pi_openai_base_url
_pi_protocol_variant = _pi_support._pi_protocol_variant
_pi_protocol_variants = _pi_support._pi_protocol_variants
_pi_runtime_model_names = _pi_support._pi_runtime_model_names
_pi_profile_id = _pi_support._pi_profile_id
_pi_pick_protocol = _pi_support._pi_pick_protocol
_pi_provider_compat = _pi_support._pi_provider_compat
_pi_model_compat = _pi_support._pi_model_compat
_pi_model_thinking_level_map = _pi_support._pi_model_thinking_level_map
_pi_effective_selected_model = _pi_support._pi_effective_selected_model
_pi_wire_model_name = _pi_support._pi_wire_model_name
_pi_model_entry = _pi_support._pi_model_entry
_pi_group_provider_ref = _pi_support._pi_group_provider_ref
_pi_build_models_payload = _pi_support._pi_build_models_payload
_pi_gateway_env = _pi_support._pi_gateway_env
_pi_provider_export_env = _pi_support._pi_provider_export_env
launch_pi = _pi_support.launch_pi

def launch_opencode(model_info, runtime, once=False):
    """启动 OpenCode，通过 OpenAI-compatible provider 注入 session-local config。"""
    return _opencode_launch_impl(
        model_info,
        runtime,
        once=once,
        entrypoint=_opencode_entrypoint,
        global_omo_env=_opencode_global_omo_env,
        global_command=_opencode_global_command,
        exec_or_run=_exec_or_run,
        gateway_health_check=_opencode_gateway_health_check,
        resolve_model=_resolve_model,
        runtime_routes=_opencode_runtime_routes,
        gateway_env=_opencode_gateway_env,
        select_launch_candidate=_opencode_select_launch_candidate,
        console=console,
        sys_exit=sys.exit,
        inject_selected_model_name=_inject_selected_model_name,
        install_session_packet_env=_install_session_packet_env,
        session_command=_opencode_session_command,
    )


def launch_gemini(model_info, runtime, once=False):
    """启动 Gemini，当前只支持官方账号档案模式。"""
    auth_mode = runtime.get("auth_mode", "api_key")
    if auth_mode != "oauth":
        console.print("[red]Gemini 当前只支持官方账号入口，不支持直接使用模型源启动[/red]")
        sys.exit(1)

    env = _account_env(runtime, model_info=model_info)
    _prepare_oauth_home_context(runtime, env, "gemini")
    model = _resolve_model(model_info)
    cmd = ["gemini"]
    if model:
        cmd += ["-m", model]
    _exec_or_run(cmd, env, once)


def launch_agy(model_info, runtime, once=False):
    """启动 Antigravity CLI，当前只支持官方账号档案模式。"""
    auth_mode = runtime.get("auth_mode", "api_key")
    if auth_mode != "oauth":
        console.print("[red]Antigravity CLI 当前只支持官方账号入口，不支持直接使用模型源启动[/red]")
        sys.exit(1)

    env = _account_env(runtime, model_info=model_info)
    _prepare_oauth_home_context(runtime, env, "agy")
    cmd = ["agy"]
    if runtime.get("bypass"):
        cmd.append("--dangerously-skip-permissions")
    if runtime.get("agy_sandbox") or runtime.get("sandbox"):
        cmd.append("--sandbox")
    _exec_or_run(cmd, env, once)


LAUNCHERS = {
    "claude": launch_claude,
    "codex": launch_codex,
    "opencode": launch_opencode,
    "pi": launch_pi,
    "gemini": launch_gemini,
    "agy": launch_agy,
}


_is_opencode_global_profile_runtime = _opencode_is_global_profile_runtime_impl
_opencode_global_export_env = partial(
    _opencode_global_export_env_impl,
    apply_bypass_env=_opencode_apply_bypass_env,
)
_opencode_provider_export_env = partial(
    _opencode_provider_export_env_impl,
    export_config_path=_opencode_export_config_path,
    write_opencode_config=_write_opencode_config,
    apply_route_env=_opencode_apply_route_env,
    apply_bypass_env=_opencode_apply_bypass_env,
)


def _runtime_with_export_model(runtime, model_info=None):
    runtime = dict(runtime) if isinstance(runtime, dict) else {}
    resolved_model = _resolve_model(model_info or runtime)
    if resolved_model and not _resolve_model(runtime):
        runtime["model"] = resolved_model
    return runtime


def get_export_env(cli, runtime, model_info=None):
    """返回指定 CLI 需要的 export 环境变量字典。"""
    from mms_launcher.export import build_export_env

    return build_export_env(
        cli,
        runtime,
        model_info=model_info,
        runtime_with_export_model=_runtime_with_export_model,
        is_opencode_global_profile_runtime=_is_opencode_global_profile_runtime,
        opencode_global_export_env=_opencode_global_export_env,
        validate_account_for_cli=validate_account_for_cli,
        validate_provider_for_cli=validate_provider_for_cli,
        anthropic_base_url=_anthropic_base_url,
        openai_base_url=_openai_base_url,
        resolve_model=_resolve_model,
        opencode_provider_export_env=_opencode_provider_export_env,
        pi_provider_export_env=_pi_provider_export_env,
        inject_host_capability_hints=_inject_host_capability_hints,
        mms_toon_script_path=_mms_toon_script_path,
        mms_context_script_path=_mms_context_script_path,
        mms_gain_script_path=_mms_gain_script_path,
        token_saver_script_path=_token_saver_script_path,
        token_gain_script_path=_token_gain_script_path,
        xmem_cli_path=_xmem_cli_path,
        safe_getcwd=_safe_getcwd,
    )


_show_launch_info = _show_launch_info_impl


def launch_cli(cli, model_info, runtime, once=False, extra_args=None):
    """Compatibility wrapper for the unified launcher dispatch entrypoint."""
    from mms_launcher.dispatch import launch_cli as launch_cli_dispatch

    return launch_cli_dispatch(
        cli,
        model_info,
        runtime,
        once=once,
        extra_args=extra_args,
        launchers=LAUNCHERS,
        console=console,
        validate_account_for_cli_fn=validate_account_for_cli,
        validate_provider_for_cli_fn=validate_provider_for_cli,
        is_opencode_global_profile_runtime_fn=_is_opencode_global_profile_runtime,
        enforce_claude_network_guard_or_exit_fn=_enforce_claude_network_guard_or_exit,
        claude_bypass_requires_proxy_fn=_claude_bypass_requires_proxy,
        resolve_model_fn=_resolve_model,
        exit_oauth_claude_manual_only_fn=_exit_oauth_claude_manual_only,
        probe_models_fn=_probe_models,
        launch_status_fn=_launch_status,
        print_launch_step_done_fn=_print_launch_step_done,
        show_launch_info_fn=_show_launch_info,
        exit_fn=sys.exit,
    )


_print_session_summary = _print_session_summary_impl


def _exec_or_run(
    cmd,
    env,
    once,
    cleanup_path=None,
    state_home=None,
    cleanup_context=None,
    exit_callback=None,
    force_subprocess=False,
    bridge_info=None,
):
    """Compatibility wrapper for launcher process execution."""
    return _exec_or_run_impl(
        cmd,
        env,
        once,
        cleanup_path=cleanup_path,
        state_home=state_home,
        cleanup_context=cleanup_context,
        exit_callback=exit_callback,
        force_subprocess=force_subprocess,
        bridge_info=bridge_info,
        prepare_cli_command_fn=prepare_cli_command,
        console=console,
        activated_state=activated_claude_account_state,
        record_session_child_pid=_record_session_child_pid,
        print_session_summary=_print_session_summary,
    )
